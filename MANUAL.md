# Phase Studio User Manual

**Version 1.0.7**

## 1. Introduction

Phase Studio is a desktop application for iterative crystallographic phase retrieval, density-map processing, peak extraction, and model preparation. It integrates:

- **Superflip** for charge flipping and related map calculations,
- **SharpED** for optional server-side map deblurring,
- **EDMA** for peak extraction and structure export,
- **Jana2020** for project-oriented workflows and result hand-off.

The application can be used as a Jana2020 companion or as a standalone workflow with external reflection data.

Phase Studio is not intended to replace final crystallographic refinement. Its role is to organize reconstruction, map processing, diagnostics, iterative model seeding, and transfer of selected results into a reproducible workflow.

---

## 2. Installation and requirements

### 2.1 Windows release

A packaged Windows build is available from:

https://github.com/ji-ze/Phase-Studio/releases

The packaged application does not require a separate Python installation.

### 2.2 External crystallographic software

Phase Studio does not redistribute Superflip or EDMA.

Install them separately from:

https://superflip.fzu.cz/

Configure their executable paths in **Advanced → Setup** if the defaults do not match your installation.

### 2.3 Jana2020

Jana2020 is required for:

- direct Jana `.inflip` workflows,
- Jana-specific project integration,
- hand-off of selected results back to Jana2020.

Standalone external-HKL workflows do not require an active Jana2020 project.

### 2.4 SharpED

SharpED processing is optional.

API-token access is available at:

https://sharped.fzu.cz/

The default server configured in Phase Studio is:

```text
https://jana.fzu.cz/
```

Never commit API tokens to a repository or include them in shared logs.

### 2.5 Source installation

Development and source-build instructions are maintained separately in [BUILDING.md](BUILDING.md).

---

## 3. Interface overview

The main window is divided into two areas.

### 3.1 Configuration panel

The left side contains:

- **Basic**
  - Input
  - Workflow
  - Output
  - Map feedback
  - Help
- **Advanced**
  - Setup
  - Superflip
  - EDMA
  - SharpED
  - Help

Both **Help** tabs are self-contained in-app reference material: Basic → Help covers the Basic tabs (getting-started guide, Input/Workflow/Output/Map feedback field reference, About); Advanced → Help covers the Advanced tabs (Setup/Superflip/EDMA/SharpED field reference, plus the raw Superflip keyword reference). Each has its own CONTENTS navigation row and does not duplicate the other's sections.

### 3.2 Run dashboard

The right side contains:

- **Superflip Convergence**
- **Structure Comparison**
- **Execution Log**

The lower-left **Run Status** panel reports:

- overall run progress,
- current-cycle progress,
- the active workflow stage.

### 3.3 Run states

The application uses these high-level run states:

- `READY`
- `RUNNING`
- `COMPLETE`
- `CANCELLED`
- `ERROR`

---

## 4. Input data and crystallographic metadata

### 4.1 Input modes

The current GUI supports Jana-oriented and external-data workflows, including:

- **Jana `.inflip`**
- **Jana `.inflip` with overrides**
- **External HKL**

#### Jana `.inflip`

The `.inflip` file acts as the primary workflow input. Phase Studio can use crystallographic metadata and compatible Superflip settings obtained from the file.

#### Jana `.inflip` with overrides

The `.inflip` file remains the template while selected inputs are replaced by files or settings chosen in Phase Studio.

#### External HKL

External reflection data are loaded independently of Jana2020. The user must also provide the crystallographic metadata required by the downstream workflow.

### 4.2 Crystal metadata source

The **Crystal metadata** section defines where Phase Studio obtains:

- unit-cell parameters,
- space-group information,
- composition.

Available sources include:

- **Jana `.inflip`**
- **Reference file**
- **Manual**

When a metadata source is imported, Phase Studio shows a compact read-only summary. Manual fields are shown only when **Manual** is selected.

### 4.3 Manual metadata

Manual metadata entry is intended primarily for HKL-only workflows.

The current GUI supports entry of:

- `a`, `b`, `c`,
- `α`, `β`, `γ`,
- space-group information,
- composition.

Cell lengths are expressed in Å and angles in degrees.

The selected metadata source is authoritative for the run. Phase Studio should not silently combine incompatible metadata from different sources.

### 4.4 Reference and initial model

