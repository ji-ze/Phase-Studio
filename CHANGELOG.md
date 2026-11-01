# Changelog

## 2.0.7 — development, not published

- Hide the inapplicable standalone significance control for FWHM data while preserving saved values and execution validation; display Automatic for the wavelength sentinel.
- Show diagnostic metadata provenance and an explicit powder indexed-coverage caveat.
- Keep plot-tab geometry stable at constrained display scales; provide an explicit reset action for inapplicable saved significance limits.
- Describe classic molecular-view counts as selected molecular components without changing selection or exports.
- Resolve a missing diagnostic wavelength from available run inputs and invalidate cached diagnostics when the reference changes. Existing incoming diagnostic wavelength priorities are preserved.
- Record the GUI audit and outstanding evidence/physical-monitor acceptance requirements in `docs/GUI_UX_AUDIT_2_0_7.md`.
- Complete molecular views across multiple cell boundaries: independently verified Selexipag reference now shows both complete 35-heavy-atom molecules (70 total), with full cell unchanged at 280. Scientific input files and exporters are unchanged.
- Use current Wizard reference/wavelength fields for validation and completeness without overwriting cached manual settings.

## 2.0.6 — published 2026-10-21

- Fix embedded Jana HKL interpretation in Wizard Map Feedback and the
  execution configuration using the verified shared diagnostics result;
  FWHM is preserved as peak width and never treated as measurement sigma.

- Repair repeated EDMA threshold review and long-path atomic result replacement.
- Persist Jana2020 OAuth securely and automatically across application processes.
- Standardize Map Feedback significance to I/σ(I), with explicit amplitude
  approximation, unchanged zero-limit behavior and preserved saved settings.

- Correct EDMA density-column interpretation and preserve Jana peak protocol;
  stop interpreting peak density as atomic displacement.
- Add scientific export provenance and truthful site/connectivity presentation.
- Complete responsive HKL/Wizard presentation and Qt ownership fixes.
- Integrate signed Windows update verification, independent helper, guarded
  transactions, rollback/recovery and both distribution profiles.

See [2.0.6 release notes](RELEASE_NOTES_2_0_6.md) for scientific compatibility
details and outstanding production-acceptance gates. Historical release notes
remain authoritative for earlier versions; this development branch does not rewrite them.
