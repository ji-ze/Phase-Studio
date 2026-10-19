"""Actual Qt final release UI acceptance; all remote states are controlled.

Uses a read-only copy of existing ochlor input when available. No inference,
credential persistence or original project publication occurs.
"""
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
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['PHASE_STUDIO_STARTUP_PROBE'] = '1'
os.environ.pop('SHARPED_API_TOKEN', None)
from PySide6.QtCore import QSettings, QRect, QPoint, Qt
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtTest import QTest
from phase_studio import jana_superflip as js, update_ui
from phase_studio.credentials import CredentialStore
from phase_studio.update_checker import Release, CheckResult, VERSION
from phase_studio.ui_style import apply_phase_studio_style
from test_wizard_text_clipping import write_inflip

scale = float(os.environ.get('QT_SCALE_FACTOR', '1'))
out = ROOT / 'build/acceptance-final-wizard-release-2.0.5' / f'scale-{scale}'
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
apply_phase_studio_style(app)
records = {}
area = QRect(0, 0, int(1920 / scale), int(1040 / scale))


def settle():
    for _ in range(25):
        app.processEvents()


def capture(name, widget, wizard):
    settle()
    assert widget.grab().save(str(out / (name + '.png')))
    records[name] = dict(size=widget.size().toTuple(), dpr=widget.devicePixelRatioF(),
        model=wizard.model.currentText(), manual=wizard.model_user_picked['value'],
        account=wizard.connection_status.text(), catalogue=wizard.model_status.text(),
        input_summary=wizard.reflections_value.text(),
        remote_state='Controlled offline catalogue/account/update fixture; no inference')


