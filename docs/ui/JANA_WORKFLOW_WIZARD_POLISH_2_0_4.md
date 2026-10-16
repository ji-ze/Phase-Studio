# Jana2020 Workflow Wizard polish — Phase Studio 2.0.4

## Cause and scope

The existing footer is already outside the QScrollArea: this was not a z-order overlap. At the unchanged preferred height, the landing page's natural content is taller than the scroll viewport. With populated ochlor metadata at 821 × 780 logical pixels, the previous page needs 591 px plus 45 px for the filename and content margins/spacing (636 total), while the viewport provides 613 px. Both lower cards therefore extend below the visible viewport at scroll position zero, directly above the fixed footer. The scroll maximum is 23 px. Oversized card minimum heights, top-aligned text with surplus space below it, and vertically stacked diagnostic buttons after narrow-width reflow contribute to this.

At 900 × 850 the previous source already fits. This report does not claim otherwise. No new Workflow screenshot was attached with this request; the comparison uses the repository's existing 900 × 820 capture dimensions and the real default 821 × 780 window. Before screenshots replay the unchanged landing-page code from HEAD, with current shared branding and actual parsed ochlor input. No scientific workflow is started by the capture tool.

Only the landing-page presentation in phase_studio/jana_superflip.py changed. Prior OAuth work in that file and the other dirty working-tree files is preserved. No other agent was editing this file. No shared application branding/style, scientific processing, parser, authentication, executable discovery, packaging profile or version changes were made by this task.

## Changes

- Reduced page/section gaps and section body padding.
- Preserved the two Reflection/Crystal columns and all existing numeric formatting, units, space-group notation and chemical subscripts.
- Both diagnostic buttons have equal widths and at least 36 px height. At smaller widths they occupy one horizontal row below the metadata instead of two stacked rows; the metadata columns can still stack independently.
- Reduced primary card minimum heights from 96 to 88 px and secondary minimum heights from 110 to 96 px. Text sizes are unchanged. Content groups are vertically centered; paired descriptions reserve the same measured line height and align at the top. Their reservation is recalculated on widening, so stale wrapped text does not keep a card unnecessarily tall.
- Existing navy workflow artwork uses consistent 32 px drawings in 40 px containers. No logo or new artwork was introduced.
- Recommended remains a label; its card no longer has a permanent highlighted background. Hover and keyboard focus remain distinct, with full-card mouse/keyboard activation unchanged.
- Secondary cards stack below 660 px of available row width. They remain equal-sized and side by side on ordinary desktop widths.
- Existing fixed footer, current-page stack sizing, filename elision/accessibility and vertical-only scrolling are preserved. Nothing is hidden to suppress overflow.

## Measured before/after

All dimensions below are Qt logical pixels, at 100% scaling, with the same input and window sizes. Exact measurements for all captured states and DPI factors are in each screenshot directory's geometry.json.

| Measurement | Before | After |
| --- | ---: | ---: |
| Input Summary, 900 × 850 | 132 | 126 |
| Input Summary, 736 × 850 | 221 | 175 |
| Each primary card, desktop | 96 | 88 |
| Each secondary card, desktop | 110 | 96 |
| Landing page, desktop | 591 | 537 |
| Landing page, 736 × 850 | 680 | 598 |
| Scroll maximum, 821 × 780 | 23 | 0 |
| Fully visible cards, 821 × 780 | 2 | 4 |
| Scroll maximum, 736 × 850 | 42 | 0 |

Desktop vertical saving: **54 px**. At 736 px width: **82 px**, including **46 px** in the summary. The requested 120–180 px estimate was not needed for this already partially compacted source; reducing readable text to obtain that number would not be justified. Outer window height and geometry policy remain unchanged.

## Validation

Focused checks: Wizard redesign 44, hierarchy/workflow routing 21, startup isolation 17, geometry 74, typography/clipping 18, icon and mouse/keyboard behavior 58. New tests/test_wizard_layout_polish.py verifies actual parsed metadata, complete card visibility at 821 × 780 and ordinary desktop sizes, equal heights, label/icon/chevron containment, fixed footer during scrolling, horizontal scrollbar absence, equal diagnostic button widths, diagnostic callbacks, optional disclosure, keyboard and mouse activation, long-filename accessibility and Cancel. Each child uses isolated temporary input/settings at 100%, 125%, 150%.

Additional screen simulation passes: 1920 × 1080, 2560 × 1440 and 1366 × 768 physical pixels at all three scaling factors. The actual startup window remains within each simulated screen; high scaling on laptop/Full HD screens permits central scrolling and keeps the footer visible. These are Qt offscreen simulations, not physical multi-monitor certification.

Scientific golden checks: **46 passed**, including unchanged input/output and M80 byte contracts. No scientific golden files changed.

Complete final suite: **214 passed, 1 skipped, 37 subtests passed** in 190.49 seconds, without warnings. Recorded in build/wizard-polish-pytest-final.log. git diff --check passed. The existing 2.0.4 standalone EXE SHA-256 remains 100492fdc423b1763b2a258a07c3007234f5ad3b7767b77e8a63785bda49f359; these source UI changes are not included in that unchanged binary.

## Files in this focused change

- phase_studio/jana_superflip.py (landing-page presentation; prior OAuth entry-point additions retained).
- tests/test_wizard_layout_polish.py (new isolated Qt/DPI behavioral guards).
- packaging/tools/capture_wizard_polish.py (new reproducible actual-widget screenshots and measurements).
- docs/ui/JANA_WORKFLOW_WIZARD_POLISH_2_0_4.md (this report).
- docs/screenshots/2.0.4-wizard-polish/ (63 actual-widget PNG captures plus per-profile geometry JSON).

## Rendered screenshots

Actual PySide6 widget captures, not mockups:

- docs/screenshots/2.0.4-wizard-polish/before/scale-1/default-desktop.png
- docs/screenshots/2.0.4-wizard-polish/after/scale-1/default-desktop.png
- before/after scale-1, scale-1.25 and scale-1.5 directories each include normal, default desktop, repository reference size, optional reference expanded, both primary hover states, keyboard focus, reduced height and narrow layout.
- after-native/scale-1 contains Windows-platform widget captures. The current native display reports a portrait available area of 600 × 1220 logical pixels, so these show the naturally clamped narrow layout with scrolling. They are not evidence for a 900 px-wide native desktop.

Capture utility: packaging/tools/capture_wizard_polish.py. It reads the isolated ochlor input from the earlier OAuth acceptance run and routes metadata lookup through the installed Jana directory for capture only. It does not launch Superflip, SharpED inference, EDMA or a Professional-mode backend. Before-source replay uses --baseline and git show HEAD without replacing any working-tree file.

Real Jana2020 launch/handoff acceptance and Windows multi-monitor changes were not repeated for this presentation-only change. They remain distinct from the tested card dispatch and startup-isolation guards. No commit, push, tag, publication or executable rebuild was performed.
