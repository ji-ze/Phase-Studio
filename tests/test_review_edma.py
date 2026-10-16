"""Release guards for independent, non-blocking interactive EDMA review."""

import queue
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase_studio.review_edma import ReviewEDMAExecutor


checks = []


def check(name, condition):
    checks.append((name, bool(condition)))
    print(("PASS" if condition else "FAIL") + " - " + name)


def request(executor, key, threshold, job, callback, run_id="run-1"):
    return executor.request(
        key=key, cache_key=(*key, threshold), run_id=run_id,
        candidate_id=f"{key}-{threshold}", source=str(key[1]), cycle=int(key[2]),
        threshold=threshold, job=job, callback=callback,
    )


def main():
    outcomes = queue.Queue()
    executor = ReviewEDMAExecutor(outcomes.put)
    gate = threading.Event()
    started = []
    callbacks = []
    callback_threads = []
    gui_thread = threading.get_ident()

    def slow_job(threshold):
        def run(stop_event):
            started.append(threshold)
            while not gate.wait(0.005):
                if stop_event.is_set():
                    raise RuntimeError("cancelled")
            return f"candidate-{threshold}"
        return run

    def completed(outcome):
        callbacks.append(outcome.request.threshold)
        callback_threads.append(threading.get_ident())

    key = ("run-1", "sharped", 1, "map-hash")
    started_at = time.perf_counter()
    request(executor, key, 0.8, slow_job(0.8), completed)
    for threshold in (0.7, 0.6, 0.5):
        request(executor, key, threshold, slow_job(threshold), completed)
    latency = time.perf_counter() - started_at
    check("four rapid threshold callbacks return without waiting for EDMA", latency < 0.05)
    check("one candidate has only one active review process", started == [0.8])
    check("latest requested threshold is visible while review runs",
          executor.requested_threshold(key, 1.0) == 0.5)

    workflow_ticks = []
    workflow_done = threading.Event()

    def workflow():
        for index in range(5):
            workflow_ticks.append(index)
            time.sleep(0.005)
        workflow_done.set()

    threading.Thread(target=workflow, daemon=True).start()
    check("main workflow progresses while review EDMA remains blocked",
          workflow_done.wait(0.2) and not gate.is_set())

    gate.set()
    first = outcomes.get(timeout=1.0)
    executor.complete(first)
    latest = outcomes.get(timeout=1.0)
    executor.complete(latest)
    check("rapid clicks run first and latest requests only", started == [0.8, 0.5])
    check("obsolete completion never updates the panel", callbacks == [0.5])
    check("review callbacks execute on the GUI owner thread",
          callback_threads == [gui_thread])

    calls_before_cache = len(started)
    request(executor, key, 0.8, slow_job(0.8), completed)
    cached = outcomes.get(timeout=0.2)
    executor.complete(cached)
    check("returning to a completed threshold uses the cache", cached.cache_hit)
    check("cached threshold does not launch another EDMA process",
          len(started) == calls_before_cache)

    parallel_gate = threading.Event()
    both_started = threading.Event()
    active = set()
    active_lock = threading.Lock()

    def parallel_job(label):
        def run(_stop_event):
            with active_lock:
                active.add(label)
                if len(active) == 2:
                    both_started.set()
            parallel_gate.wait(1.0)
            return label
        return run

    request(executor, ("run-1", "superflip", 1, "sf-map"), 0.9,
            parallel_job("superflip"), lambda _outcome: None)
    request(executor, ("run-1", "sharped", 1, "sh-map"), 0.4,
            parallel_job("sharped"), lambda _outcome: None)
    check("different candidates can run review EDMA concurrently", both_started.wait(0.5))
    parallel_gate.set()
    for _ in range(2):
        executor.complete(outcomes.get(timeout=1.0))

    stale_gate = threading.Event()
    stale_callbacks = []

    def stale_job(stop_event):
        while not stale_gate.wait(0.005):
            if stop_event.is_set():
                raise RuntimeError("cancelled")
        return "stale"

    request(executor, ("run-1", "sharped", 2, "old-map"), 0.4,
            stale_job, lambda outcome: stale_callbacks.append(outcome))
    executor.cancel_all()
    stale_gate.set()
    executor.complete(outcomes.get(timeout=1.0))
    check("cancelled Run-1 review cannot call back into Run 2", not stale_callbacks)

    # Exercise the production scheduling boundary with EDMA replaced by a
    # deterministic file writer.  This proves the review calls only EDMA, uses
    # the immutable selected map, and allocates a request-specific workspace.
    from phase_studio.app import CycleResult, IterativeSuperflipPipelineQtGUI
    from phase_studio.map_quality import MapQualityMetrics, ResultCandidate
    with tempfile.TemporaryDirectory() as temp_name:
        temp = Path(temp_name)
        selected_map = temp / "run_001" / "cycle_001" / "sharped.xplor"
        selected_map.parent.mkdir(parents=True)
        selected_map.write_text("immutable scientific map", encoding="utf-8")
        original_cif = temp / "original.cif"
        cif_text = (
            "data_review\n_cell_length_a 10\n_cell_length_b 10\n_cell_length_c 10\n"
            "_cell_angle_alpha 90\n_cell_angle_beta 90\n_cell_angle_gamma 90\n"
            "_space_group_name_H-M_alt 'P 1'\nloop_\n_atom_site_label\n"
            "_atom_site_type_symbol\n_atom_site_fract_x\n_atom_site_fract_y\n"
            "_atom_site_fract_z\nC1 C 0.1 0.1 0.1\n"
        )
        original_cif.write_text(cif_text, encoding="utf-8")
        candidate = ResultCandidate(
            cycle=1, source="deblurred", map_path=str(selected_map),
            structure_path=str(original_cif), metrics=MapQualityMetrics(),
            edma_sigma=0.5, candidate_id="run-1:sharped:c001:t0.50:fixture",
            map_sha256="map-hash", run_id="run-1",
        )
        result = CycleResult(
            cycle=1, model_source="none", model_in=None, model_metric=None,
            superflip_map=selected_map, superflip_edma_cif=original_cif,
            superflip_metric=None, deblur_map=selected_map,
            deblur_edma_cif=original_cif, deblur_metric=None,
            deblur_edma_sigma=0.5, run_id="run-1",
        )
        production_outcomes = queue.Queue()
        backend = SimpleNamespace()
        backend.review_edma_executor = ReviewEDMAExecutor(production_outcomes.put)
        backend._resume_state = SimpleNamespace(
            cfg=SimpleNamespace(work_dir=temp), run_id="run-1",
        )
        backend._active_run_id = "run-1"
        backend._run_event_context = threading.local()
        backend.stop_now = threading.Event()
        backend._review_candidate_key = IterativeSuperflipPipelineQtGUI._review_candidate_key
        backend._review_cache_key = IterativeSuperflipPipelineQtGUI._review_cache_key
        backend._cycle_result_for_candidate = lambda _candidate: result
        review_logs = []
        backend._append_execution_log = lambda message, **kwargs: review_logs.append((message, kwargs))
        edma_calls = []

        def fake_edma(state, input_map, output_dir, prefix, threshold, **kwargs):
            edma_calls.append((Path(input_map), Path(output_dir), prefix, threshold, kwargs))
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            produced = Path(output_dir) / f"{prefix}.cif"
            produced.write_text(cif_text, encoding="utf-8")
            return produced

        backend._run_configured_edma_stage = fake_edma
        production_callbacks = []
        production_request = IterativeSuperflipPipelineQtGUI.request_result_candidate_retune(
            backend,
            candidate, True,
            lambda updated, report, req: production_callbacks.append((updated, report, req)),
        )
        backend.review_edma_executor.complete(production_outcomes.get(timeout=1.0))
        check("production +atoms schedules exactly one EDMA call", len(edma_calls) == 1)
        check("production review reads the exact immutable selected map",
              edma_calls[0][0].resolve() == selected_map.resolve()
              and selected_map.read_text(encoding="utf-8") == "immutable scientific map")
        check("production review uses a request-specific workspace outside the active cycle",
              "review_edma" in edma_calls[0][1].parts
              and edma_calls[0][1] != selected_map.parent)
        check("production review owns an independent cancellation event",
              edma_calls[0][4]["stop_event"] is not backend.stop_now)
        check("production review is EDMA-only and publishes the requested threshold",
              production_request.threshold == 0.4
              and production_callbacks[0][0].edma_sigma == 0.4
              and production_callbacks[0][1] is None)
        updated_candidate = production_callbacks[0][0]
        check("threshold completion atomically publishes structure identity and ASU composition",
              updated_candidate.edma_asu_composition == "C1"
              and updated_candidate.structure_sha256
              and updated_candidate.candidate_id != candidate.candidate_id)
        check("completed review updates only its matching Cycle-1 SharpED candidate",
              result.deblur_edma_sigma == 0.4
              and result.superflip_edma_cif == original_cif)
        gui_review_logs = [message for message, kwargs in review_logs if kwargs.get("level") != "DETAIL"]
        detailed_review_logs = [message for message, kwargs in review_logs if kwargs.get("level") == "DETAIL"]
        check("review EDMA GUI logging is concise start/completion progress",
              any("Structure prediction · EDMA recalculation started · 0.40" in message for message in gui_review_logs)
              and any("Structure prediction · EDMA updated · 1 detected sites · 0.40" in message for message in gui_review_logs))
        check("review EDMA diagnostics prove request/candidate/map/paths/hash/duration",
              any(all(token in message for token in (
                  "Review EDMA request", candidate.candidate_id, "source map SHA-256 map-hash",
                  str(selected_map), "output directory",
              )) for message in detailed_review_logs)
              and any(all(token in message for token in (
                  "complete", "resulting SHA-256", "duration",
              )) for message in detailed_review_logs))

    failures = [name for name, passed in checks if not passed]
    if failures:
        print(f"\n{len(failures)} of {len(checks)} checks FAILED:")
        for name in failures:
            print("  - " + name)
        raise SystemExit(1)
    print(f"\nAll {len(checks)} checks passed.")


if __name__ == "__main__":
    main()
