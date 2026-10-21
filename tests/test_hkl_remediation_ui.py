"""Actual Qt tooltip, search, clipboard and geometry acceptance at three DPIs."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_hkl_remediation_three_scales():
    for scale in ('1', '1.25', '1.5'):
        result = subprocess.run([sys.executable, __file__, '--child'], cwd=ROOT,
            env=os.environ | {'QT_QPA_PLATFORM':'offscreen', 'QT_SCALE_FACTOR':scale,
                              'PHASE_STUDIO_STARTUP_PROBE':'1'},
            capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, scale+'\n'+result.stdout+result.stderr


def check():
    import copy
    import itertools
    import json
    import tempfile
    import time
    from dataclasses import replace
    from unittest.mock import patch
    sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
    from PySide6.QtCore import QPoint, QRect, QSize, QSettings, QTimer, Qt, QItemSelectionModel
    from PySide6.QtGui import QScreen, QTextDocument
    from PySide6.QtWidgets import QApplication, QLabel, QToolTip, QTableWidgetSelectionRange
    from PySide6.QtTest import QTest
    from phase_studio import app as a
    from phase_studio.hkl_diagnostics_ui import _detail_dialog, validation_dialog
    from phase_studio.scientific_typography import scientific_tooltip
    from phase_studio.ui_style import _wrap_tooltip_html
    from test_hkl_diagnostics import DiagnosticsTests
    qt = QApplication([]);a.apply_phase_studio_style(qt)
    scale = float(os.environ['QT_SCALE_FACTOR'])
    out = ROOT/'build/acceptance-hkl-remediation-2.0.5'/f'scale-{scale}'
    out.mkdir(parents=True, exist_ok=True)
    records = {}

    def settle():
        for _ in range(20): qt.processEvents()

    def plain(html):
        document = QTextDocument();document.setHtml(html)
        return document.toPlainText()

    def snap(name, widget):
        settle();assert widget.grab().save(str(out/(name+'.png')))

    def query(view, text):
        view.hkl_search.setText(text)
        QTest.keyClick(view.hkl_search, Qt.Key_Return)
        deadline = time.monotonic()+8
        while view.hkl_preview_label.text().startswith('Searching'):
            QTest.qWait(10);settle()
            assert time.monotonic() < deadline
        return view.hkl_preview_label.text()

    with tempfile.TemporaryDirectory() as tmp, patch.object(QScreen, 'availableGeometry', return_value=QRect(0,0,int(1920/scale),int(1040/scale))):
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tmp)
        fixture = DiagnosticsTests();fixture.setUp()
        with patch.object(a.IterativeSuperflipPipelineQtGUI, 'load_settings', lambda self:None), \
                patch.object(a.IterativeSuperflipPipelineQtGUI, 'save_settings', lambda self:None), \
                patch.object(a.IterativeSuperflipPipelineQtGUI, 'refresh_sharped_models', lambda self:None):
            win = a.IterativeSuperflipPipelineQtGUI();win.timer.stop()
        triples = list(itertools.islice(itertools.product(range(1,9),range(9),range(9)),630))+[(-7,2,-1)]
        load = fixture.load('\n'.join(f'{h} {k} {l} 10 .1' for h,k,l in triples))
        before = copy.deepcopy(load.diagnostics)
        view = validation_dialog(win,load);view.show();settle()
        assert view.hkl_preview_label.text()=='Showing all 631 records'
        assert not any('Input-integrity issues:' in plain(label.text()) for label in view.findChildren(QLabel))
        explanation = ('Input integrity checks parsing, reflection indices, auxiliary values and duplicate records. '
                       'It does not establish experimental or scientific validity.')
        assert plain(view.hkl_integrity_status.toolTip()) == explanation
        snap('01-validation',view)
        # Render the actual QToolTip, as well as inspecting its QTextDocument text.
        label = view.hkl_integrity_status
        QToolTip.showText(label.mapToGlobal(QPoint(0,label.height())),label.toolTip(),label)
        settle()
        tooltip = next(w for w in qt.topLevelWidgets() if w.objectName()=='qtooltip_label' and w.isVisible())
        assert plain(tooltip.text()) == explanation
        snap('02-integrity-tooltip',tooltip);QToolTip.hideText()
        for source in ('C:/project A & B/"quoted"/<sample>/data.hkl', 'I < 3 & F > 2', '<qt>not trusted HTML</qt>'):
            wrapped = _wrap_tooltip_html(source)
            assert scientific_tooltip(wrapped)==wrapped
            assert _wrap_tooltip_html(scientific_tooltip(source,literal=True))==scientific_tooltip(source,literal=True)
            assert plain(scientific_tooltip(source,literal=True))==source
            probe=QLabel();probe.setToolTip(source)
            for _ in range(4): probe.setToolTip(scientific_tooltip(probe.toolTip()))
            assert plain(probe.toolTip())==source
            probe.deleteLater()
        for widget in view.findChildren(a.QWidget):
            tip=widget.toolTip()
            if tip:
                rendered=plain(tip)
                assert '<div' not in rendered and '<qt>' not in rendered and '&quot;' not in rendered
        assert query(view,'  -7   2  -1  ')=='1 match · Showing 1'
        assert view.hkl_table.model().index(0,0).data(Qt.UserRole) == -7
        snap('03-exact-negative-search',view)
        assert query(view,'-7 2 1')=='No matching reflections'  # No Friedel/symmetry expansion.
        snap('13-no-search-results',view)
        assert query(view,'1')=='81 matches · Showing 81'
        assert query(view,'invalid')=='No matching reflections'
        assert query(view,'1 2 3 4')=='No matching reflections'
        assert query(view,'')=='Showing all 631 records'
        view.hkl_table.selectRow(0)
        view.hkl_table.selectionModel().select(view.hkl_table.model().index(1,0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
        view.hkl_copy_selected_button.click()
        copied=QApplication.clipboard().text().splitlines()
        assert len(copied)==3 and copied[1].startswith('1\t0\t0\t10.0')
        snap('04-selection-copy',view)
        detail=_detail_dialog(view,load.diagnostics);detail.show();settle()
        assert detail.size()==QSize(1050,620)
        for index in range(7):
            detail.hkl_details_tabs.setCurrentIndex(index);settle()
            assert detail.size()==QSize(1050,620)
            assert detail.hkl_details_tabs.widget(index).horizontalScrollBar().maximum()==0
            snap(f'05-advanced-tab-{index}',detail)
        detail.resize(1400,850);detail.move(9000,9000);detail.hkl_details_tabs.setCurrentIndex(3);detail.close()
        small=QRect(0,20,800,560)
        with patch.object(QScreen,'availableGeometry',return_value=small):
            restored=_detail_dialog(view,load.diagnostics);restored.show();settle()
            assert small.contains(restored.frameGeometry()),restored.frameGeometry()
            assert restored.hkl_details_tabs.currentIndex()==3 and restored.hkl_close_button.isVisible()
            snap('12-restored-reduced-monitor',restored);restored.close()
        assert load.diagnostics==before
        view.close()
        clean=fixture.load('1 2 1 10 .1\n')
        clean_view=validation_dialog(win,clean)
        assert plain(clean_view.hkl_integrity_status.text())=='Input integrity: No issues detected'
        clean_view.close()
        unknown=replace(clean,diagnostics=replace(clean.diagnostics,counts=tuple(
            (key,None if key=='invalid_indices' else value) for key,value in clean.diagnostics.counts)))
        unknown_view=validation_dialog(win,unknown)
        assert 'Some checks unavailable' in plain(unknown_view.hkl_integrity_status.text())
        unknown_view.close()
        # An independent large view fixture exercises presentation search only.
        # Diagnostic counters and source records remain unchanged.
        large=replace(load,reflections=load.reflections*500)
        large_view=validation_dialog(win,large);large_view.show();settle()
        heartbeats=[]
        heartbeat=QTimer();heartbeat.setInterval(10)
        heartbeat.timeout.connect(lambda:heartbeats.append(time.monotonic()))
        heartbeat.start();started=time.monotonic()
        assert query(large_view,'1')=='40,500 matches · Showing 40,500'
        assert large_view.hkl_table.model().rowCount()==40500
        assert len(heartbeats)>1
        records.update(large_records=len(large.reflections),first_query_seconds=time.monotonic()-started,
                       heartbeat_count=len(heartbeats),diagnostics_unchanged=load.diagnostics==before)
        heartbeat.stop();large_view.close();win.close();fixture.tearDown()
    (out/'acceptance.json').write_text(json.dumps(records,indent=2),encoding='utf8')
    print('PASS actual tooltip rendering, indexed search, copy and geometry at',scale,records)


if __name__=='__main__':
    check() if '--child' in sys.argv else test_hkl_remediation_three_scales()
