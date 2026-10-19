"""Display conventions and read-only membership; no network or phasing."""
import os
import subprocess
import sys
from pathlib import Path
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_resolution_coordinates_do_not_invent_invalid_resolution():
    from phase_studio.hkl_diagnostics_ui import resolution_coordinates, resolution_interval
    actual = resolution_coordinates([.1,.5,0,-1,float('nan'),float('inf')],True)
    assert np.allclose(actual[:2],[5,1])
    assert np.all(np.isnan(actual[2:]))
    assert np.allclose(resolution_coordinates([.1,.5]),[.1,.5])
    assert '∞' in resolution_interval(0,.5,True)


@pytest.mark.parametrize('values,expected',[([],10),([0],10),([45],50),([99],100),([100],100),([None,np.nan,18],20)])
def test_percent_limits(values,expected):
    from phase_studio.hkl_diagnostics_ui import overlap_percent_limit
    assert overlap_percent_limit(values)==expected


def test_actual_interactive_widgets_and_read_only_exports():
    result = subprocess.run([sys.executable,__file__,'--child'],cwd=ROOT,
        env=os.environ|{'QT_QPA_PLATFORM':'offscreen'},capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr


def exercise():
    import tempfile
    from dataclasses import replace
    from types import SimpleNamespace
    from unittest.mock import patch
    from PySide6.QtCore import QSettings,Qt,QTimer
    from PySide6.QtWidgets import QApplication,QLabel,QToolTip
    from matplotlib.backend_bases import MouseEvent
    sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
    from test_hkl_diagnostics import DiagnosticsTests
    from phase_studio import app as a,hkl_diagnostics_ui as ui
    from phase_studio.hkl_diagnostics import export_shell_csv
    app=QApplication([])
    fixture=DiagnosticsTests();fixture.setUp()
    with tempfile.TemporaryDirectory() as tmp,patch.object(a.IterativeSuperflipPipelineQtGUI,'refresh_sharped_models',lambda self:None),patch.object(a.IterativeSuperflipPipelineQtGUI,'load_settings',lambda self:None),patch.object(a.IterativeSuperflipPipelineQtGUI,'save_settings',lambda self:None):
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,tmp)
        win=a.IterativeSuperflipPipelineQtGUI();win.timer.stop()
        try:
            load=fixture.load('1 2 1 -10 .1\n2 2 1 0 .1\n3 2 1 5 .1\n4 2 1 50 .1\n5 2 1 100 .1\n',
                overlap_groups={(1,2,1):7,(2,2,1):7,(3,2,1):9,(4,2,1):9})
            analysis=a.analyze_hkl_data(load.hkl_path,load.data_mode,load.cell,load.spacegroup,load.spacegroup_hm,_loaded=load)
            original=load.hkl_path.read_bytes()
            dialog=ui.completeness_dialog(win,analysis);dialog.show()
            for _ in range(8):app.processEvents()
            report=dialog.diagnostics
            before=repr(report)
            export_shell_csv(Path(tmp)/'before.csv',report)
            report.export_json(Path(tmp)/'before.json',analysis)
            assert any('Indexed coverage' in dialog.hkl_bins_table.horizontalHeaderItem(c).text() for c in range(dialog.hkl_bins_table.columnCount()))
            assert 'experimentally resolved' in ui.COVERAGE_HELP
            x=np.asarray(dialog.hkl_axes['intensity'].lines[0].get_xdata())
            y=np.asarray(dialog.hkl_axes['intensity'].lines[0].get_ydata(),dtype=float)
            dialog.hkl_resolution_axis.setCurrentIndex(1)
            assert np.allclose(dialog.hkl_axes['intensity'].lines[0].get_xdata(),1/(2*x))
            assert dialog.hkl_axes['intensity'].xaxis_inverted()
            assert np.allclose(y,np.asarray(dialog.hkl_axes['intensity'].lines[0].get_ydata(),dtype=float),equal_nan=True)
            assert 'd</i>' in dialog.hkl_bins_title.text()
            hist=dialog.hkl_histogram_axis
            assert dialog.hkl_histogram_range_controls.isHidden()
            assert hist.get_xlim()==(-10,100)
            dialog.hkl_histogram_focus.setCurrentIndex(2)
            assert not dialog.hkl_histogram_range_controls.isHidden()
            bars=[(p.get_x(),p.get_width(),p.get_height()) for p in hist.patches]
            full=hist.get_xlim()
            dialog.hkl_histogram_min.setValue(0);dialog.hkl_histogram_max.setValue(50)
            dialog.hkl_histogram_apply.click()
            assert hist.get_xlim()==(0,50)
            assert '2 / 5' in dialog.hkl_histogram_range_status.text()
            dialog.hkl_histogram_scale.setCurrentIndex(0)
            assert hist.get_yscale()=='log'
            assert all(p.get_visible()==(p.get_height()>0) for p in hist.patches)
            for patch_bar in hist.patches:
                if patch_bar.get_visible():
                    assert np.all(np.isfinite(patch_bar.get_transform().transform(patch_bar.get_path().vertices)))
            with patch.object(a.QFileDialog,'getSaveFileName',return_value=(str(Path(tmp)/'selected.svg'),'SVG')):
                from PySide6.QtWidgets import QPushButton
                next(b for b in dialog.findChildren(QPushButton) if b.text()=='Export plot').click()
            assert 'selected range' in (Path(tmp)/'selected.svg').read_text(encoding='utf8')
            dialog.hkl_histogram_reset.click()
            assert dialog.hkl_histogram_range_controls.isHidden()
            assert hist.get_xlim()==full
            assert bars==[(p.get_x(),p.get_width(),p.get_height()) for p in hist.patches]
            dialog.hkl_histogram_scale.setCurrentIndex(1)
            dialog.hkl_canvas.draw()
            bar=next(p for p in hist.patches if p.get_height()>0)
            px,py=hist.transData.transform((bar.get_x()+bar.get_width()/2,bar.get_height()/2))
            event=MouseEvent('motion_notify_event',dialog.hkl_canvas,px,py)
            with patch.object(dialog.hkl_canvas,'draw_idle',side_effect=AssertionError('hover redraw')):
                dialog.hkl_hover_controllers[0].motion(event)
            assert 'Original input records' in QToolTip.text()
            dialog.hkl_plot_tabs.setCurrentIndex(1)
            assert dialog.hkl_overlap_resolution_axis.currentIndex()==1
            dialog.hkl_overlap_resolution_axis.setCurrentIndex(0)
            assert dialog.hkl_resolution_axis.currentIndex()==0
            assert np.allclose(dialog.hkl_overlap_figure.axes[1].lines[0].get_xdata(),x)
            assert dialog.hkl_overlap_figure.axes[1].get_ylim()[0]==0
            assert 'Input HKL records in overlapping groups (%)'==dialog.hkl_overlap_figure.axes[1].get_title()
            assert [t.get_text() for t in dialog.hkl_overlap_figure.axes[0].get_xticklabels()]==['2 HKL']
            table=dialog.hkl_bins_table
            table.sortItems(2,Qt.DescendingOrder);table.selectRow(0)
            dialog.hkl_copy_bins.click()
            assert 'Bin min' in app.clipboard().text() and len(app.clipboard().text().splitlines())==2
            inspected=[]
            def close_actual_inspector():
                current=app.activeModalWidget()
                assert current is not None
                lo,hi=dialog.hkl_selected_overlap_interval
                selected=current.records_model.indices
                assert np.all(current.records_model.stl[selected]>lo)
                assert np.all(current.records_model.stl[selected]<=hi)
                inspected.append(True)
                current.accept()
            QTimer.singleShot(20,close_actual_inspector)
            dialog.hkl_inspect_groups.click()
            assert inspected and dialog.hkl_group_detail is None
            detail=ui.overlap_group_dialog(dialog,analysis,report)
            model=detail.records_model
            assert model.rowCount()==4
            assert list(model.groups[model.indices])==[7,7,9,9]
            assert not any('2θ (degrees)'==name for name in model.columns)
            detail.records_view.selectRow(0);detail.copy_rows.click()
            assert 'Group ID' in app.clipboard().text()
            edge=model.stl[1]
            model.filter_records(2,model.stl[0]-1e-9,edge)
            assert list(model.indices)==[0,1]
            model.filter_records(3)
            assert model.rowCount()==0
            exact=ui.overlap_group_dialog(dialog,analysis,report,interval=(model.stl[0]-1e-9,model.stl[1]))
            initial_indices=exact.records_model.indices.copy()
            exact.apply_filter.click()
            assert np.array_equal(initial_indices,exact.records_model.indices)
            exact.close()
            large_raw=[replace(analysis.reflections_raw[0],h=i+1) for i in range(100000)]
            large=SimpleNamespace(reflections_raw=large_raw,cell=analysis.cell,data_mode=analysis.data_mode)
            metadata=dict(report.overlap)
            metadata.update(groups=tuple(((r.h,r.k,r.l),i//2+1) for i,r in enumerate(large_raw)),
                            size_distribution=((2,50000),))
            large_report=replace(report,overlap=tuple(metadata.items()))
            lazy=ui.overlap_group_dialog(dialog,large,large_report)
            assert lazy.records_model.rowCount()==100000
            assert lazy.records_model.sort_column==-1
            assert len(lazy.findChildren(QLabel))<15
            assert lazy.records_model.data(lazy.records_model.index(99999,4))=='2'
            lazy.records_view.sortByColumn(1,Qt.DescendingOrder)
            assert lazy.records_model.data(lazy.records_model.index(0,1))=='100000'
            lazy.records_model.filter_records(2)
            assert lazy.records_model.data(lazy.records_model.index(0,1))=='100000'
            lazy.close()
            export_shell_csv(Path(tmp)/'after.csv',report)
            report.export_json(Path(tmp)/'after.json',analysis)
            assert (Path(tmp)/'before.csv').read_bytes()==(Path(tmp)/'after.csv').read_bytes()
            assert (Path(tmp)/'before.json').read_bytes()==(Path(tmp)/'after.json').read_bytes()
            assert repr(report)==before and load.hkl_path.read_bytes()==original
            detail.close();dialog.close()
            for values in ('0','-2','7'):
                small=fixture.load(f'1 2 1 {values} .1\n')
                analyzed=a.analyze_hkl_data(small.hkl_path,small.data_mode,small.cell,small.spacegroup,small.spacegroup_hm,_loaded=small)
                view=ui.completeness_dialog(win,analyzed)
                view.hkl_histogram_scale.setCurrentIndex(0)
                assert sum(p.get_height() for p in view.hkl_histogram_axis.patches)==1
                view.close()
            nonfinite=fixture.load('1 2 1 nan .1\n')
            analyzed=a.analyze_hkl_data(nonfinite.hkl_path,nonfinite.data_mode,nonfinite.cell,nonfinite.spacegroup,nonfinite.spacegroup_hm,_loaded=nonfinite)
            view=ui.completeness_dialog(win,analyzed)
            assert view.hkl_histogram_axis is None and not view.hkl_histogram_apply.isEnabled()
            assert not view.hkl_inspect_groups.isEnabled()
            view.close()
        finally:
            fixture.tearDown();win.close()
    print('Interactive HKL, membership and export assertions passed')


if __name__=='__main__':exercise()
