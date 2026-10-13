# Phase Studio 1.0.9 performance audit

Audit date: 2026-09-14. The baseline was captured from commit `5dee420`
before source changes. Optimized measurements use the same machine, Python
environment, executables, and fixtures. Times are wall-clock measurements from
`time.perf_counter()` unless stated otherwise.

## Central result

The external programs and server remain the dominant cost of realistic work.
Phase Studio did contain four measured sources of avoidable latency: a fixed
external-process monitor delay, a duplicate 10.77 MB map read during phase
recycling, redundant rendering within one GUI queue batch, and the initial
two-second SharpED polling interval. All four were reduced without changing
scientific inputs, calculations, or outputs.

An actual 12.33 MB EDMA stage measured 2.535 s after the changes: 1.619 s in
EDMA and 0.916 s (36.1%) in Phase Studio map normalization, input/output I/O,
and structure processing. This is the most Phase Studio-heavy measured local
stage. It is not representative of a full run dominated by Superflip or a
remote SharpED job. A component-composed Superflip + EDMA path using the same
fixtures is approximately 7.37 s: 5.97 s external work and 1.40 s Phase Studio
work, or about 19%. The Phase Studio share includes 0.40 s map assessment and
0.92 s of required EDMA preparation/postprocessing.

An authenticated SharpED run of the 10.77 MB fixture completed in 19.232 s:
19.200 s was external computation/network waiting and 0.033 s was Phase
Studio-owned work, or 0.2%. For this representative remote stage, Phase Studio
overhead is negligible. The server does not publish an internal completion
timestamp, so its actual compute time cannot be separated from the deliberate
interval between status requests; the client request, probe, and wait spans are
reported separately instead.

## Before and after

| Measured operation | Baseline | Optimized | Saved | Evidence |
|---|---:|---:|---:|---|
| Monitor a 30 ms silent child process, median of 15 | 0.20384 s | 0.06173 s | 0.14210 s (69.7%) | Direct child median was 0.06151 s; remaining monitor cost was 0.00023 s |
| Compose one recycling map, 10,765,379 bytes and 3,000 reflections, median of 3 | 1.28938 s | 0.85354 s | 0.43584 s (33.8%) | Output SHA-256 values were identical |
| Peak Phase Studio working set during that composition | 167.55 MB | 160.75 MB | 6.79 MB | Separate fresh processes, Windows peak working set |
| Worker message to visible GUI log, median of 20 | 0.1310 s | 0.0432 s | 0.0878 s (67.0%) | Maximum fell from 0.1947 s to 0.0678 s |
| SharpED completion detected when ready at 0.1 s | 2.0 s | 1.0 s | 1.0 s | Exact status schedule simulation |
| SharpED completion detected when ready at 0.6 s | 2.0 s | 1.0 s | 1.0 s | Exact status schedule simulation |
| SharpED completion detected when ready at 1.1 s | 2.0 s | 2.0 s | 0 s | Long-job interval remains unchanged |
| Public model request before a DEFAULT run | 2 calls | 1 call | about 0.101 s | Live request median 0.1006 s; immediate preflight result is reused |
| Authenticated SharpED client overhead, 10.77 MB input | uninstrumented | 0.033 s of 19.232 s | exact split now available | 0.2% Phase Studio-owned; 19.200 s external |

The real synthetic Superflip fixture took 4.415 s at baseline and 4.352 s
after the process-monitor change. Its 12,334,504-byte best-density map had an
identical SHA-256. Superflip computation itself was not altered.

## Measured stage breakdown

The following entries are direct component measurements plus one authenticated
SharpED stage. They must not be summed into a claimed single full-window run.

