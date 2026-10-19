# Phase Studio 2.0.5

This release brings together the reviewed changes since `v2.0.4`. Runtime,
package metadata, window displays and Windows resources share the authoritative
2.0.5 version in `phase_studio/version.py`.

## Changes since 2.0.4

- Autosolve explicitly uses the live UNIVERSAL API model for search,
  prediction, refinement and correction. This is an intentional change to its
  neural-network predictions; normal Wizard PEAK A/SEED recommendations and
  Professional manual selections remain unchanged.
- Autosolve checks requirements before opening Execution, supports cancellable
  catalogue probing and prevents duplicate starts. Missing models are server
  compatibility failures, with no silent model fallback.
- Visible configuration recovery, separate authentication/authorization errors,
  safe OAuth download failures and additional diagnostic redaction.
- Stage-aware Autosolve presentation, adaptive comparison panels, explicit
  terminal Close and preserved scientific candidate/provenance safeguards.
- Shared trackball camera, persistent optional inversion, coalesced motion,
  geometry reuse, compact metric help and measured full-cell rendering checks.

- Stable Jana2020 Wizard geometry across all three pages, disclosure changes,
  asynchronous model-list updates and validation warnings. Preserve user resize
  and position; clamp restored windows to the available screen.
- Compact model and authentication controls, responsive map-feedback panels,
  shared header/footer geometry and version/update controls in the header.
- Dataset-wide Input analysis toolbar, concise record/unique-index summary,
  aligned italic unit-cell notation and distinct recommended/focused cards.
- Explicit automatic/manual model status, a compact 110 px cycle control,
  Restore automatic, selection-preserving catalogue refresh and actionable
  missing-model states. One cycle retains PEAK A; multiple cycles retain SEED.
- SharpED credentials, public catalogue availability and verified authorization
  remain distinct. Manage account opens the existing secure account dialog.
  Browsing or refreshing models never submits an inference job.
- Public GitHub update checks run in the background, preserve notification
  preferences and handle numeric versions and installed prereleases. They
  offer the relevant release page without downloading or replacing executables.
- Shared scientific typography for Qt labels, table headers, tooltips, copied
  rich summaries and embedded Matplotlib charts. Preserve machine-readable names.
- Refined seven-tab HKL Advanced Diagnostics: compact geometry, balanced counts
  and crystal symmetry, explicit resolution range, phase/uncertainty provenance,
  concise overlap distribution and readable availability selection.
- Context-sensitive completeness/overlap resolution tables, discrete overlap
  group-size categories, percentage presentation and constrained chart layout.
  Reuse authoritative group membership; omit ambiguous per-bin group counts.
- Expanded regression and DPI evidence for Wizard and scientific HKL interfaces.
- Threshold-specific immutable candidate snapshots synchronize Result Selection,
  fullscreen metadata and actual geometry. Pass freezes the chosen candidate;
  a late Cycle 3 event cannot replace an accepted Cycle 2 selection.
- Fullscreen fits its actual viewport while preserving deliberate manual camera
  changes. Optional sensitivity and conventional CPK-style colors are visual
  preferences. Repeated unchanged previews reuse artists and geometry.
- Cycle completion commits progress before announcing completion. Independent
  EDMA controls retain completed structures during asynchronous recalculation.
- Repository hygiene and documentation follow-ups since the 2.0.4 release:
  curated public screenshot evidence, contributing guidance and integration audit.

Scientific parsing, symmetry, resolution/coverage algorithms, powder grouping,
original observations, Superflip/SharpED/EDMA calculations, export schemas and
Jana2020 handoff are unchanged by these UI refinements.

Prior 2.0.4 acceptance reports and build artifacts keep their historical names.
The newest final-polish report and captures are labelled 2.0.5. Local workshop
drafts remain drafts; this version designation does not publish them.

## Downloads and installation

- **Standalone:** download and run `PhaseStudio-2.0.5-x64.exe`.
- **Jana2020 developer integration:** extract `PhaseStudio-Jana2020-2.0.5.zip`
  and keep `Phase_studio.exe` beside its complete `_internal` directory. Follow
  [developer integration](docs/JANA_DEVELOPER_INTEGRATION.md); the isolated EXE is not a portable product.
- Verify the two downloads with `SHA256SUMS.txt`. No obsolete Jana installer or
  duplicate Superflip/EDMA executables are distributed.
- Windows x64; the bundled Qt runtime requires Windows 10 1903 or newer.

## Verification and limits

See `docs/FINAL_WIZARD_RELEASE_ACCEPTANCE_2_0_5.md` and the linked HKL/viewer
reports for test counts, source/build provenance and screenshot acceptance.
Scientific goldens and selected-candidate Jana protocol checks are preserved.
Controlled Qt captures cover 100%, 125% and 150% scaling. Frozen offline UI
checks exercise both products without scientific processing or paid inference.

Native Jana2020 import/refinement continuation, physical-monitor foreground/DPI
behavior and long-running OAuth-expiry scenarios still require manual acceptance.
Automated protocol tests and mock connection states do not establish those results.
Stored manual access keys remain unverified when only the public model catalogue
has responded; authorization is checked by the existing authenticated workflow.
