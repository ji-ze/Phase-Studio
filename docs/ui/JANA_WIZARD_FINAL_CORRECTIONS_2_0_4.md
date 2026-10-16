# Jana2020 Wizard final GUI corrections — 2.0.4

This pass changes only the Wizard presentation and keyboard accessibility.
The working tree already contained other 2.0.4 changes; they were preserved.
No release build, version change, commit, push, tag or publication was performed.

## Findings and corrections

The existing central scroll area already reached both secondary cards at its
maximum scroll position, including with optional inputs expanded. The Cancel
footer was already outside that area. Those working arrangements remain intact.
Disclosure changes invalidate the page layout and update its existing size-hint
based stack sizing; collapse removes the extra space without clearing inputs.

An explicit landing-page tab order now follows the visual order, including the
two optional text inputs and Browse buttons when expanded. Hidden controls are
automatically skipped by Qt. A focus event filter reveals the entire control
rectangle, with six logical pixels of margin, after Qt's normal focus handling.
Focus alone performs no action; card Enter/Space handlers are unchanged.

The disclosure has the stable label **Optional reference and initial model**,
using Qt's standard right/down arrow icons instead of text glyphs. It remains
a compact, keyboard-accessible button. File tooltips include the current full
path, including after a manual replacement; selections survive collapse.

The HKL hints are exactly:

- Validate HKL: “Check reflection data and input format.”
- Analyze completeness: “Show reflection completeness and intensity statistics.”

These two short hints use the standard Qt tooltip property directly, bypassing
the application's rich-text wrapper intended for long scientific help. The
shared tooltip style now has a neutral light background, dark text, subtle gray
border and small padding. Other tooltip content and normal Qt timing remain
unchanged. HKL buttons have local secondary-action styles, with subtle hover,
separate focus and pressed states and compensated border padding.

Recommended, Experimental, runtime, workflow captions, optional placeholders
and card chevrons use slightly darker secondary text. Description text already
used the readable navy-gray color and remains unchanged. Branding is unchanged.

The secondary-card breakpoint is measured from title/status text, existing icon,
chevron, padding, spacing and focus border. Cards stay beside one another when
there is room and stack when narrower. Primary-card heights are unchanged.

## Files in this correction

- `phase_studio/jana_superflip.py`: Wizard-only presentation and focus handling.
- `phase_studio/ui_style.py`: conservative shared tooltip colors/padding.
- `tests/test_wizard_final_ui.py`: isolated Qt checks at three DPI scales.
- `tests/test_jana_wizard_tile_icons.py`: permit only the exact standard Qt
  disclosure arrow in addition to the existing product-icon inventory.
- `packaging/tools/capture_wizard_final.py`: actual-widget screenshots and geometry.
- This report and `docs/screenshots/2.0.4-wizard-final/`.

## Screenshot evidence

`docs/screenshots/2.0.4-wizard-final/{before,after}/scale-{1,1.25,1.5}/`
contains 60 PNGs and six geometry reports. Before captures load source snapshots
of the dirty working tree taken immediately before this correction, not the older
Git HEAD. No screenshots were synthesized or redrawn; they are grabs of actual
PySide6 widgets using Qt's offscreen platform at the specified scale factor.

Each scale contains:

1. `01-normal-collapsed.png`
2. `02-normal-expanded.png`
3. `03-reduced-expanded-top.png`
4. `04-reduced-expanded-bottom.png`
5. `05-last-card-keyboard-focus.png`
6. `06-validate-tooltip.png` and `06-validate-tooltip-tooltip.png`
7. `07-completeness-tooltip.png` and `07-completeness-tooltip-tooltip.png`
8. `08-narrow-expanded-bottom.png`

Qt tooltips are separate top-level widgets: each hover screenshot has its own
genuine companion tooltip image rather than a composited or fabricated popup.
The geometry JSON records actual window/viewport/card rectangles, scroll values
and maximum, horizontal range and footer geometry. After captures confirm both
secondary cards completely visible at the bottom and zero horizontal range at
all three scales. Normal expanded captures intentionally show the top of the
scrolling content; the dedicated bottom captures prove the complete range.

The narrow request is 640 logical pixels; existing screen-dependent minimum
geometry can clamp it to 736 at scale 1. The actual size is recorded, and the
secondary cards stack at that width too. At 125% and 150% the captured narrow
window is 640 logical pixels. No minimum window size was increased.

## Scope

No scientific algorithms, workflow selection/execution semantics, Professional
initialization, window ownership/activation, OAuth, API endpoints, EDMA settings,
ranking, Result Selection, Jana handoff or scientific output writers changed in
this pass. This is GUI acceptance evidence, not a new live scientific calculation
or a native Jana2020 scientific acceptance test.

## Validation results

- Complete pytest suite: **266 passed, 1 skipped, 37 subtests passed**, 266.42 s.
  Log: `build/wizard-final/pytest.log`.
- Focused GUI tests: `test_wizard_final_ui.py` and
  `test_wizard_layout_polish.py`: **2 passed**, each running isolated Qt processes
  at 100%, 125% and 150%. Checks include disclosure text/icons/visibility/paths,
  size hints, collapse range restoration, entire focused-card visibility,
  fixed footer, Tab/Shift+Tab, hidden controls, no activation on focus,
  Enter/Space activation, actual diagnostic callbacks, tooltip display/dismissal,
  button geometry and narrow stacking.
- Existing GUI script suites: hierarchy **21**, redesign **44**, tile icons
  **58**, geometry **74**, text clipping **18**, authentication geometry **3**,
  requirements scaling **6** — **224 checks passed**.
- Scientific golden core **46**, displacement parameters **44**, Jana density
  alignment **41**, workflow states **141** — **272 checks passed**. Exact
  Superflip golden input and historical CRLF output guards remain green.
- Screenshot geometry independently checked at all three scales: full secondary
  cards at maximum scroll, complete last card on keyboard focus, zero horizontal
  range. The 100% bottom, expanded and narrow screenshots, tooltip, and 150%
  focused-card screenshot were also visually inspected.
- `git diff --check` passed for the modified tracked source/tests.

The script logs are in `build/wizard-final/test_*.log` and their summary is
`build/wizard-final/script-results.json`. These are test results for the current
working tree; no claim is made about a newly built executable.
