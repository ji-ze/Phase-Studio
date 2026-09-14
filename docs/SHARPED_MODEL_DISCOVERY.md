# SharpED model discovery: diagnosis and verification

> Historical diagnosis only. The current client intentionally uses the older
> single-host API until the production server is unified.

## Confirmed cause

Phase Studio used `GET https://jana.fzu.cz/sharp-ed/models`. That host still
returns an older catalog and `"default":"koala 2.0"`. The corresponding current
service endpoint, `https://sharped.fzu.cz/sharp-ed/models`, returns `koala 4.0`
as default. This is a difference between live server responses, not a cached
desktop response or a parsing-field mismatch.

Refresh fetched the older host again and truthfully received its old data, but
logged only “Models refreshed.” Restart restored the same server URL and fetched
the same host. DEFAULT was already resolved near execution in the two workflow
wrappers; it resolved to the default of the wrong host. It was not generally
bound to a release-time value during RunConfig creation.

There were also two hard-coded `koala 2.0` selections in the main GUI: the initial
selector and Recommended preset. These are now `default`. A saved concrete
selection remains explicit while available, including a deliberately selected
`koala 2.0`; its intent cannot safely be inferred from its name.

## Request and response evidence

Direct live probes during this task produced:

| Endpoint | HTTP | Models | Default | koala 4.0 | buzzard 2.0 |
| --- | --- | ---: | --- | --- | --- |
| `https://jana.fzu.cz/sharp-ed/models` | 200 | 10 | koala 2.0 | absent | present |
| `https://sharped.fzu.cz/sharp-ed/models` | 200 | 11 | koala 4.0 | present | present |

Both routes returned identical metadata with and without the supplied Bearer
header. Model discovery is public; a successful model response does not prove
that a token is accepted for upload. No documented harmless authenticated
verification endpoint was established, and no guessed route was added.

The current response schema is a JSON object:

```json
{
  "default": "koala 4.0",
  "models": [
    "koala 1.0", "koala 2.0", "koala 4.0",
    "viper 2.0", "viper 3.0", "viper 4.0", "koalaB 1.0",
    "agama 1.0", "agama 2.0", "buzzard 1.0", "buzzard 2.0"
  ]
}
```

This is a recorded response, not an application fallback. The model list and
default are read from these same fields at runtime.

The former client supplied `User-Agent: PhaseStudio-SharpED/1.0`, with no
Authorization header for discovery. The corrected request also supplies
`Accept: application/json` and `Cache-Control: no-cache`; it remains GET and
unauthenticated. urllib supplies its normal transport headers. Upload remains
`POST /api/user/sharp-ed/upload`, multipart form data with Bearer authorization.

