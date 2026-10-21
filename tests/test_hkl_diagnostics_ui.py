"""Actual Qt diagnostics geometry and shared report/export guards at three scales."""
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def check_gui():
    import tempfile
    import csv
    import json
    import threading
    import time
    from PySide6.QtCore import QSettings,Qt,QPoint
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication,QLabel
    from test_hkl_diagnostics import DiagnosticsTests
    from phase_studio import app as a
    from phase_studio import hkl_diagnostics as d
    app=QApplication([])
    a.apply_phase_studio_style(app)
    with tempfile.TemporaryDirectory() as tmp:
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,tmp)
        win=a.IterativeSuperflipPipelineQtGUI()
        fixture=DiagnosticsTests()
        fixture.setUp()
        load=fixture.load('\n'.join(f'{h} {k} 1 {h*k} .0527' for h in range(1,8) for k in range(1,7)))
        analysis=a.analyze_hkl_data(load.hkl_path,load.data_mode,load.cell,load.spacegroup,load.spacegroup_hm,load.source_note,_loaded=load)
        def settle():
            for _ in range(30):app.processEvents()
        dialog=win._build_hkl_completeness_dialog(analysis)
        dialog.show();dialog.resize(1120,950);settle()
        table=dialog.hkl_bins_table
        dialog.hkl_bins_toggle.setChecked(True);settle()
        visible=sum(table.rowViewportPosition(i)>=0 and table.rowViewportPosition(i)+table.rowHeight(i)<=table.viewport().height() for i in range(table.rowCount()))
        assert visible>=1,(visible,table.size().toTuple(),dialog.size().toTuple())
        table.scrollToBottom();settle()
        assert table.visualItemRect(table.item(table.rowCount()-1,0)).intersects(table.viewport().rect())
        table.scrollToTop()
        assert 'I/FWHM' not in dialog.summary_text
        assert len(dialog.hkl_figure.axes)==3
        assert all('/FWHM' not in ax.get_title()+ax.get_ylabel() for ax in dialog.hkl_figure.axes)
        assert 'width' not in dialog.hkl_axes
        assert 'FWHM constant' in dialog.hkl_compact_summary.text()
        rows=[dict(row) for row in analysis.diagnostics.shells]
        for i,row in enumerate(rows):
            if row['coverage'] is None: assert table.item(i,4).text()=='n/a'
            else: assert abs(float(table.item(i,4).text())-row['coverage'])<=.000501
        import numpy as np
        plotted=np.asarray(dialog.hkl_axes['intensity'].lines[0].get_ydata(),dtype=float)
        assert np.allclose(plotted,[r['mean_value'] if r['mean_value'] is not None else np.nan for r in rows],equal_nan=True)
        path=Path(tmp)/'bins.csv';d.export_shell_csv(path,analysis.diagnostics)
        exported=list(csv.DictReader(path.open()))
        assert len(exported)==table.rowCount()
        for row,expected in zip(exported,rows):
            assert row['mean_value']==('n/a' if expected['mean_value'] is None else str(expected['mean_value']))
        main_geometry=(dialog.hkl_plot_panel.geometry(),table.geometry(),dialog.hkl_canvas.size())
        dialog.hkl_advanced_button.click();settle()
        assert dialog.hkl_advanced.isVisible()
        dialog.hkl_advanced.hkl_capability_table.setCurrentCell(3,0);settle()
        from phase_studio.scientific_typography import scientific_text
        assert any(scientific_text('CC1/2') in label.text() for label in dialog.hkl_advanced.findChildren(QLabel))
        assert main_geometry==(dialog.hkl_plot_panel.geometry(),table.geometry(),dialog.hkl_canvas.size())
        dialog.resize(760,800);settle()
        assert dialog.hkl_content_splitter.height()>0
        assert dialog.rect().contains(dialog.findChildren(a.QPushButton)[-1].geometry())
        dialog.close()
        assert not dialog.hkl_advanced.isVisible()
        # A supported overlap tab and its export share the report's plot data.
        from unittest.mock import patch
        overlapping=fixture.load('1 2 1 10 .1\n2 2 1 20 .1\n3 2 1 30 .1\n',overlap_groups={(1,2,1):1,(2,2,1):1})
        overlap_analysis=a.analyze_hkl_data(overlapping.hkl_path,overlapping.data_mode,overlapping.cell,overlapping.spacegroup,overlapping.spacegroup_hm,overlapping.source_note,_loaded=overlapping)
        overlap_view=win._build_hkl_completeness_dialog(overlap_analysis)
        overlap_view.show();overlap_view.resize(1120,900);settle()
        overlap_geometry=(overlap_view.hkl_plot_panel.geometry(),overlap_view.hkl_bins_table.geometry())
        overlap_view.hkl_plot_tabs.setCurrentIndex(1)
        settle()
        assert overlap_view.hkl_plot_tabs.tabText(1)=='Peak overlap'
        assert [key for key,_ in overlap_view.hkl_bin_columns] == ['lo','hi','input','affected','percent','intensity_percent']
        assert sum(int(overlap_view.hkl_bins_table.model().index(i,3).data()) for i in range(overlap_view.hkl_bins_table.model().rowCount())) == 2
        assert sum(int(overlap_view.hkl_bins_table.model().index(i,2).data()) for i in range(overlap_view.hkl_bins_table.model().rowCount())) == 3
        for i,row in enumerate(overlap_view.hkl_overlap_bin_rows):
            assert '<' not in overlap_view.hkl_bins_table.model().index(i,0).data()
            if not row['input']:
                assert overlap_view.hkl_bins_table.model().index(i,4).data() == 'N/A'
                assert overlap_view.hkl_bins_table.model().index(i,5).data() == 'N/A'
        assert [tick.get_text() for tick in overlap_view.hkl_overlap_figure.axes[0].get_xticklabels()] == ['2 HKL']
        assert overlap_geometry==(overlap_view.hkl_plot_panel.geometry(),overlap_view.hkl_bins_table.geometry())
        overlap_view.hkl_advanced_button.click();settle()
        assert overlap_geometry==(overlap_view.hkl_plot_panel.geometry(),overlap_view.hkl_bins_table.geometry())
        expected=[dict(row)['overlap_fraction'] for row in overlap_analysis.diagnostics.shells]
        plotted=np.asarray(overlap_view.hkl_overlap_figure.axes[1].lines[0].get_ydata(),dtype=float)
        assert np.allclose(plotted,100*np.asarray(expected,dtype=float),equal_nan=True)
        plot_path=Path(tmp)/'overlap.svg'
        with patch.object(a.QFileDialog,'getSaveFileName',return_value=(str(plot_path),'SVG')):
            next(button for button in overlap_view.findChildren(a.QPushButton) if button.text()=='Export plot').click()
        assert 'Input HKL records in overlapping groups (%)' in plot_path.read_text(encoding='utf8')
        pdf_path=Path(tmp)/'main.pdf';overlap_view.hkl_figure.savefig(pdf_path)
        assert pdf_path.read_bytes().startswith(b'%PDF')
        overlap_view.close()
        # Invalid/origin-only input must retain access to Advanced Diagnostics.
        origin=fixture.load('0 0 0 10 .0527\n')
        invalid_view=win._build_hkl_validation_dialog(origin)
        invalid_view.show();settle();invalid_view.hkl_advanced_button.click();settle()
        assert invalid_view.hkl_advanced.isVisible()
        assert any('N/A' in value.text() for value in invalid_view.hkl_advanced.hkl_resolution_values.values())
        invalid_view.close()
        validation=win._build_hkl_validation_dialog(load)
        validation.show();validation.resize(1060,800);settle()
        headers=[validation.hkl_table.model().headerData(i,Qt.Horizontal) for i in range(validation.hkl_table.model().columnCount())]
        assert 'Phase (°)' not in headers and 'I/FWHM' not in headers
        validation.hkl_search.setText('2 2 1');QTest.qWait(220);settle()
        for _ in range(200):
            if not validation.hkl_preview_label.text().startswith('Searching'): break
            QTest.qWait(10);settle()
        assert validation.hkl_table.model().rowCount()==1
        assert [validation.hkl_table.model().index(0,i).data() for i in range(3)]==['2','2','1']
        validation.close()
        duplicates=fixture.load('1 2 1 10 .1\n1 2 1 20 .1\n2 2 1 30 .1\n')
        duplicate_view=win._build_hkl_validation_dialog(duplicates)
        duplicate_view.show();settle()
        duplicate_view.hkl_search.setText('1 2 1')
        QTest.keyClick(duplicate_view.hkl_search,Qt.Key_Return);settle()
        for _ in range(200):
            if not duplicate_view.hkl_preview_label.text().startswith('Searching'): break
            QTest.qWait(10);settle()
        assert duplicate_view.isVisible() and duplicate_view.hkl_advanced is None
        assert duplicate_view.hkl_table.model().rowCount()==2
        assert [duplicate_view.hkl_table.model().index(i,3).data(Qt.UserRole) for i in range(2)]==[10,20]
        assert duplicate_view.hkl_preview_label.text() == '2 matches \u00b7 Showing 2'
        duplicate_view.hkl_table.selectRow(0);duplicate_view.hkl_copy_selected_button.click()
        assert '10.0' in QApplication.clipboard().text()
        duplicate_view.close()
        missing=fixture.load('1 2 1 10\n',a.REFLECTION_DATA_MODE_INTENSITY)
        v=win._build_hkl_validation_dialog(missing)
        assert v.hkl_table.model().index(0,4).data()=='n/a'
        assert '~' not in v.hkl_table.model().index(0,4).data()
        v.close()
        # Cancellation is cooperative, and must never deliver a result dialog.
        def slow():
            while True:
                d.check_cancelled();time.sleep(.002)
        win._start_hkl_background_task('Synthetic cancellable HKL test',slow,'hkl_load_result')
        QTest.qWait(650)
        assert win._hkl_progress_dialog.isVisible()
        next(button for button in win._hkl_progress_dialog.findChildren(a.QPushButton) if button.text()=='Cancel').click()
        win.hkl_task_worker.join(timeout=3)
        assert not win.hkl_task_worker.is_alive()
        queued=[]
        while not win.msg_queue.empty():queued.append(win.msg_queue.get_nowait()[0])
        assert 'hkl_load_result' not in queued and 'hkl_task_error' not in queued
        assert 'hkl_task_finished' in queued
        win._set_hkl_task_running(False)
        # Wizard's own large-file summary must also stay off the Qt thread.
        from unittest.mock import patch
        from PySide6.QtWidgets import QDialog
        from phase_studio import jana_superflip as js
        from test_wizard_text_clipping import write_inflip
        wizard_dir=Path(tmp)/'wizard';wizard_dir.mkdir()
        jana=wizard_dir/'Jana';(jana/'SUPERFLIP').mkdir(parents=True)
        for name in ('superflip.exe','EDMA.exe'):
            (jana/'SUPERFLIP'/name).write_bytes(b'fixture executable')
        js.application_dir=lambda:jana
        inflip=write_inflip(wizard_dir)
        inflip.write_bytes(b'# '+b'p'*1_000_001+b'\n'+inflip.read_bytes())
        original_loader=a.build_hkl_load_result
        thread_ids=[]
        def tracked_load(request):
            thread_ids.append(threading.get_ident())
            time.sleep(.08)
            return original_loader(request)
        with patch.object(QDialog,'exec',lambda self:QDialog.Rejected),patch.object(a,'build_hkl_load_result',tracked_load):
            wizard=js._JanaWorkflowWizard([],inflip)
            wizard.run();wizard.dialog.show()
            limit=time.monotonic()+10
            loops=0
            while time.monotonic()<limit:
                app.processEvents();time.sleep(.005);loops+=1
                if '432 HKL records' in wizard.reflections_value.text():break
            assert '432 HKL records' in wizard.reflections_value.text(),wizard.reflections_value.text()
            assert thread_ids and all(t!=threading.get_ident() for t in thread_ids)
            assert loops>=5
            wizard.dialog.close()
        fixture.tearDown()
        win.timer.stop();win.close()
    print('HKL UI, six visible bins, search, exports, plots and cancellation passed.')


def test_hkl_diagnostics_gui_dpi():
    for scale in ('1','1.25','1.5'):
        p=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child'],cwd=ROOT,
            env=os.environ|{'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':scale},capture_output=True,text=True,timeout=60)
        assert p.returncode==0,f'{scale}: {p.stdout}\n{p.stderr}'


if __name__=='__main__':
    check_gui() if '--child' in sys.argv else test_hkl_diagnostics_gui_dpi()
