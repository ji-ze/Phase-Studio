# Phase Studio 2.0.2 public release audit

Audit date: 13 October 2026. Public baseline: v1.0.10. Versions 2.0.0 and
2.0.1 were internal builds. Runtime/source version remains 2.0.2.

## Source and repository

The current source snapshot is reviewed on release/2.0.2. Private local paths
were removed from current documentation and optional external-data tests.
Local scientific acceptance reports remain local; no maps, personal tokens,
machine logs, virtual environments or build caches are committed. Generated
build shortcuts and credential files are ignored. Historical source scanning
covered 762 blobs and found no credential-shaped literal candidates.

The public release commit is based on the existing public main ancestry;
unpublished development history is preserved locally. Existing public commits,
branches, tags and 1.x Releases are not rewritten or deleted. Main integration
is reviewable separately; no automatic main merge is assumed.

## Licensing and attribution

Unmodified MIT with owner-confirmed copyright line:
`Copyright (c) 2026 Fyzikální ústav AV ČR, v. v. i.`
Scientific citation is project attribution policy, not an extra MIT restriction.
CITATION.cff passes the official CFF 1.2.0 JSON schema; no DOI, paper or journal
is invented. Release date is omitted while publication is not confirmed.
Jiří Zelenka is Phase Studio author/lead developer; the four SharpED developer
credits are separate. README, AUTHORS, About and software metadata reflect this.

Dependency licenses are collected into the frozen legal resources. Qt/PySide
LGPL and third-party texts, the bootloader exception, Python/numerical-library
notices, OpenSSL 3.5.7 notices and the Science Gothic OFL text are retained.
Unused Qt virtual-keyboard/PDF plugins are excluded. Exact-version Qt/PySide
source download directories were checked successfully; rebuilding/replacement
instructions and upstream source links are provided. Gemmi 0.7.5 covered source
is available at https://github.com/project-gemmi/gemmi/tree/v0.7.5.
Microsoft runtime DLLs come from the PySide wheel; installed complete Visual
Studio Build Tools and Community products were identified. Redistribution
continues to be governed by Microsoft's separate license terms, not MIT.
This is a technical/provenance audit, not independent legal certification.

## SharpED Public API

The supplied five-page PDF names jana.fzu.cz as Public API and sharped.fzu.cz
as browser service. The client default was corrected to the documented Public
API, retaining bearer/job-token authentication and the existing user routes.
Both model catalogues returned the same four exact model IDs. The final frozen
standalone also fetched the documented catalogue successfully using Windows
truststore with certificate and hostname verification enabled.

The temporary preview ends 31 October 2026, 23:59 Europe/Prague. Later charges
and entitlements follow provider policy. Phase Studio is free software; that
does not grant SharpED account/subscription access, server code or weights.
No personal credential or authenticated scientific submission was used in this
release catalogue audit. Authenticated inference still needs account acceptance.

## Automated validation

- 48 direct suites: **2,188 checks passed**.
- Unittest discovery: **64 tests passed**.
- Pytest: **64 tests passed**.
- Scientific golden values, generated Superflip inputs and report schemas pass.
- Normal EDMA 0.50σ defaults, Uiso Biso conversion/clamping (0.010–0.150 Å²),
  candidate-specific Jana return and original density coordinate frame pass.
- Jana completion (192 checks), density alignment (41), displacement (44),
  normal EDMA defaults (17), model policy (44), final UI (30), selector (72),
  workflow-state (141), DPI clipping (18) and public package guards (6) pass.
- compileall and git diff --check pass.
- Both actual frozen brand checks resolve Science Gothic weight 400, zero
  tracking. Body text uses the normal UI font.
- Developer version query exits without creating a Wizard.
- Native dependency/import audit: no unresolved imports or conflicting DLLs.
- Developer archive: **899 files** extracted and verified byte-for-byte.

## Distribution

Public files are standalone EXE, Jana developer ZIP, SHA256SUMS.txt and release
notes. The obsolete separate installer is not built or uploaded.
The ZIP root contains PhaseStudio-Jana2020-2.0.2/Phase_studio.exe and _internal.
Hashes are recorded in the checked release manifest and final task report.

## Not tested manually / publication status

Actual Jana GUI import, visual map/atom alignment, normal continuation and
second-run acceptance remain not tested in this environment. Automated/file
checks are not claimed as manual acceptance. Authenticated SharpED inference
and multi-monitor workstation acceptance also remain unperformed here.
The GitHub release should remain a draft until the maintainer resolves the
remaining acceptance/publication gates. No default-branch merge is automatic.
