"""Regression tests for 2.0.2 user-facing copy: the Wizard hierarchy,
removed objective page, Autosolve handoff wording, and handoff-map tooltips.

Two layers:
  * a static scan of every non-docstring string constant in phase_studio/
    for retired phrases ("previous expert workflows", "Option A/B",
    "with no further input", "Pass to Jana2020 now", "pipeline");
  * the live Wizard pages, whose visible texts are compared exactly.

Plain Python test (no pytest dependency); run with
`python tests/test_ui_copy.py`.
"""
import ast
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

results_log = []

RETIRED_PHRASES = (
    ("previous expert workflows", re.compile(r"previous expert", re.I)),
    ("Option A / Option B", re.compile(r"\bOption [AB]\b|\bOption \{")),
    ("with no further input", re.compile(r"no further input", re.I)),
    ("Pass to Jana2020 now", re.compile(r"Pass to Jana2020 now")),
    ("pipeline", re.compile(r"\bpipeline\b", re.I)),
)

PHASE_RECYCLING_DESCRIPTION = (
    "Iterate Superflip and SharpED over multiple cycles while keeping user control over "
    "the initial model, Map Feedback and the map passed to Jana2020."
)
def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


def user_string_constants():
    """(file, line, text) for every string constant that is not a
    docstring. f-string literal parts are included; comments are not
    constants and so are never scanned."""
    found = []
    for path in sorted((ROOT / "phase_studio").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                    docstrings.add(id(first.value))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                found.append((path.name, node.lineno, node.value))
    return found


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    # =====================================================================
    # Static: no retired phrase survives in any user-reachable string.
    # =====================================================================
    constants = user_string_constants()
    check("the static scan found the package's string constants", len(constants) > 1000)
    for label, pattern in RETIRED_PHRASES:
        hits = [f"{name}:{line}" for name, line, text in constants if pattern.search(text)]
        check(f"no user-facing string contains '{label}'" + (f" (found at {', '.join(hits[:5])})" if hits else ""), not hits)

    from PySide6.QtWidgets import QApplication, QDialog, QLabel, QWidget

    app = QApplication.instance() or QApplication([sys.argv[0]])
    import phase_studio.ui_style as ui_style

    ui_style.apply_phase_studio_style(app)
    import phase_studio.jana_superflip as js

    QDialog.exec = lambda self: QDialog.Rejected

    check("phase-recycling card description states the difference from Autosolve exactly",
          js.WORKFLOW_DESCRIPTIONS[js.WORKFLOW_PHASE_RECYCLING] == PHASE_RECYCLING_DESCRIPTION)
    check("phase-recycling card description does not mention the specialized sharped_recycle mode",
          "recycle" not in js.WORKFLOW_DESCRIPTIONS[js.WORKFLOW_PHASE_RECYCLING].replace("recycling", ""))
    check("the obsolete objective-state authority is removed",
          not hasattr(js, "AUTOSOLVE_GOAL_LABELS"))

    def build():
        wizard = js._JanaWorkflowWizard([], None)
        wizard.run()
        wizard._ensure_workflow_requirements = lambda **_kwargs: True
        wizard.dialog.show()
        app.processEvents()
        return wizard

    def visible_texts(root: QWidget):
        return [label.text() for label in root.findChildren(QLabel) if label.isVisibleTo(root) and label.text()]

    # =====================================================================
    # 2.0.2 landing page: two primary and two secondary workflows.
    # =====================================================================
    wizard = build()
    app.processEvents()
    page_texts = visible_texts(wizard.page1)
    check("landing page names all four workflows",
          all(text in " ".join(page_texts) for text in (
              "Superflip only", "Superflip + SharpED", "SharpED Autosolve", "Professional mode",
          )))
    all_texts = " ".join(visible_texts(wizard.dialog))
    check("no visible Advanced entry remains", "Advanced" not in all_texts)
    check("Professional mode is a complete secondary expert tile",
          wizard.professional_mode_tile.title_label.text() == "Professional mode"
          and "Superflip, SharpED, and EDMA" in wizard.professional_mode_tile.subtitle_label.text())

    # Handoff-map radios: tooltips describe what the choice really does.
    for radio in (wizard.sharped_map_radio, wizard.superflip_map_radio):
        tip = radio.toolTip()
        check(f"'{radio.text()}' tooltip: names Result Selection and the Jana2020 handoff",
              "Result Selection" in tip and "Jana2020 handoff" in tip)
        check(f"'{radio.text()}' tooltip: states the next cycle is initialized from the SharpED map",
              "initialized from the SharpED map" in tip)
    wizard.dialog.close()

    # =====================================================================
    # Recommended workflow routes directly from configuration to Map Feedback.
    # =====================================================================
    wizard = build()
    wizard.superflip_sharped_tile._on_click()
    wizard.primary_button.click()
    app.processEvents()
    check("configuration Next opens Map Feedback directly", wizard.stack.currentWidget() is wizard.page3)
    check("no objective page or objective widgets remain", all(not hasattr(wizard, name) for name in (
        "page_autosolve", "autosolve_option_a_tile", "autosolve_option_b_tile", "autosolve_state",
    )))
    joined = " ".join(visible_texts(wizard.dialog))
    check("removed objective copy is absent",
          "Solve the phase problem" not in joined and "Predict the structure model" not in joined)
    wizard.dialog.close()

    wizard = build()
    wizard.autosolve_tile._on_click()
    check("SharpED Autosolve starts without showing the objective page",
          wizard.result["action"] == "autosolve" and wizard.stack.currentWidget() is wizard.page1)
    wizard.dialog.close()

    # =====================================================================
    # Autosolve launch log: the handoff contract is Result Selection, not
    # an unattended handoff.
    # =====================================================================
    source = (ROOT / "phase_studio" / "jana_superflip.py").read_text(encoding="utf-8")
    block = source[source.index("def launch_autosolve_from_jana"):]
    block = block[:block.index("\ndef ", 1)]
    check("Autosolve launch log names the shared phase search and its exact SharpED model",
          "the shared phase search " in block and "(Superflip + SharpED '{PHASE_SEARCH_MODEL}')" in block)
    check("Autosolve launch log describes the Model prediction and Review (no unattended handoff)",
          "a Model prediction is generated from the best" in block and "Review opens" in block
          and "the result you choose to Jana2020" in block)

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
