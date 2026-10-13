"""Regression: no Jana Wizard tile text is cropped, before AND after the
deferred .inflip input-summary population, at 100/125/150% scale.

Root cause guarded here: the Wizard pins its page stack to the current
page's height; the .inflip input summary is filled in one event-loop turn
later (two-line cell, reflection counts, composition, "From .inflip" notes)
and made page 1 taller than the pinned height, so Qt squeezed the
compressible action tiles below their own minimum and cropped the glyphs of
their titles/subtitles. Each scale runs in its own child process
(QT_SCALE_FACTOR must be set before Qt starts).

Plain Python test (no pytest dependency); run with
`python tests/test_wizard_text_clipping.py`.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCALES = ("1", "1.25", "1.5")
DESCENDERS = "Typography check: pgyjq — Qypgj"


def write_inflip(directory: Path) -> Path:
    """A Jana2020-style .inflip shaped like a real job (monoclinic P21/n cell,
    explicit symmetry, composition with H, embedded amplitude block)."""
    lines = [
        "title clipping_fixture_Superflip",
        "perform CF",
        "outputfile \"clipping_fixture_Superflip.m81\" \"clipping_fixture_Superflip.m80\"",
        "outputformat jana",
        "dimension 3",
        "cell 24.3524 35.5608 26.0322 90.00 91.02 90.00",
        "spacegroup P21/n",
        "centro yes",
        "centers", "0 0 0", "endcenters",
        "symmetry", "x1 x2 x3", "-x1+1/2 x2+1/2 -x3+1/2", "-x1 -x2 -x3", "x1+1/2 -x2+1/2 x3+1/2", "endsymmetry",
        "composition Ag124 S88 B768 H704 O40",
        "dataformat amplitude",
        "fbegin",
    ]
    for h in range(1, 9):
        for k in range(0, 9):
            for l in range(0, 6):
                lines.append(f"{h} {k} {l} {10.0 + h + k + l:.2f} 1.00")
    lines.append("endf")
    path = directory / "clipping_fixture_Superflip.inflip"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


CHILD = r'''
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from PySide6.QtWidgets import QApplication, QDialog
app = QApplication([sys.argv[0]])
import phase_studio.ui_style as ui_style
ui_style.apply_phase_studio_style(app)
import phase_studio.jana_superflip as js
QDialog.exec = lambda self: QDialog.Rejected
inflip = Path(sys.argv[2])
descenders = sys.argv[3]
jana_root = inflip.parent / "Jana Active"
scientific_dir = jana_root / "SUPERFLIP"
scientific_dir.mkdir(parents=True, exist_ok=True)
(scientific_dir / "superflip.exe").write_bytes(b"active scientific Superflip")
(scientific_dir / "EDMA.exe").write_bytes(b"active EDMA")
js.application_dir = lambda: jana_root

def label_problems(tag, labels):
    out = []
    for label in labels:
        if label is None:
            continue
        need = max(label.fontMetrics().height(), label.minimumSizeHint().height())
        if label.wordWrap() and label.width() > 1:
            need = max(need, label.heightForWidth(label.width()))
        if label.height() < need:
            out.append(f"{tag}: {label.objectName()} {label.text()!r} height {label.height()} < {need}")
    return out

def tile_labels(tile):
    return [tile.title_label, tile.subtitle_label, tile.secondary_label]

def tile_problems(tag, wizard, tiles):
    out = []
    for tile in tiles:
        if tile.height() < tile.minimumSizeHint().height():
            out.append(f"{tag}: tile {tile.title_label.text()!r} squeezed {tile.height()} < {tile.minimumSizeHint().height()}")
        out += label_problems(tag, tile_labels(tile))
    return out

w = js._JanaWorkflowWizard([str(inflip)], inflip)
w.run()
w.dialog.show()
app.processEvents()
problems = []
main_tiles = (w.original_superflip_tile, w.superflip_sharped_tile, w.autosolve_tile, w.professional_mode_tile)
problems += tile_problems("initial page", w, main_tiles)
for _ in range(30):
    app.processEvents()
populated = w.reflections_value.text() != "Not available"
problems += tile_problems("populated page", w, main_tiles)
problems += label_problems("populated input summary", [w.reflections_value, w.format_value, w.cell_value, w.spacegroup_value, w.composition_value])
# Descenders: set real descender-heavy text, re-fit, nothing may crop.
for tile in main_tiles:
    tile.subtitle_label.setText(descenders)
    tile.title_label.setText("Typography pgyjq")
for _ in range(5):
    app.processEvents()
w._adjust_dialog_size()
for _ in range(5):
    app.processEvents()
problems += tile_problems("descenders", w, main_tiles)
geometry_equal = (
    w.autosolve_tile.height() == w.professional_mode_tile.height()
    and abs(w.autosolve_tile.width() - w.professional_mode_tile.width()) <= 1
    and w.autosolve_tile.title_label.geometry().topLeft() == w.professional_mode_tile.title_label.geometry().topLeft()
    and w.autosolve_tile.subtitle_label.geometry().topLeft() == w.professional_mode_tile.subtitle_label.geometry().topLeft()
    and w.autosolve_tile.icon_label.geometry().topLeft() == w.professional_mode_tile.icon_label.geometry().topLeft()
    and abs(w.autosolve_tile.chevron_label.geometry().center().y() - w.professional_mode_tile.chevron_label.geometry().center().y()) <= 1
)
w.superflip_sharped_tile._on_click()
w.primary_button.click()
for _ in range(10):
    app.processEvents()
direct_map_feedback = w.stack.currentWidget() is w.page3 and not hasattr(w, "page_autosolve")
icons_visible = all(t.icon_label.pixmap() is not None and not t.icon_label.pixmap().isNull() for t in main_tiles)
print("POPULATED", populated)
print("MAIN_EQUAL", geometry_equal)
print("DIRECT_MAP_FEEDBACK", direct_map_feedback)
print("ICONS", icons_visible)
for p in problems:
    print("PROBLEM", p)
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
    with tempfile.TemporaryDirectory() as directory:
        inflip = write_inflip(Path(directory))
        child = Path(directory) / "child.py"
        child.write_text(CHILD, encoding="utf-8")
        for scale in SCALES:
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR=scale, PYTHONIOENCODING="utf-8")
            if os.name == "nt":
                env.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
            done = subprocess.run(
                [sys.executable, str(child), str(ROOT), str(inflip), DESCENDERS],
                capture_output=True, text=True, encoding="utf-8", env=env, timeout=300,
            )
            out = done.stdout
            tag = f"{float(scale) * 100:.0f}%"
            check(f"{tag}: child ran to completion", "DONE" in out)
            if "DONE" not in out:
                print(done.stderr[-2000:])
                continue
            check(f"{tag}: the .inflip input summary was really populated", "POPULATED True" in out)
            problems = [line for line in out.splitlines() if line.startswith("PROBLEM")]
            for line in problems:
                print("   " + line)
            check(f"{tag}: no tile or input-summary text cropped (initial, populated, descenders)", not problems)
            check(f"{tag}: the two badged main tiles have identical height, icon, title, subtitle and chevron geometry", "MAIN_EQUAL True" in out)
            check(f"{tag}: recommended configuration routes directly to Map Feedback", "DIRECT_MAP_FEEDBACK True" in out)
            check(f"{tag}: all four workflow tile icons are visible", "ICONS True" in out)
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
