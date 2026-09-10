# Building Phase Studio

This document contains source-installation, packaging, and developer-oriented build information for **Phase Studio 1.0.8**.

End users normally do not need these steps. See [README.md](README.md) and [MANUAL.md](MANUAL.md) instead.

---

## 1. Source installation

Clone the repository and create an isolated Python environment.

### Windows

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[app]"
python -m phase_studio
```

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[app]"
python -m phase_studio
```

If the repository defines a different supported Python range in `pyproject.toml`, use that as the source of truth.

---

## 2. Developer checks

### Compile check

```bash
python -m compileall -q phase_studio
```

### Tests

Run the repository test suite using the current project configuration.

For example, where pytest is configured:

```bash
python -m pytest
```

Do not claim platform-specific functionality is verified unless it has been tested on that platform.

---

## 3. Windows portable build

Windows builds are **onedir** PyInstaller distributions. Do not switch them to
one-file: production and the test suite depend on this layout.

```text
dist\PhaseStudio\
    PhaseStudio.exe
    _internal\
    JanaIntegration\          (staged copy of dist\superflip\)
        superflip.exe
        _internal\

dist\superflip\               (authoritative Jana wrapper build)
    superflip.exe
    _internal\
```

All of these are *portable*: they start on a clean, freshly installed
Windows 10/11 x64 machine with no Python, no Conda, no PySide6/Qt, and **no
separately installed Visual C++ Redistributable**.

### Build

Activate the build environment first (the script uses the `python` on `PATH`
deliberately, so it honours an activated venv/Conda environment), then:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