| Stage | Calls | Wall time | Ownership and interpretation |
|---|---:|---:|---|
| Local Superflip/EDMA preflight | 1 | 0.000171 s | Phase Studio; negligible |
| Live public SharpED model discovery | 3 | 0.0877-0.1223 s | Network; median 0.1006 s, 11 models, server default `koala 4.0` |
| Parse and merge 1,330 HKL records | 30 | 0.00202 s median | Phase Studio |
| Build immutable validation context | 30 | 0.07111 s median | Phase Studio; reused across cycles |
| Write prepared HKL | 30 | 0.00394 s median | Phase Studio |
| Generate Superflip input | 30 | 0.00096 s median | Phase Studio |
| Real Superflip process fixture | 1 | 4.35190 s | External process, including process startup |
| XPLOR map write, 96 cubed | 1 | 0.319 s | Phase Studio file I/O |
| XPLOR map read, 10.77 MB | 3 | 0.3482 s median | Phase Studio file I/O |
| Metrics after the map is loaded | 3 | 0.0546 s median | Phase Studio Fourier work |
| Complete map assessment from file | 3 | 0.4010 s median | Phase Studio; one read and one FFT |
| Correlate two 10.77 MB maps | 3 | 0.7334 s median | Phase Studio; two required reads |
| Recycling Fourier composition | 3 | 0.8535 s median | Phase Studio; optimized from 1.2894 s |
| Real EDMA stage total, 12.33 MB map | 1 | 2.535 s | 1.619 s external, 0.916 s Phase Studio |
| Authenticated SharpED total, 10.77 MB map | 1 | 19.232 s | 19.200 s external, 0.033 s Phase Studio |
| SharpED upload transfer | 1 | 0.318 s | External network transfer |
| SharpED server processing and polling | 1 | 18.666 s | External aggregate; child spans below are included, not additional |
| SharpED polling interval waits | 9 | 15.994 s total | External server wait plus bounded detection interval |
| SharpED compatibility probes | 9 | 1.951 s total | External network/protocol compatibility |
| SharpED status requests | 10 | 0.718 s total | External network/protocol status checks |
| SharpED download transfer | 1 | 0.216 s | External network transfer; 10,765,363-byte result |
| Empty plot redraw | 3 | 0.0201 s median | GUI thread |
| Structure redraw | 3 | 0.0285 s median | GUI thread |
| One completed result with a 31-atom CIF | 3 | 0.1037 s median | GUI thread; parsing and rendering |
| Write reports for 1 / 10 / 100 results | 3 each | 0.0011 / 0.0042 / 0.0349 s median | Phase Studio; one durable write per completed cycle retained |
| Open and immediately close result selector for 1 / 20 / 100 candidates | 3 each | 0.0485 / 0.0638 / 0.1022 s median | GUI thread; selected preview is loaded lazily |

The five largest Phase Studio-owned costs in the measured fixtures are EDMA
normalization/postprocessing (0.916 s), recycling composition (0.854 s),
two-map correlation (0.733 s), complete map assessment (0.401 s), and completed
result parsing/rendering (0.104 s). Only the duplicated part of recycling
composition was removable. The other costs produce required scientific data,
required EDMA input, or visible results.

## Execution trace and ownership

`Run phasing` collects and validates configuration on the GUI thread. The
shared preflight then checks only the programs and service required by the
selected workflow. Local executable checks are filesystem probes and take
less than a millisecond. The SharpED check performs one public model request;
its result now supplies the concrete server default to the immediately
following run.

The worker parses and merges HKL data, builds the reference and validation
context once, freezes any holdout set, and writes the observed work HKL once.
Each ordinary cycle then generates Superflip input, launches Superflip, checks
the output, exports any requested maps/reflections, optionally runs the OMIT
Superflip branch, runs EDMA when enabled, assesses the map, prepares and sends
the SharpED map, optionally runs EDMA on the returned map, applies map feedback,
writes one result/report set, and enqueues presentation updates. The worker
does not wait for GUI rendering before beginning the next scientific cycle.

Phase recycling reuses the prepared reflections and validation context. Its
cycle boundary contains the required returned-map read, Fourier coefficient
calculation, observed-amplitude composition, XPLOR write, correlation, metrics,
and report write. The duplicate read formerly inside Fourier prediction was
the only removable boundary cost found.

`Continue run` reuses its existing immutable state and starts a new timing
report for the continued portion. Graceful stop finishes the active cycle and
then closes the report; immediate cancellation retains the existing 50 ms
process check and 200 ms SharpED cancellation check. Both paths keep worker
threads from touching Qt widgets.

The standalone and Jana2020 phase-recycling paths reach the same worker. The
Jana2020 Superflip-only and Superflip + SharpED wrapper paths stay separate and
lightweight. They do not import the full application or Matplotlib. Only phase
recycling opens the full window.

## SharpED network and polling

Upload is followed by a status request immediately, with no initial sleep.
For the default configured interval, status requests now occur at approximately
0, 1, 2, 4, 6 seconds and then every two seconds. Previously they occurred at
0, 2, 4, 6 seconds. This adds at most one early status/download-probe pair and
does not increase sustained load during a long job. Download begins immediately
when completion or downloadable output is detected.

