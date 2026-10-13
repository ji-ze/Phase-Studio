# Public 2.0.2 release packaging

Use the existing Windows build environment and specifications. Tests must pass
before packaging. No scientific Superflip/EDMA binaries or SharpED weights are
bundled. Public release output contains:

```text
dist/release/PhaseStudio-2.0.2-x64.exe
dist/release/PhaseStudio-Jana2020-2.0.2.zip
dist/release/SHA256SUMS.txt
dist/release/RELEASE_NOTES_2_0_2.md
```

Build with `packaging/build_windows.ps1 -Target All`; All means standalone plus
the Jana developer ONEDIR package, never the historical installer. The ZIP root
is `PhaseStudio-Jana2020-2.0.2/`, with `Phase_studio.exe` and `_internal`.
The archive generator verifies extraction bytes against its source tree.
Historical installer source/specs are retained but not in the public workflow.

License texts collected from installed distributions and upstream notices are
embedded as `PhaseStudioLegal` resources. Rebuild from the published source
using a compatible Python/PySide environment and the checked-in specifications.
To replace Qt/PySide, build those dependencies from the versioned upstream
sources listed in THIRD_PARTY_NOTICES.md, install the modified bindings into a
separate build environment, then rebuild the matching profile. ONEDIR also
allows replacement of compatible dynamic libraries directly. Phase Studio
does not restrict reverse engineering needed to debug library modifications.

Public binary publication requires the appropriate Microsoft runtime rights,
complete third-party notices/corresponding-source access, the approved Phase
Studio license, and passing release checks. A draft is not proof of manual
Jana GUI acceptance or a substitute for outstanding redistribution approvals.

## Manual GitHub release preparation

Use tag `v2.0.2` on the verified release commit and title
`Phase Studio 2.0.2 — First Public 2.x Release`. Paste root release notes.
Upload only the standalone EXE, Jana developer ZIP and SHA256SUMS.txt.
Do not upload the obsolete Jana installer or delete historical releases.
Prefer a draft until outstanding publication gates are cleared. Verify the
remote commit SHA before associating the tag. Never force-push or rewrite
history; the release branch is not automatically merged into main.

The audited dependency versions are recorded in release-requirements-2.0.2.txt.
