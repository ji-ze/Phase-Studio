# Manual SharpED key persistence correction (2.0.4)

## Causes found in the implementation

1. `CredentialStore.set` and the manual dialog defaulted Remember to false.
   `save_input` inherited that choice. First-time keys therefore normally lived
   only in `_session`, and disappeared with the process.
2. `load_settings` migrated plaintext QSettings keys to session memory only,
   then unconditionally removed the old copies. The next process had no key.
3. `set(..., remember=False)` deleted a previously saved credential.
   `save_input('')` could reach this path through an empty configuration field.
4. A failed secure-store read was cached as an empty value for the rest of the
   process. GUI fields also retained independent snapshots after account changes.

No packaging-specific Credential Manager target was found: the existing target
is a stable SHA-256 of the API origin, independent of executable path, release
version, standalone/Jana mode or installation directory. The Windows backend
already uses `CredWriteW` with `CRED_PERSIST_LOCAL_MACHINE` (2): persistent across
logon/reboots, scoped to the current Windows user on this machine.

## Resulting policy

- Manual keys default to secure persistence when the Windows backend is
  available. The dialog's Remember checkbox defaults on. Explicitly unchecked
  means session-only for the entered key; an older saved key is retained.
- Only explicit Remove deletes a saved key. Empty configuration saves do not.
  Replacement writes the new key without an intermediate delete.
- Startup still loads the secure store before constructing the active workflow.
  Live Wizard/full-configuration fields subscribe to store changes using owned
  Qt signal bindings, including replacement, removal and OAuth state changes.
- Failed uploads, timeouts, server errors and failed login probes never delete
  credentials. A transient secure-store read failure can be retried.
- Legacy matching plaintext settings are scrubbed only after successful secure
  migration. A failed migration or a different older key is retained rather
  than silently discarded. No new plaintext copy is written. A previously
  deleted credential cannot be recovered by this change.
- Manual key validation shares the HTTP Bearer grammar guard. Unicode-polluted
  credentials cannot replace a working saved key. Valid tokens are saved and
  restored unchanged; scientific metadata remains UTF-8 multipart body data.
- Existing origin isolation is preserved. A key for a custom API origin is not
  silently copied to another host. No additional credential-storage dependency
  is required: the packaged runtime uses Windows `advapi32` through ctypes.

Browser OAuth access remains deliberately short-lived/session-only under the
existing server contract (approximately one hour, no refresh token). This fix
persists manually generated API keys; it does not turn expiring OAuth access
into a permanent credential or change PKCE, endpoints or server policy.

## Verification and build

Automated tests cover default first save, new-store restart, stable legacy
WinCred target, replacement, explicit deletion, opt-out without deletion,
matching migration and failed-migration retry, transient secure-read recovery,
timeout/503 upload followed by success using the same exact key, live Qt field
synchronization, actual Jana Wizard restoration, and Unicode upload/header
regressions. All credentials in these tests are synthetic.

The opt-in `--credential-self-check <report.json> write|read|remove` command
tests the actual WinCred backend in separate packaged processes, under the
exclusive `FZU/PhaseStudio/SelfTest/CredentialPersistence` target. It does not
read or write real production credential targets; JSON contains booleans only.
The final remove phase deletes only this synthetic test entry.

Build command (with `.venv-build/Scripts` on PATH):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File packaging/build_windows.ps1 -Target All -DistRoot dist/2.0.4-auth-fix
```

Logs and synthetic-only diagnostic reports: `build/persistence-*`.
Version remains 2.0.4. Existing distributions are retained. No commit or push.

## Final results

- Focused auth/persistence/Unicode tests: 95 passed, 32 subtests passed.
- Final persistence/manual-dialog/Unicode regressions: 51 passed after the last
  saved-access control adjustment.
- Complete suite: 251 passed, 1 skipped, 37 subtests passed (210.33 s).
- Scientific golden checks: 46 passed. Jana completion checks: 192 passed.
- Both packaging boundaries passed; native dependency audit: zero blocking
  problems and zero conflicting DLL names; Jana ZIP verified 900 files.
- Real packaged WinCred sequence passed: standalone writes synthetic key,
  separate Jana EXE restores it, replaced standalone EXE restores it, Jana EXE
  explicitly removes it. Each phase exited 0. No real credential was accessed.
- Both final EXEs launched the local OAuth callback/exchange and Qt-responsive
  self-check successfully (exit 0). No production inference was submitted.
- Embedded code objects in both final EXEs match current source for credentials,
  access UI, transport, error reporting, OAuth, diagnostics, app and Jana module;
  EXE timestamps postdate those sources. Details/hashes are recorded in
  `build/persistence-frozen-verification.json`.

Standalone was refreshed after the last UI adjustment with the same build
command and `-Target Standalone`. Outputs:

- `dist/2.0.4-auth-fix/release/PhaseStudio-2.0.4-x64.exe`
- `dist/2.0.4-auth-fix/PhaseStudio-Jana2020-2.0.4/Phase_studio.exe`
  (requires its accompanying `_internal` directory)
- `dist/2.0.4-auth-fix/release/PhaseStudio-Jana2020-2.0.4.zip`

Source files changed for this persistence pass: `credentials.py`,
`sharped_access.py`, `app.py`, `jana_superflip.py`, `standalone.py`, and
`oauth_diagnostics.py`; regression tests and user documentation were updated.
The preceding Unicode guard in `sharped_server_client.py` and its error-report
mapping remain included and tested. That failure originates from an invalid
Authorization credential, not the map filename; the historical paste action
cannot be independently reconstructed without inspecting the private value.

Windows itself was not rebooted during verification. Reboot/logon durability
uses the existing Windows Credential Manager persistence mode 2, with the same
current-user/API-origin target as earlier installations. On systems without
secure storage, only explicit session use is available; no plaintext fallback
is created. Already-lost tokens cannot be recovered. OAuth expiry/reauthorization
remains governed by the separate server contract described above.
