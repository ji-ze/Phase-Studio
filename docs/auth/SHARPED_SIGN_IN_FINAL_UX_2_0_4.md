# Final SharpED sign-in UX - 2.0.4

## Changes and cause

The previous 340 px collapsed minimum and body stretch reserved space above Back; a 300 px minimum also spread out the smaller progress/error views. Sizing now follows visible Qt height-for-width hints plus only visible chrome. No expanding body spacer remains. Default minimum is 300 px; smaller states can fit their own content. Expanded forms are bounded by the current screen, and collapsing restores the compact size.

Default copy matches the latest request: Use your existing Jana2020 account..., browser reassurance explains automatic continuation, and Use an access key instead is the only secondary disclosure. Shared logo, Science Gothic Regular/400/zero tracking wordmarks, Segoe UI and version 2.0.4 are unchanged.

One presentation-state authority defines heading, description, action labels, progress, Back, disclosure and browser actions. Waiting/exchange use animated Working dots instead of a fillable bar or percentage. Waiting offers reopening the same URL and Cancel sign-in, with no Back. Exchange hides reopening, uses Connecting to SharpED / Completing your secure connection, and preserves the existing safe cancellation guard. Cancel/Escape return to the previous Wizard; the listener is cancelled, late callbacks/results are ignored, and the UI timer stops. Successful exchange activates the credential and accepts immediately: the success capture is a pre-accept test hook, not a screen requiring another click. Caller continuation/error handling is unchanged.

Jana network failures offer Try again; timeout offers Sign in again with fresh state/verifier; malformed responses use a short retry message. SharpED reachability failures identify SharpED and recheck using the existing credential, without a new OAuth transaction or inference submission. The retry view says Connecting to SharpED while checking, rather than retaining the failure heading. A generic server 403 gets SharpED access unavailable, no default reauthentication and no billing/subscription inference. Existing API classification does not establish a structured entitlement reason, so the more specific signed-in/subscription wording is deliberately not asserted from it. No billing/account-switching URLs were invented. Only a fixed whitelisted error category is sent to the diagnostic logger; credentials, authorization URLs and raw error bodies are not logged.

Manual mode now has a short description, an integrated eye action in the password field, Connect using access key and the verified Get an access key link. Detailed instructions stay behind a subdued disclosure and remain in the user guide. Persistence preferences/replacement/removal are collapsed separately. A different key cannot silently replace saved access: the first attempt reveals saving options, preserves the existing key and requires an explicit second Connect. Sign-out masks any restored legacy key. Secure credential authority/protocols are unchanged.

## Measurements (Qt logical pixels, 100%)

| State | Previous | Final |
| --- | ---: | ---: |
| Default | 540 x 340 | 540 x 323 |
| Browser waiting / exchange | 540 x 340 | 540 x 240 |
| Manual options | 540 x 679 | 540 x 576 |
| Manual help | 540 x 748, scroll maximum 71 | 540 x 724, scroll maximum 0 |

All these final states have no horizontal scrollbar. Small/high-DPI screens may legitimately scroll expanded content; footer/actions remain reachable. Actual per-state sizes and effective DPR are recorded beside captures.

## Storage investigation

The earlier screenshot tool explicitly injected CredentialStore() without a backend; offscreen global processes also deliberately disable persistence. The warning therefore did not prove a Windows storage failure. A read-only native initialization check confirmed WindowsCredentialBackend is available here; no credentials were read/written/deleted by that check. Mock screenshots separately show session-only and persistent-backend modes. Actual WinCred writing was not re-tested using a real secret. The session-only wording is now just Your access key will be used for this session only, within manual mode. OAuth remains memory-only; no refresh token/persistent OAuth storage was added.

## Tests and scope

Full suite: **229 passed, 1 skipped, 37 subtests passed** (build/auth-final-pytest-verified.log). After the final visual refinements, the combined authentication/manual suite passed **50 tests** and all three DPI geometry profiles passed. New guards cover timeout/fresh retry, waiting versus exchange, API retry without OAuth or persistence changes, denial without reauthentication, collapse sizing, integrated masking and saved-key review. Existing callback cleanup, GUI responsiveness, typed credentials, secure storage, cancellation/stale results, ownership/foreground and scientific-configuration invariants remain green. Requirement scaling: 6 checks. Scientific golden checks: **46 passed**; Jana completion: **192 passed**. Source standalone and Jana entry-point self-checks passed with local mocked exchange and real loopback delivery; no inference was submitted.

OAuth core, server settings, protected API endpoints/payloads, client phase-studio, PKCE S256, scope sharped, literal IPv4 /callback, 3600-second lifetime and absence of ID/refresh tokens are unchanged. No scientific code, configuration defaults, candidate/job identities, metrics, map/model outputs, licensing or release history changed. Prior dirty-tree work is preserved. Production browser/API acceptance from the earlier real ochlor run was not repeated for this UI-only pass. Native real Jana2020 focus and real one-hour renewal are not newly certified by mock tests.

## Captures and files

Actual PySide6 widgets: docs/screenshots/2.0.4-sign-in-final/before and after, each at scale-1, scale-1.25 and scale-1.5, plus after-native/scale-1. Before uses the saved preceding 2.0.4 source snapshot, not an older OAuth implementation. Captures cover default, waiting, exchange, pre-close success, manual mode/help, failure, expiry, generic denial, cancellation returning to the actual Wizard with preserved configuration, Jana retry, timeout and mocked saved-access management. Metadata marks mocked authorization; no real credentials appear. Native effective DPR is recorded, rather than inferred from the environment factor. Capture utility: packaging/tools/capture_sign_in_final.py.

Production changes are confined to phase_studio/sharped_access.py. Related tests, current user guide, this report and screenshot tooling were updated/added. Existing EXEs were not rebuilt and retain the earlier UI; frozen-profile acceptance requires a subsequent build. No commit, push, tag, publication or obsolete installer.