The reference structure can provide:

- crystallographic metadata,
- atom sites for metrics and comparison,
- a structural reference for selected workflow stages.

The initial model is optional and can be used to seed the first Superflip cycle when supported by the selected workflow.

### 4.5 Working directory

The working directory stores generated inputs and outputs, including:

- Superflip input files,
- maps,
- logs,
- EDMA outputs,
- SharpED outputs,
- per-cycle models,
- metrics and exported results.

Use a dedicated directory for each reconstruction run when reproducibility is important.

---

## 5. Reflection-data diagnostics

### 5.1 Validate HKL

Use **Validate HKL** before starting a reconstruction, especially for external data.

The dialog reports:

- source and reflection format,
- unit cell and space group,
- parsed reflection count,
- unique reflection count,
- σ(Fobs) availability,
- phase-value coverage,
- a sample of parsed reflections.

The reflection table may include:

- `h`, `k`, `l`,
- observed value,
- uncertainty,
- phase,
- `I/σ(I)`,
- `d`,
- `sinθ/λ`.

The purpose of this dialog is to validate parsing and input interpretation. It is not a substitute for crystallographic refinement or a complete data-quality assessment.

### 5.2 Analyze completeness

**Analyze completeness** opens the HKL Completeness dialog.

The current layout separates three scientific views:

1. **Completeness (%) vs. `sinθ/λ`**
2. **Mean `I/σ(I)` vs. `sinθ/λ`**
3. **Reflection distribution vs. `I/σ(I)`**

The first two share a common resolution axis.

The summary reports values such as:

- unique reflections,
- `d_min`,
- the resolution at 98% cumulative completeness,
- median `I/σ(I)`,
- the resolution where mean `I/σ(I)` falls below 3, when available,
- phase-value coverage,
- σ(Fobs) coverage.

The **Resolution Bins** table provides shell-wise statistics.

The dialog can also provide copy/export actions when available in the current build.

### 5.3 FWHM-format data

**HKL format** (Basic → Input) includes two additional modes, `hkl I fwhm` and `hkl F fwhm`, for reflection data whose second column is a peak-shape full width at half maximum — for example intensities extracted from a Le Bail powder-pattern fit — rather than a genuine measurement uncertainty. Selecting `set from inflip` also recognizes a Jana `.inflip` `dataformat ... fwhm` line automatically.

Because FWHM is not comparable in scale or meaning to σ, an `I/FWHM` ratio is not a signal-to-noise ratio. When FWHM data is detected:

- Validate HKL and Analyze completeness relabel every σ-based column and statistic (`sigma(Iobs)`/`sigma(Fobs)` becomes `FWHM(Iobs)`/`FWHM(Fobs)`, `I/σ(I)` becomes `I/FWHM`), and the "Derived I/σ" conversion column (which applies an F→I error-propagation factor that assumes a genuine σ) is left blank.
- The `I/σ(I) = 3` significance threshold and the resolution where mean `I/σ(I)` falls below it are not computed or shown, since that convention does not apply to FWHM data; the completeness dialog displays an explanatory note instead.
- The Superflip input still receives the correct `dataformat ... fwhm` keyword (not `dummy` or a plain `sigma` assumption), so Superflip itself is told the true nature of the column.

---

## 6. Reconstruction workflow

### 6.1 Starting preset

**Starting preset** applies a bundle of starting values in one step; every value stays individually editable afterward, and re-selecting a preset re-applies its values. **Recommended** is the default: a general-purpose baseline (cycles 5, Phasing method Superflip, next-cycle model deblurred_xplor, XPLOR damping 0.3, all optional processing enabled except symmetry averaging, SharpED model koala 2.0) that matches the built-in defaults, so a fresh install and a fresh selection of **Recommended** produce the same configuration. The other presets (MOF atomic resolution, MOF medium resolution, small molecule, inorganic) tune a handful of settings for a specific sample type. **custom** applies nothing and is only a placeholder for "I've configured this by hand" — selecting it does not change or reset any current value.

Treat presets as starting points rather than universal scientific recommendations.

### 6.2 Cycles

**Cycles** controls the requested number of iterative reconstruction cycles.

The effective number of cycles can also depend on the selected next-cycle model policy.

### 6.3 Phasing method