The script cleans only its own two output trees (`dist\PhaseStudio`,
`dist\superflip` and the matching `build\` work directories) before building,
so a new `_internal` is never overlaid on an older one. Pass `-Clean:$false`
to skip that step.

It then stages `dist\superflip\` into `dist\PhaseStudio\JanaIntegration\`,
where the frozen application looks for the wrapper it installs into Jana2020,
and finally verifies all three trees against the portable-runtime manifests.

To invoke PyInstaller directly:

```powershell
python -m PyInstaller --clean --noconfirm packaging\pyinstaller\PhaseStudio.spec
python -m PyInstaller --clean --noconfirm superflip.spec
```

A reference build environment (plain venv, PySide6 wheel from PyPI):

```powershell
uv venv --python 3.12 .venv-build
uv pip install --python .venv-build\Scripts\python.exe `
  pyinstaller==6.20.0 PySide6==6.11.1 shiboken6==6.11.1 `
  numpy matplotlib gemmi qtvscodestyle pefile
uv pip install --python .venv-build\Scripts\python.exe -e . --no-deps
.venv-build\Scripts\Activate.ps1
```

`pefile` is required by the specs' dependency discovery and by the auditors in
`packaging\tools\`; PyInstaller already depends on it.

### Build environment requirements

The build environment must be a **plain (non-Conda) virtual environment using
the PySide6 wheel from PyPI**. That wheel is self-contained: `Qt6*.dll`,
`shiboken6`, the Qt plugins and a matching Visual C++ runtime all live inside
the installed `PySide6`/`shiboken6` packages, so one internally consistent Qt
runtime can be staged.

Conda/Anaconda PySide6 keeps Qt in `<env>\Library\bin` and its plugins in
`<env>\Library\lib\qt6\plugins`, outside the Python package. The specs reject
such an environment rather than produce a bundle that only works on the build
machine. Qt DLLs must never be mixed in from Anaconda, PyQt, QGIS, Jana2020,
`PATH`, or another Phase Studio build.

### What makes the distribution portable

Handled by `packaging/pyinstaller/portable_runtime.py`, shared by both specs:

- **App-local Visual C++ runtime.** `vcruntime140.dll`, `vcruntime140_1.dll`,
  `msvcp140.dll`, `msvcp140_1.dll` and `msvcp140_2.dll` are bundled. Windows
  ships none of these; a clean PC has them only if some other product installed
  `vc_redist.x64.exe`. The required set is discovered from the PE import tables
  of the binaries the build actually collected, and each DLL is taken from an
  explicit in-environment source — never from `System32` and never from `PATH`.
- **One copy of each, at the `_internal` root.** Windows keeps one module per
  base name per process. Several copies of `msvcp140.dll` at different versions
  in different subdirectories is a real cause of
  `DLL load failed ...: The specified procedure could not be found`.
- **No app-local Universal CRT.** `ucrtbase.dll` and the `api-ms-win-*.dll`
  forwarder stubs are removed. The UCRT is a component of Windows 10/11;
  shipping a private, older copy is a portability hazard, not a fix. Some
  redistributable Python builds place one in their install root, from where
  dependency analysis will otherwise collect it.
- **DLL search isolation.** The `pyi_rth_dll_isolation.py` runtime hook calls
  `SetDefaultDllDirectories` so native DLLs resolve only from the system
  directory, the loading DLL's own directory, and this bundle's directories.
  `PATH` and the executable's own directory stop contributing, which matters
  because the Superflip wrapper is deployed inside the Jana2020 tree. Inherited
  `QT_PLUGIN_PATH`/`QTDIR` values pointing outside the bundle are dropped.

### Minimum platform

Currently supported 64-bit Windows 10/11. Qt 6 links the ICU library that ships
with Windows (`icuuc.dll`), which is present from **Windows 10 version 1903**
onwards; it is an OS component and cannot be bundled. The build reports this as
a platform requirement rather than a packaging defect. No Windows 7/8
compatibility work is included.

### Verifying a build

`packaging\build_windows.ps1` prints a portability report for each
distribution, listing only the DLLs the audited build actually requires:

```text
  Portable runtime:
    msvcp140.dll             OK
    msvcp140_1.dll           OK
    msvcp140_2.dll           OK
    vcruntime140.dll         OK
    vcruntime140_1.dll       OK
    Qt6Core.dll              OK
    Qt6Gui.dll               OK
    Qt6Widgets.dll           OK
    no app-local UCRT        OK (Windows provides the UCRT)
    no duplicate runtime     OK
```

The two auditors it drives can also be run by hand:

```powershell
# Where every native dependency resolves from
python packaging\tools\audit_dependencies.py --dist dist\PhaseStudio

# Every imported symbol against the DLL that will provide it,
# plus conflicting duplicate DLL base names
python packaging\tools\verify_imports.py dist\PhaseStudio

# The build environment itself, before packaging
python packaging\tools\audit_dependencies.py --env
```

`verify_imports.py` exists because an unsatisfied *symbol* is what produces
`The specified procedure could not be found` (Windows error 127), as opposed to
a missing DLL (error 126).

### Windows SmartScreen

PyInstaller packaging does not establish publisher trust. Unsigned executables can trigger Microsoft Defender SmartScreen and may appear as an unknown publisher.

Code signing is a separate release/distribution concern.

---

## 4. Linux one-file build

Linux builds should be produced in a controlled environment representative of the intended target systems.

In the Conda-based build environment previously used for Phase Studio, the working one-file build explicitly bundled compatible Conda OpenSSL and Expat libraries:

```bash
python -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name PhaseStudio \
  --collect-data phase_studio \
  --collect-data qtvscodestyle \
  --add-binary "$CONDA_PREFIX/lib/libssl.so.3:." \
  --add-binary "$CONDA_PREFIX/lib/libcrypto.so.3:." \
  --add-binary "$CONDA_PREFIX/lib/libexpat.so.1:." \
  phase_studio/app.py
```

Expected output:

```text
dist/PhaseStudio
```

### Why the additional libraries may be required

Conda Python can be linked against Conda-provided runtime libraries. If PyInstaller bundles a mismatched system library instead, startup errors can occur in components such as:

- `_ssl`,
- `libcrypto`,
- `pyexpat`,
- `libexpat`.

The exact packaging requirements depend on the build environment. If the project later adopts a dedicated `.spec` file or build script that handles these dependencies automatically, that repository configuration should replace the manual command above.

---

## 5. Linux desktop integration and icon

A Linux ELF executable does not use a Windows `.ico` file in the same way as a Windows PE executable, and the repository does not currently ship a standalone SVG/PNG icon asset — only the Windows multi-size `phase_studio/assets/phase_studio.ico`. The in-app logo mark itself is drawn at runtime (`create_phase_studio_logo_pixmap` in `phase_studio/app.py`) rather than loaded from an image file.

For desktop integration, extract a PNG from the `.ico` first, for example with ImageMagick:

```bash
convert phase_studio/assets/phase_studio.ico -resize 256x256 phase_studio_icon.png
```

Then install an application icon and a `.desktop` entry:

```ini
[Desktop Entry]
Type=Application
Name=Phase Studio
Exec=/opt/PhaseStudio/PhaseStudio
Icon=/opt/PhaseStudio/phase_studio_icon.png
Terminal=false
Categories=Science;Education;
```

Copy the generated icon beside the executable or install it in the appropriate system icon directory, then set `Icon` to that installed path or icon name. If the project later adds a dedicated cross-platform SVG/PNG asset, prefer that over an extracted `.ico` frame.

---

## 6. Jana2020 Superflip wrapper

The Jana2020 wrapper is built from:

```text
phase_studio/jana_superflip.py
```

Its authoritative PyInstaller specification stays at the repository root:

```text
superflip.spec
```

Always prefer that `.spec` file over reconstructing its settings manually:

```powershell
python -m PyInstaller --clean --noconfirm superflip.spec
```

or build it together with the application:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

The wrapper build is **onedir** and must stay that way:

```text
dist\superflip\
    superflip.exe
    _internal\
```

Keep the complete generated directory together — `superflip.exe` cannot run
without its `_internal\` directory.

The wrapper is packaged with the same portable-runtime rules as the main
application (see section 3), which matters especially here: the wrapper is
deployed *inside* the Jana2020 tree, so its DLL search path is isolated to
prevent it from loading Qt, ICU or Visual C++ runtime binaries belonging to
Jana2020 or to anything else on `PATH`.

---

## 7. Wrapper deployment

A typical Jana2020 deployment keeps the original Superflip executable available separately from the Phase Studio wrapper.

Example layout:

```text
C:\Jana2020\SUPERFLIP\superflip_original.exe
C:\Jana2020\SUPERFLIP\superflip.exe
C:\Jana2020\SUPERFLIP\EDMA.exe
```

Before replacing or wrapping an existing installation:

1. close Jana2020,
2. preserve the original Superflip executable,
3. copy the wrapper build according to the current project instructions,
4. confirm EDMA is available,
5. restart Jana2020,
6. test a non-production calculation first.

---

## 8. Packaging hygiene

Do not commit generated build artifacts unless the repository explicitly tracks release binaries.

Typical local artifacts include:

```text
build/
dist/
__pycache__/
*.egg-info/
```

Also exclude:

- API tokens,
- SharpED job credentials,
- personal settings,
- generated scientific run directories,
- private input datasets.

---

## 9. Release checklist

Before publishing a build:

1. confirm the application version,
2. run the test suite,
3. open the packaged executable,
4. verify external-program discovery,
5. verify HKL Validation and HKL Completeness,
6. verify a representative Superflip/EDMA workflow,
7. verify SharpED only if network credentials and server access are available,
8. verify cancellation behaviour,
9. check README, MANUAL, EXAMPLES, and BUILDING for stale version references,
10. confirm no credentials or user-specific paths are included.

For Windows releases, also verify the final signing/publisher state if code signing is part of the release process.
