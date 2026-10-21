# Phase Studio 2.0.6 — release candidate

This is the combined release candidate, not a published production release.
Real Jana2020 import/refinement, interactive UAC/non-admin behavior, physical
monitor acceptance and an approved non-public production-key signing run remain
release gates. No production signing key is generated or changed by a build.

## Scientific correctness and Jana2020

- Correct EDMA maxima density parsing: the nine-column table supplies density
  in column eight, not the centre-of-charge x coordinate in column four.
  Four-column and previously supported indexed maxima remain compatible.
- Preserve EDMA `m40forjana yes` peak density/charge bytes. These are not Biso
  or Uiso. Unknown atomic displacement parameters are omitted from CIF and left
  blank in the PDB B-factor field instead of inventing density-derived values.
- Genuine finite physical ADPs still convert Biso to Uiso once where required,
  then use the protective Uiso interval **0.010–0.150 Å²**. PDB uses the
  corresponding Biso convention. Reference/Jana-owned structures are not rewritten.
- Record raw-peak provenance, site-count distinctions and artifact hashes;
  preserve provenance when promoting a threshold-specific candidate. Handoff
  continues to use the immutable scientific map and corresponding Jana model.
- Keep disconnected EDMA sites visible without presenting distance-only
  contacts as verified chemical bonds; expose scientific provenance in details.

These are justified corrections, not a claim that every old structural export
is byte-identical. Correct density can change merged-peak representatives and
density-based element assignment. Maps, original reflections, extraction,
symmetry, merge tolerances, composition quotas and ranking authorities are
unchanged. Regenerate affected historical exports explicitly from their maps;
handoff does not silently recompute them. See the
[EDMA protocol correction](docs/EDMA_PEAK_PROTOCOL_CORRECTION_2_0_6.md).

## GUI, HKL and runtime stability

- Repair threshold-specific EDMA review on long Windows project paths using
  short isolated workspaces and atomic replacement. Failed extraction retains
  diagnostics and the previous valid candidate; repeated + atoms / - atoms
  operations never substitute preview maps or recompute phasing.
- Automatically restore Jana2020 OAuth access grants from Windows Credential
  Manager across processes and executable updates. No new Remember checkbox
  is required. Explicit sign-out removes the OAuth grant while preserving a
  separately stored manual API key. Temporary connection failures retain it.
- Standardize Map Feedback's positive significance limit to I/σ(I) in both
  configuration paths. Amplitude uncertainties use the explicit first-order
  estimate I/σ(I) ≈ F/(2σ(F)); FWHM is never treated as uncertainty. The strict
  positive gate changes intentionally; a zero limit still disables filtering.
  Existing saved numerical limits are retained without silent migration.

- Virtualize full reflection tables with bounded cell caching, full-dataset
  search/sort and selected-row TSV copying at source precision.
- Improve responsive HKL diagnostics and display-only histogram Detail/Full
  views while preserving diagnostic objects and established JSON/CSV exports.
- Improve Wizard sizing, feedback layout and explanatory text; prevent mouse
  wheel scrolling from changing unfocused scientific parameter controls.
- Fix Qt arrow-overlay ownership during repeated dialog destruction/shutdown.
  Keep source, rendered, ASU and Jana site counts explicitly distinguished.

## Signed Windows updates and packaging

- Integrate consent-based updates for Standalone ONEFILE and Jana2020 ONEDIR:
  canonical Ed25519 manifests, pinned public key, exact profile/version/hash/size
  checks, bounded downloads, current-user DPAPI plans and an independent helper.
- Preserve process/path guards, owned-runtime inventory, journal, startup
  verification, rollback and interrupted recovery. Jana uses explicit
  cancel/close/reopen; updating never completes a scientific handoff.
- Retain an exactly identical installed runtime during a verified full-package
  transaction. A separately signed EXE-only distribution is not included.
- Keep the verified `combined-safe` packaging profile, required native plugins,
  export backends, scientific fonts and legal resources.

Existing installations without updater support need a one-time manual migration.
The production public key is pinned and the main-only signing environment is
configured. Publication requires separately configured environment protections;
availability and a public release are not implied by these release notes.

## Acceptance and limitations

See [final acceptance](docs/FINAL_RELEASE_ACCEPTANCE_2_0_6.md) for the fresh
combined-tree regression results, build provenance and deliverable checksums.
Synthetic credential checks do not constitute live-server authentication.
OAuth grants remain subject to server expiry (currently at most one hour),
with a 60-second safety margin; no refresh token flow is invented. If secure
storage is unavailable or the credential exceeds Windows storage limits, an
explicit warning accompanies session-only authentication.

Historical screenshots and workshop PDFs are preserved. Older Map Feedback
images showing F/σ(F) or value/σ labels are superseded by the I/σ(I) policy in
[the significance note](docs/MAP_FEEDBACK_SIGNIFICANCE_2_0_6.md); they have not
been silently regenerated. Unknown EDMA displacement parameters remain unknown.
