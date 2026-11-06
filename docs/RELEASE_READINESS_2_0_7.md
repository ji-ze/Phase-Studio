# Final scientific correction and release acceptance

The starting accepted source is `9458722d48f1ed0a0e198ff95635f7897782559e`
(860 passed, four skipped, 37 successful subtests). Those are historical counts,
not the result for the changes below. Final exact-commit results, package hashes,
screenshots and the structured verification matrix accompany the development
acceptance archive and PR #21. PR #21 remains draft. No merge, tag or publication
is authorized. The release verdict remains **NO-GO** until the outstanding
interactive and production-signing gates are accepted.

## Exact native powder membership

The installed 32-bit Superflip identifies 794 groups containing 3,796 Selexipag
records. The double-precision geometric estimate identifies 794 groups containing
3,795. The differing member is **(-22, 2, 5)**, native group 329; its adjacent
partner is **(16, 2, 8)**. Both measured widths are 0.0144 degrees 2θ,
wavelength 0.39986 Å, separation factor 0.2. The actual serialized calculation
cell is (37.961900, 6.110100, 22.473900, 90, 98.3300, 90), which must not be
replaced with the differently rounded original reference-CIF cell.

An independent 60-decimal adjugate reciprocal-metric and trigonometric-series
oracle gives 2θ values 15.6278381634338395024642673931766871305735443357219001434126
and 15.6307189506189282118676434419196418325617168994203838562077 degrees.
Their separation is 0.0028807871850887094033760487429547019881725636984837127951,
versus a criterion of 0.00288: **7.871850887094033760487429547019881725636984837127951e-7
degrees above the boundary**. Double precision correctly separates this pair
under the mathematical criterion. Native execution includes it.

Native executable SHA-256:
`2933a0c5245f4addc6365f26e5e4ca73a113e875a5901587db2bdd201a80bf3e`,
version 09/21/20 10:33. The publicly available Fortran source archive has SHA-256
`2d91760abd1bbf1522afc00282ad2151dfaa3a6d8360906ee94cccd83ec69c3f`
and identifies itself as **2014**, not the installed 2020 version. Its native
REAL cell/reciprocal metric, LU inversion, scalar products and Bragg intermediates
use single precision with some double intermediates. Adjacent-angle grouping is
transitive; strict separation `threshold < gap` means equality overlaps.
Degree/radian conversion and serialization were examined. Forty independent
precision/promotion variants reproduce the boundary inclusion in some cases,
but none establishes full membership equivalence with the installed binary.
The exact compiler/intermediate behavior of that binary is therefore unresolved.
No variant was selected merely to force counts.

A separate two-record native factor sweep brackets the input transition in
[0.19994048029184341, 0.19994048032164574]. This is an observed input-factor
interval, **not** a rigorous bound on native angle differences: factor and width
rounding intervene. The evidence's nominal `native_gap_estimate_bracket` must
not be interpreted as an exact native angle. The independent high-precision
mathematical decision remains visibly different.

Production powder feedback now consumes the **actual completed Superflip
expanded reflection table**, verifying every HKL, widths, cell, wavelength,
factor, record counts and file hashes. No tolerance is widened and no count is
forced. The separation factor is now also forwarded to native input (previously
the native default could differ from the GUI setting), alongside the measured
wavelength. Expanded logging is required. Unsupported, incomplete, averaged-over,
stale or changed tables fail with an actionable rerun error; no estimate is
silently substituted. Active powder feedback requires native Superflip execution.
The offline geometric estimate remains available, explicitly identified in
diagnostics. Stage statistics retain the grouping authority and provenance.

Fresh isolated native calculations establish exact execution membership for
all 4,690 Selexipag records (3,796 members/794 groups) and all 631 Ochlor records
(193 members/91 groups). Original pilot hashes remain unchanged. The new
`verify_native_overlap_207.py` independently extracts the native table, exports
every membership, checks every group before and after redistribution at mix
0, 0.25 and 1 for I/FWHM and F/FWHM, checks seven-decimal serialization against
its analytical rounding bound, and runs the corrected files through deterministic 20-cycle native
CF calculation. This is compatibility/conservation acceptance, not a rerun
of the historical reconstruction or evidence of chemical correctness.

## Reflection semantics retained

The prior actual FWHM/significance correction remains in force; see
`FWHM_SCIENTIFIC_CORRECTION_2_0_7.md`. FWHM is a measured width, never σ(I) or σ(F).
Finite nonnegative intensity with a valid measured width is retained; invalid
values are rejected by the established validation/filter policy. Zero intensity
can be valid. A positive significance cutoff without genuine uncertainty is
rejected explicitly. Genuine amplitude significance uses I/σ(I) = F/(2σ(F));
exported measured uncertainties keep their physical meaning. Uncertainty-free
exports use their supported representation or reject the request; no sigma is
invented. Widths survive powder processing unchanged.

