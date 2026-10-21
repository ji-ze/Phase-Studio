"""Actual execution widgets, projected fits and run-scoped job lifecycle guards."""
import os
from pathlib import Path
import sys
import tempfile
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np


class ExecutionRedesign(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        from phase_studio.ui_style import apply_phase_studio_style
        cls._owns_application = QApplication.instance() is None
        cls.qtapp = QApplication.instance() or QApplication([])
        apply_phase_studio_style(cls.qtapp)

    @classmethod
    def tearDownClass(cls):
        # Dispose the owned native application while Python is still alive.
        # Leaving the Matplotlib/modal-widget graph to interpreter finalization
        # can deadlock PySide6's native application destructor on Windows.
        if cls._owns_application:
            import shiboken6
            cls.qtapp.processEvents()
            shiboken6.delete(cls.qtapp)
            cls.qtapp = None

    def setUp(self):
        from phase_studio import app as engine
        from phase_studio.autosolve_window import AutosolveWindow
        self.engine = engine
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patches = [patch.object(engine.IterativeSuperflipPipelineQtGUI, method, lambda self: None)
                        for method in ("save_settings", "load_settings", "refresh_sharped_models")]
        for item in self.patches:
            item.start()
        self.backend = engine.IterativeSuperflipPipelineQtGUI()
        self.backend._active_run_id = "current-test-run"
        self.backend.jana_wizard_context = engine.JanaWizardContext(launched_from_jana_wizard=True, launch_mode="phase_recycling")
        self.backend.autosolve_is_jana = lambda: True
        self.window = AutosolveWindow(self.backend, "A", workflow_name="Superflip + SharpED")
        self.window._refresh_timer.stop()
        self.window._rotate_timer.stop()
        self.window.auto_rotate_button.setChecked(False)
        self.window.show()
        self.window.resize(1400, 950)
        self.settle()

    def tearDown(self):
        from PySide6.QtCore import QCoreApplication,QEvent
        self.window.close()
        self.backend.review_edma_executor.cancel_all()
        self.backend.close()
        self.window.deleteLater()
        self.backend.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        self.qtapp.processEvents()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def settle(self):
        for _ in range(8):
            self.qtapp.processEvents()
        self.window.structure_canvas.draw()

    def structures(self):
        from phase_studio.map_quality import MapQualityMetrics
        def cif(name, coordinates):
            path = self.root / name
            path.write_text("data_test\n_cell_length_a 60\n_cell_length_b 60\n_cell_length_c 60\n"
                "_cell_angle_alpha 90\n_cell_angle_beta 90\n_cell_angle_gamma 90\n_space_group_name_H-M_alt 'P 1'\n"
                "loop_\n_atom_site_label\n_atom_site_type_symbol\n_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\n"
                + "\n".join(f"C{i+1} C {x/60:.9f} {y/60:.9f} {z/60:.9f}" for i,(x,y,z) in enumerate(coordinates)), encoding="utf8")
            return path
        dense = cif("dense.cif", [(10+x*1.4,10+y*1.4,10+z*1.4) for x in range(5) for y in range(4) for z in range(3)])
        elongated = cif("elongated.cif", [(10+i*1.4,10+(i%2)*.3,10) for i in range(24)])
        maps = [self.root / name for name in ("sf.xplor", "db.xplor")]
        for path in maps:
            path.write_text("closed map identity fixture", encoding="utf8")
        result = self.engine.CycleResult(cycle=1, model_source="none", model_in=None, model_metric=None,
            superflip_map=maps[0],superflip_edma_cif=dense,superflip_metric=None,
            deblur_map=maps[1],deblur_edma_cif=elongated,deblur_metric=None,
            sharped_model="SEED (cyclic CF)",superflip_quality=MapQualityMetrics(),deblur_quality=MapQualityMetrics(),
            superflip_edma_sigma=.5,deblur_edma_sigma=.5,run_id="current-test-run")
        self.backend.results = [result]
        self.window._refresh_tick()
        self.settle()
        return result

    def test_run_log_placeholder_replaced_and_completed_cycle_event_owns_count(self):
        backend=self.backend
        backend.progress_bar.setRange(0,3)
        backend._overall_progress_floor=0
        backend._set_run_status('RUNNING')
        self.assertNotIn('Ready. Select an input',backend.log_text.toPlainText())
        self.assertIn('Workflow started',backend.log_text.toPlainText())
        backend._append_execution_log('Superflip map completed.',subsystem='Superflip')
        text=backend.log_text.toPlainText()
        self.window._refresh_tick()
        self.assertEqual(text,backend.log_text.toPlainText())
        backend._apply_cycle_progress_state(self.engine.CycleProgressState(1,3,'EDMA',3,7,busy=True))
        self.assertEqual(backend.progress_bar.value(),0)
        backend._apply_cycle_progress_state(self.engine.CycleProgressState(1,3,'Finalizing cycle',7,7,complete=True))
        self.assertEqual(backend.progress_bar.value(),1)

    def test_active_handoff_rejects_wrong_run_or_unsealed_jana_model(self):
        result=self.structures()
        self.backend._set_run_status('RUNNING')
        with patch.object(self.backend,'request_autosolve_pass_now') as request:
            self.window._on_pass_now()
            request.assert_not_called()  # visualization fixture has no Jana model
        result.run_id='another-run'
        self.window._refresh_tick()
        self.assertFalse(self.window.pass_now_button.isEnabled())

    def test_finalizing_headline_and_committed_cycle_precede_completion_log(self):
        b=self.backend;b._set_run_status('RUNNING')
        b._apply_cycle_progress_state(self.engine.CycleProgressState(3,3,'Finalizing cycle',7,7,
            detail='calculating metrics',busy=True))
        self.window._refresh_tick()
        self.assertIn('Cycle 3 of 3 · Finalizing',self.window.status_headline.text())
        state=SimpleNamespace(completed_cycles=2,cfg=SimpleNamespace(cycles=3),run_id='current-test-run')
        seen=[]
        with patch.object(b,'log',side_effect=lambda *args,**kw:seen.append(('log',state.completed_cycles))), \
             patch.object(b,'_queue_run_event',side_effect=lambda *args:seen.append(('event',state.completed_cycles))), \
             patch.object(b,'_emit_cycle_progress',side_effect=lambda *args,**kw:seen.append(('complete',state.completed_cycles))), \
             patch.object(b,'_emit_requested_workflow_stop',return_value=False):
            b._finalize_completed_cycle(state,3,['Finalizing cycle'])
        self.assertEqual(seen,[('event',3),('complete',3),('log',3)])

    def test_completed_panel_edma_controls_are_independent_and_explain_missing_resources(self):
        from phase_studio import autosolve_review as guided
        self.structures();b=self.backend;b._set_run_status('RUNNING')
        self.window._refresh_tick()
        observed=self.window.review_columns[guided.ROLE_OBSERVED]
        self.assertFalse(observed['add'].isEnabled())
        self.assertIn('execution context',observed['add'].toolTip())
        executable=self.root/'EDMA.exe';executable.write_bytes(b'UI fixture, never executed')
        b._resume_state=SimpleNamespace(run_id='current-test-run',cfg=SimpleNamespace(work_dir=self.root,edma_exe=str(executable)))
        with patch.object(b.review_edma_executor,'is_busy',side_effect=lambda key:key[1]=='superflip'), \
             patch.object(b.review_edma_executor,'requested_threshold',return_value=.4):
            self.window._refresh_tick()
            self.assertFalse(observed['add'].isEnabled())
            self.assertTrue(self.window.review_columns[guided.ROLE_PREDICTED]['add'].isEnabled())
            self.assertIn('recalculation',observed['add'].toolTip())

    def test_fullscreen_scientific_details_preserve_units(self):
        from phase_studio import autosolve_review as guided
        self.structures()
        data = self.window._panel_fullscreen_presentation(guided.ROLE_PREDICTED)
        self.assertIn('0.010–0.150 Å²', data['scientific_details'])
        self.assertNotIn('?', data['scientific_details'])
        self.assertNotIn('?', data['metadata'])

    def test_projected_fit_compact_elongated_dense_orientations(self):
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from mpl_toolkits.mplot3d import proj3d
        from phase_studio.structure_camera import fit_projected_structure
        figure = Figure(figsize=(12,4),dpi=100)
        canvas = FigureCanvasAgg(figure)
        axis = figure.add_subplot(projection="3d")
        for points in (
            np.asarray([(x,y,z) for x in (-1,1) for y in (-1,1) for z in (-1,1)], dtype=float),
            np.column_stack((np.arange(80),np.sin(np.arange(80))*.2,np.zeros(80))),
            np.random.default_rng(22).normal(size=(1200,3)),
        ):
            original = points.copy()
            for elev,azim in ((20,35),(60,110),(-15,-60)):
                axis.view_init(elev=elev,azim=azim)
                canvas.draw()
                self.assertTrue(fit_projected_structure(axis,points))
                canvas.draw()
                x,y,_ = proj3d.proj_transform(*points.T,axis.get_proj())
                pixels = axis.transData.transform(np.column_stack((x,y)))
                viewport = axis.get_position(original=True).transformed(figure.transFigure)
                fraction = max(np.ptp(pixels[:,0])/viewport.width,np.ptp(pixels[:,1])/viewport.height)
                self.assertAlmostEqual(fraction,.78,places=5)
                np.testing.assert_allclose((pixels.min(axis=0)+pixels.max(axis=0))/2,
                    [viewport.x0+viewport.width/2,viewport.y0+viewport.height/2],atol=1e-5)
            np.testing.assert_array_equal(points,original)

    def test_progressive_results_and_stable_geometry(self):
        self.assertFalse(self.window.pass_now_button.isEnabled())
        result = self.structures()
        dbpath = result.deblur_edma_cif
        result.deblur_edma_cif = self.root / "pending.cif"
        self.window._refresh_tick();self.settle()
        self.assertTrue(self.window.review_columns["observed"]["fullscreen"].isEnabled())
        self.assertFalse(self.window.review_columns["predicted"]["fullscreen"].isEnabled())
        result.deblur_edma_cif = dbpath
        self.window._refresh_tick();self.settle()
        self.assertEqual(len(self.window._structure_interactive_axes),2)
        self.assertTrue(self.window.pass_now_button.isEnabled())

    def test_camera_independent_and_survives_other_candidate_and_resize(self):
        from phase_studio import autosolve_review as guided
        from dataclasses import replace
        result = self.structures()
        first,second = self.window.structure_axes
        self.window._camera.active_axis = first
        second_limits = self.window._structure_axis_limits(second)
        self.window._camera_orientation_changed(54,80,first)
        self.window._camera._scroll(SimpleNamespace(inaxes=first,step=1))
        first_limits = self.window._structure_axis_limits(first)
        self.assertEqual(second_limits,self.window._structure_axis_limits(second))
        self.assertEqual(second.elev,20)
        self.window._cycle_combos[guided.ROLE_OBSERVED].setCurrentIndex(1)
        self.backend.results.append(replace(result,cycle=2))
        self.window._refresh_tick();self.settle()
        first,second = self.window.structure_axes
        self.assertEqual(first_limits,self.window._structure_axis_limits(first))
        self.assertEqual((first.elev,first.azim),(54,80))
        self.window.resize(1200,800);self.settle()
        self.assertEqual(first_limits,self.window._structure_axis_limits(first))
        untouched = self.window._structure_axis_limits(second)
        self.window._fit_panel(guided.ROLE_OBSERVED)
        self.assertEqual(untouched,self.window._structure_axis_limits(second))

    def test_representation_preserves_edma_count_composition_and_files(self):
        result = self.structures()
        before = {p:p.read_bytes() for p in (result.superflip_edma_cif,result.deblur_edma_cif)}
        expected = dict(self.window._panel_atom_counts)
        self.assertTrue(all(label.get_fontfamily()==["Segoe UI"] for label in self.window._panel_captions))
        formulas = [label.text() for label in self.window.formula_labels]
        self.window.full_cell_view_button.setChecked(True);self.settle()
        self.assertEqual(self.window._panel_atom_counts,expected)
        self.window.molecule_view_button.setChecked(True);self.settle()
        self.assertEqual(self.window._panel_atom_counts,expected)
        self.assertEqual([label.text() for label in self.window.formula_labels],formulas)
        self.window._fit_structure_view();self.settle()
        self.assertEqual(self.window._panel_atom_counts,expected)
        for path,contents in before.items():
            self.assertEqual(path.read_bytes(),contents)

    def test_operation_lifetimes_overlap_and_ignore_stale_run_and_resurrection(self):
        backend = self.backend
        backend._set_run_status("RUNNING")
        state = SimpleNamespace(run_id="current-test-run")
        def concurrent():
            backend._poll_queue()
            self.assertIn("Superflip", " ".join(backend.active_workflow_operations()))
            backend._run_display_operation(state,1,"SharpED",lambda: backend._poll_queue())
            self.assertIn("SharpED", " ".join(backend.active_workflow_operations()))
        backend._run_display_operation(state,1,"Superflip",concurrent)
        backend._poll_queue()
        self.assertEqual(backend.active_workflow_operations(),[])
        previous_progress=backend._cycle_progress_state
        backend._run_display_operation(SimpleNamespace(run_id="old-run"),9,"SharpED",
            lambda: backend._emit_cycle_progress(9,10,["SharpED"],"SharpED",busy=True))
        backend._poll_queue()
        self.assertIs(backend._cycle_progress_state,previous_progress)
        backend._queue_run_event("operation_state",("stale","Superflip",9,"running"),"old-run")
        backend._queue_run_event("operation_state",("out-of-order","SharpED",1,"finished"),state.run_id)
        backend._queue_run_event("operation_state",("out-of-order","SharpED",1,"running"),state.run_id)
        backend._poll_queue()
        self.assertEqual(backend.active_workflow_operations(),[])
        backend._set_run_status("CANCELLED")
        self.window._refresh_tick()
        self.assertIn("Cancelled",self.window.status_headline.text())
        self.assertEqual(backend.current_cycle_progress.maximum(),1)
        self.assertFalse(backend.superflip_repeat_group.isVisible())

    def test_ordinary_early_pass_is_refused_until_workflow_stops(self):
        result = self.structures()
        self._write_handoff_metadata_fixture(result)
        self.backend._set_run_status("RUNNING")
        self.window._refresh_tick()
        self.assertFalse(self.window.pass_now_button.isEnabled())
        self.assertIn('stop the workflow', self.window.pass_now_button.toolTip())
        with patch.object(self.backend, "request_autosolve_pass_now") as request:
            self.window._on_pass_now()
            request.assert_not_called()
        self.backend._set_run_status("COMPLETE")
        self.window._refresh_tick()
        self.assertTrue(self.window.pass_now_button.isEnabled())
        with patch.object(self.backend, "request_autosolve_pass_now") as request:
            self.window._on_pass_now()
            request.assert_called_once()

    def test_interactive_edma_pending_completion_and_exact_map_identity(self):
        import threading
        import time
        from phase_studio import autosolve_review as guided
        result = self.structures()
        original_map = result.superflip_map.read_bytes()
        original_model = result.superflip_edma_cif
        other_model = result.deblur_edma_cif
        gate = threading.Event()
        entered = threading.Event()
        self.backend._resume_state = SimpleNamespace(
            run_id="current-test-run",cfg=SimpleNamespace(work_dir=self.root))
        self.backend._set_run_status("RUNNING")
        calls = []
        def extract(state,input_map,output_dir,prefix,threshold,**kwargs):
            calls.append((input_map,threshold))
            entered.set()
            self.assertTrue(gate.wait(8))
            output_dir.mkdir(parents=True,exist_ok=True)
            path = output_dir / (prefix+"_edma.cif")
            path.write_bytes(original_model.read_bytes())
            return path
        with patch.object(self.backend,"_run_configured_edma_stage",extract), \
             patch.object(self.engine,"run_sharped_deblur",side_effect=AssertionError("must not run SharpED")), \
             patch.object(self.engine,"run_superflip_cycle",side_effect=AssertionError("must not run Superflip")):
            self.window._adjust_panel_threshold(guided.ROLE_OBSERVED,True)
            self.assertTrue(entered.wait(2))
            self.backend._poll_queue();self.window._refresh_tick();self.settle()
            self.assertTrue(self.window.edma_threshold_labels[0].text().startswith("EDMA 0.50"))
            self.assertIn("0.40",self.window.review_columns[guided.ROLE_OBSERVED]["status"].text())
            self.assertEqual(result.superflip_edma_cif,original_model)
            self.assertEqual(result.deblur_edma_cif,other_model)
            self.assertFalse(self.window.pass_now_button.isEnabled())
            gate.set()
            deadline = time.monotonic()+5
            while result.superflip_edma_sigma != .4 and time.monotonic()<deadline:
                self.backend._poll_queue();self.qtapp.processEvents();time.sleep(.01)
            self.window._refresh_tick();self.settle()
            self.assertEqual(calls,[(result.superflip_map,.4)])
            self.assertEqual(result.superflip_edma_sigma,.4)
            self.assertTrue(self.window.edma_threshold_labels[0].text().startswith("EDMA 0.40"))
            self.assertEqual(result.deblur_edma_cif,other_model)
            self.assertEqual(result.superflip_map.read_bytes(),original_map)
            self.assertFalse(self.window.pass_now_button.isEnabled())
            self.backend._set_run_status('STOPPED')
            self.window._refresh_tick()
            self.assertTrue(self.window.pass_now_button.isEnabled())

        # A failed next extraction must also end its job lifetime, preserve the
        # completed .40 candidate, and leave an actionable failure message.
        with patch.object(self.backend,"_run_configured_edma_stage",side_effect=OSError("synthetic EDMA failure")):
            self.window._adjust_panel_threshold(guided.ROLE_OBSERVED,True)
            deadline = time.monotonic()+5
            candidate = self.backend.autosolve_observed_candidates()[0]
            key = self.backend._review_candidate_key(candidate)
            while self.backend.review_edma_executor.is_busy(key) and time.monotonic()<deadline:
                self.backend._poll_queue();self.qtapp.processEvents();time.sleep(.01)
            self.backend._poll_queue();self.window._refresh_tick();self.settle()
            self.assertEqual(result.superflip_edma_sigma,.4)
            self.assertEqual(self.backend._structure_jobs[("superflip",1)].status,"failed")
            self.assertEqual(self.backend.active_workflow_operations(),[])
            self.assertIn("failed",self.window.review_columns[guided.ROLE_OBSERVED]["status"].text())
            self.assertTrue(self.window.pass_now_button.isEnabled())

    def test_invalid_review_output_preserves_completed_candidates(self):
        import time
        result = self.structures()
        self.backend._resume_state = SimpleNamespace(
            run_id="current-test-run", cfg=SimpleNamespace(work_dir=self.root, jana_inflip=self.root/'input.inflip'))
        for source in ('superflip', 'deblurred'):
            original = next(c for c in self.engine.result_candidates_from_results([result]) if c.source == source)
            for invalid in ('missing', 'empty', 'malformed', 'missing-m40'):
                outcomes = []
                def extract(state, input_map, output_dir, prefix, threshold, **kwargs):
                    output_dir.mkdir(parents=True, exist_ok=True)
                    path = output_dir / 'review_edma.cif'
                    if invalid == 'empty':
                        path.write_text('data_empty\n')
                    elif invalid == 'malformed':
                        path.write_text('not a CIF')
                    elif invalid == 'missing-m40':
                        path.write_bytes(Path(original.structure_path).read_bytes())
                    return path
                with patch.object(self.backend, '_run_configured_edma_stage', extract):
                    request = self.backend.request_result_candidate_retune(original, True,
                        lambda updated, report, request: outcomes.append((updated, report)))
                    deadline = time.monotonic()+5
                    while not outcomes and time.monotonic() < deadline:
                        self.backend._poll_queue(); self.qtapp.processEvents(); time.sleep(.01)
                self.assertTrue(outcomes, invalid)
                self.assertIsNone(outcomes[0][0])
                self.assertEqual(outcomes[0][1].subsystem, 'EDMA')
                current = next(c for c in self.engine.result_candidates_from_results([result]) if c.source == source)
                self.assertEqual(current, original)
                self.assertEqual(self.backend.review_edma_executor.requested_threshold(request.key, .5), .5)

    def test_finished_edma_job_cannot_be_resurrected_by_late_callback(self):
        from dataclasses import replace
        result = self.structures()
        self.backend._set_run_status("RUNNING")
        state = SimpleNamespace(run_id="current-test-run")
        request = self.backend._new_structure_job(state,"superflip",1,result.superflip_map,.5)
        self.backend._structure_job_status(request,"complete",result.superflip_edma_cif)
        self.backend._structure_job_status(request,"running")
        self.backend._poll_queue()
        self.assertEqual(self.backend._structure_jobs[("superflip",1)].status,"complete")
        self.assertEqual(self.backend.active_workflow_operations(),[])

    def test_runtime_geometry_at_three_scales(self):
        for scale in ("1","1.25","1.5"):
            env = dict(os.environ,QT_QPA_PLATFORM="offscreen",QT_SCALE_FACTOR=scale)
            child = subprocess.run([sys.executable,__file__,"--geometry"],env=env,
                                   text=True,capture_output=True,timeout=60)
            self.assertEqual(child.returncode,0,child.stdout+child.stderr)

    def test_completed_captions_distinguish_running_cycle_and_manual_selection(self):
        from phase_studio import autosolve_review as guided
        from dataclasses import replace
        result = self.structures()
        self.backend._set_run_status('RUNNING')
        self.backend._apply_cycle_progress_state(self.engine.CycleProgressState(3,3,'Superflip',1,7,busy=True))
        self.window._refresh_tick()
        self.assertTrue(any('Completed result' in text.get_text() and 'Cycle 3' in text.get_text()
                            for text in self.window._panel_captions))
        combo = self.window._cycle_combos[guided.ROLE_OBSERVED]
        combo.setCurrentIndex(combo.findData(1))
        self.backend.results.append(replace(result,cycle=2))
        self.window._refresh_tick()
        self.assertEqual(self.window._last_panels[guided.ROLE_OBSERVED].cycle,1)
        self.assertEqual(self.window._last_panels[guided.ROLE_PREDICTED].cycle,2)
        self.assertFalse(self.window.pass_now_button.isEnabled())

    def test_sharped_phases_are_actual_progress_and_unknown_duration(self):
        self.backend._set_run_status('RUNNING')
        self.backend._operation_states['request'] = ('SharpED',1,'running')
        for detail in ('uploading','processing','downloading'):
            self.backend._apply_cycle_progress_state(self.engine.CycleProgressState(1,3,'SharpED',2,7,detail=detail,busy=True))
            self.window._refresh_tick()
            self.assertIn(detail.split('ing')[0].lower(), ' '.join(self.backend.active_workflow_operations()).lower())
            self.assertEqual(self.backend.current_cycle_progress.maximum(),0)

    def test_independent_live_completion_is_browsable_before_cycle_recording(self):
        from phase_studio import autosolve_review as guided
        result = self.structures()
        self.backend.results.clear()
        self.backend._set_run_status('RUNNING')
        state = SimpleNamespace(run_id='current-test-run')
        job = self.backend._new_structure_job(state,'superflip',1,result.superflip_map,.5)
        self.backend._structure_job_status(job,'complete',result.superflip_edma_cif)
        self.backend._poll_queue()
        self.window._refresh_tick()
        combo = self.window._cycle_combos[guided.ROLE_OBSERVED]
        self.assertTrue(combo.isEnabled())
        self.assertGreater(combo.findData(1),0)
        combo.setCurrentIndex(combo.findData(1))
        newer = self.backend._new_structure_job(state,'superflip',2,result.superflip_map,.4)
        self.backend._structure_job_status(newer,'complete',result.superflip_edma_cif)
        self.backend._poll_queue()
        self.window._refresh_tick()
        self.assertEqual(self.window._last_panels[guided.ROLE_OBSERVED].cycle,1)
        combo.setCurrentIndex(0)
        self.assertEqual(self.window._last_panels[guided.ROLE_OBSERVED].cycle,2)
        self.backend._active_run_id = 'next-run'
        self.backend._live_structures.clear()
        self.backend._structure_jobs.clear()
        self.window._refresh_tick()
        self.assertEqual(combo.count(),1)
        self.assertIsNone(self.window._last_panels[guided.ROLE_OBSERVED])

    def _write_handoff_metadata_fixture(self,result):
        # File-backed UI eligibility fixture only. Actual m40 publication is
        # independently exercised by the real EDMA/Jana acceptance and goldens.
        for path in (result.superflip_edma_cif,result.deblur_edma_cif):
            count=len(self.engine.parse_cif_atoms(path))
            path.with_suffix('.m40').write_text(f'{count} 0 0 0\n# UI eligibility fixture; never published\n')

    def test_immediate_stop_freezes_animation_before_worker_acknowledgement(self):
        self.backend._set_run_status("RUNNING")
        self.backend._operation_states["live"]=("SharpED",1,"running")
        self.backend.current_cycle_progress.setRange(0,0)
        self.backend.request_immediate_stop()
        self.window._refresh_tick()
        self.assertEqual(self.backend.current_cycle_progress.maximum(),1)
        self.assertIn("Stopping",self.window.status_headline.text())
        self.assertFalse(self.backend.superflip_repeat_group.isVisible())


def geometry_probe():
    from PySide6.QtCore import QPoint, QRect
    from mpl_toolkits.mplot3d import proj3d
    ExecutionRedesign.setUpClass()
    test = ExecutionRedesign()
    test.setUp()
    try:
        window = test.window
        def box(widget):
            return QRect(widget.mapTo(window,QPoint()),widget.size())
        for completed in (False,True):
            if completed:
                test.structures()
            for width,height in ((1280,720),(1500,850),(1920,1080),(2560,1440)):
                window.resize(width,height)
                test.settle()
                assert window.size().toTuple()==(width,height),window.size().toTuple()
                assert box(window.cancel_button).bottom()<height
                assert box(test.backend.run_status_panel).bottom()<box(window.cancel_button).top()
                assert box(window.validation_note).bottom()<box(test.backend.log_text).top()
                columns=list(window.review_columns.values())
                assert abs(columns[0]["column"].width()-columns[1]["column"].width())<=1
                for column in columns:
                    assert box(column["actions"]).bottom()<box(window.validation_note).top()
                if completed:
                    for artist in window._structure_depth_artists:
                        axis=artist.scatter.axes
                        coords=artist.atom_coordinates
                        x,y,_=proj3d.proj_transform(*coords.T,axis.get_proj())
                        pixels=axis.transData.transform(np.column_stack((x,y)))
                        viewport=axis.get_position(original=True).transformed(window.structure_figure.transFigure)
                        fraction=max(np.ptp(pixels[:,0])/viewport.width,np.ptp(pixels[:,1])/viewport.height)
                        assert .70<=fraction<=.85,(width,height,fraction)
                        np.testing.assert_allclose(artist.scatter.get_clip_box().bounds,viewport.bounds)
        print("Geometry/scaled projection matrix passed",os.environ.get("QT_SCALE_FACTOR"))
    finally:
        test.tearDown()
        ExecutionRedesign.tearDownClass()


if __name__ == "__main__":
    if "--geometry" in sys.argv:
        geometry_probe()
    else:
        unittest.main()
