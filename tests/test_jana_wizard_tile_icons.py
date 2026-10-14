"""Regression tests for the Jana Wizard / Autosolve icon family and action
affordances (Phase Studio 2.0.0 visual-consistency pass).

Icons: the 2.0.3 Wizard uses four coordinated navy line drawings from
ui_branding.ESTABLISHED_ICON_INVENTORY. Existing application, link and
Qt icons remain available on other surfaces. These checks FAIL if:

- any Wizard/Autosolve action carries an icon that is not pixel-identical
  to its declared inventory source (or declares no source at all);
- new icon-drawing functions or new image assets appear in the package;
- an action that has no established icon silently gains one.

Interaction/geometry: the whole tile is a genuine click target
(press+release inside triggers, press+release-outside does not), keyboard
focus + Enter/Space activation, and paired tiles have identical geometry.

Plain Python test (no pytest dependency); run with
`python tests/test_jana_wizard_tile_icons.py`.
"""
import ast
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
results_log = []

# The approved inventory, including the explicitly requested 2.0.3 vector
# workflow family, pinned independently of the production module.
APPROVED_ICON_SOURCES = {
    "workflow_superflip", "workflow_sharped", "workflow_autosolve", "workflow_settings",
    "phase_studio_mark", "external_link", "qt_warning", "qt_information",
    # Qt standard (platform-shipped) monochrome glyphs for the four primary
    # Wizard tiles -- approved explicitly; never custom artwork.
    "qt_media_play", "qt_media_seek_forward", "qt_file_dialog_detailed_view", "qt_file_dialog_list_view",
}
APPROVED_ASSET_FILES = {"phase_studio.ico", "phase_studio_splash.png"}
# Every function/method in the package whose name marks it as icon/glyph
# artwork. Anything else matching ICON_FUNCTION_PATTERN is new artwork.
APPROVED_ICON_FUNCTIONS = {
    "create_phase_studio_logo_pixmap", "create_phase_studio_app_icon", "apply_phase_studio_app_icon",
    "established_icon", "apply_established_icon", "_external_link_icon", "chain_pixmap",
}
ICON_FUNCTION_PATTERN = re.compile(r"(icon|glyph|pixmap)", re.IGNORECASE)


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


def _images_equal(icon_a, icon_b, size=24) -> bool:
    return icon_a.pixmap(size, size).toImage() == icon_b.pixmap(size, size).toImage()


def _widget_icon(widget):
    """The QIcon actually shown by `widget` (a button's icon, a label's
    pixmap, or any icon/pixmap inside a composite tile), or None."""
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QAbstractButton, QLabel

    if isinstance(widget, QAbstractButton):
        return None if widget.icon().isNull() else widget.icon()
    if isinstance(widget, QLabel):
        pixmap = widget.pixmap()
        return None if pixmap is None or pixmap.isNull() else QIcon(pixmap)
    for child in widget.findChildren(QLabel):
        pixmap = child.pixmap()
        if pixmap is not None and not pixmap.isNull():
            return QIcon(pixmap)
    for child in widget.findChildren(QAbstractButton):
        if not child.icon().isNull():
            return child.icon()
    return None


