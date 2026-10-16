> Historical investigation record. The subsequently supplied native-client contract and implementation are documented in [JANA2020_OAUTH_2_0_4.md](JANA2020_OAUTH_2_0_4.md). Earlier missing-configuration conclusions below are superseded.

# Authentication audit validation — 2026-10-14

## Automated regressions

- Manual authentication: 29 tests passed.
- Authentication dialog geometry: 3 checks passed (100/125/150% DPI).
- Scientific golden checks: 46 passed.
- Direct repository scripts: 56 suites including the above, 2356 reported
  checks/tests in aggregate. Initial packaging-note and mutable-baseline failures
  were repaired and rechecked; these are not hidden as first-pass successes.
- Targeted recheck: configuration DPI, release packaging and split-distribution
  tests: 29 passed.
- Final complete pytest run: **184 passed, 1 skipped, 5 subtests passed**.
  The skipped test requires an explicitly configured real-project input.
- `git diff --check` passed. Runtime scientific/authentication implementations
  are unchanged; only canonical runtime version and test/release inputs changed.

The initial full pytest pass also reported three configuration DPI failures at
the model-selection assertion during concurrent test execution. These passed in
the isolated recheck and in the final full run; no production change was made
to suppress them. Initial root-wide pytest discovery was stopped and replaced
with repository `tests/` discovery, excluding generated build directories.

The scientific AST guard formerly assumed functions were still in app.py and
referenced mutable main. It now pins released v2.0.3 and compares each moved
authority in its actual module; equality is retained, not bypassed.

## Public server checks

See PUBLIC_PROBES.json for anonymous metadata and HTTP status evidence. The
issuer advertises code/S256; the SharpED web redirect requests code/S256 with
its existing web client. No code exchange, authenticated UserInfo, API token
authorization or refresh was tested. These are not production acceptance.

No OAuth implementation exists in this pass, so OAuth mock-provider scenarios
and OAuth UI/distribution-state screenshots are not claimed as passed.

## Joint browser check

The user opened the official SharpED token page and reported successful login
to SharpED Tool with the desktop API-token section. The real current manual
Connect to SharpED dialog was opened visibly, with its normal production
catalogue check and session-only default. The user followed the browser action
and confirmed it leads to manual token generation, not automatic desktop token
delivery. The dialog ended without acceptance or a supplied key. No token was
requested in chat, inspected or recorded. This confirms navigation, not manual
key authorization and not OAuth browser-to-desktop acceptance.

The user reports a Phase Studio client registration exists, but its configuration
is unavailable. Public client ID/type, approved redirect policy, secretless
exchange, scopes/audience and SharpED permission check remain pending.

## Release handling

Branch: development/2.0.4. Canonical version: 2.0.4. No commit/push/tag/publication
or binary build. Previous workshop work is preserved. Existing standalone 2.0.3
EXE SHA256 remains
`521412d2ce3602a9c061f52ff8126b6b59dcb74c65bdac52a6814643b2e95d21`.

**OAuth readiness: not implemented/enabled; awaiting verified server/client/API
configuration and subsequent real acceptance.**
