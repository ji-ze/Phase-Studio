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
