# Phase Studio User Manual

## 1. Purpose And Scope

Phase Studio is a crystallographic workflow application for running and
diagnosing iterative Superflip calculations in a Jana2020 environment. It
combines:

- Superflip charge flipping,
- optional SharpED density-map deblurring,
- EDMA peak searching,
- reflection-data diagnostics,
- density-map conversion and symmetrization,
- iterative model-seeded reconstruction,
- and Jana2020 hand-off tools.

The application can be used in two principal ways:

1. as a companion application for Jana2020 projects;
2. as a standalone workflow using external HKL and CIF-compatible reference
   data.

Phase Studio does not replace crystallographic refinement in Jana2020. Its
primary purpose is to integrate structure solution, density-map processing,
peak searching, diagnostic analysis and model preparation in a controlled and
inspectable way.

The program supports two operating modes:

- **Full Phase Studio GUI** launched from Python as `python -m phase_studio` or
  `phase-studio`.
- **Jana2020 Superflip wrapper** built as `superflip.exe` and launched by
  Jana2020 instead of the original Superflip executable.

The wrapper mode preserves a normal Jana2020 user workflow while adding Phase
Studio choices before the Superflip calculation is executed.

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
available as separate files. In the full GUI:

- the HKL file supplies observed reflection records,
- `External reference file` is the single reference selector,
- CIF/INS/RES-compatible reference files supply the unit cell, space group,
  composition and optional atomic coordinates for metrics,
- Jana, XPLOR and CCP4 density maps are written as Superflip `referencefile`
  inputs, with the format inferred from the filename.

Fully external HKL mode requires a CIF/INS/RES-compatible reference file.
HKL data alone do not contain the crystallographic model metadata needed by
EDMA, completeness analysis and structure metrics. In Jana `.inflip` modes,
map reference files can be used because the `.inflip` supplies the missing
cell, space group and composition.

### 2.3 HKL Data Formats

The `HKL data format` selector controls how reflection records are interpreted
and written to the Superflip `fbegin/endf` block.

Available modes:

- `auto`: first read `dataformat` / `dataitemwidths` from a Jana `.inflip`
  file when available, otherwise infer the most likely format from HKL headers
  and file names.
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

### 3.1 Windows Executable

A prebuilt Windows version is available from:

https://github.com/ji-ze/Phase-Studio/releases

The prebuilt application can be launched directly and does not require a
separate Python installation.

The Windows package does not include Superflip or EDMA. Install both programs
separately from:

https://superflip.fzu.cz/

After installation, configure their executable paths in Phase Studio if the
default paths do not match your system.

Jana2020 is required for direct use of Jana `.inflip` files, Jana-specific
project integration and transfer of generated results back to Jana2020.
Jana2020 is not strictly required for workflows based entirely on external HKL
and CIF-compatible reference data.

### 3.2 Python Environment

Use Python 3.10 or newer.

Required Python packages:

- `numpy`
- `matplotlib`
- `gemmi`
- `PySide6` for the GUI

Optional packages:

- `qtvscodestyle` for consistent graphical-interface styling;
- `pyinstaller` for building the Windows executable and Jana2020 wrapper.

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

After editable installation, the GUI can also be started with:

```bash
phase-studio
```

### 3.3 SharpED API Token

SharpED integration is optional. A SharpED API token is required only when
server-side SharpED density-map deblurring is enabled.

Jana2020 users can obtain a token from:

https://sharped.fzu.cz/

The same website provides an online SharpED application that can be used
independently of Phase Studio.

The API token can be entered directly in the SharpED tab. It can also be
supplied through the `SHARPED_API_TOKEN` environment variable.

Linux/macOS:

```bash
export SHARPED_API_TOKEN="your-token"
```

Windows PowerShell:

```powershell
$env:SHARPED_API_TOKEN = "your-token"
```

Do not commit API tokens to public repositories or store them in publicly
accessible configuration files.

## 4. Main GUI Overview

The full GUI has settings tabs on the left and output views on the right. The
right side contains a normalized Superflip metrics plot, a synchronized
three-view structure preview and the execution log. Dragging any structure
preview rotates all three views together. Hydrogens are hidden in the preview.

The GUI stores settings through Qt `QSettings` under the application name
`PhaseStudio`.

### 4.1 Paths Tab

The Paths tab defines crystallographic inputs and external executables.

