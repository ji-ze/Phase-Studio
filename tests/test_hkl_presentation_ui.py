"""Actual Qt display acceptance at three DPI scales, including short windows."""
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def check_ui():
    import tempfile
    import csv
    import json
    import numpy as np
    from unittest.mock import patch
    from PySide6.QtCore import Qt,QSettings
    from PySide6.QtWidgets import QApplication,QLabel,QPushButton
    from PySide6.QtTest import QTest
    from phase_studio import app as a
    from phase_studio import hkl_diagnostics as d
    from phase_studio import hkl_diagnostics_ui as ui
    import test_hkl_diagnostics as fixtures
    app=QApplication([]);a.apply_phase_studio_style(app)
    with tempfile.TemporaryDirectory() as tmp:
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,tmp)
        win=a.IterativeSuperflipPipelineQtGUI()
        fixture=fixtures.DiagnosticsTests();fixture.setUp()
        def analysis(load):
            return a.analyze_hkl_data(load.hkl_path,load.data_mode,load.cell,load.spacegroup,load.spacegroup_hm,_loaded=load)
        def settle():
            for _ in range(25):app.processEvents()
        def visible_rows(table):
            return sum(table.rowViewportPosition(i)>=0 and table.rowViewportPosition(i)+table.rowHeight(i)<=table.viewport().height() for i in range(table.rowCount()))
        load=fixture.load('1 2 1 5.123456789 0 1.23456789\n2 2 1 -3 0 2\n3 2 1 0 0 1\n4 2 1 1000000000000 0 1\n0 0 0 99 0 1\n',a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA)
        original=analysis(load)
        view=win._build_hkl_completeness_dialog(original)
        view.show();view.resize(1120,950);settle()
        assert visible_rows(view.hkl_bins_table)>=6
        from phase_studio.scientific_typography import scientific_text
        assert view.hkl_axes['significance'].get_title()==scientific_text('Mean F/σ(F) vs resolution', 'plot')
        assert 'Mean F/σ(F)' in [view.hkl_bins_table.horizontalHeaderItem(j).text() for j in range(view.hkl_bins_table.columnCount())]
        rows=[dict(row) for row in view.diagnostics.shells]
        expected=np.asarray([row['mean_f_over_sigma'] for row in rows],dtype=float)
        assert np.allclose(np.asarray(view.hkl_axes['significance'].lines[0].get_ydata(),dtype=float),expected,equal_nan=True)
        derived=np.asarray([dict(row)['mean_significance'] for row in original.diagnostics.shells],dtype=float)
        assert np.allclose(np.asarray(view.hkl_derived_figure.axes[0].lines[0].get_ydata(),dtype=float),derived,equal_nan=True)
        assert any(label.text()=='Not reached' and ui.D98_NOT_REACHED in label.toolTip() for label in view.hkl_metrics_panel.findChildren(QLabel))
        assert view.hkl_bins_table.item(0,0).text()=='0.00000'
        assert view.hkl_bins_table.item(0,0).textAlignment() & Qt.AlignRight
        assert view.hkl_bins_table.horizontalHeaderItem(0).textAlignment() & Qt.AlignLeft
        hist=view.hkl_histogram_axis
        assert hist.get_yscale()=='log' and hist.get_xscale()=='linear'
        assert sum(p.get_height() for p in hist.patches)==4
        assert hist.get_xlim()[0]<=-3 and hist.get_xlim()[1]>=1e12
        assert len(hist.patches)<=160
        before_data=view.hkl_distribution_values.copy()
        view.hkl_histogram_scale.setCurrentIndex(1);settle()
        assert hist.get_yscale()=='linear' and np.array_equal(before_data,view.hkl_distribution_values)
        main=(view.geometry(),view.hkl_plot_panel.geometry(),view.hkl_bins_table.geometry(),view.hkl_canvas.size())
        view.hkl_advanced_button.click();settle()
        assert view.hkl_advanced.isVisible() and not view.hkl_advanced.isModal()
        assert main==(view.geometry(),view.hkl_plot_panel.geometry(),view.hkl_bins_table.geometry(),view.hkl_canvas.size())
        assert view.hkl_advanced.hkl_details_tabs.count()==7
        assert not any('parsed_records:' in label.text() for label in view.hkl_advanced.findChildren(QLabel))
        view.hkl_advanced.close();settle()
        assert not view.hkl_advanced_button.isChecked() and view.isVisible()
        plot_geometry=view.hkl_plot_panel.geometry();table_geometry=view.hkl_bins_table.geometry()
        view.hkl_plot_tabs.setCurrentIndex(1);settle()
        assert view.hkl_plot_panel.geometry()==plot_geometry and view.hkl_bins_table.geometry()==table_geometry
        svg=Path(tmp)/'derived.svg'
        with patch.object(a.QFileDialog,'getSaveFileName',return_value=(str(svg),'SVG')):
            next(button for button in view.findChildren(QPushButton) if button.text()=='Export plot').click()
        assert 'Derived' in svg.read_text(encoding='utf8')
        view.hkl_plot_tabs.setCurrentIndex(0);view.resize(760,700);settle()
        assert view.hkl_canvas.height()>=280
        assert view.hkl_chart_scroll.verticalScrollBar().maximum()>0
        view.hkl_chart_scroll.verticalScrollBar().setValue(view.hkl_chart_scroll.verticalScrollBar().maximum());settle()
        assert next(button for button in view.findChildren(QPushButton) if button.text()=='Close').isVisible()
        path=Path(tmp)/'shells.csv';d.export_shell_csv(path,view.diagnostics)
        csv_rows=list(csv.DictReader(path.open()))
        assert any(row['mean_f_over_sigma']==str(5.123456789/1.23456789) for row in csv_rows)
        path=Path(tmp)/'report.json';view.diagnostics.export_json(path,original)
        assert json.loads(path.read_text(encoding='utf8'))['resolution']['d98'] is None
        view.hkl_advanced_button.setChecked(True);settle();view.close()
        assert not view.hkl_advanced.isVisible()
        v=win._build_hkl_validation_dialog(load);v.show();v.resize(1120,800);settle()
        assert v.hkl_preview_label.text().startswith('Showing first 5 of 5 records')
        headers=[v.hkl_table.horizontalHeaderItem(i).text() for i in range(v.hkl_table.columnCount())]
        assert 'F/σ(F)' in headers and ui.DERIVED_LABEL not in headers
        assert v.hkl_table.item(0,0).text()=='1'  # original row order until a user sorts
        v.hkl_derived_checkbox.setChecked(True)
        assert v.hkl_table.horizontalHeaderItem(v.hkl_table.columnCount()-1).text()==ui.DERIVED_LABEL
        v.hkl_search.setText('3 2 1');QTest.qWait(220);settle()
        assert v.hkl_table.rowCount()==1 and '1 matching records (5 total)' in v.hkl_preview_label.text()
        assert v.hkl_table.item(0,5).text()=='0.0000'
        v.close()
        # Complete powder list exercises both compact summaries; variable
        # widths retain their curve while powder never gains significance.
        hkls=a.gemmi.make_miller_array(fixture.cell,fixture.sg,2.5,0,True)
        text='\n'.join(f'{h} {k} {l} {h*h+k*k+l*l+1} .0527' for h,k,l in hkls)
        powder=fixture.load(text)
        p=win._build_hkl_completeness_dialog(analysis(powder));p.show();p.resize(1120,900);settle()
        assert set(p.hkl_axes)=={'intensity','distribution'}
        assert '100%' in p.hkl_compact_summary.text() and 'FWHM constant: 0.0527' in p.hkl_compact_summary.text()
        assert visible_rows(p.hkl_bins_table)>=6
        assert not hasattr(p,'hkl_derived_figure') and p.hkl_plot_tabs.count()==1
        p.close()
        variable=fixture.load(text.rsplit('.0527',1)[0]+'.1')
        p=win._build_hkl_completeness_dialog(analysis(variable));p.show();p.resize(1120,900);settle()
        assert 'width' in p.hkl_axes and 'input units' in p.hkl_axes['width'].get_ylabel()
        assert 'significance' not in p.hkl_axes
        p.close()
        fixture.tearDown();win.timer.stop();win.close()
    print('Primary/secondary metrics, adaptive plots, detail geometry, precision, signed histogram, exports and closure passed.')


def test_hkl_presentation_gui_dpi():
    for scale in ('1','1.25','1.5'):
        result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child'],cwd=ROOT,
            env=os.environ|{'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':scale},capture_output=True,text=True,timeout=60)
        assert result.returncode==0,f'{scale}: {result.stdout}\n{result.stderr}'


if __name__=='__main__':check_ui() if '--child' in sys.argv else test_hkl_presentation_gui_dpi()
