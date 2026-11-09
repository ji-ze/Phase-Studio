"""Structured recovery, report provenance and bibliography; real Ochlor is read-only."""
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from phase_studio import app as a
from phase_studio.error_reporting import build_validation_report
from phase_studio.validation_issues import ValidationIssue

_application = None


@pytest.fixture
def window(tmp_path, monkeypatch):
    global _application
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    _application = QApplication.instance() or QApplication([])
    a.apply_phase_studio_style(_application)
    monkeypatch.setenv('PHASE_STUDIO_STARTUP_PROBE', '1')
    monkeypatch.setattr(a, 'QSettings', lambda *_args: QSettings(str(tmp_path/'settings.ini'), QSettings.IniFormat))
    for name in ('load_settings', 'save_settings', 'refresh_sharped_models'):
        monkeypatch.setattr(a.IterativeSuperflipPipelineQtGUI, name, lambda self: None)
    widget = a.IterativeSuperflipPipelineQtGUI()
    widget.timer.stop()
    widget.show()
    _application.processEvents()
    yield widget
    widget.close()
    _application.processEvents()


def test_citations_do_not_invent_publication_metadata():
    from phase_studio.scientific_citations import references
    from phase_studio.legal_content import citation_text
    refs = references('2.0.7')
    assert len(refs) == 4 and refs[0].citation == citation_text('2.0.7')
    assert refs[1].doi == '10.1107/S0021889807029238' and refs[1].pages == '786--790'
    assert refs[2].doi == '10.1107/S0021889812016068' and refs[2].pages == '575--580'
    assert 'Prathapa' in refs[2].authors and 'van Smaalen' in refs[2].authors
    assert not refs[3].year and not refs[3].doi and not refs[3].version
    assert 'Provisional' in refs[3].status
    assert 'year =' not in refs[3].bibtex() and 'doi =' not in refs[3].bibtex()
    assert '2025' not in refs[3].citation


def test_feedback_eligibility_is_explicit_without_changing_parameters():
    from phase_studio.feedback_presentation import effective_operation
    assert effective_operation(False, 1, 3, .25).status == 'Disabled'
    assert effective_operation(True, 3, 3, .25).status == 'Not eligible'
    zero = effective_operation(True, 1, 3, 0)
    assert not zero.active and zero.target_cycle == 2
    assert zero.status == 'Configured but inactive'
    assert not effective_operation(True, 1, 3, .25, available=False).active
    active = effective_operation(True, 1, 3, .25)
    assert active.active and active.target_cycle == 2


def test_short_about_scroll_and_exclusive_keyboard_selection(window):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from phase_studio.about_ui import AboutDialog
    dialog = AboutDialog(window, jana=False)
    dialog.show()
    dialog.resize(640, 360)
    _application.processEvents()
    expected = dialog.size()
    for index, card in enumerate(dialog.cards):
        card.setFocus(Qt.TabFocusReason)
        QTest.keyClick(card, Qt.Key_Space)
        _application.processEvents()
        assert sum(item.isChecked() for item in dialog.cards) == 1
        assert card.isChecked() and dialog.stack.currentIndex() == index
        assert dialog.size() == expected
        panel = dialog.stack.currentWidget()
        panel.verticalScrollBar().setValue(panel.verticalScrollBar().maximum())
        assert dialog.rect().contains(dialog.close_button.geometry().bottomRight())
    dialog.close()


def test_citation_selection_copy_links_and_export(window, tmp_path, monkeypatch):
    from PySide6.QtCore import Qt, QUrl
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QApplication, QFileDialog
    from phase_studio.citation_ui import CitationDialog
    viewer = CitationDialog(window)
    viewer.show()
    _application.processEvents()
    assert not viewer.copy_selected.isEnabled()
    viewer.list.setCurrentRow(2)
    viewer.copy_button.click()
    assert QApplication.clipboard().text() == viewer.references[2].citation
    opened = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: opened.append(url))
    viewer.source_button.click()
    assert opened == [QUrl('https://doi.org/10.1107/S0021889812016068')]
    viewer.list.item(1).setCheckState(Qt.Checked)
    viewer.list.item(3).setCheckState(Qt.Checked)
    viewer.copy_selected.click()
    assert QApplication.clipboard().text() == '\n\n'.join(r.citation for r in (viewer.references[1], viewer.references[3]))
    target = tmp_path/'references.bib'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *_args: (str(target), 'BibTeX'))
    viewer.export_button.click()
    exported = target.read_text(encoding='utf8')
    assert '@article{Superflip2007' in exported and '@misc{SharpED' in exported
    assert 'EDMA2012' not in exported and 'PhaseStudio' not in exported
    viewer.search.setText('Prathapa')
    assert not viewer.list.item(2).isHidden() and viewer.list.item(1).isHidden()
    viewer.close()


