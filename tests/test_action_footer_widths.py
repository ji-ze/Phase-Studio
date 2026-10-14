"""Regression: primary action labels ("Save map and model" / "Pass to
Jana2020" and the other action/footer buttons) are never clipped at
constrained logical widths.

Root cause guarded here: the main window's primary action row gave every
button an equal third of the row (QSizePolicy.Ignored + equal stretch), so
at ~1268 logical px the longest label, "Save map and model", was cut. Each
button's minimum width is now its own text-derived size hint and the row's
stretch follows those hints.

Checked for the main window and the shared Result Selection dialog, in both
the standalone and the Jana2020 context, at logical widths 1024-1920, with
1/2/4/10/30 candidates, in child processes at QT_SCALE_FACTOR 1 / 1.25 / 1.5.
This is Qt logical geometry, not physical Windows display scaling.

Plain Python test (no pytest dependency); run with
`python tests/test_action_footer_widths.py`.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCALES = ("1", "1.25", "1.5")
WIDTHS = (1024, 1152, 1200, 1268, 1280, 1366, 1440, 1920)
COUNTS = (1, 2, 4, 10, 30)

CHILD = r'''
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, str(Path(sys.argv[1]) / "tests"))
from PySide6.QtWidgets import QApplication, QDialog, QPushButton
app = QApplication([sys.argv[0]])
import phase_studio.ui_style as ui_style
ui_style.apply_phase_studio_style(app)
from phase_studio import app as appmod
from test_jana_completion import build_window
WIDTHS = [int(v) for v in sys.argv[2].split(",")]
COUNTS = [int(v) for v in sys.argv[3].split(",")]
ACTION_TEXTS = {"Run phasing", "Continue run", "Save map and model", "Pass to Jana2020", "Save available result",
                "Stop after current cycle", "Stop immediately", "Clear results", "Return to Phase Studio"}

def clipped(root):
    out = []
    for b in root.findChildren(QPushButton):
        if b.isVisibleTo(root) and b.text() in ACTION_TEXTS and b.width() < b.sizeHint().width():
            out.append(f"{b.text()!r} {b.width()}<{b.sizeHint().width()}")
    return out

opened = []
QDialog.exec = lambda self: (opened.append(self), QDialog.Rejected)[1]
for context, launch_mode in (("standalone", "standalone"), ("jana", "full_configuration")):
    win, results = build_window(appmod, launch_mode=launch_mode, cycles=max(COUNTS))
    win.results = results
    win._sync_jana_action_button()
    win.show()
    for width in WIDTHS:
        win.resize(width, 800)
        app.processEvents()
        label = win.jana_action_btn.text()
        problems = clipped(win)
        print(f"MAIN {context} {width} label={label!r} actual={win.width()} " + ("OK" if not problems else "CLIPPED " + "; ".join(problems)))
    all_superflip = [c for c in win._result_candidates() if c.source == "superflip"]
    for count in COUNTS:
        win._result_candidates = lambda n=count: all_superflip[:n]
        opened.clear()
        win.open_result_selector("jana" if context == "jana" else "standalone")
        dialog = opened[-1]
        dialog.show()
        for width in WIDTHS:
            dialog.resize(width, 760)
            app.processEvents()
            problems = clipped(dialog)
            print(f"DIALOG {context} n={count} {width} label={dialog._action_button.text()!r} actual={dialog.width()} " + ("OK" if not problems else "CLIPPED " + "; ".join(problems)))
        dialog.close()
    win.close()

# AutosolveWindow footer: Cancel plus the 2.0.2 early Pass to Jana2020 action
# more -- see the per-panel REVIEW_TEXTS check below) and the view toolbar,
# never clipped.
from phase_studio.autosolve_window import AutosolveWindow
from PySide6.QtWidgets import QToolButton
AUTOSOLVE_TEXTS = {"Cancel", "Fit", "Reset view", "Auto rotate: On", "Complete molecules", "Full cell"}
backend, results = build_window(appmod, launch_mode="autosolve", cycles=3)
backend.results = results
aw = AutosolveWindow(backend, "A")
aw.show()
for width in WIDTHS:
    aw.resize(width, 800)
    app.processEvents()
    aw._refresh_tick()
    app.processEvents()
    buttons = [b for b in aw.findChildren(QPushButton) + aw.findChildren(QToolButton) if b.isVisibleTo(aw) and b.text() in AUTOSOLVE_TEXTS]
    problems = [f"{b.text()!r} {b.width()}<{b.sizeHint().width()}" for b in buttons if b.width() < b.sizeHint().width()]
    seen = sorted({b.text() for b in buttons})
    print(f"AUTOSOLVE {width} actual={aw.width()} seen={len(seen)} " + ("OK" if not problems else "CLIPPED " + "; ".join(problems)))
# 2.0.1 Review: both panels' four actions (+ atoms, - atoms, Recalculate,
# Pass to Jana2020) must stay readable at every width and scale.
import phase_studio.autosolve_review as guided
from pathlib import Path as _P
first = results[0]
backend.autosolve_panels = {
    "observed": guided.ReviewPanel("observed", first.cycle, _P(first.superflip_map), _P(first.superflip_edma_cif), 1.0),
    "predicted": guided.ReviewPanel("predicted", first.cycle, _P(first.deblur_map), _P(first.deblur_edma_cif), 2.0,
                                    sharped_model=guided.PREDICTION_MODEL),
}
backend._autosolve_stage = "review"
backend._set_run_status("Review")
REVIEW_TEXTS = {"+ atoms", "- atoms", "Recalculate", "Pass to Jana2020", "Save map and model"}
for width in WIDTHS:
    aw.resize(width, 860)
    app.processEvents()
    aw._refresh_tick()
    app.processEvents()
    buttons = [b for b in aw.findChildren(QPushButton) if b.isVisibleTo(aw) and b.text() in REVIEW_TEXTS]
    problems = [f"{b.text()!r} {b.width()}<{b.sizeHint().width()}" for b in buttons if b.width() < b.sizeHint().width()]
    print(f"REVIEW {width} actual={aw.width()} seen={len(buttons)} " + ("OK" if not problems else "CLIPPED " + "; ".join(problems)))
aw.close()
print("DONE")
'''

results_log = []
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


def main():
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        child = Path(directory) / "child.py"
        child.write_text(CHILD, encoding="utf-8")
        for scale in SCALES:
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR=scale, PYTHONIOENCODING="utf-8")
            if os.name == "nt":
                env.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
            done = subprocess.run(
                [sys.executable, str(child), str(ROOT), ",".join(map(str, WIDTHS)), ",".join(map(str, COUNTS))],
                capture_output=True, text=True, encoding="utf-8", env=env, timeout=900,
            )
            out = done.stdout
            tag = f"{float(scale) * 100:.0f}%"
            check(f"{tag}: child ran to completion", "DONE" in out)
            if "DONE" not in out:
                print(done.stderr[-3000:])
                continue
            lines = [line for line in out.splitlines() if line.startswith(("MAIN", "DIALOG"))]
            for kind, context in (("MAIN", "standalone"), ("MAIN", "jana"), ("DIALOG", "standalone"), ("DIALOG", "jana")):
                rows = [line for line in lines if line.startswith(f"{kind} {context} ")]
                bad = [line for line in rows if "CLIPPED" in line]
                for line in bad:
                    print("   " + line)
                expected_rows = len(WIDTHS) * (1 if kind == "MAIN" else len(COUNTS))
                check(
                    f"{tag}: {'main window' if kind == 'MAIN' else 'Result Selection'} ({context}) -- no action label clipped "
                    f"at logical widths {WIDTHS[0]}-{WIDTHS[-1]}" + ("" if kind == "MAIN" else f", {len(COUNTS)} candidate counts"),
                    len(rows) == expected_rows and not bad,
                )
            autosolve_rows = [line for line in out.splitlines() if line.startswith("AUTOSOLVE ")]
            for line in autosolve_rows:
                if "CLIPPED" in line:
                    print("   " + line)
            check(
                f"{tag}: AutosolveWindow -- Cancel / view toolbar never clipped at logical widths "
                f"{WIDTHS[0]}-{WIDTHS[-1]}",
                len(autosolve_rows) == len(WIDTHS)
                and all("CLIPPED" not in line and "seen=6" in line for line in autosolve_rows),
            )
            review_rows = [line for line in out.splitlines() if line.startswith("REVIEW ")]
            for line in review_rows:
                if "CLIPPED" in line or "seen=9" not in line:
                    print("   " + line)
            check(
                f"{tag}: Autosolve Review -- both panels' four actions never clipped at logical widths "
                f"{WIDTHS[0]}-{WIDTHS[-1]}",
                len(review_rows) == len(WIDTHS)
                and all("CLIPPED" not in line and "seen=9" in line for line in review_rows),
            )
            labels = {line.split("label=")[1].split(" actual=")[0] for line in lines}
            check(f"{tag}: both primary labels exercised", {"'Save map and model'", "'Pass to Jana2020'"} <= labels)
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