with tempfile.TemporaryDirectory() as temporary, patch.object(QScreen, 'availableGeometry', return_value=area):
    base = Path(temporary)
    real = Path.home() / 'Documents/ochlor/ochlor_Superflip.inflip'
    original = real.read_bytes() if real.is_file() else None
    if original:
        source = base / 'ochlor.inflip'
        source.write_bytes(original)
    else:
        source = write_inflip(base)
    before = source.read_bytes()
    jana = base / 'Jana'
    (jana / 'SUPERFLIP').mkdir(parents=True)
    for name in ('superflip.exe', 'EDMA.exe'):
        (jana / 'SUPERFLIP' / name).write_bytes(b'Offline UI fixture, never executed')
    imports = js._qt_imports
    settings = lambda org, name: QSettings(str(base / (name + '.ini')), QSettings.IniFormat)
    store = CredentialStore(backend=None)
    update_settings = settings('PhaseStudio', 'updates')
    update_state = update_ui.UpdateState(update_settings, base / 'updates.lock')
    update_state.set_enabled(False)
    reply = [Release(tuple(map(int, VERSION.split('.'))))]
    service = update_ui.UpdateService(app, state=update_state, fetcher=lambda: reply[0],
        clock=lambda: 1800000000., browser=lambda url: True)
    app._phase_studio_updates = service
    peak, seed = js.SHARPED_ONE_CYCLE_MODEL, js.SHARPED_ITERATIVE_MODEL
    catalogue = dict(models=[peak, seed, 'Controlled extra model'], offline=False)

    def fetch_models(_client):
        if catalogue['offline']:
            raise TimeoutError('Controlled offline catalogue')
        return SimpleNamespace(models=catalogue['models'], default_model=seed)

    def reject(dialog):
        # Wizard run returns without entering a blocking modal event loop.
        return QDialog.Rejected

    with patch.object(js, '_qt_imports', lambda: imports() | {'QSettings': settings}), \
            patch.object(js, 'credential_store', store), patch.object(QDialog, 'exec', reject), \
            patch.object(js, 'application_dir', lambda: jana), \
            patch.object(js.SharpEDServerClient, 'get_models', fetch_models):
        w = js._JanaWorkflowWizard([], source)
        w.run()
        w.dialog.show()
        settle()
        initial = QRect(w.dialog.geometry())

        def stable():
            settle()
            assert w.dialog.geometry() == initial
            assert w.scroll_area.horizontalScrollBar().maximum() == 0
            assert area.contains(QRect(w.cancel_button.mapToGlobal(QPoint()), w.cancel_button.size()))
            assert not w.scroll_area.isAncestorOf(w.footer)

        def models_done():
            until = time.monotonic() + 5
            while w.model_cache['inflight']:
                settle()
                w.refresh_timer.timeout.emit()
                assert time.monotonic() < until
                QTest.qWait(5)
            stable()

        capture('01-workflow', w.dialog, w)
        assert 'HKL records' in w.reflections_value.text()
        assert 'not symmetry-independent' in w.reflections_value.toolTip()
        w.files_toggle.click()
        stable()
        capture('02-input-options-expanded', w.dialog, w)
        w.files_toggle.click()
        w.superflip_sharped_tile.setFocus(Qt.TabFocusReason)
        settle()
        capture('03-workflow-keyboard-focus', w.dialog, w)
        assert w.superflip_sharped_tile.hasFocus()
        QTest.keyClick(w.superflip_sharped_tile, Qt.Key_Space)
        models_done()
        w.cycles.setValue(3)
        stable()
        assert w.cycles.width() == 110 and w.model.currentText() == seed
        capture('04-automatic-model', w.dialog, w)
        w.model.setCurrentText(peak)
        w.model.activated.emit(w.model.currentIndex())
        w.cycles.setValue(4)
        assert w.model.currentText() == peak and w.model_user_picked['value']
        assert 'Different from recommendation' in w.manual_model_indicator.text()
        capture('05-manual-override', w.dialog, w)
        w.restore_automatic_model_button.click()
        assert w.model.currentText() == seed and not w.model_user_picked['value']
        capture('06-restored-automatic', w.dialog, w)
        w.api_token.setText('mock-access-key-for-offline-UI-test')
        assert w.connection_status.text() == 'Credentials available — not yet verified'
        capture('07-credentials-unverified', w.dialog, w)
        catalogue['offline'] = True
        w.refresh_models_button.click()
        models_done()
        assert w.model_policy_error and w.model.currentText() == seed
        assert 'verified' in w.connection_status.text()
        capture('08-offline-catalogue', w.dialog, w)
        catalogue['offline'] = False
        w.refresh_models_button.click()
        models_done()
        w.sharped_toggle.click()
        stable()
        capture('09-advanced-sharped', w.dialog, w)
        w.sharped_toggle.click()
        menu = w.update_menu.menu()
        menu.popup(w.update_menu.mapToGlobal(QPoint(0, w.update_menu.height())))
        capture('10-version-menu', menu, w)
        menu.hide()
        action = next(a for a in menu.actions() if a.text() == 'Check for updates')
        for name, response in (
            ('11-update-current-mock', Release(tuple(map(int, VERSION.split('.'))))),
            ('12-update-newer-mock', Release((2, 0, 10), 'https://github.com/ji-ze/Phase-Studio/releases/tag/v2.0.10')),
            ('16-update-unavailable-mock', CheckResult(error='network', detail='TimeoutError'))):
            reply[0] = response
            action.trigger()
            deadline = time.monotonic() + 5
            while service.busy:
                settle()
                QTest.qWait(5)
                assert time.monotonic() < deadline
            capture(name, service.notice, w)
            service.notice.close()
            settle()
        w.primary_button.click()
        stable()
        assert w.stack.currentWidget() is w.page3
        capture('13-map-feedback', w.dialog, w)
        w.back_button.click()
        w.back_button.click()
        stable()

        def capture_child(dialog):
            dialog.show()
            settle()
            capture('17-manage-account' if dialog.objectName() == 'sharpedAccessDialog'
                    else '14-child-hkl-analysis', dialog, w)
            dialog.close()
            return QDialog.Rejected

        with patch.object(QDialog, 'exec', capture_child):
            w.validate_hkl_button.click()
            deadline = time.monotonic() + 8
            while '14-child-hkl-analysis' not in records:
                settle()
                w.backing_window_holder['win']._poll_queue()
                QTest.qWait(5)
                assert time.monotonic() < deadline
        stable()
        configured = (w.cycles.value(), w.model.currentText(), w.model_user_picked['value'])
        with patch.object(QDialog, 'exec', capture_child):
            w.sharped_account_button.click()
        assert configured == (w.cycles.value(), w.model.currentText(), w.model_user_picked['value'])
        stable()
        w.dialog.resize(790, min(700, area.height() - 20))
        settle()
        assert w.scroll_area.horizontalScrollBar().maximum() == 0
        assert w.footer.isVisible() and w.cancel_button.isVisible()
        capture('15-reduced-desktop', w.dialog, w)
        w.dialog.close()
        if w.backing_window_holder['win'] is not None:
            w.backing_window_holder['win'].close()
    assert source.read_bytes() == before
    if original:
        assert real.read_bytes() == original
    records['input'] = dict(kind='Read-only ochlor copy' if original else 'Synthetic HKL fixture',
        sha256=hashlib.sha256(before).hexdigest(), unchanged=True)
(out / 'acceptance.json').write_text(json.dumps(records, indent=2), encoding='utf8')
print('PASS final Wizard actual Qt acceptance at scale', scale)
