# Phase Studio — Superflip + SharpED
## Complete Workflow and Settings Guide

<!-- DOCUMENT {"version": "2.0.3", "edition": "Development-source review edition", "filename": "PhaseStudio_Superflip_SharpED_Complete_Guide.pdf"} -->

<!-- PAGE {"title": "Edition, evidence and limitations", "image": null} -->
**Read this version note first.** These guides show the current 2.0.3 development-source interface, checked on 14 October 2026. The public release currently provides **v2.0.2**, with `PhaseStudio-2.0.2-x64.exe`. Some 2.0.3 setup, authentication and layout details differ. There is no published 2.0.3 binary in the verified release listing. Do not rename a 2.0.2 file to pretend it is 2.0.3.

Application screenshots are actual PySide6 renders. The teaching reflections and structures are synthetic and shareable, not a private or experimentally validated structure. Catalogue, prediction and staged-progress examples are identified as illustrative fixtures. Only the local Superflip/EDMA demonstration was actually calculated.

**Review edition:** native Jana2020 launch/return screenshots are awaiting approved capture; the authenticated SharpED token controls have been captured and sanitised. Their missing images are identified rather than replaced with invented screens. This edition is not final publication acceptance.

<!-- PAGE {"title": "The workflow in one page", "image": "screenshots/workflow/execution-completed.png", "landscape": true, "caption": "Actual GUI; combined processing state and scores are illustrative fixtures."} -->
**Phase Studio** is free, open-source crystallographic desktop software. It coordinates calculations, displays candidate structures and retains scientific outputs.

**Superflip** solves the crystallographic phase problem using charge flipping. **EDMA** locates atomic sites in electron-density maps. They are local, independently distributed programs with their own licences.

**SharpED** processes density maps online using machine learning. It uses your existing Jana2020 account; a separate SharpED registration is not needed. Free Phase Studio software does not imply free service inference or account entitlement.

Treat every model as a candidate. Check chemistry, symmetry and agreement with the original measured reflections, then refine independently. A convincing picture or a high apparent score is not proof of correctness.

One normal cycle runs charge flipping, produces a scientific map, processes it with SharpED when enabled, and extracts structures with EDMA according to selected options. A later cycle can receive a completed map/model seed and optionally derived reflections. These are separate mechanisms: map/model seeding is not the same as altering measured reflection input.

<!-- PAGE {"title": "The workflow in one page · enlarged view", "image": "screenshots/workflow/execution-completed.png", "landscape": true, "crop": null, "caption": "Actual GUI; combined processing state and scores are illustrative fixtures."} -->
Enlarged genuine application capture. For meaning, settings and fixture limitations, read the preceding page.

<!-- PAGE {"title": "1 · Verify input and optional models", "image": "screenshots/jana2020/wizard-input.png", "crop": "wizard-summary"} -->
Read Input Summary and expand optional files only when needed. The incoming .inflip supplies the Jana context; standalone external HKL requires validated manual/reference metadata.

Input composition is the Superflip search composition. EDMA ASU composition is calculated from the selected candidate; it is not a relabelled search composition.

A **Reference model** is evaluation/metadata context; **Initial model (cycle 1)** supplies a deliberate seed. An initial model may change cycle 1 from random phases. Later-cycle provenance identifies the actual reused source; cycle number alone cannot prove which seed was used.

<!-- PAGE {"title": "2 · Validate HKL before phasing", "image": "screenshots/workflow/hkl-validation.png", "crop": "validation"} -->
Validate HKL reports how rows/columns, uncertainties, phases and symmetry-unique reflections were interpreted. Check the selected layout and samples, not only a green status.

Amplitude formats use F and σ(F); intensity formats use I and σ(I). Intensity is converted to amplitude when required by crystallographic comparisons; phase-bearing formats keep their specified convention. FWHM formats store a peak width and do not supply a significance uncertainty.

Standalone manual metadata needs positive cell lengths, angles strictly between 0° and 180°, a resolvable space group and composition. Manual empty/Not set values are not physical metadata.

<!-- PAGE {"title": "3 · Understand completeness", "image": "screenshots/workflow/hkl-completeness.png"} -->
Analyze completeness enumerates theoretical symmetry-unique reflections within the observed reciprocal-space/resolution bounds and compares observed unique coverage in sinθ/λ bins. It reports dmin and the available coverage/statistical summaries, including the 98% cumulative point where defined.

Intensity/uncertainty curves depend on the selected format and available uncertainty. A width column cannot substitute for σ(I). Coverage outside the analyzed bounds is not demonstrated by the plot.

Use completeness to identify gaps and format/context issues. It does not independently validate phases, chemical connectivity or a neural prediction.

<!-- PAGE {"title": "4 · One cycle versus multiple cycles", "image": "screenshots/workflow/configuration-one-cycle.png"} -->
**Number of cycles** is 1–999 in the Wizard; its fresh combined-workflow Wizard default is 5, matching full configuration; Superflip-only recommends 1. Saved settings and imported context can override these values. One cycle is a single pass and cannot apply feedback to a later cycle.

Multiple cycles repeat the outer scientific stages. The first may use random phases or an explicit initial model; subsequent runs may use a completed SharpED map, another supported map, a structure seed or no seed according to actual configuration/provenance.

Superflip's **Maximum iterations** and **Repeat mode** are internal budgets, not the outer cycle count. When a model file seeds a Superflip cycle, the generated-input code forces repeatmode to 1. Do not multiply a displayed repeat preference blindly by every seeded cycle.

More cycles/trials take longer. Inspect candidates and independent diffraction agreement; extra computation is not proof of a better solution.

<!-- PAGE {"title": "5 · Automatic model selection", "image": "screenshots/workflow/configuration-multi-cycle.png"} -->
In the normal combined Wizard: 1 cycle → **PEAK A (model prediction)**; 2 or more → **SEED (cyclic CF)**, using exact catalogue IDs. The displayed catalogue is fetched dynamically and is not a permanent model list.

**Refresh** queries available models; its accessible name is Refresh models. The GUI reports the number available and any policy/catalogue error. If the required automatic model is unavailable, correct that condition rather than inventing a substitute.

Professional/full configuration has its own **Model: default** option, which resolves the server default. Do not mistake that explicit server-default choice for the Wizard's automatic PEAK A/SEED cycle policy.

<!-- PAGE {"title": "6 · Manual model selection", "image": "screenshots/workflow/configuration-manual.png"} -->
Choosing a model in the dropdown marks it **Manually selected**. Changing cycle count does not replace an available manual override. **Restore automatic** opts back into the cycle policy.

On refresh, a manual choice is preserved if the exact model remains available. If it disappears, the current implementation restores automatic mode and displays the removal notice. Do not assume the same catalogue exists on every date.

Model choice affects remote inference and may affect seeds/derived data used by later cycles. It is not merely a colour or camera preference. Model names do not reveal a scientifically verified architecture/training explanation; use provider documentation for those details.

<!-- PAGE {"title": "7 · Wizard SharpED settings", "image": "screenshots/workflow/wizard-sharped-settings.png"} -->
The actual disclosure is **Advanced SharpED settings**. It exposes a masked **SharpED access key** and **Account access…**. The normal Wizard does not expose a server URL editor, output-resolution editor, element constraints or RS/BL controls.

Account access opens the reusable Connect dialog without launching a scientific workflow. The key is session-only unless explicitly remembered securely. Back/browser round trips preserve the configured scientific fields.

For output sampling, elements, value transform and network controls, use **Professional mode → Advanced → SharpED** when that broader configuration is required. Do not invent desktop fields from web-only options.

