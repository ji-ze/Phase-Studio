"""Genuine current execution/selector UI; scientific/prediction states are fixtures.

The local-run screenshots elsewhere use actual Superflip/EDMA. These additional
screens teach the combined workflow without using production SharpED credentials.
"""
import os,sys,json
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/"tests"))
from PySide6.QtCore import QCoreApplication,QEvent,QPoint
from PySide6.QtWidgets import QApplication,QDialog,QLabel
from phase_studio import app as engine
from phase_studio.autosolve_window import AutosolveWindow
from phase_studio.ui_style import apply_phase_studio_style
from phase_studio.map_quality import ValidationProfile,MapQualityMetrics
from test_jana_completion import build_window
app=QApplication([]);apply_phase_studio_style(app)
engine.IterativeSuperflipPipelineQtGUI.refresh_sharped_models=lambda self:None
backend,results=build_window(engine)
backend.timer.stop()
demo=Path("docs/tutorials/demo/tutorial_reference.cif")
for r in results:
    for path in (r.superflip_edma_cif,r.deblur_edma_cif):path.write_bytes(demo.read_bytes())
    r.sharped_model="SEED (cyclic CF)"
    r.validation_profile=ValidationProfile.REFERENCE_FREE.value
    r.superflip_quality=replace(r.superflip_quality,n_free_reflections=0,n_work_reflections=100)
    r.deblur_quality=replace(r.deblur_quality,n_free_reflections=0,n_work_reflections=100)
backend.results=results
backend.reference_atoms_for_plot=[]
backend.structure_cell=engine.gemmi.UnitCell(10,10,10,90,90,90)
backend.jana_wizard_context=engine.JanaWizardContext(True,"phase_recycling")
out=ROOT/"docs/tutorials/screenshots/workflow";out.mkdir(parents=True,exist_ok=True)
records=[];windows=[backend]
def events():
    for _ in range(12):app.processEvents()
def capture(name,w,targets=None):
    events()
    for label in w.findChildren(QLabel):
        assert "honzi" not in label.text().lower() and "ochlor" not in label.text().lower()
    pix=w.grab();assert pix.save(str(out/(name+".png")))
    boxes=[]
    for title,widget in (targets or []):
        p=widget.mapTo(w,QPoint());boxes.append(dict(label=title,rect=[p.x()/w.width(),p.y()/w.height(),widget.width()/w.width(),widget.height()/w.height()]))
    records.append(dict(id=name,path="screenshots/workflow/"+name+".png",captured=True,synthetic=True,source_window=type(w).__name__,
                        fixture="Illustrative combined-workflow state; synthetic structures and fixture metrics, no live inference or Jana transfer",redaction="No private data or credentials",targets=boxes))
try:
    window=AutosolveWindow(backend,"A",workflow_name="Superflip + SharpED");windows.append(window)
    window._refresh_timer.stop();window._rotate_timer.stop();window.auto_rotate_button.setChecked(False)
    backend._active_run_id="public-tutorial-ui-fixture"
    backend._set_run_status("RUNNING")
    backend._operation_states={"sf2":("Superflip",2,"running"),"nn1":("SharpED",1,"running")}
    backend._apply_cycle_progress_state(engine.CycleProgressState(2,3,"Superflip",1,7,detail="running",busy=True))
    window.show();window.resize(1500,950);window._refresh_tick();events()
    capture("execution-concurrent",window)
    backend._operation_states={};backend._set_run_status("COMPLETED")
    backend.progress_bar.setRange(0,3);backend.progress_bar.setValue(3)
    backend._set_overall_progress_text("3 of 3 cycles completed")
    window._refresh_tick();events();capture("execution-completed",window)
    window.full_cell_view_button.setChecked(True);events();capture("viewer-full-cell",window)
    window.molecule_view_button.setChecked(True);events();capture("viewer-complete-molecules",window)
    window.close()
    opened=[]
    with patch.object(engine.ResultSelectionDialog,"exec",lambda d:opened.append(d) or QDialog.Rejected):
        backend.open_result_selector("jana")
    selector=opened[0];windows.append(selector)
    selector._rotate_timer.stop();selector._auto_rotate_button.setChecked(False);selector.show();selector.resize(1450,900);events()
    selector._superflip_btn.setChecked(True);events()
    capture("selector-charge-flipping",selector,[("Choose the result family",selector._superflip_btn),("Select an actual candidate",selector._views["superflip"].table),("Pass the selected candidate",selector._action_button)])
    selector._sharped_btn.setChecked(True);events()
    capture("selector-model-prediction",selector)
    selector._views["deblurred"].table.selectRow(0);events();capture("selector-manual-candidate",selector)
    # Show the real asynchronous lifecycle without invoking EDMA on the test map.
    from types import SimpleNamespace
    selector._adjust_threshold_async=lambda c,add,callback:SimpleNamespace(threshold=.4)
    selector._change_threshold(True);events();capture("selector-edma-pending",selector)
    selector.close()
finally:
    for w in windows:w.close();w.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    (ROOT/"docs/tutorials/sources/result_screenshot_inventory.json").write_text(json.dumps(records,indent=2))
    import shiboken6
    shiboken6.delete(app)
