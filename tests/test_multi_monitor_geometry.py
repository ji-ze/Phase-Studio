"""Adaptive work-area and DPI guards for 2.0.2 top-level windows."""

import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def segment_probe():
    from PySide6.QtWidgets import QApplication
    from phase_studio.result_selection import ResultFamilySegment

    app = QApplication.instance() or QApplication([sys.argv[0]])
    segment = ResultFamilySegment("CHARGE-FLIPPING SOLUTION", "Superflip phase solution")
    segment.resize(480, segment.minimumHeight())
    segment.show()
    app.processEvents()
    labels = (segment.title_label, segment.subtitle_label)
    result = {
        "minimum": segment.minimumHeight(),
        "hint": segment.minimumSizeHint().height(),
        "lines_fit": all(label.height() >= label.fontMetrics().height() for label in labels),
        "both_visible": all(label.isVisible() and bool(label.text()) for label in labels),
    }
    print(json.dumps(result))


def result_dialog_probe():
    from unittest.mock import patch
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtWidgets import QApplication, QDialog
    import phase_studio.app as appmod
    import test_jana_completion as tjc

    app = QApplication.instance() or QApplication([sys.argv[0]])
    appmod.IterativeSuperflipPipelineQtGUI.save_settings = lambda self: None
    appmod.IterativeSuperflipPipelineQtGUI.load_settings = lambda self: None
    appmod.IterativeSuperflipPipelineQtGUI.refresh_sharped_models = lambda self: None
    win, cycle_results = tjc.build_window(appmod, launch_mode="phase_recycling", cycles=1)
    win.results = cycle_results
    opened = []
    with patch.object(appmod.ResultSelectionDialog, "exec", lambda dialog: opened.append(dialog) or QDialog.Rejected):
        win.open_result_selector("jana")
    dialog = opened[0]
    dialog.show()
    app.processEvents()
    app.processEvents()
    available = dialog.available_geometry_at_open
    pass_rect = QRect(dialog._action_button.mapToGlobal(QPoint(0, 0)), dialog._action_button.size())
    return_rect = QRect(dialog._close_button.mapToGlobal(QPoint(0, 0)), dialog._close_button.size())
    result = {
        "frame_inside": available.contains(dialog.frameGeometry()),
        "pass_inside": available.contains(pass_rect),
        "return_inside": available.contains(return_rect),
        "pass_visible": dialog._action_button.isVisible() and dialog._action_button.text() == "Pass to Jana2020",
        "normal": not dialog.isMaximized(),
        "footer_visible": dialog._footer.isVisible(),
        "client": [dialog.width(), dialog.height()],
        "available": [available.width(), available.height()],
    }
    print(json.dumps(result))
    dialog.close()
    win.close()


if os.environ.get("PHASE_STUDIO_GEOMETRY_CHILD") == "1":
    segment_probe()
    raise SystemExit(0)
if os.environ.get("PHASE_STUDIO_GEOMETRY_CHILD") == "dialog":
    result_dialog_probe()
    raise SystemExit(0)


checks = []


def check(name, condition):
    checks.append((name, bool(condition)))
    print(("PASS" if condition else "FAIL") + " - " + name)


def main():
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QApplication, QDialog
    from phase_studio.ui_branding import (
        clamp_window_to_available_screen,
        fit_dialog_to_available_screen,
        fitted_dialog_client_size,
    )

    # Two representative usable work areas, already excluding their taskbars.
    for label, available in (("smaller", QSize(1366, 728)), ("larger", QSize(2560, 1400))):
        result = fitted_dialog_client_size(
            available, QSize(16, 39), QSize(1420, 880), 0.92, 0.90,
        )
        check(f"{label} monitor clamps width to 92% of availableGeometry",
              result.width() + 16 <= int(available.width() * 0.92))
        check(f"{label} monitor clamps height above the taskbar work-area edge",
              result.height() + 39 <= int(available.height() * 0.90))

    app = QApplication.instance() or QApplication([sys.argv[0]])
    dialog = QDialog()
    available = fit_dialog_to_available_screen(
        dialog, QSize(1420, 880), width_fraction=0.92, height_fraction=0.90,
    )
    dialog.show()
    app.processEvents()
    check("adaptive top-level frame starts wholly inside availableGeometry",
          available.contains(dialog.frameGeometry()))
    original_size = dialog.size()
    dialog.move(available.right() + 400, available.bottom() + 400)
    clamp_window_to_available_screen(dialog)
    app.processEvents()
    check("off-screen restored geometry is repositioned into the current monitor",
          available.contains(dialog.frameGeometry()))
    check("screen-change clamping preserves a normally fitting window size",
          dialog.size() == original_size)
    dialog.resize(available.size())
    clamp_window_to_available_screen(
        dialog, width_fraction=0.92, height_fraction=0.90, center_if_resized=True,
    )
    app.processEvents()
    check("restored normal geometry cannot reopen pseudo-maximized",
          dialog.frameGeometry().width() <= int(available.width() * 0.92)
          and dialog.frameGeometry().height() <= int(available.height() * 0.90))
    dialog.close()

    for scale in ("1", "1.25", "1.5"):
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["QT_SCALE_FACTOR"] = scale
        env["PHASE_STUDIO_GEOMETRY_CHILD"] = "1"
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve())], cwd=str(ROOT), env=env,
            text=True, capture_output=True, timeout=30,
        )
        payload = json.loads(completed.stdout.strip().splitlines()[-1]) if completed.returncode == 0 else {}
        check(f"{scale}x DPI: both selector lines fit actual font metrics",
              completed.returncode == 0 and payload.get("lines_fit") and payload.get("both_visible")
              and payload.get("minimum", 0) >= payload.get("hint", 0))

        env["PHASE_STUDIO_GEOMETRY_CHILD"] = "dialog"
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve())], cwd=str(ROOT), env=env,
            text=True, capture_output=True, timeout=60,
        )
        payload = json.loads(completed.stdout.strip().splitlines()[-1]) if completed.returncode == 0 else {}
        check(f"{scale}x DPI: Result Selection footer and both actions fit availableGeometry",
              completed.returncode == 0 and payload.get("frame_inside")
              and payload.get("pass_inside") and payload.get("return_inside")
              and payload.get("pass_visible") and payload.get("normal")
              and payload.get("footer_visible"))

    failures = [name for name, passed in checks if not passed]
    if failures:
        print(f"\n{len(failures)} of {len(checks)} checks FAILED:")
        for name in failures:
            print("  - " + name)
        raise SystemExit(1)
    print(f"\nAll {len(checks)} checks passed.")


if __name__ == "__main__":
    main()