<!-- PAGE {"title": "8 · Generate the SharpED access key", "image": "screenshots/web/sharped-token-controls.png"} -->
1. In Phase Studio, click **Open SharpED token page**. The official destination is [https://sharped.fzu.cz/sharp-ed](https://sharped.fzu.cz/sharp-ed).
2. If redirected, sign in on the website with your existing Jana2020 account. Never enter your Jana password into Phase Studio.
3. On the SharpED Tool page, find **API tokens for desktop application** and click **Show**.
4. Enter a descriptive **New token name**, for example `Phase Studio laptop`, and click **Create token**.
5. Copy the newly generated access key, return to Phase Studio and paste it into **SharpED access key**.
6. Click **Connect to SharpED** to continue your original workflow.

**Verified website capture:** the accompanying authenticated-page crop shows the actual **API tokens for desktop application**, **Show**, **New token name** and **Create token** controls. Account identity, browser details and the existing-token table are excluded. No token was created or copied during documentation capture.

<!-- PAGE {"title": "9 · Authentication and entitlement", "image": "screenshots/web/jana-login.png", "crop": "web-login"} -->
The access-key field is masked. **Show/Hide** changes only visibility; do not expose a key in screenshots. **Remember access on this device** explicitly enables Windows Credential Manager storage; otherwise the key stays in memory for the session. **Replace access key** and **Remove saved access** manage that access. **Back** returns with scientific settings preserved.

Connect checks service/catalogue reachability and retains the supplied key. The public catalogue request does **not** prove inference entitlement or authenticated token validity. An authenticated processing request can still reject the key or account permission.

There is no automatic OAuth browser-to-desktop token delivery in this version. Copy and paste the key yourself. The account website and the client Public API host are different: keep the preset API configuration; do not replace it with the token-page URL.

Only send data that you are authorised to share with the remote service. Check current provider terms and entitlement before inference. No permanent free-access promise or price is made in this guide.

<!-- PAGE {"title": "10 · Advanced inference controls", "image": "screenshots/workflow/professional-sharped.png", "crop": "configuration"} -->
**Elements:** blank derives unique non-H elements from the configured composition/reference; an explicit element list constrains the submitted inference request. Check chemistry rather than restricting elements to force a desired answer.

**Output resolution (Å):** 0.001–10.0; constructor default 0.2. It is sent as `outres`. The client describes requested sampling/resolution; it does not establish that the network creates new experimental information. Detailed server interpretation requires provider clarification.

**Map value exponent:** 0–10; the live default is listed in the parameter reference. A signed power transform sign(x)|x|^a is applied before submission and inverted on the returned map. 1 is identity; 0 disables the transform. It changes voxel values for processing, not cell/grid/origin. A changed exponent can still change the nonlinear inference output.

No RS/BL fields are present in this desktop configuration. Their scientific meaning is not guessed here.

<!-- PAGE {"title": "11 · Transfer and network limits", "image": "screenshots/workflow/professional-sharped.png", "crop": "configuration"} -->
**Upload limit (MB):** 0–100000, default 100; 0 disables the client's limit check. If the voxel grid was omitted, the workflow can choose a coarser native grid before map calculation to fit the limit. Oversized maps may use the existing tiled submission/reassembly path; do not assume this changes the scientific frame.

**HTTP timeout (s):** 600–7200, default 600. **Polling interval (s):** 1–3600, default 2. **Maximum polls:** −1–1000000, default −1 (Unlimited). These affect waiting/transport, not the charge-flipping mathematics; too short a wait/limit may fail a legitimate long inference.

Keep the preset API endpoint. The token website is `https://sharped.fzu.cz/sharp-ed`; the current client Public API defaults to `https://jana.fzu.cz/`. Some inherited tooltips mention the web host; the actual client constant and request code are authoritative.

<!-- PAGE {"title": "12 · Map Feedback changes later input", "image": "screenshots/workflow/feedback-one-cycle-disabled.png"} -->
Map Feedback uses a completed processed map to prepare derived reflections for subsequent cycles. The original measured dataset and frozen validation context remain distinguishable from the derived HKL files. It is not the same as supplying a next-cycle phase seed.

Methods are optional and initially off. **Start after cycle** means the completed cycle whose map first feeds the next one; useful choices need a subsequent cycle. In the Wizard the maximum is the preceding cycle of the budget. For one cycle the controls are unavailable while remembered values are retained.

When both supported methods are enabled, the implemented order is missing completion/intensity correction, then powder overlap repartitioning, then write the next-cycle input. Validate every changed-input result against the original measurement, not just the derived input.

<!-- PAGE {"title": "13 · Missing-reflection completion", "image": "screenshots/workflow/feedback-missing-reflections.png"} -->
**Enable missing-reflection completion:** off by default. **Start after cycle:** default 1; outer-cycle dependent. **Maximum added reflections (%):** 0–100, default 0.

Candidate missing HKLs are selected within the existing observed index bounds and resolution limit. Positive map-predicted intensities are scaled to the observed data and ranked; additions are capped by the specified fraction of the current count. Zero percent adds no reflections, even if the checkbox is on.

These are inferred values, not newly measured reflections. Additions can influence later cycles and must not be treated as independent observations validating the model that supplied them.

<!-- PAGE {"title": "14 · Weak-reflection correction with σ", "image": "screenshots/workflow/feedback-single-crystal.png"} -->
**Enable weak-reflection intensity correction** is off initially. **Start after cycle** defaults to 1. **Correction damping** is 0–1, default 0. A positive **I/σ(I) limit** threshold selects eligible positive finite values with finite positive matching uncertainty.

The filter always uses I/σ(I). For amplitude data it estimates I/σ(I) ≈ F/[2σ(F)] by first-order propagation of I=F² and σ(I)≈2Fσ(F). This does not recover original experimental intensity significance, particularly for weak reflections. A limit of 2 approximately corresponds to F/σ(F)<4. The correction itself blends intensities, with F converted through its intensity representation and converted back.

Inew = (1 − d)Iobs + d × scaled Imap. The scale uses the median of positive observed/predicted intensity ratios. d=0 is no correction; d=1 uses the scaled map prediction for eligible rows. A significance cutoff is strict: a ratio equal to the threshold is not selected.

Use a nonzero cutoff only when the input actually supplies the correct experimental uncertainty.

<!-- PAGE {"title": "15 · Threshold zero and width-only data", "image": "screenshots/workflow/feedback-powder.png"} -->
**I/σ(I) limit = 0** means uncertainty-independent correction, not I/σ(I)<0. It bypasses the significance test and applies where the map predicts a positive intensity. The implementation can also affect zero observed values; do not interpret older “non-zero reflections” copy as a restriction excluding them.

For **h k l · I · FWHM**, no σ(I) is supplied. The significance field is unavailable; the verified threshold-zero correction remains possible with positive damping. FWHM is never silently used as an experimental uncertainty.

The powder screenshot states the missing-uncertainty condition explicitly. This is a distinct mode, not evidence that every weak-reflection operation is valid for every format.

<!-- PAGE {"title": "16 · Powder overlap repartitioning", "image": "screenshots/workflow/feedback-powder.png", "crop": "powder-controls"} -->
Available only for supported FWHM formats. **Enable powder overlap repartitioning (FWHM data)** is off initially. **Start after cycle** defaults to 1. **Wavelength (Å)** is 0–10, default 0 (automatic); the resolved value must be positive.

Automatic wavelength uses the relevant Jana .m90, then input wavelength declarations, then the reference wavelength where available. Enter the actual experiment's wavelength if it cannot be resolved. The pictured 1.00000 Å is a synthetic teaching value.

**Separation factor:** 0.001–100, default 0.2. Adjacent Bragg peaks are grouped transitively when Δ(2θ) < factor × (FWHM1+FWHM2)/2; widths must use consistent angular units.

**Map ratio mix:** 0–1, default 1. It blends observed within-group shares with shares implied by map-predicted intensities. Zero retains observed shares; one uses predicted shares. Each overlap group's total observed intensity is conserved. This still changes individual reflection inputs for later cycles.

<!-- PAGE {"title": "17 · Cross-validation is an opt-in", "image": "screenshots/workflow/configuration-multi-cycle.png"} -->
**Compute OMIT validation maps** is unchecked for a fresh Wizard job and is not silently inherited from old job settings. It freezes a symmetry/Friedel-orbit-safe 5% holdout and excludes those HKLs from all work-data/feedback stages of the omit branch.

**Calculate R_free** follows the OMIT choice automatically and is not independently editable in that Wizard state. Extra omit Superflip/SharpED work roughly increases the per-cycle cost; exact time depends on the job.

The holdout must genuinely be withheld. Metrics of an arbitrary imported map that may have used those reflections are not automatically independent. In full configuration these are the corresponding Optional processing settings; preserve their actual dependency rules.

<!-- PAGE {"title": "18 · EDMA threshold and atomic sites", "image": "screenshots/workflow/selector-edma-pending.png", "landscape": true} -->
Normal Charge-flipping solution and Model prediction extraction defaults are **0.50σ**. The threshold is applied relative to the map's standard-deviation scale in the generated EDMA workflow, not as a probability that a peak is an atom.

**+ atoms** lowers the threshold; from 0.50σ it requests 0.40σ. **− atoms** raises it to 0.60σ. Step policy is 0.20σ at/above the 0.80σ boundary, 0.10σ below it and 0.05σ below 0.30σ, with direction-aware boundary handling and guided range 0.10–3.00σ.

Lower thresholds may reveal additional sites or noise. Higher thresholds may remove weak real sites. The interaction reruns EDMA only on the completed candidate's unchanged scientific map; it does not rerun Superflip/SharpED or silently change candidate family/cycle.

<!-- PAGE {"title": "18 · EDMA threshold and atomic sites · enlarged view", "image": "screenshots/workflow/selector-edma-pending.png", "landscape": true, "crop": null, "caption": "Actual application UI; synthetic teaching input / labelled demonstration state."} -->
Enlarged genuine application capture. For meaning, settings and fixture limitations, read the preceding page.

<!-- PAGE {"title": "19 · Four different atom counts", "image": "screenshots/workflow/selector-model-prediction.png", "landscape": true} -->
**Raw EDMA peaks** are extraction output before cleanup. **EDMA candidate sites** are the retained independent sites in the actual selected structure. **ASU composition** reduces that candidate using its symmetry. **Displayed atoms** may include periodic/symmetry images. **Jana model sites** are the composition-constrained list in the actual returned model.

These counts can differ legitimately. No display expansion creates independent measured atoms. More EDMA peaks after lowering a threshold do not imply that every new peak is written as a Jana atom.

If the Jana model is “prepared during handoff,” an exact count is not asserted yet. A completed/sealed model's reported count is authoritative. The screenshot deliberately illustrates a count distinction using fixture artifacts, not an accepted native Jana import.

<!-- PAGE {"title": "19 · Four different atom counts · enlarged view", "image": "screenshots/workflow/selector-model-prediction.png", "landscape": true, "crop": null, "caption": "Actual application UI; synthetic teaching input / labelled demonstration state."} -->
Enlarged genuine application capture. For meaning, settings and fixture limitations, read the preceding page.

<!-- PAGE {"title": "20 · Read execution progress", "image": "screenshots/workflow/execution-concurrent.png", "landscape": true} -->
**Charge-flipping solution** is the Superflip map/EDMA result; **Model prediction** is the SharpED-processed map/EDMA result. The panels track their own selected completed source/cycle and camera.

Overall progress counts the outer workflow budget; current-operation progress identifies active stages. Superflip repeat progress is an internal trial counter. Server processing may have an indeterminate interval when no meaningful percentage is available.

Completed structures can appear during other work. Concurrent labels describe active operations, not a claim that every stage starts simultaneously. Use **Execution Log**, **Expand log** and **Open log** for current messages and project-local details.

<!-- PAGE {"title": "20 · Read execution progress · enlarged view", "image": "screenshots/workflow/execution-concurrent.png", "landscape": true, "crop": null, "caption": "Actual application UI; synthetic teaching input / labelled demonstration state."} -->
Enlarged genuine application capture. For meaning, settings and fixture limitations, read the preceding page.

<!-- PAGE {"title": "21 · Rotate, pan, zoom and Fit", "image": "screenshots/workflow/viewer-complete-molecules.png", "landscape": true} -->
Drag with the left mouse button to rotate. Middle/right drag or Shift+left drag pans. The mouse wheel zooms the pointed panel. **Fit** reframes displayed content without changing orientation; **Reset view** restores the default camera. F and R are their keyboard shortcuts, and Space toggles Auto rotate where supported.

**Auto rotate** animates the camera, not atomic coordinates. Turn it off for careful comparison. **Fullscreen** opens the selected structure in a detached viewer retaining its current orientation; it does not create a new candidate.

Each result panel preserves its own camera during ordinary redraw. A different candidate/representation can warrant an automatic fit. Camera transformations never modify fractional coordinates, occupancy, symmetry or exported models.

<!-- PAGE {"title": "21 · Rotate, pan, zoom and Fit · enlarged view", "image": "screenshots/workflow/viewer-complete-molecules.png", "landscape": true, "crop": null, "caption": "Actual application UI; synthetic teaching input / labelled demonstration state."} -->
Enlarged genuine application capture. For meaning, settings and fixture limitations, read the preceding page.

<!-- PAGE {"title": "22 · Complete molecules versus Full cell", "image": "screenshots/workflow/viewer-full-cell.png", "landscape": true} -->
**Complete molecules** assembles compact periodic fragments from the selected density-derived sites for viewing. Atoms may cross unit-cell boundaries so the connected fragment can be inspected. It does not prove that a disconnected peak cloud is a chemically valid molecule; finite framework fragments have their own display policy.

**Full cell** shows the symmetry-expanded cell representation and unit-cell frame. Repeated/symmetry-related images are display atoms, not additional independent EDMA detections.

Use both views to inspect boundary connectivity, duplicates and symmetry. Neither changes the selected candidate's scientific coordinates or the returned Jana context.

<!-- PAGE {"title": "22 · Complete molecules versus Full cell · enlarged view", "image": "screenshots/workflow/viewer-full-cell.png", "landscape": true, "crop": null, "caption": "Actual application UI; synthetic teaching input / labelled demonstration state."} -->
Enlarged genuine application capture. For meaning, settings and fixture limitations, read the preceding page.

<!-- PAGE {"title": "23 · Browse completed candidates", "image": "screenshots/workflow/execution-completed.png", "landscape": true} -->
Use the available previous/next candidate controls to inspect completed cycles. **Latest** follows the newest completed candidate for that panel; it is not necessarily the recommended/best candidate. A manual selection can be inspected while another cycle runs.

Do not infer seed provenance from the row number. Read **Superflip initialization** and **Reflection input** metadata: an explicitly supplied first-cycle model, reused map/model or derived-reflection input changes scientific lineage.

A running threshold update does not replace the authoritative last completed candidate. Wait for its candidate-specific completion before passing the requested new threshold.

<!-- PAGE {"title": "23 · Browse completed candidates · enlarged view", "image": "screenshots/workflow/execution-completed.png", "landscape": true, "crop": null, "caption": "Actual application UI; synthetic teaching input / labelled demonstration state."} -->
Enlarged genuine application capture. For meaning, settings and fixture limitations, read the preceding page.

<!-- PAGE {"title": "24 · Choose a family and cycle", "image": "screenshots/workflow/selector-manual-candidate.png", "landscape": true} -->
Result Selection uses separate **Charge-flipping solution** and **Model prediction** families, with candidate cycle rows and an independent recommendation per family. A recommendation star does not lock your choice.

Click a row, then check selected-family/cycle summary, EDMA threshold, ASU composition, Jana model and provenance. Returning to Phase Studio is a review/navigation action, not a handoff.

The **Pass to Jana2020** action operates on the selected completed candidate, even when it differs from the recommendation. It remains unavailable for an incomplete/invalid/pending candidate. A standalone result context does not expose Jana handoff.

<!-- PAGE {"title": "24 · Choose a family and cycle · enlarged view", "image": "screenshots/workflow/selector-manual-candidate.png", "landscape": true, "crop": null, "caption": "Actual application UI; synthetic teaching input / labelled demonstration state."} -->
Enlarged genuine application capture. For meaning, settings and fixture limitations, read the preceding page.

<!-- PAGE {"title": "25 · What R factor and Amplitude CC mean", "image": "screenshots/workflow/selector-charge-flipping.png", "landscape": true} -->
For finite nonnegative observed amplitudes Fo and Fourier-derived map amplitudes Fc, the client fits a nonnegative scale s = max(0, ΣFoFc/ΣFc²), then calculates R = Σ|Fo − sFc|/ΣFo. Fo comes from the frozen original measured reflections, including the existing intensity-to-amplitude conversion.

**Amplitude CC** is Pearson correlation of those same observed/calculated amplitude arrays; it is unavailable when there are too few pairs or insufficient variance. It is not an independent atomic refinement residual.

If Superflip imposed the observed amplitudes, R≈0 and CC≈1 can follow by construction even with incorrect phases. Different phase maps can have the same amplitude scores. Rounded equal scores need not be an internal ranking tie.

No universal correctness cutoff is supplied. Interpret these values with provenance, phase-sensitive information and independent crystallographic validation.

<!-- PAGE {"title": "25 · What R factor and Amplitude CC mean · enlarged view", "image": "screenshots/workflow/selector-charge-flipping.png", "landscape": true, "crop": null, "caption": "Actual application UI; synthetic teaching input / labelled demonstration state."} -->
Enlarged genuine application capture. For meaning, settings and fixture limitations, read the preceding page.

<!-- PAGE {"title": "26 · C3, holdout and recommendations", "image": "screenshots/workflow/selector-model-prediction.png", "landscape": true} -->
**C3** is the weighted mean cos[φ(h)+φ(k)−φ(h+k)] from the map Fourier phases. Triplet weights are products of original measured amplitudes normalised by their RMS; the deterministic set is bounded by 64 strong seeds and 50,000 triplets. C3 is not an amplitude correlation or refinement residual and does not prove a correct structure.

With a genuine frozen holdout, R_free/CC_free compare excluded original amplitudes to Fourier amplitudes from the relevant omit result; R_free requires at least three usable pairs. Reference-based profiles may show reference match/phase agreement and RMSD instead. A reference that seeded the run is not independent evidence.

Ranking uses the active profile's ordered, directional criteria and tie-breakers, not a universal combined score. Families have separate recommendations. Check the scientific warning and why a candidate is recommended rather than choosing the largest-looking number.

<!-- PAGE {"title": "26 · C3, holdout and recommendations · enlarged view", "image": "screenshots/workflow/selector-model-prediction.png", "landscape": true, "crop": null, "caption": "Actual application UI; synthetic teaching input / labelled demonstration state."} -->
Enlarged genuine application capture. For meaning, settings and fixture limitations, read the preceding page.

<!-- PAGE {"title": "27 · Graceful stop and early handoff", "image": "screenshots/workflow/execution-completed.png", "landscape": true} -->
**Stop after current cycle** completes the current cycle and retains valid completed results; **Stop immediately** cancels active work. Previously completed valid candidates can remain available, but unfinished output is not a valid replacement.

The execution-window Pass action can request early handoff when a valid completed candidate exists. The confirmation stops further scientific work, waits for a safe terminal state, then opens result review. It does not send an arbitrary half-finished map immediately.

Confirm a completed candidate in the selector. No source family/cycle/threshold should be inferred solely from whichever panel happened to look newest. Native early-return acceptance still needs real Jana verification.

<!-- PAGE {"title": "27 · Graceful stop and early handoff · enlarged view", "image": "screenshots/workflow/execution-completed.png", "landscape": true, "crop": null, "caption": "Actual application UI; synthetic teaching input / labelled demonstration state."} -->
Enlarged genuine application capture. For meaning, settings and fixture limitations, read the preceding page.

<!-- PAGE {"title": "28 · Return the scientific map and model", "image": "screenshots/workflow/selector-manual-candidate.png", "landscape": true} -->
**Pass to Jana2020** validates and transfers the actual selected map, matching structure/model and original context. It checks candidate identity and scientific files rather than using preview geometry. Completed EDMA threshold selection is respected; raw extra peaks need not alter the composition-constrained Jana atom list.

The map grid/origin and atomic coordinate frame must remain aligned. No Superflip/SharpED recomputation occurs just to pass a completed candidate. Output names derive from the incoming Jana .inflip declarations, not a fixed standalone naming guess.

**Acceptance gap:** native Jana launch, imported map/model alignment and normal continuation require approved real-machine screenshots/testing. The fixture selector below does not claim that those checks have been completed.

<!-- PAGE {"title": "28 · Return the scientific map and model · enlarged view", "image": "screenshots/workflow/selector-manual-candidate.png", "landscape": true, "crop": null, "caption": "Actual application UI; synthetic teaching input / labelled demonstration state."} -->
Enlarged genuine application capture. For meaning, settings and fixture limitations, read the preceding page.

<!-- PAGE {"title": "29 · Interpreting your results", "image": null} -->
Charge flipping is a crystallographic structure-solution method; SharpED is machine-learning map processing. Both outputs still require crystallographic interpretation. Neural predictions may contain artifacts, missing sites or plausible but incorrect density.

EDMA peaks must be judged against chemistry, symmetry, connectivity and original diffraction information. Additional display atoms or attractive molecular fragments do not add independent evidence. A high apparent score can reflect imposed amplitudes or a reused reference.

Preserve the original experiment separately from feedback-modified inputs. Compare candidates, inspect uncertainty/coverage and refine independently in an appropriate crystallographic program. No screenshot or synthetic demonstration in this guide is an experimentally established new structure.

<!-- PAGE {"title": "30 · Professional mode: use it deliberately", "image": "screenshots/workflow/professional-superflip.png", "crop": "configuration"} -->
Professional mode exposes full Basic/Advanced control without auto-running. The following parameter reference covers every stored input control present in the current full GUI, including options unavailable in normal Superflip + SharpED processing.

Defaults are constructor values in a fresh full configuration, unless marked imported/context-dependent. Wizard defaults, presets, saved settings and .inflip imports can override them. Disabled options are not silently active just because a remembered value is displayed.

Most scientific controls feed external program keywords. Where the client only passes a keyword and does not establish a complete numerical interpretation, that limitation is stated; consult the applicable official Superflip/EDMA manual rather than inferring a scientific guarantee from a label.

<!-- PAGE {"title": "Parameter reference · Input · 1", "image": "screenshots/standalone/standalone-input.png", "crop": "configuration", "reference": true, "keys": ["input_source_mode", "jana_inflip"]} -->
**Input mode** · `input_source_mode`

**Allowed:** Jana2020 .inflip; Jana2020 .inflip with external HKL/reference overrides; External HKL + CIF reference. **Fresh full-configuration default:** External HKL + CIF reference.

Choose whether reflections come from Jana2020 .inflip, selected overrides, or an external HKL file.

Changes input interpretation/metadata or the first seed; affects scientific computation. Disabled context fields are ignored. Change only to match the actual experiment/model, not to improve the displayed score.

---

**Jana2020 .inflip file** · `jana_inflip`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** project/input dependent; no universal personal path.

Jana2020 Superflip input file. In Jana modes its fbegin/endf reflection block is the default HKL source, and its cell/space-group/composition keywords can provide the reference metadata.

Changes input interpretation/metadata or the first seed; affects scientific computation. Disabled context fields are ignored. Change only to match the actual experiment/model, not to improve the displayed score.

<!-- PAGE {"title": "Parameter reference · Input · 2", "image": "screenshots/standalone/standalone-input.png", "crop": "configuration", "reference": true, "keys": ["hkl", "reflection_data_mode"]} -->
**External HKL file** · `hkl`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** project/input dependent; no universal personal path.

External reflection file. In Jana override mode it replaces only the fbegin/endf reflection block; in external mode it is the required reflection source.

Changes input interpretation/metadata or the first seed; affects scientific computation. Disabled context fields are ignored. Change only to match the actual experiment/model, not to improve the displayed score.

---

**HKL format** · `reflection_data_mode`

**Allowed:** Set from .inflip; h k l · I · σ(I); h k l · F · σ(F); h k l · I · phase · σ(I); h k l · F · phase · σ(F); h k l · I · FWHM; h k l · F · FWHM. **Fresh full-configuration default:** h k l · I · σ(I).

Exact HKL column order. 'Set from .inflip' imports Jana's dataformat. The other choices use the displayed h k l · value · optional phase · uncertainty layout. Phase is in degrees; Phase Studio converts it to Superflip turns. FWHM choices describe peak width, not measurement uncertainty, so sigma-based statistics are hidden or relabeled I/FWHM.

Changes input interpretation/metadata or the first seed; affects scientific computation. Disabled context fields are ignored. Change only to match the actual experiment/model, not to improve the displayed score.

<!-- PAGE {"title": "Parameter reference · Input · 3", "image": "screenshots/standalone/standalone-input.png", "crop": "configuration", "reference": true, "keys": ["metadata_source", "reference_cif"]} -->
**Metadata source** · `metadata_source`

**Allowed:** Jana2020 .inflip; Reference structure; Manual. **Fresh full-configuration default:** Jana2020 .inflip.

Selects the authoritative source for unit-cell, space-group and composition metadata, independently of the reflection-data source -- for example, External HKL input with metadata taken from a Jana2020 .inflip or reference structure.

Changes input interpretation/metadata or the first seed; affects scientific computation. Disabled context fields are ignored. Change only to match the actual experiment/model, not to improve the displayed score.

---

**Reference model** · `reference_cif`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** project/input dependent; no universal personal path.

Optional external reference. CIF/INS/RES files can provide metadata and atom sites; Jana/XPLOR/CCP4 maps can be Superflip reference densities.

Changes input interpretation/metadata or the first seed; affects scientific computation. Disabled context fields are ignored. Change only to match the actual experiment/model, not to improve the displayed score.

<!-- PAGE {"title": "Parameter reference · Input · 4", "image": "screenshots/standalone/standalone-input.png", "crop": "configuration", "reference": true, "keys": ["first_cycle_modelfile", "manual_cell_a"]} -->
**Initial model (cycle 1)** · `first_cycle_modelfile`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** project/input dependent; no universal personal path.

Optional external density or structure model for cycle 1. Supported Superflip modelfile inputs are XPLOR, CCP4 and CIF.

Changes input interpretation/metadata or the first seed; affects scientific computation. Disabled context fields are ignored. Change only to match the actual experiment/model, not to improve the displayed score.

---

**a** · `manual_cell_a`

**Allowed:** 0.0 to 10000.0. **Fresh full-configuration default:** 0.

Manual unit-cell a length in Å; 0 means Not set. A valid calculation needs a positive physical value. Used only with Manual metadata.

Changes input interpretation/metadata or the first seed; affects scientific computation. Disabled context fields are ignored. Change only to match the actual experiment/model, not to improve the displayed score.

<!-- PAGE {"title": "Parameter reference · Input · 5", "image": "screenshots/standalone/standalone-input.png", "crop": "configuration", "reference": true, "keys": ["manual_cell_alpha", "manual_cell_b"]} -->
**alpha** · `manual_cell_alpha`

**Allowed:** 0.0 to 179.99999. **Fresh full-configuration default:** 0.

Manual cell angle α in degrees; 0 is Not set, not a valid angle. Physical angles must be strictly between 0 and 180. Used only with Manual metadata.

Changes input interpretation/metadata or the first seed; affects scientific computation. Disabled context fields are ignored. Change only to match the actual experiment/model, not to improve the displayed score.

---

**b** · `manual_cell_b`

**Allowed:** 0.0 to 10000.0. **Fresh full-configuration default:** 0.

Manual unit-cell b length in Å; 0 means Not set. A valid calculation needs a positive physical value. Used only with Manual metadata.

Changes input interpretation/metadata or the first seed; affects scientific computation. Disabled context fields are ignored. Change only to match the actual experiment/model, not to improve the displayed score.

<!-- PAGE {"title": "Parameter reference · Input · 6", "image": "screenshots/standalone/standalone-input.png", "crop": "configuration", "reference": true, "keys": ["manual_cell_beta", "manual_cell_c"]} -->
**beta** · `manual_cell_beta`

**Allowed:** 0.0 to 179.99999. **Fresh full-configuration default:** 0.

Manual cell angle β in degrees; 0 is Not set, not a valid angle. Physical angles must be strictly between 0 and 180. Used only with Manual metadata.

Changes input interpretation/metadata or the first seed; affects scientific computation. Disabled context fields are ignored. Change only to match the actual experiment/model, not to improve the displayed score.

---

**c** · `manual_cell_c`

**Allowed:** 0.0 to 10000.0. **Fresh full-configuration default:** 0.

Manual unit-cell c length in Å; 0 means Not set. A valid calculation needs a positive physical value. Used only with Manual metadata.

Changes input interpretation/metadata or the first seed; affects scientific computation. Disabled context fields are ignored. Change only to match the actual experiment/model, not to improve the displayed score.

<!-- PAGE {"title": "Parameter reference · Input · 7", "image": "screenshots/standalone/standalone-input.png", "crop": "configuration", "reference": true, "keys": ["manual_cell_gamma", "manual_spacegroup_number"]} -->
**gamma** · `manual_cell_gamma`

**Allowed:** 0.0 to 179.99999. **Fresh full-configuration default:** 0.

Manual cell angle γ in degrees; 0 is Not set, not a valid angle. Physical angles must be strictly between 0 and 180. Used only with Manual metadata.

Changes input interpretation/metadata or the first seed; affects scientific computation. Disabled context fields are ignored. Change only to match the actual experiment/model, not to improve the displayed score.

---

**Number** · `manual_spacegroup_number`

**Allowed:** 0 to 230. **Fresh full-configuration default:** 0.

International space-group number 1–230; displayed 0 is Not set. Resolve a consistent number/symbol for Manual metadata.

Changes input interpretation/metadata or the first seed; affects scientific computation. Disabled context fields are ignored. Change only to match the actual experiment/model, not to improve the displayed score.

<!-- PAGE {"title": "Parameter reference · Input · 8", "image": "screenshots/standalone/standalone-input.png", "crop": "configuration", "reference": true, "keys": ["manual_spacegroup_symbol", "manual_composition"]} -->
**Symbol** · `manual_spacegroup_symbol`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** blank.

Space-group symbol entered for Manual metadata; it must resolve consistently with any supplied number. An empty/unresolvable symbol is not validated symmetry.

Changes input interpretation/metadata or the first seed; affects scientific computation. Disabled context fields are ignored. Change only to match the actual experiment/model, not to improve the displayed score.

---

**Composition** · `manual_composition`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** blank.

Element/count composition for Manual metadata; blank is unset. Supply a valid formula for the actual crystallographic cell/search context. It is not a promise that EDMA will detect that exact ASU composition.

Changes input interpretation/metadata or the first seed; affects scientific computation. Disabled context fields are ignored. Change only to match the actual experiment/model, not to improve the displayed score.

<!-- PAGE {"title": "Parameter reference · Workflow · 1", "image": "screenshots/standalone/standalone-workflow.png", "crop": "configuration", "reference": true, "keys": ["workflow_preset", "cycles"]} -->
**Workflow preset** · `workflow_preset`

**Allowed:** Recommended; Custom; MOF atomic resolution; MOF medium resolution; small molecule; inorganic. **Fresh full-configuration default:** Recommended.

Loads a group of settings rather than one scientific scalar. Recommended is the constructor choice; confirm resulting values because a preset/import can override individual constructor defaults. It does not itself certify result quality.

Changes enabled stages, cycle budget or next-cycle seeding. Review dependent controls after changing it; one-cycle/disabled-stage values are not silently active. Use only when the required local tools/account/data exist.

---

**Cycles** · `cycles`

**Allowed:** 1 to 999. **Fresh full-configuration default:** 5.

Number of iterative Superflip → EDMA → SharpED → EDMA cycles to run.

Changes enabled stages, cycle budget or next-cycle seeding. Review dependent controls after changing it; one-cycle/disabled-stage values are not silently active. Use only when the required local tools/account/data exist.

<!-- PAGE {"title": "Parameter reference · Workflow · 2", "image": "screenshots/standalone/standalone-workflow.png", "crop": "configuration", "reference": true, "keys": ["reconstruction_mode", "damping_factor"]} -->
**Phasing method** · `reconstruction_mode`

**Allowed:** Superflip. **Fresh full-configuration default:** Superflip.

Superflip runs the standard charge-flipping cycle every cycle (unchanged default). '1st Superflip, then SharpED (beta)' runs Superflip only once, then each cycle deblurs with SharpED, reads phi_calc by FFT from that SharpED map for every measured hkl, and recomposes a map from |Fobs| + phi_calc for the next cycle; it does not work well with some models. 'SharpED (experimental)' skips Superflip entirely and starts cycle 1 from |Fobs| with independent random phases; it does not work yet and is intended for development, not production use. Hidden unless 'Show beta and experimental features' is enabled on Advanced -> Setup.

Changes enabled stages, cycle budget or next-cycle seeding. Review dependent controls after changing it; one-cycle/disabled-stage values are not silently active. Use only when the required local tools/account/data exist.

---

**XPLOR damping (1/x)** · `damping_factor`

**Allowed:** 0.001 to 1.0. **Fresh full-configuration default:** 0.3.

Inverse XPLOR damping 1/x, not Map Feedback correction damping. x=1 has no damping; x=.5 gives factor 2. Existing map blending uses the reciprocal factor and is relevant only to XPLOR next-cycle seeds. CIF/None disable/ignore it.

Changes enabled stages, cycle budget or next-cycle seeding. Review dependent controls after changing it; one-cycle/disabled-stage values are not silently active. Use only when the required local tools/account/data exist.

<!-- PAGE {"title": "Parameter reference · Workflow · 3", "image": "screenshots/standalone/standalone-workflow.png", "crop": "configuration", "reference": true, "keys": ["exclude_atoms", "sharped_model"]} -->
**Excluded atoms** · `exclude_atoms`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** none.

Optional atom labels to remove from CIF modelfiles before the next Superflip cycle. Use comma, semicolon or whitespace separation.

Changes enabled stages, cycle budget or next-cycle seeding. Review dependent controls after changing it; one-cycle/disabled-stage values are not silently active. Use only when the required local tools/account/data exist.

---

**Model** · `sharped_model`

**Allowed:** default. **Fresh full-configuration default:** default.

SharpED server model name. Use default to query /sharp-ed/models and select the server default.

Changes enabled stages, cycle budget or next-cycle seeding. Review dependent controls after changing it; one-cycle/disabled-stage values are not silently active. Use only when the required local tools/account/data exist.

<!-- PAGE {"title": "Parameter reference · Workflow · 4", "image": "screenshots/standalone/standalone-workflow.png", "crop": "configuration", "reference": true, "keys": ["run_edma_superflip", "run_sharped"]} -->
**Run EDMA on Superflip map** · `run_edma_superflip`

**Allowed:** On / Off. **Fresh full-configuration default:** on.

Run EDMA peak search on the Superflip XPLOR map and write CIF, XYZ and PDB structure exports.

Changes enabled stages, cycle budget or next-cycle seeding. Review dependent controls after changing it; one-cycle/disabled-stage values are not silently active. Use only when the required local tools/account/data exist.

---

**Run SharpED** · `run_sharped`

**Allowed:** On / Off. **Fresh full-configuration default:** on.

Run SharpED server deblurring on the Superflip XPLOR map. If disabled, the SharpED map is a copy of the Superflip map.

Changes enabled stages, cycle budget or next-cycle seeding. Review dependent controls after changing it; one-cycle/disabled-stage values are not silently active. Use only when the required local tools/account/data exist.

<!-- PAGE {"title": "Parameter reference · Workflow · 5", "image": "screenshots/standalone/standalone-workflow.png", "crop": "configuration", "reference": true, "keys": ["symmetrize_deblurred_map", "run_edma_deblurred"]} -->
**Symmetrize SharpED map with Superflip (beta)** · `symmetrize_deblurred_map`

**Allowed:** On / Off. **Fresh full-configuration default:** off.

After SharpED deblurring, run Superflip in perform symmetry mode with the deblurred XPLOR as modelfile. No charge flipping is performed; the output map is averaged according to the supplied space-group symmetry and is then used for EDMA, Jana export, feedback and later-cycle XPLOR modelfiles.

Changes enabled stages, cycle budget or next-cycle seeding. Review dependent controls after changing it; one-cycle/disabled-stage values are not silently active. Use only when the required local tools/account/data exist.

---

**Run EDMA on SharpED map** · `run_edma_deblurred`

**Allowed:** On / Off. **Fresh full-configuration default:** on.

Run EDMA peak search on the SharpED XPLOR map. Disable this when you only want map export or Superflip EDMA results.

Changes enabled stages, cycle budget or next-cycle seeding. Review dependent controls after changing it; one-cycle/disabled-stage values are not silently active. Use only when the required local tools/account/data exist.

<!-- PAGE {"title": "Parameter reference · Workflow · 6", "image": "screenshots/standalone/standalone-workflow.png", "crop": "configuration", "reference": true, "keys": ["compute_omit_maps", "compute_omit_rfree"]} -->
**Compute OMIT validation maps (5% holdout)** · `compute_omit_maps`

**Allowed:** On / Off. **Fresh full-configuration default:** off.

Freeze a symmetry/Friedel-orbit-safe 5% holdout before the workflow and exclude it from every work-data and feedback step. Enables cross-validation metrics and profile-aware result recommendation for both Superflip and SharpED. Roughly doubles Superflip/SharpED time per cycle.

Changes enabled stages, cycle budget or next-cycle seeding. Review dependent controls after changing it; one-cycle/disabled-stage values are not silently active. Use only when the required local tools/account/data exist.

---

**Calculate R_free on the 5% holdout** · `compute_omit_rfree`

**Allowed:** On / Off. **Fresh full-configuration default:** off.

R_free is calculated automatically whenever the frozen 5% holdout is enabled because it is a primary cross-validation metric. Result recommendation uses explicit lexicographic criteria; no combined numeric score is created.

Changes enabled stages, cycle budget or next-cycle seeding. Review dependent controls after changing it; one-cycle/disabled-stage values are not silently active. Use only when the required local tools/account/data exist.

<!-- PAGE {"title": "Parameter reference · Workflow · 7", "image": "screenshots/standalone/standalone-workflow.png", "crop": "configuration", "reference": true, "keys": ["run_edma_recycle_final", "modelfile_source"]} -->
**Run EDMA on final map** · `run_edma_recycle_final`

**Allowed:** On / Off. **Fresh full-configuration default:** off.

Applies to the beta/experimental phase-recycling methods, not ordinary Superflip cycling; it is disabled/hidden in the standard workflow. Enabling it extracts the final recycling map, not every standard cycle.

Changes enabled stages, cycle budget or next-cycle seeding. Review dependent controls after changing it; one-cycle/disabled-stage values are not silently active. Use only when the required local tools/account/data exist.

---

**Next-cycle model** · `modelfile_source`

**Allowed:** Superflip map (XPLOR); SharpED map (XPLOR); SharpED structure (EDMA CIF); None. **Fresh full-configuration default:** SharpED map (XPLOR).

Controls the actual seed for cycle 2 onward: Superflip map (XPLOR), SharpED map (XPLOR), SharpED structure (EDMA CIF), or None. Constructor default is SharpED map. None forces a one-cycle workflow; XPLOR damping is irrelevant for CIF/None. Selection/provenance, not cycle number alone, determines the seed.

Changes enabled stages, cycle budget or next-cycle seeding. Review dependent controls after changing it; one-cycle/disabled-stage values are not silently active. Use only when the required local tools/account/data exist.

<!-- PAGE {"title": "Parameter reference · Map feedback · 1", "image": "screenshots/standalone/standalone-map-feedback.png", "crop": "configuration", "reference": true, "keys": ["map_feedback_missing_enabled", "map_feedback_missing_from_cycle"]} -->
**Enable missing-reflection completion** · `map_feedback_missing_enabled`

**Allowed:** On / Off. **Fresh full-configuration default:** off.

Enables missing-reflection completion. When off, the fields below are ignored.

Affects derived reflection input for subsequent cycles only when the corresponding method is enabled and a later cycle exists. Original measured reflections remain distinct. Validate the changed-input result against them.

---

**Start after cycle** · `map_feedback_missing_from_cycle`

**Allowed:** 1 to 999. **Fresh full-configuration default:** 1.

First completed cycle whose map is used to add missing reflections for the next cycle.

Affects derived reflection input for subsequent cycles only when the corresponding method is enabled and a later cycle exists. Original measured reflections remain distinct. Validate the changed-input result against them.

<!-- PAGE {"title": "Parameter reference · Map feedback · 2", "image": "screenshots/standalone/standalone-map-feedback.png", "crop": "configuration", "reference": true, "keys": ["map_feedback_missing_percent_limit", "map_feedback_intensity_enabled"]} -->
**Maximum added reflections (%)** · `map_feedback_missing_percent_limit`

**Allowed:** 0.0 to 100.0. **Fresh full-configuration default:** 0.0.

Maximum number of added missing reflections, expressed as a percent of the current HKL count. This prevents map feedback from overwhelming measured data.

Affects derived reflection input for subsequent cycles only when the corresponding method is enabled and a later cycle exists. Original measured reflections remain distinct. Validate the changed-input result against them.

---

**Enable intensity correction** · `map_feedback_intensity_enabled`

**Allowed:** On / Off. **Fresh full-configuration default:** off.

Enables map-based intensity correction. When off, the fields below are ignored.

Affects derived reflection input for subsequent cycles only when the corresponding method is enabled and a later cycle exists. Original measured reflections remain distinct. Validate the changed-input result against them.

<!-- PAGE {"title": "Parameter reference · Map feedback · 3", "image": "screenshots/standalone/standalone-map-feedback.png", "crop": "configuration", "reference": true, "keys": ["map_feedback_intensity_from_cycle", "map_feedback_intensity_damping"]} -->
**Start after cycle** · `map_feedback_intensity_from_cycle`

**Allowed:** 1 to 999. **Fresh full-configuration default:** 1.

First completed cycle whose map is used to damp observed intensities for the next cycle.

Affects derived reflection input for subsequent cycles only when the corresponding method is enabled and a later cycle exists. Original measured reflections remain distinct. Validate the changed-input result against them.

---

**Correction damping** · `map_feedback_intensity_damping`

**Allowed:** 0.0 to 1.0. **Fresh full-configuration default:** 0.0.

Damping factor for map-based intensity correction. 0 keeps observed data; 1 replaces them by scaled map-derived intensities.

Affects derived reflection input for subsequent cycles only when the corresponding method is enabled and a later cycle exists. Original measured reflections remain distinct. Validate the changed-input result against them.

<!-- PAGE {"title": "Parameter reference · Map feedback · 4", "image": "screenshots/standalone/standalone-map-feedback.png", "crop": "configuration", "reference": true, "keys": ["map_feedback_intensity_max_i_over_sigma", "redistribute_overlaps"]} -->
**I/σ(I) limit** · `map_feedback_intensity_max_i_over_sigma`

**Allowed:** 0.0 to 1000.0. **Fresh full-configuration default:** 0.0.

The strict positive-cutoff filter always uses I/σ(I); amplitudes use the first-order estimate F/[2σ(F)]. Stored numerical limits are retained unchanged. Historical amplitude settings used direct F/σ(F); explicitly halve an old limit only if you want to preserve its approximate selection. No automatic migration is performed. Zero bypasses the significance filter: eligible rows have positive map-predicted intensity and can include zero observed values. A nonzero cutoff is unavailable for FWHM-only data without experimental uncertainty.

Affects derived reflection input for subsequent cycles only when the corresponding method is enabled and a later cycle exists. Original measured reflections remain distinct. Validate the changed-input result against them.

---

**Enable powder overlap repartitioning (FWHM data)** · `redistribute_overlaps`

**Allowed:** On / Off. **Fresh full-configuration default:** off.

Enables powder overlap repartitioning: each cycle, redistribute the combined observed intensity of overlapping-reflection groups (hkl I/F fwhm data only) between their members, using intensities calculated by FFT from that cycle's processed map. When off, the fields below are ignored.

Affects derived reflection input for subsequent cycles only when the corresponding method is enabled and a later cycle exists. Original measured reflections remain distinct. Validate the changed-input result against them.

<!-- PAGE {"title": "Parameter reference · Map feedback · 5", "image": "screenshots/standalone/standalone-map-feedback.png", "crop": "configuration", "reference": true, "keys": ["powder_redistribution_from_cycle", "powder_wavelength"]} -->
**Start after cycle** · `powder_redistribution_from_cycle`

**Allowed:** 1 to 999. **Fresh full-configuration default:** 1.

First completed cycle whose map is used to redistribute overlapping powder reflections for the next cycle.

Affects derived reflection input for subsequent cycles only when the corresponding method is enabled and a later cycle exists. Original measured reflections remain distinct. Validate the changed-input result against them.

---

**Wavelength (Å)** · `powder_wavelength`

**Allowed:** 0.0 to 10.0. **Fresh full-configuration default:** 0.0.

Radiation wavelength in Å, required to compute 2θ for powder overlap repartitioning. If left at 0, it is auto-detected from the Jana .m90 file, then the .inflip file's lambda/wavelength line, then from the reference file's _diffrn_radiation_wavelength tag; enter it manually if neither source has it.

Affects derived reflection input for subsequent cycles only when the corresponding method is enabled and a later cycle exists. Original measured reflections remain distinct. Validate the changed-input result against them.

<!-- PAGE {"title": "Parameter reference · Map feedback · 6", "image": "screenshots/standalone/standalone-map-feedback.png", "crop": "configuration", "reference": true, "keys": ["powder_separation_factor", "powder_redistribution_mix"]} -->
**Separation factor** · `powder_separation_factor`

**Allowed:** 0.001 to 100.0. **Fresh full-configuration default:** 0.2.

Multiplier of the mean FWHM (in the same 2θ-like units as the data) used to decide whether two reflections' Bragg peaks overlap: delta(2θ) < separation_factor * (FWHM1 + FWHM2) / 2. Matches Superflip's own fwhmseparation keyword.

Affects derived reflection input for subsequent cycles only when the corresponding method is enabled and a later cycle exists. Original measured reflections remain distinct. Validate the changed-input result against them.

---

**Map ratio mix** · `powder_redistribution_mix`

**Allowed:** 0.0 to 1.0. **Fresh full-configuration default:** 1.0.

Blend factor for powder overlap repartitioning: 0 keeps each reflection's observed share of its group's total intensity; 1 replaces it entirely with the share implied by intensities calculated from the processed map. The group total is always conserved regardless of this value.

Affects derived reflection input for subsequent cycles only when the corresponding method is enabled and a later cycle exists. Original measured reflections remain distinct. Validate the changed-input result against them.

<!-- PAGE {"title": "Parameter reference · Output · 1", "image": "screenshots/standalone/standalone-output.png", "crop": "configuration", "reference": true, "keys": ["work_dir", "map_export_format"]} -->
**Working directory** · `work_dir`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** project/input dependent; no universal personal path.

Output directory for generated HKL files, Superflip inputs, maps, EDMA results, logs and metrics.

Changes output location or additional external file formats, not camera/atomic coordinates. Required internal scientific files remain. Choose a new project-local folder and formats appropriate for the receiving program.

---

**Map format** · `map_export_format`

**Allowed:** xplor; ccp4; jana; HKL reflections with phases; ShelX (fcf). **Fresh full-configuration default:** xplor.

XPLOR is always produced internally (EDMA and SharpED require it). xplor keeps only that working map; ccp4 or jana additionally saves a CCP4 map or Jana m80/m81 density+reflection files. 'HKL reflections with phases' and 'ShelX (fcf)' instead save, for each cycle's Superflip map, the observed |Fobs|/intensity together with phases (and, for ShelX, calculated F squared) read by FFT from that map, in a standardized text file or a ShelX/Jana-compatible .fcf file.

Changes output location or additional external file formats, not camera/atomic coordinates. Required internal scientific files remain. Choose a new project-local folder and formats appropriate for the receiving program.

<!-- PAGE {"title": "Parameter reference · Output · 2", "image": "screenshots/standalone/standalone-output.png", "crop": "configuration", "reference": true, "keys": ["structure_export_format"]} -->
**Structure format** · `structure_export_format`

**Allowed:** cif; xyz; pdb. **Fresh full-configuration default:** cif.

CIF is always produced internally (used for metrics and next-cycle modelfiles). xyz or pdb additionally saves that structure format alongside the CIF.

Changes output location or additional external file formats, not camera/atomic coordinates. Required internal scientific files remain. Choose a new project-local folder and formats appropriate for the receiving program.

<!-- PAGE {"title": "Parameter reference · Setup · 1", "image": "screenshots/workflow/professional-setup.png", "crop": "configuration", "reference": true, "keys": ["superflip_exe", "edma_exe"]} -->
**Superflip executable** · `superflip_exe`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** active/validated installation; no single drive is required.

Absolute path to the active Jana2020 scientific Superflip executable. Default: <active Jana2020 root>\SUPERFLIP\superflip.exe.

Configures program/service access or exposes optional UI features. It does not alter measured reflection values merely by being edited. Use verified installed programs/current service settings.

---

**EDMA executable** · `edma_exe`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** active/validated installation; no single drive is required.

Absolute path to the Jana2020 EDMA executable used for peak extraction and structure export from XPLOR density maps. Default: C:\Jana2020\SUPERFLIP\EDMA.exe.

Configures program/service access or exposes optional UI features. It does not alter measured reflection values merely by being edited. Use verified installed programs/current service settings.

<!-- PAGE {"title": "Parameter reference · Setup · 2", "image": "screenshots/workflow/professional-setup.png", "crop": "configuration", "reference": true, "keys": ["sharped_base_url", "sharped_api_token"]} -->
**Server URL** · `sharped_base_url`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** https://jana.fzu.cz/.

Actual client default is https://jana.fzu.cz/. This is a Public API base, not the https://sharped.fzu.cz/sharp-ed account page. Leave it unchanged for the normal service. The inherited web-host tooltip is stale; the client constant/request code is authoritative.

Configures program/service access or exposes optional UI features. It does not alter measured reflection values merely by being edited. Use verified installed programs/current service settings.

---

**SharpED access key** · `sharped_api_token`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** blank.

Private access key for the existing Jana account. Empty until supplied; session-only unless explicitly remembered in Windows Credential Manager. Never publish it. Catalogue reachability is not token/inference-entitlement validation.

Configures program/service access or exposes optional UI features. It does not alter measured reflection values merely by being edited. Use verified installed programs/current service settings.

<!-- PAGE {"title": "Parameter reference · Setup · 3", "image": "screenshots/workflow/professional-setup.png", "crop": "configuration", "reference": true, "keys": ["show_beta_features"]} -->
**Show beta and experimental features** · `show_beta_features`

**Allowed:** On / Off. **Fresh full-configuration default:** off.

Off initially. Reveals otherwise hidden beta/experimental phasing methods and their controls. It does not make those methods equivalent to the normal Superflip + SharpED workflow or scientifically validated.

Configures program/service access or exposes optional UI features. It does not alter measured reflection values merely by being edited. Use verified installed programs/current service settings.

<!-- PAGE {"title": "Parameter reference · Superflip · 1", "image": "screenshots/workflow/professional-superflip.png", "crop": "configuration", "reference": true, "keys": ["perform_algorithm", "maxcycles"]} -->
**Algorithm** · `perform_algorithm`

**Allowed:** CF; AAR; lde; general; fourier; symmetry. **Fresh full-configuration default:** CF.

External Superflip perform keyword. CF is normal charge flipping; alternatives AAR, lde, general, fourier and symmetry invoke distinct external operations. Keep CF for this tutorial. The client does not fully define every algorithm mathematically; use the official manual/version-specific interface before changing it.

Controls external phasing input/trials/map construction, not just display. Imported .inflip/preset values may replace fresh defaults. For optional/raw keyword syntax and scientific use consult the official manual for the actual executable.

---

**Maximum iterations** · `maxcycles`

**Allowed:** 1 to 100000. **Fresh full-configuration default:** 2000.

Maximum number of Superflip iterations per run.

Controls external phasing input/trials/map construction, not just display. Imported .inflip/preset values may replace fresh defaults. For optional/raw keyword syntax and scientific use consult the official manual for the actual executable.

<!-- PAGE {"title": "Parameter reference · Superflip · 2", "image": "screenshots/workflow/professional-superflip.png", "crop": "configuration", "reference": true, "keys": ["repeatmode", "randomseed"]} -->
**Repeat mode** · `repeatmode`

**Allowed:** 1 to 10000. **Fresh full-configuration default:** 10.

Superflip repeatmode parameter controlling repeated independent attempts and convergence sampling.

Controls external phasing input/trials/map construction, not just display. Imported .inflip/preset values may replace fresh defaults. For optional/raw keyword syntax and scientific use consult the official manual for the actual executable.

---

**Random seed** · `randomseed`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** AUTO.

Random seed passed to Superflip. Use a fixed value for reproducibility or Superflip-supported automatic syntax if desired.

Controls external phasing input/trials/map construction, not just display. Imported .inflip/preset values may replace fresh defaults. For optional/raw keyword syntax and scientific use consult the official manual for the actual executable.

<!-- PAGE {"title": "Parameter reference · Superflip · 3", "image": "screenshots/workflow/professional-superflip.png", "crop": "configuration", "reference": true, "keys": ["delta", "weakratio"]} -->
**Delta** · `delta`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** AUTO.

Superflip delta keyword. AUTO lets Superflip estimate the flip threshold.

Controls external phasing input/trials/map construction, not just display. Imported .inflip/preset values may replace fresh defaults. For optional/raw keyword syntax and scientific use consult the official manual for the actual executable.

---

**Weak ratio** · `weakratio`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** 0.000.

Superflip weakratio keyword.

Controls external phasing input/trials/map construction, not just display. Imported .inflip/preset values may replace fresh defaults. For optional/raw keyword syntax and scientific use consult the official manual for the actual executable.

<!-- PAGE {"title": "Parameter reference · Superflip · 4", "image": "screenshots/workflow/professional-superflip.png", "crop": "configuration", "reference": true, "keys": ["biso", "polish"]} -->
**Biso** · `biso`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** 0.000.

Overall isotropic B factor used to sharpen the map. Use 0.000 if no sharpening is wanted.

Controls external phasing input/trials/map construction, not just display. Imported .inflip/preset values may replace fresh defaults. For optional/raw keyword syntax and scientific use consult the official manual for the actual executable.

---

**Enable final polish** · `polish`

**Allowed:** On / Off. **Fresh full-configuration default:** on.

Adds 'polish yes' to the Superflip input, enabling Superflip's final polishing/refinement stage when supported by the executable.

Controls external phasing input/trials/map construction, not just display. Imported .inflip/preset values may replace fresh defaults. For optional/raw keyword syntax and scientific use consult the official manual for the actual executable.

<!-- PAGE {"title": "Parameter reference · Superflip · 5", "image": "screenshots/workflow/professional-superflip.png", "crop": "configuration", "reference": true, "keys": ["voxel", "bestdensities_count"]} -->
**Voxel grid** · `voxel`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** .

Superflip voxel grid. The default omit/blank skips the keyword. Use three integers, for example 180 80 160, or AUTO to compute a 0.2 A grid from the unit cell.

Controls external phasing input/trials/map construction, not just display. Imported .inflip/preset values may replace fresh defaults. For optional/raw keyword syntax and scientific use consult the official manual for the actual executable.

---

**Stored best densities** · `bestdensities_count`

**Allowed:** 1 to 100. **Fresh full-configuration default:** 1.

First argument of bestdensities: how many best density maps Superflip keeps.

Controls external phasing input/trials/map construction, not just display. Imported .inflip/preset values may replace fresh defaults. For optional/raw keyword syntax and scientific use consult the official manual for the actual executable.

<!-- PAGE {"title": "Parameter reference · Superflip · 6", "image": "screenshots/workflow/professional-superflip.png", "crop": "configuration", "reference": true, "keys": ["bestdensities_metric", "searchsymmetry"]} -->
**Density selection metric** · `bestdensities_metric`

**Allowed:** rvalue; peakiness; symmetry; reference. **Fresh full-configuration default:** symmetry.

Second argument of bestdensities: rvalue, peakiness, symmetry or reference. 'symmetry' biases saved-density selection toward symmetry-consistent solutions.

Controls external phasing input/trials/map construction, not just display. Imported .inflip/preset values may replace fresh defaults. For optional/raw keyword syntax and scientific use consult the official manual for the actual executable.

---

**Search symmetry** · `searchsymmetry`

**Allowed:** average; shift; no. **Fresh full-configuration default:** average.

Superflip searchsymmetry keyword: no, shift or average.

Controls external phasing input/trials/map construction, not just display. Imported .inflip/preset values may replace fresh defaults. For optional/raw keyword syntax and scientific use consult the official manual for the actual executable.

<!-- PAGE {"title": "Parameter reference · Superflip · 7", "image": "screenshots/workflow/professional-superflip.png", "crop": "configuration", "reference": true, "keys": ["derivesymmetry", "i_over_sigma_min"]} -->
**Derive symmetry** · `derivesymmetry`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** yes.

Superflip derivesymmetry keyword. Common values are yes, no or use, depending on Superflip version.

Controls external phasing input/trials/map construction, not just display. Imported .inflip/preset values may replace fresh defaults. For optional/raw keyword syntax and scientific use consult the official manual for the actual executable.

---

**Minimum observed value/σ** · `i_over_sigma_min`

**Allowed:** 0.0 to 100.0. **Fresh full-configuration default:** 2.0.

Pre-run observed value/uncertainty filter, distinct from Map Feedback's later correction cutoff. It uses the selected reflection representation when writing scientific input; do not treat a FWHM width as measurement significance.

Controls external phasing input/trials/map construction, not just display. Imported .inflip/preset values may replace fresh defaults. For optional/raw keyword syntax and scientific use consult the official manual for the actual executable.

<!-- PAGE {"title": "Parameter reference · Superflip · 8", "image": "screenshots/workflow/professional-superflip.png", "crop": "configuration", "reference": true, "keys": ["resolution_d_min", "normalize"]} -->
**High-resolution cutoff dmin (Å)** · `resolution_d_min`

**Allowed:** 0.0 to 20.0. **Fresh full-configuration default:** 0.0.

Optional resolution cutoff in Angstrom. 0 keeps all reflections; 1.2 keeps only reflections with d >= 1.2 A.

Controls external phasing input/trials/map construction, not just display. Imported .inflip/preset values may replace fresh defaults. For optional/raw keyword syntax and scientific use consult the official manual for the actual executable.

---

**Normalization** · `normalize`

**Allowed:** none; local; atoms; wilson. **Fresh full-configuration default:** atoms.

Constructor default is atoms. The current compatibility writer omits the normalize keyword for EVERY selection (atoms, wilson, local and none). This stored choice currently has no emitted normalization effect; the inherited tooltip is not the writer authority.

Controls external phasing input/trials/map construction, not just display. Imported .inflip/preset values may replace fresh defaults. For optional/raw keyword syntax and scientific use consult the official manual for the actual executable.

<!-- PAGE {"title": "Parameter reference · Superflip · 9", "image": "screenshots/workflow/professional-superflip.png", "crop": "configuration", "reference": true, "keys": ["nresshells", "missing"]} -->
**Resolution shells** · `nresshells`

**Allowed:** 0 to 100000. **Fresh full-configuration default:** 100.

Stored resolution-shell count. The writer omits every normalize keyword; this setting has no emitted normalization effect in the current implementation.

Controls external phasing input/trials/map construction, not just display. Imported .inflip/preset values may replace fresh defaults. For optional/raw keyword syntax and scientific use consult the official manual for the actual executable.

---

**Missing reflections** · `missing`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** bound 0.5 2.5.

Optional Superflip missing-data keyword line, for example bounds for missing reflections.

Controls external phasing input/trials/map construction, not just display. Imported .inflip/preset values may replace fresh defaults. For optional/raw keyword syntax and scientific use consult the official manual for the actual executable.

<!-- PAGE {"title": "Parameter reference · Superflip · 10", "image": "screenshots/workflow/professional-superflip.png", "crop": "configuration", "reference": true, "keys": ["electrons", "extra_superflip_keywords"]} -->
**Electrons** · `electrons`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** .

Superflip electrons keyword. Leave blank to omit.

Controls external phasing input/trials/map construction, not just display. Imported .inflip/preset values may replace fresh defaults. For optional/raw keyword syntax and scientific use consult the official manual for the actual executable.

---

**Extra Superflip keywords** · `extra_superflip_keywords`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** blank.

Additional documented Superflip keyword lines before fbegin. Blank by default. No GUI numerical range; invalid/version-unsupported syntax can fail the external run. Do not override generated context blindly.

Controls external phasing input/trials/map construction, not just display. Imported .inflip/preset values may replace fresh defaults. For optional/raw keyword syntax and scientific use consult the official manual for the actual executable.

<!-- PAGE {"title": "Parameter reference · EDMA · 1", "image": "screenshots/workflow/professional-edma.png", "crop": "configuration", "reference": true, "keys": ["plimit_superflip", "plimit_deblur"]} -->
**Superflip threshold** · `plimit_superflip`

**Allowed:** 0.0 to 100.0. **Fresh full-configuration default:** 0.5.

Threshold for EDMA extraction from the Superflip scientific map, in map σ units. Normal default .50. Changes extracted candidate sites; it does not rerun phasing or imply chemical validity.

Controls structure extraction/model export from the completed map, not neural inference or the camera. Parameters apply only to enabled extraction stages; raw sites and composition-constrained Jana sites can differ.

---

**SharpED threshold (σ)** · `plimit_deblur`

**Allowed:** 0.0 to 100.0. **Fresh full-configuration default:** 0.5.

Threshold for EDMA extraction from the SharpED scientific map, in map σ units. Normal default .50. Relevant only when that extraction stage is enabled. Guided Autosolve has its own 1.00σ policy.

Controls structure extraction/model export from the completed map, not neural inference or the camera. Parameters apply only to enabled extraction stages; raw sites and composition-constrained Jana sites can differ.

<!-- PAGE {"title": "Parameter reference · EDMA · 2", "image": "screenshots/workflow/professional-edma.png", "crop": "configuration", "reference": true, "keys": ["edma_maxima", "edma_numberofatoms"]} -->
**Maxima selection** · `edma_maxima`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** all.

EDMA maxima keyword. 'all' lists all density maxima above plimit; use more restrictive EDMA syntax only when you want to limit peak picking.

Controls structure extraction/model export from the completed map, not neural inference or the camera. Parameters apply only to enabled extraction stages; raw sites and composition-constrained Jana sites can differ.

---

**Atom-count mode** · `edma_numberofatoms`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** composition.

EDMA numberofatoms keyword for structure export. 'composition' asks EDMA to export atom counts consistent with the chemical composition.

Controls structure extraction/model export from the completed map, not neural inference or the camera. Parameters apply only to enabled extraction stages; raw sites and composition-constrained Jana sites can differ.

<!-- PAGE {"title": "Parameter reference · EDMA · 3", "image": "screenshots/workflow/professional-edma.png", "crop": "configuration", "reference": true, "keys": ["merge_distance", "edma_fullcell"]} -->
**Merge distance (Å)** · `merge_distance`

**Allowed:** 0.0 to 10.0. **Fresh full-configuration default:** 0.75.

Distance tolerance in Angstrom for reducing EDMA maxima to one representative per full space-group orbit before writing the CIF asymmetric unit.

Controls structure extraction/model export from the completed map, not neural inference or the camera. Parameters apply only to enabled extraction stages; raw sites and composition-constrained Jana sites can differ.

---

**Full-cell** · `edma_fullcell`

**Allowed:** no; yes. **Fresh full-configuration default:** no.

EDMA fullcell keyword. 'no' writes symmetry-independent maxima when the supplied space-group symmetry is correct; 'yes' lists the full unit cell.

Controls structure extraction/model export from the completed map, not neural inference or the camera. Parameters apply only to enabled extraction stages; raw sites and composition-constrained Jana sites can differ.

<!-- PAGE {"title": "Parameter reference · EDMA · 4", "image": "screenshots/workflow/professional-edma.png", "crop": "configuration", "reference": true, "keys": ["edma_centerofcharge", "edma_chlimit"]} -->
**Use center of charge** · `edma_centerofcharge`

**Allowed:** On / Off. **Fresh full-configuration default:** on.

EDMA centerofcharge keyword. When enabled, EDMA refines peak positions to the center of charge of the atomic basin before export.

Controls structure extraction/model export from the completed map, not neural inference or the camera. Parameters apply only to enabled extraction stages; raw sites and composition-constrained Jana sites can differ.

---

**Charge limit** · `edma_chlimit`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** 0.2500.

EDMA chlimit keyword. Minimum integrated charge for exported maxima; useful for suppressing noise peaks in rough or over-sharpened maps.

Controls structure extraction/model export from the completed map, not neural inference or the camera. Parameters apply only to enabled extraction stages; raw sites and composition-constrained Jana sites can differ.

<!-- PAGE {"title": "Parameter reference · EDMA · 5", "image": "screenshots/workflow/professional-edma.png", "crop": "configuration", "reference": true, "keys": ["edma_chlimlist", "extra_edma_keywords"]} -->
**Charge-list threshold** · `edma_chlimlist`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** 0.0057 relative.

EDMA chlimlist keyword. Charge-list threshold, for example '0.0057 relative', used together with numberofatoms and composition-based export.

Controls structure extraction/model export from the completed map, not neural inference or the camera. Parameters apply only to enabled extraction stages; raw sites and composition-constrained Jana sites can differ.

---

**Extra EDMA keywords** · `extra_edma_keywords`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** blank.

Additional documented EDMA keyword lines. Blank by default. No GUI numeric range; only supported external syntax is meaningful. These affect structure extraction and can change candidate models, not merely the camera.

Controls structure extraction/model export from the completed map, not neural inference or the camera. Parameters apply only to enabled extraction stages; raw sites and composition-constrained Jana sites can differ.

<!-- PAGE {"title": "Parameter reference · SharpED · 1", "image": "screenshots/workflow/professional-sharped.png", "crop": "configuration", "reference": true, "keys": ["sharped_elements", "sharped_outres"]} -->
**Elements** · `sharped_elements`

**Allowed:** valid text/path/keyword syntax; no GUI numeric interval. **Fresh full-configuration default:** .

Chemical elements sent to the SharpED server. Leave blank to derive unique non-H elements from the reference composition.

Controls remote processing, pre/post map transform or transport as described. Inactive SharpED stages ignore these values. Data submission needs the correct account entitlement and authorisation to share the map.

---

**Output resolution (Å)** · `sharped_outres`

**Allowed:** 0.001 to 10.0. **Fresh full-configuration default:** 0.2.

Requested server output sampling/resolution scalar in Å, sent as outres. Default .2. Server-specific numerical interpretation is not fully established by client code; ask the provider rather than claiming new experimental resolution.

Controls remote processing, pre/post map transform or transport as described. Inactive SharpED stages ignore these values. Data submission needs the correct account entitlement and authorisation to share the map.

<!-- PAGE {"title": "Parameter reference · SharpED · 2", "image": "screenshots/workflow/professional-sharped.png", "crop": "configuration", "reference": true, "keys": ["sharped_map_value_exponent", "sharped_max_upload_mb"]} -->
**Map value exponent** · `sharped_map_value_exponent`

**Allowed:** 0.0 to 10.0. **Fresh full-configuration default:** 1.0.

Reversible signed power transform sign(x)·|x|^a applied to map values before SharpED and inverted automatically on the returned SharpED map; 1.0 leaves values unchanged and 0 disables the transform. Only voxel values are affected — grid, cell, symmetry, format and the SharpED request itself are untouched.

Controls remote processing, pre/post map transform or transport as described. Inactive SharpED stages ignore these values. Data submission needs the correct account entitlement and authorisation to share the map.

---

**Upload limit (MB)** · `sharped_max_upload_mb`

**Allowed:** 0.0 to 100000.0. **Fresh full-configuration default:** 100.0.

Maximum XPLOR map size uploaded to the SharpED server in megabytes. Use 100 MB for the current public server limit. If voxel is empty/omit, Phase Studio can add a coarser Superflip voxel keyword before map calculation so the native Superflip XPLOR fits. Set 0 to disable this check.

Controls remote processing, pre/post map transform or transport as described. Inactive SharpED stages ignore these values. Data submission needs the correct account entitlement and authorisation to share the map.

<!-- PAGE {"title": "Parameter reference · SharpED · 3", "image": "screenshots/workflow/professional-sharped.png", "crop": "configuration", "reference": true, "keys": ["sharped_timeout_seconds", "sharped_poll_seconds"]} -->
**HTTP timeout (s)** · `sharped_timeout_seconds`

**Allowed:** 600 to 7200. **Fresh full-configuration default:** 600.

HTTP timeout in seconds for SharpED model query, upload, status and download requests. Phase Studio enforces at least 600 seconds for large XPLOR uploads.

Controls remote processing, pre/post map transform or transport as described. Inactive SharpED stages ignore these values. Data submission needs the correct account entitlement and authorisation to share the map.

---

**Polling interval (s)** · `sharped_poll_seconds`

**Allowed:** 1 to 3600. **Fresh full-configuration default:** 2.

Seconds between status polling requests.

Controls remote processing, pre/post map transform or transport as described. Inactive SharpED stages ignore these values. Data submission needs the correct account entitlement and authorisation to share the map.

<!-- PAGE {"title": "Parameter reference · SharpED · 4", "image": "screenshots/workflow/professional-sharped.png", "crop": "configuration", "reference": true, "keys": ["sharped_max_polls"]} -->
**Maximum polls** · `sharped_max_polls`

**Allowed:** -1 to 1000000. **Fresh full-configuration default:** -1.

Maximum number of status polls. Use -1 to wait without a fixed polling limit.

Controls remote processing, pre/post map transform or transport as described. Inactive SharpED stages ignore these values. Data submission needs the correct account entitlement and authorisation to share the map.

<!-- PAGE {"title": "Technical appendix · native Jana files", "image": null} -->
The incoming Jana .inflip determines return names: outputfile controls the scientific map destination(s), outputbase supplies companion model/context names, and writem40 identifies the EDMA model target. Phase Studio validates this original context instead of substituting a stale standalone project.

The native protocol uses M40 atomic-model records, M50 project/crystallographic context and M80/M81 density/map-related outputs. The original M50 context is preserved. The selected actual map's grid/origin is retained during conversion; a preview or temporary screenshot is not a scientific density input.

Corresponding EDMA exports preserve coordinates/occupancy/site identity and normalise physical displacement parameters. Biso is converted by Uiso = Biso/(8π²), then finite exported Uiso is bounded to 0.010–0.150 Å². PDB writes the corresponding B factor, not Uiso directly. These export safeguards do not validate a chemically correct atom assignment.

Candidate identity, source/cycle/threshold and file hashes guard the one selected return. This file-level mechanism does not replace native GUI acceptance of the imported map/model and continuing refinement.

<!-- PAGE {"title": "Troubleshooting and unresolved definitions", "image": null} -->
Missing/incompatible local tools: use the validated setup flow, not a silent skip or arbitrary replacement in Jana. Missing/rejected key: follow the exact token-page process; unreachable/5xx service failures are separate from authentication or bad science.

Unavailable automatic model: refresh the live catalogue; use a deliberate manual available model only when scientifically appropriate. Disabled Map Feedback: check cycle count, reflection format, experimental uncertainty, checkbox and positive resolved wavelength. No detected atoms: inspect extraction completion/map/threshold/chemistry rather than assuming a solved empty structure.

**Definitions requiring provider/manual clarification:** output-resolution server interpretation, individual neural model architecture/training, and complete mathematics/version compatibility of raw Superflip/EDMA keywords. RS/BL are not desktop controls. No quality-score cutoffs are invented.

**Image/acceptance gaps:** the actual current native Jana launch menu and returned model/map view with normal continuation, and packaged 2.0.3 workstation acceptance. These guides remain a review edition until those gaps are closed.

<!-- PAGE {"title": "Useful links, sources and attribution", "image": null} -->
[Phase Studio repository](https://github.com/ji-ze/Phase-Studio) · [Public releases](https://github.com/ji-ze/Phase-Studio/releases) · [Issue tracker](https://github.com/ji-ze/Phase-Studio/issues)

[Jana2020](https://jana.fzu.cz/) · [SharpED token page](https://sharped.fzu.cz/sharp-ed) · [Official Superflip/EDMA distributions](https://superflip.fzu.cz/)

[Superflip licence](https://superflip.fzu.cz/download/license_superflip.txt) · [EDMA licence](https://superflip.fzu.cz/download/license_EDMA.txt) · [Phase Studio MIT licence](https://github.com/ji-ze/Phase-Studio/blob/main/LICENSE)

**SharpED terms:** read the current terms shown by the provider. The project supplied `SharpED_Online_Service_and_API_Terms_2026-10-13_FINAL.pdf`, but no independently verified direct public terms URL is available for this edition. No guessed terms link is included.

**Software author:** Jiří Zelenka, Institute of Physics of the Czech Academy of Sciences. **SharpED developers, separately:** Jiří Zelenka, Jan Rohlíček, Monika Kučeráková and Zdeněk Buk, at the same institute.

Phase Studio uses the MIT licence. Scientific citation guidance is separate from the licence: cite the software version you actually used, its author, institute and repository, together with relevant Superflip, EDMA and Jana references. No new Phase Studio DOI is asserted.

PDF body fonts are the openly licensed DejaVu Sans family. Screenshots preserve the authentic application wordmarks. No proprietary font files are distributed with these guides.

[Standalone first use](PhaseStudio_FirstUse_Standalone.pdf) · [Jana2020 first use](PhaseStudio_FirstUse_Jana2020.pdf)

Implementation authorities: jana_superflip.py (Wizard/context/model policy); requirements.py/scientific_tools.py (tools); sharped_access.py/credentials.py (account/key); app.py (input, feedback, external stages, outputs); map_quality.py (scores/profiles); result_selection.py/autosolve_window.py/structure_camera.py (review/viewers); autosolve_review.py (guided policy). The settings inventory records the actual current stored fields and constructor lines. These are local source references, not claims about a future interface.
