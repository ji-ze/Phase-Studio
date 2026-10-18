"""Regression tests for Phase Studio 2.0.0 Autosolve's orchestration glue:
the adaptive continue/extend/stop decision of the shared phase search, the
user-initiated measured-data corrections of 2.0.1's Review (Powder
repartitioning vs suspect-intensity correction), and the Result Selection
end point -- hooked into the existing "done" queue event via
IterativeSuperflipPipelineQtGUI's _autosolve_on_run_done() /
autosolve_request_correction() / _autosolve_handoff(). The guided
prediction/Review/refinement flow is covered by test_autosolve_guided.py.

The adaptive-cycle policy itself (AdaptiveCyclePolicy) is already covered by
tests/test_autosolve_policy.py, and the real _run_pipeline_cycles() cycle
mechanics (including Continue/Resume) by tests/test_workflow_states.py; this
file tests the glue between them: given a set of already-completed
CycleResults and a policy, does the orchestrator make the right call and
mutate the right state? continue_run() and perform_jana_handoff() are
stubbed/mocked here rather than actually re-exercised.

Plain Python test (no pytest dependency); run with
`python tests/test_autosolve_orchestration.py`.
"""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

results_log = []


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


def main():
    from PySide6.QtWidgets import QApplication
    from phase_studio.map_quality import MapQualityMetrics, ValidationProfile
    import phase_studio.app as appmod
    import test_jana_completion as tjc

    app = QApplication.instance() or QApplication([sys.argv[0]])

    appmod.IterativeSuperflipPipelineQtGUI.save_settings = lambda self: None
    appmod.IterativeSuperflipPipelineQtGUI.load_settings = lambda self: None

    tmp = Path(tempfile.mkdtemp())

    def model(name):
        path = tmp / name
        path.write_text(tjc.CIF, encoding="utf-8")
        # A ready Jana candidate requires its corresponding validated model.
        path.with_suffix(".m40").write_text(
            "    2    0    0    0\n"
            " 1.000000 0.000000 0.000000 0.000000 0.000000 0.000000\n"
            " 0.000000\n"
            " 0.000000 0.000000 0.000000 0.000000 0.000000 0.000000\n"
            " 0.000000 0.000000 0.000000 0.000000 0.000000 0.000000\n"
            "C1        1  1     1.000000 0.100000 0.100000 0.100000\n"
            "   1.0000   1.0000\n"
            "O1        2  1     1.000000 0.500000 0.400000 0.350000\n"
            "   1.0000   1.0000\n", encoding="utf-8")
        return path

    def map_file(name):
        path = tmp / name
        path.write_text("real existing map", encoding="utf-8")
        return path

    def make_cycle_result(cycle, superflip_score, deblur_score):
        sf_quality = MapQualityMetrics(
            reference_f05=superflip_score, reference_rmsd=0.40,
            reference_phase_agreement=0.70, amplitude_rf=0.25,
            amplitude_cc=0.75, r_free=0.32, cc_free=0.70,
            omit_map_correlation=0.65, triplet_c3=0.55,
            n_measured_reflections=100, n_work_reflections=95, n_free_reflections=5,
        )
        db_quality = MapQualityMetrics(
            reference_f05=deblur_score, reference_rmsd=0.30,
            reference_phase_agreement=0.80, amplitude_rf=0.20,
            amplitude_cc=0.82, r_free=0.27, cc_free=0.77,
            omit_map_correlation=0.72, triplet_c3=0.62,
            n_measured_reflections=100, n_work_reflections=95, n_free_reflections=5,
        )
        return appmod.CycleResult(
            cycle=cycle, model_source="superflip", model_in=None, model_metric=None,
            superflip_map=map_file(f"sf{cycle}.xplor"),
            superflip_edma_cif=model(f"sf{cycle}.cif"), superflip_metric=0.4,
            deblur_map=map_file(f"db{cycle}.xplor"),
            deblur_edma_cif=model(f"db{cycle}.cif"), deblur_metric=0.3,
            validation_profile=ValidationProfile.REFERENCE_AND_HOLDOUT.value,
            superflip_quality=sf_quality,
            deblur_quality=db_quality,
        )

    def make_window(option, cycles_done, extra_cfg=None):
        win = appmod.IterativeSuperflipPipelineQtGUI()
        # Model-catalog prefetch is outside this orchestration unit test. If
        # its deferred worker reports while processEvents() drives a handoff,
        # never allow the real modal error dialog to block the harness.
        win._show_error_report = lambda *_args, **_kwargs: None
        inflip = model("job.inflip")
        cfg = tjc.make_run_config(appmod, tmp, inflip)
        cfg.jana_inflip = inflip
        cfg.reference_cif = tmp / "no_such_reference.cif"
        cfg.run_sharped = True
        cfg.input_source_mode = "external"
        cfg.reflection_data_mode = appmod.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA
        if extra_cfg:
            for key, value in extra_cfg.items():
                setattr(cfg, key, value)
        win.last_run_config = cfg
        win.jana_wizard_context = appmod.JanaWizardContext(
            launched_from_jana_wizard=True, launch_mode="autosolve", autosolve_option=option,
        )
        win.current_validation_profile = ValidationProfile.REFERENCE_AND_HOLDOUT
        # Cycles 1..10 monotonically improve (best = the newest cycle);
        # cycles 11..15 (when present) hold flat at cycle 10's score, so the
        # policy sees no improvement in that second block.
        results = []
        for c in range(1, cycles_done + 1):
            score_cycle = min(c, 10)
            results.append(make_cycle_result(c, 0.50 + score_cycle * 0.01, 0.50 + score_cycle * 0.01))
        win.results = results
        win._resume_state = SimpleNamespace(completed_cycles=cycles_done, cfg=cfg)
        return win

    # =====================================================================
    # The initial search is a fixed five cycles, then prediction starts.
    # =====================================================================
    win = make_window("A", 5)
    win._autosolve_stage = "search"
    win._autosolve_policy = appmod.AdaptiveCyclePolicy(win.current_validation_profile, initial=5, block_size=3)
    continue_calls = []
    win.continue_run = lambda: continue_calls.append(True)
    initial_prediction_calls = []
    win._autosolve_begin_prediction = lambda: initial_prediction_calls.append(True)
    win._autosolve_on_run_done()
    check("Option A cycle 5: starts prediction after the fixed initial block", initial_prediction_calls == [True])
    check("Option A: initial search does not auto-extend", continue_calls == [])
    check("Option A: policy limit remains five cycles", win._autosolve_policy.state.current_cycle_limit == 5)

    # Second block (11-15) makes no further improvement -> the shared phase
    # search converged: 2.0.1 generates the Model prediction next (never
    # an automatic handoff, never an automatic Map Feedback stage).
    win2 = make_window("A", 5)
    win2._autosolve_stage = "search"
    win2._autosolve_policy = appmod.AdaptiveCyclePolicy(win2.current_validation_profile, initial=5, block_size=3)
    handoff_calls = []
    prediction_calls = []
    win2._autosolve_handoff = lambda source: handoff_calls.append(source)
    win2._autosolve_begin_prediction = lambda: prediction_calls.append(True)
    win2.continue_run = lambda: (_ for _ in ()).throw(AssertionError("must not extend again"))
    win2._autosolve_on_run_done()
    check("Option A cycle 5 generates the Model prediction without an automatic handoff",
          prediction_calls == [True] and handoff_calls == [])

    # =====================================================================
    # Autosolve's end point goes through the SAME Result Selection dialog
    # as every other Jana2020 handoff: the recommended cycle is preselected
    # on the goal's tab, the user may override it, and only the accepted
    # choice is passed to Jana2020 (never a direct perform_jana_handoff).
    # =====================================================================
    import time
    from PySide6.QtWidgets import QDialog

    def offered(dialog):
        return [c for view in dialog._views.values() for c in view.ordered]

    def drive_handoff(window, source, accept=True, override_cycle=None):
        opened = []
        handoff_args = {}

        def fake_exec(dialog):
            opened.append(dialog)
            if override_cycle is not None:
                view = dialog._views[source]
                view.selected = [c for c in view.ordered if c.cycle == override_cycle][0]
            return QDialog.Accepted if accept else QDialog.Rejected

        def fake_handoff(cfg, result, candidate, **kwargs):
            handoff_args.update(cfg=cfg, result=result, candidate=candidate)

        with patch.object(appmod.ResultSelectionDialog, "exec", fake_exec), \
             patch.object(appmod, "perform_jana_handoff", side_effect=fake_handoff):
            window._autosolve_handoff(source)
            check(f"handoff ({source}): nothing is passed before the user confirms in Result Selection",
                  not handoff_args)
            for _ in range(100):
                app.processEvents()
                if handoff_args or (opened and not accept) or window.autosolve_handoff_state == "declined":
                    break
                time.sleep(0.02)
        return opened, handoff_args

    win3 = make_window("A", 10)
    logged3 = []
    original_log3 = win3._append_execution_log
    win3._append_execution_log = lambda msg, **kw: (logged3.append(msg), original_log3(msg, **kw))
    opened3, handoff_args = drive_handoff(win3, "superflip")
    check("handoff: the shared ResultSelectionDialog was opened (exactly once)",
          len(opened3) == 1 and isinstance(opened3[0], appmod.ResultSelectionDialog))
    check("handoff: Option A opens on the Superflip tab with the recommended Cycle 10 preselected",
          bool(opened3) and opened3[0].selected_candidate is not None
          and opened3[0].selected_candidate.source == "superflip" and opened3[0].selected_candidate.cycle == 10)
    check("handoff: the accepted selection is what perform_jana_handoff receives (cycle 10, superflip)",
          handoff_args.get("result") is not None and handoff_args["result"].cycle == 10
          and handoff_args.get("candidate") is opened3[0].selected_candidate
          and handoff_args["candidate"].source == "superflip")
    check("handoff: state reports the selected-result handoff", win3.autosolve_handoff_state == "handing_off")
    check("handoff log: no 'with no further input' claim anywhere",
          not any("no further input" in str(m) for m in logged3))
    check("handoff log: names Result Selection and the recommended cycle",
          any("Result Selection" in str(m) and "Cycle 10" in str(m) for m in logged3))

    # User override: a different cycle chosen in Result Selection is what
    # Jana2020 receives -- the recommendation is only a preselection.
    win3b = make_window("A", 10)
    _opened, override_args = drive_handoff(win3b, "superflip", override_cycle=4)
    check("handoff: a user override in Result Selection wins (cycle 4 passed, not the recommended 10)",
          override_args.get("result") is not None and override_args["result"].cycle == 4)

    # Declined: closing Result Selection passes nothing and keeps results.
    win3c = make_window("A", 10)
    opened3c, declined_args = drive_handoff(win3c, "superflip", accept=False)
    check("handoff: closing Result Selection passes nothing to Jana2020",
          len(opened3c) == 1 and not declined_args and win3c.autosolve_handoff_state == "declined")
    check("handoff declined: completed results remain available", len(win3c.results) == 10)

    # Option B opens on the SharpED tab.
    win3d = make_window("B", 10)
    opened3d, b_args = drive_handoff(win3d, "deblurred")
    check("handoff: Option B opens on the SharpED tab and passes the accepted SharpED result",
          bool(opened3d) and opened3d[0].selected_candidate is not None
          and opened3d[0].selected_candidate.source == "deblurred"
          and b_args.get("candidate") is opened3d[0].selected_candidate)

    # No completed candidate at all: nothing opened, nothing passed.
    win3e = make_window("A", 10)
    win3e.results = []
    opened3e, empty_args = drive_handoff(win3e, "superflip")
    check("handoff with no completed result: no dialog, nothing passed, state declined",
          not opened3e and not empty_args and win3e.autosolve_handoff_state == "declined")

    # Early handoff: only COMPLETED cycles are offered. Cycles 1-5 are
    # recorded; an in-flight cycle 6 never enters win.results (only
    # _finalize_completed_cycle appends there), so the dialog gets 1-5.
    win3f = make_window("A", 5)
    opened3f, _early_args = drive_handoff(win3f, "superflip")
    offered_cycles = sorted({c.cycle for c in offered(opened3f[0])}) if opened3f else []
    check("early handoff: Result Selection offers only completed cycles (1-5)", offered_cycles == [1, 2, 3, 4, 5])
    completed_maps = {Path(r.superflip_map) for r in win3f.results} | {Path(r.deblur_map) for r in win3f.results}
    check("early handoff: every offered map is a recorded completed-cycle map (no preview/temp files)",
          bool(opened3f) and all(Path(c.map_path) in completed_maps for c in offered(opened3f[0])))

    # Pass to Jana2020 after the run has already ended (not RUNNING): no
    # stop request, straight into Result Selection.
    win3g = make_window("A", 5)
    win3g._run_status = "COMPLETED"
    selector_calls = []
    win3g._autosolve_handoff = lambda source: selector_calls.append(source)
    win3g.request_autosolve_pass_now()
    check("Pass to Jana2020 when no run is active: opens Result Selection directly, no stop request",
          selector_calls == ["superflip"] and not win3g.stop_now.is_set())

    # =====================================================================
    # Option B shares the SAME phase search (2.0.1): it stops on the
    # Observed-data (Superflip) stream exactly like Option A and generates the
    # Model prediction -- no automatic Map Feedback stage any more.
    # =====================================================================
    win4 = make_window("B", 8, extra_cfg={"reflection_data_mode": appmod.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA})
    win4._autosolve_stage = "search"
    win4._autosolve_policy = appmod.AdaptiveCyclePolicy(win4.current_validation_profile, initial=5, block_size=3)
    prediction_calls_b = []
    win4._autosolve_begin_prediction = lambda: prediction_calls_b.append(True)
    win4.continue_run = lambda: (_ for _ in ()).throw(AssertionError("the shared search must not auto-start Map Feedback"))
    win4._autosolve_on_run_done()
    check("Option B initial search stops like Option A and generates the Model prediction",
          prediction_calls_b == [True])
    check("Option B: measured data are NOT modified automatically",
          win4.last_run_config.map_feedback_intensity_enabled is False and win4.last_run_config.redistribute_overlaps is False)

    # Review: the existing weak-intensity correction runs only on request,
    # with the established configuration (non-FWHM data).
    win4._autosolve_stage = "review"
    plan_b, _detail = win4.autosolve_correction_plan()
    check("Review (non-FWHM): 'Correct suspect intensities' is the applicable correction", plan_b == "intensity")
    check("Review (non-FWHM): Powder repartitioning is not offered", plan_b != "powder")
    continue_calls_b = []
    win4.continue_run = lambda: continue_calls_b.append(True)
    check("Review: a correction that does not apply is refused", win4.autosolve_request_correction("powder") is False)
    check("Review: the applicable correction starts on request", win4.autosolve_request_correction("intensity") is True)
    check("Correction: weak-intensity correction is enabled", win4.last_run_config.map_feedback_intensity_enabled is True)
    check("Correction: weak-intensity starts at the next cycle", win4.last_run_config.map_feedback_intensity_from_cycle == 9)
    check("Correction: weak-intensity max I/sigma is 3.0", win4.last_run_config.map_feedback_intensity_max_i_over_sigma == 3.0)
    check("Correction: weak-intensity damping is 0.100 (not the XPLOR damping_factor)", win4.last_run_config.map_feedback_intensity_damping == 0.100)
    check("Correction: Powder repartitioning stays off for the non-FWHM branch", win4.last_run_config.redistribute_overlaps is False)
    check("Correction: a fresh three-cycle adaptive budget started (8 completed + 3 = 11)", win4._autosolve_policy.state.current_cycle_limit == 11)
    check("Correction: cycles widget bumped for the new stage", win4._spin_value("cycles") == 11)
    check("Correction: the phase search continues with 'UNIVERSAL'",
          win4.last_run_config.sharped_model == "UNIVERSAL" and win4._autosolve_stage == "map_feedback")
    check("Correction: continue_run() was called to start the corrected-data stage", len(continue_calls_b) == 1)

    # =====================================================================
    # Defensive: a "done" event that does not land on the policy's current
    # decision point must be a genuine no-op, never silently treated as
    # "stop" (this exact fallthrough was a real bug caught while writing
    # this test -- see _autosolve_on_run_done's "continue" branch).
    # =====================================================================
    win_offschedule = make_window("A", 7)
    win_offschedule._autosolve_stage = "refinement"
    win_offschedule._autosolve_policy = appmod.AdaptiveCyclePolicy(win_offschedule.current_validation_profile, initial=8, block_size=3)
    off_schedule_handoffs = []
    win_offschedule._autosolve_handoff = lambda source: off_schedule_handoffs.append(source)
    win_offschedule.continue_run = lambda: (_ for _ in ()).throw(AssertionError("must not extend off-schedule"))
    win_offschedule._autosolve_on_run_done()
    check("off-schedule 'done' (cyc=7, limit=8): does not hand off", off_schedule_handoffs == [])
    check("off-schedule 'done': the policy limit is unchanged", win_offschedule._autosolve_policy.state.current_cycle_limit == 8)

    # =====================================================================
    # Option B, FWHM data with a resolvable wavelength (via .inflip lambda
    # line) -> Powder repartitioning branch instead.
    # =====================================================================
    inflip_with_lambda = tmp / "with_lambda.inflip"
    inflip_with_lambda.write_text("title fixture\nlambda 1.54184\n", encoding="utf-8")

    win6 = make_window(
        "B", 8,
        extra_cfg={
            "reflection_data_mode": appmod.REFLECTION_DATA_MODE_AMPLITUDE_FWHM,
            "jana_inflip": inflip_with_lambda,
        },
    )
    win6._autosolve_stage = "review"
    win6.continue_run = lambda: None
    plan_6, detail_6 = win6.autosolve_correction_plan()
    check("Review (FWHM + wavelength): 'Powder repartitioning' is the applicable correction", plan_6 == "powder")
    check("Review (FWHM + wavelength): suspect-intensity correction is not offered", plan_6 != "intensity")
    check("Review (FWHM): powder repartitioning starts on request", win6.autosolve_request_correction("powder") is True)
    check("Correction (FWHM): Powder repartitioning is enabled", win6.last_run_config.redistribute_overlaps is True)
    check("Correction (FWHM): repartitioning starts at the next cycle", win6.last_run_config.powder_redistribution_from_cycle == 9)
    check("Correction (FWHM): wavelength resolved from the .inflip lambda line", abs(win6.last_run_config.powder_wavelength - 1.54184) < 1e-9)
    check("Correction (FWHM): separation factor is 0.200", win6.last_run_config.powder_separation_factor == 0.200)
    check("Correction (FWHM): map ratio mix is 0.3", win6.last_run_config.powder_redistribution_mix == 0.3)
    check("Correction (FWHM): weak-intensity correction stays off", win6.last_run_config.map_feedback_intensity_enabled is False)

    # =====================================================================
    # FWHM data but NO resolvable wavelength anywhere -> neither correction
    # is offered (no permanently disabled control), a specific remediation
    # message is logged, and nothing is modified silently.
    # =====================================================================
    inflip_no_lambda = tmp / "no_lambda.inflip"
    inflip_no_lambda.write_text("title fixture\n", encoding="utf-8")
    win7 = make_window(
        "B", 8,
        extra_cfg={
            "reflection_data_mode": appmod.REFLECTION_DATA_MODE_AMPLITUDE_FWHM,
            "jana_inflip": inflip_no_lambda,
        },
    )
    win7.continue_run = lambda: (_ for _ in ()).throw(AssertionError("must not start a Map Feedback stage without a wavelength"))
    logged = []
    win7._append_execution_log = lambda msg, **kw: logged.append(msg)
    win7._autosolve_enter_review()
    plan_7, _detail_7 = win7.autosolve_correction_plan()
    check("FWHM without wavelength: no correction applies (neither button is shown)", plan_7 is None)
    check("FWHM without wavelength: requesting either correction is refused",
          win7.autosolve_request_correction("powder") is False and win7.autosolve_request_correction("intensity") is False)
    check("FWHM without wavelength: never a silent fallback to weak-intensity correction",
          win7.last_run_config.map_feedback_intensity_enabled is False and win7.last_run_config.redistribute_overlaps is False)
    check("FWHM without wavelength: a specific remediation message is logged",
          any("wavelength" in str(msg).lower() for msg in logged))
    check("FWHM without wavelength: the workflow waits in Review (no hang, no handoff)", win7._autosolve_stage == "review")

    # =====================================================================
    # "Pass to Jana2020 now" (revised semantics): stop the active work
    # IMMEDIATELY (the same mechanism Cancel uses -- never waits for the
    # in-flight cycle), then hand off the best ALREADY COMPLETED candidate.
    # An in-flight cycle is never in win.results (only _finalize_completed_
    # cycle() ever appends to it), so it is automatically excluded with no
    # extra filtering logic -- these tests simulate that by simply never
    # adding a "cycle 4" result to win.results.
    # =====================================================================
    win8 = make_window("A", 5)
    win8._run_status = "RUNNING"
    check("request_autosolve_pass_now(): sets the pass-now flag", not win8._autosolve_pass_now_requested)
    win8.request_autosolve_pass_now()
    check("request_autosolve_pass_now(): flag is now set", win8._autosolve_pass_now_requested)
    check("early Pass freezes a completed canonical candidate snapshot before stopping",
          win8._handoff_pending and len(win8._handoff_candidate_snapshot or []) == len(win8._result_candidates()))
    check("request_autosolve_pass_now(): uses the immediate-stop mechanism, not a graceful stop", win8.stop_now.is_set())
    check("request_autosolve_pass_now(): stop_after_cycle is also set (immediate implies graceful)", win8.stop_after_cycle.is_set())

    handoff_calls_8 = []
    win8._autosolve_handoff = lambda source: handoff_calls_8.append(source)
    win8.msg_queue.put(("cancelled", None))
    win8._poll_queue()
    check("Pass to Jana2020 (running): the resulting 'cancelled' event opens the handoff for the goal source", handoff_calls_8 == ["superflip"])
    check("Pass to Jana2020 (running): the flag is cleared after handoff", not win8._autosolve_pass_now_requested)

    # A plain Cancel (no Pass-to-Jana2020-now request) must NOT trigger an
    # automatic handoff -- only Cancel combined with the explicit pass-now
    # flag does.
    win9 = make_window("A", 5)
    handoff_calls_9 = []
    win9._autosolve_handoff = lambda source: handoff_calls_9.append(source)
    win9.msg_queue.put(("cancelled", None))
    win9._poll_queue()
    check("a plain Cancel (no Pass-to-Jana2020-now) does not auto-hand-off", handoff_calls_9 == [])

    # Existing non-Autosolve launch modes are unaffected: the flag is never
    # set for them, so this new branch never fires either.
    win10 = make_window("A", 5)
    win10.jana_wizard_context.launch_mode = "phase_recycling"
    handoff_calls_10 = []
    win10._autosolve_handoff = lambda source: handoff_calls_10.append(source)
    win10.msg_queue.put(("cancelled", None))
    win10._poll_queue()
    check("phase_recycling's own Cancel is completely unaffected", handoff_calls_10 == [])

    # Race: Pass to Jana2020 pressed after the worker already queued its
    # graceful "stopped" / final "done" event. The explicit handoff intent
    # wins, using its own STOPPED-for-handoff presentation rather than
    # misreporting the user's action as an ordinary cancellation.
    for late_event, payload in (("stopped", 5), ("done", None)):
        win_race = make_window("A", 5)
        win_race._run_status = "RUNNING"
        race_calls = []
        win_race._autosolve_handoff = lambda source, calls=race_calls: calls.append(source)
        win_race.request_autosolve_pass_now()
        win_race.msg_queue.put((late_event, payload))
        win_race._poll_queue()
        check(f"race ('{late_event}' already queued): the run ends in the distinct handoff stop state",
              str(win_race._run_status).upper() == "STOPPED"
              and "cancelled by the user" not in win_race.log_text.toPlainText().lower())
        check(f"race ('{late_event}' already queued): the Pass to Jana2020 request still opens Result Selection",
              race_calls == ["superflip"] and not win_race._autosolve_pass_now_requested)

    # From here on Result Selection is accepted with its preselection
    # unchanged (the recommended cycle of the goal's source), so the
    # handed-off result below is the one the user would confirm.
    accept_selection = patch.object(appmod.ResultSelectionDialog, "exec", lambda dialog: QDialog.Accepted)
    accept_selection.start()
    # =====================================================================
    # Item 31.A: cycles 1-3 complete, cycle 4 currently running Superflip
    # (never added to win.results, since it never finished) -- Pass-now
    # must cancel cycle 4, ignore it, and hand off the best of cycles 1-3.
    # =====================================================================
    with patch.object(appmod, "perform_jana_handoff") as fake_handoff_a:
        win_a = make_window("A", 3)  # cycle 4 deliberately absent: still "running"
        win_a._run_status = "RUNNING"
        win_a.request_autosolve_pass_now()
        check("31.A: Pass-now on a running cycle uses immediate-stop", win_a.stop_now.is_set())
        win_a.msg_queue.put(("cancelled", None))
        win_a._poll_queue()
        app.processEvents()
        import time as _time
        for _ in range(50):
            if fake_handoff_a.called:
                break
            _time.sleep(0.02)
            app.processEvents()
        check("31.A: cycle 4 is never handed off (it was never completed)", fake_handoff_a.called)
        handed_result = fake_handoff_a.call_args[0][1] if fake_handoff_a.called else None
        check("31.A: the candidate set remains cycles 1-3 (best = cycle 3)", handed_result is not None and handed_result.cycle == 3)

    # =====================================================================
    # Item 31.B: cycle 4 is mid-SharpED (polling) rather than mid-Superflip
    # -- from the GUI's own perspective this is identical to 31.A, since
    # exclusion is based purely on win.results membership (only a fully
    # finished cycle is ever appended there), not on which sub-stage was
    # interrupted. Same fixture, same expectation.
    # =====================================================================
    with patch.object(appmod, "perform_jana_handoff") as fake_handoff_b:
        win_b = make_window("B", 3)  # cycle 4 "mid-SharpED-polling": absent from results
        win_b._run_status = "RUNNING"
        win_b.request_autosolve_pass_now()
        win_b.msg_queue.put(("cancelled", None))
        win_b._poll_queue()
        app.processEvents()
        for _ in range(50):
            if fake_handoff_b.called:
                break
            _time.sleep(0.02)
            app.processEvents()
        check("31.B: polling is cancelled, no cycle-4 SharpED candidate is used", fake_handoff_b.called)
        handed_result_b = fake_handoff_b.call_args[0][1] if fake_handoff_b.called else None
        candidate_arg_b = fake_handoff_b.call_args[0][2] if fake_handoff_b.called else None
        check("31.B: the best completed (cycle 3) SharpED result is handed off", handed_result_b is not None and handed_result_b.cycle == 3)
        check("31.B: source is deblurred (SharpED), Option B",
              candidate_arg_b is not None and candidate_arg_b.source == "deblurred")

    # =====================================================================
    # Item 31.C: zero completed cycles -- no handoff, a clear message, and
    # the calculation state stays safe (no fabricated candidate).
    # =====================================================================
    with patch.object(appmod, "perform_jana_handoff") as fake_handoff_c:
        win_c = make_window("A", 0)
        win_c._run_status = "RUNNING"
        logged_c = []
        win_c._append_execution_log = lambda msg, **kw: logged_c.append(getattr(msg, "text", msg))
        win_c.request_autosolve_pass_now()
        check("31.C: zero completed cycles do not trigger the handoff stop path",
              not win_c.stop_now.is_set() and not win_c._handoff_pending
              and not win_c._autosolve_pass_now_requested)
        win_c.msg_queue.put(("cancelled", None))
        win_c._poll_queue()
        app.processEvents()
        check("31.C: no handoff is attempted with zero completed cycles", not fake_handoff_c.called)
        check(
            "31.C: a clear, concise message is logged",
            any("no completed result" in msg.lower() for msg in logged_c),
        )

    # =====================================================================
    # Item 31.D/E: Option A targets the best completed Superflip candidate;
    # Option B targets the best completed SharpED candidate -- the existing
    # source-specific recommendation logic, never Superflip-vs-SharpED.
    # =====================================================================
    with patch.object(appmod, "perform_jana_handoff") as fake_handoff_d:
        win_d = make_window("A", 4)
        win_d._run_status = "RUNNING"
        win_d.request_autosolve_pass_now()
        win_d.msg_queue.put(("cancelled", None))
        win_d._poll_queue()
        app.processEvents()
        for _ in range(50):
            if fake_handoff_d.called:
                break
            _time.sleep(0.02)
            app.processEvents()
        candidate_arg_d = fake_handoff_d.call_args[0][2] if fake_handoff_d.called else None
        check("31.D: Option A hands off the best completed Superflip candidate",
              candidate_arg_d is not None and candidate_arg_d.source == "superflip")

    with patch.object(appmod, "perform_jana_handoff") as fake_handoff_e:
        win_e = make_window("B", 4)
        win_e._run_status = "RUNNING"
        win_e.request_autosolve_pass_now()
        win_e.msg_queue.put(("cancelled", None))
        win_e._poll_queue()
        app.processEvents()
        for _ in range(50):
            if fake_handoff_e.called:
                break
            _time.sleep(0.02)
            app.processEvents()
        candidate_arg_e = fake_handoff_e.call_args[0][2] if fake_handoff_e.called else None
        check("31.E: Option B hands off the best completed SharpED candidate",
              candidate_arg_e is not None and candidate_arg_e.source == "deblurred")
    accept_selection.stop()

    failures = [name for name, ok in results_log if not ok]
    print()
    if failures:
        print(f"{len(failures)} of {len(results_log)} checks FAILED:")
        for failure in failures:
            print("  - " + failure)
        return 1
    print(f"All {len(results_log)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
