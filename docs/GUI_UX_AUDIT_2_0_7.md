# Phase Studio 2.0.7 GUI audit — development evidence

Audit date: 2026-11-01. This is an incomplete acceptance record, not release approval.

Latest scientific evidence: [Selexipag reference review](SELEXIPAG_REFERENCE_REVIEW_2_0_7.md).
The original CIF and real run are now available. The 62-site molecular view was
confirmed defective and corrected to 70 sites by an independently verified
periodic-query fix. The nine original screenshots remain unavailable. Validation
figures below distinguish the initial UI pass from the subsequent correction.
Latest full regression: **637 passed, 4 skipped, 37 subtests passed**; fresh
ONEFILE/ONEDIR builds and frozen GUI acceptance both passed after the correction.

## Release closure and baseline

Fetched all remote branches and tags before editing. Public GitHub API release
`v2.0.6` is neither draft nor prerelease; published 2026-10-21. The peeled tag
and remote `main` both resolve to `c033982590c8db34515dfc7891620b438ea33d28`.
[Public release](https://github.com/ji-ze/Phase-Studio/releases/tag/v2.0.6).

Both uploaded packages and signed metadata exist. Local copies from the earlier
authenticated release download match the current public asset digests. The
manifest verifies against the compiled pinned Ed25519 public key; both package
sizes and SHA-256 values match that verified manifest:

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| PhaseStudio-2.0.6-x64.exe | 98357837 | c2cd43ac2130e1655484e37726b18bd506612f66dec2012a2d5fe65592623fda |
| PhaseStudio-Jana2020-2.0.6.zip | 95947648 | 8035fa56882010412be70c32dad1d810de94afb4c518a532be62ac738fd77f65 |
| release-manifest.json | 562 | 1df41f1863ee4b953fff4d8beb1816c50878eb1c7226777f7c2c78927f85f630 |
| release-manifest.sig | 64 | cb0cd1c17eb407f072c73aaa56844de218311538ee43dccbc8a58ef338123e5d |

No 2.0.7 or SignPath branch was present locally or remotely; no SignPath source
references were found in packaging/workflow documentation. Created
`development/2.0.7` from verified remote main. Original branch was
`fix/map-feedback-fwhm-2.0.6`; local main was behind remote. Untracked
`docs/workshop/` is pre-existing user work and excluded from this change.
Historical release notes, tag, release body and artifacts are unchanged.

## Evidence boundaries

The initial attachment contained the request text only. The user subsequently
provided the real run directory and original CIF. Independent CIF verification
and reconstructed real-model captures are recorded in the linked reference
review. The nine original screenshots and scientific README remain unavailable;
**no finding is claimed to be verified directly against those nine screenshots**.

New screenshots are actual styled Qt widgets with explicitly synthetic data,
captured offscreen. Baseline source is an untouched archive of remote main;
current source is the development working tree. Captures and logs stay under
ignored `build/audit-2.0.7/`. No private scientific data or binary captures belong
in the PR. No physical-monitor, mixed-DPI, interactive UAC or real Jana session
acceptance is implied.

## Prioritized findings

| ID | Priority | Classification | Evidence / root cause | Disposition |
| --- | --- | --- | --- | --- |
| U01 | P2 | Confirmed scientific presentation defect | Standalone `_sync_map_feedback_widgets` enabled the significance editor by checkbox/cycle alone, including FWHM. Wizard already hides it. | Hide the whole standalone row for FWHM; explain width versus uncertainty; preserve saved values and validation. An explicit reset button handles an inapplicable saved positive limit without silently migrating it. |
| U02 | P2 | Confirmed scientific presentation defect | Wavelength zero displayed as a numerical wavelength despite representing automatic resolution. | Use spinbox special-value text Automatic; value, precision and defaults unchanged. |
| U03 | P2 | Confirmed usability defect | Compact diagnostic input summary accepted `source_note` but did not show cell/symmetry provenance. An open diagnostic is a snapshot and can differ from subsequently edited inputs. | Add selectable provenance in Input details and a snapshot explanation tooltip. |
| U04 | P2 | Confirmed scientific presentation defect | Powder coverage caveat exists in help but is not persistently visible in the main completeness view. | Add visible explanation that indexed coverage is not independent experimental completeness. |
| U05 | P2 | Confirmed scientific presentation defect | Classic viewer counts primary molecular components without explaining subset policy. | Explain independent components and exclusions in the view tooltip; retain a compact count to avoid metadata clipping. |
| U06 | P1 | Confirmed scientific presentation defect | Real CIF reproduces 62 sites and loses 8 heavy atoms because molecular growth leaves the fixed neighbour-cell pool. Independent graph gives two complete 35-site molecules. | Correct periodic query origin, verified on the original and generated references and independent translated-chain tests. Selection policy and exporters are unchanged. |
| U07 | P2 | Confirmed usability defect | Diagnostic context omitted reference/manual fallback and Wizard actions collected stale backing-window values instead of current Wizard fields. | Add missing-value fallback/cache invalidation and snapshot current Wizard inputs for both diagnostic actions without replacing manual overrides. |
| U08 | P1 | Suspected scientific discrepancy requiring investigation | Diagnostic context prefers inflip over matching m90; shared run resolver documents manual, m90, inflip, reference, and classic `get_config` omits m90 argument. | Preserve existing priorities and execution. Conflicting-source reconciliation deferred; existing tests deliberately pin diagnostic precedence. |
| U09 | P1 | Confirmed visual defect | At 1280×800 / 200%, 640×400 logical area cannot accommodate existing fixed footer, header and two-panel minimum content; actual capture clips content despite top-level window fitting. | Open acceptance failure. Geometry-only fit is insufficient. Requires a separately reviewed compact layout solution. |
| U10 | P3 | Optional aesthetic improvement | Ready state reserves large plotting/structure area. | Keep plot area and stable layout; no empty-state redesign without real screenshots. |
| U11 | P2 | Confirmed usability defect | README/changelog still described the published release as unavailable. | Correct status; set runtime and citation version to development 2.0.7. |
| U12 | P2 | Confirmed visual defect | The newly visible coverage caveat exposed a 2-pixel plot-height shift at 150% when changing diagnostic tabs with different page minimum sizes. | Let the splitter own plot-tab height; reserve a stable caveat area; shorten the bins caption while retaining definitions in tooltips. Existing geometry regression passes unchanged. |
| U13 | P2 | Suspected scientific discrepancy requiring investigation | Standalone control gating knows the declared/resolved format, but does not inspect every measurement before displaying a significance editor for a non-FWHM format. Missing/dummy sigma must not be treated as measured uncertainty. | Existing parser/diagnostic and execution guards remain authoritative; broader capability-driven control gating needs verified input loading, not an inferred filename or synthetic uncertainty. |

No P0 issue was established. Priorities describe observed risk, not proof of a
scientific execution failure.

## Scientific investigations

### Molecular counts

`_plot_structure_atoms` counts the atoms actually passed to the scatter after
H/D/He exclusion; it does not count a CIF formula or expected full-cell sites.
`_classic_structure_atoms` expands symmetry in Full cell. In molecular mode it
calls `build_complete_molecule_view` with default `retain_all_sites=False` and
returns its primary `.atoms`. The builder grows periodic/symmetry neighbours,
unwraps connectivity, retains the largest component and comparable components
(at least 80% of the largest), demotes smaller fragments/singletons, and has a
secondary layer that the classic path does not return. Some other viewers use
`retain_all_sites=True`. These are distinct display policies.

The subsequent real-CIF investigation confirms that the fixed candidate pool
truncated both independent molecules, producing 31-site primary fragments.
The correction queries periodic neighbours relative to each frontier atom's
own cell; both independent components now contain 35 heavy atoms. Gemmi confirms
134 total /70 heavy ASU sites and 280 full-cell heavy sites. All labels and the
expected C52 N8 O8 S2 composition are present, with no duplicate primary sites.
See the reference review for the independent numerical graph, symmetry check,
original-CIF metadata and private before/after inventory. No uploaded CIF or
scientific exporter was modified.

### Metadata provenance

The main Input summary, `_collect_hkl_analysis_request` and `get_config` all use
`_resolve_crystal_metadata_from_inputs`. Manual metadata errors are surfaced
before a diagnostic request or run config can be constructed. Validation also
rejects absent metadata. Thus the source does not establish that missing manual
values silently produce a valid run. An earlier diagnostic snapshot, changed
selection, or a distinct Wizard/backend state can explain differing displays;
the missing screenshots/session are needed to distinguish them. The real run
log does confirm the declared `.inflip` cell and P2₁/c, including its legitimate
rounding differences from the original CIF. No manual override is replaced.
Wizard diagnostic requests now use current Wizard fields directly; the main
diagnostic exposes its recorded source and explains snapshot semantics.

### Wavelength and coverage

The diagnostic fallback now uses explicit request wavelength/reference metadata
only when the incoming context has no wavelength, retaining existing malformed
metadata failures and existing inflip/m90 precedence. It does not assign width
units to unverified external five-column files. It creates no default measured
wavelength and changes no run parameter. A targeted independent cubic-cell
Bragg-law check validates the resolved value and reference-cache invalidation.
Wizard validation/completeness additionally snapshot their current reference and
explicit wavelength instead of relying on a stale Advanced backing window.
Replay of the real input resolves 0.39986 Å and matches logged overlap totals.
Conflict cases remain U08, not silently normalized numerical results.

`d_min` is the accepted input resolution boundary; `d98` is the existing
cumulative ≥98% symmetry-allowed indexed-HKL boundary, not proof of separately
resolved powder observations. Allowed HKL are theoretical symmetry orbits;
shell counts/means/medians and FWHM remain the existing statistics. No chart
values, shell boundaries, axis semantics, golden references or exports changed.

## Section coverage

Actual standalone Basic Input, Workflow, Output, Map feedback, Help, validation
and completeness widgets were captured; the offline packaging probe also
exercises Wizard configuration, Map Feedback, advanced pages, plots, result
selection, camera and fullscreen. Existing scientific authorities cover
execution/cancellation/Jana handoff. Stylesheets, fonts, branding, footer
priority, splitter organization and camera implementation remain intact.
The initial visual inspection confirms readable fixed buttons at 1366×768 /100%
and legible 1920×1140 baseline; clipped high-scaling layouts remain open.
Running Complete molecules/Full cell comparisons against the requested real
session, all-section keyboard/accessibility acceptance and physical geometry
restoration cannot be declared complete from these captures.

## Before/after comparison inventory

Paths in this table are relative to ignored `build/audit-2.0.7/`. Main-window
comparisons use 1920×1140 at 100%; diagnostics use the same 1060×680 request.
Use `packaging/tools/capture_gui_audit_207.py before|after` to reproduce.
`PHASE_STUDIO_AUDIT_SOURCE_ROOT` selects the clean archived baseline source.

| Problem / root cause | Correction | Before | After | Validation / limitation |
| --- | --- | --- | --- | --- |
| FWHM significance gate advertised | Hide row; explain capability | before/Map-feedback.png | after/Map-feedback.png | Actual Qt comparison; synthetic format selection |
| Saved positive limit becomes inapplicable | Preserve value and offer explicit reset | before/Map-feedback-saved-limit.png | after/Map-feedback-saved-limit.png | Reset changes the setting only when clicked; targeted Qt assertion |
| Wavelength zero sentinel | Automatic display | before/Map-feedback.png | after/Map-feedback.png | Underlying numeric zero preserved |
| Missing diagnostic provenance | Input-details provenance | before/validation.png | after/validation.png | Synthetic snapshot, not the missing session |
| Powder completeness interpretation | Visible caveat | before/completeness.png | after/completeness.png | Existing scientific statistics unchanged |
| Unqualified molecular subset count | Selected-component qualifier | before/molecular-subset.png | after/molecular-subset.png | Synthetic atoms; no conclusion about Selexipag |
| Missing reference wavelength fallback | Show resolved value/source | before/wavelength-validation.png | after/wavelength-validation.png | Synthetic reference; independent Bragg-law and cache tests |

The `matrix/` inventory contains 16 separate Qt processes spanning 1920×1140,
1920×1080, 1366×768 and 1280×800 at 100/125/150/200%. `geometry.json` reports
window fit only; it is expressly **not** a clipping/accessibility pass.
At minimum the 1280×800 /200% capture is a visual failure. Full physical
maximization, negative monitor coordinates, live mixed-DPI and real Jana2020
remain manual acceptance requirements.

`jana-matrix/` separately exercises the integrated Wizard and its professional
backend at the same requested resolutions/scales using the controlled packaging
probe. All 16 standalone capture processes and 16 integrated probes returned 0.
A successful probe is not a claim of exhaustive visual acceptance. Baseline
`before-small/Map-feedback.png` reproduces the 1280×800 /200% clipping on
released source, establishing that U09 is inherited rather than introduced.

## Initial UI pass validation and remaining gates

Fresh scientific authority scripts passed: core (46), Jana completion (195),
Autosolve orchestration (79), workflow states (141), Result Selection (72), EDMA
review (20), displacement parameters (42), fullscreen viewer (exit 0).
The source packaging/GUI acceptance probe passed using controlled fixtures.
The first complete pytest run finished with 623 passed, 4 skipped, 37 subtests
and 6 failures. Three release-version failures were corrected (citation,
development notes, version expectation); the diagnostic geometry failure was
corrected without weakening its assertion; two Windows-native checks passed
outside sandbox restrictions. Final focused UI checks: 11 passed, including
the unchanged DPI geometry regression. The final complete native-access run
passed: **631 passed, 4 skipped, 37 subtests passed in 600.87 seconds**.
Command: `.venv-build/Scripts/python.exe -m pytest -q -p no:cacheprovider
--basetemp=build/qa207-regression`; log: `pytest-final-full.txt` under the audit
evidence directory. The four skips are the existing opt-in real-project case
and inapplicable ONEFILE/ONEDIR transaction combinations; no scientific golden
expectation or test assertion was weakened. After splitting the independent
fallback test into its own file, both new regression tests also passed together
in 2.68 seconds (`pytest-split.txt`).
No historical run is substituted for a new acceptance result.

Both packaging specifications remain unchanged. Fresh 2.0.7 packages were built
from isolated `build/a207-final`, using the existing combined-safe profile.
Both native-dependency and distribution-boundary audits passed; the Jana ZIP
was extracted and verified (407 files). Snapshot hashes and build output remain
in `build/audit-2.0.7/`. Frozen controlled GUI acceptance results are recorded
below. These unsigned local development packages were not uploaded or released;
2.0.6 artifact verification is separate release closure.

Final frozen acceptance: standalone ONEFILE and Jana ONEDIR both returned 0,
reported version 2.0.7 and `ok: true`, and preserved their controlled input bytes.
Execution/selection/export authorities were additionally compared by AST to
released source: `get_config`, `_validate_run_config`, feedback, overlap grouping,
wavelength resolver, classic structure selection, CIF parsing/symmetry expansion
and CIF writing are unchanged. All final frozen runtime source hashes match the
development working tree. See ignored `scientific-invariants.json` and
`acceptance-summary.json` for machine-readable evidence.

Local build SHA-256 values (unsigned development artifacts):

- ONEFILE: `01e9691d53f2af2410163249c0e52e06da9e550c717205b95e983c719ca1e240`.
- Jana ZIP: `f6601802b1d0525004ae89386a6ad9692adf2718719b7c5b88ee79ec8901fc3e`.
Missing original screenshots, competing-source case U08, small/high-DPI clipping,
physical-monitor checks and real Jana acceptance prevent release approval.
No 2.0.7 tag, release or merge is authorized by this report.

## CIF follow-up validation

The original CIF and run were subsequently supplied and investigated as described
in the [reference review](SELEXIPAG_REFERENCE_REVIEW_2_0_7.md). The isolated periodic
query correction is commit `ca92ce8`; current-Wizard diagnostic snapshots are in
`7b4751f`. Complete regression after the molecular correction: **637 passed,
4 skipped, 37 subtests passed in 515.10 seconds**. The additional Wizard snapshot
test and relevant UI/chain tests separately passed (10 tests); viewer/camera/
routing checks passed (21 tests). All eight authority scripts were rerun and
passed with the same check counts reported above. No scientific golden was
weakened; two UI routing mocks now target the new asynchronous request path.

Both profiles were rebuilt from immutable `build/a207-cif` using combined-safe;
native dependency and distribution checks passed, as did 407-file Jana ZIP
verification. Both frozen GUI probes returned 0, version 2.0.7, `ok: true`, and
unchanged controlled inputs. All runtime snapshot hashes match current source.
Latest local unsigned build hashes:

- ONEFILE: `ce996ce9223fee9008c50c608701d7682e14b2b7497e0a64ca014953669d9ca8`.
- Jana ZIP: `d7e02c0bab710b5b837e1cb085e4ec43dcba3e9540bc7aa8934f6e3a2739cc4b`.

Reconstructed real-CIF before/after captures under ignored
`build/audit-2.0.7/real-run/before/` and `after/` include `molecule.png`
(62 →70 heavy atoms), `cell.png` (280 unchanged), `validation.png` and
`completeness.png`. Main windows are 1920×1140 /100%; paired diagnostics use
1060×680 /100%. These are not the missing original nine screenshots. Detailed
logs, independent numerical checks and hashes stay local under `real-run/`.

## Review integration and changed files

Draft PR: https://github.com/ji-ze/Phase-Studio/pull/21. The diagnostic fallback is
isolated in commit `9983104`; UI/development documentation is in `440c5cb`.

| Area | Changed files |
| --- | --- |
| Runtime | `phase_studio/app.py`, `phase_studio/autosolve_window.py`, `phase_studio/jana_superflip.py`, `phase_studio/hkl_diagnostics.py`, `phase_studio/hkl_diagnostics_ui.py`, `phase_studio/version.py` |
| Regression | `tests/test_wavelength_fallback_207.py`, `tests/test_molecule_cell_crossings_207.py`, `tests/test_gui_audit_207.py`, `tests/test_wizard_final_ui.py`, `tests/test_wizard_layout_polish.py`, `tests/test_split_distribution.py` (development version expectation only) |
| Reproduction | `packaging/tools/capture_gui_audit_207.py` |
| Development/release closure | `README.md`, `CHANGELOG.md`, `CITATION.cff`, `RELEASE_NOTES_2_0_7.md`, this audit, `docs/SELEXIPAG_REFERENCE_REVIEW_2_0_7.md` |

Local comparison viewer: `build/audit-2.0.7/comparison.html`. Capture binaries,
source snapshots, packages and detailed test logs are ignored and remain local.
Only pre-existing untracked `docs/workshop/` remains outside this work.
