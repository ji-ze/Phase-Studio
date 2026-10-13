"""Focused guards for the Jana-initiated Windows foreground contract."""
import inspect
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication, QWidget

import phase_studio.jana_superflip as jana
import phase_studio.ui_branding as branding


def main() -> int:
    failures = []

    def check(name, condition):
        print(("PASS" if condition else "FAIL") + " - " + name)
        if not condition:
            failures.append(name)

    app = QApplication.instance() or QApplication([sys.argv[0]])
    window = QWidget()
    branding.activate_user_launched_window(window)
    app.processEvents()
    check("Qt activation helper shows the target top-level window", window.isVisible())

    helper = inspect.getsource(branding.activate_user_launched_window)
    check("activation is repeated after the native handle exists",
          "window.winId()" in helper and "QTimer.singleShot(0" in helper
          and "QTimer.singleShot(120" in helper and "QTimer.singleShot(350" in helper)
    check("Qt raise and activation are both explicit",
          "window.raise_()" in helper and "window.activateWindow()" in helper)
    native = inspect.getsource(branding._windows_foreground_activation)
    check("Jana-only Windows fallback verifies and promotes the real HWND",
          all(api in native for api in (
              "GetForegroundWindow", "ShowWindow", "BringWindowToTop",
              "SetActiveWindow", "SetFocus", "SetForegroundWindow",
          )) and "window.winId()" in native)
    check("foreground-lock attachment is always detached",
          "AttachThreadInput(current_thread, foreground_thread, True)" in native
          and "AttachThreadInput(current_thread, foreground_thread, False)" in native
          and "finally:" in native)
    check("temporary TOPMOST fallback always restores NOTOPMOST",
          "hwnd_topmost" in native and "hwnd_notopmost" in native
          and native.index("hwnd_topmost") < native.index("hwnd_notopmost")
          and "final topmost state: no" in native)
    check("detailed diagnostics record the verified final foreground HWND",
          "Jana/previous foreground HWND" in native
          and "final foreground HWND" in native
          and "activation successful" in native)

    launcher = inspect.getsource(jana.launch_phase_studio_from_jana)
    autosolve = inspect.getsource(jana.launch_autosolve_from_jana)
    check("both Jana GUI routes request the scoped foreground activation",
          "windows_foreground=True, diagnostic_log=diagnostic_log" in launcher
          and "windows_foreground=True, diagnostic_log=diagnostic_log" in autosolve)

    transfer = inspect.getsource(branding.transfer_user_foreground)
    check("foreground transfer shows and creates the target HWND before retiring the source",
          transfer.index("target.show()") < transfer.index("target.winId()")
          < transfer.index("activate_user_launched_window(")
          < transfer.rindex("retire_source_when_active()"))
    check("foreground transfer verifies the target HWND before hiding the source",
          "foreground == target_hwnd" in transfer
          and transfer.index("foreground == target_hwnd") < transfer.index("source.hide()"))
    check("Superflip + SharpED transition uses the verified foreground transfer",
          "transfer_user_foreground(" in launcher
          and "splash, execution, windows_foreground=True" in launcher
          and "win, execution, windows_foreground=True" not in launcher
          and launcher.index("execution = AutosolveWindow(")
          < launcher.index("transfer_user_foreground(")
          < launcher.index("win.start_run()"))

    app_source = (Path(__file__).resolve().parent.parent / "phase_studio" / "app.py").read_text(encoding="utf-8")
    selector = app_source[app_source.index("def open_result_selector"):app_source.index("def _start_jana_handoff")]
    check("Result Selection is parent-owned and queued for activation before exec",
          "dialog_parent if dialog_parent is not None else self" in selector
          and "activate_owned_dialog(dialog, diagnostic_log=activation_log)" in selector
          and selector.index("activate_owned_dialog(dialog, diagnostic_log=activation_log)") < selector.index("dialog.exec()"))

    window.close()
    if failures:
        print(f"\n{len(failures)} check(s) FAILED: {failures}")
        return 1
    print("\nAll 12 checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
