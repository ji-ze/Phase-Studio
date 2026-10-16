# Jana2020 browser sign-in — Phase Studio 2.0.4

The server owner's definitive native-client contract supersedes the earlier
feasibility audit. Updated production discovery was fetched anonymously on
2026-10-14 and is retained in `JANA2020_OAUTH_2_0_4_DISCOVERY.json`: it now
advertises `none`, `sharped`, code and S256 as required.

| Setting | Production contract |
| --- | --- |
| Client | `phase-studio`, public native; no secret or Basic client authentication |
| Issuer | `https://jana.fzu.cz` |
| Discovery | `https://jana.fzu.cz/.well-known/openid-configuration` |
| Authorization | `https://jana.fzu.cz/oauth/authorize` |
| Token | `https://jana.fzu.cz/oauth/token` |
| Redirect | `http://127.0.0.1:{ephemeral_port}/callback` |
| Grant / PKCE | Authorization Code / S256; code lifetime 120 seconds, single use |
| Scope | `sharped`; no openid/profile/email requested |
| Resource | Optional `https://sharped.fzu.cz`, omitted by the normal UI |
| Access token | Bearer, 3600-second lifetime; treated as opaque |
| Refresh / ID token | Neither issued or requested |
| Protected API | `https://sharped.fzu.cz/api/user/sharp-ed/{upload,status,download}` |

## User procedure

1. Select your intended SharpED workflow and open **Account access…** when
   connection is required. All configured scientific controls remain intact.
2. Choose **Sign in with Jana2020**. Complete the Jana2020 authorization in your
   default browser using your existing account; there is no separate SharpED
   account and Phase Studio never requests your password.
3. The browser returns to the temporary local callback and shows **Sign-in
   completed**. The dialog closes after the code exchange. Continue the intended
   workflow; no manual key generation or copying is needed for OAuth.
4. Access is session-only. Expired access requires a new browser authorization,
   normally able to reuse an existing Jana browser session subject to server
   policy. There is no refresh-token grant or permanent Remember option for OAuth.
5. **Reconnect with Jana2020** starts a fresh flow. **Sign out** removes active
   OAuth authorization from the application without claiming browser logout or
   deletion of an independently saved legacy access key.
6. For compatibility, **Other sign-in options** expands the legacy manual
   controls. That method retains session-only or explicit Windows Credential
   Manager persistence, key removal and the verified manual token-page instructions.

Authorization completion is not a claim of SharpED inference entitlement.
There is no supplied harmless protected access-check endpoint. Public model
discovery is not used to validate OAuth tokens; API permission is confirmed
by the next normally requested protected operation. No paid job is submitted
just to test login. A 403 is not automatically treated as token expiration.

## Components and security

- `oauth.py`: small standard-library code/S256 implementation for the supplied
  contract. Reuses the inference client's verified Windows truststore TLS.
  Discovery issuer/endpoints are pinned; mismatches fail closed. Redirects of
  discovery/token requests are not followed. No cookie jar or browser automation.
- Fresh cryptographic verifier/state per transaction. A worker binds exactly
  127.0.0.1 on an ephemeral port before the GUI opens the browser. Exact callback
  path/Host, state, parameter multiplicity/shape and optional issuer are checked.
  Invalid/stale responses do not consume a legitimate pending login. A valid
  response consumes the attempt before its single exchange; codes are never retried.
- Listener lifetime is bounded to 120 seconds, individual sockets are timed out,
  and sockets close on completion/failure/cancellation. Callback pages contain no
  credential/code, disable caching and scripts/framing. HTTP request logging is off.
- `oauth_ui.py`: QRunnable workers, explicitly queued dialog delivery and an
  application-owned bridge for renewal requested by scientific worker threads.
  Normal owned dialog behaviour is reused; no permanently topmost window or
  hidden Professional mode is introduced.
- `credentials.py`: existing CredentialStore extended with explicitly selected
  OAuth/manual modes. OAuth token/monotonic expiration are process-only. Legacy
  secure entries are neither overwritten nor removed by OAuth login. Retired
  credential fingerprints identify in-flight operations after renewal; signing
  out prevents further requests using them. Existing secret redaction/migration
  is preserved. Clearing active authorization is not a forensic memory-erasure
  claim; stale scientific configs remain barred from using signed-out credentials.
- `sharped_server_client.py`: OAuth operations use the contract's SharpED origin;
  manual configuration/protocol remains unchanged. Job tokens stay job identifiers,
  never OAuth tokens in URL paths or alternative account headers. OAuth requests
  reject other hosts and HTTP; authenticated redirects are not followed.
- The token deadline is monotonic, starting conservatively before exchange, with
  a 60-second request safety margin. Serialized renewal coalesces concurrent
  callers. Expiration before upload renews before the single POST. Status/download
  GET may reauthorize once after 401 and repeat that same job operation. No 403
  renewal loop, no refresh request, no upload replay on 401/network ambiguity.

There is no additional OAuth/OIDC library: this intentionally implements only
the supplied public-client code/S256 exchange, not JWT identity parsing or
unsupported grant/session protocols. Inference fields, map processing, scientific
selection, EDMA defaults, Uiso policy and Jana handoff are unchanged.

## Controlled frozen/runtime checks

Both executable profiles support opt-in diagnostics:

```powershell
PhaseStudio-2.0.4-x64.exe --oauth-self-check output.json
Phase_studio.exe --oauth-self-check output.json
```

This uses a clearly labelled local fixture, a real loopback listener and Qt
worker delivery, without browser login or inference. Reports contain only
booleans, version and interface/path information; not credentials/codes.

For a user-controlled real browser smoke test:

```powershell
PhaseStudio-2.0.4-x64.exe --oauth-sign-in-check output.json
Phase_studio.exe --oauth-sign-in-check output.json
```

The real dialog uses a separate session-only CredentialStore and reports method,
granted scope and remaining lifetime, never the token. This is opt-in, not a
routine test or inference request. It cannot prove protected API permission.

The current reviewed connection-dialog image is capture 08 in
`docs/screenshots/2.0.4/wizard/README.md`. Its isolated empty credential store
does not establish production login. Geometry/DPI tests likewise do not prove
browser authorization or protected API permission.

Production acceptance must separately record real browser return/token exchange,
an explicitly authorized normal job's upload/status/download, manual fallback,
renewal after expiry and behaviour on a native Jana workstation. If no permitted
job/user interaction is available, those remain acceptance gaps; mock tests and
frozen diagnostics do not close them. No commit, push or public release is implied.
