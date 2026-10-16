> Historical investigation record. The subsequently supplied native-client contract and implementation are documented in [JANA2020_OAUTH_2_0_4.md](JANA2020_OAUTH_2_0_4.md). Earlier missing-configuration conclusions below are superseded.

# Jana2020 / SharpED server handoff for Phase Studio 2.0.4

Status, 2026-10-14: requested backend confirmation/configuration, **not implemented
server changes**. Jana publishes OIDC discovery and the SharpED web client uses
code + S256. Neither the web client registration nor the manual API-token
workflow establishes public-native Phase Studio authorization.

The user reports a registration exists, but no configuration is available yet.
Confirm and supply that registration rather than creating a duplicate blindly.

## Information the server developer must supply

1. Confirm the trusted issuer `https://jana.fzu.cz`, advertised authorization
   and token endpoints, deployment architecture and test-environment issuer.
   Supply authoritative configuration/documentation; identify any external IdP.
2. Register a distinct Phase Studio **public native** client. Supply its actual
   `client_id`, with token endpoint authentication method `none`. No secret may
   be required or embedded. Do not reuse web client `sharped`.
3. Approve an exact loopback host/path with variable ephemeral port, following
   RFC 8252. Proposed URI pattern: `http://127.0.0.1:{port}/callback`.
   This is a proposal, not a currently verified redirect. Only the port varies;
   do not allow arbitrary hosts, paths or open redirects. Explicitly confirm
   IPv4 policy and whether IPv6 loopback is supported/registered separately.
4. Enforce Authorization Code + PKCE S256 for this public client. Reject missing
   challenges/verifiers, plain, mismatches, downgrade attempts, expired/reused
   codes and mismatched client/redirect. Publish accurate metadata, including
   `none` when supported. Return authorization issuer information or document
   the approved mix-up defence.
5. Supply the minimum **actual** scopes and API audience/resource identifier
   needed by SharpED. No inference scope/audience is invented here. Clarify
   whether profile/email is needed; identity claims are optional, not inference
   authorization. Describe consent and browser-session reuse policies.
6. Confirm whether `/api/user/sharp-ed/upload`, status and download accept these
   access tokens. Describe server validation and job ownership. Preserve legacy
   manual-key clients and current endpoints while introducing OAuth support.
7. Supply a documented, harmless authenticated access/entitlement endpoint, its
   response schema and error meanings. It must neither upload density nor create
   a job, incur a charge or consume quota. A public model list is insufficient.
   Specify 401 versus 403 and the evidence required to classify subscription or
   entitlement denial; never infer a subscription from login success.
8. Specify access-token lifetime, refresh availability, requested scopes,
   rotation/reuse detection, expiry, revocation endpoint and logout semantics.
   Discovery currently advertises no refresh grant. Do not assume refresh is
   available. Define whether API permission changes invalidate existing tokens.

## API and identity validation

Choose/document either signed access tokens validated against the trusted
issuer's keys, or opaque access tokens with authenticated server-to-server
introspection. Validate issuer/audience, lifetime, permitted algorithms, scopes,
account state and job ownership on the server; reject ID tokens as API tokens.
Keep introspection credentials server-side. Enforce current SharpED permissions
and subscriptions independently of account authentication, for every protected
operation. Do not hard-code plans into the desktop.

For desktop **OIDC**, provide asymmetric ID-token signing and verified HTTPS
JWKS metadata/rotation; current HS256-only metadata with no JWKS URI does not
provide a safe desktop signature-verification arrangement. The desktop must
validate signature, exact issuer, audience/authorized-party claims, nonce and
expiry. No shared signing secret may ship with Phase Studio. Alternatively
approve OAuth-only login without ID-token identity claims, retaining correct
access-token authorization at SharpED. UserInfo alone is not an entitlement
check and must not substitute for token validation.

## Desktop implementation after configuration is verified

Reuse CredentialStore and its native secure backend through an explicit typed
OAuth credential/storage extension, keeping manual keys separate and backwards
compatible. Do not introduce a second independent credential manager.

Start the loopback listener before QDesktopServices launches the default browser;
bind only the approved literal loopback address and an ephemeral port. Each
transaction owns a fresh cryptographically random verifier, S256 challenge,
state and (for OIDC) nonce. Keep pending state in memory. Validate method, exact
callback path/host, bounded query shape, unique parameters, state, issuer where
applicable and exactly one code or authorization error. Reject malformed,
unsolicited, duplicate, replayed and stale callbacks. Token exchange must use
the identical redirect URI and verifier over verified TLS. Apply timeouts and
close listeners on completion, failure and cancellation; do not open public
interfaces or require elevation. Never log callback codes or local query URLs.

Validate token type, nonempty access token, lifetime and response shape, then
use the documented harmless SharpED authorization check. Show Connected and
resume the selected workflow only after both authorization and API permission
are confirmed. No workflow restart, implicit mode switch or scientific-setting
reset is allowed. OAuth-only errors must not disable local Superflip.

Support session-only and explicit secure Remember choices. Store sensitive
credential bundles only in Windows Credential Manager, never QSettings/JSON/
INI/projects/logs. Use serialized refresh transactions and atomically rotate
credentials; concurrent jobs must not race refresh or retain revoked credentials.
On refresh failure, require reauthentication. Sign out stops pending attempts,
clears secure/session credentials and invokes approved revocation if available;
local logout must remain possible if revocation is offline. Do not promise that
local logout also terminates the user's shared browser session.

Once operational, use Sign in with Jana2020 as the primary action and Use an
existing access key as the manual fallback. Provide cancellation/retry, timeout,
session-expired and server-confirmed entitlement feedback without raw secrets
or HTTP diagnostics. Preserve the existing owned, non-topmost dialog and all
Jana scientific controls. Never collect passwords or read browser cookies.

## Test environment and acceptance gates

Provide a separate test issuer/client, permitted loopback policy, known audience,
test account access controlled by the server owner, harmless access-check API,
and scenarios for denied entitlement, revocation, refresh rotation/expiry and
offline server. Users authenticate in their browser; do not send passwords or
tokens to Codex. No paid inference job is an authentication test.

Automated mock-provider coverage must exercise code + S256 success/failure,
missing/expired/replayed code, invalid/missing/duplicate state, redirect/query
errors, stale/duplicate callback, browser cancellation, timeout, unavailable
port, network/TLS failure, wrong issuer/audience, OIDC nonce/signature/expiry
(if OIDC chosen), access-token expiry, refresh success/failure/rotation,
revocation, entitlement denial, legacy manual fallback and secure save/removal.

Capture actual implemented states at 100/125/150% DPI in standalone and Jana
ONEDIR: initial, browser waiting, exchange, connected, cancelled, expired,
denied access, fallback and restored Wizard. Mock screenshots must be labelled
as mocks. Verify Jana remains usable in the foreground. Run existing API,
credentials, Wizard, workflow, Jana handoff and scientific golden regressions.

Production enablement requires a real system-browser authorization with the
registered public client, callback, secretless S256 exchange, correct API
access token and harmless entitlement check, followed by supported refresh,
revocation/sign-out and next-session tests. Record redacted evidence separately
from mock results. Keep OAuth disabled until all mandatory gates pass. Do not
publish 2.0.4 as an OAuth release on the strength of discovery alone.

References: [RFC 8252](https://datatracker.ietf.org/doc/html/rfc8252),
[RFC 9700](https://www.rfc-editor.org/info/rfc9700/),
[OIDC Core](https://openid.net/specs/openid-connect-core-1_0.html).