The original 25-cycle evidence contains 4,690 original records and 4,413 legacy
written records. The corrected policy retains 4,690, restoring all 277 formerly
excluded records: 136 zero and 141 positive intensities. Their full inventory
is retained in prior read-only evidence. No numerical equivalence between old
and corrected reconstruction results is asserted.

## Integration and release boundaries

Eight real SharpED responses from earlier authorized jobs 1868–1875 remain the
inference evidence. This task submits **zero new jobs**. Frozen acceptance loads
all eight saved returned maps; replay is distinguished from a fresh service
request. Native EDMA/map exports and the Jana state authorities verify selected
map/model identity, sealed selection, second-run freshness, cancellation and
protocol preservation in isolated controlled projects. Loading a CIF or map
does not establish real Jana refinement acceptance.

An existing Jana process is present, but the accessible desktop is a virtual
640×480 WinDisc display, and no complete original refinement project is exposed
in the known evidence folders. Actual interactive Jana launch/return/refinement
remains **UNVERIFIED**. The real Sign in button was exercised with the genuine
OAuth worker; opening the default browser failed in this environment before
callback or token exchange. No live credential was replaced. Browser SSO and
reauthentication remain **UNVERIFIED**, rather than a simulated pass.

Real PySide6 frozen probes cover 100/125/150/200% scales and legal resource hashes.
These are offscreen captures. Physical/mixed-DPI monitors, full-window visual
inspection on that hardware, and a clean Windows VM remain **UNVERIFIED**.
Native Windows Credential Manager is checked using a unique disposable fixture
target with cross-process persistence and cleanup. Unicode/long-path and
nonadministrator execution have their own actual-binary acceptance driver.

That driver discovered a real ONEDIR Unicode-path defect after the first full
900/4/37 campaign: Qt's filename-based font registration returned no families
and silently selected Agency FB even though the bundled font existed. Loading
the unchanged original font bytes through Qt's data API corrects this boundary;
regression tests explicitly load the actual face from Czech/Chinese and
extended-length font paths. The failed campaign is preserved, and a new
exact-commit full campaign is required after the fix. The host's
`LongPathsEnabled` policy is disabled. Explicit extended-length (`\\?\`) font
file access is tested without changing that system policy; this does not prove
whole-application long-path launch. Native CreateProcess probes failed with
WinError 206/267, and an explicit-application probe timed out. Whole-application
paths over 260 characters remain UNVERIFIED. The environment driver reports
this missing prerequisite separately; its `passed` field describes available
checks, while `complete_path_acceptance` remains false on this host.

The subsequent `cfe1d92` full campaign recorded 902 passed, three skipped and
one native-fixture setup timeout; it is not accepted as a passing campaign.
The handwritten unphased Fourier fixture was replaced by the production input
writer's explicitly seeded CF calculation, keeping the original timeout and all
exact membership/conservation assertions. Reflection-format probes likewise use
CF for unphased input and Fourier only when explicit phases are supplied.
The earlier stall is preserved as a native test-producer limitation, not claimed
fixed inside the vendor executable. Final acceptance requires another complete
suite and all authorities on the final source, without retrying failed tests.

A further actual native handoff in a Czech/Chinese directory exposed loss of
Unicode characters in Superflip's absolute input argument (native exit 2).
EDMA in that same directory had succeeded. The `d4b2f69` campaign was stopped
and preserved rather than counted as final acceptance. GUI and wrapper map
conversions now pass their existing ASCII input filename relative to the exact
working directory; local incoming wrapper inputs likewise address the original
file relatively. No project, dataset or original input is renamed. Native
regressions cover real EDMA/model transfer, m80/m81 density parity, legacy
conversion and preservation of the original input. All 196 existing Jana
authority checks remain intact. This establishes Unicode-directory support for
the tested ASCII basenames; arbitrary non-ASCII native input/output basenames
remain unverified.

`SIGNPATH_2_0_7.md` records the helper-before-embedding architecture, narrow nested
artifact configurations, final Authenticode/Ed25519 checks and exact missing
owner configuration. Production signing remains **UNVERIFIED**; local packages
are unsigned development artifacts. Existing production key ID and released
2.0.6 trust/helper sources remain unchanged. An ephemeral-key updater acceptance
fixture is isolated from production trust and is never distributed as production.

Generated terminology inventories are preserved byte-for-byte in a deterministic
8,038,166-byte archive (SHA-256
`ad08e33db66d1b9a97c5269d44a86a65630d98cc8fab0a01c6b3554b8c2ee7ad`).
Their immutable Git snapshot, raw/Git hashes, restoration rules and generator
instructions are retained under `reviews/2.0.7-ui-terminology/`. Historical
terminology findings are separated from current resolved scientific defects;
remaining editorial acceptance is not declared complete.

The baseline outer development ZIP is preserved and hash verified. Its loose
standalone executable was already absent during this task's initial inventory;
the original bytes remain in the unchanged ZIP and accepted build cache. No
cause for that pre-existing absence is asserted. Original experiments, saved
responses, previous builds and `docs/workshop/` are preserved.
