"""Items 26-27 (verify-only, accepted as-is): the measured-data correction
confirmation dialog and the Predicted-structure SharpED warning at
100/125/150% scale. No scientific behavior is exercised here -- only that
neither piece of UI clips, overlaps, or duplicates itself as the OS text
scale changes.

Plain Python test (no pytest dependency); run with
`python tests/test_correction_dialog_scaling.py`.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCALES = ("1", "1.25", "1.5")

CHILD = r'''
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication([sys.argv[0]])
import phase_studio.ui_style as ui_style
ui_style.apply_phase_studio_style(app)
import phase_studio.app as appmod
import phase_studio.autosolve_review as guided
from phase_studio.autosolve_window import AutosolveWindow
from phase_studio.map_quality import ValidationProfile

appmod.IterativeSuperflipPipelineQtGUI.save_settings = lambda self: None
appmod.IterativeSuperflipPipelineQtGUI.load_settings = lambda self: None

tmp = Path(tempfile.mkdtemp())
CIF = """data_test
_cell_length_a 10.0
_cell_length_b 10.0
_cell_length_c 10.0
_cell_angle_alpha 90.0
_cell_angle_beta 90.0
_cell_angle_gamma 90.0
_space_group_name_H-M_alt 'P 1'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
C1 C 0.50 0.50 0.50
O1 O 0.56 0.50 0.50
"""

def model(name):
    p = tmp / name
    p.write_text(CIF, encoding="utf-8")
    return p

def map_file(name):
    p = tmp / name
    p.write_text("real existing map", encoding="utf-8")
    return p

backend = appmod.IterativeSuperflipPipelineQtGUI()
backend.current_validation_profile = ValidationProfile.REFERENCE_AND_HOLDOUT
backend.autosolve_panels = {
    "observed": guided.ReviewPanel(role="observed", cycle=4, map_path=map_file("obs.xplor"),
                                    current_cif=model("obs.cif"), threshold_sigma=1.0),
    "predicted": guided.ReviewPanel(role="predicted", cycle=4, map_path=map_file("pred.xplor"),
                                     current_cif=model("pred.cif"), threshold_sigma=1.0),
}
backend._autosolve_stage = guided.STAGE_REVIEW
backend._run_status = "REVIEW"
backend.autosolve_correction_plan = lambda: (guided.CORRECTION_INTENSITY, "")

aw = AutosolveWindow(backend, "A")
aw.resize(1366, 860)
aw.show()
app.processEvents()
aw._refresh_tick()
app.processEvents()

problems = []

def need_height(label):
    need = max(label.fontMetrics().height(), label.minimumSizeHint().height())
    if label.wordWrap() and label.width() > 1:
        need = max(need, label.heightForWidth(label.width()))
    return need

warning = aw.review_columns["predicted"]["warning"]
if not warning.isVisible():
    problems.append("Predicted-structure SharpED warning is not visible in Final Review")
if warning.width() > aw.review_columns["predicted"]["column"].width():
    problems.append("Predicted-structure SharpED warning overflows its own panel width")
if warning.height() < need_height(warning):
    problems.append(f"Predicted-structure SharpED warning clipped: height {warning.height()} < {need_height(warning)}")
if "SharpED" not in warning.text() or "original measured diffraction data" not in warning.text() or "independent crystallographic refinement" not in warning.text():
    problems.append(f"Predicted-structure SharpED warning text unexpected: {warning.text()!r}")

observed_warning = aw.review_columns["observed"]["warning"]
if observed_warning.isVisible() and "SharpED" in observed_warning.text():
    problems.append("the SharpED warning duplicated onto the Observed-data panel")

shown_boxes = []

def fake_exec(box):
    shown_boxes.append(box)
    return 0

QMessageBox.exec = fake_exec
aw.correction_buttons["intensity"].click()
app.processEvents()
if not shown_boxes:
    problems.append("clicking 'Correct suspect intensities' did not open the confirmation dialog")
else:
    box = shown_boxes[0]
    box.show()
    app.processEvents()
    text_label = box.findChild(type(warning))
    if text_label is not None and text_label.wordWrap() and text_label.width() > 1:
        if text_label.height() < need_height(text_label):
            problems.append(f"correction dialog text clipped: height {text_label.height()} < {need_height(text_label)}")
    buttons = box.buttons()
    if len(buttons) != 2:
        problems.append(f"correction dialog has {len(buttons)} buttons, expected 2")
    else:
        texts = [b.text() for b in buttons]
        if "Cancel" not in texts or "Correct intensities" not in texts:
            problems.append(f"correction dialog button texts unexpected: {texts!r}")
        xs = [b.mapTo(box, b.rect().topLeft()).x() for b in buttons]
        widths = [b.width() for b in buttons]
        left, right = sorted(zip(xs, widths), key=lambda p: p[0])
        if left[0] + left[1] > right[0] + 1:
            problems.append(f"correction dialog buttons overlap: {list(zip(texts, xs, widths))}")
    if "SharpED" in box.text():
        problems.append("the SharpED warning duplicated into the correction confirmation dialog")
    screen = app.primaryScreen()
    avail = screen.availableGeometry() if screen is not None else None
    box_geo = box.frameGeometry()
    if avail is not None and (box_geo.width() > avail.width() or box_geo.height() > avail.height()):
        problems.append(f"correction dialog ({box_geo.width()}x{box_geo.height()}) exceeds the available screen ({avail.width()}x{avail.height()})")

for p in problems:
    print("PROBLEM", p)
print("DONE")
'''

results_log = []


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


def main():
    with tempfile.TemporaryDirectory() as directory:
        child = Path(directory) / "child.py"
        child.write_text(CHILD, encoding="utf-8")
        for scale in SCALES:
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR=scale, PYTHONIOENCODING="utf-8")
            if os.name == "nt":
                env.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
            done = subprocess.run(
                [sys.executable, str(child), str(ROOT)],
                capture_output=True, text=True, encoding="utf-8", env=env, timeout=120,
            )
            out = done.stdout
            tag = f"{float(scale) * 100:.0f}%"
            check(f"{tag}: child ran to completion", "DONE" in out)
            if "DONE" not in out:
                print(done.stderr[-2000:])
                continue
            problems = [line for line in out.splitlines() if line.startswith("PROBLEM")]
            for line in problems:
                print("   " + line)
            check(
                f"{tag}: correction dialog and Predicted-structure warning are not clipped, "
                "not duplicated, and stay on-screen",
                not problems,
            )
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
