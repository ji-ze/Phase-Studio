# Phase Studio 2.0.3 — SharpED account onboarding

This task follows the standing instruction that subsequent UI work targets **2.0.3**. The attachment's older 2.0.2 title does not change the release version. The existing dirty-tree Wizard/configuration/execution/result-selection work is preserved. No build, commit, push, tag or publication is included.

## A. User experience and confirmed website workflow

The reusable `SharpEDAccessDialog` replaces the SharpED branch of the previous requirements-remediation dialog. Both the normal Jana Wizard and the full application's SharpED-dependent actions use it. An explicit **Account access…** action in the Wizard's advanced SharpED settings and full configuration also opens the same component, allowing an existing key to be replaced or removed.

The visible title is **Connect to SharpED**, with **Use your existing Jana2020 account** below it. Its primary explanation is:

> Connect to SharpED using your existing Jana2020 account. No separate SharpED account is required.

The instructions follow the user's confirmed real-screen procedure exactly:

1. Open the SharpED token page.
2. Sign in with your existing Jana2020 account if prompted. The website may first redirect to Jana2020 sign-in.
3. On the SharpED Tool page, expand **API tokens for desktop application** using **Show**.
4. Enter a **New token name** (for example, Phase Studio laptop) and click **Create token**.
5. Copy the newly generated access key and paste it below.

**Open SharpED token page** calls `QDesktopServices.openUrl(QUrl(reqs.SHARPED_ACCOUNT_URL))`, with the constant pinned to **https://sharped.fzu.cz/sharp-ed**. It opens the system browser. The website handles authentication/redirection; the desktop does not open an invented account page or collect Jana passwords. The provider's [Jana2020 login page](https://jana.fzu.cz/login) is an independently verified sign-in destination, but is not the main desktop action. Unauthenticated public requests to the protected SharpED page returned the Jana login page; authenticated menu names come from the user's explicit confirmation, not an invented server interface.

The desktop input is labelled **SharpED access key**, with **Paste your access key here** as its placeholder. It is masked by default. Show/Hide is explicit; the small help control explains that an access key is also called an API token and belongs to the user's Jana2020 account. Footer actions are **Back** and **Connect to SharpED**. There is no Skip action or silent switch to another scientific workflow.

The remote-data disclosure is visible:

> Electron-density data are sent to the SharpED online service when processing starts. Online access depends on your account permissions.

It also distinguishes the free/open-source desktop software and local Superflip-only processing from the separately governed online service. No service price, unlimited entitlement or new terms-acceptance mechanism is invented. The existing service terms remain unchanged; no provider-published terms URL was available to add as a new link.

Back returns to the calling UI without starting a scientific worker or treating cancellation as a calculation failure. The integration tests compare every pre-existing scientific input control around opening the browser, Back and Connect: input path, cycle budget, manual model choice and all other captured settings remain unchanged. Only the accepted access key changes. Removing saved access also clears the calling Wizard's key rather than reviving a stale copy. The existing preflight loop continues the originally requested workflow after a successful connection check.

## B. Existing authentication protocol and secure storage

The API client remains `SharpEDServerClient`. Its configured base URL remains **https://jana.fzu.cz/**, distinct from the browser's SharpED token-page destination. Upload, user-specific Bearer headers, job tokens, model discovery, status polling, downloads, TLS verification and scientific data transport are unchanged.

The connection check reuses the existing public **GET `/sharp-ed/models`** request. It tests server reachability and expected catalogue format without creating a job. This request is **unauthenticated**, so it cannot prove that a personal key is valid or entitled to inference. The dialog explicitly states that permission is confirmed when online processing starts. No expensive inference, mock production authentication route or imaginary lightweight credential endpoint was added.

The check runs off the GUI thread. A visible Connecting state prevents duplicate requests and freezes editing of the pending credential; Back remains available. Results arriving after dismissal are ignored and do not save a key or start processing. User-visible failures distinguish an empty key, explicit HTTP 401 rejection, explicit HTTP 403 account permission denial, a network timeout/unreachable server, and HTTP 5xx service unavailability. No subscription failure is inferred from a generic network error or public catalogue success. Detailed existing run/wrapper diagnostics remain redacted and project-local; the normal onboarding feedback does not echo server exceptions or credentials.

