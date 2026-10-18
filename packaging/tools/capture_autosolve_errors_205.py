"""Render the real execution window with explicit synthetic lifecycle fixtures.

No API calls, external scientific jobs or Jana publication. Run independently
with QT_SCALE_FACTOR=1, 1.25 or 1.5; first argument labels before/after output.
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QLabel
from phase_studio import app as engine
from phase_studio.autosolve_window import AutosolveWindow
from phase_studio.ui_style import apply_phase_studio_style
from phase_studio.map_quality import MapQualityMetrics

work = ROOT / "build/acceptance-autosolve-errors-2.0.5/fixtures" / ("scale-" + os.environ.get("QT_SCALE_FACTOR","1"))
work.mkdir(parents=True, exist_ok=True)
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(work / "settings"))
engine.IterativeSuperflipPipelineQtGUI.load_settings = lambda self: None
engine.IterativeSuperflipPipelineQtGUI.save_settings = lambda self: None
engine.IterativeSuperflipPipelineQtGUI.refresh_sharped_models = lambda self: None
app = QApplication([])
apply_phase_studio_style(app)
backend = engine.IterativeSuperflipPipelineQtGUI()
backend.jana_wizard_context = engine.JanaWizardContext(launched_from_jana_wizard=True, launch_mode="autosolve")
backend.autosolve_is_jana = lambda: True
backend._active_run_id = "render-fixture"
backend.launch_mode = "autosolve"
backend._set_run_status("RUNNING")
backend.progress_bar.setRange(0,5)
backend.progress_bar.setValue(0)
backend._set_overall_progress_text("0 of 5 cycles completed")
window = AutosolveWindow(backend, "A", workflow_name="SharpED Autosolve")
window._refresh_timer.stop()
window._rotate_timer.stop()
window.auto_rotate_button.setChecked(False)
marker=QLabel("SYNTHETIC EXECUTION STATE — OFFLINE UI FIXTURE — NO SCIENTIFIC RUN / JANA PUBLICATION")
marker.setWordWrap(True)
marker.setStyleSheet("color: #52658b; padding: 3px 12px;")
window.centralWidget().layout().insertWidget(1,marker)
window.show()
out = ROOT / "build/acceptance-autosolve-errors-2.0.5" / ("scale-" + os.environ.get("QT_SCALE_FACTOR", "1"))
out.mkdir(parents=True, exist_ok=True)

def structure(name, points):
    path = work / (name + ".cif")
    path.write_text("data_render_fixture\n_cell_length_a 60\n_cell_length_b 60\n_cell_length_c 60\n"
        "_cell_angle_alpha 90\n_cell_angle_beta 90\n_cell_angle_gamma 90\n_space_group_name_H-M_alt 'P 1'\n"
        "loop_\n_atom_site_label\n_atom_site_type_symbol\n_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\n"
        + "\n".join(f"C{i+1} C {x/60:.9f} {y/60:.9f} {z/60:.9f}" for i, (x,y,z) in enumerate(points)) + "\n", encoding="utf8")
    return path

dense = structure("dense-fixture", [(10+x*1.4, 10+y*1.4, 10+z*1.4) for x in range(5) for y in range(4) for z in range(3)])
elongated = structure("elongated-fixture", [(10+i*1.4, 10+(i%2)*.3, 10) for i in range(24)])
sfmap = work / "superflip-fixture.xplor"
dbmap = work / "sharped-fixture.xplor"
sfmap.write_text("UI fixture only, never used for handoff", encoding="utf8")
dbmap.write_text("UI fixture only, never used for handoff", encoding="utf8")
result = engine.CycleResult(cycle=1, model_source="none", model_in=None, model_metric=None,
    superflip_map=sfmap, superflip_edma_cif=dense, superflip_metric=None,
    deblur_map=dbmap, deblur_edma_cif=elongated, deblur_metric=None,
    sharped_model="UNIVERSAL", superflip_quality=MapQualityMetrics(), deblur_quality=MapQualityMetrics(),
    superflip_edma_sigma=.5, deblur_edma_sigma=.5, run_id="render-fixture")

def stage(name, detail="running"):
    backend._operation_states = {"render-primary": (name,1,"running")}
    backend._apply_cycle_progress_state(engine.CycleProgressState(1,5,name,1,7,detail=detail,busy=True))

def capture(name, height=1000, width=1500):
    window.resize(width,height)
    window._refresh_tick()
    for _ in range(8):
        app.processEvents()
    window.structure_canvas.draw()
    from mpl_toolkits.mplot3d import proj3d
    import numpy as np
    import json
    fills = []
    for artist in window._structure_depth_artists:
        axis = artist.scatter.axes
        points = artist.atom_coordinates
        if window.view_mode == "cell":
            points = np.vstack((points,artist.cell_corners))
        x,y,_ = proj3d.proj_transform(*points.T,axis.get_proj())
        pixels = axis.transData.transform(np.column_stack((x,y)))
        viewport = axis.get_position(original=True).transformed(window.structure_figure.transFigure)
        fills.append(max(np.ptp(pixels[:,0])/viewport.width,np.ptp(pixels[:,1])/viewport.height))
    (out/(name+".json")).write_text(json.dumps({"logical_size":window.size().toTuple(),
        "device_pixel_ratio":window.devicePixelRatioF(),"projected_geometry_fill":fills},indent=2),encoding="utf8")
    if True:
        assert window.grab().save(str(out / (name + ".png")))
    print(name,"logical",window.size().toTuple(),"DPR",window.devicePixelRatioF(), flush=True)



from phase_studio import autosolve_review as guided
from phase_studio.error_reporting import ErrorReport, build_error_report, show_phase_studio_error
from PySide6.QtCore import QTimer
panels = {}
backend.autosolve_display_panel = lambda role: panels.get(role)
backend.autosolve_warning_text = lambda role: None
backend.autosolve_in_review = lambda: backend._autosolve_stage in guided.REVIEW_STAGES
backend.autosolve_review_busy = lambda: False
backend._autosolve_stage = guided.STAGE_SEARCH
stage('Superflip')
capture('01-phase-search')
backend._set_run_status('IDLE')
capture('02-not-started')
backend._set_run_status('RUNNING')
panels['observed'] = guided.ReviewPanel('observed',1,sfmap,dense,1.0)
backend.results = [result]
stage('SharpED')
capture('03-charge-flipping-ready')
backend._autosolve_stage = guided.STAGE_PREDICTING
capture('04-creating-prediction')
panels['predicted'] = guided.ReviewPanel('predicted',1,dbmap,elongated,1.0,'UNIVERSAL')
backend.autosolve_panels = panels
backend._autosolve_stage = guided.STAGE_REVIEW
backend._set_run_status('REVIEW')
backend._operation_states = {}
capture('05-completed-review')
backend._autosolve_stage = guided.STAGE_REFINEMENT
backend._set_run_status('RUNNING')
stage('Superflip')
capture('06-refinement')
backend._set_run_status('CANCELLED')
capture('07-cancelled')
backend._set_run_status('ERROR')
capture('08-failed-stage')
window.hide()
reports = [
 ('09-missing-universal', ErrorReport('sharped_model_missing','SharpED','Required SharpED model is unavailable','Autosolve requires UNIVERSAL, but it is not in the current live catalogue.','Check the catalogue again or return to your workflow.','Offline fixture; no inference')),
 ('10-network',build_error_report('SharpED connection refused',subsystem='SharpED')),
 ('11-authentication',build_error_report('SharpED HTTP error 401',subsystem='SharpED')),
 ('12-access-denied',build_error_report('SharpED HTTP error 403',subsystem='SharpED')),
]
for name,report in reports:
 def grab(name=name):
  dialog=app.activeModalWidget()
  assert dialog is not None
  assert dialog.grab().save(str(out/(name+'.png')))
  dialog.reject()
 QTimer.singleShot(80,grab)
 show_phase_studio_error(None,report,backend._error_actions(report))
backend.review_edma_executor.cancel_all()
window.close()
backend.close()
app.processEvents()
print('Offline Autosolve/error screenshots completed',flush=True)
