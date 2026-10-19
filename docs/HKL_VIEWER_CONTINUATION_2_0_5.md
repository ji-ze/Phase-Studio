# HKL and viewer continuation acceptance, 2026-10-19

The HKL tooltip was escaped twice: the global QWidget tooltip wrapper had
already produced a width-limited HTML document before the scientific-label
formatter escaped that document again. Scientific tooltips now preserve the
existing wrapper. Dynamic literal content is escaped once. Input integrity has
one concise summary and explicitly does not establish experimental validity.

Advanced Diagnostics uses the existing `hklAdvanced` settings authority with a
1050 × 620 logical default and a deferred native-frame clamp. Its seven tabs
remain independently scrollable. Completeness uses the existing
`hklCompleteness/windowRect` and splitter settings, a 1400 × 950 default, and
the same native-frame clamp. Two-panel charts stack below 1100 logical pixels;
the overlap summary wraps to two columns. Short graph viewports scroll rather
than discard labels. The bin table reserves six rows using actual Qt metrics.

Reflection search builds a presentation-only HKL index off the GUI thread,
searches all parsed records, reports the complete match count, and displays at
most 200 rows in original order. Revision checks discard stale results. TSV
copying uses selected rows, visual column order and stored numeric values.
Unknown uncertainties remain unavailable; powder HKL counts are not claimed
to represent independently resolved experimental peaks.

The shared Camera button paints a vector chevron in separately reserved space.
The selector's control groups wrap instead of eliding camera/representation
labels. Short candidate-family headings and a one-third default table share
leave more readable evidence beside the viewer while preserving user settings.
The EDMA composition tooltip is plain, concise explanatory text; an explicit
Details dialog provides copyable candidate/source/cycle/threshold, site counts
and output hashes. The execution window's ordinary Jana workflow says
`Select result for Jana2020`; the existing selector confirmation remains the
handoff authority. Full input paths are copied deliberately through a context
menu instead of appearing in an obstructing hover tooltip.

## Scientific parity

Reports from the committed baseline and current presentation code were compared
using the existing trusted local analysis cache. Both report objects and exported
JSON/CSV bytes were identical.

| Dataset | Parsed | d_min (Å) | d98 (Å) |
| --- | ---: | ---: | ---: |
| ochlor | 631 | 1.1990790613015834 | 1.1990790613015834 |
| 2int3total | 328606 | 0.7255092594101177 | 0.8161153076022714 |

ochlor JSON SHA-256:
`879b15909db922c026de74f9ad76cd1d59b526608b8d6980f703fb592d011d6d`.
ochlor CSV SHA-256:
`fa2161602823e0c4f18ce30f7f34af5defac4b633954cb53fb0561b770985a29`.
2int3total JSON SHA-256:
`1efc4d5e63920c382072bbd35904dee7d168fda3a3240233c5a62e757d29b90f`.
2int3total CSV SHA-256:
`900dbda297a2c8442a0c9b7398c4033744b22fffece8e46e25af250f6d865f3b`.

The scientific golden script passed 46 checks and Jana completion passed 195.
The full pytest run passed 515 tests and 37 subtests, with one opt-in test
skipped. Subsequent viewer-focused runs passed 70 regressions and 25 selector
tests, and the explicit Result Selection script passed all 72 checks. These
counts overlap and must not be added into one claimed unique test total.
Actual stored ochlor results were inspected across both sources, cycles 1–3,
representations, detached navigation and the available second threshold. Source
hashes and frozen handoff selection remained unchanged. No inference was run.

## Local evidence and limits

Actual offscreen Qt captures at 100%, 125% and 150% are retained only under:

- `build/acceptance-hkl-remediation-2.0.5/`
- `build/acceptance-hkl-completeness-layout-2.0.5/`
- `build/acceptance-viewer-remediation-2.0.5/`

Contact sheets index the unchanged original captures. Reduced-screen restored
geometry and footer visibility are asserted. A positive-coordinate synthetic
screen was tested; physical multi-monitor, negative-coordinate native screen
placement and a real interactive Jana waiting/return session are not claimed.
Short-screen graph panes require their visible vertical scrollbar. These tests
do not establish native-monitor acceptance or a new scientific handoff protocol.
