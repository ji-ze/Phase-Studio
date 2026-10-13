"""Regression tests for Phase Studio's workflow terminal states.

Plain Python test (no pytest dependency; run with
`python tests/test_workflow_states.py`), following this project's usual
checks-list-plus-exit-code convention.

Real Jana2020 testing showed "Stop after current cycle" reported as
CANCELLED, with the log saying the workflow had been cancelled by the user.
That is wrong and it matters scientifically: a graceful stop lets the current
cycle finish normally, so its results are valid and still usable for the
Jana2020 hand-off. An immediate interruption is a different state entirely.

The four user-facing terminal states are now distinct:

    COMPLETE   all requested work finished normally
    STOPPED    "Stop after current cycle" -- current cycle completed, results valid
    CANCELLED  immediate interruption ("Stop immediately")
    FAILED     terminated by an error (stored internally as ERROR)
"""
import dataclasses
import os
import queue
import sys
import tempfile
import threading
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

results_log = []


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


def main():
    from PySide6.QtWidgets import QApplication, QDialog

    app = QApplication.instance() or QApplication([sys.argv[0]])
    import phase_studio.ui_style as ui_style

    ui_style.apply_phase_studio_style(app)
    import phase_studio.app as appmod
    import test_jana_completion as tjc

    QDialog.exec = lambda self: QDialog.Rejected

    def running_window(mode="phase_recycling"):
        win, cycle_results = tjc.build_window(appmod, "deblurred", mode)
        win.results = []
        win._set_run_status("Running")
        win._jana_auto_selector_shown = False
        return win, cycle_results

    def ordinary_cycle_state(win, cycles=2):
        """Small deterministic state for exercising the real cycle gate."""
        import gemmi

        temp = Path(tempfile.mkdtemp())
        inflip = temp / "job.inflip"
        inflip.write_text("title stop-race fixture\n", encoding="utf-8")
        cfg = tjc.make_run_config(appmod, temp, inflip)
        cfg.cycles = cycles
        cfg.reconstruction_mode = "superflip"
        cfg.referencefile_mode = "omit"
        cfg.modelfile_source = "none"
        cfg.map_export_format = "xplor"
        cfg.structure_export_format = "cif"
        cfg.reflection_data_mode = appmod.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA
        cfg.run_sharped = False
        cfg.run_edma_superflip = False
        cfg.run_edma_deblurred = False
        cfg.symmetrize_deblurred_map = False
        observed = temp / "observed.hkl"
        observed.write_text("1 0 0 10 1\n", encoding="utf-8")
        ref_ctx = appmod.ReferenceContext(
            cif_path=temp / "reference.cif",
            work_ref_cif=temp / "reference.cif",
            cell=gemmi.UnitCell(10, 10, 10, 90, 90, 90),
            spacegroup=gemmi.SpaceGroup("P 1"),
            spacegroup_hm="P 1",
            composition="C 1",
            atoms=[],
        )
        return appmod.PipelineState(
            cfg=cfg,
            ref_ctx=ref_ctx,
            observed_hkls={cfg.reflection_data_mode: observed},
            configured_data_mode=cfg.reflection_data_mode,
            referencefile_mode="omit",
            explicit_superflip_referencefile=None,
            modelfile_mode="none",
            use_xplor_modelfile=False,
            use_cif_modelfile=False,
            use_superflip_xplor_modelfile=False,
            sharped_elements="C",
            exclude_labels=[],
            progress_stages=appmod.cycle_progress_stages(cfg),
            current_reflections=[appmod.Reflection(1, 0, 0, 10.0, 1.0)],
        )

    def drain_events(win):
        events = []
        while True:
            try:
                events.append(win.msg_queue.get_nowait())
            except queue.Empty:
                return events

    # A completed EDMA structure is a GUI-ready artifact before its cycle is
    # finalized. Identity and hashes prevent stale callbacks from replacing it.
    live_win, live_results = running_window()
    first = live_results[0]
    live_win._active_run_id = str(first.run_id)
    map_path = Path(first.superflip_map)
    cif_path = Path(first.superflip_edma_cif)
    live_job = appmod.StructureJobUpdate(
        run_id=str(first.run_id), source="superflip", cycle=1,
        map_path=map_path, map_sha256=appmod.file_sha256(map_path), threshold=1.0,
        request_id="automatic:superflip:1:1", generation=1, status="running",
    )
    complete = live_win._structure_job_status(live_job, "complete", cif_path)
    live_win._poll_queue()
    check("EDMA completion publishes its structure before any CycleResult is recorded",
          not live_win.results and live_win._live_structures.get("superflip") == complete
          and live_win._structure_source_paths["superflip"] == cif_path)
    check("live EDMA publication includes the same structure's ASU composition",
          complete.edma_asu_composition == appmod.edma_asu_composition_from_cif(cif_path)
          and bool(complete.edma_asu_composition))
    pending = appmod.StructureJobUpdate(
        run_id=str(first.run_id), source="superflip", cycle=2,
        map_path=map_path, map_sha256=appmod.file_sha256(map_path), threshold=1.0,
        request_id="automatic:superflip:2:2", generation=2, status="running",
    )
    live_win.msg_queue.put(("structure_state", pending))
    live_win._poll_queue()
    check("a newer running EDMA job keeps the latest completed structure visible",
          live_win._live_structures.get("superflip") == complete
          and live_win._structure_source_paths["superflip"] == cif_path)
    stale = appmod.StructureJobUpdate(
        run_id=str(first.run_id), source="superflip", cycle=2,
        map_path=map_path, map_sha256="stale-map-hash", threshold=0.8,
        request_id="stale", generation=1, status="complete",
        structure_path=cif_path, structure_sha256=appmod.file_sha256(cif_path),
    )
    live_win.msg_queue.put(("structure_state", stale))
    live_win._poll_queue()
    check("stale generation/map identity cannot replace a live structure",
          live_win._live_structures.get("superflip") == complete)

    # =====================================================================
    # COMPLETE
    # =====================================================================
    win, cycle_results = running_window()
    for result in cycle_results:
        win.msg_queue.put(("result", result))
    win.msg_queue.put(("done", len(cycle_results)))
    win._poll_queue()
    check("normal completion reports COMPLETE", win._run_status == "COMPLETE")
    check("normal completion badge reads COMPLETE", win.status_badge.text() == "COMPLETE")

    # =====================================================================
    # STOPPED -- graceful stop after a completed cycle
    # =====================================================================
    win, cycle_results = running_window()
    for result in cycle_results[:2]:
        win.msg_queue.put(("result", result))
    win.msg_queue.put(("stopped", 2))
    win._poll_queue()
    log_text = win.log_text.toPlainText()

    check("graceful stop reports STOPPED", win._run_status == "STOPPED")
    check("graceful stop badge reads STOPPED", win.status_badge.text() == "STOPPED")
    check(
        "graceful stop badge has its own style state",
        win.status_badge.property("runState") == "stopped",
    )
    check(
        "graceful stop says the workflow stopped as requested",
        "Workflow stopped after cycle 2 as requested." in log_text,
    )
    check(
        "graceful stop says completed results are available",
        "Completed results are available." in log_text,
    )
    check(
        "graceful stop never calls itself a cancellation",
        "cancel" not in log_text.lower(),
    )
    check("graceful stop keeps every completed result", len(win.results) == 2)
    check(
        "graceful stop leaves the run status text distinct from a cancellation",
        "Stopped" in win.current_cycle_detail.text() or win._run_status == "STOPPED",
    )
    # Section 14: a partial workflow is still a usable result set.
    check(
        "graceful stop keeps the Jana2020 hand-off available",
        win.jana_action_btn.isEnabled(),
    )
    check(
        "graceful stop keeps the Jana2020 action labelled Pass to Jana2020",
        win.jana_action_btn.text() == "Pass to Jana2020",
    )
    graceful_opened = []
    QDialog.exec = lambda self: (graceful_opened.append(self.windowTitle()), QDialog.Rejected)[1]
    win._on_jana_action_clicked()
    check(
        "graceful stop: the result selector still opens for the completed cycles",
        graceful_opened == ["Jana2020 result selection"],
    )
    QDialog.exec = lambda self: QDialog.Rejected
    check(
        "graceful stop does not require the configured cycle count to finish",
        len(win.results) < int(win.last_run_config.cycles),
    )

    # Early Pass is a distinct terminal intent: freeze Cycle 1, stop the
    # unfinished next cycle, then open Result Selection automatically.
    win, cycle_results = running_window("full_configuration")
    win.msg_queue.put(("result", cycle_results[0]))
    win._poll_queue()
    check("early Pass becomes enabled after the first canonical completed result",
          win.jana_action_btn.isEnabled())
    early_opened = []
    win.open_result_selector = lambda *args, **kwargs: (early_opened.append((args, kwargs)), True)[1]
    win._on_jana_action_clicked()
    check("early Pass marks handoff pending and freezes only completed candidates",
          win._handoff_pending and len(win._handoff_candidate_snapshot or []) == 2)
    check("early Pass safely requests immediate termination of unfinished work",
          win.stop_now.is_set() and win.stop_after_cycle.is_set())
    win.msg_queue.put(("cancelled", 1))
    win.msg_queue.put(("done", 1))  # defensive duplicate terminal event must be ignored
    win._poll_queue()
    for _ in range(5):
        app.processEvents()
    early_log = win.log_text.toPlainText()
    check("early Pass automatically opens Result Selection on the GUI thread",
          len(early_opened) == 1 and early_opened[0][0] == ("jana",))
    check("early Pass remains one-shot when duplicate terminal events are queued",
          len(early_opened) == 1)
    check("early Pass uses a distinct STOPPED handoff terminal presentation",
          win._run_status == "STOPPED" and "Workflow cancelled by the user." not in early_log)
    check("early Pass preserves the completed result registry", len(win.results) == 1)
    check("early Pass clears pending only after Result Selection has launched", not win._handoff_pending)
    QDialog.exec = lambda self: QDialog.Rejected

    # =====================================================================
    # CANCELLED -- immediate interruption
    # =====================================================================
    win, cycle_results = running_window()
    win.msg_queue.put(("result", cycle_results[0]))
    win.msg_queue.put(("cancelled", 1))
    win._poll_queue()
    log_text = win.log_text.toPlainText()
    check("immediate stop reports CANCELLED", win._run_status == "CANCELLED")
    check("immediate stop badge reads CANCELLED", win.status_badge.text() == "CANCELLED")
    check(
        "immediate stop says the workflow was cancelled by the user",
        "Workflow cancelled by the user." in log_text,
    )
    check(
        "immediate stop is never reported as STOPPED",
        "stopped after cycle" not in log_text.lower(),
    )

    # =====================================================================
    # FAILED
    # =====================================================================
    win, cycle_results = running_window()
    win._show_error_report = lambda report, **kwargs: None
    report = appmod.build_error_report(
        RuntimeError("synthetic failure"), subsystem="Pipeline", operation="Run workflow"
    )
    win.msg_queue.put(("error_report", report))
    win._poll_queue()
    check(
        "an execution error reports a failed state",
        win._run_status in {"ERROR", "FAILED"},
    )
    check(
        "a failure is not reported as STOPPED or COMPLETE",
        win._run_status not in {"STOPPED", "COMPLETE"},
    )

    # =====================================================================
    # Status normalization
    # =====================================================================
    win, _cycle_results = running_window()
    for supplied, expected in (
        ("Stopped", "STOPPED"),
        ("STOPPED", "STOPPED"),
        ("Cancelled", "CANCELLED"),
        ("Complete", "COMPLETE"),
        ("Failed", "ERROR"),
    ):
        win._set_run_status(supplied)
        check(
            "run status %r normalizes to %s" % (supplied, expected),
            win._run_status == expected,
        )
    check(
        "a graceful stop is never folded into CANCELLED",
        (win._set_run_status("Stopped"), win._run_status)[1] != "CANCELLED",
    )

    # Deterministic reproduction of the terminal-state race. The immediate
    # request arrives after scientific stages and result construction, inside
    # the short report-finalization section and before the shared stop gate.
    # No sleeps are involved: the report hook is the exact synchronization
    # checkpoint.
    win, _cycle_results = running_window()
    state = ordinary_cycle_state(win)
    started_cycles = []

    def fake_superflip(cycle_dir, prefix, *_args, **_kwargs):
        started_cycles.append(prefix)
        output = cycle_dir / (prefix + ".xplor")
        output.write_text("deterministic map\n", encoding="utf-8")
        return output

    def fake_structure(path, *_args, **_kwargs):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(tjc.CIF, encoding="utf-8")

    report_checkpoint_reached = []

    def cancel_during_report(_path, _results):
        report_checkpoint_reached.append(True)
        win.request_immediate_stop()

    with patch.object(appmod, "run_superflip_cycle", side_effect=fake_superflip), \
         patch.object(appmod, "export_phased_reflections_from_map"), \
         patch.object(appmod, "parse_superflip_cycle_metrics", return_value=appmod.SuperflipLogMetrics()), \
         patch.object(appmod, "write_structure_bundle", side_effect=fake_structure), \
         patch.object(appmod, "write_metrics_csv", side_effect=cancel_during_report), \
         patch.object(appmod, "write_map_quality_report"):
        win._run_pipeline_cycles(state)

    race_events = drain_events(win)
    terminal_events = [kind for kind, _payload in race_events if kind in {"done", "stopped", "cancelled", "error_report"}]
    check("immediate-stop race reaches the deterministic report checkpoint", report_checkpoint_reached == [True])
    check("immediate stop during report finalization has cancellation priority", terminal_events == ["cancelled"])
    check("immediate stop prevents the next scientific cycle", started_cycles == ["cycle_001_superflip"])
    check("report-finalization cancellation records one valid cycle result", len(state.all_results) == 1)
    check(
        "report-finalization cancellation publishes that valid result exactly once",
        sum(kind == "result" for kind, _payload in race_events) == 1,
    )

    # Both request orders resolve through the same priority policy. This pins
    # the case where a graceful request is upgraded before terminalization as
    # well as the case where a later graceful check sees an existing immediate
    # request.
    for label, request_order in (
        ("graceful then immediate", ("graceful", "immediate")),
        ("immediate then graceful", ("immediate", "graceful")),
    ):
        win, _cycle_results = running_window()
        drain_events(win)
        for request in request_order:
            if request == "immediate":
                win.request_immediate_stop()
            else:
                win.request_stop_after_cycle()
        emitted = win._emit_requested_workflow_stop(1)
        priority_events = [kind for kind, _payload in drain_events(win) if kind in {"stopped", "cancelled"}]
        check(label + " emits a terminal request", emitted)
        check(label + " resolves to CANCELLED", priority_events == ["cancelled"])

    win, _cycle_results = running_window()
    drain_events(win)
    check("no stop request does not emit a terminal event", not win._emit_requested_workflow_stop(0))
    check("no stop request leaves the terminal queue empty", drain_events(win) == [])

    # A queued graceful/complete terminal event is not authoritative until the
    # GUI consumes it. The button is still active in that interval, so a later
    # immediate request must upgrade either event to CANCELLED.
    for queued_kind in ("stopped", "done"):
        win, _cycle_results = running_window()
        win.msg_queue.put((queued_kind, 1))
        win.request_immediate_stop()
        win._poll_queue()
        check("immediate request upgrades queued " + queued_kind, win._run_status == "CANCELLED")

    # Reproduce the same post-stage race in the distinct recycling loop. The
    # synchronization point is Fourier recomposition, after SharpED returns;
    # the next recycling cycle must never start.
    win, _cycle_results = running_window()
    recycle_state = ordinary_cycle_state(win)
    recycle_state.cfg.reconstruction_mode = "sharped_recycle"
    recycle_state.recycle_map = recycle_state.cfg.work_dir / "recycle_input.xplor"
    recycle_state.recycle_map.write_text("recycle input\n", encoding="utf-8")
    recycle_sharped_calls = []

    def fake_recycle_sharped(_input, output, *_args, **_kwargs):
        recycle_sharped_calls.append(Path(output).name)
        Path(output).write_text("deblurred\n", encoding="utf-8")
        return output

    def cancel_during_recomposition(output, *_args, **_kwargs):
        Path(output).write_text("recomposed\n", encoding="utf-8")
        win.request_immediate_stop()

    with patch.object(appmod, "run_sharped_deblur", side_effect=fake_recycle_sharped), \
         patch.object(appmod, "compose_fobs_phicalc_map", side_effect=cancel_during_recomposition), \
         patch.object(appmod, "xplor_map_correlation", return_value=None), \
         patch.object(appmod, "write_structure_bundle", side_effect=fake_structure), \
         patch.object(appmod, "write_metrics_csv"), \
         patch.object(appmod, "write_map_quality_report"):
        win._run_sharped_recycle_cycles(recycle_state)

    recycle_terminals = [
        kind for kind, _payload in drain_events(win)
        if kind in {"done", "stopped", "cancelled", "error_report"}
    ]
    check("immediate stop during recycling recomposition resolves to CANCELLED", recycle_terminals == ["cancelled"])
    check("immediate stop prevents the next recycling cycle", recycle_sharped_calls == ["cycle_001_deblurred.xplor"])

    # The final completed-progress callback is the last worker-owned boundary
    # before terminal evaluation. Injecting there deterministically covers a
    # cancellation concurrent with completed-cycle bookkeeping.
    win, _cycle_results = running_window()
    finalize_state = ordinary_cycle_state(win)
    finalization_cycles = []
    original_emit_progress = win._emit_cycle_progress

    def cancel_during_completed_progress(*args, **kwargs):
        original_emit_progress(*args, **kwargs)
        if kwargs.get("complete"):
            win.request_immediate_stop()

    def finalization_superflip(cycle_dir, prefix, *_args, **_kwargs):
        finalization_cycles.append(prefix)
        output = cycle_dir / (prefix + ".xplor")
        output.write_text("deterministic map\n", encoding="utf-8")
        return output

    with patch.object(win, "_emit_cycle_progress", side_effect=cancel_during_completed_progress), \
         patch.object(appmod, "run_superflip_cycle", side_effect=finalization_superflip), \
         patch.object(appmod, "export_phased_reflections_from_map"), \
         patch.object(appmod, "parse_superflip_cycle_metrics", return_value=appmod.SuperflipLogMetrics()), \
         patch.object(appmod, "write_structure_bundle", side_effect=fake_structure), \
         patch.object(appmod, "write_metrics_csv"), \
         patch.object(appmod, "write_map_quality_report"):
        win._run_pipeline_cycles(finalize_state)

    finalization_terminals = [
        kind for kind, _payload in drain_events(win)
        if kind in {"done", "stopped", "cancelled", "error_report"}
    ]
    check("immediate stop during completed-cycle bookkeeping resolves to CANCELLED", finalization_terminals == ["cancelled"])
    check("completed-cycle cancellation prevents cycle transition", finalization_cycles == ["cycle_001_superflip"])

    # A graceful checkpoint followed by Continue must start at the following
    # cycle and append one row/result, without replaying the completed cycle.
    win, _cycle_results = running_window()
    resume_state = ordinary_cycle_state(win)
    resumed_cycles = []
    report_result_counts = []
    stop_after_first_report = [True]

    def resume_superflip(cycle_dir, prefix, *_args, **_kwargs):
        resumed_cycles.append(prefix)
        output = cycle_dir / (prefix + ".xplor")
        output.write_text("deterministic map\n", encoding="utf-8")
        return output

    def checkpoint_report(_path, results):
        report_result_counts.append(len(results))
        if stop_after_first_report[0]:
            stop_after_first_report[0] = False
            win.request_stop_after_cycle()

    with patch.object(appmod, "run_superflip_cycle", side_effect=resume_superflip), \
         patch.object(appmod, "export_phased_reflections_from_map"), \
         patch.object(appmod, "parse_superflip_cycle_metrics", return_value=appmod.SuperflipLogMetrics()), \
         patch.object(appmod, "write_structure_bundle", side_effect=fake_structure), \
         patch.object(appmod, "write_metrics_csv", side_effect=checkpoint_report), \
         patch.object(appmod, "write_map_quality_report"):
        win._run_pipeline_cycles(resume_state)
        first_terminals = [
            kind for kind, _payload in drain_events(win)
            if kind in {"done", "stopped", "cancelled", "error_report"}
        ]
        win.stop_after_cycle.clear()
        win.stop_now.clear()
        win._run_pipeline_cycles(resume_state)

    resumed_events = drain_events(win)
    resumed_terminals = [
        kind for kind, _payload in resumed_events
        if kind in {"done", "stopped", "cancelled", "error_report"}
    ]
    check("graceful checkpoint before Continue is STOPPED", first_terminals == ["stopped"])
    check("Continue starts exactly at the next cycle", resumed_cycles == ["cycle_001_superflip", "cycle_002_superflip"])
    check("Continue preserves one result per completed cycle", [result.cycle for result in resume_state.all_results] == [1, 2])
    check("Continue rewrites reports with non-duplicated accumulated rows", report_result_counts == [1, 2])
    check("continued requested work finishes COMPLETE", resumed_terminals == ["done"])

    # Exercise the remaining ordinary-cycle non-process checkpoints through the
    # real loop. Each hook requests cancellation synchronously and the shared
    # terminal gate must prevent cycle 2.
    def run_ordinary_checkpoint(configure, patch_name, side_effect):
        checkpoint_win, _results = running_window()
        checkpoint_state = ordinary_cycle_state(checkpoint_win)
        configure(checkpoint_state)
        checkpoint_state.progress_stages = appmod.cycle_progress_stages(checkpoint_state.cfg)
        checkpoint_cycles = []

        def checkpoint_superflip(cycle_dir, prefix, *_args, **_kwargs):
            checkpoint_cycles.append(prefix)
            output = cycle_dir / (prefix + ".xplor")
            output.write_text("deterministic map\n", encoding="utf-8")
            return output

        with ExitStack() as stack:
            stack.enter_context(patch.object(appmod, "run_superflip_cycle", side_effect=checkpoint_superflip))
            stack.enter_context(patch.object(appmod, "export_phased_reflections_from_map"))
            stack.enter_context(patch.object(appmod, "parse_superflip_cycle_metrics", return_value=appmod.SuperflipLogMetrics()))
            stack.enter_context(patch.object(appmod, "write_structure_bundle", side_effect=fake_structure))
            stack.enter_context(patch.object(appmod, "write_metrics_csv"))
            stack.enter_context(patch.object(appmod, "write_map_quality_report"))
            stack.enter_context(patch.object(appmod, patch_name, side_effect=lambda *args, **kwargs: side_effect(checkpoint_win, *args, **kwargs)))
            checkpoint_win._run_pipeline_cycles(checkpoint_state)

        checkpoint_terminals = [
            kind for kind, _payload in drain_events(checkpoint_win)
            if kind in {"done", "stopped", "cancelled", "error_report"}
        ]
        return checkpoint_terminals, checkpoint_cycles

    def configure_sharped(state):
        state.cfg.run_sharped = True

    def cancel_after_sharped(checkpoint_win, _input, output, *_args, **_kwargs):
        Path(output).write_text("deblurred\n", encoding="utf-8")
        checkpoint_win.request_immediate_stop()
        return output

    terminals, cycles = run_ordinary_checkpoint(configure_sharped, "run_sharped_deblur", cancel_after_sharped)
    check("immediate stop during SharpED postprocessing resolves to CANCELLED", terminals == ["cancelled"])
    check("SharpED postprocessing cancellation prevents cycle transition", cycles == ["cycle_001_superflip"])

    def configure_validation(state):
        from phase_studio.map_quality import ValidationContext, ValidationProfile

        state.validation_context = ValidationContext(
            original_measured_reflections=(), work_reflections=(), free_reflections=(),
            reference_model=None, triplet_set=(), triplet_weights=(), reference_phases=(),
            unit_cell=None, profile=ValidationProfile.REFERENCE_FREE,
        )

    def cancel_during_validation(checkpoint_win, *_args, **_kwargs):
        from phase_studio.map_quality import MapQualityMetrics

        checkpoint_win.request_immediate_stop()
        return MapQualityMetrics()

    terminals, cycles = run_ordinary_checkpoint(configure_validation, "assess_xplor_map", cancel_during_validation)
    check("immediate stop during validation/map-quality metrics resolves to CANCELLED", terminals == ["cancelled"])
    check("validation cancellation prevents cycle transition", cycles == ["cycle_001_superflip"])

    def configure_feedback(state):
        state.cfg.map_feedback_missing_enabled = True
        state.cfg.map_feedback_missing_from_cycle = 1
        state.cfg.map_feedback_missing_percent_limit = 5.0

    def cancel_during_feedback(checkpoint_win, reflections, *_args, **_kwargs):
        checkpoint_win.request_immediate_stop()
        return list(reflections), None

    terminals, cycles = run_ordinary_checkpoint(
        configure_feedback, "apply_map_feedback_to_reflections", cancel_during_feedback,
    )
    check("immediate stop during Map Feedback resolves to CANCELLED", terminals == ["cancelled"])
    check("Map Feedback cancellation prevents cycle transition", cycles == ["cycle_001_superflip"])

    # Invocation and progress baseline for the plumbing consolidated in the
    # final Phase 3B commit. Both scientific EDMA positions remain distinct.
    win, _cycle_results = running_window()
    invocation_state = ordinary_cycle_state(win)
    invocation_state.cfg.run_sharped = True
    invocation_state.cfg.run_edma_superflip = True
    invocation_state.cfg.run_edma_deblurred = True
    invocation_state.cfg.plimit_superflip = 1.25
    invocation_state.cfg.plimit_deblur = 2.5
    invocation_state.progress_stages = appmod.cycle_progress_stages(invocation_state.cfg)
    superflip_invocations = []
    sharped_invocations = []
    edma_invocations = []

    def counted_superflip(cycle_dir, prefix, *_args, **_kwargs):
        superflip_invocations.append(prefix)
        output = cycle_dir / (prefix + ".xplor")
        output.write_text("deterministic map\n", encoding="utf-8")
        return output

    def counted_sharped(input_map, output_map, *_args, **_kwargs):
        sharped_invocations.append((Path(input_map).name, Path(output_map).name))
        Path(output_map).write_text("deterministic deblurred map\n", encoding="utf-8")
        return output_map

    def counted_edma(input_map, output_dir, prefix, _ref_ctx, plimit, *_args, **_kwargs):
        edma_invocations.append((Path(input_map).name, Path(output_dir).name, prefix, plimit))
        output = Path(output_dir) / (prefix + "_edma.cif")
        fake_structure(output)
        return output

    with patch.object(appmod, "run_superflip_cycle", side_effect=counted_superflip), \
         patch.object(appmod, "export_phased_reflections_from_map"), \
         patch.object(appmod, "parse_superflip_cycle_metrics", return_value=appmod.SuperflipLogMetrics()), \
         patch.object(appmod, "run_sharped_deblur", side_effect=counted_sharped), \
         patch.object(appmod, "run_edma_on_xplor", side_effect=counted_edma), \
         patch.object(appmod, "nearest_metric_to_reference", return_value=None), \
         patch.object(appmod, "atom_reference_match_metrics", return_value=None), \
         patch.object(appmod, "count_heavy_atoms", return_value=0), \
         patch.object(appmod, "cif_has_readable_atoms", return_value=True), \
         patch.object(appmod, "write_metrics_csv"), \
         patch.object(appmod, "write_map_quality_report"):
        win._run_pipeline_cycles(invocation_state)

    invocation_events = drain_events(win)
    invocation_progress = [
        payload.stage_name for kind, payload in invocation_events if kind == "cycle_progress"
    ]
    expected_cycle_progress = [
        "Preparing cycle", "Superflip", "Superflip", "EDMA · Superflip map",
        "SharpED", "EDMA · SharpED map", "Finalizing cycle", "Finalizing cycle",
    ]
    check("two ordinary cycles invoke Superflip exactly twice", superflip_invocations == ["cycle_001_superflip", "cycle_002_superflip"])
    check("two ordinary cycles invoke SharpED exactly twice", len(sharped_invocations) == 2)
    check("two ordinary cycles invoke both EDMA positions exactly four times", len(edma_invocations) == 4)
    check(
        "EDMA stage prefixes and thresholds remain distinct and ordered",
        [(item[2], item[3]) for item in edma_invocations] == [
            ("cycle_001_superflip", 1.25), ("cycle_001_deblurred", 2.5),
            ("cycle_002_superflip", 1.25), ("cycle_002_deblurred", 2.5),
        ],
    )
    check("stage progress order is identical for both ordinary cycles", invocation_progress == expected_cycle_progress * 2)
    check("ordinary invocation baseline records exactly two results", [result.cycle for result in invocation_state.all_results] == [1, 2])
    check(
        "ordinary invocation baseline completes once",
        [kind for kind, _payload in invocation_events if kind in {"done", "stopped", "cancelled"}] == ["done"],
    )

    # A blocked automatic EDMA process must not delay submission of the
    # scientifically independent SharpED branch from the same immutable map.
    overlap_win, _results = running_window()
    overlap_state = ordinary_cycle_state(overlap_win, cycles=1)
    overlap_state.cfg.run_sharped = True
    overlap_state.cfg.run_edma_superflip = True
    overlap_state.cfg.run_edma_deblurred = False
    overlap_state.progress_stages = appmod.cycle_progress_stages(overlap_state.cfg)
    sf_edma_started = threading.Event()
    sharped_started = threading.Event()
    release_sf_edma = threading.Event()
    overlap_ok = [False]

    def overlap_edma(_input, output_dir, prefix, *_args, **_kwargs):
        if "superflip" in prefix:
            sf_edma_started.set()
            overlap_ok[0] = sharped_started.wait(1.0)
            release_sf_edma.wait(1.0)
        output = Path(output_dir) / (prefix + "_edma.cif")
        fake_structure(output)
        return output

    def overlap_sharped(_input, output, *_args, **_kwargs):
        sharped_started.set()
        release_sf_edma.set()
        Path(output).write_text("overlapped sharped map\n", encoding="utf-8")
        return output

    with patch.object(appmod, "run_superflip_cycle", side_effect=counted_superflip), \
         patch.object(appmod, "export_phased_reflections_from_map"), \
         patch.object(appmod, "parse_superflip_cycle_metrics", return_value=appmod.SuperflipLogMetrics()), \
         patch.object(appmod, "run_sharped_deblur", side_effect=overlap_sharped), \
         patch.object(appmod, "run_edma_on_xplor", side_effect=overlap_edma), \
         patch.object(appmod, "nearest_metric_to_reference", return_value=None), \
         patch.object(appmod, "atom_reference_match_metrics", return_value=None), \
         patch.object(appmod, "count_heavy_atoms", return_value=0), \
         patch.object(appmod, "cif_has_readable_atoms", return_value=True), \
         patch.object(appmod, "write_metrics_csv"), \
         patch.object(appmod, "write_map_quality_report"):
        overlap_win._run_pipeline_cycles(overlap_state)
    check("SharpED starts while Superflip-map EDMA is still running",
          sf_edma_started.is_set() and sharped_started.is_set() and overlap_ok[0])

    # A failed ordinary cycle checkpoints each completed scientific stage.
    # The five SharpED transport/postprocessing failure labels intentionally
    # enter through the same configured SharpED stage: transport retries stay
    # inside that stage and never restart Superflip or EDMA/Superflip.
    def stage_resume_case(failure_name):
        resume_win, _results = running_window()
        resume_state = ordinary_cycle_state(resume_win, cycles=1)
        resume_state.cfg.run_sharped = True
        resume_state.cfg.run_edma_superflip = True
        resume_state.cfg.run_edma_deblurred = True
        resume_state.progress_stages = appmod.cycle_progress_stages(resume_state.cfg)
        calls = {"superflip": 0, "edma_superflip": 0, "sharped": 0,
                 "edma_sharped": 0, "validation": 0, "reports": 0,
                 "finalization": 0}
        failed = [False]

        def fail_once(stage):
            if failure_name == stage and not failed[0]:
                failed[0] = True
                raise RuntimeError("synthetic " + stage + " failure")

        def matrix_superflip(cycle_dir, prefix, *_args, **_kwargs):
            calls["superflip"] += 1
            fail_once("Superflip")
            output = Path(cycle_dir) / (prefix + ".xplor")
            output.write_text("stable superflip map\n", encoding="utf-8")
            return output

        def matrix_edma(_input, output_dir, prefix, *_args, **_kwargs):
            stage = "edma_superflip" if "superflip" in prefix else "edma_sharped"
            calls[stage] += 1
            fail_once("EDMA / Superflip" if stage == "edma_superflip" else "EDMA / SharpED")
            output = Path(output_dir) / (prefix + "_edma.cif")
            fake_structure(output)
            return output

        def matrix_sharped(_input, output, *_args, **_kwargs):
            calls["sharped"] += 1
            if failure_name in {
                "SharpED upload", "SharpED polling", "SharpED download",
                "SharpED postprocessing",
            } and not failed[0]:
                failed[0] = True
                raise RuntimeError("synthetic " + failure_name + " failure")
            Path(output).write_text("stable sharped map\n", encoding="utf-8")
            return output

        def matrix_validation(*_args, **_kwargs):
            calls["validation"] += 1
            # Superflip validation is first; exercise the final validation.
            if failure_name == "validation" and calls["validation"] == 2 and not failed[0]:
                failed[0] = True
                raise RuntimeError("synthetic validation failure")
            return appmod.MapQualityMetrics()

        def matrix_report(_path, _results):
            calls["reports"] += 1
            fail_once("reports")

        original_finalize = resume_win._finalize_completed_cycle

        def matrix_finalize(*args, **kwargs):
            calls["finalization"] += 1
            fail_once("cycle finalization")
            return original_finalize(*args, **kwargs)

        with patch.object(appmod, "run_superflip_cycle", side_effect=matrix_superflip), \
             patch.object(appmod, "export_phased_reflections_from_map"), \
             patch.object(appmod, "parse_superflip_cycle_metrics", return_value=appmod.SuperflipLogMetrics()), \
             patch.object(appmod, "run_sharped_deblur", side_effect=matrix_sharped), \
             patch.object(appmod, "run_edma_on_xplor", side_effect=matrix_edma), \
             patch.object(appmod, "nearest_metric_to_reference", return_value=None), \
             patch.object(appmod, "atom_reference_match_metrics", return_value=None), \
             patch.object(appmod, "count_heavy_atoms", return_value=0), \
             patch.object(appmod, "cif_has_readable_atoms", return_value=True), \
             patch.object(appmod, "assess_xplor_map", side_effect=matrix_validation), \
             patch.object(appmod, "write_metrics_csv", side_effect=matrix_report), \
             patch.object(appmod, "write_map_quality_report"), \
             patch.object(resume_win, "_finalize_completed_cycle", side_effect=matrix_finalize):
            try:
                resume_win._run_pipeline_cycles(resume_state)
            except RuntimeError:
                pass
            resume_win._run_pipeline_cycles(resume_state)
        return calls, resume_state

    expected_before_failure = {
        "Superflip": (2, 1, 1, 1),
        "EDMA / Superflip": (1, 2, 1, 1),
        "SharpED upload": (1, 1, 2, 1),
        "SharpED polling": (1, 1, 2, 1),
        "SharpED download": (1, 1, 2, 1),
        "SharpED postprocessing": (1, 1, 2, 1),
        "EDMA / SharpED": (1, 1, 1, 2),
        "validation": (1, 1, 1, 1),
        "reports": (1, 1, 1, 1),
        "cycle finalization": (1, 1, 1, 1),
    }
    for failure_name, expected_calls in expected_before_failure.items():
        calls, resumed_state = stage_resume_case(failure_name)
        observed_calls = (
            calls["superflip"], calls["edma_superflip"], calls["sharped"],
            calls["edma_sharped"],
        )
        check(failure_name + " resumes without replaying completed scientific stages",
              observed_calls == expected_calls)
        check(failure_name + " records exactly one result row",
              [item.cycle for item in resumed_state.all_results] == [1])
        check(failure_name + " keeps cycle numbering and completes once",
              resumed_state.completed_cycles == 1)

    feedback_win, _results = running_window()
    feedback_state = ordinary_cycle_state(feedback_win, cycles=2)
    feedback_state.cfg.map_feedback_missing_enabled = True
    feedback_state.cfg.map_feedback_missing_from_cycle = 1
    feedback_state.cfg.map_feedback_missing_percent_limit = 5.0
    feedback_state.progress_stages = appmod.cycle_progress_stages(feedback_state.cfg)
    feedback_superflip_calls = []
    feedback_attempts = [0]

    def feedback_superflip(cycle_dir, prefix, *_args, **_kwargs):
        feedback_superflip_calls.append(prefix)
        output = Path(cycle_dir) / (prefix + ".xplor")
        output.write_text("stable map\n", encoding="utf-8")
        return output

    def failing_feedback(reflections, *_args, **_kwargs):
        feedback_attempts[0] += 1
        if feedback_attempts[0] == 1:
            raise RuntimeError("synthetic Map Feedback failure")
        return list(reflections), None

    with patch.object(appmod, "run_superflip_cycle", side_effect=feedback_superflip), \
         patch.object(appmod, "export_phased_reflections_from_map"), \
         patch.object(appmod, "parse_superflip_cycle_metrics", return_value=appmod.SuperflipLogMetrics()), \
         patch.object(appmod, "write_structure_bundle", side_effect=fake_structure), \
         patch.object(appmod, "apply_map_feedback_to_reflections", side_effect=failing_feedback), \
         patch.object(appmod, "write_metrics_csv"), \
         patch.object(appmod, "write_map_quality_report"):
        try:
            feedback_win._run_pipeline_cycles(feedback_state)
        except RuntimeError:
            pass
        feedback_win._run_pipeline_cycles(feedback_state)
    check("Map Feedback resume does not rerun cycle 1 Superflip",
          feedback_superflip_calls == ["cycle_001_superflip", "cycle_002_superflip"])
    check("Map Feedback resume does not duplicate result/report rows",
          [item.cycle for item in feedback_state.all_results] == [1, 2])
    check("Map Feedback resumes at the unchanged cycle number",
          feedback_state.completed_cycles == 2)

    # Consuming an error event changes only the terminal UI. It cannot invoke
    # Continue or start another worker behind the user's back.
    auto_retry_win, _results = running_window()
    auto_retry_calls = []
    auto_retry_win.continue_run = lambda: auto_retry_calls.append("continue")
    auto_retry_win._show_error_report = lambda *_args, **_kwargs: None
    auto_retry_win.msg_queue.put(("error_report", appmod.build_error_report(RuntimeError("offline"))))
    auto_retry_win._poll_queue()
    check("a workflow failure never invokes Continue automatically", auto_retry_calls == [])


    # --- Mechanism invocation counts (release acceptance) -----------------
    # Deterministic mocks for the two DISTINCT cycle mechanisms:
    #   ordinary loop (_run_pipeline_cycles, reconstruction_mode "superflip",
    #   used by Autosolve): Superflip AND SharpED every cycle;
    #   specialized phase recycling (_run_sharped_recycle_cycles,
    #   "sharped_recycle", Professional "1st Superflip, then SharpED (beta)"):
    #   Superflip at most once, SharpED + |Fobs|/phi_calc recomposition every
    #   cycle. Also records what Result Selection genuinely receives.
    def invocation_case(mode, cycles=3):
        case_win, _results = running_window()
        case_state = ordinary_cycle_state(case_win, cycles=cycles)
        case_state.cfg.reconstruction_mode = mode
        case_state.cfg.run_sharped = True
        case_state.cfg.run_edma_superflip = True
        case_state.cfg.run_edma_deblurred = True
        case_state.cfg.run_edma_recycle_final = True
        case_state.progress_stages = appmod.cycle_progress_stages(case_state.cfg)
        # The real run always builds a validation context; without one no
        # cycle gets a quality and nothing becomes a Result Selection candidate.
        from phase_studio.map_quality import FrozenReflection, make_validation_context
        case_state.validation_context = make_validation_context([FrozenReflection(1, 0, 0, 10.0)])
        counts = {"superflip": 0, "sharped": 0, "compose": 0, "edma": 0}

        def count_superflip(cycle_dir, prefix, *_args, **_kwargs):
            counts["superflip"] += 1
            output = Path(cycle_dir) / (prefix + ".xplor")
            output.write_text("superflip map\n", encoding="utf-8")
            return output

        def count_sharped(_input, output, *_args, **_kwargs):
            counts["sharped"] += 1
            Path(output).write_text("sharped map\n", encoding="utf-8")
            return output

        def count_compose(output, *_args, **_kwargs):
            counts["compose"] += 1
            Path(output).write_text("recomposed map\n", encoding="utf-8")

        def count_edma(_input, output_dir, prefix, *_args, **_kwargs):
            counts["edma"] += 1
            output = Path(output_dir) / (prefix + "_edma.cif")
            fake_structure(output)
            return output

        with patch.object(appmod, "run_superflip_cycle", side_effect=count_superflip), \
             patch.object(appmod, "export_phased_reflections_from_map"), \
             patch.object(appmod, "parse_superflip_cycle_metrics", return_value=appmod.SuperflipLogMetrics()), \
             patch.object(appmod, "run_sharped_deblur", side_effect=count_sharped), \
             patch.object(appmod, "compose_fobs_phicalc_map", side_effect=count_compose), \
             patch.object(appmod, "xplor_map_correlation", return_value=None), \
             patch.object(appmod, "run_edma_on_xplor", side_effect=count_edma), \
             patch.object(appmod, "nearest_metric_to_reference", return_value=None), \
             patch.object(appmod, "atom_reference_match_metrics", return_value=None), \
             patch.object(appmod, "count_heavy_atoms", return_value=0), \
             patch.object(appmod, "cif_has_readable_atoms", return_value=True), \
             patch.object(appmod, "assess_xplor_map", return_value=appmod.MapQualityMetrics()), \
             patch.object(appmod, "write_metrics_csv"), \
             patch.object(appmod, "write_map_quality_report"):
            if mode == "superflip":
                case_win._run_pipeline_cycles(case_state)
            else:
                case_win._run_sharped_recycle_cycles(case_state)
        candidates = appmod.result_candidates_from_results(case_state.all_results)
        per_source = {
            source: sorted(c.cycle for c in candidates if c.source == source)
            for source in ("superflip", "deblurred")
        }
        return counts, per_source, case_state

    ordinary_counts, ordinary_candidates, ordinary_state = invocation_case("superflip")
    check("ordinary loop, 3 cycles: Superflip runs every cycle (3)", ordinary_counts["superflip"] == 3)
    check("ordinary loop, 3 cycles: SharpED runs every cycle (3)", ordinary_counts["sharped"] == 3)
    check("ordinary loop: no |Fobs|/phi_calc recomposition", ordinary_counts["compose"] == 0)
    check(
        "ordinary loop: Superflip Cycle 1..3 and SharpED Cycle 1..3 candidates",
        ordinary_candidates == {"superflip": [1, 2, 3], "deblurred": [1, 2, 3]},
    )
    recycle_counts, recycle_candidates, recycle_state = invocation_case("sharped_recycle")
    check("specialized recycling, 3 cycles: Superflip runs at most once (1)", recycle_counts["superflip"] == 1)
    check("specialized recycling, 3 cycles: SharpED runs every cycle (3)", recycle_counts["sharped"] == 3)
    check("specialized recycling, 3 cycles: |Fobs|/phi_calc recomposition every cycle (3)", recycle_counts["compose"] == 3)
    check("specialized recycling: EDMA only on the final map (1)", recycle_counts["edma"] == 1)
    check(
        "specialized recycling: Result Selection gets ONE real Superflip candidate and 3 SharpED-recycled candidates",
        recycle_candidates == {"superflip": [1], "deblurred": [1, 2, 3]},
    )
    check(
        "both mechanisms are separate code paths (recycle results carry their own model_source)",
        {r.model_source for r in recycle_state.all_results} == {"sharped_recycle"}
        and all(r.model_source != "sharped_recycle" for r in ordinary_state.all_results),
    )
    provenance_base = ordinary_state.all_results[0]
    provenance_results = [
        dataclasses.replace(
            provenance_base, cycle=1, model_source="none",
            intensity_correction_avg_change_percent=None,
            powder_repartition_avg_change_percent=None,
        ),
        dataclasses.replace(
            provenance_base, cycle=2, model_source="deblurred_xplor",
            intensity_correction_avg_change_percent=3.25,
        ),
        # The label follows the actual input even at a later cycle; cycle
        # number alone is deliberately not an initialization authority.
        dataclasses.replace(provenance_base, cycle=3, model_source="none"),
    ]
    provenance_candidates = [
        candidate for candidate in appmod.result_candidates_from_results(provenance_results)
        if candidate.source == "superflip"
    ]
    check(
        "candidate lineage records Cycle 1's verified random phase start",
        provenance_candidates[0].superflip_initialization == "Random phase start",
    )
    check(
        "candidate lineage records an actual SharpED-map seed independently of cycle number",
        provenance_candidates[1].superflip_initialization == "SharpED-seeded"
        and provenance_candidates[2].superflip_initialization == "Random phase start",
    )
    check(
        "candidate lineage distinguishes original and Map Feedback-adjusted reflection data",
        provenance_candidates[0].reflection_input_provenance == "Original measured reflection data"
        and provenance_candidates[1].reflection_input_provenance == "Map Feedback-adjusted reflection data",
    )

    # Routing pins that ARE settled: Autosolve launches the ordinary loop;
    # Professional's specialized option resolves to "sharped_recycle".
    check("Professional '1st Superflip, then SharpED (beta)' -> sharped_recycle",
          appmod.normalize_reconstruction_mode("1st Superflip, then SharpED (beta)") == "sharped_recycle")
    launcher_source = Path(appmod.__file__).with_name("jana_superflip.py").read_text(encoding="utf-8")
    autosolve_block = launcher_source[launcher_source.index("def launch_autosolve_from_jana"):]
    autosolve_block = autosolve_block[:autosolve_block.index("\ndef ", 1)]
    check(
        "Autosolve applies the 'recommended' preset (reconstruction_mode Superflip) and never selects sharped_recycle",
        'win._apply_workflow_preset("recommended")' in autosolve_block
        and "sharped_recycle" not in autosolve_block and "reconstruction_mode" not in autosolve_block.split('"""', 2)[-1],
    )
    preset_win, _unused = running_window()
    preset_win._apply_workflow_preset("recommended")
    check("the 'recommended' preset selects the ordinary loop",
          appmod.normalize_reconstruction_mode(preset_win._combo_value("reconstruction_mode")) == "superflip")

    # Three top-level runs in one GUI process must own disjoint directories,
    # candidates and model provenance. Delayed Run-1 terminal events are
    # deliberately queued before Run 2 starts and must be discarded.
    isolation_win, isolation_templates = running_window("full_configuration")
    isolation_base = Path(tempfile.mkdtemp()) / "phase-studio-runs"
    run_records = []
    for index, model_name in enumerate((
        "koala 2.0", "koala model progressive", "koala 2.0",
    ), start=1):
        cfg = ordinary_cycle_state(isolation_win, cycles=1).cfg
        cfg.work_dir = isolation_base
        cfg.first_cycle_modelfile = None
        incoming = isolation_base.parent / f"incoming_run_{index}.inflip"
        incoming.write_bytes(f"title diagnostic_run_{index}\r\n# Original Jana context\r\n".encode("ascii"))
        cfg.jana_inflip = incoming
        if index > 1:
            isolation_win.msg_queue.put(("result", isolation_templates[0]))
            isolation_win.msg_queue.put(("done", 99))
        isolation_win._begin_fresh_run_context(cfg)
        snapshot = cfg.work_dir / "diagnostics" / "incoming.inflip"
        check(f"sequential run {index}: incoming Jana input is retained byte-for-byte",
              snapshot.read_bytes() == incoming.read_bytes())
        metadata = appmod.json.loads((snapshot.parent / "incoming_context.json").read_text(encoding="utf-8"))
        check(f"sequential run {index}: diagnostic copy preserves the authoritative original context",
              cfg.jana_inflip == incoming and metadata["source"] == str(incoming)
              and metadata["sha256"] == appmod.file_sha256(incoming))
        isolation_win.last_run_config = cfg
        template = isolation_templates[0]
        map_path = cfg.work_dir / f"{model_name.replace(' ', '-')}-{index}.xplor"
        cif_path = cfg.work_dir / f"{model_name.replace(' ', '-')}-{index}.cif"
        map_path.write_text(f"map for {cfg.run_id} {model_name}\n", encoding="utf-8")
        cif_path.write_text(tjc.CIF + f"\n# {cfg.run_id} {model_name}\n", encoding="utf-8")
        result = appmod.replace(
            template,
            cycle=1,
            deblur_map=map_path,
            deblur_edma_cif=cif_path,
            sharped_model=model_name,
            run_id=cfg.run_id,
        )
        isolation_win.results = [result]
        candidate = next(
            item for item in isolation_win._result_candidates()
            if item.source == "deblurred"
        )
        run_records.append((cfg.run_id, cfg.work_dir, candidate))
        isolation_win._poll_queue()
        check(f"sequential run {index}: stale queue events cannot alter the fresh registry",
              isolation_win.results == [result] and isolation_win._run_status == "RUNNING")
        check(f"sequential run {index}: first-cycle model remains genuinely empty",
              cfg.first_cycle_modelfile is None)
    check("three-run stress: unique monotonically allocated run IDs and directories",
          [record[0] for record in run_records] == ["run_0001", "run_0002", "run_0003"]
          and len({record[1] for record in run_records}) == 3)
    check("three-run stress: each candidate carries only its own run identity",
          all(candidate.run_id == run_id and candidate.candidate_id.startswith(run_id + ":")
              for run_id, _directory, candidate in run_records))
    check("three-run stress: model order is exact in both directions",
          [record[2].sharped_model for record in run_records]
          == ["koala 2.0", "koala model progressive", "koala 2.0"])
    check("three-run stress: no map or structure hash is reused",
          len({record[2].map_sha256 for record in run_records}) == 3
          and len({record[2].structure_sha256 for record in run_records}) == 3)
    check("three-run stress: every candidate artifact is inside its owning run directory",
          all(Path(candidate.map_path).parent == directory
              and Path(candidate.structure_path).parent == directory
              for _run_id, directory, candidate in run_records))

    failures = [name for name, ok in results_log if not ok]
    print()
    if failures:
        print(str(len(failures)) + " of " + str(len(results_log)) + " checks FAILED:")
        for name in failures:
            print("  - " + name)
        return 1
    print("All " + str(len(results_log)) + " checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
