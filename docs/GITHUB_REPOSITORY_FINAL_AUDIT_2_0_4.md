# Phase Studio 2.0.4 — final GitHub repository audit

Audit date: 2026-10-16. Repository: <https://github.com/ji-ze/Phase-Studio>.
This audit concerns repository integration, not a new scientific or native
Jana2020 acceptance claim.

## A. Repository status

- Default/stable branch: `main`. Development source: `development/2.0.4`.
- Initial stash list was empty; only the excluded workshop was untracked.
- Initial development HEAD and public release tag: `2451961ee4811dccf2f54767df36d08b1064fcdc`.
- Fetched `origin` with pruning and tags before decisions and after merging.
- Initial `main` had one unique merge commit; development had five unique
  commits. The proposed merge was conflict-free and had the development tree.
- Source integration is now on `main` through PR #12, merge commit
  `6d4cdc2ac2b7788d8290542166f526df2540f87f`.
- Tracked work is committed. The local, untracked `docs/workshop/` contains
  38 unfinished workshop files (6,441,385 bytes); it was deliberately excluded
  and preserved. Ignored build outputs, environments and full QA inventories
  also remain local. There was no reset, force-push or history rewrite.
- The development branch is retained at its pushed cleanup commit. `main`
  additionally contains the merge and this documentation-only audit snapshot.

## B. Commits and scientific scope

Already pushed before this audit:

| Commit | Scope |
|---|---|
| `1c4def7` | Jana powder overlap diagnostics and HKL UI |
| `f9b6fe9` | Validated Jana sign-in and secure credential lifecycle |
| `df89005` | Execution lifecycle, result readiness and feedback UI |
| `b4d700f` | Clean distribution/scientific acceptance documentation |
| `2451961` | Final Wizard, diagnostics, notifications, docs and release source |

Created by this audit:

