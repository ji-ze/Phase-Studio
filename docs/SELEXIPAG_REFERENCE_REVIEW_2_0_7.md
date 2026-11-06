# Selexipag reference and real-run review — 2.0.7

This extends the [GUI audit](GUI_UX_AUDIT_2_0_7.md) with the subsequently supplied
original CIF and real 25-cycle run. Uploaded coordinates, reflections, logs and
private captures remain outside public Git commits. The nine original screenshots
are still unavailable; newly generated captures are explicitly reconstructions.

## Independent CIF verification

Gemmi reads two blocks (`global` and the structural block `I`); verification
selects the block containing atomic sites rather than assuming a single block.

| Property | Independently read / verified |
| --- | --- |
| Molecular formula | C26 H32 N4 O4 S |
| Space group | P2₁/c, #14; four symmetry operators |
| Z | 8 |
| Cell a, b, c / Å | 37.96347, 6.110426, 22.47454 |
| Cell α, β, γ / degrees | 90, 98.3273, 90 |
| Wavelength / Å | 0.39986 |
| ASU sites, including hydrogen | 134: C52 H64 N8 O8 S2 |
| ASU non-hydrogen sites | 70 |
| Full-cell non-hydrogen sites | 280, independently generated with Gemmi symmetry and periodic deduplication |
| Occupancy | All 134 explicitly equal 1 |
| Disorder groups | All 134 are `.`; no split group declared |

The ASU contains two independent molecules (Z′ = Z / 4 = 2), each with 35 heavy
atoms. An exhaustive minimum-image graph independently gives two components of
35 sites, with 74 bonds total under the existing presentation cutoffs. No CIF
coordinates, occupancies or symmetry operators were changed.

The two independent molecules are chemically equivalent copies of the same
compound; they are crystallographically independent. None of the four space-group
operators maps one component onto the other. Even a relaxed nearest-same-element
matching gives a minimum RMS lower bound of 8.40345 Å over those operators,
well beyond coincident-site tolerance. The final viewer has 70 distinct labelled
heavy sites, not two symmetry-generated renderings of one independent molecule.
“Complete molecules” therefore correctly shows both independent components.

## Confirmed 62-versus-70 defect and correction

Both the original CIF and the generated run reference reproduce **62 atoms** on
released code: C50 N8 O4, with both sulfur atoms, four oxygens and two carbons
absent from primary content. This is a confirmed scientific presentation defect,
not merely a different counting convention.

The candidate pool contains the home cell and its 26 neighbours. Growth queried
that pool in absolute coordinates, so a molecule spanning several short cell
lengths could leave the pool. The resulting fragments were then filtered by the
existing component-size policy. Intermediate component sizes were 31, 16, 31,
19; some previously reached sites were revisited through the disconnected
fragments. Merely retaining every fragment would produce 97 sites, so changing
the subset filter would conceal the root cause and introduce duplicates.

The isolated correction translates each frontier query into its own home cell,
queries the unchanged periodic/symmetry pool, then translates the accepted image
back. Bond cutoffs, symmetry, selection policy and framework limits are unchanged.
The corrected components are **35 + 35 = 70**, with C52 N8 O8 S2, all heavy labels
represented, 74 bonds, no graph-sanity problems, and zero unassigned fragments.
The retain-all representation also has 70 sites. Full cell remains 280.

Independent synthetic verification uses one or two 20-site carbon chains crossing
multiple cell faces. Cartesian construction fixes 19 bonds per chain, with length
√2.44 Å. All sites and bonds must survive positive and negative lattice-origin
translations; input labels, elements and coordinate arrays must remain unchanged.
The old implementation can return 25 primary sites for a 20-site chain; the
corrected implementation returns exactly 20. No private coordinates are used in
the committed regression tests.

Actual before/after Qt captures at identical 1920×1140 /100% are local:
`build/audit-2.0.7/real-run/before/molecule.png` and `after/molecule.png`.
Both also have `cell.png` captures and machine-readable counts. Visual inspection
confirmed the restored sulfur-containing groups and unchanged full-cell count.
The long subset qualifier was moved into the view-button tooltip to avoid clipping
the formula/count line; the tooltip explicitly permits multiple independent
molecules in this view.

