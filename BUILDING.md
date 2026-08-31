# Building Phase Studio

This document contains source-installation, packaging, and developer-oriented build information for **Phase Studio 1.0.7**.

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

## 3. Windows one-file build

The project has been packaged with PyInstaller as a single GUI executable.

From the repository root in an environment containing the application dependencies:

```powershell
python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name PhaseStudio `
  --icon phase_studio\assets\phase_studio.ico `
  --collect-data phase_studio `
  --collect-all qtvscodestyle `
  phase_studio\app.py
```

Expected output:

```text
dist\PhaseStudio.exe
```

Before publishing a release, test the executable on a machine/environment that does not rely on the active development environment.

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

A Linux ELF executable does not use a Windows `.ico` file in the same way as a Windows PE executable. Use one of the square cross-platform assets included in the repository:

```text
phase_studio/assets/phase_studio_icon.svg
phase_studio/assets/phase_studio_icon.png
```

The full-width brand mark is also available as `phase_studio_logo.svg` and `phase_studio_logo.png`.

For desktop integration, install an application icon and a `.desktop` entry.

Example:

```ini
[Desktop Entry]
Type=Application
Name=Phase Studio
Exec=/opt/PhaseStudio/PhaseStudio
Icon=/opt/PhaseStudio/phase_studio_icon.png
Terminal=false
Categories=Science;Education;
```

Copy the selected icon asset beside the executable or install it in the appropriate system icon directory, then set `Icon` to that installed path or icon name.

---

## 6. Jana2020 Superflip wrapper

The Jana2020 wrapper is built from:

```text
phase_studio/jana_superflip.py
```

The repository may provide a dedicated PyInstaller specification such as:

```text
superflip.spec
```

When present, prefer the repository `.spec` file over reconstructing its settings manually:

```bash
python -m PyInstaller --clean --noconfirm superflip.spec
```

A typical onedir wrapper build produces:

```text
dist/superflip/
```

Keep the complete generated directory together unless the specification explicitly produces a one-file build.

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