| Commit | Branch / publication | Result |
|---|---|---|
| [`64093d7`](https://github.com/ji-ze/Phase-Studio/commit/64093d796c28157320fa96e92645aeead794d14f) | `development/2.0.4`, pushed | Curated public evidence, portable QA inputs, citation and repository hygiene |
| [`6d4cdc2`](https://github.com/ji-ze/Phase-Studio/commit/6d4cdc2ac2b7788d8290542166f526df2540f87f) | `main`, GitHub PR merge | Integrates the complete validated development history |
| This audit snapshot | `main`, documentation-only follow-up (audit and current README preview) | Exact commit is available in this file's Git history; no source/build change |

The complete development/main diff was inspected by subsystem: OAuth/PKCE,
credential synchronization/renewal and header safety; read-only HKL and verified
powder FWHM/wavelength diagnostics; Wizard/Map Feedback/Execution/Autosolve;
candidate readiness, per-run selection, EDMA threshold identity and Jana
handoff; update notifications; shared viewer presentation; and both packaging
profiles. Existing changes are retained, not reimplemented or guessed at.

The audit itself changes no production module, scientific algorithm, output
convention, numerical default, ranking, authentication endpoint or golden
expectation. All **63 production/assets/build-spec Git blobs** are identical
between `v2.0.4`, the cleanup commit and the merged source. Windows checkout
LF/CRLF normalization is separate from Git blob identity. The full merge tree
also exactly matches the tested development tree. No scientific merge conflict
was encountered.

## C. Pull requests and GitHub checks

- [PR #12 — Phase Studio 2.0.4: Scientific Validation, GUI Improvements and Jana2020 Integration](https://github.com/ji-ze/Phase-Studio/pull/12)
  is **Merged**, from `development/2.0.4` to `main`.
- Head: `64093d796c28157320fa96e92645aeead794d14f`.
- Merge: `6d4cdc2ac2b7788d8290542166f526df2540f87f`.
- Before merge: GitHub reported `mergeable=true`, `mergeable_state=clean`,
  no reviews and zero check runs/status contexts. There were no Actions
  workflows, branch protections or repository rulesets. Therefore no required
  approval/check was bypassed. Zero CI is **not** reported as passing CI.
- The empty combined-status endpoint reported `pending` with zero statuses;
  this is not a queued workflow. Both the raw count and absence of workflows
  were inspected rather than treating it as a failed or running check.
- Merge used the existing repository convention, a merge commit, with the
  exact tested head SHA. No admin override was requested.
- No matching open PR existed beforehand. Historical PRs #7–#11 were merged;
  no duplicate or contributor PR was closed or modified.

## D. Branches and cleanup

| Branches | Classification / action |
|---|---|
| `main` | Stable, updated; never deleted or force-pushed |
| `development/2.0.4` | Source integrated; retained pending the next development workflow |
| `development/2.0.3`, `release/2.0.2` | Integrated historical release references; retained |
| `auto-referencefile-from-cycle-2`, `sharped-phase-recycling`, `beta-visibility-fixes` | Ancestry-integrated older feature branches; retained rather than assuming deletion intent |
| `release/1.0.9-split-distribution` | Remote has 28 commits not ancestry-integrated into initial main; local has another 14 not pushed; preserved |
| Local `release/2.0.0`, `release/2.0.1`, `backup/private-development-2.0.2-20261013` | Unique local history; preserved and not published |

No branch was deleted. Stale tracking references were pruned by fetch; no
concurrent remote work was overwritten. Old branch dates alone were not used
as evidence that unique work could be removed.

## E. Hygiene, licensing and public documentation

- Removed **1,053 generated inventory files from current tracking**, retaining
  every original locally. Preserved **15 curated images** from those inventories,
  their concise READMEs, the separate release/Wizard samples, intentional public
  tutorial PDFs and synthetic tutorial input files. Complete inventories are
  ignored and were not recommitted. One otherwise-selected image was excluded
  after visual inspection found a personal path in its pixels.
- Sanitized public diagnostic/narrative filesystem paths without changing
  scientific values or hashes. QA tools accept `PHASE_STUDIO_TEST_INFLIP`,
  `PHASE_STUDIO_LARGE_INFLIP` and `PHASE_STUDIO_JANA_PROJECT` instead of an
  author's profile path. No datasets or scientific executables were added.
- A local pattern scan of current tracked text found no personal-profile
  paths or potential private-key/GitHub-token/long credential-field matches.
  This is a scoped scan, not a guarantee about every possible secret or all
  historical content. Historical commits/tagged inventories and paths remain;
  removing historical content would require separately authorized history work.
- MIT `LICENSE` is unchanged, including
  `Copyright (c) 2026 Fyzikální ústav AV ČR, v. v. i.` and standard MIT text.
  Citation policy remains separate. README and `CITATION.cff` now cite 2.0.4.
- Phase Studio authorship remains Jiří Zelenka at Fyzikální ústav AV ČR.
  SharpED separately credits Jiří Zelenka, Jan Rohlíček, Monika Kučeráková and
  Zdeněk Buk. Service/API terms and entitlement remain distinct from desktop MIT.
- Third-party notices, Science Gothic OFL, external Superflip/EDMA/Jana rights
  and ONEFILE versus complete developer ONEDIR instructions were inspected.
  The obsolete separate Jana installer is not a new public artifact.
- Added `CONTRIBUTING.md`; existing issue tracker remains the reporting route.
  No issue templates or Actions workflows existed; none was fabricated.
  Updated the vague GitHub description and added factual project topics.
- Checked public Markdown destinations after curation. Eight relative PDF
  links in tutorial *source fragments* resolve at the generated PDF output
  directory rather than the fragment directory; the intended public PDFs
  remain tracked. These are not missing scientific data.

## F. Validation

- Before cleanup commit/merge: complete pytest **356 passed, 1 skipped,
  37 subtests passed** in 301.43 s.
- Complete suite executed again on merged `main` (`6d4cdc2`): **356 passed, 1 skipped, 37 subtests passed in 295.74s (0:04:55)**. No failures.
- Scientific golden runner: **46 checks passed**, before and after merge.
- Explicit standalone runners: Jana completion **192**, Wizard geometry **75**,
  tile/icons **58**, requirements **58**, model formats **27**, Wizard models
  **44**, all passed.
- Packaging source tests: **20 passed**. Existing standalone ONEFILE and
  developer ONEDIR passed their respective distribution-boundary checks.
  The developer artifact is historical, not a new final-main build.
- Opt-in real ochlor metadata/input-preservation test: **1 passed** separately;
  no new inference or native handoff was initiated.
- Python compilation and `git diff --check` passed. No golden output was
  regenerated to accommodate a failure.
- CI against the merge: **not configured**, not a claimed successful Actions run.

Local raw verification remains under ignored `build/github-audit-2.0.4/`.

## G. Separate milestones and remaining acceptance

| Milestone | Actual status |
|---|---|
| Source repository finalized | Validated source and intentional hygiene changes committed/pushed; unfinished workshop excluded |
| Main updated | Yes, merge `6d4cdc2` plus this documentation-only snapshot |
| Pull request merged | Yes, #12, verified through GitHub directly |
| Release preparation | Existing clean tagged build was prepared in the preceding task; no rebuild/publication in this audit |
| Public release | Already published before this task: [v2.0.4](https://github.com/ji-ze/Phase-Studio/releases/tag/v2.0.4); unchanged |

The existing standalone EXE was built from clean tagged commit `2451961`, not
from the later merge/audit commits. Its SHA-256 is
`d55bd1cebab93afc39a72e86b924fea487bccd2ac3fafc6eac2e80789d770773`.
It remains the sole release asset. No tag, release or binary was created,
replaced or deleted in this task. A future artifact claiming a different
commit must be rebuilt from that exact clean commit; tags must not be moved.

Repository integration has no remaining external blocker. Native Jana2020
handoff/overlay and continuation, physical-monitor DPI/fullscreen acceptance
and complete long-running OAuth-expiry scenarios remain product acceptance
tasks. Existing historical OAuth/job and mock/offscreen evidence do not close
them. The remaining UI-review proposals are recorded in
`ui/REVIEW_CORRECTIONS_2_0_4_CS.md`; no release-readiness claim is inferred here.

**GitHub repository finalization completed successfully. All intended validated
Phase Studio 2.0.4 source changes are committed, pushed and integrated.**
