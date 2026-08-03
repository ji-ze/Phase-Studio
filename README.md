# Phase Studio for Jana2020

**Phase Studio** is a standalone crystallographic workflow application for structure solution and density-map processing. It integrates **Superflip charge flipping**, optional **SharpED map deblurring**, **EDMA peak searching**, reflection-data diagnostics, iterative model seeding, and transfer of results back to **Jana2020**.

Phase Studio can work directly with Jana2020 `.inflip` files or independently with external HKL and CIF data.

---

## Download and Run on Windows

A ready-to-run Windows version is available from the GitHub Releases page:

### [Download Phase Studio for Windows](https://github.com/ji-ze/Phase-Studio/releases)

The Windows release does not require a separate Python installation.

### Additional programs required

Phase Studio does **not** include Superflip or EDMA. Both programs must be installed separately, including when using the prebuilt Windows executable.

Superflip and EDMA can be obtained from:

### [Download Superflip and EDMA](https://superflip.fzu.cz/)

Make sure that the Superflip and EDMA executables are available at the paths configured in Phase Studio.

Jana2020 is required only for workflows that use Jana `.inflip` files or transfer results directly back to Jana2020. External HKL and CIF workflows can be used without an active Jana2020 project.

---

## SharpED Access

SharpED deblurring is optional. Phase Studio can be used with Superflip and EDMA without enabling SharpED.

Server-side SharpED processing requires an API token.

**Jana2020 users can obtain a SharpED token at:**

### https://sharped.fzu.cz/

The same website also provides the online version of SharpED, which can be used independently of Phase Studio.

The token can be entered directly in the Phase Studio graphical interface.

---

## Quick Start

1. Download and extract the latest Windows release.
2. Install Superflip and EDMA from [superflip.fzu.cz](https://superflip.fzu.cz/).
3. Start `Phase Studio.exe`.
4. Set the paths to the Superflip and EDMA executables if they are not detected automatically.
5. Optionally enter a SharpED API token.
6. Select an input workflow:

   * Jana `.inflip`,
   * Jana `.inflip` with external HKL or reference overrides,
   * or external HKL and CIF data.
7. Test the reflection-data import.
8. Configure the reconstruction options and run the pipeline.
9. Inspect the generated maps and structural models.
10. Export the selected result or transfer it back to Jana2020.

---

## Main Features

* Direct loading of Jana2020 `.inflip` files.
* External HKL and CIF input mode.
* Superflip charge-flipping workflows.
* Optional SharpED density-map deblurring.
* EDMA peak searching.
* Reflection-data loading tests and completeness analysis.
* Iterative model-seeded Superflip cycles.
* Map conversion, symmetrization, and export.
* Transfer of selected maps and models back to Jana2020.
* Reproducible storage of parameters and intermediate results.
* Standalone graphical interface for Windows, Linux, and macOS.

---

## Supported Workflows

### Jana `.inflip`

Run Superflip using an existing Jana2020 `.inflip` file and optionally override selected parameters from the Phase Studio interface.

### Jana `.inflip` with overrides

Use the Jana `.inflip` file as a workflow template while replacing the HKL data, reference structure, or selected crystallographic parameters.

### External HKL and CIF

Create a structure-solution workflow from external reflection data, unit-cell parameters, space-group symmetry, and an optional CIF reference structure.

### Iterative model seeding

Use atomic positions obtained from Superflip, EDMA, SharpED-processed maps, Jana2020 models, or external CIF files as starting models for subsequent Superflip cycles.

---

## Documentation

Detailed installation, configuration, workflow, and development instructions are available in:

### [MANUAL.md](MANUAL.md)

The manual includes:

* installation from Python source,
* detailed input-mode descriptions,
* reflection-data diagnostics,
* SharpED and EDMA configuration,
* iterative model-seeded workflows,
* Jana2020 hand-off,
* Windows wrapper deployment,
* repository structure,
* and package validation.

---

## External Software

Phase Studio integrates external crystallographic software but does not redistribute it.

* **Superflip and EDMA:** https://superflip.fzu.cz/
* **SharpED and API-token access:** https://sharped.fzu.cz/
* **Phase Studio Windows releases:** https://github.com/ji-ze/Phase-Studio/releases

---

## Scope

Phase Studio is intended for crystallographers working with:

* electron-diffraction data,
* X-ray diffraction data,
* electron-density maps,
* electrostatic-potential maps,
* Jana2020 and Superflip projects,
* external HKL datasets,
* partially solved crystal structures,
* and iterative structure-solution workflows.

Phase Studio complements Jana2020 but does not replace crystallographic model refinement in Jana2020.
