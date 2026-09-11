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

    stack_reported = (
        wizard.stack.heightForWidth(width)
        if wizard.stack.hasHeightForWidth()
        else wizard.stack.sizeHint().height()
    )
    check(
        "the raw stack still reports the tallest page (the Qt behaviour being corrected)",
        stack_reported >= max(heights),
    )

    for index, page in enumerate(pages):
        wizard.stack.setCurrentWidget(page)
        measured = wizard._content_height_for_width(width)
        others = [h for i, h in enumerate(heights) if i != index]
        check(
            "page %d: measured height follows the current page, not the stack maximum"
            % (index + 1),
            measured < stack_reported or page_height(page) >= max(heights),
        )
        if others and page_height(page) < max(others):
            check(
                "page %d: a short page is not padded out to the tallest page" % (index + 1),
                measured < stack_reported,
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
