"""Behavior guards for the shared live detached/fullscreen viewer host."""
import os
import sys
from types import SimpleNamespace

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from phase_studio.fullscreen_viewer import show_detached_viewer, show_single_structure_viewer


def main() -> int:
    app = QApplication.instance() or QApplication([sys.argv[0]])
    owner = QWidget()
    layout = QVBoxLayout(owner)
    before = QLabel("before")
    viewer = QWidget()
    viewer.setObjectName("liveScientificViewer")
    viewer.setProperty("candidate", "deblurred:2:0.4")
    after = QLabel("after")
    layout.addWidget(before)
    layout.addWidget(viewer)
    layout.addWidget(after)
    owner.show()
    app.processEvents()

    window = show_detached_viewer(owner, viewer, "Model prediction", None)
    app.processEvents()
    checks = []

    def check(label, condition):
        checks.append((label, bool(condition)))
        print(("PASS" if condition else "FAIL") + " - " + label)

    check("the exact live viewer widget is detached", viewer.parentWidget() is window)
    check("true fullscreen uses the unambiguous Exit fullscreen action",
          window.fullscreen_button.text() == "Exit fullscreen")
    check("candidate state survives detaching", viewer.property("candidate") == "deblurred:2:0.4")
    same = show_detached_viewer(owner, viewer, "Model prediction", window)
    check("repeated Fullscreen reuses the existing window", same is window)
    QTest.keyClick(window, Qt.Key_F11)
    app.processEvents()
    check("F11 keeps the live widget hosted and names the available action",
          viewer.parentWidget() is window and window.fullscreen_button.text() == "Enter fullscreen")
    window.setGeometry(30,40,640,480)
    app.processEvents()
    saved=window.geometry()
    window.toggle_fullscreen();app.processEvents()
    window.toggle_fullscreen();app.processEvents()
    check("fullscreen restores the preceding normal geometry",window.geometry()==saved and not window.isMaximized())
    QTest.keyClick(window, Qt.Key_Escape)
    app.processEvents()
    check("Esc leaves true fullscreen without closing the detached viewer", viewer.parentWidget() is window and not window.isFullScreen())
    window.close()
    app.processEvents()
    check("Close viewer restores the viewer to its parent", viewer.parentWidget() is owner)
    check("the viewer returns to its original layout position", layout.indexOf(viewer) == 1)
    check("candidate state survives the fullscreen round trip", viewer.property("candidate") == "deblurred:2:0.4")

    mode = {"value": "molecule"}
    calls = []
    atom = SimpleNamespace(element="C")
    def presentation():
        return {
            "atoms": [atom], "coords": np.asarray([[0.0, 0.0, 0.0]]),
            "bonds": [], "cell_segments": [], "fit": (np.zeros(3), 1.0),
            "title": "Phase Studio — Model prediction · Cycle 2",
            "metadata": f"Model prediction · Cycle 2 · {mode['value']}",
        }
    single = show_single_structure_viewer(
        owner, "Phase Studio — Model prediction · Cycle 2", presentation,
        color_for=lambda _element: "#333333",
        set_mode=lambda value: mode.__setitem__("value", value),
        adjust_threshold=lambda add: calls.append(add),
    )
    app.processEvents()
    check("single-structure fullscreen owns exactly one canvas axis", len(single.figure.axes) == 1)
    check("single-structure fullscreen identifies only its selected family",
          "Model prediction" in single.metadata_label.text() and "Charge-flipping solution" not in single.metadata_label.text())
    check("single-structure fullscreen exposes an element legend", "C" in single.legend_label.text())
    check("maximized single-structure viewer offers Enter fullscreen",
          single.fullscreen_button.text() == "Enter fullscreen")
    single.auto_rotate_button.click()
    check("single-structure auto rotation uses a camera-only timer", single._rotation_timer.isActive())
    single.auto_rotate_button.click()
    threshold_buttons = [button for button in single.findChildren(type(single.fullscreen_button)) if button.text() == "+ atoms"]
    threshold_buttons[0].click()
    check("single-structure threshold control delegates to the shared parent state", calls == [True])
    single.close()

    failures = [label for label, ok in checks if not ok]
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
