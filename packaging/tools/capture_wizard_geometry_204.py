"""Actual offline Wizard navigation, logical geometry assertions and ten captures."""
import os
import sys
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['PHASE_STUDIO_STARTUP_PROBE'] = '1'
os.environ.pop('SHARPED_API_TOKEN', None)
from PySide6.QtCore import QSettings, QRect, Qt, QPoint
from PySide6.QtGui import QScreen, QFontDatabase, QPainter
from PySide6.QtWidgets import QApplication, QDialog, QToolTip, QLabel
from PySide6.QtTest import QTest
from phase_studio import jana_superflip as js, app as engine
from phase_studio.credentials import CredentialStore
from phase_studio.version import VERSION
from phase_studio.ui_style import apply_phase_studio_style
from test_wizard_text_clipping import write_inflip

qt = QApplication([])
for name in ('segoeui.ttf', 'segoeuib.ttf', 'seguisym.ttf'):
    QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / name))
apply_phase_studio_style(qt)
scale = float(os.environ.get('QT_SCALE_FACTOR', '1'))
out = Path(os.environ.get('PHASE_STUDIO_GEOMETRY_OUTPUT', str(ROOT / ('build/acceptance-wizard-geometry-'+VERSION))))
out.mkdir(parents=True, exist_ok=True)
records = []
capture_enabled = os.environ.get("PHASE_STUDIO_GEOMETRY_CAPTURE", "1") == "1"


def settle():
    for _ in range(35):
        qt.processEvents()


def measure(w, name, expected=None, shot=None):
    settle()
    rect = w.dialog.geometry()
    if expected is not None:
        assert rect == expected, (name, rect, expected)
    assert w.scroll_area.horizontalScrollBar().maximum() == 0, name
    assert w.cancel_button.isVisible(), name
    assert w.footer.geometry().bottom() < w.dialog.height(), name
    records.append(dict(name=name, rect=rect.getRect(), frame=w.dialog.frameGeometry().getRect(),
                        header=w.brand_header.height(), banner=w.context_banner.height(),
                        footer=w.footer.height(), scroll=w.scroll_area.verticalScrollBar().maximum()))
    if shot and capture_enabled:
        QToolTip.hideText()
        assert w.dialog.grab().save(str(out / (shot + '.png')))
    return QRect(rect)


