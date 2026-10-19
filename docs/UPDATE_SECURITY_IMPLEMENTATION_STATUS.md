# Windows updater implementation status

This is an unfinished implementation, not a working automatic installer.
The existing application still provides release notifications and browser-based
release access. The new security modules are not yet connected to that UI.

Completed foundations:

- `update_manifest.py`: canonical versioned JSON, detached Ed25519 signatures,
  compiled public-key trust, exact repository/channel/Windows x64/profile and
  version matching, exact asset names/sizes/hashes and protocol compatibility.
- `update_download.py`: bounded public HTTPS streaming, explicit official
  repository/CDN redirect authority, cancellation, exact-size checks, progress,
  fresh destinations and no authenticated SharpED HTTP client or headers.
- `update_package.py`: checksum verification and validation of the complete
  Jana ZIP inventory before extraction into a fresh staging directory. Rejects
  traversal, normalization, duplicate/case-conflicting paths, links, device names,
  alternate streams, unexpected ownership roots and missing executable/runtime.
- Synthetic tests use ephemeral Ed25519 keys and controlled response fixtures.
  They never establish a production signing identity or download public binaries.

No production public key is configured. `TRUSTED_KEYS` is intentionally empty;
runtime signature verification fails closed. Release engineering must supply a
reviewed public Ed25519 key and identify the approved signing secret/service.
Private keys must never enter source, local acceptance logs or an executable.

Still required before claiming complete update support:

1. Connect authenticated discovery/download/verification to the existing update
   service and consent UI, including exact `/releases/latest` asset metadata.
2. Implement and package the independent Windows transaction helper, process
   identity checks, installation lock, ownership inventory, journal, rollback,
   permission/UAC handling and verified relaunch health protocol.
3. Preserve Jana's parent-process contract. The current `jana_superflip.main`
   directly owns the Wizard/scientific invocation, receives the original inflip
   and working directory, returns nonzero for cancellation and returns after the
   selected workflow. No resident bootstrap keeping Jana's waiter alive was
   established. Restarting another EXE cannot be assumed equivalent. A verified
   bootstrap or explicit reopen-from-Jana fallback is required.
4. Add signed-manifest release tooling and the strict six-asset boundary,
   protected GitHub Actions publication, reproducible frozen helper packaging,
   disposable Windows update/rollback acceptance and actual update-state Qt
   screenshots.
5. Select the next unused patch version after remote tag inspection. Published
   `v2.0.5` and its existing assets must remain unchanged. Existing users need a
   one-time manual migration to the first updater-capable version.

No automatic replacement of an installation has been enabled. No public release
has been created or overwritten by this work. The new modules do not write to
Jana scientific executables, projects or handoff files.