def config(tmp_path, threshold):
    hkl = tmp_path/'input.hkl'
    hkl.write_text('1 0 0 12 .05\n', encoding='utf8')
    return SimpleNamespace(i_over_sigma_min=threshold, extra_superflip_keywords='', powder_wavelength=1.541866,
        powder_separation_factor=.2, map_feedback_missing_enabled=False, map_export_format='xplor',
        input_source_mode=a.INPUT_MODE_EXTERNAL, superflip_referencefile=None, jana_inflip=None, hkl=hkl,
        first_cycle_modelfile=None, redistribute_overlaps=False, cycles=3, powder_redistribution_from_cycle=1,
        run_superflip=True)


def test_fwhm_recovery_uses_structured_target_and_never_executable_prose(window, tmp_path):
    cfg = config(tmp_path, 2)
    host = SimpleNamespace(_resolve_configured_data_mode=lambda cfg: a.REFLECTION_DATA_MODE_INTENSITY_FWHM)
    issues, details = a.IterativeSuperflipPipelineQtGUI._validate_run_config(host, cfg)
    assert len(issues) == 1 and issues[0].code == 'significance_fwhm'
    report = build_validation_report(issues, technical_details=details)
    assert report.title == 'Invalid reflection significance threshold'
    actions = window._error_actions(report)
    assert [action.label for action in actions] == ['Review significance threshold']
    before = window.inputs['i_over_sigma_min'].value()
    actions[0].callback()
    for _ in range(15):
        _application.processEvents()
    assert window.category_tabs.currentIndex() == 1
    assert window.advanced_tabs.tabText(window.advanced_tabs.currentIndex()) == 'Superflip'
    assert window.inputs['i_over_sigma_min'].hasFocus()
    assert window.inputs['i_over_sigma_min'].value() == before
    cfg.i_over_sigma_min = 0
    assert a.IterativeSuperflipPipelineQtGUI._validate_run_config(host, cfg)[0] == []
    incidental = build_validation_report(['Superflip is mentioned while explaining an unrelated input constraint.'])
    assert not any('Superflip' in action.label for action in window._error_actions(incidental))
    mixed = build_validation_report([ValidationIssue('Missing file', 'inflip_missing', 'jana_inflip'),
        ValidationIssue('Configure executable', 'edma_missing', 'edma_exe', 'Setup', True)])
    assert [action.label for action in window._error_actions(mixed)] == ['Select .inflip…', 'Set up EDMA']


def test_feedback_current_and_historical_reports_never_mix(window, tmp_path):
    assert not window.feedback_details.isEnabled()
    window.last_run_config = SimpleNamespace(run_id='current', work_dir=tmp_path)
    old = dict(run_id='earlier', source_cycle=1, target_cycle=2, definitions='Saved earlier run',
               operations=[dict(operation='intensity', status='Applied', modified_reflections=3)])
    window.feedback_reports[1] = old
    window._update_feedback_availability()
    assert window._current_feedback_reports() == [] and not window.feedback_details.isEnabled()
    current = old | dict(run_id='current', definitions='Actual evaluated current-run observation',
        operations=[dict(operation='intensity', status='No numerical change', modified_reflections=0)])
    window._receive_feedback_diagnostics(current)
    assert window.feedback_details.isEnabled()
    assert 'No reflection changes applied' in window.feedback_summary.text()
    assert window._current_feedback_reports() == [current]


