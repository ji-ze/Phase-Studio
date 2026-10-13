# Phase Studio 2.0.2 — First Public 2.x Release

2.0.2 is the first public release of the 2.x generation. 2.0.0 and 2.0.1 were
internal builds. These notes describe the progression from public 1.0.10.

## Workflow experience

The Jana Wizard presents Superflip only, Superflip + SharpED, experimental
SharpED Autosolve and Professional mode. Recommended workflows run in a
focused execution window; Professional mode opens full configuration without
starting automatically. Model selection follows the cycle count unless the
user explicitly selects a manual override.

## Scientific processing and result review

Existing iterative Superflip/SharpED, HKL analysis and Map Feedback are retained.
Guided Autosolve adds phase-search and refinement review. Charge-flipping and
Model prediction retain independent completed results and cycle recommendations.
Result Selection and interactive atom-threshold control operate on the selected
completed source/cycle candidate. Complete-molecule and Full-cell views
distinguish independent detected sites from displayed symmetry images.

Normal EDMA defaults are 0.50σ per result family; Autosolve keeps its own policy.
EDMA-derived displacement exports use Biso-to-Uiso conversion and Uiso limits
of 0.010–0.150 Å². Lowering a peak threshold may leave the composition-constrained
Jana model unchanged, which is reported explicitly.

## Jana2020 integration

Selected maps and EDMA models are passed together through the Jana protocol.
Density conversion preserves the selected grid and coordinate frame rather
than repeating an origin search after atom extraction. Completed results
remain available after graceful stopping.

Jana developers receive `Phase_studio.exe` and the complete `_internal`
ONEDIR runtime. A separate Jana installer is not a 2.0.2 release asset.

## Windows application

The x64 standalone download remains ONEFILE, with no separate Python install.
Improvements include Windows TLS trust handling, responsive navigation and
Result Selection, consistent structure review, project-local diagnostics and
run-scoped incoming Jana input copies. Science Gothic Regular with zero
tracking is confined to the Phase Studio title and colored SharpED wordmark.

## Scientific and legal notices

Phase Studio is free open-source desktop software under MIT. Publications
reporting work performed with it should cite the software; README and
CITATION.cff supply the citation. Author and lead developer Jiří Zelenka is
affiliated with the Institute of Physics of the Czech Academy of Sciences.
SharpED developer credits are separate.

SharpED requires its own account, personal token and applicable current access
entitlement/service terms. MIT does not grant a SharpED subscription or model
weights. The supplied October 2026 preview terms expire on 31 October; later
service policy determines access and charges.

Predictions and recommendations require independent crystallographic validation.
Numerical/file tests do not establish actual Jana GUI import, map/atom alignment
or continuation acceptance, which remain pending on a real workstation.
