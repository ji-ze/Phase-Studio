# Phase Studio User Manual

## 1. Purpose And Scope

Phase Studio is a crystallographic workflow application for running and
diagnosing iterative Superflip calculations in a Jana2020 environment. It is
designed for workflows where the crystallographer needs to combine reflection
data, reference crystallographic metadata, density maps, peak extraction and
Jana hand-off in a controlled and inspectable way.

The program supports two main operating modes:

- **Full Phase Studio GUI** launched from Python as `python -m phase_studio` or
  `phase-studio`.
- **Jana2020 Superflip wrapper** built as `superflip.exe` and launched by
  Jana2020 instead of the original Superflip executable.

The wrapper mode is intended to preserve a normal Jana2020 user workflow while
adding Phase Studio choices before the Superflip calculation is executed.

## 2. Crystallographic Concepts Used By Phase Studio

### 2.1 Jana `.inflip` As A Primary Input

A Jana `.inflip` file can provide:

- unit-cell parameters,
- space-group information,
- composition,
- Superflip keywords,
- an embedded `fbegin/endf` reflection block,
- optional reference-file declarations.

When `Jana .inflip` input mode is selected, Phase Studio treats the `.inflip`
file as the authoritative crystallographic input unless the user explicitly
selects override files.

### 2.2 External HKL And Reference Inputs

External input mode is used when reflection data and reference metadata are
available as separate files. In this mode:

- the HKL file supplies observed reflection records,
- `External reference file` is the single reference selector,
- CIF-compatible reference files supply the unit cell, space group, composition
  and optional atomic coordinates for metrics,
- Jana, XPLOR and CCP4 density maps are written as Superflip `referencefile`
  inputs, with the format inferred from the filename.

Fully external HKL mode still requires a CIF-compatible reference file because
HKL data alone do not contain the crystallographic model metadata needed by
EDMA, completeness analysis and structure metrics. In Jana `.inflip` modes,
map reference files can be used because the `.inflip` supplies the missing cell,
space group and composition.

### 2.3 HKL Data Formats

The `HKL data format` selector controls how reflection records are interpreted
and written to the Superflip `fbegin/endf` block.

Available modes:

- `auto`: first read `dataformat` / `dataitemwidths` from a Jana `.inflip` file
  when available, otherwise infer the most likely format from HKL headers and
  file names.
- `intensity`: interpret the observed value as intensity, typically
  `h k l I sigma(I)`.
- `amplitude_dummy_sigma`: interpret the observed value as `Fobs`; write
  `dataformat amplitude dummy` for Superflip.
- `fobs_zero_phase_sigma`: use fixed-width `h k l Fobs phase sigma` records
  and automatically calculate safe `dataitemwidths`.

Sigma values are retained internally when available and are used by HKL load
testing, completeness statistics, standardized HKL export and `I/sigma`
diagnostics.

## 3. Installation

### 3.1 Python Environment

Use Python 3.10 or newer.

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[app]"
```

Windows PowerShell:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[app]"
```

### 3.2 Starting The GUI

From the repository root:

```bash
python -m phase_studio
```

After editable installation:

```bash
phase-studio
```

### 3.3 SharpED API Token

SharpED server deblurring requires an API token. The token can be supplied in
the GUI or through an environment variable.

Linux/macOS:

```bash
export SHARPED_API_TOKEN=your-token
```

PowerShell:

```powershell
$env:SHARPED_API_TOKEN = "your-token"
```

## 4. Main GUI Overview

### 4.1 Paths Tab

The Paths tab defines the crystallographic inputs and external executables.

Important fields:

- `Input data mode`: selects Jana `.inflip`, Jana `.inflip` with overrides, or
  fully external HKL + CIF reference input.
- `Jana .inflip`: primary Jana/Superflip input file.
- `External HKL`: external reflection file used in override or external mode.
- `HKL data format`: controls interpretation of observed values and sigmas.
- `Test HKL load`: opens a diagnostic table showing parsed reflection records.
- `Analyze completeness`: opens the reflection completeness and intensity
  statistics window.
