"""Actual Qt search, lossless selected rows and constrained window restoration."""
import os
from pathlib import Path
import subprocess
import sys


def check_gui():
    import tempfile
    from unittest.mock import patch
    from PySide6.QtCore import QSettings, QRect, QPoint, Qt, QItemSelectionModel
    from PySide6.QtGui import QScreen
    from PySide6.QtWidgets import QApplication, QPushButton
    from PySide6.QtTest import QTest
    from test_hkl_diagnostics import DiagnosticsTests
    from phase_studio import app as a
    qt = QApplication([])
    a.apply_phase_studio_style(qt)
    factor = float(os.environ['QT_SCALE_FACTOR'])
    available = QRect(0,0,int(1920/factor),int(1040/factor))
    def settle():
        for _ in range(25): qt.processEvents()
    with tempfile.TemporaryDirectory() as tmp, patch.object(a.IterativeSuperflipPipelineQtGUI,'refresh_sharped_models',lambda self:None), patch.object(QScreen,'availableGeometry',return_value=available):
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,tmp)
        win = a.IterativeSuperflipPipelineQtGUI(); win.timer.stop()
        fixture = DiagnosticsTests(); fixture.setUp()
        try:
            load = fixture.load('\n'.join(f'{h} 0 1 12.345678901234567 .0527' for h in range(-450,451)))
            original = repr(load.reflections)
            dialog = win._build_hkl_validation_dialog(load); dialog.show(); settle()
            search,table = dialog.hkl_search,dialog.hkl_table
            assert search.isClearButtonEnabled()
            assert search.placeholderText()=='Find reflection (h k l), e.g. 0 2 0'
            assert table.model().rowCount()==901 and '901' in dialog.hkl_preview_label.text()
            assert len({table.columnWidth(c) for c in range(3)})==1
            for text,expected in [('300 0 1',300),('-300 0 1',-300),('0 0 1',0)]:
                search.setText(text); QTest.qWait(210); settle()
                for _ in range(200):
                    if not dialog.hkl_preview_label.text().startswith('Searching'): break
                    QTest.qWait(10);settle()
                assert table.model().rowCount()==1 and table.model().index(0,0).data(Qt.UserRole)==expected
            search.setText('no match'); QTest.qWait(210); settle()
            for _ in range(200):
                if not dialog.hkl_preview_label.text().startswith('Searching'): break
                QTest.qWait(10);settle()
            assert table.model().rowCount()==0 and dialog.hkl_preview_label.text()=='No matching reflections'
            search.clear(); QTest.qWait(210); settle()
            table.sortByColumn(0,Qt.DescendingOrder)
            assert table.model().index(0,0).data(Qt.UserRole)==450
            table.sortByColumn(0,Qt.AscendingOrder)
            assert table.model().index(0,0).data(Qt.UserRole)==-450
            selection = table.selectionModel()
            for row in (0,1): selection.select(table.model().index(row,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
            dialog.hkl_copy_selected_button.click()
            text = qt.clipboard().text().splitlines()
            assert text[0].split('\t')[:3]==['h','k','l'] and len(text)==3
            assert text[1].split('\t')[3]==str(load.reflections[0].value)
            assert repr(load.reflections)==original
            dialog.close()
            small = fixture.load('1 2 1 10 .1\n2 2 1 20 .1\n3 2 1 30 .1\n',overlap_groups={(1,2,1):1,(2,2,1):1})
            analysis = a.analyze_hkl_data(small.hkl_path,small.data_mode,small.cell,small.spacegroup,small.spacegroup_hm,_loaded=small)
            settings = QSettings(QSettings.defaultFormat(),QSettings.UserScope,'PhaseStudio','PhaseStudio')
            settings.setValue('hklCompleteness/windowRect',QRect(2400,1800,2100,1400))
            review = win._build_hkl_completeness_dialog(analysis); review.show(); settle()
            histogram = review.hkl_histogram_axis
            bins_before = [(p.get_x(),p.get_height(),p.get_width()) for p in histogram.patches]
            original_limits = histogram.get_xlim()
            review.hkl_histogram_focus.setCurrentIndex(1); settle()
            assert bins_before==[(p.get_x(),p.get_height(),p.get_width()) for p in histogram.patches]
            review.hkl_histogram_scale.setCurrentIndex(0); settle()
            review.hkl_histogram_focus.setCurrentIndex(0); settle()
            assert histogram.get_xlim()==original_limits
            close = next(b for b in review.findChildren(QPushButton) if b.text()=='Close')
            assert available.contains(QRect(close.mapToGlobal(QPoint()),close.size()))
            assert available.contains(review.frameGeometry())
            review.hkl_plot_tabs.setCurrentIndex(1); settle()
            assert review.hkl_advanced_button.isVisible()
            assert review.hkl_bins_table.model().headerData(5,Qt.Horizontal)=='Affected intensity in bin (%)'
            assert 'same interval' in review.hkl_bins_table.horizontalHeaderItem(5).toolTip()
            assert [key for key,_ in review.hkl_bin_columns]==['lo','hi','input','affected','percent','intensity_percent']
            review.hkl_content_splitter.setSizes([300,250]); settle()
            expected = review.hkl_content_splitter.sizes()
            geometry = review.geometry()
            review.accept()
            assert [int(x) for x in settings.value('hklCompleteness/splitter')]==expected, (settings.value('hklCompleteness/splitter'),expected)
            restored = win._build_hkl_completeness_dialog(analysis); restored.show(); settle()
            assert restored.geometry()==geometry
            assert all(abs(x-y)<=2 for x,y in zip(restored.hkl_content_splitter.sizes(),expected)), (restored.hkl_content_splitter.sizes(),expected,restored.geometry(),geometry)
            restored.showMaximized(); settle(); restored.showNormal(); settle()
            close = next(b for b in restored.findChildren(QPushButton) if b.text()=='Close')
            assert restored.rect().contains(QRect(close.mapTo(restored,QPoint()),close.size()))
            restored.close()
        finally:
            fixture.tearDown(); win.close()


def test_gui_final_polish_at_three_scales():
    root = Path(__file__).resolve().parents[1]
    for scale in ('1','1.25','1.5'):
        result = subprocess.run([sys.executable,__file__,'--check'],cwd=root,
            env=os.environ|{'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':scale,'PHASE_STUDIO_STARTUP_PROBE':'1'},capture_output=True,text=True,timeout=90)
        assert result.returncode==0,scale+'\n'+result.stdout+result.stderr


if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    check_gui()
