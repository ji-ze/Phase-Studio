# Contributing to Phase Studio

Open an issue describing the problem, expected behavior, application version,
standalone or Jana2020 mode, and minimal reproducible steps. Remove access keys,
OAuth codes, account details and private project paths from attachments. Share
scientific data only when you have permission to publish it.

For source changes, open a pull request against `main`. Keep implementation,
meaningful regression tests and documentation together. Preserve scientific
output conventions and explain any intentional numerical or workflow changes.
Do not regenerate scientific expected values simply to make a test pass.

Use a Python environment with the project's Windows build dependencies, then run:

```powershell
python -m pytest -q -p no:cacheprovider
python tests/test_scientific_core.py
git diff --check
```

Some regression runners are standalone scripts and must also be executed
explicitly for the affected component. Real server processing and native
Jana2020 acceptance are separate, opt-in checks; mock or offscreen results do
not establish either. Do not use other people's accounts, data or service quota.

Build outputs, complete screenshot inventories, private credentials and local
scientific projects belong outside tracked source. Retain a few representative,
sanitized documentation images. External Superflip, EDMA and Jana2020 binaries
are not covered by the Phase Studio MIT license and must not be committed or
redistributed without applicable rights.

Describe validation limits in the PR. Maintainers merge only after reviewing
scientific semantics, tests, applicable checks and required reviews. Publishing
a release or changing a historical tag is a separate operation.
