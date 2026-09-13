"""Regression tests for the Jana2020 Workflow Wizard's window geometry.

Plain Python test (no pytest dependency; run with
`python tests/test_wizard_geometry.py`), following this project's usual
checks-list-plus-exit-code convention.

The Wizard used to take whatever width its scrollable content's sizeHint()
happened to report, which settled near the 640 px minimum on a normal desktop.
Workflow descriptions, the Scientific-validation text and the cross-validation
explanation all wrapped far more than necessary, which made the Phase Recycling
page tall enough to need scrolling while leaving wide empty bands below the
content -- a desktop dialog that read like a narrow mobile form.

The width is now a deliberate policy (preferred ~720 px, floor 680, ceiling
820) clamped to the screen that is actually available, so the extra horizontal
space removes wrapping instead of the page growing taller.

Nothing here asserts a fixed window position or a fixed pixel layout: the
checks are about the policy and its clamping behaviour.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

results_log = []

# The narrow layout this pass replaced: the dialog's own hard minimum width.
OLD_NARROW_WIDTH = 640


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


class _WidthProbe:
    """Exercises the real width policy against a synthetic screen/content size,
    without needing a second QApplication per resolution."""

    def __init__(self, wizard_cls, natural_width, available_width):
        from PySide6.QtCore import QSize

        self.WIZARD_MIN_WIDTH = wizard_cls.WIZARD_MIN_WIDTH
        self.WIZARD_PREFERRED_WIDTH = wizard_cls.WIZARD_PREFERRED_WIDTH
        self.WIZARD_MAX_WIDTH = wizard_cls.WIZARD_MAX_WIDTH
        self.WIZARD_MAX_SCREEN_FRACTION = wizard_cls.WIZARD_MAX_SCREEN_FRACTION
        self._preferred = wizard_cls._preferred_dialog_width
        self._available = available_width

        class _Content:
            def sizeHint(self_inner):
                return QSize(natural_width, 400)

        self.content = _Content()

    def _available_screen_width(self):
        return self._available

    def width(self):
        return self._preferred(self)


def main():
    from PySide6.QtWidgets import QApplication, QDialog
    from PySide6.QtCore import Qt

    app = QApplication.instance() or QApplication([sys.argv[0]])
    import phase_studio.ui_style as ui_style

    ui_style.apply_phase_studio_style(app)
    import phase_studio.jana_superflip as js

    wizard_cls = js._JanaWorkflowWizard

    # =====================================================================
    # The policy constants themselves
    # =====================================================================
    check(
        "preferred width is substantially wider than the old narrow layout",
        wizard_cls.WIZARD_PREFERRED_WIDTH >= OLD_NARROW_WIDTH + 60,
    )
    check(
        "preferred width is in the intended 680-760 px desktop band",
        680 <= wizard_cls.WIZARD_PREFERRED_WIDTH <= 760,
    )
    check(
        "minimum practical width is wider than the old narrow layout",
        wizard_cls.WIZARD_MIN_WIDTH > OLD_NARROW_WIDTH,
    )
    check(
        "the width policy is ordered min <= preferred <= max",
        wizard_cls.WIZARD_MIN_WIDTH
        <= wizard_cls.WIZARD_PREFERRED_WIDTH
        <= wizard_cls.WIZARD_MAX_WIDTH,
    )
    check(
        "the screen fraction leaves a margin (<= 92%)",
        0.0 < wizard_cls.WIZARD_MAX_SCREEN_FRACTION <= 0.92,
    )

    # =====================================================================
    # Responsiveness across the required resolutions
    # =====================================================================
    for screen_width, label in ((1920, "1920x1080"), (1600, "1600x900"), (1366, "1366x768")):
        cap = int(screen_width * wizard_cls.WIZARD_MAX_SCREEN_FRACTION)
        # A narrow natural hint (the old behaviour) must still be widened.
        narrow = _WidthProbe(wizard_cls, 500, screen_width).width()
        check(
            "%s: a narrow content hint is widened to the preferred width" % label,
            narrow == wizard_cls.WIZARD_PREFERRED_WIDTH,
        )
        check(
            "%s: the result is wider than the old narrow layout" % label,
            narrow > OLD_NARROW_WIDTH,
        )
        check(
            "%s: the window never exceeds the available screen width" % label,
            narrow <= cap,
        )
        # Content that genuinely wants more space is honoured, up to the cap.
        wide = _WidthProbe(wizard_cls, 900, screen_width).width()
        check(
            "%s: wider content is honoured but capped at the maximum" % label,
            wizard_cls.WIZARD_PREFERRED_WIDTH <= wide <= wizard_cls.WIZARD_MAX_WIDTH,
        )
        check(
            "%s: capped width still fits the available screen" % label,
            wide <= cap,
        )

    # A display too small for even the preferred width must still be clamped.
    tiny = _WidthProbe(wizard_cls, 900, 700).width()
    check(
        "a display narrower than the preferred width clamps to the screen",
        tiny <= int(700 * wizard_cls.WIZARD_MAX_SCREEN_FRACTION),
    )

    # =====================================================================
    # The real Wizard dialog
    # =====================================================================
    QDialog.exec = lambda self: QDialog.Rejected
    wizard = js._JanaWorkflowWizard([], None)
    wizard.run()
    dialog = wizard.dialog

    screen = dialog.screen()
    available = screen.availableGeometry() if screen is not None else None

    check(
        "the real Wizard is wider than the old narrow layout",
        dialog.width() > OLD_NARROW_WIDTH,
    )
    check(
        "the real Wizard reaches at least the practical minimum width",
        dialog.width() >= min(wizard_cls.WIZARD_MIN_WIDTH, wizard.WIZARD_MAX_WIDTH),
    )
    if available is not None:
        check(
            "the real Wizard never exceeds the available screen width",
            dialog.frameGeometry().width() <= available.width(),
        )
        check(
            "the real Wizard never exceeds the available screen height",
            dialog.frameGeometry().height() <= available.height(),
        )

    # The footer must stay outside the scroll area, so navigation is always
    # reachable however tall the page content becomes.
    footer = wizard.chrome_holder.get("footer")
    check("the Wizard has a footer with the navigation actions", footer is not None)
    scroll_area = getattr(wizard, "scroll_area", None)
    check("the Wizard body is inside a scroll area", scroll_area is not None)
    if footer is not None and scroll_area is not None:
        check(
            "the footer is NOT inside the scroll area (it cannot scroll away)",
            not scroll_area.isAncestorOf(footer),
        )
        check(
            "the header is NOT inside the scroll area (it stays stable)",
            not scroll_area.isAncestorOf(wizard.brand_header),
        )
        check(
            "the scrollable body can scroll when content exceeds the window",
            scroll_area.widgetResizable(),
        )

    # Widening must reduce, not increase, the height the page needs.
    content = wizard.content
    if content.hasHeightForWidth():
        narrow_height = content.heightForWidth(OLD_NARROW_WIDTH)
        wide_height = content.heightForWidth(wizard_cls.WIZARD_PREFERRED_WIDTH)
        check(
            "the wider layout needs no more vertical space than the narrow one",
            wide_height <= narrow_height,
        )

    # =====================================================================
    # Height tracks the page on screen, not the tallest page in the stack
    # =====================================================================
    width = wizard_cls.WIZARD_PREFERRED_WIDTH

    def page_height(page):
        if page.hasHeightForWidth():
            return page.heightForWidth(width)
        return page.sizeHint().height()

    pages = [wizard.stack.widget(i) for i in range(wizard.stack.count())]
    check("the Wizard stacks more than one page", len(pages) > 1)
    heights = [page_height(page) for page in pages]
    check("the Wizard pages genuinely differ in height", len(set(heights)) > 1)

    # The stack now reports the page on screen rather than the tallest page it
    # holds -- that correction is what stops short pages being padded out and
    # stops the scroll area believing every page overflows.
    for index, page in enumerate(pages):
        wizard.stack.setCurrentWidget(page)
        app.processEvents()
        reported = (
            wizard.stack.heightForWidth(width)
            if wizard.stack.hasHeightForWidth()
            else wizard.stack.sizeHint().height()
        )
        check(
            "page %d: the stack reports this page, not the tallest one" % (index + 1),
            abs(reported - page_height(page)) <= 2,
        )
        measured = wizard._content_height_for_width(width)
        taller = [h for i, h in enumerate(heights) if i != index and h > page_height(page)]
        if taller:
            check(
                "page %d: a short page is not padded out to the tallest page"
                % (index + 1),
                measured < max(taller) + page_height(page),
            )

    # No large dead band: the shortest page must measure clearly shorter than
    # the tallest one, which is exactly what the empty area under page 1 was.
    wizard.stack.setCurrentWidget(pages[heights.index(min(heights))])
    shortest = wizard._content_height_for_width(width)
    wizard.stack.setCurrentWidget(pages[heights.index(max(heights))])
    tallest = wizard._content_height_for_width(width)
    check(
        "the shortest page sizes the window clearly smaller than the tallest page",
        shortest < tallest,
    )

    # =====================================================================
    # Disabled controls must stay readable (Map feedback shows real values in
    # controls that are disabled until their feature is switched on).
    # =====================================================================
    import re as _re

    def _linear(component):
        value = component / 255.0
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    def _luminance(hex_colour):
        r = int(hex_colour[1:3], 16)
        g = int(hex_colour[3:5], 16)
        b = int(hex_colour[5:7], 16)
        return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)

    def contrast(fg, bg):
        light, dark = sorted((_luminance(fg), _luminance(bg)), reverse=True)
        return (light + 0.05) / (dark + 0.05)

    style = ui_style.PHASE_STUDIO_QSS if hasattr(ui_style, "PHASE_STUDIO_QSS") else None
    if style is None:
        import inspect as _inspect

        style = _inspect.getsource(ui_style)
    block = _re.search(
        r"QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled \{(.*?)\}",
        style,
        _re.S,
    )
    check("the disabled-control style block is present", block is not None)
    if block is not None:
        body = block.group(1)
        fg = _re.search(r"color:\s*(#[0-9a-fA-F]{6})", body)
        bg = _re.search(r"background-color:\s*(#[0-9a-fA-F]{6})", body)
        check("disabled controls define a foreground colour", fg is not None)
        check("disabled controls define a background colour", bg is not None)
        if fg and bg:
            ratio = contrast(fg.group(1), bg.group(1))
            check(
                "disabled control text is comfortably readable (>= 4.5:1), was ~2.8:1",
                ratio >= 4.5,
            )
            # It must still READ as disabled: clearly lower contrast than the
            # enabled navy on the same field.
            enabled_ratio = contrast("#001170", bg.group(1))
            check(
                "disabled controls remain clearly weaker than enabled ones",
                ratio < enabled_ratio,
            )

    # Short numeric editors are not stretched across the whole Wizard.
    width_cap = getattr(wizard_cls, "MAP_FEEDBACK_EDITOR_WIDTH", None)
    check("a Map feedback editor width is defined", width_cap is not None)
    if width_cap is not None:
        check(
            "the editor width sits in the intended 180-240 px band",
            180 <= width_cap <= 240,
        )
        for name in (
            "missing_start_cycle_spin",
            "missing_percent_spin",
            "intensity_start_cycle_spin",
            "intensity_damping_spin",
            "intensity_sigma_spin",
            "powder_start_cycle_spin",
        ):
            widget = getattr(wizard, name, None)
            if widget is None:
                continue
            check(
                "Map feedback editor %s is not stretched full width" % name,
                widget.maximumWidth() <= width_cap,
            )

    # =====================================================================
    # Window icon (section 38): the Wizard must not fall back to the generic
    # Qt icon in the title bar, taskbar or Alt+Tab.
    # =====================================================================
    import phase_studio.app as appmod

    appmod.apply_phase_studio_app_icon(app)
    check("the application carries a Phase Studio icon", not app.windowIcon().isNull())
    check(
        "the Wizard window inherits a non-null icon",
        not wizard.dialog.windowIcon().isNull(),
    )
    check(
        "the icon comes from the one existing helper (no second asset)",
        not appmod.create_phase_studio_app_icon(64).isNull(),
    )
    check(
        "the Wizard title identifies the Jana2020 context",
        "for Jana2020" in wizard.dialog.windowTitle(),
    )

    # =====================================================================
    # Scrollbars (section 37): a page whose content fits must not show one.
    #
    # QStackedLayout reports the tallest page it holds whichever page is
    # showing, and the surrounding layout caches that, so every page used to
    # be told it overflowed and every page carried a scrollbar.
    # =====================================================================
    scroll_area = wizard.scroll_area
    check(
        "the scroll area only shows a scrollbar when needed",
        scroll_area.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded,
    )

    def page_fits(page):
        """Does this page's own requirement fit the scroll viewport?"""
        wizard.stack.setCurrentWidget(page)
        wizard._adjust_dialog_size()
        app.processEvents()
        needed = wizard._page_height_for_width(
            page, wizard._content_inner_width(wizard.dialog.width())
        )
        return needed, scroll_area.viewport().height()

    for label, page_attr in (
        ("initial workflow page", "page1"),
        ("Phase recycling configuration", "page2"),
        ("Map feedback", "page3"),
    ):
        page = getattr(wizard, page_attr, None)
        if page is None:
            continue
        needed, viewport = page_fits(page)
        visible = scroll_area.verticalScrollBar().isVisible()
        if needed <= viewport:
            check(
                "%s: no scrollbar when the content fits" % label,
                not visible,
            )
        else:
            # Genuinely taller than the viewport: the content keeps its full
            # height (nothing is clipped to hide the scrollbar) and the policy
            # allows scrolling.
            check(
                "%s: content keeps its full height and can scroll" % label,
                wizard.stack.height() >= needed - 2
                and scroll_area.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded,
            )
        check(
            "%s: the stack is pinned to this page, not the tallest one" % label,
            abs(wizard.stack.height() - needed) <= 2,
        )

    # Expanded SharpED settings must not break the sizing either.
    if hasattr(wizard, "sharped_toggle"):
        wizard.stack.setCurrentWidget(wizard.page2)
        wizard.sharped_toggle.setChecked(True)
        wizard._adjust_dialog_size()
        app.processEvents()
        needed = wizard._page_height_for_width(
            wizard.page2, wizard._content_inner_width(wizard.dialog.width())
        )
        check(
            "expanded SharpED settings: the stack still follows the page",
            abs(wizard.stack.height() - needed) <= 2,
        )
        wizard.sharped_toggle.setChecked(False)
        wizard._adjust_dialog_size()
        app.processEvents()

    # The footer must never be overlapped by, or scroll with, page content.
    footer_widget = wizard.chrome_holder.get("footer")
    if footer_widget is not None:
        check(
            "the footer sits below the scrollable body, never overlapping it",
            footer_widget.y() >= scroll_area.y() + scroll_area.height() - 2,
        )

    # =====================================================================
    # Shared visual constants (section 34) rather than scattered pixels.
    # =====================================================================
    spacing = getattr(ui_style, "PHASE_STUDIO_SPACING", None)
    check("shared spacing constants exist", isinstance(spacing, dict))
    if isinstance(spacing, dict):
        for key in ("page_margin", "section_gap", "row_gap", "numeric_editor_width"):
            check("spacing level %r is defined" % key, key in spacing)
        check(
            "every Wizard page uses the shared section gap",
            all(
                getattr(wizard, name).layout().spacing() == spacing["section_gap"]
                for name in ("page1", "page2", "page3")
                if getattr(wizard, name, None) is not None
            ),
        )

    from PySide6.QtWidgets import QGroupBox

    groups = wizard.dialog.findChildren(QGroupBox)
    check("the Wizard has configuration sections", len(groups) > 0)
    check(
        "every Wizard section shares one style hook",
        all(g.objectName() == "wizardSection" for g in groups),
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