The [web application](https://sharped.fzu.cz/sharp-ed) redirected to login.
Its authenticated frontend network configuration could not be inspected.
Therefore the exact request made inside an authenticated browser session is
unverified. The current host's [public metadata](https://sharped.fzu.cz/sharp-ed/models)
was verified directly and agrees with the reported web catalog. The
[older host's metadata](https://jana.fzu.cz/sharp-ed/models) reproduces the defect.

## State and restoration audit

| Consumer or path | Before | After |
| --- | --- | --- |
| `SharpEDServerClient.get_models` | Transient parsed result, permissive filtering | Validated immutable `ModelsResult`, shared per normalized server |
| Main GUI | Initial concrete selection; queue payload split default/list; independent combo reconciliation | Initial DEFAULT; shared snapshot; common reconciliation/status helpers |
| Main startup | Build UI, load settings, schedule model request after 250 ms | Same lifecycle, but legacy URLs migrate and existing live snapshots cannot be replaced by restored selection values |
| Main QSettings | `PhaseStudio/PhaseStudio`, `inputs/sharped_base_url`, `inputs/sharped_model` | Same keys; persist connection and selection intent, never authoritative metadata |
| Jana Wizard | Independent session combo and reconciliation; token included in model-cache key | Shared catalog and reconciliation; scheduling state keyed only by server URL |
| Wizard settings | `PhaseStudio/JanaSuperflipWrapper` key `model`; shared URL preferred over legacy `server_url` | Same selection persistence and shared/legacy URL loading, with URL migration |
| Jana handoff/config | `options.model` copied into `sharped_model` | Intent still copied unchanged; no early DEFAULT resolution |
| Main settings/config restoration | Generic widget assignment | Model assignment reconciles with available shared metadata; removed values become DEFAULT |
| Preflight | Separate transient call to the same HTTP client | Same shared catalog, optionally reusing a successful response from the last 15 seconds |
| Submission | Two copies of default resolution and `SharpED latest` fallback | One resolver in the shared client immediately before multipart construction |

No persisted server-default or catalog setting existed in the production paths.
The tests deliberately inject obsolete catalog/default settings to prove they
are ignored. The remaining model-related connection controls (API token,
timeout, server URL) do not supply model names. Repository literal searches
found no bundled full production model list: the reported list came from the
older server. Historical concrete literals remaining in tests are fixtures.

`ModelsResult` contains model names, default, raw JSON, fetch time, source URL,
and status. Publication replaces the complete snapshot under a lock. Views read
the shared snapshot without blocking on network requests. Delayed callbacks
from a different server are ignored. Reconstructed widgets consume the existing
snapshot, and a custom server never displays the former server's catalog.

Both selectors retain DEFAULT or an available explicit choice. Removed choices
become DEFAULT; `get_config()` synchronizes before reading the selector.
Concrete manual entry remains available, particularly after discovery failure.

On refresh failure, the previous valid snapshot is retained and marked cached.
No bundled fallback is injected. DEFAULT submission requires a fresh successful
response and fails rather than guessing. Explicit selections bypass default
resolution and are sent unchanged. Explicit Refresh always makes a new request.
Wizard setup and preflight may reuse recent successful metadata for 15 seconds;
failed or expired snapshots do not satisfy that reuse policy. DEFAULT submission
always refreshes, even within the reuse window.

## Live job acceptance and limitations

A small synthetic periodic XPLOR map (32 × 32 × 32, about 0.4 MiB) was used;
no user scientific data was uploaded. The temporary credential was injected
through a process-local environment variable and was not saved to QSettings.

| Check | Result |
| --- | --- |
| Main workflow DEFAULT through corrected production upload path | Live catalog resolved to `koala 4.0`; exact multipart field observed as `koala 4.0`; current host rejected upload with HTTP 401, `Invalid API token` |
| Existing upload path against original host, explicit `viper 3.0` | Authenticated upload, processing, and download completed; job 4574 |
| Original host, explicit `koala 4.0` diagnostic | Returned non-JSON upload response; job could not complete |
| Current-service authenticated DEFAULT completion | Not completed: supplied token was not accepted by `sharped.fzu.cz` |
| Main GUI startup and Refresh against live service | 11 models, DEFAULT selection, current default `koala 4.0`, both new models visible |
| Main GUI reinitialization/restart simulation | Reobtained live 11-model catalog and `koala 4.0` default |
| Wizard Superflip + SharpED and phase recycling selectors | Both displayed the same live 11-model catalog and default |
| Jana DEFAULT upload | Both normal entry points verified through real multipart code with mocked transport; current-service authenticated completion remains unverified |

The supplied token is demonstrably accepted by the older host and rejected by
the current host. The application must not silently fall back to the older host
or its historical default to hide an authentication failure. A token issued by
the current service is required to complete that acceptance step.

Live UI checks used Qt offscreen and isolated settings, not manual clicks in a
packaged desktop application. Restart was a fresh window and cleared runtime
state; no packaged executable was rebuilt or installed as part of this change.

## Simplification and regression verification

| Measure | Before | After |
| --- | ---: | ---: |
| HTTP model-discovery implementations | 1 | 1 |
| UI catalog reconciliation implementations | 2 | 1 |
| Workflow default-resolution implementations | 2 | 1 |
| Hard-coded main-GUI historical model selections | 2 | 0 |
| `SharpED latest` workflow fallback branches | 2 | 0 |
| Authoritative retained runtime catalog | None; independent widget/transient results | 1 snapshot per server |

The existing client/dataclass were extended; no manager class, framework, event
bus, dependency, or second API was introduced. Parsing, status formatting, and
selection reconciliation were extracted into small shared functions. The
Wizard's unused user-pick flag and signal handlers, repeated URL default, and
credential-bearing metadata request key were removed. The large GUI builders
and event handlers now delegate the relevant model logic; unrelated code was
not rewritten.

Production source changes: 235 lines added, 124 removed (net +111), across four
files. Most additions validate and synchronize state; the two UI modules
together have one fewer line than before. Nine tracked files are changed in
total, including tests and documentation.

The complete test suite passes: **868 existing checks plus 15 new unittest
cases**, across 13 test scripts. New coverage includes the exact production
catalog transition, A/B to B/C replacement, added models, changed defaults,
preserved/removed selection, actual multipart fields, both workflow entry
points, late settings restoration, reconstruction, restart, preflight/Wizard
sharing, invalid schemas, failed refreshes, custom servers, and bounded reuse.

Scientific code changed: **no**. Scientific golden outputs changed: **no**.
All 27 scientific-core checks and 83 map-exponent checks pass. Existing console,
Jana completion, Wizard geometry, wheel safety, UI hierarchy, metric legends,
model-format, requirements, and workflow-state regressions also pass. The
public-host upload size check follows the migrated host with its limit unchanged.
Map payload construction, exponent/inverse transforms, Superflip, EDMA, HKL,
OMIT, R_free, recycling, feedback, ranking, and Jana handoff algorithms are
unchanged. DEFAULT intentionally selects the current server model; that can
change the server's output and is the requested behavior correction.

Packaging/runtime/MSIX files are unchanged; packaged builds were not rerun.
The temporary credential is excluded from source, test fixtures, settings,
reports, and commits. The pre-commit literal credential scan passed: no matches
in the entire working tree (including ignored files, test outputs, and logs)
or the Git diff. The existing `.pytest_cache` required additional read access
for that scan; it was included successfully and was not used by these tests.
