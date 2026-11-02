# Validation of feedback, comparison and provenance, 2.0.7

## Automated checks

* Final complete suite: **666 passed, 4 skipped, 37 subtests passed**, 543.38 s.
  The four conditional skips remain unchanged. Tests were run with workspace
  temporary storage and Windows system access needed for DPAPI/file-lock tests.
* After the final visible-population correction, alignment/provenance/selection
  focused checks: **22 passed**, 13.03 s. A final provenance/alignment run including
  the added SharpED-method AST guard: **15 passed**, 4.62 s.
* Independent existing authority scripts: scientific core 46, Jana completion
  195, Autosolve orchestration 79, workflow states 141, Result Selection viewer
  72, review EDMA 20, displacement parameters 42; fullscreen script exit 0.
* Execution logging authority: all 16 checks passed. Detailed messages are
  retained in diagnostic.log while the normal log omits diagnostic-only traffic.

The complete suite ran before the final H/D/He presentation-count correction;
the focused population regression then verified that correction, including the
real-widget subprocess. The subsequently added AST test checks all SharpED
client class methods against pre-provenance commit a91d129, allowing exactly
four read-only observation calls. No numerical/network method body is exempted.

## Build and frozen acceptance

Fresh isolated-source combined-safe builds completed for standalone ONEFILE and
Jana ONEDIR. Both dependency/distribution audits report zero blocking problems;
the developer ZIP was extracted and all 407 files verified.

Both final executables passed `--packaging-acceptance` with
`PHASE_STUDIO_RESPONSIVE_ACCEPTANCE=1`, exit 0, `ok=true` and
`original_input_unchanged=true`. Every runtime Python source was byte-compared
with the build snapshot. Outputs remain local under ignored
`build/a207-final-verified/`; no unsigned test build is published as a release.

## Scientific and private-data evidence

The existing read-only recorded-feedback replay checks all 20 transitions and
88,462 saved reflection values against the unchanged correction routine within
seven-decimal file rounding. The structure inventory covers the reference and
50 saved CIFs and checks their/map-file hashes before and after. Original data
and original screenshots remain local; public examples use synthetic fixtures.

The full-cell visual check exposed a metadata mismatch: hidden hydrogen sites
were counted in the new matching population. The final code, test and capture
now agree on 280 displayed heavy reference sites and 280 reference matching
sites. Cycle-25 full-cell results show 252/280 and 260/280 positional matches;
molecular comparison shows 63/70 and 65/70. These are presentation diagnostics,
not chemical completeness or independent validation claims.

No scientific filter, reflection writer, correction formula, default, random
seed or validation-ranking rule was changed. No additional paid inference was
started. SignPath/signing configuration, public 2.0.6 and docs/workshop remain
unchanged.

## Remaining review gates

* Critical legacy FWHM input-filter defect documented in the
  [provenance audit](RUN_PROVENANCE_2_0_7.md); no silent mathematical correction.
* [Terminology proposals](reviews/2.0.7-ui-terminology/README.md) remain Pending.
  Extraction is broad; exhaustive individual semantic/runtime coverage is not
  certified. All remaining unverified state families are listed.
* Earlier whole-window high-DPI clipping, physical/mixed-monitor and live Jana
  acceptance, and wavelength-source priority review remain open. Focused widget
  checks do not establish full physical-monitor acceptance.
* Historical automatic seed, unknown effective legacy parameters and remote
  immutable checkpoint/runtime identities cannot be reconstructed from absent
  records. The provenance manifest makes no bitwise reproduction claim.

Draft PR: https://github.com/ji-ze/Phase-Studio/pull/21. No merge, tag or release
publication is part of this validation.