def main():
    from PySide6.QtCore import Qt, QEvent, QPoint, QPointF
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QAbstractButton, QApplication, QDialog

    app = QApplication.instance() or QApplication([sys.argv[0]])
    import phase_studio.ui_style as ui_style

    ui_style.apply_phase_studio_style(app)
    import phase_studio.jana_superflip as js
    import phase_studio.ui_branding as branding

    QDialog.exec = lambda self: QDialog.Rejected

    def build():
        wizard = js._JanaWorkflowWizard([], None)
        wizard.run()
        wizard._ensure_workflow_requirements = lambda **_kwargs: True
        wizard.dialog.show()
        app.processEvents()
        return wizard

    # =====================================================================
    # The inventory itself, and no new artwork anywhere in the package.
    # =====================================================================
    check(
        "the module's established-icon inventory is exactly the approved pre-existing set",
        set(branding.ESTABLISHED_ICON_INVENTORY) == APPROVED_ICON_SOURCES,
    )
    assets = {p.name for p in (ROOT / "phase_studio" / "assets").iterdir() if p.is_file()}
    check("no new image/icon asset files were added to phase_studio/assets", assets == APPROVED_ASSET_FILES)
    stray_images = [
        p for p in (ROOT / "phase_studio").rglob("*")
        if p.suffix.lower() in {".svg", ".png", ".ico", ".qrc", ".bmp", ".jpg"} and p.parent.name != "assets"
    ]
    check("no image/resource files outside phase_studio/assets", stray_images == [])
    new_icon_functions = []
    for module in sorted((ROOT / "phase_studio").glob("*.py")):
        for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and ICON_FUNCTION_PATTERN.search(node.name):
                if node.name not in APPROVED_ICON_FUNCTIONS and (
                    module.name, node.name
                ) != ("sharped_access.py", "_account_icon"):
                    new_icon_functions.append(f"{module.name}:{node.name}")
    check(
        "only approved product/workflow artwork and the requested onboarding account icon exist (found: %s)" % (new_icon_functions or "none"),
        new_icon_functions == [],
    )

    # =====================================================================
    # Every Wizard and Autosolve action: either text-only, or an icon that
    # is pixel-identical to its declared inventory source.
    # =====================================================================
    wizard = build()
    wizard.superflip_sharped_tile._on_click()
    wizard.primary_button.click()
    app.processEvents()
    actions = [
        ("Superflip only tile", wizard.original_superflip_tile.icon_label, "workflow_superflip"),
        ("Superflip + SharpED tile", wizard.superflip_sharped_tile.icon_label, "workflow_sharped"),
        ("Autosolve tile", wizard.autosolve_tile.icon_label, "workflow_autosolve"),
        ("Professional mode", wizard.professional_mode_tile.icon_label, "workflow_settings"),
    ]

    import phase_studio.app as appmod
    from phase_studio.autosolve_window import AutosolveWindow

    appmod.IterativeSuperflipPipelineQtGUI.save_settings = lambda self: None
    appmod.IterativeSuperflipPipelineQtGUI.load_settings = lambda self: None
    backend = appmod.IterativeSuperflipPipelineQtGUI()
    autosolve = AutosolveWindow(backend, "B")
    actions += [
        ("Fit", autosolve.fit_button, None),
        ("Reset view", autosolve.reset_button, None),
        ("Auto rotate", autosolve.auto_rotate_button, None),
        ("Complete molecules", autosolve.molecule_view_button, None),
        ("Full cell", autosolve.full_cell_view_button, None),
        ("Cancel", autosolve.cancel_button, None),
        ("Retry", autosolve.retry_button, None),
        # Final Review's per-panel actions (2.0.1) -- always constructed,
        # regardless of which stage is currently showing them.
        ("Charge-flipping solution + atoms", autosolve.review_columns["observed"]["add"], None),
        ("Charge-flipping solution - atoms", autosolve.review_columns["observed"]["remove"], None),
        ("Charge-flipping solution Recalculate", autosolve.review_columns["observed"]["recalc"], None),
        ("Charge-flipping solution Pass to Jana2020", autosolve.review_columns["observed"]["pass_"], None),
        ("Model prediction + atoms", autosolve.review_columns["predicted"]["add"], None),
        ("Model prediction - atoms", autosolve.review_columns["predicted"]["remove"], None),
        ("Model prediction Recalculate", autosolve.review_columns["predicted"]["recalc"], None),
        ("Model prediction Pass to Jana2020", autosolve.review_columns["predicted"]["pass_"], None),
        ("Powder repartitioning", autosolve.correction_buttons["powder"], None),
        ("Correct suspect intensities", autosolve.correction_buttons["intensity"], None),
    ]

    for name, widget, expected_source in actions:
        icon = _widget_icon(widget)
        source = widget.property(branding.ICON_SOURCE_PROPERTY)
        if expected_source is None:
            check(f"{name}: text-only (no established icon exists for it -- none invented)", icon is None and source is None)
            continue
        check(f"{name}: declares established source {expected_source!r}", source == expected_source)
        check(f"{name}: declared source is in the approved inventory", source in APPROVED_ICON_SOURCES)
        reference = branding.established_icon(expected_source, wizard.dialog.style())
        # A label shows a pixmap rendered at its own size; compare there.
        size = widget.pixmap().width() if hasattr(widget, "pixmap") and widget.pixmap() is not None else 24
        check(f"{name}: shown icon is pixel-identical to the inventory icon", icon is not None and _images_equal(icon, reference, size))

    # Any OTHER icon-bearing button in either window must also be traceable
    # to the inventory -- catches an icon silently added to a new control.
    def untraceable_icons(root):
        bad = []
        for widget in root.findChildren(QAbstractButton):
            if not widget.icon().isNull() and widget.property(branding.ICON_SOURCE_PROPERTY) not in APPROVED_ICON_SOURCES:
                bad.append(widget.text() or widget.objectName())
        return bad

    landing_tiles = (
        wizard.original_superflip_tile, wizard.superflip_sharped_tile,
        wizard.autosolve_tile, wizard.professional_mode_tile,
    )
    for tile in landing_tiles:
        image = tile.icon_label.pixmap().toImage()
        painted = sum(1 for y in range(image.height()) for x in range(image.width()) if image.pixelColor(x, y).alpha() > 0)
        check(f"{tile.title_label.text()}: tile icon is visible and non-empty ({painted} painted px)", painted > 20)
    landing_sources = {tile.icon_label.property(branding.ICON_SOURCE_PROPERTY) for tile in landing_tiles}
    check("the four landing tiles use approved established icons", len(landing_sources) == 4 and landing_sources <= APPROVED_ICON_SOURCES)
    check("every icon-bearing Wizard button traces to the inventory", untraceable_icons(wizard.dialog) == [])
    check("every icon-bearing Autosolve button traces to the inventory", untraceable_icons(autosolve) == [])
    autosolve.close()

    # =====================================================================
    # Tile geometry: each visual pair shares geometry, and the
    # two recommended-workflow objective tiles have identical internal
    # geometry; a tile's text never moves when it
    # gains keyboard focus (focus border is compensated by the QSS margin).
    # =====================================================================
    wizard = build()
    app.processEvents()
    primary_tiles = (wizard.original_superflip_tile, wizard.superflip_sharped_tile)
    secondary_tiles = (wizard.autosolve_tile, wizard.professional_mode_tile)

    def tile_geometry(tile):
        return (
            tile.icon_label.geometry(),
            tile.title_label.geometry().topLeft(),
            tile.subtitle_label.geometry().topLeft(),
            tile.chevron_label.geometry().center().x() - tile.width(),
            tile.chevron_label.geometry().center().y() - tile.height() // 2,
            tile.height(),
        )

    check(
        "the two primary Wizard tiles have exactly the same internal geometry",
        tile_geometry(primary_tiles[0]) == tile_geometry(primary_tiles[1]),
    )
    check(
        "the two secondary Wizard tiles have equal outer and aligned inner geometry",
        secondary_tiles[0].size() == secondary_tiles[1].size()
        and secondary_tiles[0].title_label.geometry().topLeft()
            == secondary_tiles[1].title_label.geometry().topLeft()
        and secondary_tiles[0].subtitle_label.geometry().topLeft()
            == secondary_tiles[1].subtitle_label.geometry().topLeft(),
    )
    wizard.professional_mode_button.setFocus()
    app.processEvents()
    unfocused = wizard.original_superflip_tile.title_label.geometry().topLeft()
    wizard.original_superflip_tile.setFocus()
    app.processEvents()
    check(
        "a tile's title does not shift when the tile gains keyboard focus",
        wizard.original_superflip_tile.title_label.geometry().topLeft() == unfocused,
    )
    wizard.superflip_sharped_tile._on_click()
    wizard.primary_button.click()
    app.processEvents()
    check("recommended workflow skips the removed objective page", wizard.stack.currentWidget() is wizard.page3)
    check("removed objective widgets are absent", not hasattr(wizard, "page_autosolve"))

    # =====================================================================
    # Item 4/32: the whole tile is a genuine click target -- pointing-hand
    # cursor, hover-capable (WA_Hover), keyboard-focusable, and a press that
    # RELEASES OUTSIDE the tile must NOT trigger the action.
    # =====================================================================
    wizard = build()
    tile = wizard.original_superflip_tile
    check("tile uses a pointing-hand cursor", tile.cursor().shape() == Qt.PointingHandCursor)
    check("tile is hover-capable (WA_Hover set, drives the native :hover QSS state)", tile.testAttribute(Qt.WA_Hover))
    check("tile accepts keyboard focus", tile.focusPolicy() != Qt.NoFocus)

    # Enter/Leave must not crash (exercises the real event handlers, even
    # though the resulting QSS :hover repaint itself isn't pixel-checked
    # here).
    QApplication.sendEvent(tile, QEvent(QEvent.Enter))
    QApplication.sendEvent(tile, QEvent(QEvent.Leave))

    press_calls = []
    tile._on_click = lambda: press_calls.append(True)
    inside = QPoint(tile.width() // 2, tile.height() // 2)
    outside = QPoint(tile.width() + 50, tile.height() + 50)
    press_event = QMouseEvent(QEvent.MouseButtonPress, QPointF(inside), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    release_outside_event = QMouseEvent(QEvent.MouseButtonRelease, QPointF(outside), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    tile.mousePressEvent(press_event)
    tile.mouseReleaseEvent(release_outside_event)
    check("press-then-release-OUTSIDE the tile does not trigger the action", press_calls == [])

    release_inside_event = QMouseEvent(QEvent.MouseButtonRelease, QPointF(inside), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    tile.mousePressEvent(press_event)
    tile.mouseReleaseEvent(release_inside_event)
    check("press-then-release INSIDE the tile triggers the action once", press_calls == [True])

    # A genuine simulated click (QTest.mouseClick presses+releases at the
    # widget's center) must also trigger it.
    press_calls.clear()
    QTest.mouseClick(tile, Qt.LeftButton)
    check("a real simulated mouse click triggers the action", press_calls == [True])

    # =====================================================================
    # Item 4/32: keyboard focus + Enter/Space activation.
    # =====================================================================
    press_calls.clear()
    tile.setFocus()
    QTest.keyClick(tile, Qt.Key_Return)
    check("Enter activates the focused tile", press_calls == [True])

    press_calls.clear()
    QTest.keyClick(tile, Qt.Key_Space)
    check("Space activates the focused tile", press_calls == [True])

    # =====================================================================
    # Item 32: full end-to-end tile-driven routing, exercised via a
    # realistic simulated click/keyboard activation rather than calling the
    # stored callback directly.
    # =====================================================================
    wizard = build()
    QTest.mouseClick(wizard.original_superflip_tile, Qt.LeftButton)
    check("Original Superflip: a real mouse click starts it directly", wizard.result["action"] == "run")

    wizard = build()
    QTest.mouseClick(wizard.autosolve_tile, Qt.LeftButton)
    check("Autosolve: a real mouse click starts directly", wizard.result["action"] == "autosolve")

    wizard = build()
    wizard.superflip_sharped_tile._on_click()
    wizard.primary_button.click()
    check("Superflip + SharpED Next opens Map Feedback directly", wizard.stack.currentWidget() is wizard.page3)

    # Keyboard activation of the top-level tiles too.
    wizard = build()
    wizard.original_superflip_tile.setFocus()
    QTest.keyClick(wizard.original_superflip_tile, Qt.Key_Return)
    check("Original Superflip: Enter (keyboard) starts it directly", wizard.result["action"] == "run")

    wizard = build()
    wizard.autosolve_tile.setFocus()
    QTest.keyClick(wizard.autosolve_tile, Qt.Key_Space)
    check("Autosolve: Space (keyboard) starts directly", wizard.result["action"] == "autosolve")

    failures = [name for name, ok in results_log if not ok]
    print()
    if failures:
        print(f"{len(failures)} of {len(results_log)} checks FAILED:")
        for failure in failures:
            print("  - " + failure)
        return 1
    print(f"All {len(results_log)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