- `Input data mode`: selects `Jana .inflip`,
  `Jana .inflip with external HKL/reference overrides`, or
  `External HKL + CIF reference`.
- `Jana .inflip`: primary Jana/Superflip input file.
- `External HKL`: external reflection file used in override or external mode.
- `HKL data format`: controls interpretation of observed values and sigmas.
- `External reference file`: single selector for CIF/INS/RES structures or
  Jana/XPLOR/CCP4 map reference files. Fully external HKL mode requires a
  CIF/INS/RES structure.
- `First-cycle modelfile`: optional XPLOR, CCP4 or CIF model/map for cycle 1.
- `Work directory`: output directory for generated inputs, maps, logs and
  metrics.
- `Superflip exe/path`: path to the original Superflip executable. In full GUI
  mode do not select the Phase Studio wrapper named `superflip.exe`.
- `EDMA exe/path`: path to Jana EDMA.

### 4.2 Basic v3 Tab

The Basic v3 tab controls the iterative policy and common optional steps.

- `Sample/data preset`: high-level starting preset. It sets only basic
  defaults; advanced Superflip and EDMA keywords remain editable.
- `Cycles to run`: number of iterative cycles. If `Next-cycle modelfile` is
  `none`, the run is forced to one cycle.
- `Composition override`: optional Superflip composition string. Leave blank to
  derive composition from the reference CIF formula or atom list.
- `Next-cycle modelfile`: authoritative source for cycle 2 and later:
  `superflip_xplor`, `deblurred_xplor`, `deblurred_edma_cif`, or `none`.
- `XPLOR damping 1/x`: inverse damping value used only for XPLOR next-cycle
  model modes.
- `Exclude atoms from model CIF`: atom labels to remove from CIF modelfiles
  before the next cycle. Use comma, semicolon or whitespace separation.
- `Run EDMA after Superflip map`: run EDMA on the raw Superflip XPLOR map.
- `Run SharpED deblurring`: send the Superflip XPLOR map to the SharpED server.
  This is automatically disabled for raw `superflip_xplor` cycling.
- `Symmetrize deblurred map with Superflip`: after SharpED, run Superflip in
  `perform symmetry` mode with the deblurred XPLOR map as `modelfile`.
- `Run EDMA after deblurred map`: run EDMA on the deblurred/symmetrized map.

### 4.3 Advanced: Superflip Tab

This tab exposes Superflip keywords and output choices.

- `perform`: Superflip `perform` keyword. Common values are `CF`, `lde`,
  `general`, `fourier` and `symmetry`; `AAR` is kept for executables that
  support it.
- `outputformat`: Superflip output format keyword.
- `Legacy outputfile m81/m80/xplor`: write three outputfile names like
  Jana/Superflip templates.
- `Save Superflip XPLOR map`: request an XPLOR map. XPLOR is also kept
  internally because EDMA and SharpED consume this map format.
- `Save Superflip CCP4 map`: request an additional CCP4 map.
- `Save Superflip m80/m81`: request Jana density and phased-reflection outputs.
- `Save standardized HKL I/sigma/phase`: write a standardized observed
  reflection export with `h k l I sigma(I) phase(deg)`.
- `Export complete Jana2020 project folder`: create a Jana2020 export folder
  for each cycle with Superflip, EDMA, map, CIF and log outputs.
- `referencefile`: automatic note. The keyword is omitted by default and is
  written only when `External reference file` is selected.
- `voxel`: omitted by default. Use three integers, for example `180 80 160`,
  or `AUTO` to compute a grid from the unit cell.
- `bestdensities count`, `bestdensities metric`, `bestdensities symmetry`:
  controls for Superflip best-density selection.
- `polish yes`: writes `polish yes` when enabled.
- `maxcycles`, `repeatmode`, `Random seed`, `delta`, `weakratio`, `Biso`:
  Superflip control keywords.
- `Value/sigma min filter`: removes weak observed reflections before writing
  the Superflip HKL block.
- `Resolution d min cutoff A`: optional resolution cutoff in Angstrom. `0`
  keeps all reflections.
- `normalize`, `nresshells`, `missing keyword`: normalization and
  missing-reflection controls.
- `searchsymmetry`, `derivesymmetry`, `electrons`: symmetry and electron
  keyword controls.
- `dataitemwidths`: automatic note. Phase Studio generates widths from the
  exact `fbegin/endf` records written to the Superflip input.
