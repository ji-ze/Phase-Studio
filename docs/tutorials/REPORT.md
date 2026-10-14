# Tutorial implementation and acceptance report

Review date: 14 October 2026. Current source UI: **2.0.3**. Public release verified through GitHub's live release API: **v2.0.2**. Application behavior and version were not changed for this documentation task. Existing dirty application changes from earlier tasks were preserved. No commit, push, tag or publication was performed.

## A. Deliverables

All three PDFs have searchable text, embedded DejaVu Sans fonts, page numbers, clickable contents/outline navigation, external links, genuine captures, editorial numbered highlights and enlarged views. Exact sizes, hashes and screenshot counts follow below and are also in `sources/pdf_manifest.json`. Distribution copies are byte-identical and `dist/documentation/` contains only the three PDFs.

Standalone sections cover release/download/integrity, launch, local tools, SharpED access, input interpretation, validation, a local calculation, progress, results, exports and troubleshooting. Jana sections cover the integrated installation, input context, workflow choices, account access, cycles/model, completion, selection/threshold, handoff and continuation requirements. The complete guide covers the workflow, all 87 inventoried configuration controls, single-crystal and powder feedback, EDMA, viewers, metrics, ranking, graceful stop, handoff and scientific limitations.

## B. Screenshot sources and privacy

All application captures were newly rendered from the current actual PySide6 windows. No old-version screenshots, invented interfaces or AI-generated UI were used. The public input is a generated mathematical C6 ring in P1, with 665 synthetic intensity/uncertainty rows. The local Superflip/EDMA run genuinely completed one cycle and extracted a model at 0.50 sigma. Its map/model paths are recorded privately under `build/tutorials/local-run-result.json`.

Catalogue, prediction, metrics and staged progress/result-selection captures use clearly identified file-backed UI fixtures. They demonstrate controls and provenance, not a remotely solved structure or successful native Jana import. Original screenshot provenance is recorded in the source inventories; every illustrated section is listed in `step_screenshot_inventory.json`.

GitHub release/assets and the empty Jana login are genuine website captures made with fresh isolated Edge profiles. The actual authenticated SharpED controls were captured from the Chrome window identified by the user. The public crop excludes browser chrome, bookmarks, account identity and the existing-token table. No token was created/copied, password entered or browser credential store inspected. Raw private browser capture remains only in ignored local build storage, outside public assets. The public crop shows Show, an empty New token name field and Create token; it does not depict issuing a token or invent an account screen.

Pending approved real-machine captures: native Jana launch command/menu, the returned selected map/model in Jana, and normal Jana continuation. A collapsed/expanded browser sequence or a newly issued token is not claimed by the single sanitized controls crop. One beta control is hidden in the documented capture context; its scientific option is described, while its unavailable screenshot is explicitly recorded in the control inventory.

## C. Verified scientific semantics and limits

Authorities checked: current app input constructors and writer/feedback code; Jana Wizard/context/model policy; setup validation; authentication/storage; map-quality metrics; execution/result selection; structure camera; guided Autosolve policy; map and atomic displacement exports.

Verified distinctions include combined Wizard five-cycle default, exact catalogue-ID cycle recommendations and manual override, outer cycles versus Superflip iterations/repeats, one-cycle feedback inapplicability, I/sigma(I) versus F/sigma(F), FWHM versus uncertainty, strict positive significance cutoff, zero cutoff as uncertainty-independent map-supported correction, intensity blending/damping, delayed feedback and conservation of powder overlap-group intensity. Missing completion defaults to off with zero allowed additions. Normal EDMA thresholds are 0.50 sigma; guided Autosolve's separate 1.00-sigma policy is identified.

The writer authority revealed a stale normalization tooltip: every normalize keyword is currently omitted, including atoms/wilson/local/none. The guide describes the actual no-emission behavior and does not claim that changing this setting affects the generated input. Reference/manual metadata and disabled/imported settings are distinguished from fresh defaults.

The guide separates input composition, EDMA ASU composition, detected sites, displayed symmetry/periodic images and actual selected Jana atomic sites. It explains bounded exported Uiso (physical Biso conversion, then 0.010-0.150 square angstrom), corresponding PDB B factor, original measured-data metrics, R scaling, amplitude CC, C3, holdout limitations and per-family recommendations. Pictures, high scores and additional sites do not establish a valid structure.

