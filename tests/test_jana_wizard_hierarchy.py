"""Regression checks for the Phase Studio 2.0.2 Jana Wizard hierarchy."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

results_log = []


def check(name, condition):
    results_log.append((name, bool(condition)))
    print(("PASS" if condition else "FAIL") + " - " + name)


def _tile_title_text(tile) -> str:
    from PySide6.QtWidgets import QLabel

    for label in tile.findChildren(QLabel):
        if label.objectName() == "actionTileTitle":
            return label.text()
    return ""


def main():
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QDialog, QPushButton

    settings_dir = tempfile.TemporaryDirectory()
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, settings_dir.name)

    app = QApplication.instance() or QApplication([sys.argv[0]])
    import phase_studio.ui_style as ui_style

    ui_style.apply_phase_studio_style(app)
    import phase_studio.jana_superflip as js

    QDialog.exec = lambda self: QDialog.Rejected

    def build():
        wizard = js._JanaWorkflowWizard([], None)
        wizard.run()
        wizard._ensure_workflow_requirements = lambda **_kwargs: True
        wizard._ensure_models_loaded = lambda: None
        wizard.model_cache["loaded"] = True
        wizard.dialog.show()
        app.processEvents()
        return wizard

    wizard = build()
    check("landing page contains all four workflow tiles", all(
        wizard.page1.isAncestorOf(tile) for tile in (
            wizard.original_superflip_tile, wizard.superflip_sharped_tile,
            wizard.autosolve_tile, wizard.professional_mode_tile,
        )
    ))
    check("workflow titles match the 2.0.2 contract", [
        _tile_title_text(wizard.original_superflip_tile),
        _tile_title_text(wizard.superflip_sharped_tile),
        _tile_title_text(wizard.autosolve_tile),
    ] == ["Superflip only", "Superflip + SharpED", "SharpED Autosolve"])
    check("recommended workflow is visibly badged", wizard.superflip_sharped_tile.secondary_label.text() == "Recommended")
    check("Autosolve is visibly experimental", wizard.autosolve_tile.secondary_label.text() == "Experimental")
    check("primary workflows are marked as the primary tier", all(
        tile.property("workflowTier") == "primary"
        for tile in (wizard.original_superflip_tile, wizard.superflip_sharped_tile)
    ))
    check("Autosolve and Professional mode are equal secondary tiles", all(
        tile.property("workflowTier") == "secondary"
        for tile in (wizard.autosolve_tile, wizard.professional_mode_tile)
    ) and wizard.autosolve_tile.width() == wizard.professional_mode_tile.width()
      and wizard.autosolve_tile.height() == wizard.professional_mode_tile.height())
    check("Professional mode explains its full expert scope",
          wizard.professional_mode_tile.subtitle_label.text() ==
          "Advanced control of Superflip, SharpED and EDMA")
    check("Advanced entry is absent", not hasattr(wizard, "advanced_button"))
    check("Open full configuration is absent", not any(
        button.text() == "Open full configuration" for button in wizard.dialog.findChildren(QPushButton)
    ))
    check("landing page has no redundant primary footer action", not wizard.primary_button.isVisible())

    wizard = build()
    wizard.original_superflip_tile._on_click()
    check("Superflip only starts directly", wizard.result["action"] == "run")

    wizard = build()
    wizard.professional_mode_button.click()
    check("Professional mode opens the full configuration", wizard.result["action"] == "edit")

    wizard = build()
    wizard.superflip_sharped_tile._on_click()
    check("recommended workflow opens its configuration", wizard.stack.currentWidget() is wizard.page2)
    check("recommended workflow defaults to five cycles", wizard.cycles.value() == 5)
    check("cycle guidance describes the selected count's runtime tradeoff",
          'Additional cycles increase processing time and may improve' in wizard.cycles_recommendation.text())
    check("multi-cycle automatic guidance retains the canonical effective model",
          wizard.model_recommendation.text() ==
          "Automatically selected for 5 cycles"
          and wizard.model.currentText() == "SEED (cyclic CF)"
          and not wizard.model_user_picked["value"])
    check("SharpED model choice is a non-editable catalog selector", not wizard.model.isEditable())
    wizard.primary_button.click()
    check("recommended workflow advances directly to Map Feedback", wizard.stack.currentWidget() is wizard.page3)
    check("recommended workflow has no obsolete objective page", not hasattr(wizard, "page_autosolve"))
    wizard.primary_button.click()
    check("recommended workflow dispatches through the ordinary multi-cycle path", wizard.result["action"] == "recycle")

    wizard = build()
    wizard.autosolve_tile._on_click()
    check("Autosolve starts directly without a pre-run goal page", wizard.result["action"] == "autosolve")

    failures = [name for name, ok in results_log if not ok]
    print()
    if failures:
        print(f"{len(failures)} of {len(results_log)} checks FAILED:")
        for failure in failures:
            print("  - " + failure)
        return 1
    print(f"All {len(results_log)} checks passed.")
    settings_dir.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
