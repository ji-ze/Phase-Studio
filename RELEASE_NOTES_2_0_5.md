# Phase Studio 2.0.5 — unreleased

All changes after the published `v2.0.4` tag belong to this development version.
The runtime, package metadata, window/version displays and future Windows build
version resources derive from `phase_studio/version.py` (2.0.5). No new public
release, tag or binary has been produced by this version change.

## Changes since 2.0.4

- Stable Jana2020 Wizard geometry across all three pages, disclosure changes,
  asynchronous model-list updates and validation warnings. Preserve user resize
  and position; clamp restored windows to the available screen.
- Compact model and authentication controls, responsive map-feedback panels,
  shared header/footer geometry and version/update controls in the header.
- Shared scientific typography for Qt labels, table headers, tooltips, copied
  rich summaries and embedded Matplotlib charts. Preserve machine-readable names.
- Refined seven-tab HKL Advanced Diagnostics: compact geometry, balanced counts
  and crystal symmetry, explicit resolution range, phase/uncertainty provenance,
  concise overlap distribution and readable availability selection.
- Context-sensitive completeness/overlap resolution tables, discrete overlap
  group-size categories, percentage presentation and constrained chart layout.
  Reuse authoritative group membership; omit ambiguous per-bin group counts.
- Expanded regression and DPI evidence for Wizard and scientific HKL interfaces.
- Repository hygiene and documentation follow-ups since the 2.0.4 release:
  curated public screenshot evidence, contributing guidance and integration audit.

Scientific parsing, symmetry, resolution/coverage algorithms, powder grouping,
original observations, Superflip/SharpED/EDMA calculations, export schemas and
Jana2020 handoff are unchanged by these UI refinements.

Prior 2.0.4 acceptance reports and build artifacts keep their historical names.
The newest final-polish report and captures are labelled 2.0.5. Local workshop
drafts remain drafts; this version designation does not publish them.

## Acceptance and publication status

See `docs/HKL_ADVANCED_FINAL_POLISH_2_0_5.md` for final verification and limits.
Physical-monitor/native Jana acceptance and new distribution builds are separate
from this source/UI task. The latest published GitHub release remains 2.0.4.