- `External reference file`: the single reference selector. CIF-compatible
  files provide crystallographic metadata and atom sites; Jana/XPLOR/CCP4 maps
  are passed to Superflip as `referencefile` inputs without an explicit
  `referenceformat` keyword.
- `First-cycle modelfile`: optional model or map for the first Superflip cycle.
- `Work directory`: output directory for generated inputs, maps, logs and
  metrics.
- `Superflip exe/path`: path to the original Superflip executable.
- `EDMA exe/path`: path to Jana EDMA.

### 4.2 Basic Workflow Tab

The Basic workflow tab controls the iterative policy.

Important controls:

- `Cycles to run`: number of wrapper cycles unless `none` forces one cycle.
- `Next-cycle modelfile`: source used from cycle 2 onward.
- `XPLOR damping 1/x`: inverse damping value for XPLOR model maps.
- `Run SharpED deblurring`: enables server deblurring for deblurred XPLOR
  workflows.
- `Run EDMA after Superflip map`: extracts peaks directly from the Superflip
  map.
- `Run EDMA after deblurred map`: extracts peaks after SharpED deblurring.

### 4.3 Advanced Superflip Tab

This tab exposes Superflip keywords and output choices.

Common controls:

- `perform`: charge-flipping algorithm.
- `outputformat`: Superflip output format keyword.
- `Save Superflip XPLOR map`, `Save Superflip CCP4 map`, `Save Superflip
  m80/m81`: output selection.
- `voxel`: omitted by default. Use explicit integer grid dimensions or `AUTO`
  only when a voxel keyword is desired.
- `bestdensities`, `polish`, `maxcycles`, `repeatmode`, `randomseed`, `delta`,
  `weakratio`, `Biso`: Superflip control keywords.
- `normalize`, `nresshells`, `missing`: normalization and missing-reflection
  controls.
- `Extra Superflip keywords`: advanced manual keyword insertion. Structural
  keywords owned by Phase Studio are filtered to avoid conflicting inputs.

### 4.4 Advanced EDMA Tab

This tab controls EDMA peak extraction and structure export.

Important controls:

- `plimit after Superflip sigma`: EDMA peak threshold for raw Superflip maps.
- `plimit after deblurring sigma`: EDMA peak threshold for deblurred maps.
- `Symmetry merge distance`: distance used for merging symmetry-equivalent peak
  candidates.
- `maxima`, `fullcell`, `numberofatoms`, `centerofcharge`, `chlimit`,
  `chlimlist`: EDMA keyword controls.

### 4.5 Map Feedback Tab

Map feedback can add missing reflections or adjust weak intensities using a
completed map. This is an advanced option and should be used cautiously because
it modifies the reflection set for later Superflip cycles.

Controls:

- `Add missing reflections from completed cycle`
- `Missing-reflection limit (%)`
- `Correct intensities from completed cycle`
- `Intensity correction damping`
- `Correct only below value/sigma`

### 4.6 SharpED Tab

The SharpED tab defines server connection and inference settings.

Controls:

- server URL,
- API token,
- model selection,
- element list,
- output resolution,
- HTTP timeout and polling parameters.

## 5. HKL Diagnostics

### 5.1 Test HKL Load

Use `Test HKL load` before running a reconstruction. The dialog reports:

- HKL source,
- selected or inferred data format,
- value and sigma column mapping,
- whether `(0,0,0)` is included,
- unit-cell and space-group source,
- number of parsed reflections,
- number of unique HKL records after duplicate merging,
- first reflection records with `h`, `k`, `l`, observed value, sigma, phase,
  d-spacing and `sin(theta)/lambda`.

This is the fastest way to confirm that an HKL file is being interpreted as
intensity data, amplitude data or fixed-width `Fobs/phase/sigma` data.

