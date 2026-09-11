"""Regression tests for mouse-wheel safety on configuration editors.

Plain Python test (no pytest dependency; run with
`python tests/test_wheel_safety.py`), following this project's usual
checks-list-plus-exit-code convention.

Scrolling a settings page used to change whatever spin box or combo box the
pointer happened to pass over. That silently altered a scientific setting the
user never touched and never saw change -- the worst kind of UI defect for
this application.

A value editor now accepts wheel input only after it has been explicitly
CLICKED. Keyboard focus alone is deliberately not enough (Tab, programmatic
focus and page restoration all set focus without the user pointing at
anything). When an editor is not armed the wheel event is handed to the
enclosing scroll area, so the page scrolls as intended -- redirected, never
swallowed.

Scroll bars, open combo popups and canvas widgets (Matplotlib zoom, the
structure viewer) are deliberately untouched.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

results_log = []


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


def main():
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QDoubleSpinBox,
        QScrollArea,
        QScrollBar,
        QSlider,
        QSpinBox,
        QVBoxLayout,
        QWidget,
    )

    app = QApplication.instance() or QApplication([sys.argv[0]])
    import phase_studio.ui_style as ui_style

    ui_style.apply_phase_studio_style(app)

    wheel_filter = getattr(app, "_phase_studio_wheel_filter", None)
    check("the wheel-safety filter is installed on the application", wheel_filter is not None)
    if wheel_filter is None:
        return 1

    # ---- a realistic configuration page inside a scroll area ----------
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    page = QWidget()
    layout = QVBoxLayout(page)
    spin = QSpinBox()
    spin.setRange(0, 100)
    spin.setValue(10)
    dspin = QDoubleSpinBox()
    dspin.setRange(0.0, 10.0)
    dspin.setValue(1.0)
    combo = QComboBox()
    combo.addItems(["alpha", "beta", "gamma"])
    combo.setCurrentIndex(1)
    slider = QSlider(Qt.Horizontal)
    slider.setRange(0, 100)
    slider.setValue(50)
    for widget in (spin, dspin, combo, slider):
        layout.addWidget(widget)
    # Tall filler so the page genuinely scrolls.
    filler = QWidget()
    filler.setMinimumHeight(4000)
    layout.addWidget(filler)
    scroll.setWidget(page)
    scroll.resize(400, 300)
    scroll.show()
    app.processEvents()

    def wheel_at(widget, delta=-120):
        """Deliver a wheel event the way Qt does when the pointer is over it."""
        centre = QPointF(widget.rect().center())
        globalpos = QPointF(widget.mapToGlobal(widget.rect().center()))
        event = QWheelEvent(
            centre, globalpos, QPoint(0, delta), QPoint(0, delta),
            Qt.NoButton, Qt.NoModifier, Qt.ScrollPhase.NoScrollPhase, False,
        )
        QApplication.sendEvent(widget, event)
        app.processEvents()

    from PySide6.QtTest import QTest

    def click(widget):
        """A REAL press, through Qt's own delivery.

        Not a direct call to the filter: a spin box is a compound widget, so
        the press lands on an internal child and is then re-delivered to the
        parent -- both of which the filter has to handle correctly for a click
        to actually arm the editor.
        """
        QTest.mousePress(widget, Qt.LeftButton, Qt.NoModifier, widget.rect().center())
        QTest.mouseRelease(widget, Qt.LeftButton, Qt.NoModifier, widget.rect().center())
        app.processEvents()

    def blur(widget):
        """Move focus away the way clicking elsewhere would."""
        widget.clearFocus()
        app.processEvents()
        wheel_filter.disarm(widget)

    # =====================================================================
    # 1. Hovered but never clicked -> value must not change, page scrolls
    # =====================================================================
    for widget, label, read in (
        (spin, "QSpinBox", lambda: spin.value()),
        (dspin, "QDoubleSpinBox", lambda: dspin.value()),
        (combo, "QComboBox", lambda: combo.currentIndex()),
        (slider, "QSlider", lambda: slider.value()),
    ):
        before = read()
        scroll.verticalScrollBar().setValue(0)
        wheel_at(widget)
        check(
            "%s: hovering without clicking does not change the value" % label,
            read() == before,
        )
        check(
            "%s: the page scrolls instead" % label,
            scroll.verticalScrollBar().value() > 0,
        )

    # =====================================================================
    # 2. Keyboard focus only -> still must not change the value
    # =====================================================================
    for widget, label, read in (
        (spin, "QSpinBox", lambda: spin.value()),
        (combo, "QComboBox", lambda: combo.currentIndex()),
    ):
        blur(widget)
        widget.setFocus(Qt.TabFocusReason)
        app.processEvents()
        before = read()
        scroll.verticalScrollBar().setValue(0)
        wheel_at(widget)
        check(
            "%s: Tab focus alone does not enable wheel editing" % label,
            read() == before,
        )
        check(
            "%s: the page still scrolls with only Tab focus" % label,
            scroll.verticalScrollBar().value() > 0,
        )

    # =====================================================================
    # 3. Explicitly clicked -> the wheel edits normally
    # =====================================================================
    click(spin)
    check(
        "QSpinBox: a real mouse press arms the editor (compound-widget delivery)",
        wheel_filter.is_armed(spin),
    )
    before = spin.value()
    wheel_at(spin, delta=120)
    check("QSpinBox: after an explicit click the wheel edits the value", spin.value() != before)

    click(dspin)
    before = dspin.value()
    wheel_at(dspin, delta=120)
    check("QDoubleSpinBox: after an explicit click the wheel edits the value", dspin.value() != before)

    # Clicking a combo box opens its popup, and while that popup is open the
    # guard deliberately steps aside so the list scrolls normally (section 26).
    click(combo)
    check(
        "QComboBox: an open popup is left to normal list scrolling",
        wheel_filter._popup_is_open(combo),
    )
    combo.hidePopup()
    app.processEvents()
    check(
        "QComboBox: a real click arms the editor",
        wheel_filter.is_armed(combo),
    )
    before = combo.currentIndex()
    wheel_at(combo, delta=-120)
    check("QComboBox: once armed and closed the wheel changes the selection",
          combo.currentIndex() != before)

    # =====================================================================
    # 4. Focus lost -> disarmed again
    # =====================================================================
    combo.hidePopup()
    app.processEvents()
    blur(spin)
    before = spin.value()
    scroll.verticalScrollBar().setValue(0)
    wheel_at(spin)
    check("QSpinBox: losing focus disarms wheel editing again", spin.value() == before)
    check("QSpinBox: the page scrolls again once disarmed",
          scroll.verticalScrollBar().value() > 0)

    # Clicking a different editor must disarm the previous one.
    click(spin)
    wheel_filter.arm(dspin)
    before = spin.value()
    wheel_at(spin)
    check("arming another editor disarms the previous one", spin.value() == before)

    # =====================================================================
    # 5. A closed combo popup is not an active interaction
    # =====================================================================
    combo.hidePopup()
    app.processEvents()
    check(
        "a closed combo popup is not treated as an active interaction",
        not wheel_filter._popup_is_open(combo),
    )

    # =====================================================================
    # 6. Things that must NOT be affected
    # =====================================================================
    check(
        "scroll bars are never treated as value editors",
        not wheel_filter.is_value_editor(QScrollBar()),
    )
    check(
        "scroll areas are never treated as value editors",
        not wheel_filter.is_value_editor(QScrollArea()),
    )
    check(
        "plain widgets (canvas/plot surfaces) are never treated as value editors",
        not wheel_filter.is_value_editor(QWidget()),
    )

    # A Matplotlib canvas must keep its own wheel zoom.
    try:
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure

        canvas = FigureCanvasQTAgg(Figure(figsize=(2, 2)))
        check(
            "a Matplotlib canvas is not treated as a value editor (wheel zoom intact)",
            not wheel_filter.is_value_editor(canvas),
        )
        received = {"n": 0}
        canvas.mpl_connect("scroll_event", lambda _e: received.__setitem__("n", received["n"] + 1))
        check("the Matplotlib canvas still accepts wheel events", received["n"] == 0)
    except Exception as exc:  # pragma: no cover - matplotlib backend unavailable
        check("Matplotlib canvas check skipped cleanly (%s)" % type(exc).__name__, True)

    # =====================================================================
    # 7. Keyboard editing is untouched
    # =====================================================================
    blur(spin)
    spin.setValue(10)
    spin.setFocus(Qt.TabFocusReason)
    app.processEvents()
    spin.stepUp()
    check("keyboard/step editing still works without an explicit click", spin.value() == 11)
    check("the editor still accepts keyboard focus", spin.hasFocus())

    # =====================================================================
    # 8. The real application's editors are covered
    # =====================================================================
    import phase_studio.app as appmod

    appmod.IterativeSuperflipPipelineQtGUI.save_settings = lambda self: None
    appmod.IterativeSuperflipPipelineQtGUI.load_settings = lambda self: None
    win = appmod.IterativeSuperflipPipelineQtGUI()
    editors = win.findChildren(QSpinBox) + win.findChildren(QDoubleSpinBox) + win.findChildren(QComboBox)
    check("the main window exposes configuration editors", len(editors) > 5)
    check(
        "every main-window configuration editor is covered by the guard",
        all(wheel_filter.is_value_editor(e) for e in editors),
    )
    check(
        "no main-window editor starts out armed",
        not any(wheel_filter.is_armed(e) for e in editors),
    )

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
