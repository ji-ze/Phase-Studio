# Final logging, result review and artifact identity corrections

This work continues `development/2.0.7` and draft PR #21, including the preceding wavelength/camera correction. The input is the owner's saved November 4 run: five configured cycles, three completed, status `stopped`, and no confirmed final selection. Its 110 files (539,487,023 bytes) were inventoried before inspection. Original maps, reflections, structures, logs and manifests are read-only evidence. No paid SharpED request or new reconstruction is part of this work.

## Findings and classifications

| Finding | Classification | Evidence and correction |
| --- | --- | --- |
| Normalization log appears after SharpED upload starts | Not reproduced as a race in the supplied run | EDMA reads a separately named copy under `edma_superflip` or `edma_deblurred`. All eight original/normalized pairs have identical arrays, grids, cells and axis order. All three recorded multipart SHA-256 values match the original Superflip files. |
| Normalizer permits identical source/output paths | Confirmed defect, fixed | A reproducing test showed an in-place rewrite. Identical paths and hard-link aliases are now rejected with an actionable separate-output message. |
| Reader-specific output is exposed while being written | Confirmed defect, fixed | A deterministic paused-writer test observed partial target bytes. The existing serializer now writes a unique sibling temporary file and publishes it with `os.replace` only after completion. Failure retains the previous final artifact and removes the temporary file. |
| Normalization log names only a basename | Confirmed provenance ambiguity, fixed | Completion records identify source, final consumer path, full SHA-256 and cycle; corresponding structured events retain both artifact identities. No extra SharpED map copy is introduced. |
| Result Selection lacks execution-log access | Confirmed defect, fixed | A visible non-modal viewer reads existing `events.jsonl`, `run_manifest.json` and original logs. It supports full/scientific/warning views, selected cycle/family, search, copy, sanitized export and opening the original log. Changing filters does not select a candidate. |
| Normal log omits the graceful-stop request | Confirmed defect, fixed | The old request used diagnostic-only severity. `STOP_REQUESTED`, `FINISHING_CURRENT_CYCLE`, `CURRENT_CYCLE_COMPLETED`, `STOPPED_BY_USER` and `RESULTS_AVAILABLE` now flow through the existing event/log infrastructure. Requested and acknowledged stop states remain distinct. Immediate cancellation and failure remain distinct terminal outcomes. |
| Recommendation reasons/count meanings/export identity are hard to inspect | Presentation-only issues, fixed | `Why this cycle?` exposes the actual existing ranking rule and full values. Scrollable Details explains raw maxima, CIF sites, independent ASU sites, displayed positions, Jana sites and reference matches. Transfer details expose exact source identities and declared Jana destinations; standalone export reviews the chosen destination and filenames before confirmation. |
| Export can outlive the preview's artifact identity | Confirmed boundary defect, fixed | Hashes are checked again and the existing rollback-capable publication transaction verifies sealed expected hashes before publishing. A changed source or cancelled confirmation does not substitute another candidate. Export outcome is separate from confirmed selection and from Jana refinement. |
| Legacy `r_work`/`cc_work` can imply refinement validation | Scientific presentation issue, fixed | Display labels say work-set amplitude R/CC; existing machine keys remain compatible. Reports document imposed-amplitude agreement and the lack of independent validation without holdout. Numerical calculations and rankings are unchanged. |
| Fifth amplitude column is described as measured sigma | Scientific provenance concern, explicitly qualified | The actual incoming declaration is `dataformat amplitude dummy`, resolved mode `hkl F sigma`. Its auxiliary column does not establish experimental sigma(F). Details/provenance expose that limitation. No uncertainties are invented and legitimate uncertainty calculations are unchanged. |
| Disabled feedback produces redundant unavailable fields | Presentation-only issue, fixed | A concise disabled statement replaces operation-level prose when the recorded configuration is disabled. Original-input retention is asserted only with matching input hashes and reconciled inventory; otherwise retention is explicitly unestablished. Structured per-operation details remain available. |
| Saved log access depends on a live worker | Confirmed access gap, fixed | Main Open log can choose a saved run with no active worker. Review/export do not instantiate a writing RunProvenance for historical data. Incomplete JSONL tails are disclosed and preserved; unknown cycle/family/liveness is not fabricated. |