`phase_studio/credentials.py` is the single credential authority:

- Session-only access is the default for a new key.
- **Remember access on this device** opts into Windows Credential Manager, using standard `CredReadW`, `CredWriteW`, `CredDeleteW` and `CredFree` APIs. Generic credentials are stored for the current Windows user/device with local-machine persistence, not a custom encryption scheme. See the authoritative [WinCred write API](https://learn.microsoft.com/en-us/windows/win32/api/wincred/nf-wincred-credwritew) and [credential structure](https://learn.microsoft.com/en-us/windows/win32/api/wincred/ns-wincred-credentialw).
- Credential targets are namespaced to Phase Studio and scoped to the **API origin**, including scheme/host/port. Browser page credentials are not confused with API-server credentials.
- If persistent storage is unavailable, the current session remains supported. A requested secure save that fails produces explicit feedback and does not fall back to plaintext.
- Replace and Remove use the same authority. Session-only selection removes a previously saved credential when applicable.
- Legacy full-app `inputs/sharped_api_token` and Wizard `api_token` settings are read for the current session, then removed and synchronized. Migration does not silently create new persistent storage; the user can choose Remember explicitly. Scientific settings and paths are untouched.
- A malformed old server address cannot prevent configuration repair. Legacy access stays only in the current UI session while plaintext copies are removed.
- All full-app/Wizard settings-write paths exclude private keys. `RunConfig` and `JanaRunOptions` omit the key from their repr. The existing environment-variable input remains supported without the application persisting it.
- Known configured credentials are registered with diagnostic redaction, which now also removes a bare echoed key, not only labelled token/header forms. The upload client registers the actual key before producing diagnostics. No personal credential was used in testing or embedded in screenshots/assets.

Headless/offscreen processes use session-only storage unless a test backend is explicitly injected, keeping routine tests/captures away from real Windows credentials. Separately, a native Windows Credential Manager smoke test used a unique `FZU/PhaseStudio/test/...` target and a nonfunctional synthetic key. Actual write/read/delete and absence after removal were verified successfully; the temporary entry was removed. No existing credential was read or modified.

No OAuth implementation or dependency was added. The manual credential component is isolated and reusable; a later provider-supported browser authorization method can replace credential acquisition without redesigning the whole application.

## C. Visual and modality validation

The compact dialog prefers **630×650 logical pixels**, with a white background, navy/cyan accents and a small account icon. The existing Phase Studio/SharpED shared brand renderer is unchanged: Science Gothic Regular, zero tracking, only for the product title and wordmark. Ordinary instructions, labels and controls use Segoe UI.

The fixed account header and footer remain visible when the available work area is short; the body can scroll. Error feedback is brought into view. Initial geometry is clamped to the available screen. The dialog is modal and owned by its calling workflow. The existing native foreground helper is reused; its delayed activation callbacks are now bound to the Qt window lifetime, preventing calls on a dismissed/deleted dialog without changing the branding renderer.

Actual Qt screenshots and JSON capture metadata are in [`screenshots/2.0.3-authentication`](screenshots/2.0.3-authentication). Each of the 100%, 125% and 150% software-scale directories includes:

- Missing key / first connection instructions.
- Hidden key and an explicitly nonfunctional visible demo key.
- Connecting, rejected key, account permission denial, connection failure and server unavailable.
- Cancellation and return to the preserved Jana Wizard.

There are **33 screenshots**, with no real account or credential. Tests/captures use mocked connection checks and in-memory device-storage fixtures. Capture windows use 630×650 logical pixels; scale changes their device-pixel size. The separate geometry subprocess guards test the actual available-screen clamp and reachable footer/feedback at all three scales. Software-scaled offscreen rendering is not a substitute for physical Windows monitor/DPI acceptance.

## D. Regression validation

Final validation (all final processes exited successfully):

- **55 direct test scripts, 2,300 checks**. This includes new authentication **29**, new initial screen/DPI guards **3**, existing preflight **30**, requirements **58**, requirements-dialog scaling **6**, Jana completion **192**, workflow states **141**, scientific core goldens **46**, displacement exports **44**, and SharpED API contract **15**.
- Complete unittest discovery: **129 passed** (176.833 s).
- Complete pytest discovery: **129 passed** (177.76 s).
- Native Windows Credential Manager synthetic write/read/delete smoke test passed, with the unique temporary entry removed.
- **33 actual screenshots** across 100/125/150% software scale factors. Fixed header/footer, initial screen clamp and reachable scrolled controls/feedback passed the geometry guards.
- Compile checks and `git diff --check` passed. No scientific golden expectations changed. The read-only `ochlor` input/map tests confirm unchanged original bytes; no new authenticated inference or Jana processing occurred.

The direct run resumed after updating the old geometry fixture to account for the new scrollable body: the first 37 successful results on unchanged production source were retained, and all remaining 18 scripts completed successfully. The revised guard checks that every scrolled button is actually reachable inside the viewport, in addition to retaining its full size and the on-screen frame checks.

Local logs: `build/direct-test-summary-authentication-2.0.3.txt`, `build/auth-resumed-verified.log`, `build/auth-unittest-complete.log`, `build/auth-pytest-complete.log`, and `build/test-logs-authentication-2.0.3/`.

Focused authentication tests cover missing/configured keys, empty input, confirmed URL and every verified website label, explicit Show/Hide, deferred authentication on public catalogue success, rejected keys, permission denial, timeouts, 5xx responses, retries, Back, late callbacks, secure/session persistence, replacement/removal, legacy-settings scrubbing, origin scoping, bare-key redaction, native WinCred layout/payload, unavailable storage, invalid old URL repair, owned modality, and no OAuth/inference probe. Additional real-Wizard integration guards compare all captured scientific controls across browser/Back/Connect/removal and assert that neither Professional nor Autosolve/scientific launch occurs from account management.

Existing preflight tests exercise the full application's Run action and normal Jana workflows with fake scientific workers. Superflip-only/local workflows do not ask for SharpED credentials, and a configured key requires no onboarding dialog. Authenticated connection resumes the requested workflow and its existing default/manual model policy. The existing Jana handoff, workflow-state, selector, scientific golden, Uiso export and packaging suites are included in the complete run.

The account-artwork guard was updated to allow exactly the requested `sharped_access.py:_account_icon` helper while retaining the established product/workflow icon inventory checks. No general exemption was introduced.

The standalone and Jana **source runtime** were exercised through Qt tests and captures. No new frozen EXE or ONEDIR package was built. The frozen 2.0.2 artifacts remain untouched. MIT licensing, `CITATION.cff`, service-term policy, packaging profiles, normal 0.50σ EDMA thresholds, model policy, maps, Map Feedback math, candidate identity, Uiso conversion/limits and Jana protocol outputs are unchanged.

## E. Server dependencies for future OAuth

A separate explicitly validated task will require the server developer to supply or confirm all of the following:

- Issuer/authorization-server metadata and supported discovery.
- Real authorization endpoint and token endpoint.
- Registered desktop **public client_id**; no embedded client secret.
- Allowed native loopback redirect policy, including registered localhost/127.0.0.1 URI and port rules.
- Authorization Code Flow with **PKCE S256** support and required scopes.
- Access-token format, audience, lifetime and validation/error semantics.
- Refresh-token issuance/rotation, secure persistence, revocation and logout policy.
- Account entitlement/quota/service-term behavior and its explicit error responses.
- Redirect-response/CSRF validation requirements; OpenID Connect identity metadata if needed.

None of these values is invented or wired into production. There is no automatic browser-to-desktop key delivery in this release. A real authenticated browser/SharpED processing acceptance run remains outside routine mocked tests and was not performed.