## Actual run metadata and wavelength

The provided run log confirms **4,690 parsed and unique input indices**, verified
`I + FWHM`, P2₁/c and metadata from the incoming `.inflip`. The executed cell is
37.96190 × 6.11010 × 22.47390 Å, β = 98.330°, as declared by that input. These
rounded run values differ from the original CIF's more precise cell and must not
be silently replaced. The initial model has 134 sites. The generated run reference
contains the same heavy population but carries the run cell, full-cell formula
C208 H256 N32 O32 S8, and no wavelength/Z/occupancy columns. It is not an archival
copy of all original CIF metadata.

The preserved `.inflip` has no wavelength directive; no matching `.m90` exists at
the recorded source path; the generated reference has no wavelength. The log and
cycle-5 repartitioning output nevertheless independently record **0.39986 Å**.
This is consistent with explicit Wizard entry or another reference selected at
the time. The preserved log does not prove the historical widget provenance.
The original CIF now supplied does explicitly contain 0.39986 Å.

The source confirms a UI resolution split: Wizard diagnostics previously asked a
cached Advanced backing window to collect its own inputs, whereas execution used
the current Wizard fields. Diagnostics now snapshot the Wizard's current reference
and explicit wavelength directly, while leaving cached manual metadata edits
untouched. Both validation and completeness use that same request and the existing
asynchronous/cancellable analysis path. Existing incoming-wavelength priorities
are preserved; competing `.inflip`/`.m90` metadata remains a separate audit issue.

Replaying the supplied reflections with the original CIF resolves 0.39986 Å and
gives 794 geometric overlap groups affecting 3,795 records, matching the recorded
cycle-5 grouping totals. The geometry remains an estimate for indexed records;
it is not a count of independently measured peaks. No uncertainty is inferred
from FWHM, and no run/map/export was recomputed for this investigation.

All 12 analyzed resolution shells reach 100% indexed coverage. The existing
`d_min` and `d98` coincide; an independent Gemmi d-spacing calculation confirms
the input resolution boundary. This validates the indexed-domain interpretation,
not independent experimental completeness. Detailed numeric reports stay local.

The run evidence establishes that execution used the declared `.inflip` cell and
space group. The reported Manual/Not set screenshot state still cannot be
reconstructed without the nine screenshots/session state. Diagnostic provenance
is now explicit, and no missing-manual-metadata execution defect was established.

## Validation

- Molecular correction plus existing viewer/camera/routing regressions: 21 passed.
- Wizard snapshot, synthetic cell-crossing cases and existing Wizard geometry/
  keyboard/action routing: 10 passed. The UI mocks were adapted to the new
  asynchronous route; original geometry and interaction assertions remain.
- Complete regression after the cell-crossing correction: **637 passed,
  4 skipped, 37 subtests passed in 515.10 seconds**. Existing skip conditions
  and scientific golden expectations are unchanged. The additional Wizard
  snapshot test is in the separately passing 10-test focused run.
- All eight scientific authority scripts were rerun and passed: core 46, Jana
  completion 195, Autosolve 79, workflow states 141, Result Selection 72, EDMA
  review 20, displacement 42 and fullscreen exit 0.
- Both Windows profiles were rebuilt from isolated `build/a207-cif`, passing
  native dependency, distribution and 407-file Jana ZIP verification. Both
  frozen GUI acceptance probes returned 0 with `ok: true`, version 2.0.7 and
  unchanged controlled inputs. Frozen runtime source hashes match the current
  working tree. Earlier 631-test/build results predate this correction.

Private machine-readable reports and input hashes stay in ignored
`build/audit-2.0.7/real-run/`. No original scientific file was edited, no scientific
exporter or execution algorithm changed, and no 2.0.7 release was published.


## November 1 palette and feedback follow-up

The user supplied the current screenshot folder. Later evidence, implementation, quantitative replay and remaining limitations are recorded in [the palette and feedback review](PALETTE_AND_FEEDBACK_DIAGNOSTICS_2_0_7.md). Earlier missing-evidence statements describe the investigation at that point; the exact original nine-image archive is still not identified.
