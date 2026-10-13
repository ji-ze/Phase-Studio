"""Regression tests for Phase Studio's ONE element-colour authority,
app.element_color() -- a period-based, deterministic colour system:

- period of the periodic table = colour family (CIELCh hue range);
- position within the period = controlled hue offset + alternating
  lightness/chroma, so neighbours stay distinguishable.

Covers: every real element (Z 1-118) resolves to a valid colour; period
metadata; determinism; same-period elements are not identical; the required
element pairs are clearly distinguishable; readable on the white renderer
background and not near-black; unknown labels get one neutral fallback;
the Professional renderer, result-selector preview, Autosolve and its legend
all use the same authority; and no per-element colour table exists anywhere.

Plain Python test (no pytest dependency); run with
`python tests/test_element_colors.py`.
"""
import ast
import itertools
import math
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = Path(__file__).resolve().parent.parent

results_log = []

REQUIRED_PAIRS = (
    ("C", "N"), ("C", "O"), ("O", "F"), ("O", "Cl"),
    ("Si", "P"), ("Si", "S"), ("Si", "Cl"), ("P", "S"), ("P", "Cl"), ("S", "Cl"),
    ("Fe", "Co"), ("Fe", "Ni"), ("Co", "Ni"), ("Cu", "Zn"), ("Ag", "Cd"),
    ("Pt", "Au"), ("Au", "Hg"), ("Au", "S"), ("C", "Au"),
    # the collisions of the previous palettes
    ("Ag", "S"), ("O", "Au"), ("Cl", "Au"),
)
REQUIRED_PAIR_MIN_DELTA_E = 14.0
ADJACENT_MIN_DELTA_E = 10.0
MIN_CONTRAST_ON_WHITE = 2.0
MIN_LIGHTNESS = 35.0


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


def lab(hex_color):
    r, g, b = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    r, g, b = lin(r), lin(g), lin(b)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116  # noqa: E731
    return (116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))), y


def delta_e(a, b):
    return math.dist(lab(a)[0], lab(b)[0])


def contrast_on_white(color):
    return 1.05 / (lab(color)[1] + 0.05)


