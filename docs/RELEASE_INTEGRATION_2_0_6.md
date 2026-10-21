# Phase Studio 2.0.6 — release integration record

2026-10-21: the user reports that the accepted RC build has been tested and
authorizes final Git integration, official signing and publication subject to
the stated release gates. Individual manual Jana, live OAuth, UAC and monitor
results have not been supplied; no specific manual result is inferred.

The complete accepted source inventory was rechecked against the working tree:
zero differences in all recorded files. The two local RC hashes still match
`FINAL_RELEASE_ACCEPTANCE_2_0_6.md`. No runtime changes were made during release
closure. Only this integration record and a historical-status clarification in
the acceptance report were added after acceptance. Workshop materials remain
local, untracked and excluded from the release commit.

Fresh release-critical rerun: **124 passed, 3 skipped**, covering manifest
verification, signing, package integrity, transaction rollback/recovery, Windows
process guards, cross-process OAuth persistence and EDMA recovery. The three
skips are inapplicable distribution-profile transaction combinations. The
complete combined-tree result remains **625 passed, 4 skipped, 37 subtests passed**.

GitHub audit:

- PR #14 contains only the earlier development subset; draft PR #15 adds only
  the updater to that development branch. Neither contains the complete RC.
- The consolidated release branch includes both subsets and the accepted final
  corrections. A consolidated PR to main supersedes the partial integration
  paths; no wholesale unrelated development merge is needed.
- No v2.0.6 tag/release exists at audit time. main has no branch-protection rule
  or repository ruleset; that is not treated as evidence of a completed review.
- `phase-studio-release-signing` exists, allows main only and has the named
  `PHASE_STUDIO_UPDATE_SIGNING_KEY` secret. Only its name was inspected.
- **`phase-studio-release-publication` is absent. Publication is blocked.**
  Its intended approval/protection rules require configuration and verification.
- No Actions runs currently provide release checks for the new combined tree.

The existing workflow accepts a full `source_ref` SHA and boolean `publish`.
It rejects sources outside main and existing version tags. Once integration
and environment gates pass, first use `publish=false` on main, independently
download and verify `authenticated-windows-release` using the pinned key ID
`1c016867382d60e0`, then run both frozen-profile acceptance checks against the
official artifacts. Local RC hashes are not asserted to equal future CI hashes.
Publication must use the protected existing pipeline, which creates a draft,
downloads assets and verifies them before making the release public.

No official signing or publication run has been started at this stage. Ed25519
update-manifest signing is distinct from Windows Authenticode; no Authenticode
signature is claimed. No private key or user dataset is included in the commit.
Version remains 2.0.6; the changelog is intentionally still marked RC until
publication actually succeeds.