- `Extra Superflip keywords`: additional raw Superflip keyword lines inserted
  before `fbegin`. Structural keywords owned by Phase Studio are filtered to
  avoid conflicting inputs.

### 4.4 Advanced: EDMA Tab

This tab controls EDMA peak extraction and structure export.

- `plimit after Superflip sigma`: EDMA peak threshold for raw Superflip maps,
  expressed as a multiplier of XPLOR map sigma.
- `plimit after deblurring sigma`: EDMA peak threshold for deblurred maps,
  expressed as a multiplier of XPLOR map sigma.
- `Symmetry merge distance A`: distance used for reducing EDMA maxima to one
  representative per full space-group orbit before writing the CIF asymmetric
  unit.
- `maxima`: EDMA maxima keyword. `all` lists all density maxima above `plimit`.
- `fullcell`: EDMA fullcell keyword.
- `numberofatoms`: EDMA structure-export count policy. `composition` asks EDMA
  to export atom counts consistent with the chemical composition.
- `centerofcharge yes`: enables EDMA center-of-charge peak refinement.
- `chlimit`, `chlimlist`: charge threshold controls.
- `Extra EDMA keywords`: additional raw EDMA keyword lines appended to the
  generated EDMA input.

### 4.5 Advanced: Map Feedback Tab

Map feedback can add missing reflections or adjust weak intensities using a
completed map. This is an advanced option and should be used cautiously because
it modifies the reflection set for later Superflip cycles.

- `Add missing reflections from completed cycle`: first completed cycle whose
  final map is used to add missing reflections. `0` disables the feature.
- `Missing-reflection limit (%)`: maximum number of added missing reflections,
  expressed as a percent of the current HKL count.
- `Correct intensities from completed cycle`: first completed cycle whose final
  map is used to damp observed intensities. `0` disables the feature.
- `Intensity correction damping`: `0` keeps observed data; `1` replaces them by
  scaled map-derived intensities.
- `Correct only below value/sigma`: apply map-based intensity correction only
  to non-zero reflections below this value/sigma limit. `0` corrects all
  non-zero reflections.

### 4.6 Help Tab

The Help tab contains a read-only Superflip keyword quick reference. It lists
structural keywords generated from the reference CIF, reflection-data keywords,
output/model-file keywords, density-modification controls, normalization and
missing-reflection controls, symmetry/origin options, grid options and examples
of manual keyword lines for `Extra Superflip keywords`.

### 4.7 SharpED Tab

The SharpED tab defines server connection and inference settings.

- `Server URL`: SharpED inference server base URL. The application default is
  `https://jana.fzu.cz`.
- `API token`: user token sent as `Authorization: Bearer ...` during upload,
  status and download requests.
- `Model`: SharpED model name. `default` queries the server model list and uses
  the server default.
- `Elements`: chemical elements sent to the server. Leave blank to derive
  unique non-H elements from the reference composition.
- `outres`: requested SharpED output-map sampling.
- `Max upload size MB`: maximum XPLOR map size uploaded to the SharpED server.
  Use `100` MB for the current public server limit. If `voxel` is omitted,
  Phase Studio can add a coarser Superflip voxel keyword before map calculation
  so the native Superflip XPLOR fits. Set `0` to disable this check.
- `HTTP timeout seconds`: timeout for model query, upload, status and download
  requests. Phase Studio enforces at least 600 seconds for large XPLOR uploads.
- `Poll seconds`: seconds between status polling requests.
- `Max polls (-1 = no limit)`: maximum number of status polls.

## 5. Button Reference

This section lists the clickable controls implemented in the current code.

### 5.1 File And Directory Browse Buttons

Each path row has a `...` browse button. For file rows it opens a file chooser;
for `Work directory` it opens a directory chooser. The selected value is written
back to the adjacent text field and saved in the GUI settings.

### 5.2 HKL Buttons

- `Test HKL load`: parses the selected HKL file or Jana `.inflip`
  `fbegin/endf` block and opens a diagnostic table with source, inferred
  format, value/sigma/phase mapping, `(0,0,0)` status, cell and space-group
  source, parsed reflection count, unique merged count and sample records.
- `Analyze completeness`: opens completeness and data-statistics plots for the
  selected HKL data.

### 5.3 Superflip And SharpED Utility Buttons

- `Load settings from .inflip`: reads Superflip keyword settings from an
  existing `.inflip` file. Reflection blocks are ignored during settings import.
