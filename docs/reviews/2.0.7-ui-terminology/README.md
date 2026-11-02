# UI terminology owner review, 2.0.7

Twenty priority proposals are ready for owner review. **All decisions are
Pending; no proposed wording has been applied.** The critical finding is the
legacy input ratio filter used on FWHM data. That needs a separate scientific
behavior decision, not approval of a label alone.

| Evidence | Count |
| --- | ---: |
| Python literal/template occurrences retained for residual review | 14,526 |
| Static user-facing candidates | 2,036 |
| Runtime text observations | 1,103 |
| Unique candidate/template/runtime texts | 1,711 |
| Registered main configuration settings | 87 |
| Main dropdown options, including internal values | 52 |
| Runtime tooltip occurrences | 363 |
| Static warning/error candidates | 270 |
| Secondary runtime control occurrences | 5 |
| Priority findings / proposed changes | 20 / 20 |

These are extraction counts, not certified counts of individually reviewed
unique visible messages. Helper arguments, duplicate observations and dynamic
templates have explicit classifications. Eight runtime state families and
individual semantic sign-off remain open in the coverage section below.

Read in this order:

1. [Scientific findings and coverage limits](TERMINOLOGY_REVIEW.md).
2. [Owner decision checklist](PROPOSED_TEXT_CHANGES.md).
3. [Exact text inventory](UI_TEXT_INVENTORY.md).
4. [Settings inventory](SETTINGS_INVENTORY.md).

Machine-readable files retain exact source paths, line numbers, symbols,
dynamic source templates, observed controls and numerical properties:

* `static-literals.json`: all retained Python literals, including candidates
  not classified as visible, for residual review.
* `runtime-widgets.json`: controlled-fixture runtime observations, including
  both Result Selection contexts and Autosolve.
* `settings.json`: application defaults before saved settings load, displayed
  fixture values, options/internal values, ranges/steps/precision, units or
  explicitly unknown units, tooltips, persistence and unresolved assessments.
* `settings-source.json`: exact helper calls, RunConfig definition and preset
  changes relative to the initial fixture.
* `backend-traces.json`: per-setting source references and enclosing branch
  conditions. References expose actual code paths; they do not substitute for
  individual scientific interpretation.
* `secondary-controls.json`: additional runtime control occurrences.
* `findings.json` and `coverage.json`: proposals and coverage accounting.

Rebuild with the repository build Python using `build_inventory.py`, then
`build_findings.py`. These scripts suppress settings writes and remote model
refreshes, use controlled local fixtures, and never start a paid job. Personal
saved settings and credentials are not inspected. Runtime capture does not
certify every conditional branch, native dialog or frozen-profile difference.

The inventory is ready to search and review; **exhaustive individual semantic
verification is not certified**. See the explicit unresolved rows and state
families before approving release wording.
