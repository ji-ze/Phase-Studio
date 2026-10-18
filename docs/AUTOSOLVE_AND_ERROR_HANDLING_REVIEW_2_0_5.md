# Autosolve and error recovery review — 2.0.5

Recorded 2026-10-18. This is source-development acceptance, not a published release.
Detailed local evidence: `build/acceptance-autosolve-errors-2.0.5/` and the
`build/autosolve-*-205.log` files. Scientific datasets, generated logs, binaries
and screenshots are intentionally excluded from the source commits.

## Confirmed causes and corrections

1. `autosolve_review.py` required two obsolete koala identifiers. The public
   production catalogue was queried without credentials or inference and returned
   `UNIVERSAL`, `SEED (cyclic CF)`, `PEAK A (model prediction)` and
   `PEAK B (model prediction)`. Its entries are the explicit API identifiers.
   `AUTOSOLVE_MODEL = "UNIVERSAL"` is now the sole Autosolve authority; search and
   prediction constants are compatibility aliases to it. The required tuple has
   one entry. There is no server-default alias or fallback.
2. Changing only those constants would incorrectly expose internal search maps
   as Structure predictions: the old candidate filter distinguished stages by
   model name. Refinement cycle membership is now tracked separately, including
   adaptive extensions, and cleared on a fresh run. Dedicated prediction records
   retain their existing provenance. Correction search maps remain internal.
3. The launcher showed the execution window before calling `start_run`. It now
   completes startup validation first, and creates Execution only after a
   successful start. Failure or cancellation closes the hidden backend and
   returns to Jana without a misleading empty running window.
4. Requirements previously ran synchronously in the Qt thread. Autosolve uses a
   read-only daemon probe with a request-local result queue and a cancellable
   progress dialog. Only the owning GUI request consumes its result. Cancelling
   drops the result; it cannot start a calculation or replace a later request.
   The underlying bounded network read can finish after cancellation; no
   scientific worker or submission is created by that probe. A reentrant start
   guard prevents duplicate starts while modal event processing remains active.
5. Missing models were wrapped in an Input validation report. They now have
   `sharped_model_missing`, the exact UNIVERSAL compatibility explanation and a
   working Try again action that refreshes requirements before another attempt.
   Failed catalogue retrieval remains a requirements/network/protocol failure;
   cached configuration model lists cannot establish model availability.
6. `_open_configuration_page` selected a tab on a hidden scientific backend but
   never made that destination visible. It now selects a verified page, shows
   and activates the actual configuration window, and focuses the page. An
   unknown page raises an explicit recovery error. Network/model errors no
   longer offer irrelevant settings actions. Callback failures are reported,
   rather than silently ignored, after the original modal dialog closes.
7. HTTP 403 is now authorization denial, distinct from 401 authentication.
   Download probing preserves both OAuth failures instead of swallowing an
   authorization denial as an output-not-ready result. No inference POST retry
   was introduced. Typed authentication, authorization, malformed catalogue and
   certificate categories take precedence over server wording.
8. Malformed catalogue arrays are rejected instead of silently filtering them
   into a valid-looking empty model list. Error redaction additionally covers
   API/access-key assignments, authorization codes, PKCE verifiers and callback
   `code` query parameters.

## Presentation and lifecycle

Before a first structure, Autosolve presents a readable solution-search state
instead of two empty comparison panels. With one candidate, the existing viewer
uses the available panel; the prediction panel appears when prediction begins.
Once both candidates exist, the established comparison and review controls return.
No scientific job is recreated by this transition.

The title distinguishes preparation, phase search, prediction, refinement, review
and terminal states. Not-started is separate from Running. Terminal progress is
determinate; terminal Close does not change a completed run into a cancellation.
The shared camera pauses for two seconds after interaction. Empty hidden viewers
do not animate. Footer controls remain in the existing fixed footer. Candidate
readiness and canonical Result Selection remain the export/handoff authority.

An additional confirmed presentation bug was corrected: the ordinary workflow's
generic placeholder branch overwrote real stage-only progress when there was no
concurrent-operation record. Stage-only Superflip/EDMA/SharpED events now retain
their actual activity text.

## Error and action audit matrix

Recovery is deliberately explicit. Closing an error never automatically replays
an upload. Execution Retry uses the existing completed-stage checkpoints.

