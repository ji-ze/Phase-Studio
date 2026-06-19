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

### 2.2 External HKL And Reference CIF Inputs

External input mode is used when reflection data and reference metadata are
available as separate files. In this mode:

- the HKL file supplies observed reflection records,
- the reference CIF supplies the unit cell, space group, composition and
  optional atomic coordinates for metrics,
- optional XPLOR or CIF files may be used as Superflip `referencefile` inputs.

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
  fully external HKL + reference CIF input.
- `Jana .inflip`: primary Jana/Superflip input file.
- `External HKL`: external reflection file used in override or external mode.
- `HKL data format`: controls interpretation of observed values and sigmas.
- `Test HKL load`: opens a diagnostic table showing parsed reflection records.
- `Analyze completeness`: opens the reflection completeness and intensity
  statistics window.
- `External reference CIF`: source of unit cell, space group, composition and
  optional reference atoms in external mode.
- `Superflip referencefile`: explicit Superflip `referencefile` input, written
  only when selected.
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
- whether the correct Jana `.inflip` or reference CIF is selected,
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