- `Refresh available models`: queries the configured SharpED server and updates
  the `Model` selector. In the full GUI this runs automatically once shortly
  after startup and can also be run manually.

### 5.4 Main Run Buttons

- `Run`: validates inputs, executable paths and export selections, creates the
  work directory if needed and starts the complete iterative pipeline.
- `Stop after current cycle`: requests a graceful stop once the currently
  running cycle has completed.
- `Stop now`: terminates the currently running external Superflip/EDMA process
  and stops the pipeline as soon as possible. SharpED polling also checks this
  stop request.
- `Pass data to Jana2020`: enabled after a completed run that has a Jana
  `.inflip`. It opens a hand-off dialog where a cycle and map source are chosen.
- `Clear`: clears the log panel and resets plotted metrics for the current GUI
  session.

### 5.5 Dialog Buttons In The Full GUI

- HKL diagnostic and completeness dialogs use `Close`.
- The Jana hand-off dialog uses `Pass to Jana2020` and `Cancel`.
  The suggested cycle is selected by the best Superflip symmetry agreement
  (lowest `Symm.` residual), but the user can override it manually.

### 5.6 Jana2020 Wrapper Launcher Buttons

When Phase Studio is built as `superflip.exe` and launched by Jana2020, the
launcher dialog contains these buttons:

- `Browse...` beside `External HKL`, `Reference CIF / XPLOR`,
  `Cycle 1 modelfile` and `Superflip referencefile`: selects the corresponding
  override or optional model/reference file.
- `SharpED API and model settings`: expands or collapses the SharpED connection
  settings in the wrapper launcher.
- `Refresh available models`: queries `/sharp-ed/models` on the selected server
  and repopulates the model selector.
- `Cancel`: closes the launcher without starting or modifying the Jana2020 job.
- `Open full Phase Studio configuration`: opens the complete Phase Studio
  workspace with parameters imported from the Jana2020 `.inflip`.
- `Run Jana2020 calculation`: executes the Jana2020 Superflip job through the
  Phase Studio cycle wrapper.
- Wrapper hand-off dialogs use `Pass to Jana2020` and `Cancel`.

## 6. HKL Diagnostics

### 6.1 Test HKL Load

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

### 6.2 Analyze Completeness

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

These diagnostics can reveal incomplete high-resolution shells, incorrect
indexing, mismatched unit-cell parameters, inconsistent symmetry, unexpected
resolution cutoffs, duplicated reflections or incorrect interpretation of
intensity and uncertainty columns.

## 7. Iterative Superflip Workflows

### 7.1 No Next-Cycle Model

Select `none` when only one Superflip cycle is desired. The cycle count is
forced to one.

### 7.2 Raw Superflip XPLOR Cycling

Select `superflip_xplor` to use the raw Superflip XPLOR map as the next-cycle
modelfile. SharpED is not required for this cycling mode. In the current full
GUI configuration, SharpED deblurring and deblurred-map symmetrization are
skipped for this mode.

### 7.3 Deblurred XPLOR Cycling

Select `deblurred_xplor` to send the Superflip map to SharpED and use the
returned XPLOR map as the next-cycle Superflip modelfile.

### 7.4 EDMA CIF Cycling

Select `deblurred_edma_cif` to run EDMA after the deblurred map and use the
resulting CIF coordinates as the next-cycle model. Superflip infers CIF input
from the `.cif` extension; no explicit CIF model-format keyword is written.

### 7.5 XPLOR Damping

`XPLOR damping 1/x` is an inverse input. The GUI value is converted internally
to the old damping factor:

```text
GUI value 1.0  -> effective factor 1.0  -> no damping
GUI value 0.5  -> effective factor 2.0
GUI value 0.25 -> effective factor 4.0
```

The damped map is calculated as a weighted blend of the previous model and the
new XPLOR map. Damping is used only for XPLOR next-cycle model modes and is
ignored for CIF or `none`.

## 8. SharpED API Operation

Phase Studio uses server-side SharpED inference; it does not run local SharpED
neural-network inference.

The default API base URL in both the full GUI and Jana wrapper code is:

```text
https://jana.fzu.cz
```

API-token access and the online SharpED application are documented for users at:

```text
https://sharped.fzu.cz/
```

### 8.1 Model Discovery

When `Model` is `default`, or when the user presses `Refresh available models`,
Phase Studio sends:

```text
GET /sharp-ed/models
```

