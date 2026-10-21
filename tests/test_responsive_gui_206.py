"""Read-only virtual HKL records and display-only histogram regression."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_responsive_scientific_views():
    result = subprocess.run([sys.executable, __file__, '--child'], cwd=ROOT,
        env=os.environ | {'QT_QPA_PLATFORM':'offscreen','PHASE_STUDIO_STARTUP_PROBE':'1'},
        capture_output=True,text=True,timeout=90)
    assert result.returncode == 0, result.stdout+result.stderr


def exercise():
    import copy
    import tempfile
    import time
    from unittest.mock import patch
    from PySide6.QtCore import QSettings, Qt, QItemSelectionModel
    from PySide6.QtGui import QKeySequence
    from PySide6.QtWidgets import QApplication, QTableView
    from PySide6.QtTest import QTest
    sys.path[:0] = [str(ROOT),str(ROOT/'tests')]
    from test_hkl_diagnostics import DiagnosticsTests
    from phase_studio import app as a, hkl_diagnostics_ui as ui
    from phase_studio.hkl_diagnostics import export_shell_csv
    import numpy as np
    app=QApplication([])
    fixture=DiagnosticsTests();fixture.setUp()
    with tempfile.TemporaryDirectory() as tmp, patch.object(a.IterativeSuperflipPipelineQtGUI,'refresh_sharped_models',lambda self:None),patch.object(a.IterativeSuperflipPipelineQtGUI,'load_settings',lambda self:None),patch.object(a.IterativeSuperflipPipelineQtGUI,'save_settings',lambda self:None):
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,tmp)
        win=a.IterativeSuperflipPipelineQtGUI();win.timer.stop()
        text='\n'.join(f'{i%8-4} {i//8%8-4} {i//64+1} {10000 if i==343 else (i%50+1)/10} .0527' for i in range(344))
        load=fixture.load(text)
        original=load.hkl_path.read_bytes();diagnostics=copy.deepcopy(load.diagnostics)
        view=ui.validation_dialog(win,load);view.show();app.processEvents()
        table=view.hkl_table;model=table.model()
        assert isinstance(table,QTableView) and model.rowCount()==344
        assert model.index(343,3).data(Qt.UserRole)==10000
        assert model.values.cache_info().currsize<344  # painting does not materialize the dataset
        table.sortByColumn(3,Qt.DescendingOrder)
        assert model.index(0,3).data(Qt.UserRole)==10000
        assert view.hkl_copy_selected_button.isEnabled() is False
        for row in (0,2): table.selectionModel().select(model.index(row,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
        table.setFocus();QTest.keySequence(table,QKeySequence.Copy)
        copied=app.clipboard().text().splitlines()
        assert len(copied)==3 and copied[1].split('\t')[3]=='10000.0'
        assert copied[2].split('\t')[3]==str(model.index(2,3).data(Qt.UserRole))
        assert model.rowCount()==344 and 'Selected: 2' in view.hkl_preview_label.text()
        # Prefixes include duplicates and all matches, never the old 200-row cap.
        view.hkl_search.setText('-4');QTest.keyClick(view.hkl_search,Qt.Key_Return)
        deadline=time.monotonic()+8
        while view.hkl_preview_label.text().startswith('Searching'):
            QTest.qWait(10);assert time.monotonic()<deadline
        assert model.rowCount()==43
        assert all(model.index(i,0).data(Qt.UserRole)==-4 for i in range(43))
        view.close()
        analysis=a.analyze_hkl_data(load.hkl_path,load.data_mode,load.cell,load.spacegroup,load.spacegroup_hm,_loaded=load)
        complete=ui.completeness_dialog(win,analysis);complete.show();app.processEvents()
        before=repr(complete.diagnostics)
        export_shell_csv(Path(tmp)/'before.csv',complete.diagnostics)
        full_counts,full_edges=complete.hkl_full_histogram
        assert sum(full_counts)==344
        complete.hkl_histogram_focus.setCurrentIndex(1);app.processEvents()
        detail_counts,detail_edges=complete.hkl_detail_histogram
        assert 0<sum(detail_counts)<344 and detail_edges[-1]<10000
        assert complete.hkl_histogram_axis.get_ylim()[1] < full_counts.max()
        assert 'display-only bins' in complete.hkl_histogram_range_status.text()
        assert 'outside' in complete.hkl_histogram_range_status.text()
        assert not any(bar.get_visible() for bar in complete.hkl_histogram_axis.patches)
        complete.hkl_histogram_focus.setCurrentIndex(0);app.processEvents()
        assert all(bar.get_visible() for bar in complete.hkl_histogram_axis.patches)
        assert complete.hkl_histogram_axis.get_xlim()[1]==10000
        assert np.array_equal(full_counts,complete.hkl_full_histogram[0])
        assert np.array_equal(full_edges,complete.hkl_full_histogram[1])
        export_shell_csv(Path(tmp)/'after.csv',complete.diagnostics)
        assert (Path(tmp)/'before.csv').read_bytes()==(Path(tmp)/'after.csv').read_bytes()
        assert repr(complete.diagnostics)==before and load.diagnostics==diagnostics
        assert load.hkl_path.read_bytes()==original
        complete.close();win.close()
    fixture.tearDown()


if __name__=='__main__': exercise()
