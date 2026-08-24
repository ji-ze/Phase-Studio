# Phase Studio Example Workflows

These examples illustrate practical Phase Studio configurations. They are workflow recipes, not universal crystallographic recommendations.

Use the values as starting examples and adjust them to the data being analyzed.

---

## Example 1 — Validate and reproduce a Jana2020 Superflip calculation

### Goal

Reproduce an existing Jana2020 Superflip calculation, verify reflection parsing, and inspect EDMA peak extraction without SharpED.

### Use this workflow when

- a Jana `.inflip` calculation already exists,
- the first goal is to validate Phase Studio against the existing calculation,
- SharpED processing is not required.

### Configuration

| Setting | Example value |
|---|---|
| Input mode | Jana `.inflip` |
| Metadata source | Jana `.inflip` |
| Cycles | 1 |
| Next-cycle model | None |
| EDMA on Superflip map | Enabled |
| SharpED | Disabled |
| EDMA on processed map | Disabled |

### Procedure

1. Open **Basic → Input**.
2. Select the Jana `.inflip` input mode.
3. Choose the `.inflip` file.
4. Confirm the Superflip and EDMA executable paths on **Advanced → Setup**.
5. Click **Validate HKL**.
6. Confirm that the reflection format and parsed columns are correct.
7. Click **Analyze completeness** and inspect the resolution-dependent statistics.
8. Open **Basic → Workflow**.
9. Set **Cycles** to `1`.
10. Select no next-cycle model.
11. Enable EDMA on the raw Superflip map.
12. Leave SharpED disabled.
13. Review **Advanced → EDMA** if a different peak threshold is required.
14. Click **Run phasing**.

### What to inspect

- agreement with the original Superflip calculation,
- generated XPLOR map,
- Superflip metrics,
- EDMA peak positions,
- reflection diagnostics.

### Expected outputs

Typical outputs include:

- generated Superflip input,
- Superflip XPLOR map,
- Superflip log,
- EDMA output,
- metrics file.

---

## Example 2 — Jana2020 workflow with SharpED processing

### Goal

Use SharpED to process the Superflip map before peak extraction and optionally use the processed result to seed later cycles.

### Use this workflow when

- the raw Superflip solution contains recognizable structural information,
- additional map processing is desirable,
- the result will remain connected to a Jana2020 workflow.

### Configuration

| Setting | Example value |
|---|---|
| Input mode | Jana `.inflip` |
| Metadata source | Jana `.inflip` |
| Cycles | 2 or more |
| Next-cycle model | Processed XPLOR / current equivalent |
| EDMA on Superflip map | Enabled |
| SharpED | Enabled |
| Symmetry averaging | Optional |
| EDMA on processed map | Enabled |

Use the exact option labels shown by the current GUI.

### Procedure

1. Load the Jana `.inflip` project in **Basic → Input**.
2. Select a dedicated working directory on **Basic → Model & Output**.
3. Verify the active crystallographic metadata.
4. Click **Validate HKL** and **Analyze completeness**.
5. Open **Basic → Workflow**.
6. Select the desired number of cycles.
7. Select the appropriate next-cycle model source.
8. Configure **XPLOR damping (1/x)** when an XPLOR map is reused as a model.
9. Enable EDMA on the raw Superflip map if raw-map peak extraction is needed.
10. Enable SharpED.
11. Optionally enable Superflip symmetry averaging of the processed map.
12. Enable EDMA on the processed map if structural peaks are required from that branch.
13. Open **Advanced → Setup** and confirm the SharpED server URL and API token.
14. Open **Basic → SharpED** and refresh the available model list if required.
15. Open **Advanced → SharpED**. Leave **Elements** blank to use automatic composition-derived elements, or enter them explicitly.
16. Review network and upload settings on the same page.
17. Run the pipeline.
18. Inspect convergence, structures, and EDMA outputs.
19. When a suitable result is available, use **Send to Jana2020**.

### SharpED model selection

Available SharpED models are server-dependent and can change over time. Select from the models returned by the configured server rather than relying on a permanently fixed model name in the workflow documentation.

### EDMA thresholds

Thresholds are expressed as multipliers of the map σ.

A workflow may start with a lower threshold for a clean map and a higher threshold when weak maxima generate excessive candidate peaks. Treat threshold values as dataset-dependent parameters rather than universal defaults.

### Expected outputs

Depending on enabled stages:

- raw Superflip maps,
- SharpED-processed maps,
- optional symmetry-averaged maps,
- EDMA models from one or both branches,
- per-cycle logs and metrics,
- Jana2020 hand-off data.

---

## Example 3 — Standalone external HKL with reference metadata

### Goal

Run Phase Studio without a Jana `.inflip` file using external reflection data and crystallographic metadata from a reference structure.

### Use this workflow when

- reflection data were prepared outside Jana2020,
- a compatible reference structure is available,
- standalone reconstruction is preferred.