The authenticated run submitted job 60 using the catalog default `koala 4.0`.
It made 10 status requests, 9 compatibility probes, and 9 interval waits. No
retry occurred. Upload took 0.318 s, the combined server-processing/polling
window took 18.666 s, and download took 0.216 s. The interval waits totaled
15.994 s. Because the server exposes state only when asked, the exact instant
of server completion is unknowable; detection latency is bounded below two
seconds after the accelerated initial window.

The restored one-server contract remains unchanged: every route is based on
the configured server, whose default is `https://jana.fzu.cz`. No second host,
route migration, authentication change, payload change, retry change, or map
value change was introduced.

The client uses `urllib`, so individual requests do not use an application-held
persistent connection pool. Each incomplete status also performs the existing
download probe because deployed servers may expose output before changing the
status field. The live run measured 1.951 s across the nine probes and 0.718 s
across ten status requests. Changing transport reuse or removing the deployed
server compatibility probe would change a restored protocol path, so it was
rejected. The profiler counts these waits as external network/server time.

## Wait inventory

| Wait | Classification | Action |
|---|---|---|
| Main GUI queue timer, formerly 200 ms | Conservative but reducible | Changed to 50 ms; bounded 250-message drain retained |
| External-process no-output sleep, formerly 200 ms | Unnecessary | Replaced with queue wakeup and native EOF/exit observation |
| External-process 50 ms queue timeout | Necessary | Retained for stop/deadline checks when a child is silent |
| External-process 5 s terminate/kill waits | Necessary | Error-only cleanup bounds; retained |
| External-process 2 s reader join | Necessary | Bounded pipe cleanup after exit; retained |
| SharpED configured poll interval | Externally constrained | Only the first two waits are capped at 1 s; long-job setting retained |
| SharpED internal 200 ms sleep slices | Necessary | Keeps immediate cancellation responsive while honoring the poll deadline |
| Jana wrapper `proc.wait()` | Externally constrained | Wrapper must remain until its visible command finishes; output drains concurrently |
| Jana Wizard 100 ms model-result timer | Necessary | Nonblocking result delivery from its network worker; retained |
| Zero-delay Qt callbacks | Necessary | Defer modal opening/layout until the current event turn ends |
| 250 ms startup model refresh callback | Necessary and nonblocking | The request itself runs in a worker thread; no startup delay is imposed |
| 400 ms post-handoff quit callback | Deliberate UI delay | Allows the completion state to display; unrelated to scientific progress |

No runtime `QThread.sleep`, `QThread.msleep`, `waitForFinished`, `communicate`,
or unbounded GUI-thread process wait was found.

## GUI, queue, plots, and selection

All map parsing, FFT work, external processes, server operations, validation,
feedback, and report writes remain on the scientific worker. The public
SharpED preflight request is synchronous after the user clicks Run and measured
88-122 ms on the available connection; it is the only measured GUI-thread
network event above 50 ms. Moving the dedicated remediation flow to an
asynchronous state machine would add material correctness risk for a one-time
roughly 0.1 s request, so it was left unchanged. A network failure can still
block up to its preflight timeout and remains a known responsiveness limit.

The main queue already drained up to 250 messages per tick, so backlog growth
from normal progress traffic was not found. The avoidable cost was rendering
after each item in the same drain. Plot, structure, and action updates are now
marked dirty and applied once after each bounded batch. In a regression fixture
containing two structure updates, two validation updates, and two log messages,
each of the three render/action functions ran once.

Plots are not redrawn for ordinary progress messages. The result selector
constructs candidate rows but parses and renders only the selected candidate.
No eager all-candidate map or CIF loading was found. The 100-candidate dialog
crossed 100 ms, but changing widget construction was not justified because the
preview path is already lazy and candidate counts are normally much smaller.

## File I/O, Fourier work, and cycle boundaries

Map assessment calls `read_xplor_map` once and `compute_map_quality` performs
one FFT whose coefficients feed amplitude R, amplitude correlation, phase,
triplet, entropy, and other diagnostics. No per-metric reload or repeated FFT
was found. Validation inputs, free/work masks, triplets, reference phases,
reflection parsing, symmetry setup, and reference atoms are prepared once and
reused within the run.

The recycling composer used to load a map and then call the path-based Fourier
helper, which loaded the same map again. It now calls an in-memory helper. The
serialized output is byte-for-byte identical, composition is 0.436 s faster on
the fixture, and peak working set is 6.8 MB lower.

