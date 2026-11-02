# Run provenance and scientific logging audit, 2.0.7

New runs produce a concise `log.txt`, full timestamped `diagnostic.log`,
structured `events.jsonl`, atomic `run_manifest.json`, readable `summary.md`,
`cycle_metrics.csv` and `checksums.sha256`. Session records live under
`provenance/<run_id>/`; root manifests are the latest snapshot. Each event has
run ID, session ID/sequence, UTC millisecond timestamp, cycle, component, severity
and type. Unknown values are JSON null with status/reason, never invented zero.

The Execution log toolbar exports a local sanitized metadata-only ZIP. It
removes exact local paths and remote job/request identifiers, redacts registered
credentials and secret fields, and recalculates checksums after sanitization.
It includes no scientific CIF/HKL/map arrays. Local full provenance remains
private and contains paths and scientific metadata needed to identify inputs.

## Gaps and their causes

Previously configuration was printed selectively in free text, paths stood in
for file identities, implicit GUI/preset/persisted overrides were not recorded,
and remote model names did not establish checkpoint identity. Cycle messages
interleaved across workers, feedback was summarized by an ambiguous scalar,
and an atom count did not distinguish reference context from initialization.
These gaps prevented reliable reconstruction of the actual calculation.

The observer now records effective RunConfig, requested-versus-resolved
differences, observed setting origins, original/current file SHA-256 identities,
native executable identities, actual launch arguments and generated Superflip
keywords. Setting origins distinguish pre-load application defaults, persisted
settings, preset changes and user/UI changes where observable. Generic UI
signals alone explicitly do not prove a human actor. Configuration observation
does not set controls or change defaults, ranges or persistence.

Actual parser observations reconcile accepted/unparsed/origin-excluded lines;
existing duplicate merging, holdout exclusion and the existing writer filter
are recorded separately. Actual upload file bytes and multipart payload bytes
are hashed when assembled, not inferred from a later mutable file. Remote
checkpoint identity is unknown unless explicitly returned by the server, and
then is labelled server-supplied rather than independently byte-verified.

Completed results and completed cycles are separate events. A cycle is complete
only at the existing continuation-finalization authority. Cancellation/failure
and incomplete cycles remain explicit. Reopening preserves earlier events with
new session IDs; damaged JSONL tails are archived verbatim before recovery.
Selection, handoff request and handoff completion are separate observations;
none establishes that Jana performed a later refinement.

## Historical evidence: 134 sites and reference roles

The supplied original reference CIF contains 134 asymmetric-unit sites: 70
heavy sites and 64 H, including two independent molecules. The old message
`Initial atomic model: 134 sites` counts reference-context sites and cannot
establish a first-cycle phasing seed.

