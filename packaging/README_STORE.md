# Phase Studio: Windows / Microsoft Store packaging

This directory contains the standalone Windows build and Microsoft Store
(MSIX) packaging pipeline for Phase Studio. It is separate from the
scientific application source under `phase_studio/`.

## Layout

```
packaging/
    pyinstaller/
        PhaseStudio.spec         PhaseStudio ONEDIR build (Store staging)
    msix/
        AppxManifest.template.xml
        store_identity.example.json
        Assets/                  MSIX visual assets (generate; see below)
    build_windows.ps1            developer/testing build (no MSIX)
    build_store_msix.ps1         Microsoft Store MSIX pipeline
    sign_test_msix.ps1           optional local test-signing of an MSIX
    generate_store_assets.py     renders msix/Assets/*.png from the app's own vector logo
    README_STORE.md              this file
```

The repository root also keeps its own `PhaseStudio.spec` (ONEFILE, quick ad
hoc developer distribution) and `superflip.spec` (ONEDIR). `superflip.spec`
is not just "unrelated and left as-is" -- it is the **authoritative,
already-verified-against-a-real-Jana2020-installation** Jana2020 wrapper
build, and both `build_windows.ps1` and `build_store_msix.ps1` build the Jana
wrapper by invoking it directly, with the exact command
`python -m PyInstaller --clean --noconfirm superflip.spec` run from the
repository root. Neither packaging script maintains a second, separately
frozen Jana wrapper spec.

## Two applications, one package

- **PhaseStudio.exe** -- the actual Store application entry point. Runs
  standalone; Jana2020 is entirely optional.
