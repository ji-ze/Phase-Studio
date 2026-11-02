"""Isolated actual Qt candidate selection, input history, exports and DPI evidence."""
import os,sys,tempfile,json,csv
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from PySide6.QtWidgets import QApplication,QDialog,QFileDialog,QTabWidget
from PySide6.QtCore import QRect
from PySide6.QtGui import QScreen,QTextDocument
from phase_studio import app as a
from phase_studio.feedback_selection import FeedbackHistory
from phase_studio.feedback_diagnostics import load_summaries
from test_feedback_selection_207 import recorded_step
import test_jana_completion as fixture

scale=float(sys.argv[1]);qt=QApplication([]);a.apply_phase_studio_style(qt)
physical_width,physical_height=1920,1140
out=ROOT/'build/feedback-selection207/gui'/str(scale);out.mkdir(parents=True,exist_ok=True)

def events():
    for _ in range(6):qt.processEvents()

with tempfile.TemporaryDirectory() as tmp,patch.multiple(a.IterativeSuperflipPipelineQtGUI,
     refresh_sharped_models=lambda self:None,load_settings=lambda self:None,save_settings=lambda self:None),patch.object(
     QScreen,'availableGeometry',return_value=QRect(0,0,int(physical_width/scale),int(physical_height/scale))):
    root=Path(tmp)
    recorded_step(root,cycle=7)
    recorded_step(root,cycle=8,intensity=True,powder=False)
    recorded_step(root,cycle=1,start=5)
    from phase_studio.feedback_diagnostics_ui import FeedbackDiagnosticsDialog
    initial=FeedbackDiagnosticsDialog(None,load_summaries(root),root)
    initial.cycle.setCurrentIndex(initial.cycle.findData(0))
    assert initial.report['target_cycle']==1 and initial.report['operations']==[]
    assert initial.cumulative_model.rowCount()==2
    initial.close()
    backend,results=fixture.build_window(a,cycles=3)
    backend.results=[replace(r,cycle=r.cycle+6,powder_repartition_avg_change_percent=18.75) for r in results]
    backend.last_run_config.work_dir=root;backend.last_run_config.redistribute_overlaps=True
    backend.timer.stop()
    for context in ('jana','standalone'):
        opened=[]
        with patch.object(a.ResultSelectionDialog,'exec',lambda d:opened.append(d) or QDialog.Rejected):
            backend.open_result_selector(context)
        dialog=opened[0];dialog._rotate_timer.stop();dialog._auto_rotate_enabled=False
        dialog.show();events()
        for width in (int(physical_width/scale),int(physical_width/scale)-80):
            dialog.resize(min(1180,width-40),min(850,int(physical_height/scale)-40));events()
            assert dialog.height()<=int(physical_height/scale)
            assert dialog.rect().contains(dialog._footer.geometry())
            assert dialog._footer.rect().contains(dialog._action_button.geometry())
            assert dialog._preview_section.rect().contains(dialog._feedback_label.geometry())
            assert dialog._preview_section.rect().contains(dialog._feedback_details_button.geometry())
        texts=[]
        for source,button in (('superflip',dialog._superflip_btn),('deblurred',dialog._sharped_btn)):
            button.click();events()
            view=dialog._views[source]
            candidate=next(c for c in view.ordered if c.cycle==8)
            view.selected=candidate;events()
            snapshot=dialog.selection_snapshot
            before=(snapshot.candidate.map_path,snapshot.candidate.structure_path,snapshot.candidate.jana_model_path,
                    snapshot.candidate.candidate_id,snapshot.ready)
            dialog.refresh_feedback();events()
            after=dialog.selection_snapshot
            assert before==(after.candidate.map_path,after.candidate.structure_path,after.candidate.jana_model_path,
                            after.candidate.candidate_id,after.ready)
            text=dialog._feedback_label.accessibleName();texts.append(text)
            assert 'after cycle 7' in text and 'input for cycle 8' in text
            assert 'Powder overlap repartitioning: Applied' in text and 'modified 2/2' in text
            assert 'mean absolute relative change 18.75%' in text
            column=next(i for i in range(view.table.columnCount()) if view.table.horizontalHeaderItem(i).text()=='Feedback')
            assert view.table.item(view.ordered.index(candidate),column).text()=='Applied'
            # No new numeric column hides or relabels the independent quality metrics.
            assert any('F0.5' in view.table.horizontalHeaderItem(i).text() for i in range(view.table.columnCount()))
            dialog.grab().save(str(out/f'{context}-{source}.png'))
        assert texts[0]==texts[1]
        dialog._feedback_details_button.click();events()
        details=dialog._feedback_dialog
        assert details.cycle.currentData()==7 and details.report['target_cycle']==8
        assert details.cumulative_model.rowCount()==2
        assert details.written_model.rowCount()==2
        exact=root/f'{context}-written.csv'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(exact),'')):
            details.export_written_csv()
        actual=list(csv.DictReader(exact.open()))
        assert [float(r['before']) for r in actual]==[10.,20.]
        assert [float(r['after']) for r in actual]==[7.5,22.5]
        assert {r['source_cycle'] for r in actual}=={'7'} and {r['target_cycle'] for r in actual}=={'8'}
        exported=root/f'{context}-cumulative.csv'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(exported),'')):
            details.export_cumulative_csv()
        rows=list(csv.DictReader(exported.open()))
        assert [float(r['after']) for r in rows]==[7.5,22.5]
        assert {r['target_cycle'] for r in rows}=={'8'} and {r['source_cycle'] for r in rows}=={'0'}
        details.close()
        view=dialog._views[dialog._active_source]
        old=next(c for c in view.ordered if c.cycle==8)
        # Controlled EDMA completion changes threshold metadata, not reflection history.
        dialog._adjust_threshold_async=None
        dialog._adjust_threshold=lambda candidate,add:replace(candidate,edma_sigma=.45)
        original_text=dialog._feedback_label.accessibleName()
        dialog._change_threshold(True);events()
        assert dialog._feedback_label.accessibleName()==original_text
        from types import SimpleNamespace
        pending=[]
        def request(candidate,add,completed):
            req=SimpleNamespace(threshold=.4);pending.append((candidate,completed,req));return req
        dialog._adjust_threshold_async=request
        dialog._change_threshold(True)
        view.selected=next(c for c in view.ordered if c.cycle==9);events()
        assert 'after cycle 8' in dialog._feedback_label.accessibleName()
        assert 'Intensity correction: Applied' in dialog._feedback_label.accessibleName()
        prior_text=dialog._feedback_label.accessibleName()
        candidate,completed,req=pending[0]
        completed(replace(candidate,edma_sigma=.4),None,req);events()
        assert dialog.selected_candidate.cycle==9 and dialog._feedback_label.accessibleName()==prior_text
        # A persisted update is visible without rebuilding/reselecting the candidate.
        selected=dialog.selected_candidate
        recorded_step(root,cycle=8,powder=False,intensity=False)
        dialog.refresh_feedback();events()
        assert dialog.selected_candidate==selected and 'Status: Disabled' in dialog._feedback_label.accessibleName()
        dialog._feedback_history=FeedbackHistory(root/'old-run');dialog.refresh_feedback();events()
        assert 'Detailed Map Feedback changes unavailable for this run.' in dialog._feedback_label.accessibleName()
        assert not dialog._feedback_details_button.isEnabled()
        dialog._feedback_history=FeedbackHistory(root);dialog.refresh_feedback();events()
        assert dialog._feedback_details_button.isEnabled()
        dialog.close();events()
        recorded_step(root,cycle=8,intensity=True,powder=False)
    backend.close();events()
print('PASS candidate families, step provenance, cumulative CSV, identity, EDMA separation, refresh and layout',scale)