**Phasing method** chooses between the standard iterative Superflip cycle and two SharpED phase-recycling methods, one beta and one experimental:

- **Superflip** (default) — the standard charge-flipping cycle described in the rest of this section: Superflip runs every cycle, seeded by the next-cycle model.
- **1st Superflip, then SharpED (beta)** — Superflip runs only once (cycle 1). From then on, every cycle deblurs the previous cycle's map with SharpED, calculates phi_calc by FFT from that deblurred map for every measured hkl (expanded over the full space-group symmetry, not just the measured asymmetric-unit hkl), and recomposes a map from the observed |Fobs| and phi_calc. That recomposed map is what SharpED deblurs in the next cycle. This does not work well with some models.
- **SharpED (experimental)** — the same recycling loop, but skips Superflip entirely: cycle 1 starts from a map synthesized directly from |Fobs| with independent random phases per reflection. This does not work well yet and is intended for development, not production use. It can take extremely long to converge, even for simple structures (hundreds of cycles), and convergence is not guaranteed.

When either method is selected, **Next-cycle model**, **XPLOR damping**, **Symmetrize processed map with Superflip (beta)**, and the per-cycle EDMA checkboxes below are ignored (they are disabled in the GUI); the selected method defines its own next-cycle map and its own optional EDMA step (**Run EDMA on final map**, in Optional processing) instead. The convergence graph shows an additional **Map correlation** series for these methods (correlation between each cycle's recomposed map and the previous cycle's), since the Superflip-derived metrics used for Superflip cycling are only available for cycle 1 (or never, for **SharpED (experimental)**).

Only the SharpED server and the observed reflections are required for **SharpED (experimental)**; Superflip is never invoked in that mode.

Both **1st Superflip, then SharpED (beta)** and **SharpED (experimental)**, along with **Symmetrize processed map with Superflip (beta)**, are hidden from the GUI by default. Check **Show beta and experimental features in settings** on **Advanced → Setup** to make them selectable.

### 6.4 Next-cycle model

The next-cycle model determines what is used to seed Superflip after the first cycle. It only applies when Phasing method is Superflip.

Current workflow choices can include model sources such as:

- raw Superflip XPLOR output,
- SharpED-processed XPLOR output,
- EDMA-derived CIF output,
- no next-cycle model.

Use the exact option names shown by the current GUI.

### 6.5 XPLOR damping

**XPLOR damping (1/x)** controls damping when XPLOR maps are reused as models. It only applies when Phasing method is Superflip.

Examples:

```text
1.0  → effective factor 1.0
0.5  → effective factor 2.0
0.25 → effective factor 4.0
```

Damping applies only to workflows that use an XPLOR map as the next-cycle model.

### 6.6 Excluded atoms

When CIF models are used, selected atom labels can be excluded before a later-cycle model is prepared.

This option does not apply to XPLOR-only model paths.

### 6.7 Optional processing

The Workflow page groups these under two headings. Under "Superflip cycle" (used when Phasing method is Superflip):

- EDMA after the raw Superflip map,
- SharpED deblurring,
- Superflip symmetry averaging of the processed map (beta),
- EDMA after the processed map,
- compute omit maps (exclude 5% of reflections),
- compute R_free from the excluded 5% (requires the omit-maps option above).

