# Phase Studio for Jana2020

Phase Studio is a Qt-based crystallographic workflow application for Jana2020
users. It combines Superflip charge flipping, optional SharpED density-map
deblurring, EDMA peak extraction, reflection-data diagnostics and Jana2020
hand-off tools in one reproducible Python project.

The application is intended for crystallographers working with electron-density
or electrostatic-potential maps, Jana `.inflip` inputs, external HKL/CIF data
and iterative model-seeded Superflip workflows.

## Key Features

- Direct use of Jana2020 `.inflip` files, including embedded `fbegin/endf`
  reflection blocks, cell parameters, space group and composition.
- External HKL and reference CIF/XPLOR override modes.
- Superflip input generation with explicit control of `dataformat`,
  `dataitemwidths`, `referencefile`, `modelfile`, output formats and common
  charge-flipping parameters.
- Iterative cycling with next-cycle model sources:
  - raw Superflip XPLOR map,
  - SharpED-deblurred XPLOR map,
  - EDMA CIF after deblurred-map peak extraction,
  - no next-cycle model.
- Inverse XPLOR damping input: `0.5` corresponds to the previous damping factor
  `2.0`, `0.25` corresponds to `4.0`, and `1.0` means no damping.
- HKL load testing with parsed `h`, `k`, `l`, observed value, sigma, phase,
  d-spacing and `sin(theta)/lambda`.
- Reflection completeness and intensity statistics:
  - shell completeness versus `sin(theta)/lambda`,
  - mean `I/sigma` per shell,
  - `I/sigma` frequency histogram,
  - `d_min` and `d_full` markers.
- PyInstaller wrapper for replacing Jana2020 `superflip.exe` while preserving
  the original Superflip executable as `superflip_original.exe`.

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
   - `Jana .inflip with external HKL/CIF overrides`,
   - `External HKL + reference CIF`.
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
