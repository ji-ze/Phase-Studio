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
from PySide6.QtWidgets import QApplication
from phase_studio import app as engine
if len(sys.argv) > 1 and sys.argv[1] == "before":
    # This file was unchanged by the preceding 2.0.3 tasks. Loading its recorded
    # pre-task version provides a genuine baseline without reverting the tree.
    import importlib.util
    spec = importlib.util.spec_from_file_location("phase_studio.autosolve_window", ROOT / "build/execution-before-source.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    AutosolveWindow = module.AutosolveWindow
else:
    from phase_studio.autosolve_window import AutosolveWindow
from phase_studio.ui_style import apply_phase_studio_style
from phase_studio.map_quality import MapQualityMetrics

work = ROOT / "build/execution-capture" / ("scale-" + os.environ.get("QT_SCALE_FACTOR","1"))
work.mkdir(parents=True, exist_ok=True)
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(work / "settings"))
engine.IterativeSuperflipPipelineQtGUI.load_settings = lambda self: None
engine.IterativeSuperflipPipelineQtGUI.save_settings = lambda self: None
engine.IterativeSuperflipPipelineQtGUI.refresh_sharped_models = lambda self: None
app = QApplication([])
apply_phase_studio_style(app)
backend = engine.IterativeSuperflipPipelineQtGUI()
backend.jana_wizard_context = engine.JanaWizardContext(launched_from_jana_wizard=True, launch_mode="phase_recycling")
backend.autosolve_is_jana = lambda: True
backend._active_run_id = "render-fixture"
backend.launch_mode = "autosolve"
backend._set_run_status("RUNNING")
backend.progress_bar.setRange(0,3)
backend.progress_bar.setValue(0)
backend._set_overall_progress_text("0 of 3 cycles completed")
window = AutosolveWindow(backend, "A", workflow_name="Superflip + SharpED")
window._refresh_timer.stop()
window._rotate_timer.stop()
window.auto_rotate_button.setChecked(False)
window.show()
out = ROOT / "build/execution-2.0.3" / (sys.argv[1] if len(sys.argv) > 1 else "after") / ("scale-" + os.environ.get("QT_SCALE_FACTOR", "1"))
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
    sharped_model="SEED (cyclic CF)", superflip_quality=MapQualityMetrics(), deblur_quality=MapQualityMetrics(),
    superflip_edma_sigma=.5, deblur_edma_sigma=.5)

def stage(name, detail="running"):
    backend._operation_states = {"render-primary": (name,1,"running")}
    backend._apply_cycle_progress_state(engine.CycleProgressState(1,3,name,1,7,detail=detail,busy=True))

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
    assert window.grab().save(str(out / (name + ".png")))
    print(name,"logical",window.size().toTuple(),"DPR",window.devicePixelRatioF(), flush=True)

capture("01-empty")
stage("Superflip")
capture("02-superflip-running")
backend.results = [result]
stage("SharpED", "processing")
# Make only the Charge-flipping candidate visible in the progressive fixture.
original = result.deblur_edma_cif
result.deblur_edma_cif = work / "not-yet-completed.cif"
capture("03-charge-flipping-ready")
result.deblur_edma_cif = original
capture("04-both-ready")
capture("05-elongated-fitted")
capture("06-dense-fitted")
window.full_cell_view_button.setChecked(True)
capture("07-full-cell")
window.molecule_view_button.setChecked(True)
capture("08-complete-molecules")
if not (len(sys.argv)>1 and sys.argv[1]=="before"):
    from unittest.mock import patch
    from PySide6.QtCore import QTimer
    from dataclasses import replace
    backend._operation_states = {"sf-fixture": ("Superflip",2,"running"), "sharped-fixture": ("SharpED",1,"running")}
    capture("11-concurrent-operations")
    backend._operation_states = {"sharped-fixture": ("SharpED",1,"running")}
    job = engine.StructureJobUpdate("render-fixture","superflip",1,sfmap,"",.4,"render-edma",1,"running")
    backend._structure_jobs[("superflip",1)] = job
    with patch.object(backend.review_edma_executor,"is_busy",return_value=True), \
         patch.object(backend.review_edma_executor,"requested_threshold",return_value=.4):
        capture("09-interactive-edma-pending")
    completed = work / "dense-threshold-040.cif"
    completed.write_bytes(dense.read_bytes()+b'C61 C .283333333 .166666667 .166666667\n')
    result.superflip_edma_cif = completed
    result.superflip_edma_sigma = .4
    backend._structure_jobs[("superflip",1)] = replace(job,status="complete",structure_path=completed)
    capture("10-interactive-edma-completed")
    # Ordinary running workflows now refuse early handoff explicitly.
    window._refresh_tick()
    assert not window.pass_now_button.isEnabled()
    window._on_pass_now()
    capture("13-early-handoff-disabled")
capture("14-reduced-height",height=760)
capture("laptop-1280x720",height=720,width=1280)
backend._set_run_status("COMPLETED")
from dataclasses import replace
backend.results = [result,replace(result,cycle=2),replace(result,cycle=3)]
backend._apply_cycle_progress_state(engine.CycleProgressState(3,3,"Finalizing cycle",7,7,detail="completed",complete=True))
backend.progress_bar.setValue(3)
backend._set_overall_progress_text("3 of 3 cycles completed")
capture("12-completed")
window.close()
