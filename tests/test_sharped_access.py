"""Mocked access onboarding, verified website workflow and private storage guards."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys,time,threading,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from PySide6.QtCore import QCoreApplication,QEvent,QSettings,QTimer
from PySide6.QtWidgets import QApplication,QDialog,QLabel,QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QCheckBox,QRadioButton
from PySide6.QtTest import QTest
from phase_studio import requirements as req
from phase_studio.credentials import CredentialStore,credential_origin
from phase_studio.sharped_access import SharpEDAccessDialog
from phase_studio.error_reporting import sanitize_error_details
from phase_studio.sharped_server_client import DEFAULT_SERVER_URL

KEY='SYNTHETIC-UI-KEY-'+('x'*48)
OTHER='SYNTHETIC-REPLACEMENT-'+('y'*48)

class MemorySecureBackend:
    def __init__(self):self.values={};self.writes=[];self.deletes=[]
    def read(self,origin):return self.values.get(origin,'')
    def write(self,origin,key):self.values[origin]=key;self.writes.append((origin,key))
    def delete(self,origin):self.values.pop(origin,None);self.deletes.append(origin)

class MemorySettings:
    def __init__(self,values=None):self.values=dict(values or {})
    def value(self,key,default=None):return self.values.get(key,default)
    def remove(self,key):self.values.pop(key,None)
    def sync(self):pass

class CredentialStorageTests(unittest.TestCase):
    def test_session_only_does_not_write_storage(self):
        backend=MemorySecureBackend();store=CredentialStore(backend)
        store.set(KEY,remember=False)
        self.assertEqual(store.get(),KEY)
        self.assertEqual(backend.writes,[])
        self.assertFalse(store.remembered())
    def test_remember_replace_and_remove(self):
        backend=MemorySecureBackend();store=CredentialStore(backend)
        store.set(KEY,remember=True);store.set(OTHER,remember=True)
        self.assertEqual(CredentialStore(backend).get(),OTHER)
        store.remove()
        self.assertEqual(store.get(),'')
        self.assertEqual(CredentialStore(backend).get(),'')
    def test_session_only_choice_preserves_previously_saved_key(self):
        backend=MemorySecureBackend();store=CredentialStore(backend)
        store.set(KEY,remember=True);store.set(OTHER,remember=False)
        self.assertEqual(store.get(),OTHER)
        self.assertEqual(CredentialStore(backend).get(),KEY)
    def test_legacy_plaintext_migration_secures_key_before_scrubbing_matching_stores(self):
        shared=MemorySettings({'inputs/sharped_api_token':KEY,'inputs/cycles':3})
        legacy=MemorySettings({'api_token':OTHER,'model':'preserved-model'})
        backend=MemorySecureBackend();store=CredentialStore(backend)
        self.assertEqual(store.load_settings(shared,legacy),KEY)
        self.assertNotIn('inputs/sharped_api_token',shared.values)
        self.assertEqual(legacy.values['api_token'],OTHER)
        self.assertEqual(shared.values['inputs/cycles'],3)
        self.assertEqual(legacy.values['model'],'preserved-model')
        self.assertEqual(CredentialStore(backend).get(),KEY)
    def test_no_secure_backend_never_falls_back_to_plaintext(self):
        store=CredentialStore()
        with self.assertRaises(OSError):store.set(KEY,remember=True)
        self.assertEqual(store.get(),'')
        store.set(KEY)
        self.assertEqual(store.get(),KEY)
    def test_saved_credentials_are_scoped_to_api_origin(self):
        backend=MemorySecureBackend();store=CredentialStore(backend)
        store.set(KEY,remember=True,base_url='https://jana.fzu.cz')
        self.assertEqual(store.get('https://sharped.fzu.cz'),'')
        self.assertEqual(store.get('https://jana.fzu.cz/'),KEY)
        self.assertNotEqual(credential_origin('https://jana.fzu.cz:444'),credential_origin(DEFAULT_SERVER_URL))
    def test_invalid_old_server_address_does_not_block_settings_repair(self):
        backend=MemorySecureBackend();store=CredentialStore(backend)
        shared=MemorySettings({'inputs/sharped_api_token':KEY,'inputs/cycles':3})
        self.assertEqual(store.load_settings(shared,base_url='invalid old address'),KEY)
        self.assertFalse(store.remembered('invalid old address'))
        self.assertEqual(backend.writes,[])
        self.assertEqual(shared.values['inputs/sharped_api_token'],KEY)
        self.assertEqual(shared.values['inputs/cycles'],3)
    def test_configured_key_redacted_even_when_server_echoes_it_without_label(self):
        store=CredentialStore();store.set(KEY)
        text=sanitize_error_details('Server echoed '+KEY+'; Authorization: Bearer '+KEY)
        self.assertNotIn(KEY,text)
        self.assertIn('[REDACTED]',text)
    def test_native_credential_structure_and_payload_use_wincred(self):
        if os.name!='nt':self.skipTest('Windows structure')
        import ctypes
        from phase_studio.credentials import WindowsCredentialBackend
        backend=WindowsCredentialBackend()
        self.assertEqual(ctypes.sizeof(backend.Credential),80 if ctypes.sizeof(ctypes.c_void_p)==8 else 52)
        captured=[]
        def write(pointer,flags):
            value=ctypes.cast(pointer,ctypes.POINTER(backend.Credential)).contents
            captured.append((value.Type,value.Persist,ctypes.string_at(value.CredentialBlob,value.CredentialBlobSize)))
            return True
        backend.api=SimpleNamespace(CredWriteW=write)
        backend.write(credential_origin(DEFAULT_SERVER_URL),KEY)
        self.assertEqual(captured,[(1,2,KEY.encode('utf8'))])

class AccessDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owns_app=QApplication.instance() is None
        cls.app=QApplication.instance() or QApplication([])
        from phase_studio.ui_style import apply_phase_studio_style
        apply_phase_studio_style(cls.app)
    @classmethod
    def tearDownClass(cls):
        if cls.owns_app:
            import shiboken6
            cls.app.processEvents();shiboken6.delete(cls.app);cls.app=None
    def setUp(self):
        self.backend=MemorySecureBackend();self.store=CredentialStore(self.backend)
        self.calls=[]
        self.status=req.RequirementStatus(req.RequirementKind.SHARPED,req.RequirementState.OK)
        def verify(key):self.calls.append(key);return self.status
        self.dialog=SharpEDAccessDialog(None,req.RequirementStatus(req.RequirementKind.SHARPED,req.RequirementState.TOKEN_MISSING),verify=verify,store=self.store)
        self.dialog.show();self.app.processEvents()
    def tearDown(self):
        QTest.qWait(360)
        self.dialog.close();self.dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    def wait_probe(self):
        deadline=time.monotonic()+2
        while self.dialog._connecting and time.monotonic()<deadline:QTest.qWait(10)
        self.assertFalse(self.dialog._connecting)
    def test_unavailable_storage_instructions_do_not_offer_disabled_remember(self):
        dialog=SharpEDAccessDialog(None,store=CredentialStore(backend=None))
        try:
            text=' '.join(label.text() for label in dialog.findChildren(QLabel))
            self.assertFalse(dialog.remember.isEnabled())
            self.assertNotIn('Uncheck Remember',text)
            self.assertIn('session only',text)
        finally:
            dialog.deleteLater()
    def enter_and_connect(self,key=KEY):
        self.dialog.key_edit.setText(key);self.dialog.connect_button.click();self.wait_probe()
    def test_missing_key_is_normal_onboarding_not_an_error_banner(self):
        self.assertEqual(self.dialog.windowTitle(),'Connect to SharpED')
        self.assertFalse(self.dialog.feedback.isVisible())
        self.assertEqual(self.dialog.findChild(QLabel,'sharpedAccountSubtitle').text(),"Use your existing Jana2020 account to access SharpED's online electron-density processing.")
    def test_empty_key_shows_help_without_request(self):
        self.dialog.connect_button.click()
        self.assertEqual(self.calls,[])
        self.assertEqual(self.dialog.feedback.text(),'Enter your SharpED access key to continue.')
    def test_verified_token_page_and_exact_confirmed_web_steps(self):
        self.assertEqual(req.SHARPED_ACCOUNT_URL,'https://sharped.fzu.cz/sharp-ed')
        self.assertEqual(self.dialog.account_button.text(),'Get an access key \u2197')
        with patch('phase_studio.sharped_access.QDesktopServices.openUrl') as open_url:
            self.dialog.account_button.click()
            self.assertEqual(open_url.call_args.args[0].toString(),'https://sharped.fzu.cz/sharp-ed')
        instructions=self.dialog.findChild(QLabel,'sharpedAccessInstructions').text()
        for phrase in ('Jana2020 account if prompted','API tokens for desktop application','Show','New token name','Create token','SharpED Tool'):
            self.assertIn(phrase,instructions)
        self.assertIn('redirect',instructions)
        self.assertNotIn('account settings',instructions)
    def test_no_separate_account_registration_or_desktop_password(self):
        text=' '.join(label.text() for label in self.dialog.findChildren(QLabel))
        self.assertIn('existing Jana2020 account',text)
        self.assertNotIn('Create a SharpED account',text)
        self.assertNotIn('https://jana.fzu.cz/login',text)
        self.assertEqual(len(self.dialog.findChildren(QLineEdit)),1)
    def test_hidden_key_show_hide_is_explicit(self):
        self.dialog.key_edit.setText(KEY)
        self.assertEqual(self.dialog.key_edit.echoMode(),QLineEdit.Password)
        self.dialog.show_button.click()
        self.assertEqual(self.dialog.key_edit.echoMode(),QLineEdit.Normal)
        self.assertEqual(self.dialog.show_button.text(),'Hide')
        self.dialog.show_button.click()
        self.assertEqual(self.dialog.key_edit.echoMode(),QLineEdit.Password)
    def test_connection_success_persists_key_without_claiming_token_validation(self):
        self.enter_and_connect()
        self.assertEqual(self.dialog.selected_key,KEY)
        self.assertEqual(self.store.get(),KEY)
        self.assertEqual(CredentialStore(self.backend).get(),KEY)
        self.assertEqual(self.dialog.result(),QDialog.Accepted)
        self.assertIn('permission is confirmed',self.dialog.findChild(QLabel,'sharpedVerificationNote').text())
    def test_invalid_key_retains_workflow_and_allows_retry(self):
        self.status=req.RequirementStatus(req.RequirementKind.SHARPED,req.RequirementState.TOKEN_REJECTED)
        self.enter_and_connect()
        self.assertIsNone(self.dialog.selected_key)
        self.assertIn('not accepted',self.dialog.feedback.text())
        self.assertEqual(self.store.get(),'')
        self.status=req.RequirementStatus(req.RequirementKind.SHARPED,req.RequirementState.OK)
        self.enter_and_connect(OTHER)
        self.assertEqual(self.calls,[KEY,OTHER])
        self.assertEqual(self.dialog.selected_key,OTHER)
    def test_forbidden_is_account_access_not_unproven_subscription(self):
        self.status=req._classify_sharped_error(SimpleNamespaceError(403))
        self.enter_and_connect()
        self.assertEqual(self.status.state,req.RequirementState.ACCESS_DENIED)
        self.assertIn('permission',self.dialog.feedback.text())
        self.assertNotIn('subscription',self.dialog.feedback.text())
    def test_timeout_reports_connection_problem_not_bad_key(self):
        self.status=req._classify_sharped_error(TimeoutError('timeout '+KEY))
        self.enter_and_connect()
        self.assertIn('internet connection',self.dialog.feedback.text())
        self.assertNotIn(KEY,self.dialog.feedback.text())
        self.assertNotIn('not accepted',self.dialog.feedback.text())
    def test_server_unavailable_is_retryable_without_changing_key(self):
        self.status=req._classify_sharped_error(SimpleNamespaceError(503))
        self.enter_and_connect()
        self.assertIn('temporarily unavailable',self.dialog.feedback.text())
        self.assertEqual(self.dialog.key_edit.text(),KEY)
    def test_connection_status_requires_successful_probe_and_survives_retry(self):
        from phase_studio.sharped_access import connection_status
        self.assertEqual(connection_status(self.store),'Not connected')
        self.store.set(KEY,remember=True)
        self.assertEqual(connection_status(self.store),'Credentials available — not yet verified')
        self.status=req._classify_sharped_error(SimpleNamespaceError(503))
        self.enter_and_connect()
        self.assertEqual(connection_status(self.store),'Connection unavailable')
        self.assertEqual(self.store.get(),KEY)
        self.status=req.RequirementStatus(req.RequirementKind.SHARPED,req.RequirementState.OK)
        self.enter_and_connect()
        self.assertEqual(connection_status(self.store),'Credentials available — not yet verified')
        self.store.set(OTHER,remember=True)
        self.assertEqual(connection_status(self.store),'Credentials available — not yet verified')
        self.store.remove()
        self.assertEqual(connection_status(self.store),'Not connected')
    def test_back_does_not_change_credential_or_start_workflow(self):
        self.dialog.key_edit.setText(KEY);self.dialog.back_button.click()
        self.assertIsNone(self.dialog.selected_key)
        self.assertEqual(self.calls,[])
        self.assertEqual(self.store.get(),'')
        self.assertEqual(self.dialog.result(),QDialog.Rejected)
    def test_back_while_connecting_ignores_late_result(self):
        gate=threading.Event()
        def verify(key):gate.wait(1);return self.status
        self.dialog.verify=verify
        self.dialog.key_edit.setText(KEY);self.dialog.connect_button.click()
        self.assertTrue(self.dialog._connecting)
        self.assertEqual(self.dialog.connect_button.text(),'Connecting\u2026')
        self.dialog.back_button.click();gate.set();QTest.qWait(80)
        self.assertIsNone(self.dialog.selected_key)
        self.assertEqual(self.store.get(),'')
    def test_remember_persists_only_to_secure_backend(self):
        self.dialog.remember.setChecked(True);self.enter_and_connect()
        self.assertEqual(CredentialStore(self.backend).get(),KEY)
    def test_live_full_configuration_and_wizard_fields_follow_replace_and_remove(self):
        full=QLineEdit();wizard=QLineEdit()
        self.store.bind_input(full);self.store.bind_input(wizard)
        self.store.set(KEY)
        self.app.processEvents()
        self.assertEqual((full.text(),wizard.text()),(KEY,KEY))
        self.store.set(OTHER)
        self.app.processEvents()
        self.assertEqual((full.text(),wizard.text()),(OTHER,OTHER))
        self.store.remove()
        self.app.processEvents()
        self.assertEqual((full.text(),wizard.text()),('',''))
        self.store.save_input(full.text());self.store.save_input(wizard.text())
        self.assertEqual(CredentialStore(self.backend).get(),'')
        full.deleteLater();wizard.deleteLater()
    def test_storage_failure_never_accepts_or_writes_plaintext(self):
        self.backend.write=lambda *args:(_ for _ in ()).throw(OSError('failed '+KEY))
        self.dialog.remember.setChecked(True);self.enter_and_connect()
        self.assertIsNone(self.dialog.selected_key)
        self.assertIn('could not be saved securely',self.dialog.feedback.text())
        self.assertNotIn(KEY,self.dialog.feedback.text())
        self.dialog.remember.setChecked(False);self.enter_and_connect()
        self.assertEqual(self.dialog.selected_key,KEY)
    def test_replace_saved_key_and_remove_access(self):
        self.store.set(KEY,remember=True)
        self.dialog.management_button.setChecked(True)
        self.dialog.key_edit.setText(KEY);self.dialog.replace_button.click()
        self.assertEqual(self.dialog.key_edit.text(),'')
        self.dialog.remember.setChecked(True);self.enter_and_connect(OTHER)
        self.assertEqual(CredentialStore(self.backend).get(),OTHER)
        # Inspect the same removal authority without initiating another request.
        self.dialog._closed=False;self.dialog._remove_key()
        self.assertEqual(self.store.get(),'')
        self.assertEqual(CredentialStore(self.backend).get(),'')
    def test_dialog_is_owned_modal_with_fixed_footer_and_no_oauth(self):
        self.assertTrue(self.dialog.isModal())
        self.assertLess(self.dialog._footer.geometry().bottom(),self.dialog.height())
        self.assertEqual(DEFAULT_SERVER_URL,'https://jana.fzu.cz/')
        text=' '.join(label.text() for label in self.dialog.findChildren(QLabel))
        self.assertNotIn('OAuth',text)
        self.assertNotIn('Sign in with Jana2020',self.dialog.connect_button.text())
    def test_probe_uses_only_existing_public_catalogue_not_inference(self):
        calls=[]
        class Client:
            def __init__(self,**kwargs):calls.append(kwargs)
            def get_models(self):calls.append('models');return SimpleNamespace(models=['existing'],default_model='existing')
            def execute(self,*args):raise AssertionError('Inference is forbidden in onboarding')
        status=req.check_sharped_api(DEFAULT_SERVER_URL,KEY,client_factory=Client)
        self.assertTrue(status.ok)
        self.assertEqual(calls[1],'models')
        self.assertEqual(calls[0]['base_url'],DEFAULT_SERVER_URL)

    def _wizard_account_round_trip(self, connect, remove=False):
        from phase_studio import jana_superflip as js
        import phase_studio.sharped_access as access
        self.dialog.close()
        if remove:
            self.store.set(KEY,remember=True)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            inflip=root/'fixture.inflip'
            inflip.write_text('title auth_fixture\nperform CF\ndimension 3\ncell 10 10 10 90 90 90\nspacegroup P1\ncomposition C2\ndataformat intensity\nfbegin\n1 0 0 10 2\nendf\n',encoding='utf8')
            real_imports=js._qt_imports
            def qt_imports():
                qt=real_imports()
                qt['QSettings']=lambda organization,application:QSettings(str(root/(application+'.ini')),QSettings.IniFormat)
                return qt
            class Client:
                def __init__(self,**kwargs):pass
                def get_models(self):return SimpleNamespace(models=['PEAK A (model prediction)','SEED (cyclic CF)'],default_model='PEAK A (model prediction)')
            with patch.object(js,'_qt_imports',qt_imports), patch.object(js,'credential_store',self.store), patch.object(access,'credential_store',self.store), patch.object(js.SharpEDServerClient,'get_models',Client.get_models), patch.dict(os.environ,{'SHARPED_API_TOKEN':''}):
                with patch.object(QDialog,'exec',lambda d:QDialog.Rejected):
                    wizard=js._JanaWorkflowWizard([],inflip);wizard.run()
                if remove:
                    self.assertEqual(wizard.api_token.text(),KEY)
                wizard._ensure_models_loaded=lambda:None
                wizard.model_cache['loaded']=True
                wizard.workflow_state['key']=js.WORKFLOW_PHASE_RECYCLING
                wizard._workflow_changed()
                wizard.cycles.setValue(3)
                wizard.model.clear();wizard.model.addItems(['PEAK A (model prediction)','SEED (cyclic CF)'])
                wizard.model.setCurrentText('SEED (cyclic CF)');wizard.model.activated.emit(wizard.model.currentIndex())
                wizard._preflight_client_factory=Client
                wizard.dialog.show();self.app.processEvents()
                controls=[]
                for kind in (QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QCheckBox,QRadioButton):
                    controls.extend(w for w in wizard.dialog.findChildren(kind) if w is not wizard.api_token)
                def value(widget):
                    if isinstance(widget,QLineEdit):return widget.text()
                    if isinstance(widget,QComboBox):return (widget.currentText(),widget.currentData())
                    if isinstance(widget,(QSpinBox,QDoubleSpinBox)):return widget.value()
                    return widget.isChecked()
                before=[value(w) for w in controls]
                observed=[]
                def interact():
                    dialog=self.app.activeModalWidget()
                    observed.append(dialog)
                    dialog.account_button.click()
                    if remove:
                        dialog.remove_button.click()
                    if connect:
                        dialog.key_edit.setText(KEY);dialog.connect_button.click()
                    else:dialog.back_button.click()
                try:
                    with patch('phase_studio.sharped_access.QDesktopServices.openUrl') as browser, patch.object(js,'launch_phase_studio_from_jana') as launch, patch.object(js,'launch_autosolve_from_jana') as autosolve:
                        QTimer.singleShot(0,interact)
                        wizard._manage_sharped_access()
                        self.assertEqual(browser.call_args.args[0].toString(),'https://sharped.fzu.cz/sharp-ed')
                        launch.assert_not_called();autosolve.assert_not_called()
                    self.assertEqual([value(w) for w in controls],before)
                    self.assertEqual(wizard.inflip_path,inflip)
                    self.assertEqual(wizard.workflow_state['key'],js.WORKFLOW_PHASE_RECYCLING)
                    self.assertIs(observed[0].parentWidget(),wizard.dialog)
                    self.assertTrue(observed[0].isModal())
                    self.assertEqual(wizard.api_token.text(),KEY if connect else '')
                    self.assertNotIn(KEY,repr(wizard.result))
                finally:
                    wizard.refresh_timer.stop();wizard.dialog.close();wizard.dialog.deleteLater()
                    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_browser_and_back_preserve_all_jana_scientific_controls(self):
        self._wizard_account_round_trip(False)

    def test_browser_and_connect_change_only_the_jana_access_key(self):
        self._wizard_account_round_trip(True)

    def test_remove_saved_access_and_back_clears_the_wizard_key_without_changing_science(self):
        self._wizard_account_round_trip(False,remove=True)
        self.assertEqual(self.store.get(),'')
        self.assertEqual(CredentialStore(self.backend).get(),'')

class SimpleNamespaceError(Exception):
    def __init__(self,code):self.code=code;super().__init__('HTTP Error '+str(code))

if __name__=='__main__':unittest.main()
