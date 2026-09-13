# Split Windows distribution

Phase Studio 1.0.9 temporarily uses the original coherent SharpED API at
`https://jana.fzu.cz`: model discovery, upload, polling, and download all derive
from that single base URL. This restores the last known-working client behavior
while server migration is completed. TODO: after SharpED server unification,
migrate Phase Studio to the final `sharped.fzu.cz` API in a separate task.

## Git audit

The initial working tree was clean. Remote branches and tags were fetched.
Local/remote main pointed to `5a6427c`, also the existing `v1.0.8` tag.
The completed branch contained 74 commits not in main, including the recent
GUI, Wizard, Jana handoff, SharpED catalog/API, map scaling, console, wheel,
legend, preflight, and portable-runtime fixes.

Those commits were merged without conflicts into local main at `e62c200`.
All fetched remote branch tips are ancestors of that integrated main, and no
completed branch commits remain outside it. The existing `v1.0.8` tag was not
moved or recreated. Development continued on
`release/1.0.9-split-distribution`; only that branch changes the canonical
version to 1.0.9. No 1.0.9 release tag was created.

## Architecture and artifacts

- `phase_studio.standalone`: standalone entry point and version command.
- `phase_studio.jana_installer`: the former integration dialog, extracted into
  a dedicated application; no scientific GUI import or launch.
- `phase_studio.ui_branding`: existing Qt branding/geometry helpers, moved
  unchanged and re-exported by the shared application for existing consumers.
- `phase_studio.jana_integration`: existing filesystem integration operations,
  with explicit ownership/hash conflict checks and regression-tested rollback.
- `phase_studio.app`: shared scientific GUI without installation management;
  wrapper-launched result selection and Send to Jana2020 remain available.
- Root `superflip.spec`: same authoritative ONEDIR wrapper, now also stamping
  its Windows EXE version from the canonical version source.
- Shared packaging spec: selects the standalone or installer entry point and
  retains the existing portable Qt/VC++ runtime staging and isolation hook.
- Store script: builds/stages only standalone, rejecting installation payloads.

See [BUILDING.md](../BUILDING.md) for exact commands and output layouts.
The normal outputs are `dist/PhaseStudio`, `dist/PhaseStudioJanaInstaller`, and
`dist/superflip`. The installer carries a complete, byte-identical copy of the
authoritative wrapper in `JanaIntegration`; this is the scientific code needed
after installation, separate from the installer's own UI runtime.

During this task an older `dist/PhaseStudio/PhaseStudio.exe` process remained
running with no visible window. It was not force-terminated or overwritten.
The tested standalone artifact was therefore built in
`dist/1.0.9/PhaseStudio` using `-DistRoot`. Installer and wrapper artifacts use
their normal output locations. All are complete ONEDIR folders.

## Verification

- Complete current suite: 768 plain checks plus 23 unittest cases (7 restored
  SharpED API contract, 16 split-distribution), across 14 scripts, all passing.
- Frozen module/archive checks: standalone, installer, wrapper all pass;
  every staged wrapper file matches the authoritative build.
- Native dependency and imported-symbol audits pass for standalone, installer,
  wrapper, and the staged wrapper copy: zero unresolved/external non-Windows
  dependencies, zero blocking symbol problems, no conflicting duplicate DLLs.
- EXE resources and embedded runtime versions derive from 1.0.9. MSIX version
  derives as 1.0.9.0; conflicting explicit version overrides are rejected.
- Installer transaction tests use temporary mock Jana directories, never the
  real installation. They exercise the actual UI actions and filesystem code.
- Scientific functions match the integrated baseline, and all scientific/map
  scaling golden checks pass. No scientific request, calculation, output,
  ranking, feedback, or handoff algorithm was changed.

## Remaining manual acceptance

Run both products on a clean supported Windows PC without Python/Qt/VC++
redistributables installed separately. Exercise install/update/repair/remove
on a real Jana2020 installation, including all Wizard workflows and Full
configuration/Send to Jana2020. Confirm the old running build is closed before
rebuilding the default standalone output directory.

An actual MSIX was not produced: the local Store identity and Windows SDK
MakeAppx tooling were unavailable. Build, install, and certify it with the real
Partner Center identity; verify standalone-only contents. Windows EXEs are
unsigned local builds, so production signing and clean-machine trust checks
remain part of distribution acceptance.