## Numerical and provenance evidence

For cycles 1, 2 and 3, the SHA-256 of the actual buffered multipart file bytes is respectively:

```
ad784674273f49c026d2895ae29c0703a9f47d8eca0963b5185e0e65109a5438
a08481ebc20c0335188d84045a2c03ef166ffa3d152206a5a3bd021394f28af5
3085f29d192a23904e3192f9f5fe652540e1648c0077b7aa59184e17bf92ff94
```

Each equals its saved original Superflip map. Array comparisons cover six EDMA copies and two normalized later-cycle model files; every maximum absolute density difference is zero. The usual writer precision and map-processing algorithms are retained. A separate synthetic test compares serialized normalized output with the established writer contract. Atomic publication changes file safety, not the numerical serializer.

Amplitude agreement uses nonnegative least-squares scale `s = dot(Fobs,Fcalc)/dot(Fcalc,Fcalc)`, then `sum(abs(Fobs-s*Fcalc))/sum(Fobs)`; CC is Pearson correlation. The measured and work subsets both contain all 4,540 observations in this no-holdout run. Thus `r_work == amplitude_rf` and `cc_work == amplitude_cc` for both families in all three cycles. Cycle 1 Superflip R is 1.1742701867135986e-6 with CC 0.9999999999988055; SharpED R is 0.4958838633423064 with CC 0.6269064627200678. Charge flipping's imposed amplitudes explain why near-perfect amplitude agreement need not establish correct phases. These are not conventional refined structural R_work values.

The reference-only rule remains Reference F0.5 descending, matched-peak RMSD ascending, then reference phase agreement descending; later metrics break ties only. Replaying the stored metrics using the unchanged authority still recommends Superflip cycle 2 and SharpED cycle 1. This is a read-only GUI replay, not a rerun of phasing, inference or refinement.

Recommendations are persisted from the existing report writer's recommendation objects, rather than calculated by a new logger. Selection stays Pending until confirmation. Export completion/failure, selected identities and native Jana handoff outcomes are separate records. Passing files does not certify that Jana refinement succeeded.

## Privacy and review behavior

Live and historical exports share one metadata-only sanitizer. Tests cover local/UNC paths, personal identifiers, API/OAuth credentials, Authorization/Bearer material and remote job IDs while retaining non-secret scientific values and hashes. Original maps/HKL/CIF files are not automatically included or uploaded. Local original logs remain available to their owner.

The new actions use the existing fixed review footer; they do not consume the scientific canvas on short windows. Long details use a scrollable dialog. The camera hint wraps, metadata remains accessible, and the existing minimum-canvas and footer assertions are retained. Legacy unassigned event families remain unknown rather than being inferred from the selected GUI tab.

## Validation and release boundaries

Local evidence is under `build/final-review207/`: the original file inventory, eight map comparisons, pre-fix failing atomic-write tests, controlled lifecycle/export/privacy tests, same-data GUI before/after replays and distribution acceptance captures. The final delivery manifest records exact full-suite counts, independent authority results, source SHA, build profiles, artifact sizes and SHA-256 values after all gates complete.

The mathematical bodies of amplitude metrics, map assessment and recommendation retain strict AST equality to the prior approved source. Existing FWHM/parser/filter/export mathematical baselines remain pinned. Only the reviewed normalization wrappers, file-publication boundary and report formatter receive a new immutable metadata/IO baseline, with independent numerical/byte-contract tests. No assertion, scientific golden or short-window minimum is relaxed.

Physical/mixed-monitor DPI, clean supported-Windows VM, live Jana GUI/refinement, paths over 260 characters and broader terminology sign-off remain separate manual gates. Experimental uncertainty origin, immutable remote checkpoints and uncontrolled historical random seeds cannot be recovered from a populated auxiliary column or a saved display name. No bitwise-reconstruction equivalence is claimed.

Published 2.0.6, SignPath preparation, signing keys and unrelated workshop work are preserved. PR #21 remains draft; no merge, v2.0.7 tag, public release, production signing or paid SharpED job is authorized or performed.