with tempfile.TemporaryDirectory() as tmp:
    base = Path(tmp)
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tmp)
    factory = lambda org, app: QSettings(str(base / (app + '.ini')), QSettings.IniFormat)
    original = js._qt_imports
    js._qt_imports = lambda: original() | {'QSettings': factory}
    js.credential_store = CredentialStore(backend=None)
    engine.QSettings = factory
    engine.IterativeSuperflipPipelineQtGUI.refresh_sharped_models = lambda self: None
    jana = base / 'Jana'
    (jana / 'SUPERFLIP').mkdir(parents=True)
    for name in ('superflip.exe', 'EDMA.exe'):
        (jana / 'SUPERFLIP' / name).write_bytes(b'UI fixture, never executed')
    js.application_dir = lambda: jana
    inflip = write_inflip(base)
    before = inflip.read_bytes()
    catalog = SimpleNamespace(default_model=js.SHARPED_ITERATIVE_MODEL,
                              models=[js.SHARPED_ONE_CYCLE_MODEL, js.SHARPED_ITERATIVE_MODEL, 'Manual model'])
    with patch.object(QScreen, 'availableGeometry', return_value=QRect(0, 0, int(2560 / scale), int(1400 / scale))), \
         patch.object(QDialog, 'exec', lambda self: QDialog.Rejected), \
         patch.object(js.SharpEDServerClient, 'get_models', return_value=catalog):
        w = js._JanaWorkflowWizard([], inflip)
        w.run()
        w.dialog.show()
        settle()
        rect = measure(w, 'initial', shot='01-workflow' if scale == 1 else '09-dpi-125' if scale == 1.25 else None)
        assert 720 <= rect.height() <= 780
        assert 960 <= rect.width() <= 1040
        assert w.scroll_area.verticalScrollBar().maximum() == 0
        assert w.update_menu.isVisible() and w.brand_header.isAncestorOf(w.update_menu)
        assert not w.footer.isAncestorOf(w.update_menu)
        from phase_studio.version import VERSION
        assert w.update_menu.text() == VERSION
        assert [a.text() for a in w.update_menu.menu().actions() if not a.isSeparator()] == [
            'Check for updates', 'Notify me when new versions are available', 'About Phase Studio']
        for tile in (w.original_superflip_tile, w.superflip_sharped_tile, w.autosolve_tile, w.professional_mode_tile):
            assert w.scroll_area.viewport().rect().contains(tile.mapTo(w.scroll_area.viewport(), tile.rect().bottomRight()))
            callback = tile._on_click
            activations = []
            tile._on_click = lambda:activations.append(True)
            tile._last_activation = 0
            QTest.mouseClick(tile,Qt.LeftButton,pos=tile.rect().center())
            tile._last_activation = 0
            QTest.mouseClick(tile.title_label,Qt.LeftButton,pos=tile.title_label.rect().center())
            QTest.keyClick(tile,Qt.Key_Return)
            QTest.keyClick(tile,Qt.Key_Space)
            assert len(activations)==4,tile.title_label.text()
            tile.setEnabled(False)
            QTest.keyClick(tile,Qt.Key_Space)
            assert len(activations)==4
            tile.setEnabled(True)
            tile._on_click = callback
        independent = []
        backing = w._get_backing_window()
        backing._set_widget_value_from_string(backing.inputs['work_dir'], str(base / 'hkl'))
        def exec_analysis(dialog):
            dialog.show()
            settle()
            independent.append(dict(title=dialog.windowTitle(), rect=dialog.geometry().getRect()))
            assert dialog.geometry() != rect
            dialog.close()
            return QDialog.Rejected
        def direct_analysis(title, worker, kind):
            result = worker()
            if kind == 'hkl_load_result':
                backing._show_hkl_load_result_dialog(result)
            else:
                backing._show_hkl_completeness_dialog(result)
        backing._start_hkl_background_task = direct_analysis
        with patch.object(QDialog, 'exec', exec_analysis):
            w.validate_hkl_button.click()
            measure(w, 'after-hkl-validation', rect)
            w.analyze_completeness_button.click()
            measure(w, 'after-hkl-completeness', rect)
            from phase_studio.hkl_diagnostics_ui import _detail_dialog, presentation_report
            request = engine.build_hkl_analysis_request_from_inflip(inflip, work_dir=base / 'advanced')
            advanced = _detail_dialog(w.dialog, presentation_report(engine.build_hkl_load_result(request)))
            advanced.exec()
            measure(w, 'after-hkl-advanced', rect)
        assert len(independent) == 3, independent
        backing.timer.stop()
        backing.close()
        w.files_toggle.setChecked(True)
        measure(w, 'input-expanded', rect, '02-input-expanded' if scale == 1 else None)
        w.reference_file.setText('preserved-reference.cif')
        w.model_file.setText('preserved-initial.xplor')
        w.files_toggle.setChecked(False)
        measure(w, 'input-collapsed', rect)
        w.workflow_state['key'] = js.WORKFLOW_SUPERFLIP_SHARPED
        w._workflow_changed()
        w._ensure_models_loaded = lambda **kwargs: None
        QToolTip.showText(w.dialog.pos(), 'Temporary contextual help', w.files_toggle)
        w._attempt_run()
        w.refresh_results.put(('ok', catalog))
        w.refresh_timer.timeout.emit()
        measure(w, 'configuration', rect, '03-configuration' if scale == 1 else None)
        QTest.qWait(350)
        assert not QToolTip.isVisible()
        assert w.stack.currentWidget() is w.page2
        w.sharped_toggle.setChecked(True)
        measure(w, 'sharped-expanded', rect, '04-sharped-expanded' if scale == 1 else None)
        w.sharped_toggle.setChecked(False)
        w.refresh_results.put(('ok', catalog))
        w.refresh_timer.timeout.emit()
        measure(w, 'model-refresh', rect)
        status = w.model_status.text()
        w.model_status.setText('Temporary model-catalogue warning. ' * 120)
        measure(w, 'long-model-status', rect)
        assert w.scroll_area.verticalScrollBar().maximum() > 0
        w.model_status.setText(status)
        measure(w, 'restored-model-status', rect)
        assert w.scroll_area.verticalScrollBar().maximum() == 0
        w.model.setCurrentText('Manual model')
        w.model.activated.emit(w.model.currentIndex())
        w.cycles.setValue(5)
        assert w.model.currentText() == 'Manual model'
        w.refresh_results.put(('ok', catalog))
        w.refresh_timer.timeout.emit()
        measure(w, 'manual-model-after-refresh', rect)
        assert w.model.currentText() == 'Manual model'
        w.primary_button.click()
        assert w.stack.currentWidget() is w.page3
        w.detected_data_mode_holder['mode'] = engine.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA
        w.input_reflections = [engine.Reflection(1, 0, 0, 10.0, 2.0)]
        w._sync_page3_for_data_type()
        assert not w.missing_parameters.isVisible()
        assert w.missing_group.x() < w.intensity_group.x()
        measure(w, 'single-feedback', rect, '07-single-crystal' if scale == 1 else None)
        w.missing_enabled_checkbox.setChecked(True)
        w.intensity_enabled_checkbox.setChecked(True)
        measure(w, 'single-options', rect)
        assert w.missing_parameters.isVisible() and w.intensity_sigma_spin.isVisible()
        w.missing_enabled_checkbox.setChecked(False)
        assert not w.missing_parameters.isVisible()
        measure(w, 'single-options-collapsed', rect)
        # A controlled parsed powder mode exercises the existing availability
        # renderer; no scientific data is converted or inferred by this fixture.
        w.detected_data_mode_holder['mode'] = engine.REFLECTION_DATA_MODE_INTENSITY_FWHM
        w._sync_page3_for_data_type()
        w.powder_enabled_checkbox.setChecked(False)
        w.intensity_enabled_checkbox.setChecked(False)
        measure(w, 'powder-disabled', rect, '05-powder-disabled' if scale == 1 else None)
        w.powder_enabled_checkbox.setChecked(True)
        w.intensity_enabled_checkbox.setChecked(True)
        measure(w, 'powder-enabled-warning', rect, '06-powder-enabled' if scale == 1 else None)
        assert not w.intensity_sigma_spin.isVisible()
        w.back_button.click()
        measure(w, 'back-configuration', rect)
        assert w.cycles.value() == 5 and w.model.currentText() == 'Manual model'
        w.back_button.click()
        measure(w, 'back-workflow', rect)
        assert w.reference_file.text() == 'preserved-reference.cif'
        assert w.model_file.text() == 'preserved-initial.xplor'
        if scale == 1:
            w.update_menu.menu().popup(w.update_menu.mapToGlobal(w.update_menu.rect().bottomLeft()))
            settle()
            assert w.update_menu.menu().isVisible()
            measure(w, 'version-menu', rect, '08-version-menu')
            # A popup is a separate native surface, not a child of grab().
            # Composite the actual two Qt surfaces at their logical position.
            menu = w.update_menu.menu()
            point = QPoint(w.dialog.width() - menu.width() - 8, w.brand_header.height() - 5)
            menu.move(w.dialog.mapToGlobal(point))
            pixmap = w.dialog.grab()
            painter = QPainter(pixmap)
            painter.drawPixmap(point, menu.grab())
            painter.end()
            if capture_enabled:
                assert pixmap.save(str(out / '08-version-menu.png'))
            w.update_menu.menu().hide()
        w.dialog.resize(920, 700)
        w.dialog.move(80, 60)
        resized = measure(w, 'user-resized')
        w._attempt_run()
        measure(w, 'resized-configuration', resized)
        w.primary_button.click()
        measure(w, 'resized-feedback', resized)
        w.back_button.click()
        w.back_button.click()
        measure(w, 'resized-back', resized)
        w.dialog.done(QDialog.Rejected)
        settle()
        saved = w.settings.value('wizard/windowGeometry')
        assert saved
        w2 = js._JanaWorkflowWizard([], inflip)
        w2.run()
        w2.dialog.show()
        settle()
        assert w2.dialog.geometry() == resized, (w2.dialog.geometry(), resized)
        w2.dialog.close()
        with patch.object(QScreen, 'availableGeometry', return_value=QRect(0, 0, int(1366 / scale), int(768 / scale))):
            narrow = js._JanaWorkflowWizard([], inflip)
            narrow.run()
            narrow.dialog.show()
            small = measure(narrow, 'constrained', shot='10-dpi-150-constrained' if scale == 1.5 else None)
            assert narrow.dialog.frameGeometry().left() >= 0
            assert narrow.dialog.frameGeometry().top() >= 0
            assert narrow.dialog.frameGeometry().right() < int(1366 / scale)
            assert narrow.dialog.frameGeometry().bottom() < int(768 / scale)
            narrow._ensure_models_loaded = lambda **kwargs: None
            narrow.workflow_state['key'] = js.WORKFLOW_SUPERFLIP_SHARPED
            narrow._workflow_changed()
            narrow._attempt_run()
            measure(narrow, 'constrained-configuration', small)
            narrow.sharped_toggle.setChecked(True)
            measure(narrow, 'constrained-expanded', small)
            narrow.primary_button.click()
            measure(narrow, 'constrained-feedback', small)
            narrow.dialog.close()
        assert inflip.read_bytes() == before
        assert len({(r['header'], r['banner'], r['footer']) for r in records}) == 1
        (out / ('geometry-' + str(scale) + '.json')).write_text(json.dumps(records, indent=2), encoding='utf8')
        (out / ('independent-' + str(scale) + '.json')).write_text(json.dumps(independent, indent=2), encoding='utf8')
print('PASS real navigation, disclosure, model completion, feedback, resize, persistence and constrained screen', scale)
