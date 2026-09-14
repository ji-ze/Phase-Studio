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
    from PySide6.QtWidgets import QApplication, QDialog

    app = QApplication.instance() or QApplication([sys.argv[0]])
    import phase_studio.ui_style as ui_style

    ui_style.apply_phase_studio_style(app)
    import phase_studio.jana_superflip as js

    QDialog.exec = lambda self: QDialog.Rejected

    calls = {"n": 0, "fail": False}

    def fake_get_models(self, *args, **kwargs):
        calls["n"] += 1
        if calls["fail"]:
            raise RuntimeError("synthetic server failure")
        return _Models(["koala 2.0", "wombat 1.4", "emu 0.9"], "koala 2.0")

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
    wizard._ensure_models_loaded()
    pump(app, wizard)
    check("Superflip + SharpED: models are fetched automatically", calls["n"] == 1)
    check("Superflip + SharpED: the list is populated", wizard.model.count() >= 4)
    status = wizard.model_status.text()
    check(
        "Superflip + SharpED: 'Model list not loaded.' is gone",
        "not loaded" not in status,
    )
    check(
        "Superflip + SharpED: the count is reported",
        "3 models available" in status,
    )
    check(
        "Superflip + SharpED: the resolved server default is shown",
        "server default: koala 2.0" in status,
    )
    check(
        "the API sentinel 'default' is preserved as the internal value",
        wizard.model.currentText() == "default",
    )
    check(
        "Refresh models stays available as an explicit manual control",
        wizard.refresh_models_button.isEnabled(),
    )

    # --- caching: re-entering the page must not re-query ---
    wizard._ensure_models_loaded()
    pump(app, wizard, seconds=0.4)
    check("a cached list is reused on re-entry (Back/Next)", calls["n"] == 1)

    # --- an explicit user choice survives a later refresh ---
    wizard.model.setCurrentText("wombat 1.4")
    wizard.refresh_models_button.click()
    pump(app, wizard)
    check("manual Refresh models performs a new request", calls["n"] == 2)
    check(
        "an explicit model choice is preserved across a refresh",
        wizard.model.currentText() == "wombat 1.4",
    )

    # --- a changed server configuration invalidates the cache ---
    wizard.server_url.setText("https://another.example.invalid")
    wizard._ensure_models_loaded()
    pump(app, wizard)
    check("changing the server configuration re-queries", calls["n"] == 3)

    # =====================================================================
    # Phase recycling: exactly one automatic request
    # =====================================================================
    calls["n"] = 0
    wizard = build(js.WORKFLOW_PHASE_RECYCLING)
    wizard._ensure_models_loaded()
    pump(app, wizard)
    check("Phase recycling: models are fetched automatically", calls["n"] == 1)
    check(
        "Phase recycling: the resolved server default is shown",
        "server default: koala 2.0" in wizard.model_status.text(),
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
        "a model identifier can still be typed by hand after a failure",
        wizard.model.isEditable(),
    )
    calls["fail"] = False

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