The response is expected to be JSON with a server default model and a list of
available model names. If model discovery fails, the model can still be entered
manually.

### 8.2 Upload And Processing

When SharpED deblurring is enabled, Phase Studio:

1. prepares the Superflip XPLOR map for upload;
2. checks the configured upload-size limit;
3. creates a multipart request containing:
   - `file`: the XPLOR map,
   - `elements`: the element list,
   - `outres`: requested output sampling,
   - `model`: the selected model name;
4. sends:

```text
POST /api/user/sharp-ed/upload
Authorization: Bearer <API token>
```

The upload response is expected to contain `success`, a job `token`, optional
`job_id` and optional `status_url`. If no `status_url` is returned, Phase Studio
uses:

```text
/api/user/sharp-ed/status/<job-token>
```

### 8.3 Polling And Download

Phase Studio polls the job status using bearer-token authentication. The client
tries both the user API token and the job token for status/download requests,
because server deployments may differ in which token they require.

A job is treated as complete when the status is one of `completed`, `complete`,
`done`, `ready`, `finished`, `success` or `succeeded`, or when a download URL or
output filename is present. A job is treated as failed when the status is one of
`failed`, `failure`, `error`, `errored`, `cancelled` or `canceled`.

If no download URL is supplied for a completed job, Phase Studio uses:

```text
GET /api/user/sharp-ed/download/<job-token>
```

The downloaded body is written to the configured output map path. Phase Studio
checks that the output is non-empty and does not look like a JSON/HTML/error
response. SharpED messages for each deblurred map are also written to a
`*.sharped.log` file next to the output map.

## 9. Outputs

Each cycle can write:

- generated Superflip `.inflip`,
- Superflip XPLOR map,
- optional CCP4 map,
- optional Jana m80/m81 outputs,
- standardized HKL export,
- Superflip log,
- EDMA CIF/XYZ/PDB output after the raw Superflip map,
- SharpED-deblurred XPLOR map,
- optional Superflip-symmetrized deblurred XPLOR map,
- EDMA CIF/XYZ/PDB output after the deblurred map,
- `metrics.csv`,
- optional Jana2020 project export folders.

The work directory is user-configurable. Original and processed maps are stored
separately so raw Superflip maps, symmetrized maps, SharpED results, EDMA
outputs and later iterative-cycle maps can be compared directly.

## 10. Jana2020 Hand-Off

For workflows originating from Jana2020, selected maps and models can be
transferred back to Jana2020.

Transferable results may include:

- EDMA-derived atomic positions,
- SharpED-assisted models,
- Superflip model files,
- CIF structures,
- processed density maps,
- and selected reconstruction-cycle outputs.

The hand-off procedure reduces the need for manual file conversion and editing.
After transfer, detailed model completion and crystallographic refinement
should be performed in Jana2020.

## 11. Jana2020 Wrapper Mode

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

The wrapper searches for the original Superflip executable in the following
order:

```text
C:\Jana2020\SUPERFLIP\superflip_original.exe
<wrapper directory>\superflip_original.exe
<wrapper directory>\SuperFlip-orig.exe
<wrapper directory>\superflip-original.exe
PATH: superflip_original.exe
PATH: SuperFlip-orig.exe
```

Wrapper input modes:

- `Jana .inflip`: incoming Jana `.inflip` remains the primary input.
- `Jana .inflip with external HKL/CIF overrides`: incoming `.inflip` remains
  the template, while selected HKL/reference files replace matching sources.
- `External HKL + reference CIF`: external files supply reflection/reference
  data; the incoming Jana `.inflip` is used as a hand-off template and for
  compatible Superflip keywords.

For model-seeded wrapper cycles, `repeatmode` is forced to `1` and
`randomseed` is omitted.

After cycles are complete, Phase Studio can pass the selected Superflip or
deblurred map back to Jana2020 for the final hand-off calculation.

## 12. Building The Wrapper

Install graphical-interface and build dependencies:

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

Keep the complete `dist/superflip/` directory together. Required Python
packages and DLL files are stored next to the executable. Copy the complete
folder contents into the Jana2020 Superflip directory.

Recommended Jana2020 deployment procedure:

