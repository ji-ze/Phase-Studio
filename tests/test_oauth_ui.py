"""Real Qt + local mock authorization; no browser session or production job."""
import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from pathlib import Path
import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
import threading
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication,QEvent,QThread,QTimer,Qt
from PySide6.QtWidgets import QApplication,QDialog,QLabel,QPushButton
from PySide6.QtTest import QTest
from phase_studio.credentials import CredentialStore
from phase_studio.oauth import OAuthAttempt,OAuthCredential
from phase_studio.oauth_ui import OAuthWorker
from phase_studio.sharped_access import SharpEDAccessDialog
from test_oauth import Provider
from urllib.request import urlopen
from urllib.parse import urlencode,urlsplit
import json


class OAuthUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owned=QApplication.instance() is None
        cls.app=QApplication.instance() or QApplication([])
    @classmethod
    def tearDownClass(cls):
        if cls.owned:
            import shiboken6
            shiboken6.delete(cls.app)
    def setUp(self):
        self.provider=Provider();self.store=CredentialStore();self.urls=[]
        self.worker_patch=patch("phase_studio.oauth_ui.OAuthWorker",side_effect=lambda:OAuthWorker(OAuthAttempt(self.provider)))
        self.worker_patch.start()
        def browser(url):
            self.assertEqual(QThread.currentThread(),self.app.thread())
            self.urls.append(url.toString());return True
        self.browser_patch=patch("phase_studio.sharped_access.QDesktopServices.openUrl",side_effect=browser)
        self.browser_patch.start()
        self.dialog=SharpEDAccessDialog(store=self.store);self.dialog.show();self.app.processEvents()
    def tearDown(self):
        self.dialog.close();self.wait(lambda:self.dialog._oauth_worker is None or self.dialog._closed)
        from PySide6.QtCore import QThreadPool
        QThreadPool.globalInstance().waitForDone(3000);self.app.processEvents()
        self.dialog.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        self.browser_patch.stop();self.worker_patch.stop();self.provider.close()
    def wait(self,check):
        end=time.monotonic()+3
        while not check() and time.monotonic()<end:QTest.qWait(10)
        self.assertTrue(check())
    def complete(self):
        with urlopen(self.provider.base+"/oauth/authorize?"+urlsplit(self.urls[-1]).query) as r:q=json.load(r)
        callback=self.dialog._oauth_worker.attempt.redirect_uri
        errors=[]
        def finish():
            try:
                with urlopen(callback+"?"+urlencode(q),timeout=2) as r:r.read()
            except Exception as e:errors.append(type(e).__name__)
        t=threading.Thread(target=finish);t.start()
        self.wait(lambda:self.dialog.result()==QDialog.Accepted);t.join(2)
        self.assertEqual(errors,[])
    def test_primary_browser_flow_asynchronous_and_session_only(self):
        self.assertEqual(self.dialog.sign_in_button.text(),"Sign in with Jana2020")
        self.assertFalse(self.dialog.manual_panel.isVisible())
        self.assertFalse(self.dialog.connect_button.isVisible())
        self.dialog.sign_in_button.click();self.wait(lambda:bool(self.urls))
        self.assertIn("browser",self.dialog.feedback.text())
        self.assertFalse(self.dialog.back_button.isVisible())
        self.complete()
        self.assertEqual(self.dialog.selected_key,"mock-oauth-access")
        self.assertEqual(self.store.authentication_method(),"oauth")
        from phase_studio.sharped_access import connection_status
        self.assertEqual(connection_status(self.store),'Connected')
        self.assertFalse(self.store.remembered())
    def test_final_copy_geometry_and_collapse(self):
        d=self.dialog
        self.assertEqual(d.presentation_state,"initial")
        self.assertLessEqual(d.height(),340)
        self.assertIn("continues automatically",d.reassurance.text())
        before=d.size()
        d.manual_button.click();self.app.processEvents()
        self.assertFalse(d.management_panel.isVisible())
        self.assertEqual(d.key_edit.placeholderText(),"Paste your access key")
        self.assertIn(d.show_button,d.key_edit.actions())
        d.manual_button.click();self.app.processEvents()
        self.assertEqual(d.size(),before)
    def test_exchange_state_is_not_browser_waiting(self):
        self.dialog.sign_in_button.click();self.wait(lambda:bool(self.urls))
        self.dialog._oauth_progress("exchange")
        self.assertEqual(self.dialog.presentation_state,"exchange")
        self.assertEqual(self.dialog.heading.text(),"Connecting to SharpED")
        self.assertEqual(self.dialog.description.text(),"Completing your secure connection…")
        self.assertFalse(self.dialog.reopen_button.isVisible())
        self.assertFalse(self.dialog.back_button.isVisible())
        self.assertFalse(hasattr(self.dialog.progress,"value"))
    def test_timeout_retry_creates_fresh_state_and_verifier(self):
        self.worker_patch.stop()
        with patch("phase_studio.oauth_ui.OAuthWorker",side_effect=lambda:OAuthWorker(OAuthAttempt(self.provider,timeout=.2))):
            self.dialog.sign_in_button.click();first=self.dialog._oauth_worker.attempt
            self.wait(lambda:self.dialog.presentation_state=="timeout")
            self.assertEqual(self.dialog.sign_in_button.text(),"Sign in again")
            self.assertEqual(first.server.fileno(),-1)
            self.dialog.sign_in_button.click();second=self.dialog._oauth_worker.attempt
            self.assertNotEqual(first.state,second.state)
            self.assertNotEqual(first.verifier,second.verifier)
    def test_jana_network_error_has_retry_and_no_busy_controls(self):
        from phase_studio.oauth import OAuthError
        self.provider.json=lambda *a,**k:(_ for _ in ()).throw(OAuthError("network"))
        self.dialog.sign_in_button.click();self.wait(lambda:self.dialog.presentation_state=="network")
        self.assertEqual(self.dialog.heading.text(),"Could not connect to Jana2020")
        self.assertEqual(self.dialog.sign_in_button.text(),"Try again")
        self.assertFalse(self.dialog.progress.isVisible())
        self.assertTrue(self.dialog.back_button.isVisible())
    def test_api_retry_reuses_connection_without_oauth_or_storage_write(self):
        from phase_studio import requirements as reqs
        token="mock-already-authorized"
        self.store.activate_oauth(OAuthCredential(token,time.monotonic()+3600))
        calls=[]
        status=reqs.RequirementStatus(reqs.RequirementKind.SHARPED,reqs.RequirementState.SERVER_UNAVAILABLE)
        d=SharpEDAccessDialog(status=status,store=self.store,verify=lambda key:(calls.append(key) or reqs.RequirementStatus(reqs.RequirementKind.SHARPED,reqs.RequirementState.OK)))
        d.show();self.app.processEvents()
        try:
            self.assertEqual(d.heading.text(),"Could not connect to SharpED")
            d.sign_in_button.click();self.wait(lambda:d.result()==QDialog.Accepted)
            self.assertEqual(calls,[token]);self.assertEqual(d.selected_key,token)
            self.assertIsNone(d._oauth_worker);self.assertFalse(self.store.remembered())
        finally:d.close();d.deleteLater()
    def test_new_key_requires_review_before_saved_access_changes(self):
        from test_sharped_access import MemorySecureBackend
        from phase_studio import requirements as reqs
        backend=MemorySecureBackend();store=CredentialStore(backend)
        store.set("mock-original-saved",remember=True)
        d=SharpEDAccessDialog(store=store,verify=lambda key:reqs.RequirementStatus(reqs.RequirementKind.SHARPED,reqs.RequirementState.OK))
        d.show();self.app.processEvents()
        try:
            d.manual_button.click();d.key_edit.setText("mock-replacement")
            writes=len(backend.writes);d.connect_button.click();self.app.processEvents()
            self.assertTrue(d.management_panel.isVisible());self.assertEqual(len(backend.writes),writes)
            self.assertFalse(d._connecting);self.assertEqual(store.get(),"mock-original-saved")
            d.connect_button.click();self.wait(lambda:d.result()==QDialog.Accepted)
            self.assertEqual(store.get(),"mock-replacement")
        finally:d.close();d.deleteLater()
    def test_denial_does_not_offer_or_trigger_reauthentication(self):
        self.dialog._present("denied","SharpED did not allow this request.")
        self.dialog._primary_action()
        self.assertIsNone(self.dialog._oauth_worker)
        self.assertFalse(self.dialog.sign_in_button.isVisible())
        self.assertEqual(self.dialog.heading.text(),"SharpED access unavailable")
        self.assertTrue(self.dialog.back_button.isDefault())
    def test_manual_fallback_expands_existing_key_controls(self):
        self.dialog.manual_button.click();self.app.processEvents()
        self.assertTrue(self.dialog.manual_panel.isVisible());self.assertTrue(self.dialog.connect_button.isVisible())
        self.assertEqual(self.dialog.key_edit.text(),"")
        self.assertEqual(self.urls,[])
        self.assertFalse(self.dialog.help_panel.isVisible())
        self.dialog.help_button.click();self.app.processEvents()
        self.assertTrue(self.dialog.help_panel.isVisible())
        self.dialog.help_button.click();self.app.processEvents()
        self.assertFalse(self.dialog.help_panel.isVisible())
    def test_default_is_one_primary_action_and_no_manual_controls(self):
        self.assertEqual(self.dialog.heading.text(),"Connect to SharpED")
        self.assertTrue(self.dialog.sign_in_button.hasFocus())
        for widget in (self.dialog.key_edit,self.dialog.show_button,self.dialog.remember,
                       self.dialog.replace_button,self.dialog.remove_button,self.dialog.connect_button,
                       self.dialog.account_button,self.dialog.help_panel):
            self.assertFalse(widget.isVisible())
        self.assertEqual([b for b in self.dialog.findChildren(QPushButton)
                          if b.isVisible() and b.objectName()=="primaryButton"],[self.dialog.sign_in_button])
        self.assertFalse(self.dialog._footer.isAncestorOf(self.dialog.connect_button))
        self.assertIn("Use an access key instead",self.dialog.manual_button.text())
        for label in self.dialog.findChildren(QLabel):
            if label.isVisible():
                self.assertNotIn("API",label.text());self.assertNotIn("token",label.text())
    def test_repeated_click_and_reopen_reuse_exact_attempt(self):
        self.dialog.sign_in_button.click();worker=self.dialog._oauth_worker
        self.dialog._start_oauth();self.wait(lambda:bool(self.urls))
        self.assertIs(self.dialog._oauth_worker,worker)
        self.assertEqual(len(self.urls),1)
        self.assertEqual(self.dialog.heading.text(),"Waiting for Jana2020 sign-in…")
        self.assertTrue(self.dialog.progress.isVisible())
        self.dialog.reopen_button.click()
        self.assertEqual(self.urls,[self.urls[0],self.urls[0]])
        self.assertIs(self.dialog._oauth_worker,worker)
    def test_cancel_stays_in_dialog_and_old_completion_cannot_accept_retry(self):
        self.dialog.sign_in_button.click();self.wait(lambda:bool(self.urls))
        old=self.dialog._oauth_worker
        self.dialog.cancel_sign_in_button.click();self.app.processEvents()
        self.assertFalse(self.dialog.isVisible());self.assertIsNone(self.dialog._oauth_worker)
        self.assertTrue(old.attempt.cancelled.is_set())
        self.assertEqual(self.dialog.heading.text(),"Authentication cancelled")
        self.dialog._closed=False;self.dialog.show();self.dialog.sign_in_button.click();new=self.dialog._oauth_worker
        old.signals.finished.emit(OAuthCredential("late-unused",time.monotonic()+3600),None)
        self.app.processEvents()
        self.assertIs(self.dialog._oauth_worker,new);self.assertEqual(self.store.get(),"")
        self.assertNotEqual(self.dialog.result(),QDialog.Accepted)
    def test_escape_cancels_attempt_then_returns_on_second_escape(self):
        QTest.keyClick(self.dialog,Qt.Key_Return);self.wait(lambda:bool(self.urls))
        QTest.keyClick(self.dialog,Qt.Key_Escape);self.app.processEvents()
        self.assertFalse(self.dialog.isVisible());self.assertIsNone(self.dialog._oauth_worker)
        QTest.keyClick(self.dialog,Qt.Key_Escape);self.app.processEvents()
        self.assertFalse(self.dialog.isVisible())
    def test_saved_manual_key_does_not_expand_default_and_oauth_stays_separate(self):
        d=SharpEDAccessDialog(configured_value="mock-legacy-key",store=self.store)
        d.show();self.app.processEvents()
        try:
            self.assertFalse(d.manual_panel.isVisible());self.assertEqual(d.key_edit.text(),"mock-legacy-key")
            d.manual_button.click();self.app.processEvents();self.assertTrue(d.key_edit.isVisible())
        finally:d.close();d.deleteLater()
    def test_valid_oauth_skips_redundant_prompt_but_not_permission_failure(self):
        from phase_studio.sharped_access import show_sharped_access_dialog
        from phase_studio import requirements as reqs
        self.store.activate_oauth(OAuthCredential("mock-current",time.monotonic()+3600))
        with patch("phase_studio.sharped_access.SharpEDAccessDialog") as constructor:
            self.assertEqual(show_sharped_access_dialog(None,None,store=self.store),"mock-current")
            constructor.assert_not_called()
            denied=reqs.RequirementStatus(reqs.RequirementKind.SHARPED,reqs.RequirementState.ACCESS_DENIED)
            show_sharped_access_dialog(None,denied,store=self.store)
            constructor.assert_called_once()
    def test_expired_heading_and_real_api_denial_are_distinct(self):
        from phase_studio import requirements as reqs
        self.store.activate_oauth(OAuthCredential("mock-expired",0))
        d=SharpEDAccessDialog(store=self.store);d.show();self.app.processEvents()
        try:
            self.assertEqual(d.heading.text(),"Reconnect to SharpED")
            self.assertIn("expired",d.description.text())
        finally:d.close();d.deleteLater()
        denied=reqs.RequirementStatus(reqs.RequirementKind.SHARPED,reqs.RequirementState.ACCESS_DENIED)
        d=SharpEDAccessDialog(status=denied,store=self.store);d.show();self.app.processEvents()
        try:self.assertEqual(d.heading.text(),"SharpED access unavailable");self.assertNotIn("subscription",d.description.text());self.assertFalse(d.sign_in_button.isVisible())
        finally:d.close();d.deleteLater()
    def test_owned_dialog_returns_foreground_without_permanent_topmost(self):
        from phase_studio.ui_branding import activate_owned_dialog
        self.dialog.close()
        owner=QDialog();owner.show()
        self.dialog=SharpEDAccessDialog(owner,store=self.store);self.dialog.show();self.app.processEvents()
        try:
            self.assertIs(self.dialog.parentWidget(),owner)
            self.assertTrue(self.dialog.isModal())
            self.assertFalse(self.dialog.windowFlags() & Qt.WindowStaysOnTopHint)
            with patch("phase_studio.sharped_access.activate_owned_dialog",wraps=activate_owned_dialog) as activate:
                self.dialog.sign_in_button.click();self.wait(lambda:bool(self.urls));self.complete()
                activate.assert_called_once_with(self.dialog)
        finally:owner.close();owner.deleteLater()
    def test_back_cancels_worker_and_ignores_late_result(self):
        self.dialog.sign_in_button.click();self.wait(lambda:bool(self.urls))
        worker=self.dialog._oauth_worker
        self.dialog.back_button.click()
        self.assertTrue(worker.attempt.cancelled.is_set())
        self.wait(lambda:worker.attempt.server.fileno()==-1)
        self.assertIsNone(self.dialog.selected_key);self.assertEqual(self.store.get(),"")
    def test_browser_failure_returns_retry_without_saved_credential(self):
        self.browser_patch.stop()
        with patch("phase_studio.sharped_access.QDesktopServices.openUrl",return_value=False):
            self.dialog.sign_in_button.click();self.wait(lambda:self.dialog._oauth_worker is None)
        self.assertTrue(self.dialog.sign_in_button.isEnabled());self.assertEqual(self.store.get(),"")
        self.assertNotEqual(self.dialog.result(),QDialog.Accepted)
    def test_sign_out_keeps_legacy_storage_and_returns_explicit_key_state(self):
        self.store.set("session-legacy")
        self.store.activate_oauth(OAuthCredential("mock-oauth-access",time.monotonic()+3600))
        self.dialog._sign_out()
        self.assertEqual(self.store.get(),"session-legacy")
        self.assertEqual(self.dialog.selected_key,"session-legacy")
        self.assertIn("browser session is unchanged",self.dialog.feedback.text())
    def test_running_worker_stop_cancels_owned_reauthorization(self):
        self.store.activate_oauth(OAuthCredential("expired-worker-token",0))
        stop=threading.Event();outcome=[]
        def request():
            try:self.store.oauth_for_request("expired-worker-token",cancel_event=stop)
            except Exception as error:outcome.append(getattr(error,"kind",None))
        thread=threading.Thread(target=request);thread.start()
        QTimer.singleShot(250,stop.set)
        self.wait(lambda:not thread.is_alive());thread.join(1)
        self.assertEqual(outcome,["cancelled"])
        self.assertEqual(self.store.get(),"expired-worker-token")
        self.assertFalse(any(w.isVisible() and w is not self.dialog for w in self.app.topLevelWidgets()))


if __name__=="__main__":unittest.main()
