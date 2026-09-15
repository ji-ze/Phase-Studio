# Microsoft Store packaging: standalone only

The Store product is the standalone Phase Studio desktop application.
The Jana2020 installer and its payload are distributed separately and must
never enter an MSIX. Scientific support for Jana2020 .inflip files is retained.

## Build

Use the Windows x64 environment described in [BUILDING.md](../BUILDING.md).
Create the ignored `packaging/msix/store_identity.json` from its example using
the exact Partner Center identity. Do not commit real identity/signing secrets.
Install the Windows 10/11 SDK (MakeAppx). Generate the existing branded assets:

```powershell
python packaging/generate_store_assets.py
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build_store_msix.ps1
```

The script invokes `build_windows.ps1 -Target Standalone`, audits the portable
runtime, verifies that the frozen archive has no installer UI, refuses any
JanaIntegration payload, and stages only `dist/PhaseStudio/` plus Store assets.
It renders `AppxManifest.xml` and invokes MakeAppx. Existing installer/wrapper
outputs are independent and are not cleaned or packaged by this command.

Default outputs:

- `build/store/layout/PhaseStudio/PhaseStudio.exe` and `_internal/`
- `build/store/layout/AppxManifest.xml` and `Assets/`
- `dist/store/PhaseStudio-<version>-x64.msix`
- `dist/store/manifest/AppxManifest.xml`

The manifest version is canonical `VERSION + ".0"` (currently 1.0.9.0).
An explicit `-Version` must agree; it cannot override the application version.
No Jana wrapper signing parameters or integration payload markers are used by
this Store build.

## Signing and acceptance

Microsoft signs Store submissions. For local sideload testing, use
`packaging/sign_test_msix.ps1` or the build script's `-TestCertificatePath` and
`-TestCertificatePassword` parameters. Supply certificate passwords as
SecureString; do not put credentials in scripts or logs. Sign production
installer/wrapper binaries separately before distributing them outside Store;
that signing is not part of the standalone MSIX build.

Keep the portable ONEDIR layout and existing DLL-isolation hook. All non-Windows
native dependencies must be bundled; the OS provides UCRT and (on Windows 10
1903+) ICU. Validate on a clean supported Windows installation without Python,
Conda, Qt, or a separately installed Visual C++ Redistributable. Run Store
certification/installation checks with the real Partner Center identity.