Jana handoff documentation follows current source: selected scientific map and corresponding atomic model, original incoming .inflip/project context, requested native destinations, preserved original reflections, no previews or repeated phasing during handoff. This is source verification, not a new native Jana acceptance result.

Unresolved or deliberately unsupported definitions: version-specific raw Superflip/EDMA keyword syntax beyond the verified interface; undocumented RS/BL inference controls; a provider-approved direct public API-terms URL; future service model catalogue/entitlement and server-host migration. The verified account URL is https://sharped.fzu.cz/sharp-ed; the current client preset API remains https://jana.fzu.cz/. No working endpoints were changed. The web page's advertised API-host statement does not silently replace the current client configuration in this documentation pass.

## D. Visual and automated QA

All **141 pages** were rendered at 160% and visually inspected in complete contact sheets, with individual inspection of complex result selection, feedback, account, powder and parameter examples. Capture sizing was corrected to use the real Wizard layout adjustment so feedback fields are not clipped. Enlarged landscape views supplement overview screens; actual enlarged Qt control rows support the parameter reference. Source screenshots retain authentic UI branding; editorial markers do not alter application controls.

Automated checks passed for page bounds, nonblank searchable text, replacement glyphs, known private-name/token patterns in PDF text and public inventories, asset existence/readability, configuration-control coverage, embedded used fonts, font-licence attachment, internal link destinations, relative PDF links, TOC outlines and identical distribution copies. These checks do not constitute OCR proof for every raster pixel; the sanitized website crop and application imagery were also visually reviewed. External primary destinations were checked during source verification; not every external link was exhaustively retested in every viewer.

DejaVu licence source: https://dejavu-fonts.github.io/License.html. Copyright and permission notices are retained in `assets/DejaVu-font-license.txt` and attached inside each PDF. No proprietary font files are distributed.

## E. Distribution readiness

The PDFs and their editable sources are finished **review artifacts** suitable for repository review and internal preview. They are not yet accepted as final public GitHub/website documentation or bundled 2.0.3 standalone/Jana release manuals. Native Jana launch/return/continuation evidence and packaged 2.0.3 workstation acceptance remain required. The guides themselves disclose those limits and the current public 2.0.2/source 2.0.3 difference. They have not been published or added to an EXE/ZIP.

Local setup automation is accurately described as unavailable without approved distribution integrity/licensing authority. Existing Jana distributions provide their relevant tools under the active installation's SUPERFLIP directory; the guides do not send integrated users to an obsolete separate Jana installer.

## Exact final artifact metrics

| File | Pages | Bytes | Unique screenshot assets | Embedded image occurrences |
|---|---:|---:|---:|---:|
| [PhaseStudio_FirstUse_Jana2020.pdf](PhaseStudio_FirstUse_Jana2020.pdf) | 23 | 1,304,792 | 11 | 19 |
| [PhaseStudio_FirstUse_Standalone.pdf](PhaseStudio_FirstUse_Standalone.pdf) | 21 | 1,438,419 | 12 | 18 |
| [PhaseStudio_Superflip_SharpED_Complete_Guide.pdf](PhaseStudio_Superflip_SharpED_Complete_Guide.pdf) | 97 | 3,015,744 | 109 | 129 |

There are 125 public screenshot PNG assets overall, including 86 enlarged control-row captures. All 87 inventoried settings are documented. The hidden symmetrize_deblurred_map control is recorded as unavailable in the selected capture context.

SHA-256:

- `PhaseStudio_FirstUse_Jana2020.pdf`: `d35ac69ce7e7a2c135d27123b3d87d8f2cd4cb3be22f723511876bf703f80e8f`
- `PhaseStudio_FirstUse_Standalone.pdf`: `a8b322944398d0f5c6f5bf6a0a7054c502fc0056ecb6982c45dba6dffc5fe047`
- `PhaseStudio_Superflip_SharpED_Complete_Guide.pdf`: `21597453307bd175d78589b2c97bd9fccbc1ac2400d40a26cc587d4f346fb995`