Enabling omit maps additionally runs Superflip (and, if enabled, SharpED) each cycle on a fixed random 5% of reflections excluded from the input, purely for cross-validation; roughly doubles Superflip/SharpED time per cycle. See [11.6 Superflip Convergence](#116-superflip-convergence) for where the results are displayed.

The three map-feedback mechanisms (missing-reflection completion, intensity correction, powder overlap repartitioning) each have their own enable checkbox and settings on [10. Map feedback](#10-map-feedback) (Basic → Map feedback), not here.

Under "Phase-recycling methods" (used by the two beta Phasing methods):

- EDMA on the final map.

Only enabled stages are included in the cycle.

---

## 7. Superflip configuration

The **Advanced → Superflip** page exposes detailed Superflip controls.

### 7.1 Calculation

Typical controls include:

- algorithm / `perform`,
- maximum iterations,
- repeat mode,
- random seed,
- `delta`,
- weak ratio,
- `Biso`,
- final polish.

### 7.2 Density and solution selection

Controls can include:

- voxel grid,
- number of best densities,
- best-density metric,
- symmetry-related best-density options.

### 7.3 Reflection handling

Advanced reflection handling can include:

- value/σ filters,
- resolution cutoffs,
- normalization,
- resolution shells,
- missing-reflection keywords.

These settings affect the Superflip input generated by Phase Studio and should be changed deliberately.

### 7.4 Output

Output format is configured on **Basic → Output**, not on this page: a single **Map format** choice (XPLOR, XPLOR + CCP4, XPLOR + Jana m80/m81, HKL reflections with phases, or ShelX (fcf)) and a single **Structure format** choice for the EDMA-exported structure (CIF, CIF + XYZ, or CIF + PDB). The last two Map format options save, for each cycle's Superflip map, the observed |Fobs|/intensity alongside phases (and, for ShelX, calculated F²) read by FFT from that map, instead of an extra density map.

XPLOR and CIF are always produced internally regardless of these choices, because SharpED, EDMA and later-cycle modelfiles depend on them; the Map/Structure format choice only adds one extra saved format on top.

### 7.5 Additional keywords

The additional-keyword field is intended for advanced Superflip options not exposed elsewhere in the GUI.

Phase Studio-owned structural keywords may be filtered to avoid contradictory generated input.

---

## 8. EDMA configuration

The **Advanced → EDMA** page controls peak extraction and structure export.

### 8.1 Peak extraction

Important settings include:

- threshold after the Superflip map,
- threshold after the SharpED-processed map,
- maxima selection,
- atom-count mode.

Thresholds are entered as multipliers of the map σ. Phase Studio converts the selected multiplier to the absolute EDMA `plimit` required for the specific map.

### 8.2 Symmetry and peak positions

Controls can include:

- merge distance,
- full-cell mode,
- center-of-charge refinement.

The merge distance is used when reducing symmetry-related peak positions to the asymmetric unit.

### 8.3 Chemical filtering

Controls can include:

- charge limit,
- charge-list threshold.

These settings affect which EDMA maxima are exported.

---

## 9. SharpED configuration

The SharpED model selector is on the **Basic → Workflow** page. Server connection lives on **Advanced → Setup**; elements, output resolution and transfer/network settings live on **Advanced → SharpED**.

### 9.1 Server connection

#### Server URL

The current default is:

```text
https://jana.fzu.cz/
```

#### API token

The token is used for authenticated SharpED requests.

Phase Studio must never expose the token in normal logs or error messages.

#### Show beta and experimental features in settings

**Advanced → Setup** also has an **Interface** group with this checkbox, unchecked by default. When unchecked, beta and experimental Phasing methods (and the settings that only apply to them) are removed from the Basic tabs entirely, not just disabled. Check it to make them selectable again; see [6.3 Phasing method](#63-phasing-method).

### 9.2 Model

Use **Refresh models** to query the configured server when supported.

The available model list is server-dependent and can change over time.

### 9.3 Elements

When left blank, the current workflow can derive unique non-hydrogen elements from the active composition.

The GUI may display this state as **Auto from composition** without writing that text into the stored value.

### 9.4 Output resolution

This value is sent to the SharpED server as the output-map sampling request.

The manual intentionally does not assign physical units beyond what is established by the current application/server contract.

### 9.5 Transfer and network

Current controls include:

- upload-size limit,
- HTTP timeout,
- polling interval,
- maximum number of polls.

A maximum-polls value of `-1` represents no fixed polling limit where supported by the current build.

---

## 10. Map feedback

The **Basic → Map feedback** page controls optional feedback from a completed map into later cycles.

All three mechanisms rewrite the observed HKL data used by subsequent cycles, not just the model; the page carries a warning to this effect. Each mechanism has its own **Enable** checkbox at the top of its group; unchecking it grays out (disables) the rest of that group's controls and skips the mechanism entirely, regardless of what its other fields are set to.

Each group's **Start after cycle** control ranges from `1` to the current **Cycles** value (Basic → Workflow) and its maximum tracks Cycles automatically — lowering Cycles below a group's current start cycle clamps it down.

### 10.1 Missing-reflection completion

Controls include:

- enable checkbox,
- start-after-cycle threshold (1 to Cycles),
- maximum percentage of added reflections.

### 10.2 Intensity correction

Controls include:

- enable checkbox,
- start-after-cycle threshold (1 to Cycles),
- damping,
- value/σ limit.

A damping value of `0` retains observed intensities, while `1` corresponds to full replacement by the scaled map-derived value according to the implemented workflow.

A value/σ threshold of `0` applies the correction to all non-zero reflections where this is the current implementation.

### 10.3 Powder overlap repartitioning

Enabled via its own checkbox on this page; applies only to reflections carrying an FWHM value (the `hkl I fwhm`/`hkl F fwhm` HKL formats).

Each cycle from its start-after-cycle threshold onward, reflections whose Bragg peaks overlap — `delta(2theta) < separation_factor * (FWHM1 + FWHM2) / 2`, Superflip's own `fwhmseparation` convention — are grouped, and their combined observed intensity is redistributed between them using intensities calculated by FFT from that cycle's processed map. The group total is always conserved.

Controls include:

- enable checkbox,
- start-after-cycle threshold (1 to Cycles),
- **Wavelength (Å)** — required to compute 2theta. If left at `0`, it is auto-detected first from the loaded `.inflip` file's `lambda`/`wavelength` line, then from the reference file's `_diffrn_radiation_wavelength` CIF tag; enter it manually if neither source has it. A manually entered nonzero value always takes priority over auto-detection.
- **Separation factor** — the multiplier in the overlap criterion above (default `0.2`).
- **Map ratio mix** — `0` keeps each reflection's observed share of its group; `1` (default) replaces it entirely with the map-derived share. A group where the map has no usable signal for any member falls back to the observed split unchanged.

---

## 11. Running and monitoring a reconstruction

### 11.1 Run pipeline

**Run pipeline** validates the active configuration and starts the reconstruction.

Configuration controls are locked while the pipeline is running.

### 11.2 Stop after current cycle

Requests a graceful stop after the current cycle has completed.

### 11.3 Stop immediately

Requests immediate termination of the active external calculation and stops the pipeline as soon as possible.

After cancellation, Phase Studio retains information about where the run stopped.

### 11.4 Continue

**Continue** resumes the most recent run exactly where it left off — whether it was stopped (gracefully or immediately) or reached its configured cycle count — reusing the same crystal metadata, reflections, and cycle-to-cycle model/reference feedback, so the reconstruction proceeds as if it had never been interrupted.

If the previous run reached its configured number of **Cycles** without being stopped, Continue has no further cycles to run. Increase **Cycles** above the number of completed cycles before using Continue in that case.

### 11.5 Overall and current-cycle progress

The Run Status area contains two levels:

- **Overall** — completed reconstruction cycles.
- **Current cycle** — active workflow stage and, when available, meaningful sub-progress such as Superflip repeat progress.

Phase Studio does not need to fabricate time-based percentages when no reliable denominator exists.

### 11.6 Superflip Convergence

The convergence panel has four tabs, each scaled and colored independently:

- **Superflip** — metrics tied to the raw Superflip map. With a reference structure: Reference match, Superflip RMSD, Recall and Precision (heavy, i.e. non-H/He, atoms matched to the reference within EDMA's **Merge distance**; recall = fraction of reference atoms found, precision = fraction of found atoms that are real). Without a reference: only **Heavy atoms found**, a plain count of non-H/He atoms in the EDMA output, as a fallback progress indicator. (Superflip's own internal R/Peaks/FOM/Symmetry indicators were removed from this graph: cycle 1 normally runs ab initio while cycle 2 onward is seeded by the selected next-cycle model, so they are not a like-for-like series across that transition, and `bestdensities`/`repeatmode` selects the best of several stochastic attempts each cycle, adding further cycle-to-cycle fluctuation unrelated to genuine quality change. They remain in `metrics.csv` and the execution log.)
- **SharpED** (formerly labeled "Deblurred") — the same reference-dependent set (SharpED RMSD, Recall, Precision) or reference-free fallback (Heavy atoms found) for the SharpED-processed map, plus Map correlation (SharpED phase-recycling methods only, correlating each cycle's recomposed map with the previous cycle's — always empty for the standard Superflip phasing method).
- **Superflip (omit+rfree)** — only populated when **Compute omit maps** is enabled: Omit map correlation (the raw Superflip map compared with the same cycle's omit map) and, if **Compute R_free from excluded 5%** is also enabled, R_free for the raw Superflip map. Needs no reference structure.
- **SharpED (omit+rfree)** — the same two metrics for the SharpED-processed map and its omit-map counterpart. Needs no reference structure.

Every series is normalized per tab to a 0 (worst) to 1 (best) scale for comparison; the underlying values are in `metrics.csv`.

Unavailable series can be omitted in partial or cancelled runs.

### 11.7 Structure Comparison

The current structure panel compares:

- Reference,
- Superflip,
- SharpED.

Loaded structures use synchronized rotation.

Hydrogens are hidden in the preview when this is the active visualization policy.

Depth cueing improves three-dimensional perception by rendering more distant atoms more lightly than atoms in the foreground.

### 11.8 Execution Log

The log reports workflow progress and technical diagnostics.

High-level events use subsystem prefixes such as:

- `[Superflip]`,
- `[EDMA]`,
- `[SharpED]`,
- `[HKL]`.

Detailed implementation diagnostics can be visually de-emphasized while remaining available for troubleshooting.

---

## 12. Jana2020 integration

### 12.1 Jana `.inflip` hand-off

When Phase Studio is launched in a Jana2020 context, it can import compatible project/input information and populate the GUI accordingly.

Explicit Jana2020 values and `.inflip` values take precedence over stale unrelated saved settings.

### 12.2 Send to Jana2020

When a compatible result is available, **Send to Jana2020** opens the hand-off workflow.

The available result choices depend on the completed run and the active Jana2020 context.

After hand-off, detailed model completion and final refinement should be performed in Jana2020.

---

## 13. Outputs and reproducibility

Depending on the selected workflow, Phase Studio can generate:

- Superflip `.inflip` files,
- Superflip XPLOR maps (always) plus the selected extra Map format output (CCP4 or Jana m80/m81 density map, or a standardized HKL / ShelX .fcf reflection export),
- Superflip logs,
- EDMA CIF outputs (always) plus the selected extra Structure format (XYZ or PDB),
- SharpED-processed XPLOR maps,
- symmetry-averaged processed maps,
- per-cycle models,
- metrics files.

Original and processed files are kept separately where practical so reconstruction decisions can be inspected and reproduced.

---

## 14. Troubleshooting

### 14.1 HKL validation fails

Check:

- selected input file,
- HKL format,
- whether values are intensities or amplitudes,
- sigma/phase column mapping.

Use **Validate HKL** before starting the pipeline.

### 14.2 Completeness appears unexpectedly low

Check:

- unit cell,
- space group,
- reflection-data format,
- resolution coverage,
- whether the selected metadata source belongs to the HKL dataset.

Then inspect **Analyze completeness**.

### 14.3 Crystal metadata are unavailable

If the selected metadata source cannot be read:

- choose another reference file,
- switch to Jana `.inflip`,
- or use Manual metadata.

Do not continue with unrelated metadata from an earlier project.

### 14.4 Superflip or EDMA cannot be found

Check the executable paths in **Advanced → Setup**.

In the full GUI, the Superflip path should point to the original Superflip executable rather than a Phase Studio wrapper executable.

### 14.5 SharpED authentication fails

Check:

- API token,
- server URL,
- network access.

Token access:

https://sharped.fzu.cz/

### 14.6 SharpED request times out

Check the configured:

- HTTP timeout,
- polling interval,
- maximum polls,
- network connection.

Large maps can require longer server processing times.

### 14.7 Windows SmartScreen

Unsigned Windows binaries can trigger Microsoft Defender SmartScreen and may be shown as an unknown publisher.

This behaviour is independent of PyInstaller packaging and is normally addressed through trusted code signing and publisher reputation.

---

## 15. About Phase Studio

Phase Studio is developed at the:

**Department of Structure Analysis**  
**Institute of Physics of the Czech Academy of Sciences**

https://www.fzu.cz/en/research/divisions-and-departments/division-3/department-19

### Authors

- **Jiří Zelenka** — zelenka@fzu.cz
- **Jan Rohlíček** — rohlicek@fzu.cz
- **Monika Kučeráková**
- **Zdeněk Buk**

General project/support contact:

**sharped@fzu.cz**

### Resources

- Phase Studio: https://github.com/ji-ze/Phase-Studio
- SharpED: https://sharped.fzu.cz/
- Superflip and EDMA: https://superflip.fzu.cz/