1. Close Jana2020.
2. Open `C:\Jana2020\SUPERFLIP`.
3. Rename the original `superflip.exe` to `superflip_original.exe`.
4. Copy the complete contents of `dist\superflip\` into
   `C:\Jana2020\SUPERFLIP`.
5. Confirm that `EDMA.exe` is installed.
6. Start Jana2020.
7. Run a Superflip calculation normally.

## 13. Recommended User Workflow

1. Start Phase Studio.
2. Select the appropriate input mode.
3. Load the `.inflip`, HKL and reference files required by that mode.
4. Verify the reflection-data format.
5. Run `Test HKL load`.
6. Run `Analyze completeness`.
7. Check `d_min`, `d_full`, completeness and intensity statistics.
8. Configure Superflip settings.
9. Configure the next-cycle model policy and damping if required.
10. Configure EDMA options.
11. Enter the SharpED token if deblurring is required.
12. Run the pipeline.
13. Inspect the generated maps and models.
14. Compare raw, symmetrized and SharpED-processed results.
15. Select the preferred cycle or model.
16. Export the result or transfer it back to Jana2020.

Three concrete workflow examples are provided in [EXAMPLES.md](EXAMPLES.md).

## 14. Validation And Maintenance

Compile-check Python files:

```bash
python -m compileall -q phase_studio
```

Validate package metadata and installation without installing runtime
dependencies:

```bash
python -m pip install --no-deps --prefix /tmp/phase_studio_install_test .
```

Clean local generated artifacts on Linux or macOS:

```bash
rm -rf build dist phase_studio.egg-info phase_studio/__pycache__
```

Windows PowerShell:

```powershell
Remove-Item -Recurse -Force build, dist, phase_studio.egg-info
Remove-Item -Recurse -Force phase_studio\__pycache__
```

## 15. Troubleshooting

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

### SharpED Model List Cannot Be Loaded

Check `SharpED -> Server URL`, network access and the configured HTTP timeout.
The default API server is `https://jana.fzu.cz`. A model identifier may still
be entered manually.

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
- whether the correct Jana `.inflip` or CIF-compatible reference file is
  selected,
- `HKL data format`,
- whether the data are intensities or amplitudes,
- whether the reflection file contains merged or unmerged data.

Use `Test HKL load` first, then `Analyze completeness`.

### External HKL Mode Rejects A Map Reference

This is expected in the full GUI. External HKL mode requires a CIF/INS/RES
structure because Phase Studio needs cell, symmetry, composition and reference
atoms. Jana, XPLOR and CCP4 density reference files are supported in Jana
`.inflip` modes where the `.inflip` supplies the missing metadata.

## 16. Repository Layout

```text
phase_studio/                  Python package and GUI source code
phase_studio/app.py            Main Phase Studio GUI and reconstruction pipeline
phase_studio/jana_superflip.py Jana2020-compatible Superflip wrapper launcher
phase_studio/sharped_server_client.py SharpED HTTP API client
phase_studio/ui_style.py       Qt styling utilities
phase_studio/__main__.py       python -m phase_studio entry point
superflip.spec                 PyInstaller specification for the Jana wrapper
pyproject.toml                 Package metadata and optional dependencies
README.md                      Quick-start and project overview
MANUAL.md                      Detailed user and developer documentation
EXAMPLES.md                    Three practical sample workflows
documentation/                 Optional local reference material
examples/                      Optional local example datasets
```

The `documentation/` and `examples/` directories may contain local files that
are not included in version control.

## 17. Reproducibility

Phase Studio is designed to preserve:

- original input files,
- explicit workflow parameters,
- generated Superflip input files,
- intermediate maps,
- EDMA outputs,
- SharpED outputs,
- model-seeding decisions,
- and final exported results.

This is important when comparing:

- alternative charge-flipping parameters,
- different reflection-data formats,
- raw and SharpED-processed maps,
- EDMA peak-search thresholds,
- model-damping values,
- and different iterative reconstruction strategies.

## 18. External Resources

- Phase Studio releases: https://github.com/ji-ze/Phase-Studio/releases
- Superflip and EDMA: https://superflip.fzu.cz/
- SharpED, online application and API-token access: https://sharped.fzu.cz/

## 19. Notes

- Superflip and EDMA are not included in the Phase Studio Windows package.
- SharpED processing requires network access and a valid API token.
- Phase Studio can run without SharpED.
- Jana2020 is required only for Jana-specific integration and hand-off
  workflows.
- Generated Superflip, EDMA, SharpED and PyInstaller outputs should be excluded
  through `.gitignore`.
- Reference copies of older Phase Studio versions are not required for normal
  operation.

## 20. Recommended GitHub Commit

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
