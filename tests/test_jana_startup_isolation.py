"""Jana Wizard must not construct or show Professional mode implicitly."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QDialog
    from phase_studio import app as appmod
    from phase_studio import jana_superflip as js
    from phase_studio.ui_style import apply_phase_studio_style

    settings_dir = tempfile.TemporaryDirectory()
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, settings_dir.name)
    imports = js._qt_imports
    js._qt_imports = lambda: imports() | {'QSettings': lambda org, name:
        QSettings(str(Path(settings_dir.name)/(name+'.ini')), QSettings.IniFormat)}
    app = QApplication.instance() or QApplication([sys.argv[0]])
    apply_phase_studio_style(app)
    original_dialog_exec = QDialog.exec
    QDialog.exec = lambda self: QDialog.Rejected
    checks = 0

    def check(label: str, condition: bool) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            raise AssertionError(label)

    constructed = []
    original_init = appmod.IterativeSuperflipPipelineQtGUI.__init__

    def counted_init(self, *args, **kwargs):
        constructed.append(self)
        original_init(self, *args, **kwargs)

    appmod.IterativeSuperflipPipelineQtGUI.__init__ = counted_init
    try:
        # Three complete cold Wizard constructions catch accumulated delayed
        # callbacks and stale top-level windows in the same process.
        for iteration in range(3):
            wizard = js._JanaWorkflowWizard([], None)
            wizard.run()
            wizard.dialog.show()
            app.processEvents()
            check(f"launch {iteration + 1}: Jana Wizard is visible", wizard.dialog.isVisible())
            check(f"launch {iteration + 1}: Professional backend was not constructed", not constructed and wizard.backing_window_holder["win"] is None)
            check(f"launch {iteration + 1}: no Professional top-level exists", not any(
                isinstance(widget, appmod.IterativeSuperflipPipelineQtGUI)
                for widget in QApplication.topLevelWidgets()
            ))
            wizard.dialog.activateWindow()
            app.processEvents()
            check(f"launch {iteration + 1}: focus change does not create Professional mode", not constructed)
            wizard.dialog.reject()
            wizard.dialog.close()
            wizard.dialog.deleteLater()
            app.processEvents()

        wizard = js._JanaWorkflowWizard([], None)
        wizard.run()
        wizard._ensure_workflow_requirements = lambda **_kwargs: True
        wizard._ensure_models_loaded = lambda: None
        wizard.model_cache["loaded"] = True
        wizard.model_catalog["provenance"] = "offline"
        wizard.superflip_sharped_tile._on_click()
        app.processEvents()
        check("Superflip + SharpED configuration does not construct Professional mode", not constructed)
        wizard.primary_button.click()
        app.processEvents()
        check("Map Feedback transition does not construct Professional mode", not constructed)
        wizard.dialog.reject()
        wizard.dialog.close()

        for tile_name in ("original_superflip_tile", "autosolve_tile"):
            wizard = js._JanaWorkflowWizard([], None)
            wizard.run()
            wizard._ensure_workflow_requirements = lambda **_kwargs: True
            getattr(wizard, tile_name)._on_click()
            app.processEvents()
            check(f"{tile_name}: direct dispatch does not construct Professional mode", not constructed)
            wizard.dialog.close()

        wizard = js._JanaWorkflowWizard([], None)
        wizard.run()
        wizard.professional_mode_tile._on_click()
        check("Professional selection is explicit before the full GUI route is entered", wizard.result["action"] == "edit" and not constructed)
        wizard.dialog.close()
    finally:
        appmod.IterativeSuperflipPipelineQtGUI.__init__ = original_init
        QDialog.exec = original_dialog_exec
        settings_dir.cleanup()

    print(f"Jana startup isolation checks passed: {checks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
