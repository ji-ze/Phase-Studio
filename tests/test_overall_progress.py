"""Regression: the overall (completed-cycle) progress bar is determinate
from the start of a run and never regresses within it.

Root cause guarded here: start_run() and continue_run() used to switch the
overall bar to the indeterminate (0, 0) busy state, which a static
screenshot shows as a half-filled bar; the next progress_setup event then
reset it to 0, and Autosolve's adaptive extension (10 -> 15 cycles) or
Option B's Map Feedback stage dropped it back again. Only stage-local bars
(current_cycle_progress) may be indeterminate, for work of unknown
duration.

Plain Python test (no pytest dependency); run with
`python tests/test_overall_progress.py`.
"""
import ast
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

results_log = []


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


def method_source(class_name, method_name):
    source = (ROOT / "phase_studio" / "app.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return ast.get_source_segment(source, item)
    return ""


def main():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([sys.argv[0]])
    import phase_studio.app as appmod
    from test_jana_completion import build_window

    appmod.IterativeSuperflipPipelineQtGUI.save_settings = lambda self: None
    appmod.IterativeSuperflipPipelineQtGUI.load_settings = lambda self: None

    # Static: neither entry point puts the OVERALL bar into busy mode.
    for method in ("start_run", "continue_run"):
        body = method_source("IterativeSuperflipPipelineQtGUI", method)
        check(f"{method}: source found", bool(body))
        check(f"{method}: never sets the overall bar indeterminate (progress_bar.setRange(0, 0))",
              "progress_bar.setRange(0, 0)" not in body)
        check(f"{method}: sets a determinate cycle range", "self.progress_bar.setRange(0, max(1, int(" in body)

    win, _results = build_window(appmod, launch_mode="autosolve", cycles=1)
    bar = win.progress_bar
    trace = []

    def record(label):
        trace.append((label, bar.minimum(), bar.maximum(), bar.value()))

    def event(kind, payload):
        win.msg_queue.put((kind, payload))
        win._poll_queue()
        record(f"{kind}({payload})")

    # A fresh run (what start_run() does before the worker starts).
    win._overall_progress_floor = 0
    bar.setRange(0, 10)
    win._set_overall_progress_value(0)
    record("start_run")
    event("progress_setup", 10)
    for cycle in (1, 2, 3):
        event("progress", cycle)
    # A stale or out-of-order re-emission must not move the bar backwards.
    event("progress", 2)
    check("a stale progress event does not regress the bar (stays at 3)", bar.value() == 3)
    # A re-sent progress_setup (resume / continue) keeps the value reached.
    event("progress_setup", 10)
    check("a repeated progress_setup does not reset the bar to 0", bar.value() == 3)
    for cycle in range(4, 11):
        event("progress", cycle)
    check("cycle 10 of 10 fills the bar", (bar.value(), bar.maximum()) == (10, 10))

    # Autosolve's adaptive extension 10 -> 15 (continue_run() + the
    # resumed worker's progress_setup): same completed count, new total.
    bar.setRange(0, 15)
    win._set_overall_progress_value(10)
    record("continue_run(15)")
    event("progress_setup", 15)
    check("adaptive extension 10 -> 15: bar shows 10 of 15, not 0", (bar.value(), bar.maximum()) == (10, 15))
    for cycle in range(11, 16):
        event("progress", cycle)

    # Option B's Map Feedback stage (another continue: 15 -> 25).
    bar.setRange(0, 25)
    win._set_overall_progress_value(15)
    record("continue_run(25)")
    event("progress_setup", 25)
    event("progress", 16)

    values = [value for _label, _lo, _hi, value in trace]
    check("the overall bar is determinate at every step (maximum > 0)", all(hi > 0 for _l, _lo, hi, _v in trace))
    check("the overall value never decreases within the run",
          all(later >= earlier for earlier, later in zip(values, values[1:])))
    check("the overall value never exceeds the current total", all(v <= hi for _l, _lo, hi, v in trace))
    if not all(later >= earlier for earlier, later in zip(values, values[1:])):
        for row in trace:
            print("   ", row)

    # Terminal states keep the reached value (CANCELLED / STOPPED).
    win._finish_cancelled_run()
    check("Cancelled keeps the completed-cycle value", bar.value() == 16 and bar.maximum() > 0)

    # A genuinely new workflow (Clear results / fresh start_run) resets.
    win.clear_log_plot()
    check("clearing results resets the floor and the bar", win._overall_progress_floor == 0 and bar.value() == 0)
    bar.setRange(0, 5)
    win._set_overall_progress_value(1)
    check("after a reset, a new run starts from its own progress", bar.value() == 1)

    # Stage-local work of unknown duration stays indeterminate.
    busy = appmod.CycleProgressState(
        cycle_index=1, cycle_total=5, stage_name="SharpED", stage_index=2, stage_total=4, busy=True,
    )
    win._apply_cycle_progress_state(busy)
    check("unknown-duration stage work shows the stage bar indeterminate", win.current_cycle_progress.maximum() == 0)
    check("... while the overall bar stays determinate", bar.maximum() > 0)
    win.close()

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