| Category / subsystem | User message and guidance | Actual action target | Retry / operation state | Regression evidence |
|---|---|---|---|---|
| Input / Wizard and Professional | Check invalid input before starting | Relevant file selector or visible Input page | Correct input first; no execution | remediation failed-preflight tests; configuration tests |
| Superflip runtime | Superflip unavailable; locate the installed executable | Shared local-tool remediation | Before launch, then recheck | requirements and scientific-tools setup tests |
| EDMA runtime | EDMA unavailable; locate the installed executable | Shared local-tool remediation | Before launch, then recheck | requirements tests; EDMA review tests |
| Autosolve model missing | UNIVERSAL absent from a valid live catalogue | Try again reruns requirements; Close returns to caller/Jana | No inference started | guided checks; failed-start and actual-button tests |
| Catalogue malformed / unavailable | Cannot establish current catalogue state | Shared requirements recovery; close if unavailable | Refresh only; never substitute another model | API contract; requirements; typed-category tests |
| Network / SharpED | Cannot connect; check connection/service | Close report, then existing Execution Retry | Resume unfinished stage; no blind upload replay | guided prediction failure/retry; OAuth API tests |
| TLS / SharpED | Secure connection cannot be verified | Close; repair trust/date configuration | Keep certificate verification enabled | TLS and transport tests |
| Authentication / SharpED | Sign in again or use an access key | Existing account-access remediation dialog | Browser PKCE or secondary manual key; explicit retry | OAuth UI/access/API tests |
| Authorization / SharpED | Request denied; account access needs checking | Close; contact administrator | No unsupported billing inference or credential clearing | 403 regression; OAuth download probe test |
| Server / SharpED | Server could not complete processing | Close; Execution Retry where applicable | Completed stages retained | guided retry and workflow-state tests |
| Timeout / processing | Configured request/polling limit reached | Close; inspect server status and retry explicitly | Duration unknown; no fabricated percentage | transport and workflow tests |
| Download / SharpED | Result download unavailable or invalid | Existing safe GET recovery / close | GET may resume; no replacement inference | OAuth API; API contract |
| Scientific stage / Superflip or EDMA | Calculation failed; inspect detailed log | Close; retry unfinished stage | Valid completed results retained | scientific golden, guided, review EDMA |
| Result Selection | Missing or changed artifacts prevent passing | Return to existing results | No recomputation or alternate candidate substitution | Jana completion; selector tests |
| Jana handoff | Could not pass selected result | Close and review preserved completed result | No success before publication completes | Jana completion and orchestration checks |
| Save / filesystem | Save failed; choose writable destination | Existing destination selector or close | Explicit export retry | filesystem/reporting and Jana completion tests |
| Cancellation | Operation stopped at user request | Close or return to caller | No unexpected-error replay | cancellation/preflight/guided tests |
| Update notification | Available release / check failure | Existing shared update UI | No workflow restart | update checker/UI tests |

The audit reuses the existing shared reporter and authentication flow. It does
not introduce a second error UI, OAuth client secret, refresh-token protocol or
new scientific writer. The existing reporter retains expandable, sanitized
technical details and keyboard-accessible native buttons.

## Scientific invariants and model defaults

Only Autosolve's requested neural-network model changes. Its five initial cycles,
three-cycle refinement blocks, random-phase input, structure feed-forward, EDMA
sigma policy, candidate scoring, Map Feedback calculations, measured-data
provenance, export normalization and Jana protocol remain unchanged.

The normal one-cycle Wizard still recommends PEAK A, multiple cycles recommend
SEED, and explicit Professional selections remain intact. Every actual mocked
multipart Autosolve submission is checked, rather than only testing constants.
Search/prediction/refinement/correction/retry paths all submit UNIVERSAL.

## Automated and visual evidence

- Guided engine/actual generated inputs and multipart submissions: 150 checks.
- Autosolve execution/viewer controls: 253 checks.
- Autosolve orchestration, selected candidate and early-stop handoff: 79 checks.
- Launcher routing, including failed preflight with no execution window: 36 checks.
- Standard Wizard model policy: 46 checks.
- Scientific golden checks: 46; review EDMA: 20; Jana completion: 192.
- Focused API/Unicode/remediation checks: 40 tests; recovery/OAuth/distribution:
  43 tests and 8 subtests.
- Final combined focused verification after recovery review: 70 tests and
  8 subtests passed.
- Complete suite: **419 passed, 1 skipped, 37 subtests passed**, 380.93 seconds.
  The suite includes scientific AST guards, OAuth download permission handling,
  candidate consistency, workflow state and current 2.0.5 UI regressions.
- `git diff --check` passed. Staged source review found no credential-shaped
  values, scientific dataset files, temporary logs or generated binaries.

`capture_autosolve_errors_205.py` generates controlled actual Qt windows at
100%, 125% and 150% scaling. The images cover phase search, not started,
charge-flipping result, prediction, review, refinement, cancellation, scientific
failure, missing UNIVERSAL, network failure, authentication and access denial.
They are explicitly marked synthetic, use synthetic structures/metadata, and
perform no submission or Jana publication. Representative initial/result/error
and high-DPI review images were inspected. Earlier execution and viewer reports
retain their own before/after evidence; these new captures are not claimed to be
screenshots of a live successful scientific run.

## Remaining acceptance and scope

The public catalogue was verified live. No paid inference, browser login,
real Jana handoff, frozen-executable validation or physical multi-monitor test
was performed in this remediation. Native foreground behavior still needs
real-machine acceptance; offscreen Qt cannot certify Windows focus ownership.
Failed launch returns to Jana/caller rather than automatically reopening the
Wizard. Incoming settings are preserved, and retry does not reset them.

Existing older script fixtures were repaired where they assumed that model
identity alone defined the scientific stage, or supplied no corresponding Jana
model while expecting a handoff-ready candidate. No production artifact guard
was weakened. The pinned scientific AST check explicitly exempts the changed
GUI launcher, while numerical and Jana file-protocol functions remain pinned.

Version remains 2.0.5. No release, tag, executable publication, force-push or merge
to main is part of this task.
