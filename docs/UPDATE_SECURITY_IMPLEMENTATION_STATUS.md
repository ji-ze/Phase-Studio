# Windows updater implementation status

Preproduction implementation; public deployment acceptance is incomplete.
The source trust map now contains a public Ed25519 verification key. This is
not evidence that the corresponding GitHub signing secret, protected release
environment or production release has been configured. Runtime installation
availability depends on the compiled trust map and validated package identity;
an empty trust map still fails closed. No release/tag has been created or
replaced by this remediation.

Implemented source paths:

- Canonical Ed25519 manifest verification, exact profile/version/name/hash/size
  matching, public bounded HTTPS downloads and strict complete ZIP validation.
- Shared asynchronous consent/progress/error UI, actual frozen profile detection
  and independent helper packaging with matching compiled public keys.
- Current-user DPAPI plans, protected workspaces, process/path handles, installation
  locks, runtime ownership inventories, transactional replacement and rollback.
- Version-independent SHA-256 runtime content identity over every owned file,
  including the inventory. A verified full package with an identical runtime
  retains the installed runtime byte-for-byte and only replaces the executable.
  This optimization does not yet constitute a separately published EXE-only
  asset protocol or a completed frozen cross-version acceptance test.
- Explicit UAC, original-user restart token, runtime/startup acknowledgement,
  interrupted-journal detection and authenticated manual recovery command.
- One-time key generation/public provisioning and protected build/sign/publish
  GitHub Actions workflow. No key generation takes place during release builds.
- Jana direct launches use explicit close/exit/reopen fallback. No automatic Jana
  waiter/bootstrap or scientific handoff is claimed or performed by the updater.

Acceptance evidence and remaining gates:

- Synthetic signatures, real DPAPI round trips, native Windows process/job/path
  guards and replacement fault injection are tested using disposable fixtures.
- Actual Qt update-state screenshots at 100%, 125% and 150% are stored under
  ignored `build/acceptance-updater/`. Their releases and transfer are controlled
  fixtures; these images are not evidence of public installation.
- The prepared GitHub Actions workflow has not run. Repository environment
  protections and production signing secret must still be configured.
- Isolated native full-runtime replacement, frozen startup, rollback and
  interrupted recovery passed using actual 2.0.6 packages. Identical-runtime
  retention also passed with actual packages and all runtime hashes unchanged.
  These are same-version transaction fixtures, not public signed cross-version
  installation acceptance. A separate EXE-only asset, frozen cross-version
  update, interactive UAC and actual Jana close/reopen remain activation gates.
- Automated cache retention is not enabled; private caches remain for diagnosis.

See [Windows update provisioning](WINDOWS_UPDATES.md) for exact PowerShell and
GitHub setup, the six-asset release contract, ownership boundaries, migration,
recovery and the explicit public-activation checklist. Never describe the updater
as activated until the real key and all native acceptance gates are satisfied.
