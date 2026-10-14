# Jana2020 Wizard presentation pass — 2.0.3

This work is isolated on `development/2.0.3`, based on release commit
`65ce510b71d7b33d33f4237ea3470275316e2a5b`. The user's 2.0.3 instruction
supersedes the attachment's 2.0.2 version references. Existing 2.0.2 release
assets, licensing, citation metadata and GitHub release configuration are unchanged.

## Changes

- `jana_superflip.py`: grouped reflection/crystal summary, full-width Superflip
  input composition with display-only subscripts, right-side diagnostic actions
  that move below the summary on narrow windows; compact version identifier.
- All four landing cards share a navy vector icon family. Recommended and
  Experimental sit beside their titles at desktop widths. Narrow secondary
  cards adapt together and retain matching title/description baselines.
- Primary cards use a 96-pixel minimum and secondary cards a 110-pixel minimum;
  Qt content requirements can grow them. No text height is capped.
- Optional-reference collapse restores the body's original required height
  without resizing the outer window. Header and Cancel footer remain outside
  the central scroll area. Disabled cards cannot activate.
- `ui_branding.py` owns the four line drawings; the product icon is unchanged.
  `ui_style.py` supplies the light recommended background/border.
- `version.py` identifies development as 2.0.3. Science Gothic Regular, weight
  400 and zero tracking remain confined to the existing product/SharpED branding.
  Other controls retain the existing Segoe UI styling.
- Existing tests were updated only for requested copy, icon sources and the
  deliberate version increment. Scientific fixtures and golden outputs were not changed.

## Actual Qt captures

The attachment contained text but no screenshot file. The before comparison
therefore uses the actual current 2.0.2 UI captured before editing. Both sides
use the same display-only example metadata; these captures do not claim an
HKL parser or real Jana acceptance test.

- [Before](screenshots/2.0.3-wizard/00-before.png)
- [After, normal](screenshots/2.0.3-wizard/normal.png)
- [Optional references expanded](screenshots/2.0.3-wizard/expanded.png)
- [Superflip hover](screenshots/2.0.3-wizard/hover-superflip.png)
- [Superflip + SharpED hover](screenshots/2.0.3-wizard/hover-sharped.png)
- [Keyboard focus](screenshots/2.0.3-wizard/keyboard-focus.png)
- [Reduced height](screenshots/2.0.3-wizard/short.png)
- [125% scale](screenshots/2.0.3-wizard/normal-125.png)
- [150% scale](screenshots/2.0.3-wizard/normal-150.png)
- [Narrow window](screenshots/2.0.3-wizard/narrow.png)

Reproduce with `packaging/tools/capture_wizard_redesign.py`, running separate
processes with `QT_SCALE_FACTOR=1`, `1.25` and `1.5`. These are actual offscreen
Qt widget renders, not physical Windows multi-monitor acceptance.

At 900×820 logical pixels, the collapsed page has no vertical scrollbar.
Expanded references require 63 pixels of scroll range. At 900×580, the central
body scrolls (223-pixel range); the footer remains visible. Scrolling on small
screens or high scaling is expected. Cards can wrap/grow as width decreases.

## Validation

- All 49 direct test scripts passed: **2,232 checks**.
- `unittest`: **64 passed**; `pytest`: **64 passed**. These runner totals overlap
  the direct scripts and are not additional distinct tests.
- New presentation guards: 44 checks for paired geometry, status bounds,
  lazy Professional initialization, disclosure collapse, footer and activation.
- Existing icon/activation guards: 58; hierarchy: 21; clipping at 100/125/150%: 18;
  Wizard geometry: 74; action footer: 24.
- Jana completion: 192; workflow state: 141; scientific goldens: 46;
  EDMA default guards: 17; displacement checks: 44.
- Both source entry points report 2.0.3. Existing startup isolation/entry-point
  guards pass. Source compilation and `git diff --check` pass.

No scientific algorithms, API requests, model-selection policy, thresholds,
handoff generation, map conversion or displacement calculation were modified.
Golden scientific checks remain identical. No 2.0.3 frozen package was built,
and no development changes were committed, pushed or published in this UI task.
Real Jana2020 GUI acceptance and physical Windows DPI/monitor testing remain
separate acceptance work.
