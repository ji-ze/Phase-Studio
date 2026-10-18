"""Presentation-only advanced HKL guards, exercised in isolated Qt processes."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_advanced_diagnostics_semantics_and_geometry_at_three_scales():
    for scale in ('1', '1.25', '1.5'):
        result = subprocess.run([sys.executable, __file__, '--child'], cwd=ROOT,
            env=os.environ | {'QT_QPA_PLATFORM': 'offscreen', 'QT_SCALE_FACTOR': scale},
            capture_output=True, text=True, timeout=70)
        assert result.returncode == 0, scale + '\n' + result.stdout + result.stderr


def check():
    import copy
    import json
    import tempfile
    from dataclasses import replace
    from unittest.mock import patch
    sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
    from PySide6.QtCore import QSettings, QRect, Qt
    from PySide6.QtGui import QScreen
    from PySide6.QtWidgets import QApplication, QDialog, QLabel
    from test_hkl_diagnostics import DiagnosticsTests
    from phase_studio import app as a
    from phase_studio import hkl_diagnostics as d
    from phase_studio.hkl_diagnostics_ui import _detail_dialog, _spacegroup_display, presentation_report
    qt = QApplication([])
    a.apply_phase_studio_style(qt)
    scale = float(os.environ['QT_SCALE_FACTOR'])
    def settle():
        for _ in range(15): qt.processEvents()
    with tempfile.TemporaryDirectory() as tmp:
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tmp)
        fixture = DiagnosticsTests(); fixture.setUp()
        parent = QDialog()
        def view(load):
            dialog = _detail_dialog(parent, presentation_report(load))
            dialog.show(); settle()
            return dialog
        try:
            with patch.object(QScreen, 'availableGeometry', return_value=QRect(0,0,int(1920/scale),int(1040/scale))):
                mode = a.REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA
                for text, finite, missing, nonfinite in [('1 2 1 10 0 2\n',1,0,0),
                        ('1 2 1 10 ? 2\n',0,1,0), ('1 2 1 10 inf 2\n',0,0,1)]:
                    load = fixture.load(text, mode)
                    before = copy.deepcopy(load.diagnostics)
                    dialog = view(load)
                    rows = dialog.hkl_detail_rows
                    assert rows['Finite phase fields'].text() == str(finite)
                    assert rows['Missing phase values'].text() == str(missing)
                    assert rows['Nonfinite phase values'].text() == str(nonfinite)
                    assert 'Phase diagnostics' not in rows
                    assert load.diagnostics == before
                    dialog.close()
                load = fixture.load('1 2 1 10 .0527\n2 2 1 20 .0527\n', fwhm_units='degrees_2theta', wavelength=1)
                report = load.diagnostics
                source = 'C:/very long project directory/' + ('deep folder/'*35) + 'input.hkl'
                report = replace(report, source=source, source_note='HKL source: fbegin/endf block exported from C:/project/sample.inflip; cell/symmetry source: sample.inflip')
                load.diagnostics = report
                before = copy.deepcopy(report)
                before_path=Path(tmp)/'before.json'; report.export_json(before_path)
                dialog = view(load)
                rows = dialog.hkl_detail_rows
                assert rows['Phase diagnostics'].text() == 'N/A — phase column not supplied'
                assert 'Missing phase values' not in rows and 'Finite phase fields' not in rows
                assert rows['File provenance'].text() == 'Jana2020 / Superflip input'
                assert rows['Observation-processing provenance'].text() == 'Not documented in the available input'
                assert rows['Phases'].text() == 'Not supplied (expected for this format)'
                assert rows['Absent reflections with significance ≥3'].text() == 'N/A — no genuine measurement uncertainties'
                from phase_studio.scientific_typography import scientific_text
                assert rows['Verified FWHM units'].text() == scientific_text('degrees 2θ')
                assert rows['Group-size distribution'].text()
                assert rows['Space group'].text() == 'P2₁/n (#14)'
                assert 'P 1 21/n 1' in rows['Space group'].toolTip()
                assert 'Hall:' in rows['Space group'].toolTip()
                assert rows['Input filename'].findChildren(QLabel)[0].text() == 'input.hkl'
                dialog.hkl_copy_path.click(); assert QApplication.clipboard().text() == source
                table=dialog.hkl_capability_table
                previous=dialog.hkl_details_tabs.currentIndex()
                dialog.hkl_details_tabs.setCurrentIndex(6);settle()
                assert '#e8f0fa' in table.styleSheet() and '#153c70' in table.styleSheet()
                width=table.viewport().width()
                assert abs(table.columnWidth(0)-width*.25)<=2
                assert abs(table.columnWidth(1)-width*.18)<=2
                assert any('font-weight:400' in label.styleSheet() for label in dialog.findChildren(QLabel))
                dialog.hkl_details_tabs.setCurrentIndex(previous);settle()
                statuses={table.item(i,0).text():table.item(i,1).text() for i in range(table.rowCount())}
                assert statuses['Significance']=='Unavailable' and statuses['Peak overlap']=='Limited'
                table.setCurrentCell(3,0); assert scientific_text('CC1/2') in dialog.hkl_capability_reason.text()
                assert '98%' in rows['d98'].text()
                dialog.hkl_disclosures['Resolution methodology'].click(); settle()
                assert any('ULPs' in label.text() for label in dialog.findChildren(QLabel))
                initial = dialog.size()
                assert 950<=initial.width()<=1050 and 520<=initial.height()<=540, initial.toTuple()
                for index in range(7):
                    dialog.hkl_details_tabs.setCurrentIndex(index); settle()
                    assert dialog.size()==initial
                    scroll=dialog.hkl_details_tabs.widget(index)
                    assert scroll.horizontalScrollBar().maximum()==0
                    assert dialog.hkl_close_button.isVisible()
                    assert dialog.rect().contains(dialog.hkl_close_button.geometry())
                dialog.hkl_details_tabs.setCurrentIndex(5)
                dialog.hkl_disclosures['Overlap methodology'].click()
                dialog.hkl_disclosures['Group details'].click();settle()
                assert dialog.size()==initial
                assert dialog.hkl_details_tabs.widget(5).verticalScrollBar().maximum()>0
                assert dialog.hkl_group_distribution.isVisible()
                dialog.hkl_disclosures['Overlap methodology'].click()
                dialog.hkl_disclosures['Group details'].click();settle()
                assert dialog.size()==initial
                assert all('Science Gothic' not in label.font().family() for label in dialog.findChildren(QLabel))
                report.export_json(Path(tmp)/'after.json')
                assert before_path.read_bytes()==(Path(tmp)/'after.json').read_bytes()
                assert report==before
                dialog.resize(1040,610);dialog.hkl_details_tabs.setCurrentIndex(4);settle(); saved=dialog.size();dialog.close()
                restored=view(load)
                assert restored.size()==saved, (restored.size().toTuple(), saved.toTuple(), restored.hkl_settings.value('hklAdvanced/size'))
                assert restored.hkl_details_tabs.currentIndex()==4
                restored.close()
                # Only genuine all-clear results get the concise summary.
                clean=fixture.load('1 2 1 10 .0527\n')
                clean_view=view(clean)
                assert any(label.text().startswith('No reflection-index') for label in clean_view.findChildren(QLabel))
                clean_view.close()
                issue=fixture.load('1 0 0 10 .0527\n1 0 0 11 .0527\n')
                issue_view=view(issue)
                assert not any(label.text().startswith('No reflection-index') for label in issue_view.findChildren(QLabel))
                issue_view.close()
                # Significance availability follows actual evidence, not powder presets.
                amp=fixture.load('1 2 1 10 0 2\n',a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA)
                amp_view=view(amp)
                t=amp_view.hkl_capability_table
                assert next(t.item(i,1).text() for i in range(t.rowCount()) if t.item(i,0).text()=='Significance')=='Available'
                assert amp_view.hkl_detail_rows['Mean F/σ(F)'].text()=='5'
                amp_view.close()
                unverified=replace(amp,format_verified=False,diagnostics=None)
                unverified.diagnostics=d.build_diagnostics(unverified)
                u=view(unverified)
                assert u.hkl_detail_rows['Phase diagnostics'].text()=='N/A — phase-column meaning unverified'
                assert not unverified.diagnostics.available('column_semantics')
                u.close()
                optional=fixture.load('1 2 1 10 .0527\n')
                optional.diagnostics=replace(optional.diagnostics,source='',source_note='',cell=())
                missing_view=view(optional)
                assert missing_view.hkl_detail_rows['Input filename'].findChildren(QLabel)[0].text()=='Not supplied'
                assert missing_view.hkl_detail_rows['Unit cell'].text()=='Not supplied'
                assert 'Not verified' in missing_view.hkl_detail_rows['Verified FWHM units'].text()
                assert 'Affected reflections' not in missing_view.hkl_detail_rows
                missing_view.close()
                assert _spacegroup_display('invalid setting')==('invalid setting','invalid setting')
                literal=replace(optional.diagnostics,source='C:/project/lambda/alpha.hkl')
                path_view=_detail_dialog(parent,literal);path_view.show();settle()
                assert path_view.hkl_detail_rows['Input filename'].findChildren(QLabel)[0].text()=='alpha.hkl'
                assert path_view.hkl_detail_rows['Full input path'].text()=='C:/project/lambda/alpha.hkl'
                path_view.hkl_copy_path.click();assert QApplication.clipboard().text()=='C:/project/lambda/alpha.hkl'
                path_view.close()
            # Stored oversized geometry must clamp, with Close outside the scrolling body.
            with patch.object(QScreen,'availableGeometry',return_value=QRect(0,0,640,420)):
                small=view(load)
                assert small.width()<=640 and small.height()<=420
                for i in range(7):
                    small.hkl_details_tabs.setCurrentIndex(i);settle()
                    assert small.rect().contains(small.hkl_close_button.geometry())
                    assert small.hkl_details_tabs.widget(i).horizontalScrollBar().maximum()==0
                small.close()
        finally:
            fixture.tearDown();parent.close()
    print('Advanced semantics, all four phase cases, provenance, dynamic capabilities, unchanged exports, geometry and accessibility passed.')


if __name__=='__main__':
    check() if '--child' in sys.argv else test_advanced_diagnostics_semantics_and_geometry_at_three_scales()
