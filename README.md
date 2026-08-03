# Phase Studio for Jana2020

**Phase Studio** is a standalone crystallographic workflow application designed to complement **Jana2020**. It integrates structure-solution, electron-density-map processing, peak searching, reflection-data analysis and model transfer into a single reproducible Python-based environment.

The application connects several commonly used crystallographic tools and processing steps:

* **Superflip charge flipping** for ab initio structure solution and phase refinement,
* optional **SharpED density-map deblurring** for improving the localization and separation of atomic-density maxima,
* **EDMA peak searching** for automatic extraction of candidate atomic positions,
* reflection-data diagnostics and comparison of crystallographic datasets,
* map conversion, symmetrization and export utilities,
* and tools for transferring generated structural models back to **Jana2020**.

Phase Studio can be used independently as a standalone application while remaining compatible with existing Jana2020 and Superflip workflows.

## Supported workflows

Phase Studio supports several input modes depending on the available crystallographic data and the current stage of structure solution.

### Jana `.inflip` workflow

An existing Jana2020 `.inflip` file can be loaded directly and used to run Superflip with the parameters defined in the file. Selected settings may also be overridden within Phase Studio without manually editing the original input file.

This mode is suitable for:

* reproducing existing Superflip calculations,
* testing alternative charge-flipping parameters,
* comparing multiple reconstruction strategies,
* and processing Jana2020 projects through a consistent graphical workflow.

### External reflection-data workflow

Phase Studio can also create and run structure-solution workflows from external reflection data, such as:

* HKL files containing measured amplitudes or intensities,
* crystallographic reference information,
* unit-cell parameters,
* space-group symmetry,
* and optional CIF structural models.

This allows the application to be used even when a complete Jana2020 project or `.inflip` file is not yet available.

### Model-seeded Superflip workflow

Structural models generated during an earlier calculation can be reused to initialize or constrain subsequent Superflip runs.

Possible starting models include:

* models produced directly by Superflip,
* atomic positions identified by EDMA,
* models derived from SharpED-deblurred maps,
* edited or partially completed Jana2020 models,
* and externally supplied CIF structures.

This workflow is particularly useful for difficult structures where an initial charge-flipping solution contains recognizable structural fragments but does not yet produce a complete or chemically interpretable model.

## Density-map processing

Phase Studio provides a unified environment for working with electron-density and electrostatic-potential maps generated during crystallographic structure solution.

Depending on the selected workflow, the application can process:

* raw Superflip maps,
* symmetrized maps,
* SharpED-deblurred maps,
* maps reconstructed from modified phases or amplitudes,
* and maps generated from intermediate structural models.

The original and processed maps can be retained separately, allowing direct comparison between the unmodified reconstruction and subsequent processing steps.

## SharpED integration

SharpED can optionally be used to deblur reconstructed density maps. The purpose of this step is to improve the spatial localization of density maxima and increase the separation of overlapping atomic peaks.

The deblurred map can subsequently be used for:

* visual inspection,
* EDMA peak searching,
* comparison with the original Superflip map,
* generation of an updated atomic model,
* and model-seeded Superflip calculations.

SharpED processing is optional. Phase Studio can also be used as a conventional Superflip and Jana2020 workflow manager without density-map deblurring.

## EDMA peak searching

EDMA integration enables automatic detection of candidate atomic positions in raw or processed density maps.

Peak-searching results can be inspected, filtered and exported as structural models for further processing. In particular, EDMA models can be used as:

* initial models for Jana2020 refinement,
* seeds for additional Superflip calculations,
* references for comparing raw and deblurred maps,
* or intermediate models for manual crystallographic interpretation.

This provides a reproducible connection between map reconstruction and atom-position determination.

## Reflection-data diagnostics

Phase Studio includes tools for inspecting and comparing reflection datasets used during structure solution.

The diagnostics are intended to help identify issues such as:

* inconsistent reflection indexing,
* mismatched unit-cell or symmetry information,
* incomplete or duplicated reflections,
* differences between observed and reconstructed amplitudes,
* resolution-dependent data quality,
* and inconsistencies between external HKL data and Jana2020 project files.

These checks are useful when combining data from different programs or when investigating unexpected behaviour in Superflip, map reconstruction or subsequent refinement.

## Jana2020 hand-off

Models and intermediate results generated by Phase Studio can be exported for continued work in Jana2020.

The hand-off tools are designed to reduce manual file editing when transferring:

* EDMA-derived atomic positions,
* SharpED-assisted models,
* Superflip model files,
* CIF structures,
* processed density maps,
* and modified crystallographic datasets.

Phase Studio does not replace Jana2020 refinement. Instead, it provides an integrated environment for the structure-solution and map-processing stages that precede detailed crystallographic refinement.

## Reproducibility

The complete workflow is implemented as a Python project so that individual processing steps can be repeated, inspected and documented.

Phase Studio aims to provide:

* explicit input and output files,
* reproducible processing parameters,
* traceable intermediate results,
* consistent file conversion,
* and a clear separation between original and processed crystallographic data.

This is especially important when comparing different charge-flipping configurations, map-processing methods, peak-search thresholds or model-seeding strategies.

## Intended users

Phase Studio is intended primarily for crystallographers working with:

* electron-diffraction data,
* X-ray diffraction data,
* electron-density or electrostatic-potential maps,
* Jana2020 and Superflip projects,
* external HKL datasets,
* partially solved crystal structures,
* and iterative structure-solution workflows.

The application is particularly useful for cases in which several independent programs would otherwise need to be run manually, with intermediate files repeatedly converted and transferred between them.

## Project scope

Phase Studio brings the following operations into one integrated workflow:

1. loading Jana2020 or external crystallographic input data,
2. preparing and running Superflip calculations,
3. inspecting reconstructed density maps,
4. optionally applying SharpED deblurring,
5. searching for atomic maxima using EDMA,
6. evaluating reflection and map consistency,
7. generating or updating structural models,
8. rerunning Superflip with a model-derived starting point,
9. and exporting the resulting data for Jana2020 refinement.

The project is intended to make complex and iterative crystallographic structure-solution workflows easier to reproduce, compare and maintain.

## Repository Layout

```text
phase_studio/                  Python package and GUI source code
phase_studio/app.py            Full Phase Studio GUI and reconstruction pipeline
phase_studio/jana_superflip.py Jana2020-compatible Superflip wrapper launcher
phase_studio/ui_style.py       Qt styling helper
superflip.spec                 PyInstaller build specification for Jana wrapper
pyproject.toml                 Python package metadata and optional dependencies
MANUAL.md                      Complete user manual
documentation/                 Optional local reference material, ignored by git
examples/                      Optional local example data, ignored by git
```

## Requirements

- Python 3.10 or newer.
- Jana2020 with the original Superflip and EDMA executables for full
  reconstruction workflows.
- Python packages:
  - `numpy`
  - `matplotlib`
  - `gemmi`
  - `PySide6`
  - `qtvscodestyle` optional but recommended for the GUI style
  - `pyinstaller` only for building the Jana2020 wrapper

SharpED server inference requires an API token. The token can be entered in the
GUI or supplied through `SHARPED_API_TOKEN`.

## Quick Start From Python

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[app]"
python -m phase_studio
```

Windows PowerShell:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[app]"
python -m phase_studio
```

After installation the entry point is also available:

```bash
phase-studio
```

Set a SharpED token when server-side deblurring is required:

```bash
export SHARPED_API_TOKEN=your-token
```

PowerShell:

```powershell
$env:SHARPED_API_TOKEN = "your-token"
```

## Typical Workflow

1. Select an input mode:
   - `Jana .inflip`,
   - `Jana .inflip with external HKL/reference overrides`,
   - `External HKL + CIF reference`.
2. Set or verify `HKL data format`.
   In `auto` mode Phase Studio first reads Superflip `dataformat` /
   `dataitemwidths` from a Jana `.inflip` file when available.
3. Use `Test HKL load` to verify how the reflection file is parsed.
4. Use `Analyze completeness` to inspect shell completeness, `d_min`,
   `d_full` and `I/sigma` statistics.
5. Configure next-cycle model policy, damping, Superflip options, EDMA options
   and SharpED server settings.
6. Run the pipeline.
7. For Jana-originated calculations, pass the selected cycle/map back to
   Jana2020.

See [MANUAL.md](MANUAL.md) for the full workflow documentation.

## Building The Jana2020 Superflip Wrapper

Install GUI and build dependencies:

```bash
python -m pip install -e ".[app,build]"
```

Build the wrapper:

```bash
python -m PyInstaller --clean --noconfirm superflip.spec
```

Expected output:

```text
dist/superflip/superflip.exe
```

Keep the complete `dist/superflip/` directory together; PyInstaller places
required DLLs and Python packages next to the executable.

Recommended deployment in `C:\Jana2020\SUPERFLIP`:

```text
C:\Jana2020\SUPERFLIP\superflip_original.exe
C:\Jana2020\SUPERFLIP\superflip.exe
C:\Jana2020\SUPERFLIP\EDMA.exe
```

Deployment steps:

1. Close Jana2020.
2. Rename the original Jana `superflip.exe` to `superflip_original.exe`.
3. Copy the contents of `dist\superflip\` into `C:\Jana2020\SUPERFLIP\`.
4. Start Jana2020 and run a Superflip job normally.

The wrapper searches for the original Superflip executable in this order:

```text
C:\Jana2020\SUPERFLIP\superflip_original.exe
<wrapper directory>\superflip_original.exe
<wrapper directory>\SuperFlip-orig.exe
<wrapper directory>\superflip-original.exe
PATH superflip_original.exe / SuperFlip-orig.exe
```

## Validation

Compile-check the Python package:

```bash
python -m compileall -q phase_studio
```

Validate package metadata and wheel building without installing runtime
dependencies:

```bash
python -m pip install --no-deps --prefix /tmp/phase_studio_install_test .
```

Remove generated local artifacts:

```bash
rm -rf build dist phase_studio.egg-info phase_studio/__pycache__
```

## Manual

Read the complete user manual here:

- [MANUAL.md](MANUAL.md)

## Notes

- The repository root is the active project.
- `Phase_studio_v2/` is retained as a reference copy and is not required for
  normal execution.
- Generated Superflip, EDMA, SharpED and PyInstaller outputs are ignored by
  `.gitignore`.