### 5.2 Analyze Completeness

`Analyze completeness` opens a reflection-statistics window with:

- `d_min`: highest-resolution reflection in the observed data.
- `d_full`: the high-resolution limit at which cumulative completeness remains
  at or above 98%.
- Shell completeness versus `sin(theta)/lambda`.
- Mean `I/sigma` per resolution shell.
- Frequency histogram of individual reflection `I/sigma` values.

The completeness estimate uses:

- the unit cell,
- the parsed space group,
- Laue-equivalent HKL reduction,
- Friedel-pair equivalence,
- systematic-absence filtering based on symmetry operations and translations.

The first plot combines shell completeness and mean `I/sigma`. Vertical markers
show `d_min` and `d_full`. The second plot shows the `I/sigma` frequency
distribution.

## 6. Iterative Superflip Workflows

### 6.1 No Next-Cycle Model

Select `none` when only one Superflip cycle is desired. The cycle count is
forced to one.

### 6.2 Raw Superflip XPLOR Cycling

Select `superflip_xplor` to use the raw Superflip XPLOR map as the next-cycle
modelfile. SharpED is not required for this cycling mode.

### 6.3 Deblurred XPLOR Cycling

Select `deblurred_xplor` to send the Superflip map to SharpED and use the
returned XPLOR map as the next-cycle Superflip modelfile.

### 6.4 EDMA CIF Cycling

Select `deblurred_edma_cif` to run EDMA after the deblurred map and use the
resulting CIF coordinates as the next-cycle model. Superflip infers CIF input
from the `.cif` extension; no explicit CIF model-format keyword is written.

### 6.5 XPLOR Damping

`XPLOR damping 1/x` is an inverse input. The GUI value is converted internally
to the old damping factor:

```text
GUI value 1.0  -> effective factor 1.0  -> no damping
GUI value 0.5  -> effective factor 2.0
GUI value 0.25 -> effective factor 4.0
```

The damped map is calculated as a weighted blend of the previous model and the
new XPLOR map. Damping is used only for XPLOR next-cycle model modes.

## 7. Outputs

Each cycle can write:

- generated Superflip `.inflip`,
- Superflip XPLOR map,
- optional CCP4 map,
- optional Jana m80/m81 outputs,
- Superflip log,
- EDMA CIF/XYZ/PDB output after the raw Superflip map,
- SharpED-deblurred XPLOR map,
- EDMA CIF/XYZ/PDB output after the deblurred map,
- `metrics.csv`,
- optional Jana2020 project export folders.

The work directory is user-configurable. Generated output directories and
common transient files are ignored by `.gitignore`.

## 8. Jana2020 Wrapper Mode

The wrapper is built from `phase_studio/jana_superflip.py` and is intended to be
deployed as `superflip.exe`.

Recommended deployment:

```text
C:\Jana2020\SUPERFLIP\superflip_original.exe
C:\Jana2020\SUPERFLIP\superflip.exe
C:\Jana2020\SUPERFLIP\EDMA.exe
```

The original Jana executable must remain available as
`superflip_original.exe`. When Jana2020 launches `superflip.exe`, Phase Studio
opens a launcher dialog. The user can run the simplified wrapper workflow or
open the full Phase Studio configuration.

After cycles are complete, Phase Studio can pass the selected Superflip or
deblurred map back to Jana2020 for the final hand-off calculation.

## 9. Building The Wrapper

Install build dependencies:

```bash
python -m pip install -e ".[app,build]"
```

Run PyInstaller:

```bash
python -m PyInstaller --clean --noconfirm superflip.spec
```

The built folder is:

```text
dist/superflip/
```

Copy the complete folder contents into the Jana2020 Superflip directory.

## 10. Validation And Maintenance

Compile-check Python files:

```bash
python -m compileall -q phase_studio
```

Validate packaging:

```bash
python -m pip install --no-deps --prefix /tmp/phase_studio_install_test .
```

Clean local generated artifacts:

```bash
rm -rf build dist phase_studio.egg-info phase_studio/__pycache__
```

## 11. Troubleshooting

### Gemmi Cannot Be Imported

Install `gemmi` in the active Python environment:

```bash
python -m pip install gemmi
```

or use conda-forge:

```bash
conda install -c conda-forge gemmi
```

### PySide6 Cannot Be Imported

Install the GUI extra:

```bash
python -m pip install -e ".[app]"
```

### SharpED Token Missing

Enter the token in the SharpED tab or set `SHARPED_API_TOKEN`.

### Superflip Executable Not Found

Check the `Superflip exe/path` field. In full GUI mode it should point to the
original Superflip executable, not to the Phase Studio wrapper.

### Jana Wrapper Cannot Find The Original Superflip

Verify that the original executable is available as:

```text
C:\Jana2020\SUPERFLIP\superflip_original.exe
```

or place `superflip_original.exe` next to the wrapper.

### Completeness Looks Too Low

Check:

- unit cell and space group source,
- whether the correct Jana `.inflip` or CIF-compatible reference file is selected,
- `HKL data format`,
- whether the data are intensities or amplitudes,
- whether the reflection file contains merged or unmerged data.

Use `Test HKL load` first, then `Analyze completeness`.

## 12. Recommended GitHub Commit

Suggested commit title:

```text
docs: add GitHub README and crystallographic user manual
```

Suggested commit body:

```text
- Expand README with installation, workflow and Jana2020 wrapper instructions
- Add complete English user manual for crystallographic workflows
- Document HKL diagnostics, completeness statistics and XPLOR damping semantics
```

# Phase Studio User Manual

## 1. Overview

Phase Studio is a crystallographic workflow application that integrates:

* Superflip charge flipping,
* SharpED density-map deblurring,
* EDMA peak searching,
* reflection-data diagnostics,
* density-map conversion and symmetrization,
* iterative model-seeded reconstruction,
* and Jana2020 hand-off tools.

The application can be used in two principal ways:

1. as a companion application for Jana2020 projects;
2. as a standalone workflow using external HKL and CIF data.

Phase Studio does not replace crystallographic refinement in Jana2020. Its primary purpose is to integrate structure solution, density-map processing, peak searching, diagnostic analysis, and model preparation.

---

# 2. Installation

## 2.1 Windows Executable

A prebuilt Windows version is available from:

https://github.com/ji-ze/Phase-Studio/releases

The prebuilt application can be launched directly and does not require a separate Python installation.

### Required external programs

The Windows package does not include Superflip or EDMA.

Install both programs separately from:

https://superflip.fzu.cz/

Superflip and EDMA are required even when the prebuilt Phase Studio executable is used.

After installation, configure their executable paths in Phase Studio if they are not detected automatically.

Jana2020 is required for:

* direct use of Jana `.inflip` files,
* Jana-specific project integration,
* and transfer of generated results back to Jana2020.

Jana2020 is not strictly required for workflows based entirely on external HKL and CIF data.

---

## 2.2 SharpED API Token

SharpED integration is optional.

A SharpED API token is required only when server-side SharpED density-map deblurring is enabled.

Jana2020 users can obtain a token from:

https://sharped.fzu.cz/

The same website provides an online SharpED application that can be used independently of Phase Studio.

The API token can be entered directly in the Phase Studio graphical interface.

It can also be supplied through the `SHARPED_API_TOKEN` environment variable.

### Linux and macOS

```bash
export SHARPED_API_TOKEN="your-token"
```

### Windows PowerShell

```powershell
$env:SHARPED_API_TOKEN = "your-token"
```

Do not commit API tokens to public repositories or store them in publicly accessible configuration files.

---

## 2.3 Installation from Python Source

Running Phase Studio from source requires Python 3.10 or newer.

