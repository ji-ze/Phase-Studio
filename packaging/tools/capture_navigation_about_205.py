"""Real Qt interaction/captures; remote states are explicit controlled fixtures."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['PHASE_STUDIO_STARTUP_PROBE'] = '1'
os.environ.pop('SHARPED_API_TOKEN', None)
from PySide6.QtCore import QPoint, QSettings, QRect, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QScreen
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox
from phase_studio import jana_superflip as js, update_ui
from phase_studio.about_ui import AboutDialog, RELEASES_URL, show_about_dialog
from phase_studio.credentials import CredentialStore
from phase_studio.sharped_access import SharpEDAccessDialog, account_state
from phase_studio.ui_style import apply_phase_studio_style
from phase_studio.version import VERSION
from test_wizard_text_clipping import write_inflip

scale = float(os.environ.get('QT_SCALE_FACTOR', '1'))
out = ROOT/'build/acceptance-navigation-about-2.0.5'/f'scale-{scale}'
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
apply_phase_studio_style(app)
area = QRect(0, 0, int(1920/scale), int(1040/scale))
records = {}


def settle():
    for _ in range(30): app.processEvents()


def capture(name, widget):
    settle()
    assert widget.grab().save(str(out/(name+'.png')))
    records[name] = dict(rect=widget.geometry().getRect(), dpr=widget.devicePixelRatioF(),
                         fixture='Synthetic input; controlled remote catalogue/account states; no inference')


with tempfile.TemporaryDirectory() as temporary, patch.object(QScreen, 'availableGeometry', return_value=area):
    base = Path(temporary)
    factory = lambda org, name: QSettings(str(base/(name+'.ini')), QSettings.IniFormat)
    state = update_ui.UpdateState(factory('PhaseStudio', 'updates'), base/'update.lock')
    state.set_enabled(False)
    app._phase_studio_updates = update_ui.UpdateService(app, state=state, automatic_allowed=False)
    source = write_inflip(base)
    original = source.read_bytes()
    jana = base/'Jana'
    (jana/'SUPERFLIP').mkdir(parents=True)
    for name in ('superflip.exe', 'EDMA.exe'):
        (jana/'SUPERFLIP'/name).write_bytes(b'Offline path fixture; never executed')
    store = CredentialStore(backend=None)
    imports = js._qt_imports
    response = dict(provenance='offline', fail=False,
                    models=[js.SHARPED_ONE_CYCLE_MODEL, js.SHARPED_ITERATIVE_MODEL, 'Long manual model fixture'])

    def models(_self):
        if response['fail']: raise TimeoutError('Controlled catalogue timeout')
        return SimpleNamespace(models=list(response['models']), default_model=response['models'][0],
                               provenance=response['provenance'])

    def pump(w):
        deadline = time.monotonic()+5
        while w.model_cache['inflight']:
            settle();w.refresh_timer.timeout.emit();QTest.qWait(5)
            assert time.monotonic() < deadline
        settle()

    with patch.object(js, '_qt_imports', lambda: imports()|{'QSettings': factory}), \
            patch.object(js, 'credential_store', store), \
            patch.object(js, 'application_dir', lambda: jana), \
            patch.object(js.SharpEDServerClient, 'get_models', models), \
            patch.object(QDialog, 'exec', lambda self: QDialog.Rejected):
        w = js._JanaWorkflowWizard([], source)
        w.run();w.dialog.show();settle()
        assert '432 HKL records' in w.reflections_value.text()
        capture('01-workflow', w.dialog)
        w.superflip_sharped_tile._trigger();pump(w)
        w.cycles.setValue(1);settle()
        assert w.primary_button.text() == 'Run phasing'
        assert 'Map feedback' not in w.processing_progress.text()
        assert w.model.currentText() == js.SHARPED_ONE_CYCLE_MODEL
        capture('02-one-cycle-peak', w.dialog)
        for count in (2, 3):
            w.cycles.setValue(count)
            assert w.primary_button.text() == 'Next: Map feedback →'
            assert 'Map feedback' in w.processing_progress.text()
            assert w.model.currentText() == js.SHARPED_ITERATIVE_MODEL
        capture('03-three-cycle-seed', w.dialog)
        w.model.setCurrentIndex(2);w.model.activated.emit(2)
        w.model.setFocus();QTest.keyClick(w.model, Qt.Key_Home)
        QTest.keyClick(w.model, Qt.Key_End)
        assert w.model.currentIndex() == 2
        QTest.mouseClick(w.model, Qt.LeftButton, pos=QPoint(w.model.width()-8, w.model.height()//2))
        settle();assert w.model.view().isVisible()
        w.model.hidePopup()
        w.model.setEnabled(False);settle()
        QTest.mouseClick(w.model, Qt.LeftButton, pos=QPoint(w.model.width()-8, w.model.height()//2))
        assert not w.model.view().isVisible()
        w.model.setEnabled(True)
        w.refresh_models_button.click();pump(w)
        assert w.model.currentIndex() == 2 and w.model_user_picked['value']
        capture('04-manual-override', w.dialog)
        w.restore_automatic_model_button.click()
        assert 'Controlled offline catalogue' in w.model_status.text()
        capture('05-offline-catalogue-fixture', w.dialog)
        response['provenance'] = 'live';w.refresh_models_button.click();pump(w)
        assert 'Live server catalogue' in w.model_status.text()
        assert w.connection_status.text() == 'Not connected'
        capture('13-live-catalogue-fixture', w.dialog)
        response['fail'] = True;w.refresh_models_button.click();pump(w)
        assert w.model_catalog['provenance'] == 'cached' and w.model_policy_error
        capture('14-cached-catalogue-fixture', w.dialog)
        response['fail'] = False;response['provenance'] = 'offline'
        w.refresh_models_button.click();pump(w)
        token = 'mock-access-only-not-a-real-key'
        store.set(token, remember=False);w.api_token.setText(token)
        assert w.account_state['credentials'] == 'Available for the current session'
        assert w.account_state['connection'] == 'Not checked'
        capture('06-unverified-credentials-fixture', w.dialog)
        fingerprint = hashlib.sha256(token.encode()).hexdigest()
        for status, expected in (('Authentication expired', 'rejected'), ('Connection unavailable', 'Unavailable'),
                                 ('Connected', 'Authorization verified')):
            store._access_verification = {js.DEFAULT_SERVER_URL: (fingerprint, status)}
            w._update_account_presentation()
            assert expected in w.account_state['connection']
        capture('07-verified-authorization-fixture', w.dialog)
        # Actual existing account dialog, owned by this Wizard; no browser/login.
        def inspect_account(dialog):
            assert isinstance(dialog, SharpEDAccessDialog) and dialog.parentWidget() is w.dialog
            dialog.show();settle();assert dialog.isVisible()
            dialog.reject()
            return QDialog.Rejected
        with patch('phase_studio.sharped_access.credential_store', store), patch.object(QDialog, 'exec', inspect_account):
            w.sharped_account_button.click()
        assert w.connection_status.text() == 'Connected · Authorization verified'
        checks = []
        w._ensure_workflow_requirements = lambda **kw: checks.append(kw) or False
        w.cycles.setValue(1)
        w.model_policy_error = 'Required automatic model is unavailable. Refresh models.'
        w.primary_button.click()
        assert not checks and w.stack.currentWidget() is w.page2
        assert 'unavailable' in w.model_status.text()
        w.cycles.setValue(3)
        w.primary_button.click();settle()
        assert w.stack.currentWidget() is w.page3 and not checks
        capture('08-single-crystal-feedback', w.dialog)
        w.missing_enabled_checkbox.setChecked(True)
        w.intensity_enabled_checkbox.setChecked(True)
        w.back_button.click();w.cycles.setValue(1)
        w.primary_button.click()
        assert checks == [{'needs_sharped': True}] and w.stack.currentWidget() is w.page2
        assert w.result['action'] == 'cancel'
        w._go_to_map_feedback();settle()
        assert not w.missing_enabled_checkbox.isEnabled()
        assert w.feedback_cycle_summary.text().startswith('1 cycle configured')
        w.back_button.click();w.cycles.setValue(3);w.primary_button.click();settle()
        assert w.missing_enabled_checkbox.isChecked() and w.missing_enabled_checkbox.isEnabled()
        w.back_button.click()
        # Real powder parser/metadata path, using a separate synthetic input.
        powder = base/'powder.inflip'
        powder.write_text('title powder_fixture\nperform CF\ndimension 3\ncell 10 11 12 90 90 90\n'
            'spacegroup P1\ncomposition C2\ndataformat intensity fwhm\nfbegin\n1 0 0 10 0.1\nendf\n')
        p = js._JanaWorkflowWizard([], powder);p.run();p.dialog.show()
        p.superflip_sharped_tile._trigger();pump(p);p.cycles.setValue(3);p.primary_button.click();settle()
        assert p.feedback_is_powder
        capture('09-powder-feedback', p.dialog)
        p.dialog.close()
        w.update_menu.menu().actions()[-1].trigger();settle()
        about = w.dialog._phase_studio_about
        assert isinstance(about, AboutDialog) and 'Jana2020' in about.mode_label.text()
        assert VERSION in about.version_label.text() and area.contains(about.frameGeometry())
        assert show_about_dialog(w.dialog, jana=True) is about
        capture('10-about-jana', about)
        with patch.object(QDesktopServices, 'openUrl', return_value=True) as open_url:
            from PySide6.QtWidgets import QPushButton
            next(b for b in about.findChildren(QPushButton) if b.text() == 'Official GitHub Releases').click()
            open_url.assert_called_once_with(QUrl(RELEASES_URL))
        about.credits_button.click();settle()
        assert (ROOT/'LICENSE').read_text(encoding='utf8') in about.credits.toPlainText()
        assert area.contains(about.frameGeometry())
        about.credits_button.click();QTest.keyClick(about, Qt.Key_Escape);settle()
        assert not about.isVisible()
        about = show_about_dialog(w.dialog, jana=False);settle()
        assert about.mode_label.text() == 'Standalone application'
        capture('11-about-standalone', about)
        about.findChild(QDialogButtonBox).button(QDialogButtonBox.Close).click();settle()
        assert not about.isVisible()
        about = show_about_dialog(w.dialog, jana=True);settle();about.close();settle()
        assert not about.isVisible()
        with patch('phase_studio.about_ui.version.VERSION', '9.8.7'):
            dynamic = AboutDialog(w.dialog, jana=False)
            assert dynamic.version_label.text() == 'Version 9.8.7'
            dynamic.deleteLater()
        menu = w.update_menu.menu();menu.popup(w.update_menu.mapToGlobal(w.update_menu.rect().bottomLeft()))
        capture('12-ellipsis-menu', menu);menu.close()
        w.dialog.close()
        # Exercise actual run() serialization, not only helpers or checkboxes.
        for direct in (False, True):
            run_w = js._JanaWorkflowWizard([], source)
            def execute(dialog):
                dialog.show();settle()
                run_w.superflip_sharped_tile._trigger();pump(run_w)
                run_w.cycles.setValue(3);run_w.primary_button.click()
                run_w.missing_enabled_checkbox.setChecked(True)
                run_w.intensity_enabled_checkbox.setChecked(True)
                run_w.powder_enabled_checkbox.setChecked(True)
                run_w.back_button.click();run_w.cycles.setValue(1)
                if direct: run_w._go_to_map_feedback()
                run_w._ensure_workflow_requirements = lambda **kw: True
                run_w.primary_button.click()
                assert run_w.result['action'] == 'recycle'
                assert run_w.stack.currentWidget() is (run_w.page3 if direct else run_w.page2)
                return QDialog.Accepted
            with patch.object(QDialog, 'exec', execute):
                options = run_w.run()
            assert options.cycles == 1 and options.model == js.SHARPED_ONE_CYCLE_MODEL
            assert not any((options.enable_missing_completion, options.enable_intensity_correction,
                            options.enable_powder_repartition))
            records['one-cycle-direct-page' if direct else 'one-cycle-skip-interaction'] = dict(
                cycles=options.cycles, action=options.action, model=options.model, feedback_enabled=False)
        assert source.read_bytes() == original
(out/'acceptance.json').write_text(json.dumps(records, indent=2), encoding='utf8')
print('PASS navigation, serialization, catalogue/account separation, About and screenshots at', scale)
