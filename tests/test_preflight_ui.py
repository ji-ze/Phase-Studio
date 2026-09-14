"""Click-driven coverage for full-GUI and Jana Wizard workflow preflight."""

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

results_log = []


def check(name, condition):
    ok = bool(condition)
    results_log.append((name, ok))
    print(("PASS" if ok else "FAIL") + " - " + name)


def make_exe(directory, name):
    path = Path(directory) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"MZ synthetic executable")
    return path


class _Models:
    models = ("cokoala 4.0",)
    default_model = "cokoala 4.0"


class _Client:
    def __init__(self, **_kwargs):
        pass

    def get_models(self, *_args, **_kwargs):
        return _Models()


def main():
    from PySide6.QtCore import QSettings, QTimer
    from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QPushButton

    settings_root = Path(tempfile.mkdtemp())
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(settings_root))
    app = QApplication.instance() or QApplication([sys.argv[0]])

    import phase_studio.app as appmod
    import phase_studio.jana_superflip as jana

    # Keep constructor-time catalog refreshes out of this preflight test.
    appmod.IterativeSuperflipPipelineQtGUI.refresh_sharped_models = lambda self: None

    tools = Path(tempfile.mkdtemp())
    empty = Path(tempfile.mkdtemp())
    superflip = make_exe(tools, "superflip.exe")
    edma = make_exe(tools, "EDMA.exe")

    started_threads = []

    class _MemorySettings:
        def __init__(self):
            self.values = {}

        def value(self, key, default=None):
            return self.values.get(key, default)

        def setValue(self, key, value):
            self.values[key] = value

        def remove(self, key):
            self.values.pop(key, None)

        def sync(self):
            pass

    class _Thread:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.started = False
            started_threads.append(self)

        def start(self):
            self.started = True

        def is_alive(self):
            return self.started

    original_thread = appmod.threading.Thread
    appmod.threading.Thread = _Thread

    def config(*, sf="", ed="", sharped=False, token="", edma_stage=False):
        return SimpleNamespace(
            superflip_exe=str(sf),
            edma_exe=str(ed),
            sharped_base_url=appmod.DEFAULT_SERVER_URL,
            sharped_api_token=token,
            reconstruction_mode="superflip",
            run_sharped=sharped,
            run_edma_superflip=edma_stage,
            run_edma_deblurred=False,
            run_edma_recycle_final=False,
            work_dir=Path(tempfile.mkdtemp()) / "run",
            input_source_mode=appmod.INPUT_MODE_EXTERNAL,
            jana_inflip=None,
        )

    def click_run_with_dialog(window, cfg, expected_title, action_text="Skip for now"):
        observed = {"title": "", "buttons": []}
        window.get_config = lambda: cfg
        window._validate_run_config = lambda _cfg: ([], "")
        window._preflight_jana_dir = empty
        window._preflight_client_factory = _Client

        def interact():
            dialog = QApplication.activeModalWidget()
            if dialog is None:
                return
            observed["title"] = dialog.windowTitle()
            buttons = dialog.findChildren(QPushButton)
            observed["buttons"] = [button.text() for button in buttons]
            chosen = next((button for button in buttons if button.text() == action_text), None)
            if chosen is not None:
                chosen.click()

        QTimer.singleShot(0, interact)
        window.run_btn.click()
        app.processEvents()
        check(expected_title + " dialog is reached from Run phasing",
              expected_title in observed["title"])
        return observed

    window = appmod.IterativeSuperflipPipelineQtGUI()
    window.timer.stop()
    window.settings = _MemorySettings()
    check("opening Phase Studio does not run preflight",
          QApplication.activeModalWidget() is None and window.worker is None)

    observed = click_run_with_dialog(window, config(), "Superflip setup required")
    check("Superflip remediation has all four requested actions",
          all(label in observed["buttons"] for label in (
              "Browse…", "Open download page", "Download automatically", "Skip for now"
          )))
    check("skipping missing Superflip does not start the worker", window.worker is None)

    observed = click_run_with_dialog(
        window, config(sf=superflip, edma_stage=True), "EDMA setup required"
    )
    check("EDMA remediation has all four requested actions",
          all(label in observed["buttons"] for label in (
              "Browse…", "Open download page", "Download automatically", "Skip for now"
          )))
    check("skipping missing EDMA does not start the worker", window.worker is None)

    observed = click_run_with_dialog(
        window, config(sf=superflip, sharped=True), "SharpED access required"
    )
    check("SharpED remediation has the requested account/token actions",
          all(label in observed["buttons"] for label in (
              "Open SharpED account", "Set token", "Skip for now"
          )))
    check("skipping a missing SharpED token does not start the worker", window.worker is None)

    original_picker = QFileDialog.getOpenFileName
    QFileDialog.getOpenFileName = lambda *_args, **_kwargs: (str(superflip), "")
    before = len(started_threads)
    repaired_cfg = config()
    click_run_with_dialog(window, repaired_cfg, "Superflip setup required", "Browse…")
    QFileDialog.getOpenFileName = original_picker
    check("a successful Browse repair returns to execution",
          len(started_threads) == before + 1 and started_threads[-1].started)
    check("Browse repair updates the current RunConfig",
          Path(repaired_cfg.superflip_exe) == superflip.resolve())
    check("Browse repair updates Advanced Setup",
          Path(window.inputs["superflip_exe"].value()) == superflip.resolve())
    persisted_superflip = window.settings.value("inputs/superflip_exe")
    check("Browse repair persists through the existing settings store",
          Path(str(persisted_superflip)) == superflip.resolve())
    window.close()

    # A fully valid three-requirement configuration stays silent and proceeds.
    window2 = appmod.IterativeSuperflipPipelineQtGUI()
    window2.timer.stop()
    window2.settings = _MemorySettings()
    valid_cfg = config(sf=superflip, ed=edma, sharped=True, token="configured-token", edma_stage=True)
    window2.get_config = lambda: valid_cfg
    window2._validate_run_config = lambda _cfg: ([], "")
    window2._preflight_jana_dir = empty
    window2._preflight_client_factory = _Client
    modal_seen = {"value": False}
    QTimer.singleShot(0, lambda: modal_seen.__setitem__("value", QApplication.activeModalWidget() is not None))
    before = len(started_threads)
    window2.run_btn.click()
    app.processEvents()
    check("valid requirements show no remediation dialog", not modal_seen["value"])
    check("valid requirements proceed to the workflow worker",
          len(started_threads) == before + 1 and started_threads[-1].started)
    check("preflight passes its already-fetched SharpED default to this run",
          valid_cfg.sharped_model == "cokoala 4.0")
    window2.close()

    # Setting a token in the dedicated dialog persists it, re-checks the
    # server, and resumes the same Run phasing request.
    window3 = appmod.IterativeSuperflipPipelineQtGUI()
    window3.timer.stop()
    window3.settings = _MemorySettings()
    token_cfg = config(sf=superflip, sharped=True)
    window3.get_config = lambda: token_cfg
    window3._validate_run_config = lambda _cfg: ([], "")
    window3._preflight_jana_dir = empty
    window3._preflight_client_factory = _Client

    def set_token():
        dialog = QApplication.activeModalWidget()
        if dialog is None:
            return
        token_edit = dialog.findChild(appmod.QLineEdit, "requirementTokenEdit")
        if token_edit is not None:
            token_edit.setText("configured-token")
        button = next(
            (item for item in dialog.findChildren(QPushButton) if item.text() == "Set token"), None,
        )
        if button is not None:
            button.click()

    before = len(started_threads)
    QTimer.singleShot(0, set_token)
    window3.run_btn.click()
    app.processEvents()
    check("Set token re-checks SharpED and resumes execution",
          len(started_threads) == before + 1 and started_threads[-1].started)
    check("Set token updates the current configuration and Setup field",
          token_cfg.sharped_api_token == "configured-token"
          and window3.inputs["sharped_api_token"].text() == "configured-token")
    check("Set token persists through the existing settings store",
          window3.settings.value("inputs/sharped_api_token") == "configured-token")
    window3.close()

    # Build Wizard widgets without entering its top-level blocking event loop.
    original_exec = QDialog.exec
    def build_wizard(workflow):
        QDialog.exec = lambda self: QDialog.Rejected
        wizard = jana._JanaWorkflowWizard([], None)
        wizard.run()
        QDialog.exec = original_exec
        wizard._ensure_models_loaded = lambda: None
        wizard.shared_settings = _MemorySettings()
        wizard.workflow_state["key"] = workflow
        wizard._workflow_changed()
        wizard._preflight_jana_dir = empty
        wizard._preflight_client_factory = _Client
        wizard.shared_settings.remove("inputs/superflip_exe")
        wizard.shared_settings.remove("inputs/sharped_api_token")
        wizard.shared_settings.sync()
        return wizard

    def capture_wizard_dialog(wizard, click):
        observed = {"title": ""}

        def interact():
            dialog = QApplication.activeModalWidget()
            if dialog is None:
                return
            observed["title"] = dialog.windowTitle()
            skip = next(
                (button for button in dialog.findChildren(QPushButton)
                 if button.text() == "Skip for now"), None,
            )
            if skip is not None:
                skip.click()

        QTimer.singleShot(0, interact)
        click()
        app.processEvents()
        return observed["title"]

    wizard = build_wizard(jana.WORKFLOW_SUPERFLIP_ONLY)
    title = capture_wizard_dialog(wizard, wizard.primary_button.click)
    check("Superflip-only Wizard button reaches preflight before execution",
          "Superflip setup required" in title and wizard.result["action"] == "cancel")
    wizard.refresh_timer.stop()
    wizard.dialog.deleteLater()

    wizard = build_wizard(jana.WORKFLOW_SUPERFLIP_SHARPED)
    wizard.api_token.setText("configured-token")
    wizard.primary_button.click()  # workflow page -> SharpED settings page
    title = capture_wizard_dialog(wizard, wizard.primary_button.click)
    check("Superflip + SharpED Wizard button reaches preflight before execution",
          "Superflip setup required" in title and wizard.result["action"] == "cancel")
    wizard.refresh_timer.stop()
    wizard.dialog.deleteLater()

    wizard = build_wizard(jana.WORKFLOW_PHASE_RECYCLING)
    wizard.shared_settings.setValue("inputs/superflip_exe", str(superflip))
    wizard.shared_settings.sync()
    wizard.api_token.clear()
    wizard._check_page3_validity = lambda: ""
    wizard.stack.setCurrentWidget(wizard.page3)
    wizard.primary_button.setText("Run phasing")
    title = capture_wizard_dialog(wizard, wizard.primary_button.click)
    check("Phase recycling Wizard button reaches preflight before auto-start",
          "SharpED access required" in title and wizard.result["action"] == "cancel")
    wizard.refresh_timer.stop()
    wizard.dialog.deleteLater()

    wizard = build_wizard(jana.WORKFLOW_PHASE_RECYCLING)
    called = {"value": False}
    wizard._ensure_workflow_requirements = lambda **_kwargs: called.__setitem__("value", True)
    wizard.edit_button.click()
    check("Open full configuration does not run Wizard preflight",
          not called["value"] and wizard.result["action"] == "edit")
    wizard.refresh_timer.stop()
    wizard.dialog.deleteLater()

    QDialog.exec = original_exec
    appmod.threading.Thread = original_thread
    app.processEvents()

    failures = [name for name, ok in results_log if not ok]
    print()
    if failures:
        print(f"{len(failures)} of {len(results_log)} checks FAILED:")
        for name in failures:
            print("  - " + name)
        return 1
    print(f"All {len(results_log)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