### Required Python packages

* `numpy`
* `matplotlib`
* `gemmi`
* `PySide6`

### Optional packages

* `qtvscodestyle` for consistent graphical-interface styling;
* `pyinstaller` for building the Windows executable and Jana2020 wrapper.

### Linux and macOS

```bash
python -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e ".[app]"

python -m phase_studio
```

### Windows PowerShell

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -e ".[app]"

python -m phase_studio
```

After installation, the application can also be started using:

```bash
phase-studio
```

---

# 3. Input Modes

Phase Studio supports three principal input modes.

## 3.1 Jana `.inflip`

This mode loads an existing Jana2020 `.inflip` file and uses the Superflip settings defined in that file.

Selected settings can be overridden from the Phase Studio interface without manually editing the original input file.

This mode is suitable for:

* reproducing an existing Jana2020 Superflip calculation;
* testing alternative charge-flipping settings;
* applying EDMA to generated maps;
* optionally processing maps with SharpED;
* and transferring the selected result back to Jana2020.

---

## 3.2 Jana `.inflip` with External Overrides

This mode uses a Jana `.inflip` file as the workflow template while replacing selected inputs.

Possible overrides include:

* an external HKL file;
* an external reference CIF;
* alternative cell parameters;
* alternative symmetry information;
* reflection-data-format settings;
* and selected Superflip options.

Use this mode when the Jana project contains the required structure-solution configuration but the reflection data or reference model must be replaced.

---

## 3.3 External HKL and CIF Reference

This mode creates a structure-solution workflow without requiring an existing Jana `.inflip` file.

Typical inputs include:

* an HKL reflection file;
* unit-cell parameters;
* space-group symmetry;
* reflection-data-format information;
* and an optional CIF reference structure.

This mode is suitable for datasets prepared outside Jana2020 or for exploratory calculations before a complete Jana project has been created.

---

# 4. Reflection-Data Configuration

## 4.1 HKL Data Format

The reflection-data format determines how Phase Studio and Superflip interpret individual columns in the HKL file.

When `auto` mode is selected, Phase Studio first attempts to read the following settings from the Jana `.inflip` file:

* `dataformat`;
* `dataitemwidths`.

If these values are unavailable or incompatible with the supplied HKL file, configure the format manually.

---

## 4.2 Test HKL Load

Always use **Test HKL load** before starting a complete reconstruction.

The test verifies:

* whether the HKL file can be read;
* which columns are interpreted as indices and reflection values;
* whether amplitudes, intensities, and uncertainty values are parsed correctly;
* and whether the selected format is consistent with the input file.

An incorrect HKL format may produce a calculation that runs without an obvious error but uses incorrect reflection values.

---

## 4.3 Completeness Analysis

Use **Analyze completeness** to inspect the reflection dataset.

The analysis can include:

* total reflection count;
* resolution range;
* minimum spacing, `d_min`;
* fully complete resolution, `d_full`;
* shell completeness;
* intensity-to-uncertainty statistics;
* and resolution-dependent reflection distributions.

These diagnostics can reveal:

* incomplete high-resolution shells;
* incorrect indexing;
* mismatched unit-cell parameters;
* inconsistent symmetry;
* unexpected resolution cutoffs;
* duplicated reflections;
* or incorrect interpretation of intensity and uncertainty columns.

---

# 5. Superflip Workflow

Superflip is used for charge-flipping structure solution and phase retrieval.

Phase Studio prepares the required input files, launches the Superflip executable, and records the generated outputs.

Typical Superflip outputs include:

* density or electrostatic-potential maps;
* phase information;
* model files;
* convergence information;
* and intermediate cycle results.

The generated files are stored within the Phase Studio workflow directory so that individual reconstruction cycles remain traceable.

---

# 6. Density-Map Processing

Phase Studio can work with several types of maps:

* raw Superflip maps;
* symmetrized Superflip maps;
* SharpED-deblurred maps;
* maps reconstructed from modified amplitudes or phases;
* and maps generated from intermediate structural models.

Original and processed maps should remain stored separately.

This allows direct comparison of:

* the original Superflip reconstruction;
* the symmetrized map;
* the SharpED result;
* different peak-search settings;
* and maps generated during later iterative cycles.

---

# 7. SharpED Processing

SharpED can optionally be applied to a reconstructed density or electrostatic-potential map.

The purpose of SharpED is to improve:

* localization of atomic-density maxima;
* separation of overlapping maxima;
* visual interpretability of the map;
* and the quality of input supplied to peak searching.

A SharpED-processed map can be used for:

* visual inspection;
* comparison with the original reconstruction;
* EDMA peak searching;
* generation of an updated structural model;
* export to external crystallographic software;
* and model-seeded Superflip calculations.

SharpED is not required for standard Superflip and EDMA workflows.

---

# 8. EDMA Peak Searching

EDMA identifies candidate atomic positions in density or electrostatic-potential maps.

EDMA can be applied to:

* raw Superflip maps;
* symmetrized maps;
* SharpED-deblurred maps;
* and maps generated during later reconstruction cycles.

Peak-search results can be:

* inspected;
* filtered;
* exported as structural models;
* used as starting positions for Jana2020 refinement;
* or reused as seeds for a subsequent Superflip cycle.

EDMA provides the connection between reconstructed density maxima and candidate atomic coordinates.

---

# 9. Iterative Model-Seeded Reconstruction

Phase Studio supports iterative Superflip calculations seeded by previously generated structural models.

Possible model sources include:

* Superflip model files;
* EDMA peak-search results;
* models generated from SharpED-deblurred maps;
* partially completed Jana2020 structures;
* external CIF files;
* and manually edited intermediate models.

A typical iterative workflow is:

1. run an initial Superflip calculation;
2. generate and inspect the density map;
3. optionally symmetrize the map;
4. optionally apply SharpED deblurring;
5. run EDMA peak searching;
6. inspect or edit the generated model;
7. select the next-cycle model;
8. configure model damping;
9. run a new Superflip cycle;
10. compare the resulting maps and models.

Model damping can be used to control the influence of the supplied starting model on the subsequent reconstruction.

This workflow is useful when the initial charge-flipping solution contains recognizable structural fragments but is incomplete or difficult to interpret.

---

# 10. Jana2020 Hand-Off

For workflows originating from Jana2020, selected maps and models can be transferred back to Jana2020.

Transferable results may include:

* EDMA-derived atomic positions;
* SharpED-assisted models;
* Superflip model files;
* CIF structures;
* processed density maps;
* and selected reconstruction-cycle outputs.

The hand-off procedure reduces the need for manual file conversion and editing.

After transfer, detailed model completion and crystallographic refinement should be performed in Jana2020.

---

# 11. Recommended User Workflow

1. Start Phase Studio.
2. Select the appropriate input mode.
3. Load the `.inflip`, HKL, and optional CIF files.
4. Verify the reflection-data format.
5. Run **Test HKL load**.
6. Run **Analyze completeness**.
7. Check `d_min`, `d_full`, completeness, and intensity statistics.
8. Configure Superflip settings.
9. Configure the next-cycle model policy and damping if required.
10. Configure EDMA options.
11. Enter the SharpED token if deblurring is required.
12. Run the pipeline.
13. Inspect the generated maps and models.
14. Compare raw, symmetrized, and SharpED-processed results.
15. Select the preferred cycle or model.
16. Export the result or transfer it back to Jana2020.

---

# 12. Building the Jana2020 Superflip Wrapper

Install the graphical-interface and build dependencies:

```bash
python -m pip install -e ".[app,build]"
```

Build the wrapper using PyInstaller:

```bash
python -m PyInstaller --clean --noconfirm superflip.spec
```

The expected output is:

```text
dist/superflip/superflip.exe
```

Keep the complete `dist/superflip/` directory together. Required Python packages and DLL files are stored next to the executable.

---

## 12.1 Recommended Jana2020 Deployment

Recommended installation directory:

```text
C:\Jana2020\SUPERFLIP
```

Recommended file layout:

```text
C:\Jana2020\SUPERFLIP\superflip_original.exe
C:\Jana2020\SUPERFLIP\superflip.exe
C:\Jana2020\SUPERFLIP\EDMA.exe
```

Deployment procedure:

1. Close Jana2020.

2. Open:

   ```text
   C:\Jana2020\SUPERFLIP
   ```

3. Rename the original Jana2020 executable:

   ```text
   superflip.exe
   ```

   to:

   ```text
   superflip_original.exe
   ```

4. Copy the complete contents of:

   ```text
   dist\superflip\
   ```

   into:

   ```text
   C:\Jana2020\SUPERFLIP
   ```

5. Confirm that `EDMA.exe` is installed.

6. Start Jana2020.

7. Run a Superflip calculation normally.

The wrapper searches for the original Superflip executable in the following order:

```text
C:\Jana2020\SUPERFLIP\superflip_original.exe
<wrapper directory>\superflip_original.exe
<wrapper directory>\SuperFlip-orig.exe
<wrapper directory>\superflip-original.exe
PATH: superflip_original.exe
PATH: SuperFlip-orig.exe
```

---

# 13. Repository Layout

```text
phase_studio/                  Python package and GUI source code
phase_studio/app.py            Main Phase Studio GUI and reconstruction pipeline
phase_studio/jana_superflip.py Jana2020-compatible Superflip wrapper launcher
phase_studio/ui_style.py       Qt styling utilities
superflip.spec                 PyInstaller specification for the Jana wrapper
pyproject.toml                 Package metadata and optional dependencies
README.md                      Quick-start and project overview
MANUAL.md                      Detailed user and developer documentation
documentation/                 Optional local reference material
examples/                      Optional local example datasets
```

The `documentation/` and `examples/` directories may contain local files that are not included in version control.

---

# 14. Package Validation

Compile-check the Python package:

```bash
python -m compileall -q phase_studio
```

Validate package metadata and installation without installing runtime dependencies:

```bash
python -m pip install --no-deps --prefix /tmp/phase_studio_install_test .
```

Remove generated build artifacts on Linux or macOS:

```bash
rm -rf build dist phase_studio.egg-info phase_studio/__pycache__
```

Windows PowerShell:

```powershell
Remove-Item -Recurse -Force build, dist, phase_studio.egg-info
Remove-Item -Recurse -Force phase_studio\__pycache__
```

---

# 15. Reproducibility

Phase Studio is designed to preserve:

* original input files;
* explicit workflow parameters;
* generated Superflip input files;
* intermediate maps;
* EDMA outputs;
* SharpED outputs;
* model-seeding decisions;
* and final exported results.

This is important when comparing:

* alternative charge-flipping parameters;
* different reflection-data formats;
* raw and SharpED-processed maps;
* EDMA peak-search thresholds;
* model-damping values;
* and different iterative reconstruction strategies.

---

# 16. External Resources

* Phase Studio releases:
  https://github.com/ji-ze/Phase-Studio/releases

* Superflip and EDMA:
  https://superflip.fzu.cz/

* SharpED, online application, and API-token access:
  https://sharped.fzu.cz/

---

# 17. Notes

* Superflip and EDMA are not included in the Phase Studio Windows package.
* SharpED processing requires network access and a valid API token.
* Phase Studio can run without SharpED.
* Jana2020 is required only for Jana-specific integration and hand-off workflows.
* Generated Superflip, EDMA, SharpED, and PyInstaller outputs should be excluded through `.gitignore`.
* Reference copies of older Phase Studio versions are not required for normal operation.

