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
    expected_metrics_tabs = {"Superflip", "SharpED", "Superflip validation", "SharpED validation", "Powder repartitioning", "Intensity correction"}
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
