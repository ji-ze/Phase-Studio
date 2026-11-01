"""Capture actual Qt widgets using synthetic data; outputs stay in ignored build/."""
import os
import sys
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(os.environ.get('PHASE_STUDIO_AUDIT_SOURCE_ROOT', str(ROOT)))
sys.path[:0] = [str(SOURCE), str(SOURCE / 'tests')]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['PHASE_STUDIO_STARTUP_PROBE'] = '1'


def capture(stage):
    from PySide6.QtCore import QSettings, QRect
    from PySide6.QtGui import QScreen
    from PySide6.QtWidgets import QApplication
    from phase_studio import app as a, hkl_diagnostics_ui as ui
    from test_hkl_diagnostics import DiagnosticsTests
    qt = QApplication([])
    a.apply_phase_studio_style(qt)
    factor = float(os.environ.get('QT_SCALE_FACTOR', '1'))
    width = int(int(os.environ.get('AUDIT_WIDTH', '1920')) / factor)
    height = int(int(os.environ.get('AUDIT_HEIGHT', '1140')) / factor)
    out = ROOT / 'build/audit-2.0.7' / stage
    out.mkdir(parents=True, exist_ok=True)
    fixture = DiagnosticsTests()
    fixture.setUp()
    with tempfile.TemporaryDirectory() as tmp, patch.object(QScreen, 'availableGeometry', return_value=QRect(0, 0, width, height)), patch.object(a.IterativeSuperflipPipelineQtGUI, 'refresh_sharped_models', lambda self: None), patch.object(a.IterativeSuperflipPipelineQtGUI, 'load_settings', lambda self: None), patch.object(a.IterativeSuperflipPipelineQtGUI, 'save_settings', lambda self: None):
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tmp)
        win = a.IterativeSuperflipPipelineQtGUI()
        win.timer.stop()
        win.inputs['input_source_mode'].setCurrentText(a.INPUT_MODE_LABELS[a.INPUT_MODE_EXTERNAL])
        win.inputs['reflection_data_mode'].setCurrentText(a.format_reflection_data_mode(a.REFLECTION_DATA_MODE_INTENSITY_FWHM))
        win.inputs['map_feedback_intensity_enabled'].setChecked(True)
        win._sync_map_feedback_widgets()
        win.show()
        qt.processEvents()
        win.resize(width, height)
        if os.environ.get('PHASE_STUDIO_AUDIT_ASSERT') == '1':
            control = win.inputs['map_feedback_intensity_max_i_over_sigma']
            control.setValue(2.5)
            win._sync_map_feedback_widgets()
            assert control.isHidden() and not control.isEnabled() and control.value() == 2.5
            assert not win.feedback_uncertainty_note.isHidden()
            assert 'saved positive' in win.feedback_uncertainty_note.text()
            win.inputs['reflection_data_mode'].setCurrentText(a.format_reflection_data_mode(a.REFLECTION_DATA_MODE_INTENSITY))
            assert not control.isHidden() and control.value() == 2.5
            assert win.feedback_uncertainty_note.isHidden()
            win.inputs['reflection_data_mode'].setCurrentText(a.format_reflection_data_mode(a.REFLECTION_DATA_MODE_INTENSITY_FWHM))
            assert not win.feedback_reset_significance.isHidden()
            win.feedback_reset_significance.click()
            assert control.value() == 0 and win.feedback_reset_significance.isHidden()
            win._sync_map_feedback_widgets()
            wavelength = win.inputs['powder_wavelength']
            assert wavelength.value() == 0 and wavelength.text() == 'Automatic'
        for index in range(win.basic_tabs.count()):
            win.basic_tabs.setCurrentIndex(index)
            qt.processEvents()
            win.grab().save(str(out / (win.basic_tabs.tabText(index).replace(' ', '-') + '.png')))
        win.basic_tabs.setCurrentIndex(next(i for i in range(win.basic_tabs.count()) if win.basic_tabs.tabText(i) == 'Map feedback'))
        limit = win.inputs['map_feedback_intensity_max_i_over_sigma']
        limit.setValue(2.5)
        win._sync_map_feedback_widgets()
        qt.processEvents()
        win.grab().save(str(out / 'Map-feedback-saved-limit.png'))
        limit.setValue(0)
        win._sync_map_feedback_widgets()
        inventory = dict(requested_logical=[width, height], actual_logical=[win.width(), win.height()], dpr=win.devicePixelRatioF(), fits=win.width() <= width and win.height() <= height)
        (out / 'geometry.json').write_text(json.dumps(inventory, indent=2))
        import numpy as np
        win.structure_cell = fixture.cell
        win.reference_atoms_for_plot = [a.AtomSite('C1', 'C', np.array([.1, .1, .1])), a.AtomSite('C2', 'C', np.array([.2, .1, .1]))]
        win._update_structure_views()
        qt.processEvents()
        win.grab().save(str(out / 'molecular-subset.png'))
        load = fixture.load('1 2 1 10 .0527\n2 2 1 20 .0527\n3 2 1 30 .0527')
        analysis = a.analyze_hkl_data(load.hkl_path, load.data_mode, load.cell, load.spacegroup, load.spacegroup_hm, _loaded=load)
        for name, dialog in [('validation', ui.validation_dialog(win, load)), ('completeness', ui.completeness_dialog(win, analysis))]:
            dialog.resize(1060, 680)
            dialog.show()
            qt.processEvents()
            dialog.grab().save(str(out / (name + '.png')))
            dialog.close()
        source = Path(tmp) / 'synthetic.inflip'
        source.write_text('dimension 3\ncell 10 10 10 90 90 90\nspacegroup P1\ncomposition C2\ndataformat intensity fwhm\nfbegin\n1 0 0 10 .1\n2 0 0 20 .1\nendf\n')
        reference = Path(tmp) / 'synthetic-reference.cif'
        reference.write_text('data_synthetic\n_diffrn_radiation_wavelength 0.39986\n')
        request = a.build_hkl_analysis_request_from_inflip(source, reference, Path(tmp) / 'work')
        resolved = a.build_hkl_load_result(request)
        dialog = ui.validation_dialog(win, resolved)
        dialog.resize(1060, 680)
        dialog.show()
        qt.processEvents()
        if os.environ.get('PHASE_STUDIO_AUDIT_ASSERT') == '1':
            assert 'synthetic.inflip' in dialog.hkl_metadata_provenance.text()
            assert '0.39986' in dialog.hkl_effective_wavelength.text()
        dialog.grab().save(str(out / 'wavelength-validation.png'))
        dialog.close()
        win.close()
    fixture.tearDown()


if __name__ == '__main__':
    capture(sys.argv[1])