EDMA requires a strict normalized XPLOR copy in its work directory. On the
12.33 MB fixture, EDMA-related Phase Studio work was 0.916 s and is therefore
visible, but removing that normalization could change EDMA acceptance or
results. Required intermediate maps are retained. Map correlation still reads
both maps; retaining full maps across stage boundaries would increase lifetime
and stale-cache risk, so it was not changed.

Metrics CSV and the quality report are written once after each completed
result. Even 100 accumulated results took only 0.035 s. This durability point
was retained. SharpED's small diagnostic log is rewritten as status changes
arrive, but its volume and measured request cadence did not justify a change.
No complete-file hashing occurs in the normal scientific workflow.

## Startup and memory

Five fresh optimized processes measured standalone import at 0.528 s median,
window construction at 0.178 s median, and usable state at 0.706 s median;
parent-observed process wall time was 0.833 s. The pre-change run measured
approximately 0.40 s import, 0.16 s construction, 0.56 s usable, and 0.69 s
process wall. No startup optimization was retained: the variation was in module
import timing, the added profiler is disabled by default, model discovery stays
asynchronous, and window construction did not expose a removable delay.

The standalone window used about 132.5 MB RSS with a 132.8 MB peak in a fresh
process. The Jana wrapper imported in 0.043 s median in the main measurement
(0.101 s parent-observed process wall) and used about 26 MB; the installer
imported in 0.082 s median (0.145 s parent-observed wall) and used about 37 MB.
Neither lightweight path loaded the full application or Matplotlib. Recycling
composition peaked at 160.75 MB after the fix versus 167.55 MB with the old
double-read behavior. No retained candidate-preview map arrays or leaked
figures were found in the inspected ownership paths.

## Representative configuration coverage

| Configuration | Coverage |
|---|---|
| A. Superflip only | Real installed Superflip process with fixed synthetic input; 4.352 s optimized, output hash identical |
| B. Superflip + EDMA | Real installed Superflip and EDMA components; actual EDMA split 1.619 s external / 0.916 s Phase Studio |
| C. Superflip + SharpED | Real Superflip component plus authenticated SharpED timing; SharpED was 19.200 s external / 0.033 s Phase Studio |
| D. Superflip + SharpED + EDMA | Authenticated SharpED output was accepted by real EDMA; the random fixture produced 24,768 maxima and its required symmetry merge was stopped after exceeding one minute |
| E. Multi-cycle phase recycling | Full cycle path traced; 10.77 MB composition benchmarked before/after; one live server cycle measured |
| F. Holdout/OMIT validation | Frozen holdout preparation and metric tests covered; a full OMIT run would duplicate external jobs and was not submitted solely for benchmarking |
| G. Reference validation | Reference context and complete map assessment measured; profile-aware golden tests covered |

The synthetic Superflip fixture writes its accepted density as
`best1_perf.xplor` while the generated input names `perf.xplor`, so it was used
as a real process/scientific-output benchmark rather than claimed as a
successful full-window run. This limitation is kept explicit.

The synthetic random map is also unsuitable for timing EDMA after SharpED: the
real EDMA process emitted 24,768 maxima, after which the unchanged
symmetry-aware merge exceeded one minute. That merge is scientific behavior
and has quadratic worst-case work for a pathological peak set. The benchmark
process was stopped; no algorithm, threshold, or peak selection was changed.

## Profiler use

Set `PHASE_STUDIO_PROFILE=1` before launching Phase Studio. A completed,
stopped, or failed run writes `workflow_performance.txt` in its selected work
directory. Normal runs create no performance file and add no timing lines to
the Execution Log.

The report uses monotonic nested spans and separates external owners from
Phase Studio-exclusive time. It currently identifies total preparation,
Superflip, Superflip symmetry, EDMA, SharpED model discovery, SharpED upload,
SharpED status requests, compatibility probes, polling interval waits, SharpED
server processing/polling, SharpED download, map-quality assessment, recycling
composition, and report/CSV generation. Uninstrumented time remains
the exclusive portion of `Total workflow`, so the external and Phase Studio
totals still sum to measured elapsed time.

## Verification

Before optimization, all 17 scripts and 685 checks passed. After optimization,
the suite contains 18 scripts and 691 checks. It covers default-model reuse,
bounded early polling, single-read recycling composition, byte-identical
serialized maps, opt-in nested timing, queue redraw coalescing, process launch
and cancellation, the one-server API contract, and existing golden scientific
results.

The scientific regression result is unchanged: fixed Superflip output hashes
match, old/new recycling map hashes match, numerical map arrays match after
serialization, and the 33-check golden scientific core passes without changing
expected values.
