# Phase Studio 2.0.7 test build

Development build recorded on 2026-11-09. This is an unsigned test distribution,
not a public release. PR #21 remains draft.

Executable source commit: `48205abf4cda4f77ede78f52d37dbf5c585b7241`.
The documentation commit recording this build does not change application code.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| PhaseStudio-2.0.7-x64.exe | 94,199,924 | `b26f45a475330a8606bd5c067e9175e14c6b32fbb9a2f43e617c2a18e26dab49` |
| PhaseStudio-Jana2020-2.0.7.zip | 92,844,860 | `cc318b24d979168b23c2fa667b19c6c0014690f5499869824356656c0b00f4d4` |
| PhaseStudio-2.0.7-test-release-readiness-20261109.zip | 235,103,730 | `6c929e444b0023962e701766d99a0184b4131cad5e5647a89b5658da4a05cc18` |

Local standalone executable:
`dist/test207-release-readiness-20261109/PhaseStudio-2.0.7-x64.exe`.
The same folder contains the Jana ZIP, report, screenshot gallery, checksum
manifest and structured verification matrix. Generated binaries and private
scientific evidence remain outside Git.

Validation on the executable source: 906 passed, three skipped, 37 successful
subtests; all nine scientific authorities and both frozen profiles passed.
Both distributions loaded the eight previously returned real inference maps.
No new inference was submitted. Native Unicode-directory handoff and controlled
updater rollback were verified.

Release status remains **NO-GO**: production SignPath configuration/signatures,
interactive Jana acceptance/refinement, browser SSO, physical/mixed-DPI visual
acceptance, clean VM, whole-application long paths and remaining human review
are not accepted. See [release-readiness details](RELEASE_READINESS_2_0_7.md),
[signing setup](SIGNPATH_2_0_7.md) and the
[manual checklist](MANUAL_ACCEPTANCE_2_0_7.md).