### Configuration

| Setting | Example value |
|---|---|
| Input mode | External HKL |
| Metadata source | Reference file |
| Reference | CIF/INS/RES-compatible structure |
| SharpED | Optional |
| Jana2020 hand-off | Normally not required |

### Procedure

1. Open **Basic → Input**.
2. Select the external HKL input mode.
3. Choose the HKL file.
4. Select the correct HKL data format.
5. Select **Reference file** as the metadata source.
6. Open **Basic → Model & Output** and choose the reference structure.
7. Back on **Basic → Input**, verify that the unit cell, space group, and composition were read correctly.
8. Click **Validate HKL**.
9. Confirm the reflection interpretation and unique-reflection count.
10. Click **Analyze completeness**.
11. Inspect:
    - `d_min`,
    - 98% cumulative completeness,
    - completeness vs. `sinθ/λ`,
    - mean `I/σ(I)`,
    - reflection distribution.
12. Configure **Basic → Workflow**.
13. Enable SharpED only if processed-map reconstruction is required.
14. Review EDMA and Superflip settings.
15. Run the pipeline.

### What to inspect

- whether the reference metadata match the reflection dataset,
- high-resolution completeness,
- mean `I/σ(I)` behaviour,
- consistency of the derived structure with the selected reference context.

### Expected outputs

Typical outputs include:

- generated Superflip inputs,
- maps,
- EDMA exports,
- per-cycle models,
- metrics and logs.

---

## Example 4 — HKL-only workflow with manual crystallographic metadata

### Goal

Run Phase Studio when only reflection data are available and no reference structure or Jana `.inflip` metadata source is available.

### Use this workflow when

- the HKL file is known,
- unit-cell parameters, symmetry, and composition are known independently,
- no reference CIF should be required.

### Configuration

| Setting | Example value |
|---|---|
| Input mode | External HKL |
| Metadata source | Manual |
| Unit cell | Enter manually |
| Space group | Enter manually |
| Composition | Enter manually |

### Procedure

1. Select the external HKL input mode.
2. Choose the HKL file and data format.
3. Set **Metadata source** to **Manual**.
4. Enter:
   - `a`, `b`, `c`,
   - `α`, `β`, `γ`,
   - space-group information,
   - composition.
5. Check that the manual metadata are accepted by the GUI.
6. Run **Validate HKL**.
7. Run **Analyze completeness**.
8. Configure the reconstruction workflow.
9. Start the pipeline.

### Important check

Manual metadata must describe the same crystallographic setting as the reflection data. Incorrect cell or symmetry information can make completeness analysis and downstream reconstruction misleading.

---

## Example 5 — SharpED phase recycling instead of iterative Superflip (beta)

### Goal

Use one of the beta SharpED phase-recycling phasing methods: Superflip runs at most once, and later cycles recompose a map from the observed |Fobs| and phases calculated (by FFT, expanded over the full space-group symmetry) from each cycle's SharpED-deblurred map, instead of re-running Superflip every cycle.

### Use this workflow when

- exploring whether SharpED-driven phase recycling converges better or faster than iterative charge flipping for a given dataset,
- comparing a random-phase start against a Superflip-seeded start.

### Configuration

| Setting | Example value |
|---|---|
| Phasing method | "1st Superflip, then SharpED" (or "SharpED" for the random-phase-start variant) |
| Cycles | 10–20 to start; "SharpED" (random-phase start) may need hundreds |
| Run EDMA on final map | Enabled, if a peak-picked structure is wanted at the end |

### Procedure

1. Open **Basic → Workflow**.
2. Set **Phasing method** to "1st Superflip, then SharpED" to seed cycle 1 with a single Superflip run, or "SharpED" to skip Superflip entirely and start from random phases.
3. Set **Cycles** to the number of recycling rounds desired.
4. Enable **Run EDMA on final map** if a peak-picked CIF/XYZ/PDB structure should be exported from the last cycle's map.
5. Confirm the SharpED server URL and API token on **Advanced → Setup**.
6. Click **Run phasing**.
7. Inspect the per-cycle Superflip map (or random-phase start map) and the recomposed |Fobs|+phi_calc map for each cycle in the working directory.

### Important check

**Next-cycle model**, **XPLOR damping**, **Symmetrize processed map**, and the per-cycle EDMA checkboxes are ignored by these methods and are disabled in the GUI while one is selected.

Both methods are **beta features**. "SharpED" (random-phase start) in particular can take extremely long to converge, even for simple structures (hundreds of cycles), and convergence is not guaranteed.

---

## General advice

Before a production run:

1. validate reflection parsing,
2. inspect completeness,
3. verify the active metadata source,
4. confirm external executable paths,
5. review enabled workflow stages,
6. verify SharpED settings if enabled,
7. use a dedicated working directory,
8. retain the generated inputs and intermediate outputs needed for reproducibility.
