# Final Wizard and release acceptance — 2.0.5

## Baseline inventory (before this pass)

- Branch: `development/2.0.5`, HEAD/upstream `851bfb8`, after fetching origin.
- Open PR #13 targets main `75600c4`; two development commits already pushed.
- Authoritative version: `phase_studio/version.py`, 2.0.5.
- Packaging: `packaging/build_windows.ps1 -Target All -DistRoot dist/2.0.5`;
  standalone ONEFILE plus Jana developer ONEDIR/ZIP. Obsolete installer unused.
- Twenty tracked files were dirty, plus accepted HKL/GUI/viewer reports,
  capture tools and the completeness regression. These are reviewed release
  work from preceding tasks. Untracked `docs/workshop/` remains unrelated draft
  material and is excluded from commits and release assets.
- Existing Wizard has two-column summary, 2×3 unit cell, four approved SVG
  cards, shared persistent geometry, async public catalogue, explicit PEAK A /
  SEED policy, manual override, safe account dialog and GitHub update menus.
- Existing scientific/viewer guards: 435 tests plus 37 subtests; 46 scientific
  core, 195 Jana protocol checks. Preserve the accepted frozen selection,
  fullscreen identity, independent EDMA review and camera corrections in
  `VIEWER_HANDOFF_REMEDIATION_ACCEPTANCE_2_0_5.md`.
- Latest local binaries were built from the dirty tree; they are development
  builds, not the final committed release artifacts. Rebuild after review and
  integration. Prior acceptance screenshots are ignored under `build/`.

Final implementation, tests, build provenance and publication evidence follow
as each release gate is completed.

## Implemented and reviewed scope

- Dataset-wide Input analysis toolbar below Reflection data / Crystal data;
  compact HKL record counts retain the exact literal-index/orbit distinction
  and powder-resolution caveat in a tooltip. Input cell precision/conventions,
  italic symbols, composition and all four scientific SVG icons are preserved.
- One persistent Wizard geometry policy, fixed footer, responsive summary
  columns and scrolling only where the work area cannot contain the content.
  Recommended, hover, focus, pressed and disabled tile states remain separate;
  keyboard activation does not auto-select the recommended workflow.
- Three configuration sections, 110 px cycle control, bounded model-status row,
  clear manual match/difference and Restore automatic. Catalogue refresh keeps
  valid manual choices; missing required models remain explicit errors.
  One cycle uses PEAK A, multiple cycles SEED; no server-default substitution.
- Manage account preserves workflow state and opens the shared owned dialog.
  Stored credentials, cached/public catalogue and verified authorization are
  distinct. Public catalogue success cannot verify manual-key authorization;
  no new verification inference is submitted. Secure storage/OAuth are unchanged
  by this pass; preceding accepted presentation fixes are included.
- Existing async GitHub update menu, notification preference/dismissal/backoff
  and safe release URLs remain. Stable numeric comparison also handles an
  installed prerelease; GitHub draft/prerelease assets remain excluded.
- Shared explicit `--release-ui-check` runs isolated offline Qt acceptance in
  either distribution: two-record HKL parsing, navigation, PEAK A/SEED policy,
  account dialog, update menu and active-Jana program resolution without an
  assumed `superflip_original.exe`. Dummy programs are never executed.
- Pending HKL table/search/completeness presentation and immutable viewer/
  selected-result safeguards were reviewed against the previous reports and
  retained. Scientific algorithms, parser column semantics, symmetry, inference,
  EDMA, Map Feedback numerics, coordinates and Jana writers are unchanged by
  this final Wizard pass. No scientific golden data was regenerated.

## Screenshot and test evidence

`build/acceptance-final-wizard-release-2.0.5/scale-{1.0,1.25,1.5}` contains
**51 actual Qt PNGs** plus machine-readable metadata: all 17 states at each
scale, including the actual child HKL validation and account dialogs. A
read-only copy of ochlor supplies 631 records / 631 literal unique indices;
catalogue, access-key and update responses are clearly controlled offline
fixtures. The original input hash is checked unchanged. No private dataset,
raw log or acceptance screenshot is attached to the public release.

Visual inspection covers individual landing/configuration windows and contact
sheets at all scales. At 150% the constrained logical desktop requires vertical
scrolling; keyboard focus scrolls the complete cards into view and the footer
stays fixed. It does not force different outer sizes per page. The dataset-wide
toolbar removes the previous competing action column; model availability is
kept near the selector instead of floating at the far page edge.

Focused results: **84 passed** for Wizard/configuration/update behavior and
**133 passed** for final release diagnostics, account/OAuth, update/version,
distribution and routing guards. The async large-input summary guard passes
after updating only its displayed-label expectation; its 432 records and
off-GUI-thread assertions are unchanged. The first full run found that old
label expectation (444 passed, one failure), which was corrected before the
final complete run.

Independent scripts: scientific core **46**, Jana completion **195**, EDMA
review **20**, viewer **72**, standard model policy **46**, orchestration **79**,
workflow states **141** checks passed. Logs are ignored under
`build/final-release205-*`. Final full-suite and frozen results are recorded
at completion below. Final complete suite: **447 passed, 1 skipped, 37 subtests
passed in 397.87 seconds** (`build/final-release205-full-final.log`).

## Repository, licensing and release gates

GitHub inspection found no existing v2.0.5 tag/release, no branch protection
or rulesets, no Actions workflows/check runs and no required review/status
checks. This is **CI not configured**, not an assertion that GitHub CI passed.
PR #13 is reused. Normal commits/push/merge preserve published history.

Syntax, whitespace/conflict-marker checks and source/artifact/common-secret
pattern review passed. Explicit file selection excludes unfinished workshop
drafts, local scientific datasets, credentials, ignored logs and binaries.
MIT ownership, existing third-party notices, bundled legal-resource generation
and Science Gothic OFL are preserved; no license or authorship is invented.

Native Jana import/refinement continuation, physical-monitor focus/DPI and
long-lived OAuth expiry remain manual acceptance limitations. The installed
local integration advertises 2.0.2 and is not modified by this release work.
Frozen offline fixtures do not establish native scientific acceptance.

## Committed build and publication provenance

Release binaries are rebuilt from a clean detached checkout of the reviewed
PR integration commit, using the established `packaging/build_windows.ps1
-Target All` command. The final commit, Python/PyInstaller versions, artifact
sizes/hashes, PE resource checks, frozen UI/font checks and remote asset digest
verification are recorded in the release body and ignored
`build/release205-final-manifest.json`. This avoids embedding a self-referential
commit/hash in its own source tree. Public assets are restricted to standalone
EXE, complete Jana ZIP and `SHA256SUMS.txt`.

Authoritative publication: [Phase Studio 2.0.5](https://github.com/ji-ze/Phase-Studio/releases/tag/v2.0.5).
No tag is moved and no force-push is used. Workshop drafts remain local.
