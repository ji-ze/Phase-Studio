# Phase Studio 2.0.3 local preview build

Built on 14 October 2026 from the current uncommitted `development/2.0.3`
working tree. No commit, push, tag, installation into Jana or publication was
performed. Existing `dist/release` 2.0.2 files were hash-checked and preserved.

## Artifacts

| Artifact | Location | Bytes |
|---|---|---:|
| Standalone ONEFILE | `dist/2.0.3-preview/release/PhaseStudio-2.0.3-x64.exe` | 77,995,587 |
| Complete Jana ONEDIR archive | `dist/2.0.3-preview/release/PhaseStudio-Jana2020-2.0.3.zip` | 78,381,828 |
| Jana executable, requiring adjacent runtime | `dist/2.0.3-preview/PhaseStudio-Jana2020-2.0.3/Phase_studio.exe` | 9,999,164 |

Keep `Phase_studio.exe` together with its `_internal` directory. The standalone
EXE does not require that adjacent directory. No Superflip/EDMA scientific
executables, SharpED weights or review tutorial PDFs were bundled.

SHA-256:

```text
521412d2ce3602a9c061f52ff8126b6b59dcb74c65bdac52a6814643b2e95d21  PhaseStudio-2.0.3-x64.exe
26e2d73861f24cf0d2a9e57d26fe5b47d0da0c019bc6114b1e62bbce50877584  PhaseStudio-Jana2020-2.0.3.zip
58485262025eaf19062a262256fded5c68896fba9b0e4cbc215fb054d2a9b189  Phase_studio.exe
```

The release directory also contains `SHA256SUMS.txt` and
`RELEASE_NOTES_2_0_3.md`. Packaging names now derive from the canonical source
version, avoiding 2.0.3 code inside a misleading 2.0.2 filename. Corresponding
archive checks and tests use that same version. No scientific application code
was changed in this build task.

## Validation

- 56 direct regression suites: 2,356 reported checks, no failures. The opt-in
  real-project metadata test was skipped because no project fixture was set.
- Pytest: 184 passed, five subtests passed, one opt-in real-project test skipped.
  Its cache could not be written under the sandbox; tests passed independently
  of that cache warning.
- Scientific core golden checks: 46 passed. Jana density alignment: 41 passed.
- Production Python compile check passed.
- Frozen CLI smoke checks passed for both executables: `--version` prints
  `2.0.3`. Windows PE file version is `2.0.3.0` for both.
- Standalone ONEFILE and Jana ONEDIR distribution boundaries passed; new
  authentication, credential, scientific-tools and result-view modules are
  present in both archives.
- Jana native runtime: 100 PE files, no blocking import problems or conflicting
  duplicate DLL names; all non-Windows dependencies are bundled. Windows ICU
  requires Windows 10 1903 or newer, or Windows 11.
- Jana ZIP membership, CRC and all 900 extracted file hashes were verified
  against the source ONEDIR tree.

These checks establish local build/package integrity, not native Jana2020 GUI
acceptance. Launch, selected scientific map/model return and normal Jana
continuation still require the planned real-machine acceptance test. This is
a local preview build rather than a published release.

## Reproduce

Activate the existing `.venv-build` environment, then run:

```powershell
packaging/build_windows.ps1 -Target All -DistRoot dist/2.0.3-preview
```

Build and verification logs are under ignored `build/`, including
`build203-packaging.log`, `build203-pytest.log`,
`direct-test-summary-build-2.0.3.txt` and `build203-frozen-verification.json`.
