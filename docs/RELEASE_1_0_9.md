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
  wrapper-launched profile-aware Result Selection and Pass to Jana2020 remain available.
- `phase_studio.map_quality`: immutable validation contexts, full-cell map
  diagnostics, four validation profiles, and source-neutral lexicographic
  recommendation for Superflip and SharpED candidates.
- Root `superflip.spec`: same authoritative ONEDIR wrapper, now also stamping
  its Windows EXE version from the canonical version source.
- Shared packaging spec: selects the standalone or installer entry point and
  retains the existing portable Qt/VC++ runtime staging and isolation hook.
- Store script: builds/stages only standalone, rejecting installation payloads.

See [BUILDING.md](../BUILDING.md) for exact commands and output layouts.
The public release output is exactly:

- `dist/release/PhaseStudio-1.0.9-x64.exe`
- `dist/release/PhaseStudio-Jana2020-Installer-1.0.9-x64.exe`

Both downloads are PyInstaller ONEFILE executables. The authoritative Jana
wrapper remains ONEDIR at `dist/superflip` as an internal build input. Its
complete file tree is embedded byte-for-byte in the installer and extracted by
the PyInstaller bootloader to private temporary storage before the existing
transactional integration engine stages it into Jana2020.

## Verification

The workflow-preflight audit traced commit `57567f2` through the SharpED API
rollback and the standalone/Jana distribution split. Its pure checks and the
full-window call site survived; they were neither reverted nor overwritten.
The original commit explicitly left remediation dialogs unimplemented, and
the lightweight Wizard's single-pass actions had never called the shared
preflight. Version 1.0.9 now connects every execution route and supplies the
three dedicated repair dialogs. The same focused pass removed the split-host
bridge accidentally reintroduced by `a83e6d1` and restored `396270c`'s
single-host SharpED client; it does not define a new endpoint contract.

| Requirement | Check exists | Called before execution | Dedicated repair UI | Full GUI | Wizard |
| --- | --- | --- | --- | --- | --- |
| Superflip | yes | yes | yes | pass | pass |
| EDMA | yes | yes, when an EDMA stage is enabled | yes | pass | pass when required by the full-window configuration |
| SharpED API | yes | yes, for SharpED workflows | yes | pass | pass |

- Superflip auto-detection prefers `superflip_original.exe`, rejects a marked
  Phase Studio `superflip.exe` wrapper, and accepts the fallback
  `superflip.exe` only when wrapper ownership is absent. EDMA detection is
  read-only. Both detected paths synchronize the current configuration,
  Advanced -> Setup, and QSettings.
- SharpED preflight establishes only token presence, current server
  reachability, and a well-formed public response. It does not label the token
  valid. Only explicit HTTP 401/403 evidence is classified as authentication
  rejection.
- Click-driven Qt tests cover missing Superflip, EDMA and SharpED requirements,
  silent success, Browse and Set-token repair/resume, Skip blocking, all three
  Wizard run buttons, and the non-running Open full configuration action.

- All 17 Python regression scripts pass (685 checks). This includes synthetic
  periodic Fourier maps, scale/origin invariance, triplet phase statistics,
  frozen holdout isolation, all four profile orders, both selector contexts,
  manual override state, real-file export, report/CSV contents, and existing
  scientific baselines.
- Local offscreen acceptance rendered the three-metric main panel and shared
  result selector at their target sizes. Candidate columns, recommendation
  marking, splitter balance, structure preview, and context-specific actions
  remained within the intended geometry; widget-level tests verified their
  exact labels and behavior.
- The automated Python suite covers the historical single-host API contract, frozen-product
  boundaries, private payload resolution, transactional install/update/repair/
  remove and rollback, UI text/state behavior, and the preserved scientific
  baselines.
- Frozen archive checks verify the standalone, installer, and wrapper module
  boundaries and compare every embedded wrapper file with the authoritative
  build.
- EXE resources and embedded runtime versions derive from 1.0.9. MSIX version
  derives as 1.0.9.0; conflicting explicit version overrides are rejected.
- Installer transaction tests use temporary mock Jana directories, never the
  real installation. They exercise the actual UI actions and filesystem code.
- Existing scientific functions match the integrated baseline except the
  explicitly added map-quality metrics and holdout exclusion guard. The map
  scaling and scientific golden checks pass.
- Real-executable local acceptance used the installed Superflip and EDMA on a
  temporary 728-reflection P1 crystal. All four profiles produced their three
  required finite metrics; the two holdout profiles shared one frozen,
  orbit-safe 36-reflection free set. The run produced and assessed actual
  XPLOR maps and an EDMA CIF rather than test doubles.
- The standalone, Jana wrapper, and Jana installer were rebuilt locally. All
  dependency, frozen-import, distribution-boundary, payload, and 1.0.9 version
  smoke checks pass.

## Remaining manual acceptance

Run both public EXEs on a clean supported Windows PC without Python/Qt/VC++
installed separately. Exercise install/update/repair/remove on a real Jana2020
installation, including all Wizard workflows and Full configuration/Pass to
Jana2020. Exercise every available assessment profile, manual override, and
standalone Save map and model. Inspect the GUI at Windows 100%, 125%, and 150%
display scaling.

An actual MSIX was not produced: the local Store identity and Windows SDK
MakeAppx tooling were unavailable. Build, install, and certify it with the real
Partner Center identity; verify standalone-only contents. Windows EXEs are
unsigned local builds, so production signing and clean-machine trust checks
remain part of distribution acceptance.
