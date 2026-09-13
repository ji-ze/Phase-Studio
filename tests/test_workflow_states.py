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
import os
import sys
from pathlib import Path

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
        "graceful stop keeps the Jana2020 action labelled Send to Jana2020",
        win.jana_action_btn.text() == "Send to Jana2020",
    )
    opened = []
    QDialog.exec = lambda self: (opened.append(self.windowTitle()), QDialog.Rejected)[1]
    win._on_jana_action_clicked()
    check(
        "graceful stop: the result selector still opens for the completed cycles",
        opened == ["Jana2020 result selection"],
    )
    QDialog.exec = lambda self: QDialog.Rejected
    check(
        "graceful stop does not require the configured cycle count to finish",
        len(win.results) < int(win.last_run_config.cycles),
    )

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
