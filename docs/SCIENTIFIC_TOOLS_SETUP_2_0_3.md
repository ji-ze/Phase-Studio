# Unified scientific tools setup — 2.0.3

The standing instruction that subsequent UI prompts target **2.0.3** supersedes the attachment's older 2.0.2 version text. Existing dirty-tree work is preserved. This isolated task does not build, commit, push, tag or publish, or change LICENSE, CITATION.cff or release metadata.

## A. Implementation

`scientific_tools_setup.py` provides one reusable local-tools dialog, distinct from SharpED account onboarding. It shows only required local tools; two missing tools are repaired in one combined dialog. Single-tool manual verification preserves the previous automatic continuation after a successful selection. Combined setup enables Continue only after both required paths are verified. The caller persists the successful paths and rechecks the original configuration before starting its existing workflow. Back returns without silently skipping a dependency or changing workflows.

The requested Superflip and EDMA titles, subtitles and scientific descriptions are used verbatim. The combined title is **Set up scientific tools**. The dialog uses the shared brand header and existing settings icon, ordinary Segoe UI text, white/navy/cyan styling, a fixed header/footer, and a scrollable body for short screens. Science Gothic is confined to the existing product wordmarks. Local setup has no access-key/password controls and performs no SharpED requests.

Discovery precedence:

1. Valid explicit configuration.
2. Active Jana2020 installation when launched through Jana.
3. Validated persistent Phase Studio managed installation.
4. Supported known installation (`C:\Jana2020\SUPERFLIP`).
5. Validated PATH result.

An unrelated `superflip_original.exe` is no longer discovered automatically. The original-name escape remains available beside an actual launcher whose integration marker and payload hash verify its identity. Explicit scientific paths remain configurable.

Bare legacy program-name settings are treated as PATH discovery, not as explicit installed paths that outrank the active Jana installation. This precedence edge has its own regression test.

Validation checks regular-file status, bounded file size, Windows PE application format and architecture, program-specific embedded identity, imported runtime dependencies, and an actual bounded launch without scientific input. Successful results are cached by resolved path, size, timestamps, SHA-256 and runtime-file identities; changed/deleted files and changed dependencies are rechecked. Filename and `MZ` alone are insufficient. This is **functional program identification, not cryptographic publisher authentication**.

Superflip's `-V` is used only when the inspected build contains its recognized version-switch interface; older unidentified interfaces are not blindly given `--help` or `--version`. Historical EDMA is checked with no arguments and closed stdin: its recognized input prompt plus expected EOF exit identifies the working program without supplying a map/input. All probes use a private temporary working directory, a five-second timeout, safe argument arrays, no visible console, and Windows loader-error suppression. No long calculation is started. Program versions are reported only where the probe actually provides one; no EDMA version is invented.

Manual selection and installation run through Qt thread-pool tasks. Invalid files remain unsaved, with missing, incompatible, runtime and launch failures distinguished. Back cancels setup work safely and ignores late callbacks. The original Wizard fields remain owned by the Wizard; real-widget tests compare every input control across browser/Back and assert no Professional/Autosolve launch. Existing full-GUI tests verify successful path repair resumes the requested worker and persists the path.

## B. Official distributions and licences

