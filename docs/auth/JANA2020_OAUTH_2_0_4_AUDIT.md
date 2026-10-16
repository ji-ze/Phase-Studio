> Historical investigation record. The subsequently supplied native-client contract and implementation are documented in [JANA2020_OAUTH_2_0_4.md](JANA2020_OAUTH_2_0_4.md). Earlier missing-configuration conclusions below are superseded.

# Jana2020 OAuth audit for Phase Studio 2.0.4

Audit date: 2026-10-14. Starting branch: `development/2.0.3`, commit
`ca8503caac29fec12911a71ea408c0dcb531a064`, runtime version 2.0.3.
Work is now on `development/2.0.4`; runtime version is prepared as 2.0.4.
Existing untracked workshop documentation is preserved. No commit, push, tag,
package rebuild or publication was performed.

## Decision

**OAuth/OIDC is advertised by Jana2020 and used by the SharpED web client,
but native Phase Studio authorization is not yet verified.** This is outcome B
with additional native-client and API compatibility requirements; it is not
evidence of a session-only server (outcome C).

Do not enable desktop OAuth yet. No dormant OAuth client, callback listener,
OAuth dependency or unfinished Sign in with Jana2020 button was added.
The existing secure manual access-key workflow remains active. In particular,
the working inference endpoints and scientific calculations remain unchanged.

The user subsequently reported that a registration exists but its configuration
is not yet available. Its public-native type, identity and redirect policy remain
unverified; this is not a verified Phase Studio client configuration.

The missing prerequisites are a verified **public native** client and its
approved loopback redirect policy, secretless token exchange, SharpED audience
and scopes, API validation/entitlement contract, and real browser-to-desktop
acceptance. Metadata alone cannot establish these prerequisites.

## Current architecture and public evidence

Evidence is retained in [PUBLIC_PROBES.json](JANA2020_OAUTH_2_0_4_PUBLIC_PROBES.json).
Requests were anonymous GETs with certificate verification, no cookie jar and
no redirect following. Cookie names were recorded; cookie values and response
bodies containing session state were not retained. Authorization-request state,
nonce and challenge values were omitted. No password, saved browser session,
API token, paid job or server modification was used.

Observed chain:

1. `https://sharped.fzu.cz/sharp-ed` returns 302 to
   `https://sharped.fzu.cz/login`.
2. That login returns 302 to the advertised Jana authorization endpoint with
   `client_id=sharped`, `response_type=code`, redirect URI
   `https://sharped.fzu.cz/oauth/callback`, scopes `openid profile email`,
   state, nonce and an S256 PKCE challenge.
3. Jana `/login` returns an HTML form posting to Jana `/login`.

The redirect verifies an existing **web** client, not a desktop client ID.
Never reuse `sharped` or its HTTPS callback as Phase Studio configuration.
Laravel session/XSRF cookie names and the login form are consistent with a
session-based web frontend plus OAuth integration; the exact server framework,
database, OAuth library, external identity provider and shared-account internals
are not verified because their source/configuration is unavailable.
User screenshots independently establish the shared Jana account and manual
`API tokens for desktop application` workflow. Anonymous requests do not verify
successful authenticated login or token issuance.

## Capability inventory

| Item | Status | Evidence / limitation |
| --- | --- | --- |
| OIDC discovery | Verified (published) | Jana `/.well-known/openid-configuration`: 200 JSON |
| Issuer | Verified (advertised) | `https://jana.fzu.cz` |
| Authorization endpoint | Verified (advertised and reachable) | `https://jana.fzu.cz/oauth/authorize`; parameterless GET returns 400; web redirect targets it |
| Token endpoint | Verified (advertised only) | `https://jana.fzu.cz/oauth/token`; no code exchange attempted |
| UserInfo endpoint | Verified (reachable) | `https://jana.fzu.cz/oauth/userinfo`; anonymous GET returns 401; authenticated claims not tested |
| Response type | Verified (advertised/web request) | `code` |
| PKCE S256 | Verified (advertised/web request) | S256 in metadata and web redirect; enforcement and downgrade rejection not tested |
| Scopes | Verified (advertised) | `openid`, `profile`, `email`; no SharpED inference scope advertised |
| Token endpoint authentication | Verified (advertised) | `client_secret_post`, `client_secret_basic`; `none` is absent |
| Secretless public client | Requires server configuration | User reports registration exists; actual desktop client ID/type and `none` exchange contract not supplied |
| Loopback redirects | Requires server configuration | No native redirect policy supplied; web HTTPS callback is insufficient |
| ID-token signing | Verified (advertised only) | HS256 only; no actual ID token/signature tested |
| JWKS endpoint | Not verified | No `jwks_uri` in discovery; no guessed key endpoints probed |
| External identity provider | Not verified | No server configuration available |
| OAuth AS metadata | Unsupported at checked path | Jana `/.well-known/oauth-authorization-server`: 404; this does not negate OIDC discovery |
| SharpED metadata | Unsupported at checked root paths | Both standard root discovery paths return 404 |
| Refresh grants/tokens | Not verified | Only `authorization_code` advertised; no refresh grant or offline-access scope listed |
| Revocation/introspection | Not verified | Not advertised; no endpoint guessing performed |
| Phase Studio client registration | Requires server configuration | Cannot infer registration eligibility or fabricate a client ID |
| SharpED access-token acceptance | Not verified | No OAuth credential obtained or API job submitted |
| API audience and entitlement | Requires server configuration | No published inference audience/scope or harmless authorization check established |
| Legacy-token coexistence | Not verified server-side for OAuth | Existing manual client remains supported; OAuth coexistence requires server confirmation |