def test_empty_feedback_reader_has_no_apparent_results_or_exports(window, tmp_path):
    from phase_studio.feedback_diagnostics_ui import FeedbackDiagnosticsDialog
    viewer = FeedbackDiagnosticsDialog(window, [], tmp_path, historical=True)
    viewer.show()
    _application.processEvents()
    assert not viewer.tabs.isVisible()
    assert not viewer.cycle.isVisible()
    assert all(not button.isEnabled() and not button.isVisible() for button in viewer.cycle_exports)
    assert viewer.report is None
    assert viewer.height() < 350
    viewer.close()


def test_real_ochlor_coverage_and_plot_data_remain_authoritative(window, tmp_path, monkeypatch):
    source = Path(os.environ.get('PS207_VISUAL_INFLIP', Path(__file__).resolve().parents[1]/'build/powder-final/wizard-input/ochlor_Superflip.inflip'))
    if not source.is_file():
        pytest.skip('Saved Ochlor authority is not present')
    original = source.read_bytes()
    assert hashlib.sha256(original).hexdigest() == '9136270c5e8ab6850ac6bd4390c301f17a32dcc83994184d8562735b9a26b88c'
    from phase_studio import hkl_diagnostics as hd
    from phase_studio.input_analysis import analysis_rows
    from phase_studio.input_analysis_ui import analyze_data_dialog
    from phase_studio.hkl_diagnostics_ui import presentation_report
    request = a.build_hkl_analysis_request_from_inflip(source, work_dir=source.parent)
    analysis = hd.cached_analysis(request)
    rows = analysis_rows(analysis, presentation_report(analysis))
    assert sum(row['records'] for row in rows) == 631
    assert sum(row['observed'] for row in rows) == sum(row['theory'] for row in rows) == 631
    assert analysis.d_min == analysis.d_full_98 == analysis.d_full_100 == 1.1990790613015834
    viewer = analyze_data_dialog(window, analysis)
    viewer.show()
    assert not viewer.analysis_image_button.isEnabled()
    viewer.analysis_tabs.setCurrentIndex(1)
    _application.processEvents()
    figure = viewer.analysis_figures[1]
    assert figure.axes[1].get_ylim() == (0, 100)
    assert list(figure.axes[0].lines[0].get_ydata()) == [row['records'] for row in rows]
    assert any('d_min / d98 / d_full' in text.get_text() for text in figure.axes[0].texts)
    assert viewer.analysis_image_button.isEnabled()
    from PySide6.QtWidgets import QFileDialog
    import json
    import csv
    for extension in ('png', 'svg'):
        target = tmp_path / ('resolution.' + extension)
        monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *_args, path=target: (str(path), ''))
        viewer.analysis_image_button.trigger()
        assert target.stat().st_size > 1000
    target = tmp_path/'graph.csv'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *_args: (str(target), ''))
    viewer.analysis_csv_button.trigger()
    exported = list(csv.DictReader(target.open(encoding='utf8')))
    assert [float(row['y']) for row in exported if row['series'] == 'records'] == [row['records'] for row in rows]
    target = tmp_path/'diagnostics.json'
    viewer.analysis_json_action.trigger()
    payload = json.loads(target.read_text(encoding='utf8'))
    assert payload['resolution']['d_min'] == analysis.d_min
    assert payload['resolution']['d98'] == analysis.d_full_98
    assert payload['resolution']['d_full'] == analysis.d_full_100
    assert payload['shells'] == rows
    viewer.analysis_tabs.setCurrentIndex(3)
    assert not viewer.analysis_image_button.isEnabled()
    assert source.read_bytes() == original
    viewer.close()


def test_help_topic_selectors_preserve_every_target(window):
    from PySide6.QtWidgets import QComboBox
    targets = []
    with patch.object(window, '_open_help_section', side_effect=targets.append):
        for advanced, scroll in ((False, window.help_scroll_basic), (True, window.help_scroll_advanced)):
            selector = scroll.findChild(QComboBox)
            assert selector is not None
            expected = [selector.itemData(index) for index in range(1, selector.count())]
            assert expected and all(target in window.help_sections for target in expected)
            for index in range(1, selector.count()):
                selector.activated.emit(index)
            assert targets[-len(expected):] == expected
