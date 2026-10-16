# SharpED sign-in dialog polish - Phase Studio 2.0.4

## Implemented UI

The default view now contains shared Phase Studio branding, a compact account icon and Connect to SharpED heading, the requested short description, one navy Sign in with Jana2020 button, the browser reassurance, a subdued Other sign-in options disclosure and Back. It contains no visible API/key instructions, input, Show/Hide, Remember, replacement/removal controls or manual Connect button. Existing configured or saved manual keys no longer expand the alternative automatically.

Other sign-in options reveals Use an existing access key, the masked key input, optional secure/session-only storage, replacement/removal, Sign out where applicable, and the secondary Connect using access key action. The manual action belongs to that panel, not the footer. How to get an access key opens exactly https://sharped.fzu.cz/sharp-ed. A separate Show access-key instructions disclosure contains the verified Show / New token name / Create token procedure. No new account URL or menu was invented.

The waiting view updates its heading and message, uses a subtle indeterminate progress bar and offers Open browser again and Cancel sign-in. Reopening uses the same authorization URL and attempt. Cancellation returns to the initial view; Back closes it. Escape cancels the active attempt, then closes on a second press. Success shows Jana2020 sign-in completed and accepts automatically, without a second Connect click or a claim of independently verified SharpED processing permission.

Expired/near-expiry connections use Reconnect to SharpED. The expired wording is reserved for actual expiry; near-expiry renewal does not falsely claim expiration. The account-permission explanation is used only with ACCESS_DENIED from the existing API classification and an OAuth account context. Manual failures keep their established classification. The alternative remains secondary.

A valid session bypasses redundant missing-credential prompts. Explicit account management (OK status) still opens the dialog, keeping saved-key management and Sign out reachable. Secure storage, masking, removal, separate OAuth/manual credential types and credential redaction are unchanged. Initial focus/Enter select Jana sign-in. Modal ownership and the shared foreground activation helper are preserved; no permanent topmost flag or Professional-mode instance is introduced.

## Geometry and screenshots

Measured Qt logical pixels at 100%:

| State | Before | After |
| --- | --- | --- |
| Default without configured key | 630 x 380 | 540 x 340 |
| Existing key, initial view | 630 x 650, manual section automatically visible | 540 x 340, manual section collapsed |
| Existing-key initial scroll maximum | 154 | 0 |
| Browser waiting | Previous feedback-based view | 540 x 340, no scrolling |
| Alternative explicitly expanded | Full instructions immediately visible | 540 x 679, no scrolling |

Default height reduced by 40 px; with an existing key, initial height reduced by 310 px. Expanded geometry is measured from content and capped to the available screen. The complete help can scroll on constrained screens; Back remains outside the scroll area and all controls can be reached. No horizontal scrolling.

Actual Qt screenshots and per-state geometry JSON: docs/screenshots/2.0.4-sign-in-polish/. Before/after scale-1, scale-1.25 and scale-1.5 directories contain the requested default, waiting, completing/completed, alternatives, manual help, connection failure, expiry, simulated permission denial and cancelled/initial states. There are 46 PNGs including native Windows captures. All authorization responses and permission-denial states are explicitly marked mocked; no credentials or authorization URLs are serialized into capture metadata.

Offscreen DPI results: default/waiting are 540 x 340 at 100% and 125%; at 150% the deliberately small simulated screen clamps them to 504 x 340. All have vertical and horizontal scroll maximum zero. Expanded alternatives on the small 125/150% simulated screens scroll normally. Native Windows captures are under after-native/scale-1; the actual device pixel ratio was 1.25 despite environment scale factor 1. Metadata records the effective DPR, not an assumed 100%.

Capture utility: packaging/tools/capture_sign_in_polish.py. Before captures use the isolated pre-edit source snapshot build/auth-polish-before-sharped_access.py, not an older release whose authentication implementation differs. Shared branding remains Science Gothic Regular, weight 400, zero tracking for the product/SharpED wordmarks, with Segoe UI for ordinary UI. The logo and version 2.0.4 are unchanged.

## Validation

Final complete pytest run: **222 passed, 1 skipped, 37 subtests passed** in 191.63 seconds. Log: build/auth-polish-pytest-final.log. Final combined UI/manual regression run: **43 passed**. Focused OAuth groups: **37 tests** (core 13, API 10, Qt UI 14), plus **29 manual-key/storage tests**. Coverage includes one dominant CTA, hidden default manual controls, both disclosures, same-attempt reopening, repeated-click guards, cancellation/retry and stale results, automatic acceptance, expiry, API-derived permission denial, valid-session prompt avoidance, masking/storage, configuration preservation, ownership/foreground and absence of permanent topmost flags.

An initial full run hit Windows Qt heap exception 0xc0000374 during a later Wizard construction. Completed/cancelled worker signal senders are now retained through their queued completion slot; releasing their final owner is deferred to the next Qt turn. The combined 43-test lifecycle run and final complete suite subsequently passed. The OAuth exchange and scientific worker logic were not changed.

Additional checks: authentication geometry 3 DPI profiles; requirement/scientific-setup scaling 6; Jana completion **192**; density alignment **41**; Jana startup isolation **17**; workflow hierarchy **21**; split-distribution/profile guards **20**. Scientific golden checks **46 passed**, with no golden-file changes. Both source entry points passed --oauth-self-check with actual local callback delivery, mocked exchange and a responsive Qt loop: build/auth-polish-standalone-entry.json and build/auth-polish-jana-entry.json. These checks submit no inference job.

## Scope and remaining acceptance

This pass changed phase_studio/sharped_access.py, tests/test_oauth_ui.py, tests/test_sharped_access.py, tests/test_authentication_geometry.py, the current sign-in user guide and implementation UI wording, and added the capture tool/screenshots/this report. The prior Wizard polish and OAuth working-tree changes were preserved.

OAuth protocol/server settings, client ID phase-studio, scope sharped, pinned endpoints, PKCE S256, public client/no secret, exact ephemeral IPv4 loopback /callback, 3600-second access lifetime, no ID/refresh tokens, and protected API routing/payloads are unchanged. Reauthorization uses the existing authority; job-ID preservation and no duplicate POST are covered by the existing API tests. No Superflip/EDMA settings, maps, ranking, displacement parameters, scientific calculations, licensing or release history changed.

Production browser sign-in and the three-cycle ochlor API calculation were already verified before this UI pass; they were not repeated here. Real one-hour production renewal and real Jana2020 host-window focus/handoff are not newly certified by mocked UI tests. Source entry/profile guards passed; existing frozen EXEs were not rebuilt, so they still contain the preceding dialog UI. The standalone 2.0.4 EXE SHA-256 remains 100492fdc423b1763b2a258a07c3007234f5ad3b7767b77e8a63785bda49f359. No obsolete installer, commit, push, tag, publication or server change.
