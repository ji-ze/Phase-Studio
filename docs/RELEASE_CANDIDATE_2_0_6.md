# Phase Studio 2.0.6 release candidate scope

The candidate combines the reviewed signed-updater commit with the pending
scientific EDMA correction, provenance/viewer safeguards, responsive HKL and
Wizard presentation, and Qt overlay lifetime fixes. Version is 2.0.6 throughout.

Scientific outputs are compared against established references. The EDMA
correction intentionally changes incorrect density-derived atom assignments/
ADPs, with explicit justification and actual exported-file regression tests;
it does not change maps, measured reflections, extraction or ranking. See
[the protocol evidence](EDMA_PEAK_PROTOCOL_CORRECTION_2_0_6.md).

The authoritative Windows packaging remains Standalone ONEFILE plus complete
Jana2020 ONEDIR. The full signed ZIP is the supported Jana update protocol.
Never distribute a replacement Jana EXE without its verified matching runtime.

## Deferred, preserved work

- Independent EXE-only signed assets and the stable cross-version runtime
  publication contract are deferred to a later feature release (2.0.7).
- Qt Quick/QML removal remains an explicitly experimental, non-default
  packaging measurement; it is not promoted to the production profile.
- Workshop 2.0.3 source/PDF/screenshots remain local and unchanged. Updating
  their obsolete UI/authentication instructions and reviewing privacy/assets
  is a separate documentation task, targeted after this release. Their supplied
  screenshots do not replace current Jana2020 manual acceptance.

No pending file is discarded, stashed or silently rewritten to implement this
scope. Release audit/manifests, actual test logs, screenshots, package hashes
and manual gates are recorded under ignored `build/release-closure-2.0.6/`.

## Approval and manual gates

Do not merge into main, run production signing or publish without approval.
Before signing, use a reviewed full SHA integrated into main and `publish=false`.
Before any publication, verify/configure `phase-studio-release-publication`
branch/reviewer protection; the previous API audit returned 404.

Real Jana selected-map/model import, Accept last solution and refinement;
graceful-stop/manual-selection return; the cancel/close/reopen parent contract;
interactive UAC/non-admin permissions; physical-monitor GUI acceptance; and a
non-public production-key Actions run remain explicit external acceptance gates.
Passing unit tests, frozen diagnostics and controlled PE fixtures alone is not
full production readiness.
