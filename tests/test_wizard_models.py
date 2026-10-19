"""Regression tests for the Jana2020 Wizard's SharpED model list.

Plain Python test (no pytest dependency; run with
`python tests/test_wizard_models.py`), following this project's usual
checks-list-plus-exit-code convention.

Real Jana2020 testing showed the SharpED pages opening on

    Model: default
    Model list not loaded.

with the user expected to find and press "Refresh models" before they could
choose anything. The list is now fetched automatically when a page that needs
SharpED is entered, asynchronously (the existing worker thread + poll timer,
not a second API implementation), and cached for the Wizard session.

The SharpED server is never contacted here: SharpEDServerClient.get_models is
replaced with a counting stub, so these tests also prove how many requests are
actually made.
"""
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

results_log = []


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


class _Models:
    def __init__(self, models, default_model):
        self.models = list(models)
        self.default_model = default_model
        self.status = "server"


def pump(app, wizard, seconds=3.0):
    """Let the worker thread finish and the poll timer deliver its result."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        try:
            wizard.refresh_timer.timeout.emit()
        except Exception:
            pass
        if not wizard.model_cache["inflight"]:
            break
        time.sleep(0.02)
    app.processEvents()


def main():
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QDialog

    app = QApplication.instance() or QApplication([sys.argv[0]])
    import phase_studio.ui_style as ui_style

    ui_style.apply_phase_studio_style(app)
    import phase_studio.jana_superflip as js

    QDialog.exec = lambda self: QDialog.Rejected
    QSettings("PhaseStudio", "JanaSuperflipWrapper").clear()

    calls = {"n": 0, "fail": False, "models": [
        "PEAK A (model prediction)", "UNIVERSAL", "SEED (cyclic CF)",
        "PEAK B (model prediction)",
    ]}

    def fake_get_models(self, *args, **kwargs):
        calls["n"] += 1
        if calls["fail"]:
            raise RuntimeError("synthetic server failure")
        return _Models(calls["models"], "UNIVERSAL")

    js.SharpEDServerClient.get_models = fake_get_models

    def build(workflow):
        wizard = js._JanaWorkflowWizard([], None)
        wizard.run()
        wizard.workflow_state["key"] = workflow
        wizard._workflow_changed()
        app.processEvents()
        return wizard

    # =====================================================================
    # Superflip only must not contact the SharpED server
    # =====================================================================
    calls["n"] = 0
    wizard = build(js.WORKFLOW_SUPERFLIP_ONLY)
    wizard._ensure_models_loaded()
    pump(app, wizard, seconds=0.5)
    check("Superflip only: no model request is made", calls["n"] == 0)

    # =====================================================================
    # Superflip + SharpED: exactly one automatic request
    # =====================================================================
    calls["n"] = 0
    wizard = build(js.WORKFLOW_SUPERFLIP_SHARPED)
    wizard.dialog.show()
    app.processEvents()
    check("SharpED configuration form uses the available page width",
          wizard.model.width() >= int(wizard.page2.width() * 0.50))
    check("SharpED model selector has a readable responsive maximum width",
          240 <= wizard.model.minimumWidth() <= wizard.model.maximumWidth() <= 420)
    check("cycle control has a practical responsive width",
          110 <= wizard.cycles.width() <= 140)
    check("cycle control uses the compact 110 px width",
          wizard.cycles.minimumWidth() == 110 and wizard.cycles.maximumWidth() == 110)
    wizard._ensure_models_loaded()
    pump(app, wizard)
    check("Superflip + SharpED: models are fetched automatically", calls["n"] == 1)
    check("Superflip + SharpED: the list is populated", wizard.model.count() >= 4)
    check("model dropdown is capped to a compact scrolling list",
          wizard.model.maxVisibleItems() == 8)
    status = wizard.model_status.text()
    check(
        "Superflip + SharpED: 'Model list not loaded.' is gone",
        "not loaded" not in status,
    )
    check(
        "Superflip + SharpED: the count is reported",
        "4 models available" in status,
    )
    check(
        "Superflip + SharpED: server-default presentation is hidden",
        "server default" not in status.lower(),
    )
    check("five cycles auto-select the canonical multi-cycle recommendation",
          wizard.model.currentText() == "SEED (cyclic CF)")
    wizard.cycles.setValue(2)
    check("two cycles select the iterative policy model",
          wizard.model.currentText() == "SEED (cyclic CF)")
    wizard.cycles.setValue(1)
    check("one cycle auto-selects the canonical one-cycle recommendation",
          wizard.model.currentText() == "PEAK A (model prediction)")
    check("one-cycle helper describes automatic selection without duplicating the model",
          wizard.model_recommendation.text() ==
          "Automatically selected for 1 cycle")
    wizard.cycles.setValue(5)
    check("returning to multiple cycles restores its recommendation while unlocked",
          wizard.model.currentText() == "SEED (cyclic CF)")
    check("multi-cycle helper describes automatic selection without duplicating the model",
          wizard.model_recommendation.text() ==
          "Automatically selected for 5 cycles")
    check(
        "Refresh models stays available as an explicit manual control",
        wizard.refresh_models_button.isEnabled(),
    )
    wizard._go_to_map_feedback()
    wizard.cycles.setValue(5)
    wizard.missing_enabled_checkbox.setChecked(True)
    wizard.missing_start_cycle_spin.setValue(3)
    wizard.cycles.setValue(1)
    check("one-cycle Map Feedback is marked inapplicable and editing is disabled",
          wizard.feedback_applicability_note.isVisible()
          and not wizard.missing_enabled_checkbox.isEnabled()
          and not wizard.missing_start_cycle_spin.isEnabled())
    check("one-cycle Map Feedback preserves the previously entered start cycle",
          wizard.missing_start_cycle_spin.value() == 3)
    wizard.cycles.setValue(5)
    check("multi-cycle Map Feedback restores editing and enforces N-1",
          wizard.missing_enabled_checkbox.isEnabled()
          and wizard.missing_start_cycle_spin.isEnabled()
          and wizard.missing_start_cycle_spin.maximum() == 4
          and wizard.missing_start_cycle_spin.value() == 3)

    # --- caching: re-entering the page must not re-query ---
    wizard._ensure_models_loaded()
    pump(app, wizard, seconds=0.4)
    check("a cached list is reused on re-entry (Back/Next)", calls["n"] == 1)

    # --- an explicit user choice survives a later refresh ---
    wizard.model.setCurrentText("UNIVERSAL")
    wizard.model.activated.emit(wizard.model.currentIndex())
    wizard.cycles.setValue(1)
    check("a manual model selection survives later cycle changes",
          wizard.model.currentText() == "UNIVERSAL")
    wizard.refresh_models_button.click()
    pump(app, wizard)
    check("manual Refresh models performs a new request", calls["n"] == 2)
    check(
        "an explicit model choice is preserved across a refresh",
        wizard.model.currentText() == "UNIVERSAL",
    )
    check("manual selection exposes a restore action", not wizard.manual_model_row.isHidden())
    wizard.restore_automatic_model_button.click()
    check("automatic selection hides manual status", wizard.manual_model_row.isHidden())
    check("explicit automatic-mode restore reapplies the cycle policy",
          wizard.model.currentText() == "PEAK A (model prediction)")

    # --- the hidden compatibility field cannot redirect normal Wizard traffic ---
    wizard.server_url.setText("https://another.example.invalid")
    wizard._ensure_models_loaded()
    pump(app, wizard)
    check("normal Wizard traffic remains fixed to one server authority", calls["n"] == 2)

    # A removed manual choice requires an explicit replacement or restore.
    wizard.model.setCurrentText("PEAK B (model prediction)")
    wizard.model.activated.emit(wizard.model.currentIndex())
    calls["models"] = ["PEAK A (model prediction)", "UNIVERSAL", "SEED (cyclic CF)"]
    wizard.refresh_models_button.click()
    pump(app, wizard)
    check("an unavailable manual override never substitutes another model",
          wizard.model_user_picked["value"] and wizard.model.currentIndex() == -1)
    check("manual-removal warning is explicit",
          "no longer available" in wizard.model_status.text())
    check("manual-removal blocks execution until explicitly resolved", bool(wizard.model_policy_error))
    wizard.restore_automatic_model_button.click()
    check("explicit restore resolves missing manual selection", wizard.model.currentText()=='PEAK A (model prediction)' and not wizard.model_policy_error)

    # A required policy model may never fall back to the server default.
    calls["models"] = ["UNIVERSAL", "SEED (cyclic CF)", "PEAK B (model prediction)"]
    wizard.refresh_models_button.click()
    pump(app, wizard)
    check("missing one-cycle policy model leaves no substituted selection",
          wizard.model.currentIndex() == -1)
    check("missing one-cycle policy model is a blocking policy error",
          "PEAK A (model prediction)" in wizard.model_policy_error)
    calls["models"] = [
        "PEAK A (model prediction)", "UNIVERSAL", "SEED (cyclic CF)",
        "PEAK B (model prediction)",
    ]

    # =====================================================================
    # Phase recycling: exactly one automatic request
    # =====================================================================
    calls["n"] = 0
    wizard = build(js.WORKFLOW_PHASE_RECYCLING)
    wizard._ensure_models_loaded()
    pump(app, wizard)
    check("Phase recycling: models are fetched automatically", calls["n"] == 1)
    check(
        "Phase recycling: the server default remains out of normal presentation",
        "server default" not in wizard.model_status.text().lower(),
    )
    wizard._ensure_models_loaded()
    pump(app, wizard, seconds=0.4)
    check("Phase recycling: the cached list is reused", calls["n"] == 1)

    # =====================================================================
    # Failure is concise and recoverable
    # =====================================================================
    calls["n"] = 0
    calls["fail"] = True
    wizard = build(js.WORKFLOW_SUPERFLIP_SHARPED)
    wizard._ensure_models_loaded()
    pump(app, wizard)
    status = wizard.model_status.text()
    check("a failed model request is reported", calls["n"] == 1)
    check(
        "the failure state is concise and names the retry",
        "unavailable" in status.lower() and "refresh" in status.lower(),
    )
    check(
        "Refresh models is still available after a failure",
        wizard.refresh_models_button.isEnabled(),
    )
    check(
        "a failed catalog cannot be bypassed with an unverified model name",
        not wizard.model.isEditable(),
    )
    calls["fail"] = False

    import tempfile
    settings_dir = tempfile.TemporaryDirectory()
    original_imports = js._qt_imports
    def fixture_imports():
        qt = original_imports()
        qt["QSettings"] = lambda _organization, application: QSettings(
            str(Path(settings_dir.name) / (application + ".ini")), QSettings.IniFormat,
        )
        return qt
    js._qt_imports = fixture_imports
    settings = QSettings(str(Path(settings_dir.name) / "JanaSuperflipWrapper.ini"), QSettings.IniFormat)
    settings.setValue("model", "UNIVERSAL")
    settings.remove("model_selection_mode")
    wizard = build(js.WORKFLOW_SUPERFLIP_SHARPED)
    wizard._ensure_models_loaded()
    pump(app, wizard)
    check("legacy model text alone does not establish a manual preference",
          not wizard.model_user_picked["value"])
    check("programmatic catalogue population remains automatic",
          wizard.manual_model_row.isHidden())
    settings.setValue("model_selection_mode", "manual")
    settings.setValue("model", "UNIVERSAL")
    wizard = build(js.WORKFLOW_SUPERFLIP_SHARPED)
    wizard._ensure_models_loaded()
    pump(app, wizard)
    check("explicit valid saved manual preference is restored",
          wizard.model_user_picked["value"] and wizard.model.currentText() == "UNIVERSAL")
    settings.setValue("model", "REMOVED MODEL")
    wizard = build(js.WORKFLOW_SUPERFLIP_SHARPED)
    wizard._ensure_models_loaded()
    pump(app, wizard)
    check("invalid saved manual preference requires an explicit replacement",
          wizard.model_user_picked["value"] and wizard.model.currentIndex() == -1 and bool(wizard.model_policy_error))
    settings.clear()
    js._qt_imports = original_imports
    settings_dir.cleanup()

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