The [official project page](https://superflip.fzu.cz/) was fetched successfully over certificate-verified HTTPS. It confirms these existing Windows archive references:

- [Superflip Windows archive](https://superflip.fzu.cz/download/superflip_win.zip).
- [EDMA Windows archive](https://superflip.fzu.cz/download/EDMA_win.zip).

The program-specific licence actions now open the exact links published by that page:

- [Superflip licence](https://superflip.fzu.cz/download/license_superflip.txt).
- [EDMA licence](https://superflip.fzu.cz/download/license_EDMA.txt).

Both official licence texts were read. They permit noncommercial use subject to their conditions, require copyright-holder permission for redistribution, require scientific acknowledgement, and direct commercial users to the copyright holders. They are independent of Phase Studio's MIT licence. No new redistribution permission or automated-download approval is inferred from their public availability.

**Production automatic setup is disabled.** The approved-distribution registry is empty: no independent trusted package digest/signature and no release-reviewed automated-download permission record were established. The UI offers one recommended **Official download page** action plus **Locate existing Superflip/EDMA** and separate **View licence information** actions. No guessed archive is downloaded or launched, and no third-party executable is bundled.

The retained installer backend is available only with an internal reviewed policy containing HTTPS source, independent SHA-256, licence and permission references. Tests inject explicit mock policies; these are not production approvals. The backend streams a size-bounded download, verifies the approved digest before extraction/launch, rejects unsafe archive paths/links and ambiguous executable selection, retains companions, validates the staged program, and publishes the whole installation by directory rename. It refuses destinations outside its persistent managed root and refuses to overwrite any existing installation. Cancellation/errors remove staging and never activate a partial package.

Stages are Preparing download, Downloading, Verifying downloaded files, Setting up the program, Checking compatibility and Ready to continue. Progress is indeterminate because this implementation does not have a trustworthy percentage. No simulated percentage is shown. Error details are sanitised in the diagnostic logger; ordinary UI messages contain no tracebacks. Native installation/network paths are exercised with mocks in the routine suite, not real public executable downloads.

## C. Windows and distribution paths

Jana discovery derives `<actual Jana root>\SUPERFLIP` using the existing installation-root helper, including launches from `<jana>\SharpED` and its `_internal` directory. It never appends SUPERFLIP under SharpED. Existing test overrides remain supported. No Jana executable or marker is rewritten during discovery.

Standalone managed location:

`%LOCALAPPDATA%\FZU\PhaseStudio\scientific_tools\<program>`

It is independent of cwd, `sys._MEIPASS` and PyInstaller extraction directories. Automatic setup, if subsequently approved, remains per-user and needs no administrator permissions. Browser/manual selection do not reset workflow fields. SharpED authentication and API endpoints remain unchanged.

The setup is owned and modal, and uses the established foreground activation helper; no permanent Always on Top is used. Source and simulated ONEFILE/ONEDIR path contracts are tested. **No new frozen binary was built or tested**; existing 2.0.2 packages remain untouched. Source integration is ready for inclusion in the eventual 2.0.3 standalone and Jana ONEDIR builds, subject to native packaged acceptance below.

Real installed programs were checked read-only:

| Program | Path | Result | Version |
| --- | --- | --- | --- |
| Superflip | `C:\Jana2020\SUPERFLIP\superflip.exe` | Verified | `09/21/20 10:33` |
| EDMA | `C:\Jana2020\SUPERFLIP\EDMA.exe` | Verified | No reliable version interface in this build |

SHA-256 before and after those probes matched:

- Superflip: `2933a0c5245f4addc6365f26e5e4ca73a113e875a5901587db2bdd201a80bf3e`.
- EDMA: `ea648b36d048102bee3bd56ab02069b054cebc3ec287f4762fe17cb989dbf59b`.
- `ochlor.inflip`: `21bce8a7b9641f9a484033ab295ca80be832404a892f47286f8e58a9c259af47`.
- Existing scientific SharpED map: `ce7cdadc67e9a7067216acc47da9b421ee191680c5ffd945047b190357cdc620`.

Evidence: `build/scientific-tools-real-validation.json`. No new scientific job or Jana import was run; the `ochlor` files are read-only regression inputs. `2int3total` was not used.

## D. Regression and screenshots

Focused checks: **56 new setup/discovery/installer/UI tests**, existing requirements **58**, full-GUI/Wizard preflight **30**, and requirement DPI geometry **6** — **150 checks** total. Synthetic PE fixtures and non-executing probe mocks replace the older MZ-only test files; production validation is not loosened for tests.

Final complete direct suite: **56 scripts, 2,356 checks**, all processes exited zero. The suite includes scientific core goldens **46**, displacement export **44**, EDMA defaults **17**, SharpED API contract **15**, map scaling **83**, tiling **33**, Jana completion **192**, Result Selection/viewer **72**, workflow-state **141**, model/default **44**, packaging-profile tests and all existing UI tests. Scientific golden expectations and scientific writers were not changed. Normal 0.50σ EDMA defaults, one-cycle PEAK A / multi-cycle SEED policy, Map Feedback mathematics, ranking, coordinates, Uiso limits and Jana output protocols remain intact.

Final complete unittest discovery: **185 passed**, 194.557 s. Final complete pytest discovery: **185 passed and 5 subtests passed**, 196.86 s, with the cache provider disabled. Both final processes exited zero. The read-only real-project checks were enabled in both suites. Compile checks and `git diff --check` passed.

Logs:

- `build/direct-test-summary-scientific-tools-2.0.3.txt`.
- `build/test-logs-scientific-tools-2.0.3/`.
- `build/tools-focused.log`, `build/tools-preflight.log`, `build/tools-scaling.log`.
- `build/tools-full-direct-final.log`, `build/tools-unittest-complete.log`, `build/tools-pytest-complete.log`.

Actual Qt screenshots: **39 PNGs** with per-image JSON metadata in [`screenshots/2.0.3-scientific-tools`](screenshots/2.0.3-scientific-tools): **3 previous-layout captures** and **36 new captures**, twelve per scale at 100%, 125% and 150%. Each scale includes EDMA missing, Superflip missing, both missing, each installed/verified state, manual-only setup, approved-automatic fixture, actual threaded mock download progress, mock installation completion, failed verification, and reduced-height top/bottom views. Installed-state images use explicit status fixtures; actual installed executables are independently verified above. Automatic-install captures are explicitly labelled as mock policy/download/install fixtures in their metadata.

Captures assert fixed-footer bounds, no horizontal scroll, modal ownership and no Always on Top. Representative combined, progress, failure and reduced-height screenshots were inspected visually. Separate DPI tests check actual available-screen/frame bounds and that all buttons are reachable through scrolling. The body intentionally scrolls on short screens; the footer remains visible. This is source/offscreen software-DPI evidence, not a claim of native workstation acceptance.

## E. Remaining acceptance

- No production automatic installer can be enabled until independently trusted integrity information and reviewed permission are available. Verified official manual-download and locate actions are available now.
- Historical builds without recognizable safe identity/interfaces fail verification rather than being launched for a calculation during setup. The installed Superflip/EDMA pair above passes; compatibility with every historical/compiler-specific build is not claimed.
- Native Windows 100/125/150% desktop, browser round trip, foreground behavior over real Jana2020, and newly frozen standalone/ONEDIR packages still need manual acceptance. No frozen 2.0.3 package or fresh authenticated SharpED/Jana scientific workflow was tested in this task.
- There was no change to scientific outputs, Jana handoff semantics, credentials, release licence files or existing packaging profiles.

The final real-program/project hash check matched the values above. Existing frozen 2.0.2 artifacts also retain their previously recorded hashes: standalone `139886f97ccc743ab360fd48a0d36ae43697523763d660d7c567afa6c6dee55e`, Jana ZIP `5fcc08fb6330b43833da022a3377cb89ac8eb45b259d40cfc4ef8a8b2712dbaf`. HEAD remains `65ce510b71d7b33d33f4237ea3470275316e2a5b`; no commit or publication occurred.