def main():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([sys.argv[0]])
    import gemmi
    import phase_studio.app as appmod
    import phase_studio.result_selection as result_selection
    from phase_studio.autosolve_window import AutosolveWindow

    appmod.IterativeSuperflipPipelineQtGUI.save_settings = lambda self: None
    appmod.IterativeSuperflipPipelineQtGUI.load_settings = lambda self: None
    color = appmod.element_color
    symbols = [gemmi.Element(z).name for z in range(1, 119)]

    # Every supported real element resolves to a valid, deterministic colour.
    colors = {s: color(s) for s in symbols}
    check("all 118 elements resolve to a valid #RRGGBB colour", all(re.fullmatch(r"#[0-9A-F]{6}", c) for c in colors.values()))
    check("same element -> same colour every time", all(color(s) == colors[s] for s in symbols))
    check("labels resolve through the existing element parsing (Ag12 -> Ag, ag -> Ag)", color("Ag12") == colors["Ag"] and color("ag") == colors["Ag"])
    check("no real element uses the unknown fallback", appmod.UNKNOWN_ELEMENT_COLOR not in colors.values())

    # Period metadata.
    expected_periods = {"H": 1, "He": 1, "Li": 2, "C": 2, "Ne": 2, "Na": 3, "Cl": 3, "K": 4, "Fe": 4, "Kr": 4,
                        "Rb": 5, "Ag": 5, "Xe": 5, "Cs": 6, "La": 6, "Lu": 6, "Au": 6, "Rn": 6,
                        "Fr": 7, "Ac": 7, "U": 7, "Lr": 7, "Og": 7}
    check(
        "period metadata is correct (incl. lanthanides in 6, actinides in 7)",
        all(appmod.element_period_position(gemmi.Element(s).atomic_number)[0] == p for s, p in expected_periods.items()),
    )
    check("period lengths 2/8/8/18/18/32/32", [appmod.element_period_position(z)[2] for z in (1, 3, 11, 19, 37, 55, 87)] == [2, 8, 8, 18, 18, 32, 32])
    check("Z outside 1-118 has no period", appmod.element_period_position(0) is None and appmod.element_period_position(119) is None)

    # Period families: related within, not identical.
    for period in range(1, 8):
        members = [s for s in symbols if appmod.element_period_position(gemmi.Element(s).atomic_number)[0] == period]
        check(f"period {period}: its {len(members)} elements do not all share one colour", len({colors[s] for s in members}) == len(members))
    for z in range(1, 118):
        a, b = appmod.element_period_position(z), appmod.element_period_position(z + 1)
        if a[0] == b[0]:
            if delta_e(colors[symbols[z - 1]], colors[symbols[z]]) < ADJACENT_MIN_DELTA_E:
                check(f"adjacent {symbols[z - 1]}/{symbols[z]} distinguishable", False)
    worst_adjacent = min(
        delta_e(colors[symbols[z - 1]], colors[symbols[z]]) for z in range(1, 118)
        if appmod.element_period_position(z)[0] == appmod.element_period_position(z + 1)[0]
    )
    check(f"every same-period neighbour pair differs (worst dE76 {worst_adjacent:.1f} >= {ADJACENT_MIN_DELTA_E})", worst_adjacent >= ADJACENT_MIN_DELTA_E)

    # Required element pairs.
    for a, b in REQUIRED_PAIRS:
        d = delta_e(color(a), color(b))
        check(f"{a} vs {b} clearly distinguishable (dE76 {d:.1f} >= {REQUIRED_PAIR_MIN_DELTA_E})", d >= REQUIRED_PAIR_MIN_DELTA_E)

    # Readable on the white renderer background, not near-black.
    weakest = min((contrast_on_white(c), s) for s, c in colors.items())
    darkest = min((lab(c)[0][0], s) for s, c in colors.items())
    check(f"every element is visible on white (lowest {weakest[1]} {weakest[0]:.2f}:1 >= {MIN_CONTRAST_ON_WHITE})", weakest[0] >= MIN_CONTRAST_ON_WHITE)
    check(f"no near-black atoms (darkest {darkest[1]} L* {darkest[0]:.1f} >= {MIN_LIGHTNESS})", darkest[0] >= MIN_LIGHTNESS)

    # Unknown labels: one neutral fallback, never a real element.
    unknown = [color(x) for x in ("Q", "X", "", "Zz", "?")]
    check("unknown labels -> the one neutral fallback colour", set(unknown) == {appmod.UNKNOWN_ELEMENT_COLOR})
    r, g, b = (int(appmod.UNKNOWN_ELEMENT_COLOR[i:i + 2], 16) for i in (1, 3, 5))
    check("the fallback is neutral grey", r == g == b)

    # One authority for every view and legend.
    renderer = appmod.IterativeSuperflipPipelineQtGUI()
    check("the Professional renderer delegates to element_color()", all(renderer._element_color(s) == colors[s] for s in symbols))
    check("Autosolve uses the renderer's own colour method", AutosolveWindow._element_color is appmod.IterativeSuperflipPipelineQtGUI._element_color)
    preview_host = result_selection.create_result_preview_host(renderer, None, 20.0, 35.0)
    check("the result-selector preview uses the same authority", all(preview_host._element_color(s) == colors[s] for s in ("Ag", "S", "Au", "O", "U")))
    win = AutosolveWindow(appmod.IterativeSuperflipPipelineQtGUI(), "A")
    win._set_displayed_elements(["Ag", "S", "O", "Cl", "Au", "U"])
    check("legend colour == renderer colour for every legend entry", all(c == colors[e] for e, c in win.legend_entries()))
    win.close()

    # No per-element colour table anywhere in the package.
    offenders = []
    for module in sorted((ROOT / "phase_studio").glob("*.py")):
        for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Dict) and len(node.keys) >= 5:
                keys = [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
                values = [v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str)]
                if sum(bool(re.fullmatch(r"[A-Z][a-z]?", k)) for k in keys) >= 5 and sum(bool(re.fullmatch(r"#[0-9A-Fa-f]{6}", v)) for v in values) >= 5:
                    offenders.append(f"{module.name}:{node.lineno}")
    check(f"no element->colour dictionary remains in the package ({offenders or 'none'})", offenders == [])

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
