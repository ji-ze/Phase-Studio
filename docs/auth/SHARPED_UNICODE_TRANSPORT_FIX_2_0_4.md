# SharpED upload header safety (2.0.4)

The application constructs `Authorization: Bearer <sharped_api_token>` from the
access-key input / credential store, with the environment variable
`SHARPED_API_TOKEN` as a fallback. `User-Agent` is the fixed ASCII default at
application call sites; Content-Type and Content-Length are generated ASCII.
Model, elements and resolution are already multipart body fields encoded as
UTF-8. The ASCII filename `ochlor.xplor` cannot cause this putheader failure.

Consequently a sigma in the reported upload's HTTP headers points to a polluted
authentication credential, not scientific metadata. The original failing
credential was deliberately not inspected, so its exact entry/paste source is
not independently established. A synthetic credential reproduces the original
`http.client.putheader` UnicodeEncodeError at position 311 without real secrets.

The shared request boundary now validates HTTP names/values and the RFC 6750
ASCII Bearer grammar before invoking transport. It rejects Unicode credentials,
embedded instructions and control characters with a classified authentication
error explaining how to sign in again or paste only the key. It never strips,
transcodes or logs the invalid credential. Invalid configuration headers have
their own actionable UI report. Valid Latin-1 non-credential field values remain
supported. OAuth renewal and existing account/job authentication routing remain
unchanged.

No API endpoint, multipart schema, map bytes or scientific computation changed.
Greek and Czech metadata remain reversible UTF-8 body data under the existing
server contract. Tests use a real local HTTP server for multipart transmission
and binary download, plus the existing OAuth request tests. No production job
is submitted by these checks.

Build command (activate `.venv-build/Scripts` on PATH first):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File packaging/build_windows.ps1 -Target All -DistRoot dist/2.0.4-unicode-fix
```

The standalone target is rebuilt after the final error-report source change.
Build/test logs and frozen smoke-test JSON are stored under
`build/unicode-fix-*`. Existing distributions are retained. No commit or push.

## Verification results

- Focused transport/OAuth tests: 22 passed, 8 subtests passed.
- Complete pytest suite: 241 passed, 1 skipped, 37 subtests passed (218.86 s).
- Scientific golden checks: all 46 passed.
- Jana completion checks: all 192 passed.
- Packaging: both distribution boundaries verified; native dependency audit
  reported zero blocking problems and zero conflicting DLL names; developer
  ZIP extracted and verified 900 files.
- Both final EXEs actually launched with `--oauth-self-check`, exit 0; local
  callback, mocked exchange and Qt responsiveness passed. No production sign-in
  or inference was performed for this fix.
- `build/unicode-fix-frozen-verification.json` records final SHA-256 hashes,
  sizes, source age checks, and exact embedded code-object matches for the
  client, error reporting, sign-in UI and OAuth modules in both EXEs.

Outputs:

- `dist/2.0.4-unicode-fix/release/PhaseStudio-2.0.4-x64.exe`
- `dist/2.0.4-unicode-fix/PhaseStudio-Jana2020-2.0.4/Phase_studio.exe`
  (keep its `_internal` directory alongside it)
- `dist/2.0.4-unicode-fix/release/PhaseStudio-Jana2020-2.0.4.zip`

The Jana target was built by `-Target All`; the final standalone was refreshed
with the same command using `-Target Standalone`. HTTP upload/download acceptance
uses the local mock server, not the production SharpED service. The precise
historical user action that contaminated the credential remains unverified.
