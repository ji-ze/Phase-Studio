"""Offline actual-widget acceptance; synthetic reflection input, mocked release metadata."""
import os
import sys
import tempfile
import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['PHASE_STUDIO_STARTUP_PROBE'] = '1'
os.environ.pop('SHARPED_API_TOKEN', None)
from PySide6.QtCore import QSettings, QRect, QPoint
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QApplication, QDialog, QLabel
from phase_studio import jana_superflip as js, update_ui as ui
from phase_studio.credentials import CredentialStore
from phase_studio.update_checker import Release, VERSION
from phase_studio.ui_style import apply_phase_studio_style
from test_wizard_text_clipping import write_inflip

OUT = ROOT / 'build/acceptance-wizard-mapfeedback-updates-2.0.5'
OUT.mkdir(parents=True, exist_ok=True)
scale = float(os.environ.get('QT_SCALE_FACTOR', '1'))
qt = QApplication([])
apply_phase_studio_style(qt)
records = {}

def settle():
    for _ in range(40):
        qt.processEvents()

def snap(name, widget, **info):
    settle()
    assert widget.grab().save(str(OUT / (name + '.png')))
    records[name] = dict(rect=widget.geometry().getRect(), dpr=widget.devicePixelRatioF(), **info)

with tempfile.TemporaryDirectory() as temporary:
    base = Path(temporary)
    source = write_inflip(base)
    original = source.read_bytes()
    source.write_text(source.read_text().replace('dataformat amplitude', 'dataformat intensity fwhm'), encoding='utf8')
    original = source.read_bytes()
    source.with_suffix('.m90').write_text('datblock Block1\nlambda 1.541866\nend\n', encoding='utf8')
    factory = lambda org, name: QSettings(str(base / (name + '.ini')), QSettings.IniFormat)
    state = ui.UpdateState(factory('', 'updates'), base / 'updates.lock')
    state.set_enabled(False)
    version = tuple(map(int, VERSION.split('.')))
    future = version[:2] + (version[2] + 1,)
    release = Release(future, 'https://github.com/ji-ze/Phase-Studio/releases/tag/v' + '.'.join(map(str, future)))
    service = ui.UpdateService(qt, state=state, fetcher=lambda: release, automatic_allowed=False)
    qt._phase_studio_updates = service
    jana = base / 'Jana'
    (jana / 'SUPERFLIP').mkdir(parents=True)
    for binary in ('superflip.exe', 'EDMA.exe'):
        (jana / 'SUPERFLIP' / binary).write_bytes(b'never executed; controlled fixture')
    imports = js._qt_imports
    with patch.object(js, '_qt_imports', lambda: imports() | {'QSettings': factory}), patch.object(js, 'credential_store', CredentialStore(backend=None)), patch.object(js, 'application_dir', lambda: jana), patch.object(QDialog, 'exec', lambda self: QDialog.Rejected), patch.object(QScreen, 'availableGeometry', return_value=QRect(0, 0, int(1920 / scale), int(1040 / scale))), patch.object(js.SharpEDServerClient, 'get_models', lambda self: SimpleNamespace(models=[js.SHARPED_ONE_CYCLE_MODEL, js.SHARPED_ITERATIVE_MODEL], default_model=js.SHARPED_ONE_CYCLE_MODEL)):
        w = js._JanaWorkflowWizard([], source)
        w.run()
        w.dialog.show()
        settle()
        if scale != 1:
            w.scroll_area.verticalScrollBar().setValue(w.scroll_area.verticalScrollBar().maximum())
            if scale == 1.25:
                snap('03-initial-dpi-125', w.dialog, fixture='Synthetic input; controlled Qt scale')
            w.superflip_sharped_tile._trigger()
            w.cycles.setValue(3)
            w.model_cache['loaded'] = True
            w.model_catalog['provenance'] = 'offline'
            w.model.clear()
            w.model.addItems([js.SHARPED_ONE_CYCLE_MODEL, js.SHARPED_ITERATIVE_MODEL])
            w.model_policy_error = ''
            w._go_to_map_feedback()
            w.intensity_enabled_checkbox.setChecked(True)
            w.intensity_damping_spin.setValue(.4)
            w.powder_enabled_checkbox.setChecked(True)
            settle()
            assert w.footer.isVisible() and not w.scroll_area.horizontalScrollBar().isVisible()
            for group in (w.intensity_group, w.powder_group):
                for label in group.findChildren(QLabel):
                    if label.isVisible() and label.wordWrap():
                        assert label.height() >= label.heightForWidth(label.width()), label.text()
            w.scroll_area.verticalScrollBar().setValue(w.scroll_area.verticalScrollBar().maximum())
            settle()
            assert w.scroll_area.viewport().rect().contains(w.powder_note.mapTo(w.scroll_area.viewport(), w.powder_note.rect().bottomRight()))
        else:
            w.dialog.resize(1000, 820)
            settle()
            snap('01-initial-normal', w.dialog)
            w.dialog.resize(790, 825)
            settle()
            snap('02-initial-reduced', w.dialog)
            menu = w.update_menu.menu()
            menu.popup(w.update_menu.mapToGlobal(QPoint(0, w.update_menu.height())))
            snap('04-version-menu', menu)
            menu.hide()
            service.check(w.dialog, manual=True, mode='jana')
            until = time.monotonic() + 5
            while service.busy:
                qt.processEvents()
                assert time.monotonic() < until
                time.sleep(.005)
            settle()
            assert w.update_menu.update_available
            notice = service.notice
            label = QLabel('CONTROLLED MOCK GITHUB METADATA — NOT A LIVE RELEASE CHECK', notice)
            label.setWordWrap(True)
            notice.layout().insertWidget(0, label)
            notice.resize(500, notice.sizeHint().height())
            snap('05-update-available-mock', notice)
            notice.close()
            w.superflip_sharped_tile._trigger()
            settle()
            w.cycles.setValue(3)
            w.model_cache['loaded'] = True
            w.model_catalog['provenance'] = 'offline'
            w.model_catalog['values'] = (js.SHARPED_ONE_CYCLE_MODEL, js.SHARPED_ITERATIVE_MODEL)
            w.model.clear()
            w.model.addItems(list(w.model_catalog['values']))
            w.model_policy_error = ''
            w._go_to_map_feedback()
            w.dialog.resize(1050, 850)
            settle()
            geometry = QRect(w.dialog.geometry())
            def capture_feedback(name):
                settle()
                assert w.dialog.geometry() == geometry
                assert not w.scroll_area.horizontalScrollBar().isVisible()
                assert w.footer.isVisible()
                snap(name, w.dialog, fixture='Synthetic powder/FWHM data; matching synthetic Jana m90 wavelength 1.541866 Å')
            capture_feedback('06-feedback-disabled')
            assert 'Map Feedback disabled' in w.map_feedback_warning_text.text()
            w.powder_enabled_checkbox.setChecked(True)
            assert w._map_feedback_wavelength()[0] == 1.541866
            capture_feedback('07-powder-only')
            w.powder_enabled_checkbox.setChecked(False)
            w.intensity_enabled_checkbox.setChecked(True)
            w.intensity_damping_spin.setValue(.4)
            capture_feedback('08-intensity-only')
            w.powder_enabled_checkbox.setChecked(True)
            capture_feedback('09-both-enabled')
            w.cycles.setValue(1)
            capture_feedback('10-one-cycle')
            assert w.intensity_enabled_checkbox.isChecked() and w.powder_enabled_checkbox.isChecked()
            assert not w.intensity_enabled_checkbox.isEnabled()
            w.cycles.setValue(3)
            assert w.intensity_damping_spin.value() == .4
            w.back_button.click()
            settle()
            w._go_to_map_feedback()
            settle()
            assert w.intensity_damping_spin.value() == .4 and w.powder_enabled_checkbox.isChecked()
            assert source.read_bytes() == original
        w.dialog.close()
(OUT / f'geometry-{scale}.json').write_text(json.dumps(records, indent=2), encoding='utf8')
print('Actual Qt acceptance passed at scale', scale)