- **superflip.exe** (repository root `superflip.spec`, ONEDIR) -- a separate,
  dedicated PyInstaller build of `phase_studio/jana_superflip.py`. The
  authoritative build output is `dist\superflip\`. `build_windows.ps1` then
  stages a complete copy of it into `dist\PhaseStudio\JanaIntegration\` --
  directly beside `PhaseStudio.exe` -- as a plain post-build file copy, never
  by giving PyInstaller a different spec or output name. `build_store_msix.ps1`
  carries that same already-staged `dist\PhaseStudio\` directory (including
  `JanaIntegration\`) into the MSIX layout unchanged, so the installed MSIX
  has the identical `PhaseStudio\JanaIntegration\` layout. It is bundled
  *inside* the package as an application resource, but it is never the
  package's entry point and Windows never launches it directly. Phase Studio
  itself copies it out to a user-selected `Jana2020\SUPERFLIP` folder only
  when the user explicitly runs "Install to Jana2020" -- see
  `phase_studio/jana_integration.py`.

Do not copy `PhaseStudio.exe` and rename it `superflip.exe`; always build and
ship the dedicated Jana wrapper.

## Developer build

```powershell
powershell -File packaging\build_windows.ps1
```

Produces `dist\PhaseStudio\` (with `JanaIntegration\` staged inside it) and
`dist\superflip\` (both ONEDIR, the latter via the root `superflip.spec`).
This is the fastest way to test changes locally, including the Jana2020
integration dialog itself, and running `dist\PhaseStudio\PhaseStudio.exe`
directly needs no further copying -- the Jana wrapper is already staged
beside it.

## Store MSIX build

```powershell
powershell -File packaging\build_store_msix.ps1
```

1. Cleans `build\store\` and `dist\store\`.
2. Builds `PhaseStudio` and the Jana2020 wrapper by running
   `build_windows.ps1` (same known-working build, no separate Jana spec;
   this also stages `JanaIntegration\` inside `dist\PhaseStudio\`).
3. Copies the already-staged `dist\PhaseStudio\` (with `JanaIntegration\`)
   -> layout `PhaseStudio\` under `build\store\layout\`.
4. Generates `AppxManifest.xml` from the template, the local
   `packaging\msix\store_identity.json`, and the single version source
   (`phase_studio\version.py`).
5. Validates the required visual assets exist.
6. Optionally Authenticode-signs `PhaseStudio\JanaIntegration\superflip.exe`
   (see below).
7. Calls `MakeAppx.exe pack` (auto-located under the installed Windows SDK).
8. Produces `dist\store\PhaseStudio-<version>-x64.msix`.

### Store identity (Partner Center)

`AppxManifest.template.xml` never hard-codes a Package Identity Name,
Publisher, or PublisherDisplayName -- those values come from Microsoft
Partner Center once the app is registered there. Create your own, local,
**not committed** identity file:

```powershell
Copy-Item packaging\msix\store_identity.example.json packaging\msix\store_identity.json
# then edit packaging\msix\store_identity.json with the real Partner Center values
```

### Version

One source of truth: `phase_studio/version.py` (`VERSION = "1.0.8"`). The
build script maps this to the MSIX four-part version automatically
(`1.0.8` -> `1.0.8.0`). Do not edit the MSIX version independently of it --
in particular, `packaging/msix/store_identity.json` deliberately has no
version field of its own; only Package Identity Name/Publisher come from
there.
`phase_studio/jana_integration.py`'s installed-integration marker
(`phase_studio_integration.json`) also reads this same source, so a Store
update and its bundled Jana integration payload always agree on version.

### Store assets

```powershell
python packaging\generate_store_assets.py
```

Generates the required MSIX PNG sizes directly from Phase Studio's own
**vector** brand mark (`create_phase_studio_logo_pixmap`/
`create_phase_studio_app_icon` in `phase_studio/app.py`, drawn procedurally
with QPainter, not a fixed-resolution file) into `packaging\msix\Assets\`,
rendering each one fresh at its own exact target size:

- `StoreLogo.png` (50x50)
- `Square44x44Logo.png` (44x44)
- `Square71x71Logo.png` (71x71)
- `Square150x150Logo.png` (150x150)
- `Square310x310Logo.png` (310x310)
- `Wide310x150Logo.png` (310x150)
- `SplashScreen.png` (620x300)

Deliberately not sourced from `phase_studio/assets/phase_studio.ico`: that
file is a small, fixed-resolution taskbar icon, and upscaling it would look
soft at Store tile sizes (particularly the 310x310 and splash assets) even
though the underlying mark is the same navy/blue Phase Studio identity
either way. `build_store_msix.ps1` fails with a clear error listing exactly
which assets are missing rather than silently packaging without them; it
does not generate them itself.

## Signing

### Store submission (recommended path)

Run `build_store_msix.ps1` with no signing parameters. The resulting MSIX is
**unsigned** -- this is correct. Microsoft Store re-signs the package with
its own production certificate after certification; a CA-trusted
code-signing certificate is never required from the developer for Store
distribution.

### Local/sideloaded MSIX

A directly installed (non-Store) MSIX requires a certificate the target
machine trusts. Use `sign_test_msix.ps1` (or pass
`-TestCertificatePath`/`-TestCertificatePassword` to `build_store_msix.ps1`)
with a local development certificate. Never commit a `.pfx`, private key, or
password to this repository.

### The Jana2020 wrapper is signed separately

`PhaseStudio\JanaIntegration\superflip.exe` is later **copied out of the
installed MSIX package** by Phase Studio itself, into a `Jana2020\SUPERFLIP`
folder. At that
point it is a plain, separately deployed `.exe` from Windows' perspective --
the MSIX package signature does not travel with it. `build_store_msix.ps1`
therefore supports an independent, optional Authenticode signing step for
this one file (`-JanaSigningCertificate`/`-JanaSigningPassword`,
`-TimestampUrl`). If no certificate is configured, the build still succeeds
and prints:

```
Jana integration wrapper is unsigned.
```

The Jana2020 integration dialog in Phase Studio also shows this file's
Authenticode status before installation, to help diagnose Smart App
Control/WDAC environments -- it does not block installation solely because
the wrapper is unsigned (Windows policy is the actual gate).

## Store certification / compatibility notes

- Application startup never requires Jana2020, Superflip, or EDMA to be
  present, never writes outside its own user-data locations on its own, and
  never displays a fatal error merely because Jana2020 is absent -- Jana2020
  integration is entirely optional and user-initiated.
- Phase Studio never modifies its own installed (read-only) MSIX package
  directory. All Jana2020 installation writes go to the user-selected
  `Jana2020\SUPERFLIP` folder only.
- No `allowElevation` or other restricted capability is declared. If the
  selected Jana2020 folder is not writable by the current user, Phase Studio
  reports a plain permissions error rather than attempting to self-elevate.
- Run the Windows App Certification Kit (WACK) against the packaged
  application before submission; document any remaining findings rather
  than suppressing them.

## What this pipeline does *not* do

This pipeline prepares and validates the packaging artifacts; it does not by
itself:

- register an app identity in Partner Center,
- purchase/manage a production code-signing certificate,
- submit the package to the Store,
- run on a machine without the Windows 10/11 SDK (`MakeAppx.exe`,
  `SignTool.exe`) installed.
