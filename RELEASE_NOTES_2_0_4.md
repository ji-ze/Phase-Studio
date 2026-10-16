# Phase Studio 2.0.4

Windows feature and reliability release, closing the 2.0.4 development cycle.

## Highlights

- Sign in with your existing Jana2020 account using the system browser and
  OAuth 2.0 Authorization Code + PKCE. Secure manual access keys remain available.
- Preserve protected job status/download requests across reauthentication;
  retain secure Windows credential storage and redacted diagnostics.
- Compact Jana2020 Workflow Selection, scientific SVG icons, clear recommended
  workflow and keyboard navigation, including high-DPI resource packaging.
- Improved HKL validation, completeness and structured advanced diagnostics.
  Distinguish amplitudes, intensities, uncertainties and powder FWHM explicitly.
- Powder overlap analysis uses documented Superflip FWHM conventions and
  experimental wavelength; missing wavelength never produces invented results.
- Clearer map-feedback effects, execution/result readiness and candidate-specific
  EDMA selection. Preserve scientific maps, candidate identity and Jana context.
- Optional GitHub release notifications distinguish standalone and Jana installs.
- About cites the runtime version. Manual-key instructions correctly describe
  session-only access when secure storage is unavailable.

## Windows download

Download **PhaseStudio-2.0.4-x64.exe** below. Only the standalone EXE is attached.
The Jana2020 integration needs its complete ONEDIR runtime; replacing a Jana
integration executable with this standalone download is not an update procedure.
Superflip/EDMA remain external programs. SharpED service terms and entitlement
are separate from the MIT-licensed Phase Studio application.

## Validation and known limitations

- Complete regression run: 355 passed, 1 skipped, 37 subtests passed.
  The subsequently added runtime-citation test passed separately.
- Scientific golden checks: 46 passed. Wizard model-catalog checks: 44 passed.
  Overall-progress checks: 18 passed. Real ochlor input-metadata check passed.
- Earlier production OAuth acceptance recorded a real browser return and a
  three-cycle ochlor job (3 uploads, 22 status requests, 3 downloads).
  This is historical evidence, not a new live run for this release commit.
- Native Jana2020 handoff/overlay, physical-monitor DPI/fullscreen checks and
  all long-running authentication-expiry scenarios are not fully accepted.
  Automated/offscreen screenshots do not establish those checks.
- Further presentation improvements from the supplied review remain open;
  see [review status](docs/ui/REVIEW_CORRECTIONS_2_0_4_CS.md).

## Screenshots

These are reproducible offscreen UI captures, not evidence of a live calculation.

![Jana2020 Wizard](docs/screenshots/2.0.4-release/wizard.png)

See the [Wizard implementation](docs/ui/JANA_WIZARD_SCIENTIFIC_ICONS_2_0_4.md),
[HKL diagnostics](docs/ui/HKL_ADVANCED_DIAGNOSTICS_2_0_4.md),
[sign-in design](docs/auth/SHARPED_SIGN_IN_FINAL_UX_2_0_4.md) and
[review status](docs/ui/REVIEW_CORRECTIONS_2_0_4_CS.md).
