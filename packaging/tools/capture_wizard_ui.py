"""Capture the Phase Studio 2.0.2 Jana Wizard acceptance states."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_SCALE_FACTOR", "1.25")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QDialog

from phase_studio import requirements as reqs
from phase_studio.requirements_ui import show_requirement_remediation_dialog
from phase_studio.ui_style import apply_phase_studio_style


def main() -> int:
    app = QApplication.instance() or QApplication([sys.argv[0]])
    apply_phase_studio_style(app)
    import phase_studio.jana_superflip as js

    output = ROOT / "docs" / "screenshots" / "2.0.2-wizard"
    output.mkdir(parents=True, exist_ok=True)
    QDialog.exec = lambda self: QDialog.Rejected
    wizard = js._JanaWorkflowWizard([], None)
    wizard.run()
    wizard._adjust_dialog_size = lambda: None
    wizard._ensure_workflow_requirements = lambda **_kwargs: True
    wizard._ensure_models_loaded = lambda: None
    wizard.dialog.show()
    app.processEvents()

    def capture(name: str) -> None:
        # 820×780 logical pixels is the standardized Wizard target used on a
        # Full-HD desktop at 125% scaling. The capture host itself may expose a
        # smaller virtual screen, so render the widget at the acceptance size.
        wizard.dialog.resize(820, 780)
        app.processEvents()
        path = output / name
        if not wizard.dialog.grab().save(str(path)):
            raise RuntimeError(f"Could not save {path}")
        print(path.relative_to(ROOT))

    capture("01-workflow.png")
    wizard.scroll_area.verticalScrollBar().setValue(0)
    wizard.superflip_sharped_tile._on_click()
    wizard.model.clear()
    wizard.model.addItems(["PEAK A (model prediction)", "SEED (cyclic CF)"])
    wizard.model_catalog["values"] = (
        "PEAK A (model prediction)",
        "SEED (cyclic CF)",
    )
    wizard.model_cache["loaded"] = True
    wizard.model_catalog["provenance"] = "offline"
    wizard.restore_automatic_model_button.click()
    wizard.model_status.setText("2 models available")
    wizard.cycles.setValue(1)
    capture("02-configuration-1-cycle.png")
    wizard.cycles.setValue(5)
    capture("03-configuration-5-cycles.png")
    wizard.sharped_toggle.setChecked(True)
    capture("04-sharped-settings-expanded.png")
    wizard.sharped_toggle.setChecked(False)
    wizard.primary_button.click()
    capture("05-map-feedback.png")

    modal_target = {"path": None}

    def capture_modal(dialog):
        dialog.resize(680, 360)
        dialog.show()
        app.processEvents()
        path = modal_target["path"]
        if path is None or not dialog.grab().save(str(path)):
            raise RuntimeError(f"Could not save modal screenshot {path}")
        print(path.relative_to(ROOT))
        dialog.reject()
        return QDialog.Rejected

    QDialog.exec = capture_modal
    modal_target["path"] = output / "06-sharped-access-required.png"
    show_requirement_remediation_dialog(
        wizard.dialog,
        reqs.RequirementStatus(reqs.RequirementKind.SHARPED, reqs.RequirementState.TOKEN_MISSING),
    )
    modal_target["path"] = output / "07-edma-setup-required.png"
    show_requirement_remediation_dialog(
        wizard.dialog,
        reqs.RequirementStatus(reqs.RequirementKind.EDMA, reqs.RequirementState.NOT_CONFIGURED),
    )
    wizard.dialog.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
