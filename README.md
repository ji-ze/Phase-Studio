# Phase Studio

**Phase Studio** is a desktop environment for iterative crystallographic phase retrieval, density-map processing, and model preparation. It integrates **Superflip**, **SharpED**, and **EDMA** into a reproducible workflow with direct interoperability with **Jana2020**.

Phase Studio can be used either with Jana2020 `.inflip` projects or as a standalone application with external reflection data. Crystallographic metadata can be taken from a Jana `.inflip` file, a reference structure, or entered manually.

## Key capabilities

- Superflip charge-flipping and model-seeded reconstruction workflows
- Optional SharpED density-map deblurring
- EDMA peak extraction from raw and processed maps
- HKL validation and resolution-dependent completeness analysis
- Iterative next-cycle model generation
- Optional map symmetrization and map-feedback workflows
- Side-by-side comparison of reference, Superflip, and SharpED-derived structures
- Jana2020 hand-off for selected reconstruction results
- Reproducible storage of generated inputs, maps, models, metrics, and logs

## Typical workflow

```text
Reflection data
      ↓
  Superflip
      ↓
   XPLOR map
   ↙      ↘
 EDMA    SharpED
           ↓
  optional symmetry averaging
           ↓
          EDMA
           ↓
    next-cycle model
           ↓
       Superflip

Selected result → Jana2020
```

Optional stages are included only when enabled in the workflow.

## Download and run on Windows

A ready-to-run Windows build is available from the project releases page:

**[Download Phase Studio](https://github.com/ji-ze/Phase-Studio/releases)**

The packaged Windows application does not require a separate Python installation.

### External software

Phase Studio does **not** redistribute Superflip or EDMA. Install them separately:

**[Superflip and EDMA](https://superflip.fzu.cz/)**

Jana2020 is required only for Jana-specific integration, `.inflip` workflows, and transfer of results back to Jana2020. Standalone external-HKL workflows can be used without an active Jana2020 project.

## SharpED access

SharpED processing is optional. Phase Studio can run with Superflip and EDMA alone.

Server-side SharpED processing requires an API token:

**[SharpED and API-token access](https://sharped.fzu.cz/)**

The application default SharpED server is:

```text
https://jana.fzu.cz/
```

## Quick start

1. Start Phase Studio.
2. Configure the Superflip and EDMA executable paths if necessary.
3. Choose an input mode.
4. Select the source of crystallographic metadata.
5. Use **Validate HKL** to verify the reflection-data interpretation.
6. Use **Analyze completeness** to inspect resolution-dependent data quality.
7. Configure the reconstruction workflow and optional processing steps.
8. If SharpED is enabled, enter an API token and select a model.
9. Click **Run pipeline**.
10. Inspect convergence, structure comparisons, and generated outputs.
11. For Jana2020 workflows, use **Send to Jana2020** when the desired result is available.

## Input workflows

### Jana `.inflip`

Use an existing Jana2020 `.inflip` file as the primary crystallographic input. Phase Studio can obtain crystallographic metadata and compatible Superflip settings from the file.

### Jana `.inflip` with overrides

Use the Jana `.inflip` file as the workflow template while overriding selected reflection, reference, or configuration inputs in Phase Studio.

### External HKL

Use reflection data prepared outside Jana2020. Crystallographic metadata can be supplied from:

- a compatible reference structure, or
- manual metadata entry.

Manual metadata entry supports unit-cell parameters, space-group information, and composition for HKL-only workflows.

## Monitoring and diagnostics

### HKL Validation

**Validate HKL** checks how the selected reflection file is parsed and reports, among other items:

- parsed and unique reflection counts,
- σ(Fobs) availability,
- phase-value coverage,
- unit cell and space group,
- a reflection sample with derived quantities.

### HKL Completeness

**Analyze completeness** provides:

- completeness vs. `sinθ/λ`,
- mean `I/σ(I)` vs. `sinθ/λ`,
- reflection-distribution statistics,
- `d_min`,
- the resolution at 98% cumulative completeness,
- resolution-bin statistics.

### Run monitoring

The main window reports both:

- **Overall** progress across reconstruction cycles, and
- **Current cycle** progress through the active workflow stage.

The dashboard also includes:

- Superflip convergence metrics,
- synchronized structure comparison,
- execution log and diagnostics.

## Documentation

- **[User Manual](MANUAL.md)** — complete user-facing reference
- **[Example Workflows](EXAMPLES.md)** — practical configurations and workflows
- **[Building Phase Studio](BUILDING.md)** — source installation, packaging, and wrapper deployment

Reusable branding assets are stored in `phase_studio/assets/`: the Windows multi-size `phase_studio.ico`, square cross-platform `phase_studio_icon.svg/.png`, and full `phase_studio_logo.svg/.png`.

## Project information

Phase Studio is developed at the:

**Department of Structure Analysis**  
**Institute of Physics of the Czech Academy of Sciences**

[Department website](https://www.fzu.cz/en/research/divisions-and-departments/division-3/department-19)

### Authors and contacts

- **Jiří Zelenka** — zelenka@fzu.cz
- **Jan Rohlíček** — rohlicek@fzu.cz
- **Monika Kučeráková**
- **Zdeněk Buk**

General project/support contact:

**sharped@fzu.cz**

### Resources

- Phase Studio source and releases: https://github.com/ji-ze/Phase-Studio
- SharpED: https://sharped.fzu.cz/
- Superflip and EDMA: https://superflip.fzu.cz/

## Scope

Phase Studio is designed for crystallographic reconstruction and density-map workflows involving diffraction data, electron-density or electrostatic-potential maps, partially solved structures, and iterative model-seeded phase retrieval.

It complements Jana2020 and does not replace crystallographic refinement in Jana2020.