The actual first generated input has `perform AAR`, `referencefile`,
`randomseed AUTO`, `bestdensities 1 symmetry`, and no `modelfile`.
Superflip's documented roles are distinct: modelfile initializes phases;
referencefile aligns the resulting density to a reference frame. Therefore
this was reference-assisted output alignment, with automatic random phase
initialization rather than proven initialization from 134 supplied atoms.
The reference alignment also affects the map subsequently consumed by SharpED;
it is not merely a viewer effect. `bestdensities 1 symmetry` is not
reference-ranked density selection. Later actual modelfile/referencefile lines
are recorded per cycle; reference-backed recommendation is not independent
validation. [Superflip manual, sections 4.1.27, 4.1.37 and 4.1.39](https://superflip.fzu.cz/download/superflip_user_manual.pdf).

## Historical evidence: 4,690 versus 4,413 reflections

The original reference embeds 4,690 unique HKL. The actual first written input
contains 4,413: 277 absent records comprise 136 zeros and 141 small positive
values. Applying the existing `value / fifth_field >= 2` writer gate reproduces
the exact HKL set. The minimum kept ratio is 2.0689655 and the maximum omitted
positive ratio 1.96410256. This establishes a compatible threshold interval;
the historical effective numeric setting was not serialized, so exactly 2 is
not independently proven. A resolution cutoff cannot explain the pattern.

**Critical separate scientific finding:** the fifth field is FWHM in this run,
yet the legacy writer applies its value/fifth-field gate irrespective of mode.
FWHM is a peak width, not sigma(I); the generated header also calls it sigma(I).
This is not a valid intensity significance statistic. No filtering algorithm
or historical input was silently changed in this logging work. It requires
a separate evidence-based scientific correction before release approval.
[IUCr powder dictionary, peak width definitions](https://www.iucr.org/__data/iucr/cif/dictionaries/cif_pd_1.0.1.dic.pdf).

Later written counts vary from 4,417 to 4,434 as changing intensities cross this
legacy filter. HKL entering a later written file must not automatically be
called missing-original-reflection completion.

## Exact feedback statistic and changes above 1,000%

For each overlap group, let T be the sum of observed member intensities and
m the clipped mix in [0,1]. A member's new intensity is

`I_new = T * ((1-m) * I_old/T + m * I_map/sum(I_map))`.

The existing zero-total/fallback branches remain authoritative. For members
with `I_old > 1e-12`, calculate `100 * abs(I_new-I_old)/I_old`. Average these
member percentages within each group, then average the available group means
with equal group weights. That is `avg_intensity_change_per_group`; it is not
a signed change, a mean over all reflections, or a change in group totals.
No usable group yields unavailable, not zero. Groups preserve total intensity
to floating-point tolerance. Weak denominators readily yield values over
1,000% while the total is conserved; the statistic is not an accuracy score.
For amplitude modes the existing intensity conversion is used first.

Diagnostics retain absolute and relative changes with declared denominators,
modified counts, exclusions, conservation residuals and source/target cycles.
After-cycle-N feedback feeds cycle N+1; both result families for N+1 use that
input lineage. Legacy metrics are separately labelled, not fabricated into
full per-reflection histories.

The read-only replay of all 20 saved transitions checked 88,462 persisted
reflections against the unchanged correction routine. Maximum difference was
4.9997705531268366e-8 (seven-decimal file rounding bound 5.1e-8), maximum group
conservation residual 4.547473508864641e-13. All saved legacy group means match
metrics.csv at the target cycle. Original files were hashed before and after.
This is an audit of saved artifacts, not evidence of a newly executed paid run.

## Parameters and metric meanings

Generated keywords establish actual cell, space group, composition, algorithm,
repeat/maxcycles, seed, delta, missing-reflection rule, reference/model roles
and output input format. RunConfig establishes workflow, SharpED model display
selection, EDMA controls and feedback gates; native invocation and request
assembly establish what was actually sent. Application version, git identity
when available, source digest, runtime executable and native hashes are separate
from missing build/release/checkpoint metadata.

XPLOR blending records the existing factor conversion: effective factor f is
the reciprocal of the GUI inverse value clipped to [0.001,1]. Where that
branch applies, `rho = ((f-1)*rho_previous + rho_new)/f`. Other reconstruction
branches may bypass it; a recorded parameter alone does not prove application.

F0.5 is the precision-weighted peak-matching F score, not a phase figure of
merit. Matched-peak RMSD is in angstrom and excludes unmatched reference sites;
TP/FP and counts must accompany it. Phase agreement is the implementation's
weighted reference phase-agreement statistic, not an R factor. Holdout R/CC,
OMIT map correlation and reference-backed scores retain distinct definitions
in `phase_studio/map_quality.py` and the existing validation-profile authority.
None of these metrics or candidate ranking is recalculated by the logger.

## Reproducibility limits and verification

Automatic random seeds cannot be recovered retrospectively. A display model
name does not establish immutable remote weights. Unknown historical effective
settings, build metadata and remote numerical environment remain unavailable.
File hashes establish identity, not bitwise reproduction across native/remote
platforms. Provenance is not a new execution-resume authority.

Tests cover interruption/resume identity, partial completion, atomic manifests,
hashes, malformed-tail recovery, parseable sanitized exports and credential
redaction. Existing scientific AST guards still compare parser, filter, writer
and numerical bodies; exactly three read-only parser observation calls are
normalized and individually pinned. The unchanged saved-file feedback replay
and existing scientific goldens provide numerical checks. No diagnostics path
starts a scientific executable or adds a SharpED request.

See `RESULT_SELECTION_FEEDBACK_2_0_7.md` for cycle lineage and historical file
comparisons and `STRUCTURE_ALIGNMENT_2_0_7.md` for presentation-only alignment.
