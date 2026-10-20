# EDMA peak protocol correction (2.0.6)

The earlier 2.0.2 release notes incorrectly identified EDMA peak density as
Biso. That statement and the reported clamp counts are superseded by this
verified correction. Historical project files are not rewritten.

The [official EDMA manual](https://superflip.fzu.cz/download/EDMA_user_manual.pdf)
defines the maxima table as coordinates, centre-of-charge coordinates,
integrated charge, peak density and basin volume. None is an atomic
displacement parameter. The public
[EDMA source package](https://superflip.fzu.cz/download/EDMA.tar.gz),
`EDMA_lib.f90`, `WriteStructure/WriteAtom`, distinguishes two m40 protocols:

* `m40forjana yes`: continuation contains peak density and integrated charge.
  These are preserved exactly for Jana's peak interpretation.
* Ordinary atomic m40 export: writes the configured Biso divided by 8π².
  This is already Uiso, not a per-peak displacement measurement.

Phase Studio no longer divides peak density by 8π² or clamps that result.
Its EDMA CIFs omit unknown ADPs, and PDBs leave the B-factor field blank.
Missing ADP is not a refined zero. A second confirmed parser error is fixed:
the nine-column maxima table must supply density from column eight, whereas
the previous parser supplied column four (the x coordinate of the centre of
charge). Four-column tables still supply density from column four. Correct
density can change which nearby maximum represents a merged group and which
element the existing density-based assignment selects. These are documented
scientific corrections, not merely reordered or visually modified structures.
The EDMA executable, peak extraction, composition rules and merge tolerance
are unchanged; maps and original measured reflections are not rewritten.
Explicit, finite physical ADPs still use the shared conversion and export
safety interval 0.010–0.150 Å². Peak interchange fields are exempt because
they are not ADPs; the normalizer rejects the two-field peak protocol.

Each new EDMA export records raw maxima and artifact hashes in a project-local
`*_provenance.json`. Canonical candidate promotion preserves this sidecar.
Old exports containing density-derived Uiso must be regenerated explicitly
from their scientific maps. Handoff does not silently rerun EDMA or rewrite
an immutable selected candidate.

EDMA peak candidates have unverified chemical connectivity. Their viewers
retain disconnected components and show atoms without claiming inferred
distance contacts are established chemical bonds. Symmetry-generated images
can increase displayed counts; the source asymmetric unit is unchanged.

Acceptance evidence, real-project per-site provenance, original-file hashes,
local EDMA replays and GUI screenshots are kept under the ignored directory
`build/acceptance-execution-integrity-2.0.6/`. Native Jana2020 acceptance is
separate from mocked handoff and offscreen Qt checks.
