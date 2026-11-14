# Scientific structure comparison in 2.0.7

The comparison frame is now an explicit, saved viewer preference available in
the main comparison, fullscreen, Autosolve and Result Selection camera menus.
The original independent-component presentation remains the default.

* **Crystallographic frame** retains all independent heavy sites and unwraps
  geometric components consistently across periodic boundaries.
* **Reference-aligned · presentation only** additionally selects a space-group
  equivalent and integer cell translation for each whole geometric component.
  Every displayed site retains its original CIF site and symmetry provenance.
* Full-cell presentation retains the complete symmetry-expanded cell. It does
  not move individual components into a molecular overlay.

No CIF, map, EDMA threshold, selected candidate, scientific metric or Jana
handoff is modified. Camera orientation is retained. Main comparison panels use
the same Cartesian bounds and scale. Presentation provenance can be exported
locally as JSON from the camera menu; it contains private scientific coordinates
and is intentionally separate from the sanitized support bundle.

## Constraints and interpretation

Components come from geometric proximity, not chemical assignment. Alignment
allows only actual space-group operations and integer lattice translations;
there is no free rotation, atom-wise displacement or continuous origin fitting.
The implementation uses deterministic maximum-cardinality matching within
1.0 angstrom, not globally minimum RMSD or chemical identity matching. Component
placement is greedy and deterministic. EDMA element assignments are not treated
as verified chemistry. A match is positional evidence only.

Compatible cells require lengths within 0.02% and angles within 0.02 degrees.
For the real refined-reference pair the verified run cell is the common display
metric; both original and display cells are recorded. This changes only the
projection used for comparison. Incompatible cells, excessive lattice searches
and missing references report an unavailable alignment instead of a fabricated fit.

The singular-value lattice bound covers skew cells. Each site is checked against
its source symmetry orbit and integer translation. Provenance includes matched
pairs/distances, missing reference sites, unmatched displayed sites, component
operations, lattice shifts and reference-component coverage. Hydrogen/deuterium
and helium exclusions are distinguished from heavy-site counts.

## Recorded 25-cycle run audit

Read-only audit: `packaging/tools/audit_structure_comparison_207.py`. The private
inventory covers the original reference, all 50 saved result CIFs and 50 maps;
before/after SHA-256 identities are compared. Detailed coordinates and source
labels remain under ignored `build/alignment207/real-inventory-final/`.

| Cycle 25 source | Raw CIF heavy sites | Earlier primary + secondary displayed | New opt-in displayed | Within 1 A of reference | Reference sites unmatched |
| --- | ---: | ---: | ---: | ---: | ---: |
| Reference | 70 (134 total including 64 H) | 70 | 70 | 70 | 0 |
| Superflip | 63 | 44 + 5 | 63 | 63 | 7 |
| SharpED | 65 | 27 + 5 | 65 | 65 | 5 |

The reference contains two independent 35-heavy-site molecules (Z'=2 in P21/c,
Z=8). Both are represented geometrically in each cycle-25 result. The apparent
absence of a second molecule in the earlier 44/27-site panels is largely a
component-selection/presentation effect. It does not prove complete chemistry:
seven/five reference sites remain unmatched. The SharpED COO contains 87 raw
peaks but the saved thresholded CIF contains 65 sites; the additional peaks are
not invented as atoms or added to the viewer.

The older 62-reference-site defect was a separate periodic-neighbour frontier
problem, already corrected in the preceding work. The comparison baseline at
c523e27 includes that fix and therefore shows 70 reference sites, not 62.

## Verification

`tests/test_viewer_alignment_207.py` covers periodic boundaries, multiple
independent molecules, absent and partial components, symmetry equivalents,
integer translations, noisy/sparse results, skew lattices, full-cell preservation
and incompatible cells. Its real-widget subprocess exercises all four viewer
hosts, menu broadcasts, preserved camera orientation, artist coordinates and
local provenance export, and checks scientific file bytes and selected candidate
identity. The real-data inventory and captures use saved files only; no SharpED
request or scientific rerun is performed.
