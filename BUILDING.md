# Building Phase Studio

This document contains source-installation, packaging, and developer-oriented build information for the version in `phase_studio/version.py`.

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

Run every plain Python regression script (no pytest required):

```powershell
Get-ChildItem tests/test_*.py | ForEach-Object {
    python $_.FullName
    if ($LASTEXITCODE -ne 0) { throw "Test failed: $($_.Name)" }
}
```

---

## 3. Two independent Windows products

Use a plain CPython x64 virtual environment with the PyPI PySide6 wheel,
not a Conda Qt installation. The interpreter must include its matching Tcl/Tk
runtime and library scripts; PyInstaller uses them for the early ONEFILE launch
splash shown while the archive is extracted. Install the build dependencies in
that environment:

```powershell
python -m pip install -e ".[dev]"
```

Activate it, then run from the repository root:

```powershell
# Both products, including the authoritative Jana wrapper
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build_windows.ps1 -Target All
# Standalone only; does not build or stage the Jana installer payload
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build_windows.ps1 -Target Standalone
# Installer and its complete authoritative wrapper payload
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build_windows.ps1 -Target JanaInstaller
# Wrapper alone
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build_windows.ps1 -Target JanaWrapper
```

Outputs:

```text
dist/release/PhaseStudio-1.0.10-x64.exe
dist/release/PhaseStudio-Jana2020-Installer-1.0.10-x64.exe
dist/superflip/superflip.exe            internal authoritative wrapper build
dist/superflip/_internal/               internal wrapper runtime
```

`dist/release` is the complete public release and must contain exactly the two
EXEs above. Both are PyInstaller ONEFILE applications and can be copied or
downloaded independently. The installer embeds the complete `dist/superflip`
tree and uses PyInstaller's private extraction directory at runtime; it needs no
adjacent payload. Standalone contains no installation-management UI or wrapper.
`dist/superflip` remains an internal build input and is not a third download.

`packaging/pyinstaller/PhaseStudio.spec` implements the two direct ONEFILE profiles.
`PhaseStudioJanaInstaller.spec` selects the installer entry point; the root
`PhaseStudio.spec` forwards to the standalone spec. `PhaseStudioStore.spec`
selects a standalone-only ONEDIR profile for MSIX staging. The root
`superflip.spec` remains the authoritative ONEDIR wrapper specification and is
built with `python -m PyInstaller --clean --noconfirm superflip.spec`.

The shared portable-runtime helper and DLL-isolation hook are used by every
profile. The build inspects each frozen archive, enforces product boundaries,
and compares every embedded Jana wrapper file byte-for-byte with the
authoritative ONEDIR build.

Close a release executable before rebuilding it. `-DistRoot` remains restricted
to a subdirectory of the repository's `dist`; builds never terminate processes.

Version strings in windows, Wizard, installer, integration marker, Python
metadata and Windows EXE resources derive from `phase_studio/version.py`.
Store packaging derives its fourth `.0` component from the same source.

For Microsoft Store packaging, see [packaging/README_STORE.md](packaging/README_STORE.md).

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
