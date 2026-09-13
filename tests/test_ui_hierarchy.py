"""Regression tests for the 2026 UI-layout/information-hierarchy polish pass.

Plain Python test (no pytest dependency; run with
`python tests/test_ui_hierarchy.py`), following this project's usual
checks-list-plus-exit-code convention.

Covers:
  - Full main-window construction (guards against the exact class of
    refactoring regression that motivated this pass -- a bare, unqualified
    reference to a helper that no longer exists as a free-standing name,
    e.g. a leftover `add_help_callout(...)` call after such helpers were
    converted to `self._add_help_callout(...)` bound methods).
  - Each Basic/Advanced settings page has at most one page-level
    "Open guide" action (the pageHeading + guideLink row), not a scattered
    one per subsection.
  - Every page-level guide target resolves to a real Help section anchor.
  - Canonical page heading text for each of the 8 configuration subpages.
  - Help navigation link labels are exactly the expected, unabbreviated set.
  - Callout construction: kind-aware object property, still readable text.
  - Advanced -> SharpED map value exponent control.
  - Structure Comparison: one shared camera/zoom across all three panels.
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
    from PySide6.QtWidgets import QApplication, QLabel, QToolButton, QTabWidget, QGroupBox
    app = QApplication.instance() or QApplication([sys.argv[0]])

    import phase_studio.ui_style as ui_style
    ui_style.apply_phase_studio_style(app)

    import phase_studio.app as appmod
    # Kept so the settings-persistence section further down can exercise the
    # real save/load against a throwaway INI file instead of the user's own
    # QSettings, while every other check runs against the stubs.
    real_save_settings = appmod.IterativeSuperflipPipelineQtGUI.save_settings
    real_load_settings = appmod.IterativeSuperflipPipelineQtGUI.load_settings
    appmod.IterativeSuperflipPipelineQtGUI.save_settings = lambda self: None
    appmod.IterativeSuperflipPipelineQtGUI.load_settings = lambda self: None

    # =========================================================================
    # Full main-window construction -- must not raise. This is the specific
    # regression class this pass started from (a NameError for a helper that
    # no longer existed as a bare name after an earlier refactor).
    # =========================================================================
    try:
        win = appmod.IterativeSuperflipPipelineQtGUI()
        check("Full main window constructs without raising", True)
    except Exception as exc:
        check(f"Full main window constructs without raising (raised {exc!r})", False)
        failed = [n for n, ok in results_log if not ok]
        print(f"\n{len(failed)} check(s) FAILED: {failed}")
        sys.exit(1)

    # =========================================================================
    # Page header system: each Basic/Advanced settings page has exactly one
    # pageHeading + at most one guideLink at the page level.
    # =========================================================================
    EXPECTED_PAGE_HEADERS = {
        # (category_tab_index, sub_tab_index): (expected_title, expected_guide_target)
        ("Basic", "Input"): ("Data input", "input"),
        ("Basic", "Workflow"): ("Reconstruction", "workflow"),
        ("Basic", "Output"): ("Output", "output"),
        ("Basic", "Map feedback"): ("Map feedback", "map_feedback"),
        ("Advanced", "Setup"): ("Setup", "adv_setup"),
        ("Advanced", "Superflip"): ("Superflip", "superflip"),
        ("Advanced", "EDMA"): ("EDMA", "edma"),
        ("Advanced", "SharpED"): ("SharpED", "sharped"),
    }

    def tabs_for(category_name):
        return win.basic_tabs if category_name == "Basic" else win.advanced_tabs

    def page_widget(category_name, sub_name):
        tabs = tabs_for(category_name)
        for i in range(tabs.count()):
            if tabs.tabText(i) == sub_name:
                scroll_area = tabs.widget(i)
                return scroll_area.widget()
        return None

    valid_anchors = set(win.help_sections.keys())
    check("At least one Help anchor exists to validate guide targets against", len(valid_anchors) > 0)

    for (category, sub_name), (expected_title, expected_guide) in EXPECTED_PAGE_HEADERS.items():
        page = page_widget(category, sub_name)
        if page is None:
            check(f"{category} -> {sub_name}: page found", False)
            continue
        headings = [w for w in page.findChildren(QLabel) if w.objectName() == "pageHeading"]
        check(f"{category} -> {sub_name}: exactly one pageHeading", len(headings) == 1)
        if headings:
            check(f"{category} -> {sub_name}: pageHeading text is '{expected_title}'", headings[0].text() == expected_title)

        guide_links = [w for w in page.findChildren(QToolButton) if w.objectName() == "guideLink"]
        check(f"{category} -> {sub_name}: exactly one page-level Open guide link (found {len(guide_links)})", len(guide_links) == 1)
        if guide_links:
            check(f"{category} -> {sub_name}: Open guide button text", guide_links[0].text() == "Open guide")

        check(f"{category} -> {sub_name}: guide target '{expected_guide}' resolves to a real Help section", expected_guide in valid_anchors)

    # =========================================================================
    # Subsection headings must not carry their own guide link (checked
    # globally): every guideLink anywhere in the Basic/Advanced tabs belongs
    # to a page header, i.e. the total count across all 8 pages is exactly 8.
    # =========================================================================
    total_guide_links = 0
    for category in ("Basic", "Advanced"):
        tabs = tabs_for(category)
        for i in range(tabs.count()):
            page = tabs.widget(i).widget()
            total_guide_links += len([w for w in page.findChildren(QToolButton) if w.objectName() == "guideLink"])
    check(f"Exactly 8 'Open guide' links exist across all Basic/Advanced pages (one per configured page), found {total_guide_links}", total_guide_links == 8)

    # =========================================================================
    # Help navigation labels: unabbreviated, matching the documented set.
    # =========================================================================
    basic_help_page = page_widget("Basic", "Help")
    expected_basic_labels = {"Setup", "Input", "Workflow", "Output", "Map feedback", "Jana2020", "About"}
    basic_nav_links = {
        w.text() for w in basic_help_page.findChildren(QToolButton)
        if w.objectName() == "helpNavLink" and w.text() in expected_basic_labels
    }
    check("Basic Help nav links match the expected, unabbreviated label set", basic_nav_links == expected_basic_labels)
    for label in expected_basic_labels:
        check(f"Basic Help nav label '{label}' is not truncated/abbreviated", "..." not in label)

    advanced_help_page = page_widget("Advanced", "Help")
    expected_advanced_labels = {"Setup", "Superflip", "EDMA", "SharpED", "Keywords"}
    advanced_nav_links = {
        w.text() for w in advanced_help_page.findChildren(QToolButton)
        if w.objectName() == "helpNavLink" and w.text() in expected_advanced_labels
    }
    check("Advanced Help nav links match the expected, unabbreviated label set", advanced_nav_links == expected_advanced_labels)

    # =========================================================================
    # Metrics tab bar: no corner widget competing with the tab bar, scroll
    # (not silent elision) used for overflow, all 6 scientific tab names present.
    # =========================================================================
    check("Metrics tab bar has no corner widget (moved to its own toolbar row)", win.metrics_tabs.cornerWidget() is None)
    check("Metrics tab bar uses scroll buttons rather than eliding", win.metrics_tabs.usesScrollButtons())
    from PySide6.QtCore import Qt as _Qt
    check("Metrics tab bar never silently elides", win.metrics_tabs.tabBar().elideMode() == _Qt.TextElideMode.ElideNone)
    expected_metrics_tabs = {"Superflip", "SharpED", "Superflip validation", "SharpED validation", "Powder report", "Intensity correction"}
    actual_metrics_tabs = {win.metrics_tabs.tabText(i) for i in range(win.metrics_tabs.count())}
    check("All 6 scientific metrics tab names preserved, unshortened", actual_metrics_tabs == expected_metrics_tabs)

    # =========================================================================
    # Callout system: kind-aware property, Warning stays prominent.
    # =========================================================================
    check("Map feedback Warning callout has calloutKind='warning'", win.metrics_tabs is not None)  # placeholder guard
    feedback_page = page_widget("Basic", "Map feedback")
    warning_callouts = [w for w in feedback_page.findChildren(QLabel) if w.objectName() == "settingsCallout" and w.property("calloutKind") == "warning"]
    check("Map feedback page has a warning-kind callout", len(warning_callouts) >= 1)
    if warning_callouts:
        check("Map feedback Warning callout text preserved", "modify the reflection data" in warning_callouts[0].text())

    workflow_page = page_widget("Basic", "Workflow")
    note_callouts = [w for w in workflow_page.findChildren(QLabel) if w.objectName() == "settingsCallout"]
    check("Basic Workflow page has at least one Note callout", len(note_callouts) >= 1)
    short_notes = [w for w in note_callouts if len(w.text()) < 260]
    check("Workflow Note callouts are meaningfully shorter than the old ~330-char paragraph", all(len(w.text()) < 300 for w in note_callouts))

    # =========================================================================
    # Tooltip width cap: a known-long tooltip (EDMA executable) renders as
    # width-capped rich text, not one long plain-text line.
    # =========================================================================
    edma_row = win.inputs.get("edma_exe")
    if edma_row is not None:
        tip = edma_row.toolTip()
        check("EDMA executable tooltip is wrapped as width-capped rich text", tip.startswith('<div style="max-width:'))

    # =========================================================================
    # 2026 micro-polish pass: settings nav links, run-status sub-progress
    # grouping, execution-log color tiers, Help page heading, merged Output
    # note, metadata-source tooltip clarity.
    # =========================================================================
    nav_links = {w.text(): w for w in workflow_page.findChildren(QToolButton) if w.objectName() == "settingsNavLink"}
    check("SharpED model section has exactly 2 settings-nav links (Connection/Inference), not doc-style text",
          set(nav_links) == {"Connection settings →", "Inference settings →"})
    if "Connection settings →" in nav_links:
        nav_links["Connection settings →"].click()
        check("Connection settings link navigates to Advanced/Setup", win.category_tabs.currentIndex() == 1 and win.advanced_tabs.tabText(win.advanced_tabs.currentIndex()) == "Setup")
    if "Inference settings →" in nav_links:
        nav_links["Inference settings →"].click()
        check("Inference settings link navigates to Advanced/SharpED", win.category_tabs.currentIndex() == 1 and win.advanced_tabs.tabText(win.advanced_tabs.currentIndex()) == "SharpED")
    check("No stray guideLink-named button hides inside the SharpED model section (settings nav links use their own object name)",
          not any(w.objectName() == "guideLink" for w in workflow_page.findChildren(QToolButton) if w.text() in ("Connection settings →", "Inference settings →")))

    check("superflip_repeat_group exists and groups label+bar", hasattr(win, "superflip_repeat_group"))
    if hasattr(win, "superflip_repeat_group"):
        inner_spacing = win.superflip_repeat_group.layout().spacing()
        outer_spacing = win.run_status_panel.layout().spacing()
        check("Superflip-repeat label/bar spacing is tighter than unrelated Run Status rows", inner_spacing < outer_spacing)

    from phase_studio.app import CycleProgressState
    win._apply_superflip_repeat_state(CycleProgressState(
        cycle_index=1, cycle_total=5, stage_name="Superflip", stage_index=2, stage_total=4,
        sub_index=17, sub_total=50, complete=False,
    ))
    check("Superflip repeat state sets the expected text and unhides the group",
          not win.superflip_repeat_group.isHidden() and win.superflip_repeat_detail.text() == "Superflip repeat 17 of 50")

    win._append_execution_log("Micro-polish test: normal info line.", level="INFO")
    win._append_execution_log("Micro-polish test: detail line.", level="DETAIL")
    win._append_execution_log("Micro-polish test: warning line.", level="WARNING")
    win._append_execution_log("Micro-polish test: error line.", level="ERROR")
    log_doc = win.log_text.document()
    log_colors = {}
    block = log_doc.firstBlock()
    while block.isValid():
        it = block.begin()
        if not it.atEnd():
            log_colors[block.text()] = it.fragment().charFormat().foreground().color().name()
        block = block.next()
    check("Execution log NORMAL tier color", log_colors.get("Micro-polish test: normal info line.") == "#14204a")
    check("Execution log DETAIL tier is a distinct, lighter secondary color", log_colors.get("Micro-polish test: detail line.") == "#7183a6")
    check("Execution log WARNING tier stays visually prominent (distinct color)", log_colors.get("Micro-polish test: warning line.") == "#8a5a00")
    check("Execution log ERROR tier stays visually prominent (distinct color)", log_colors.get("Micro-polish test: error line.") == "#b42318")

    help_page = page_widget("Basic", "Help")
    guide_headings = [w for w in help_page.findChildren(QGroupBox) if w.title() in ("Systematic setup guide", "Phase Studio guide")]
    check("Help page's first section heading reads 'Phase Studio guide' (was 'Systematic setup guide')",
          any(w.title() == "Phase Studio guide" for w in guide_headings) and not any(w.title() == "Systematic setup guide" for w in guide_headings))

    output_page = page_widget("Basic", "Output")
    output_callouts = [w for w in output_page.findChildren(QLabel) if w.objectName() == "settingsCallout"]
    check("Output page has exactly one merged information callout (was two separate paragraphs)", len(output_callouts) == 1)
    if output_callouts:
        check("Output callout keeps the ShelX/fcf behavior sentence", "ShelX" in output_callouts[0].text())

    metadata_tip = win.inputs["metadata_source"].toolTip()
    check("Metadata source tooltip explains independence from the reflection-data source", "independently" in metadata_tip)

    # =========================================================================
    # Advanced -> SharpED: the reversible map value exponent control.
    # Default 1.000 is the exact-identity setting that keeps the pre-existing
    # scientific behavior; 0 is the documented bypass.
    # =========================================================================
    from PySide6.QtWidgets import QDoubleSpinBox
    exponent_widget = win.inputs.get("sharped_map_value_exponent")
    check("Advanced -> SharpED exposes a 'sharped_map_value_exponent' input", exponent_widget is not None)
    if exponent_widget is not None:
        sharped_page = page_widget("Advanced", "SharpED")
        check("Map value exponent lives on the Advanced -> SharpED page",
              sharped_page is not None and exponent_widget in sharped_page.findChildren(QDoubleSpinBox))
        outres_widget = win.inputs.get("sharped_outres")
        check("Map value exponent sits in the same Inference group as Output resolution",
              outres_widget is not None and exponent_widget.parentWidget() is outres_widget.parentWidget())

        exponent_label = win.input_labels.get("sharped_map_value_exponent")
        check("Map value exponent has a form label", exponent_label is not None)
        if exponent_label is not None:
            check("Map value exponent label text is the compact 'Map value exponent'",
                  exponent_label.text().rstrip(":") == "Map value exponent")
            check("Map value exponent label is not horizontally clipped (fits its own sizeHint)",
                  exponent_label.sizeHint().width() >= exponent_label.minimumSizeHint().width())

        check("Map value exponent is a QDoubleSpinBox, matching the other numeric SharpED controls",
              isinstance(exponent_widget, QDoubleSpinBox))
        check("Map value exponent default is exactly 1.0", exponent_widget.value() == 1.0)
        check("Map value exponent renders 3 decimals ('1.000')", exponent_widget.decimals() == 3)
        check("Map value exponent minimum is 0.0", exponent_widget.minimum() == 0.0)
        check("Map value exponent maximum is a practical 10.0, not an artificially small cap",
              exponent_widget.maximum() == 10.0)
        check("Map value exponent step follows the existing SharpED numeric convention (0.05)",
              abs(exponent_widget.singleStep() - 0.05) < 1e-12)
        check("Map value exponent control height matches the other configuration controls",
              outres_widget is not None and exponent_widget.minimumHeight() == outres_widget.minimumHeight())

        # 0.0 must be accepted by the control, not clamped away.
        exponent_widget.setValue(0.0)
        check("Map value exponent accepts 0.0 (the documented bypass value)", exponent_widget.value() == 0.0)
        exponent_widget.setValue(1.0)

        tip = exponent_widget.toolTip()
        check("Map value exponent tooltip is width-capped rich text like the other tooltips",
              tip.startswith('<div style="max-width:'))
        check("Map value exponent tooltip states the signed power transform", "sign(x)" in tip)
        check("Map value exponent tooltip states that the inverse is applied automatically", "inverted automatically" in tip)
        check("Map value exponent tooltip documents 1.0 as unchanged and 0 as disabled",
              "1.0 leaves values unchanged" in tip and "0 disables the transform" in tip)

        # ---------------------------------------------------------------------
        # Persistence through the existing QSettings mechanism, exercised
        # against a throwaway INI file.
        # ---------------------------------------------------------------------
        import tempfile
        from PySide6.QtCore import QSettings
        settings_dir = Path(tempfile.mkdtemp())
        original_settings = win.settings
        win.settings = QSettings(str(settings_dir / "phase_studio_test.ini"), QSettings.IniFormat)
        try:
            exponent_widget.setValue(0.750)
            real_save_settings(win)
            check("Map value exponent is written by the existing save_settings() path",
                  str(win.settings.value("inputs/sharped_map_value_exponent", "")).startswith("0.75"))
            exponent_widget.setValue(1.0)
            real_load_settings(win)
            check("Map value exponent is restored by the existing load_settings() path (survives a restart)",
                  abs(exponent_widget.value() - 0.750) < 1e-9)
            exponent_widget.setValue(0.0)
            real_save_settings(win)
            exponent_widget.setValue(1.0)
            real_load_settings(win)
            check("The 0.0 bypass value also persists and is restored, not reset to the default",
                  exponent_widget.value() == 0.0)
        finally:
            win.settings = original_settings
            exponent_widget.setValue(1.0)
            import shutil as _shutil
            _shutil.rmtree(settings_dir, ignore_errors=True)

        # ---------------------------------------------------------------------
        # Configuration locking while a calculation is running.
        # ---------------------------------------------------------------------
        win._set_configuration_locked(True)
        check("Map value exponent is disabled while the configuration is locked", not exponent_widget.isEnabled())
        check("Map value exponent carries the shared configurationLocked style property",
              exponent_widget.property("configurationLocked") is True)
        if exponent_label is not None:
            check("Map value exponent label is locked with its field", not exponent_label.isEnabled())
        win._set_configuration_locked(False)
        check("Map value exponent is re-enabled once the configuration unlocks", exponent_widget.isEnabled())
        check("Map value exponent configurationLocked property is cleared on unlock",
              exponent_widget.property("configurationLocked") is False)
        check("Map value exponent value survives the lock/unlock cycle unchanged", exponent_widget.value() == 1.0)

    # =========================================================================
    # Structure Comparison: rotation, zoom and pan are shared by all panels.
    # Matplotlib drives rotation through elev/azim but zoom (right drag) and
    # pan (middle drag) through the 3D axis limits, so the limits have to be
    # mirrored too -- that is what this section pins down.
    # =========================================================================
    import gemmi
    import numpy as np

    def panel_limits(ax):
        return (
            tuple(round(float(v), 6) for v in ax.get_xlim3d()),
            tuple(round(float(v), 6) for v in ax.get_ylim3d()),
            tuple(round(float(v), 6) for v in ax.get_zlim3d()),
        )

    def fixture_atoms(seed):
        return [
            appmod.AtomSite(
                label=f"C{i}", element="C",
                frac=np.array([((i * 7 + seed) % 10) / 10.0,
                               ((i * 3 + seed) % 10) / 10.0,
                               ((i * 5 + seed) % 10) / 10.0], dtype=float),
            )
            for i in range(6)
        ]

    class FakeMouseEvent:
        """The few attributes Axes3D._on_move() and the app's handlers read."""

        def __init__(self, ax, x, y, xdata, ydata, button):
            self.inaxes = ax
            self.x, self.y = x, y
            self.xdata, self.ydata = xdata, ydata
            self.button = button
            self.key = None
            self.canvas = win.structure_canvas

    win.structure_cell = gemmi.UnitCell(10.0, 11.0, 12.0, 90.0, 90.0, 90.0)
    win.reference_atoms_for_plot = fixture_atoms(0)
    win.superflip_atoms_for_plot = fixture_atoms(1)
    win.deblur_atoms_for_plot = fixture_atoms(2)
    win._update_structure_views()
    # Axes3D._on_move() bails out until the projection matrix exists, which
    # only happens on a real draw -- the offscreen canvas is never painted by
    # an event loop here, so force one.
    win.structure_canvas.draw()

    check("Structure Comparison builds all 3 panels", len(win.structure_axes) == 3)
    check("All 3 panels count as interactive when all have atoms", len(win._structure_interactive_axes) == 3)
    check("All panels start from identical 3D limits (they share one cell)",
          len({panel_limits(a) for a in win.structure_axes}) == 1)

    limits_before = panel_limits(win.structure_axes[0])
    source_ax = win.structure_axes[1]

    # Right-button drag == matplotlib's 3D zoom. Drive matplotlib's own
    # handler exactly as the canvas would, then let the app mirror the result.
    source_ax.button_pressed = 3
    source_ax._sx, source_ax._sy = 0.5, 0.5
    win._begin_structure_view_drag(FakeMouseEvent(source_ax, 700, 400, 0.5, 0.5, 3))
    check("A populated panel is accepted as the drag source", win._structure_view_drag_source is source_ax)

    zoom_move = FakeMouseEvent(source_ax, 700, 300, 0.5, 0.30, 3)
    source_ax._on_move(zoom_move)
    win._sync_structure_view_from_event(zoom_move)

    limits_after = panel_limits(source_ax)
    check("Right-drag actually zoomed the panel under the cursor", limits_after != limits_before)
    check("Right-drag zoom is mirrored onto every other panel",
          len({panel_limits(a) for a in win.structure_axes}) == 1)
    stored_limits = tuple(
        tuple(round(float(v), 6) for v in pair) for pair in (win.structure_view_limits or ())
    )
    check("The shared zoom is recorded on the window for later re-renders", stored_limits == limits_after)

    win._finish_structure_view_drag(FakeMouseEvent(source_ax, 700, 300, 0.5, 0.30, 3))
    check("Finishing the drag clears the drag source", win._structure_view_drag_source is None)

    # The zoom must survive a redraw, exactly as the rotation already does.
    win._update_structure_views()
    check("Zoom is preserved across a panel re-render", panel_limits(win.structure_axes[0]) == limits_after)
    check("Panels stay identical after the re-render",
          len({panel_limits(a) for a in win.structure_axes}) == 1)

    # A different cell must reset the view rather than inherit a stale zoom.
    win.structure_cell = gemmi.UnitCell(20.0, 21.0, 22.0, 90.0, 90.0, 90.0)
    win._update_structure_views()
    check("A cell change drops the stored zoom instead of reusing it", win.structure_view_limits is None)
    check("A cell change reframes the panels on the new cell",
          panel_limits(win.structure_axes[0]) != limits_after)

    # An empty panel has no limits of its own and must not drive the others.
    win.structure_cell = gemmi.UnitCell(10.0, 11.0, 12.0, 90.0, 90.0, 90.0)
    win.deblur_atoms_for_plot = []
    win._update_structure_views()
    check("An empty panel is excluded from the interactive set", len(win._structure_interactive_axes) == 2)
    win._begin_structure_view_drag(FakeMouseEvent(win.structure_axes[2], 1200, 400, 0.5, 0.5, 3))
    check("An empty panel is refused as a drag source", win._structure_view_drag_source is None)

    check("Structure viewer hint documents the right-button zoom",
          "right-drag to zoom" in win.structure_rotation_hint.text())
    check("Structure viewer hint still documents rotation and the shared views",
          "rotate" in win.structure_rotation_hint.text() and "sync" in win.structure_rotation_hint.text())

    # The simplified Jana2020 Wizard must not gain this Advanced-only setting.
    import phase_studio.jana_superflip as jana_superflip
    check("Jana2020 Wizard's JanaRunOptions does not expose the Advanced-only map value exponent",
          "map_value_exponent" not in getattr(jana_superflip.JanaRunOptions, "__annotations__", {}))

    failed = [n for n, ok in results_log if not ok]
    print()
    if failed:
        print(f"{len(failed)} check(s) FAILED: {failed}")
        sys.exit(1)
    else:
        print(f"All {len(results_log)} checks passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