HS256 verification needs a shared signing secret. Embedding that secret in a
public desktop executable would compromise identity verification. For desktop
OIDC, request asymmetric signing and a verified JWKS URI; alternatively choose
OAuth-only acquisition with server-side API token validation and no ID-token
identity handling. Do not pass an ID token to the inference API. The current
metadata does not prove OIDC conformance or native-client security.

## Existing reusable desktop infrastructure

- `phase_studio/sharped_access.py`: shared Connect to SharpED dialog, system
  browser via QDesktopServices, exact token-page URL, masked manual key,
  asynchronous check, Back/cancellation and late-result guards. Passwords are
  never collected. Owned modality avoids a permanently topmost dialog.
- `phase_studio/credentials.py`: one CredentialStore, session-only default or
  Windows Credential Manager persistence, scoped to API origin. Removal clears
  the secure entry and session cache; legacy QSettings keys are migrated into
  the session and removed with settings synchronization. Logical settings
  removal is verified; forensic erasure of disk/registry history is not claimed.
- `phase_studio/error_reporting.py`: private-value registration/redaction used
  before manual credentials are probed or stored. No custom encryption.
- `phase_studio/sharped_server_client.py`: verified TLS, default API origin
  `https://jana.fzu.cz/`, existing `Authorization: Bearer` support. This header
  currently carries a manual key; Bearer syntax does not prove OAuth acceptance.
  Upload/status/download remain `/api/user/sharp-ed/...`.
- `phase_studio/requirements.py`: `/sharp-ed/models` is public. Preflight proves
  reachability/catalogue shape, **not** token validity or inference entitlement.
  There is no established harmless authenticated inference-access probe.
- `tests/test_sharped_access.py`: storage, settings migration, key redaction,
  manual fallback, asynchronous errors, browser URL, owned dialog and Wizard
  configuration preservation. `test_authentication_geometry.py` covers
  100/125/150% DPI. Existing API/Jana/workflow/scientific guards remain relevant.
- `packaging/build_windows.ps1` and `packaging/pyinstaller`: standalone ONEFILE
  and Jana developer ONEDIR (`Phase_studio.exe` + `_internal`) derive version
  from the canonical source. No new runtime dependency or obsolete installer
  is introduced. Existing 2.0.3 binary artifacts are untouched.

There is no implemented OAuth/OIDC/PKCE flow, refresh-token state machine or
callback handler in the current app. Reuse the secure storage boundary later;
do not overload a manual key entry with an unvalidated OAuth token bundle.

## Implementation and acceptance boundary

Changed runtime code: canonical version only. Version-specific logging/Jana/
distribution expectations are advanced to 2.0.4. Draft release notes supply the
versioned packaging input. A pre-existing scientific baseline test referenced
mutable main and functions already moved out of app.py; it now pins v2.0.3 and
compares the released module authorities directly, retaining AST equality checks. Scientific defaults, including
both normal EDMA thresholds of 0.50 sigma, model selection, Uiso limits and all
Jana map/model generation remain untouched. The existing manual dialog remains
the only active connection UI; no fake waiting/connected/expired OAuth states
or screenshots are presented.

The [server specification](JANA2020_OAUTH_SERVER_REQUIREMENTS_2_0_4.md) defines
configuration, implementation sequence and release gates. OAuth mock tests and
OAuth state/DPI/distribution captures are not applicable until a client is
implemented; they are not reported as passed. Existing manual-flow regression
and scientific checks are recorded separately in the validation report.

**Release readiness: OAuth is not implemented because the complete public-native
authorization and SharpED API contract is not yet verified/configured.** Do not
publish 2.0.4 as an OAuth release. This finding does not assert that the server
cannot support a native client after configuration.

Standards used: [RFC 8252](https://datatracker.ietf.org/doc/html/rfc8252),
[RFC 9700](https://www.rfc-editor.org/info/rfc9700/),
[OIDC discovery](https://openid.net/specs/openid-connect-discovery-1_0.html).
