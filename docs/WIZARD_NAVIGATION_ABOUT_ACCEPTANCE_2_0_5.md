# Wizard navigation, SharpED status and About acceptance — 2.0.5

## Scope and behavior

The standard Superflip + SharpED Wizard now skips Map Feedback when its
authoritative cycle spinbox is one. Configure processing displays **Run phasing**
and omits Map Feedback from its breadcrumb. This button enters the same
validation, requirements/preflight, settings save and `recycle` dispatch used by
Run on Map Feedback. Two, three and higher cycle counts retain Next → Map
Feedback → Run. No second execution implementation was introduced.

Feedback selections are deliberately job-local, initially off, and not restored
from QSettings. Within one Wizard session they survive Back and cycle changes.
The existing effective runtime gate requires more than one cycle and a compatible
workflow; missing completion, intensity correction and powder repartitioning are
all false in actual serialized one-cycle options, including programmatic entry
to the disabled page. Returning to multiple cycles restores the controls and
reuses the existing start-cycle/wavelength validation. Cycle wording uses one
pluralization helper. Active feedback explicitly describes derived reflection
data for subsequent cycles and preservation of original input files.

Superflip only retains its direct, single-cycle, SharpED-free path. Autosolve
retains its independent adaptive UNIVERSAL preflight/orchestration. Professional
mode still opens full configuration without automatic execution. The new skip
rule applies only to ordinary Superflip + SharpED.

## SharpED presentation

- Automatic selection remains exact PEAK A for one cycle and SEED for multiple
  cycles. Manual choice and Restore automatic remain authoritative. Refresh
  preserves a still-available manual model; a missing required/manual model blocks
  execution with an actionable message.
- `ModelsResult.provenance` identifies real HTTP results as live. Explicit
  controlled offline providers identify themselves as offline. Failed refresh
  retains prior entries labeled Cached and blocks use until refresh succeeds;
  unknown provenance is unavailable. Catalogue status never establishes account
  authorization. No offline catalogue or fallback inference model was added to
  the real client.
- Credential and connection presentation comes from the existing CredentialStore
  and fingerprint-bound session verification. It distinguishes no credentials,
  session access, secure storage, rejected/expired credentials, unchecked,
  checking, verified authorization and unavailable connectivity. Storage detail
  and connection state appear in the compact row's tooltip. A successful OAuth
  token exchange supplies the existing verified authorization state; public
  model discovery does not verify a manual key. No authentication protocol,
  endpoint, token storage or scientific API request behavior changed.
- Manage account opens the existing owned SharpEDAccessDialog. Tests click the
  real button and inspect that dialog, using controlled credentials and no
  browser sign-in or inference.
- The existing standard Qt combo, vector chevron overlay and 25-pixel dropdown
  target are retained. DPI captures and mouse/keyboard tests verify their
  readability, popup activation and disabled behavior.

## About and approved header

`about_ui.AboutDialog` is shared by the existing ellipsis menus in the Wizard
and main application. It uses the existing logo, Science Gothic title/SharpED
wordmark and ordinary body font. Version comes from the version module; mode
comes from the Wizard entry or main window's JanaWizardContext. The dialog has
one visible version, the official Releases button, expandable read-only credits
and Close. Credits read existing AUTHORS, LICENSE, CITATION and third-party
notices verbatim, from repository files in source runs and PhaseStudioLegal in
frozen distributions. No legal statements are independently maintained here.

One modal child is retained per owner. Repeated menu activation raises it.
Existing foreground/geometry helpers clamp the window and return focus to a
visible owner. Close, Escape and window close are tested. The approved static
`v2.0.5` and separate SVG ellipsis header, update actions and preferences remain
intact. The pre-existing full Help/About content remains accessible.

## Visual evidence

`packaging/tools/capture_navigation_about_205.py` renders actual PySide6 widgets
at QT_SCALE_FACTOR 1, 1.25 and 1.5. Each scale has fourteen PNGs and an
`acceptance.json` under ignored
`build/acceptance-navigation-about-2.0.5/scale-{1.0,1.25,1.5}/`:

1. Populated workflow landing page.
2. One-cycle PEAK A configuration and Run button.
3. Three-cycle SEED configuration and Next button.
4. Manual model override.
5. Controlled offline catalogue.
6. Credentials present, authorization unverified.
7. Verified authorization fixture.
8. Three-cycle single-crystal Map Feedback.
9. Three-cycle powder Map Feedback.
10. About in Jana mode.
11. About in standalone mode.
12. Actual ellipsis popup with About action.
13. Controlled live-response catalogue fixture.
14. Cached catalogue after a controlled timeout.

The JSON additionally records actual accepted run-option serialization for
one-cycle skip and direct-page cases, with every feedback flag false. Remote
states are fixtures, not evidence of live authorization or paid calculations.
The standalone main window's actual menu integration is also exercised by
`capture_application_menu_205.py`. Representative landing, configuration,
manual, connection, powder and About images were visually inspected.

## Verification and distribution

Final test and build evidence is recorded in the task report and ignored build
logs prefixed `navigation-`. Scientific golden expectations were not modified.
Legacy UI fixtures explicitly identify offline catalogues; the model, startup,
hierarchy and preflight drivers use temporary INI settings instead of clearing
the user's native Wizard settings. Hierarchy cases independently start with
fresh settings. The click-driven preflight driver follows the existing OAuth /
manual-access-key UI and tests actual local-tool remediation for both one and
three cycles.

| Verification | Result |
| --- | --- |
| Complete pytest suite | 454 passed, 1 opt-in skip, 37 subtests passed (463.89 s) |
| Focused navigation, About, menu, configuration, account and startup tests | 46 passed |
| Scientific core goldens | 46 checks passed |
| Jana completion / handoff | 195 checks passed |
| EDMA | 20 checks passed |
| Result selector / viewer | 72 checks passed |
| Workflow states | 141 checks passed |
| Autosolve orchestration | 79 checks passed |
| Model policy | 46 checks passed |
| Jana startup isolation | 17 checks passed |
| Wizard hierarchy | 21 checks passed |
| Actual preflight UI | 31 checks passed |
| Opt-in ochlor powder/input preservation | 1 passed |

The opt-in ochlor powder test uses a temporary project copy and confirms the
original input bytes remain unchanged. No scientific map was modified and no
paid SharpED inference was submitted.

Both established Windows profiles must be built from the reviewed committed
tree: standalone ONEFILE and Jana developer ONEDIR/ZIP, with runtime/import,
packaging, version, branding and `--release-ui-check` probes. The latter now
checks one-cycle navigation, the branded About dialog and bundled notices.
New local packages are follow-up previews, not replacements for published assets.
The destination is `dist/2.0.5-nav/`; exact sizes, SHA-256 values, source commit,
PE versions, frozen probes and analyzed module paths are recorded in ignored
`build/navigation-build-manifest.json` after the build.

Native Jana2020 end-to-end launch/foreground/handoff acceptance on the interactive
Windows desktop remains required; offscreen ownership, protocol, candidate and
golden tests do not substitute for that acceptance. GitHub CI is not claimed to
have passed without actual remote check results.

Published v2.0.5 already exists at commit
`87b2dcce9276916b94162230bfc26af43be96c38`. Its tag and three release assets remain
unchanged. Corrections are reviewed through existing PR #14 from
`development/2.0.5` to `main`, retained for a controlled follow-up release decision.
No version bump, force-push, automatic merge or binary publication is part of
this follow-up. Unrelated `docs/workshop/` drafts remain untracked.
