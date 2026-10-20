# Verified Windows distribution trimming

The default packaging profile is `combined-safe`: do not collect the unused
qtvscodestyle application resources/modules, Qt translations for the current
English GUI, or Matplotlib sample data. Scientific fonts, styles, QtAgg and
native plugins remain. The qtvscodestyle package is left installed in the
development environment; legal notices are preserved.

`distribution_options.py` controls these build-time decisions. The Matplotlib
hook delegates to the installed pinned upstream hook. Qt translation metadata
is narrowed before collection. Both specs explicitly include the dynamically
selected PDF/SVG/PS/PGF export backends; PDF export was broken in the initial
frozen baseline even though PNG and startup succeeded.

The separate `without-qt-quick-experimental` profile filters the already
disabled virtual-keyboard plugin before native dependency analysis. It is
never the default. Software OpenGL fallback remains. AVIF is supported by the
existing image export authority and is deliberately retained.

## Reproduce without replacing an existing build

From the repository with the existing Windows build environment:

```powershell
.\.venv-build\Scripts\python.exe packaging\tools\optimize_distribution.py --snapshot --snapshot-root build\o26repeat --evidence-root build\optimization-internal\repeat --all
```

Use a **new** short snapshot root each time. Existing snapshots, measured
variants and output copies are not silently replaced. The runner records source
hashes, dirty status, commit and dependency versions. It copies the actual
pending 2.0.6 source, including the updater, and excludes unrelated workshop
drafts. Every variant gets its own DistRoot under that snapshot. Named copies
are stored under `dist/optimization-2.0.6/<evidence-directory-name>/`.

The working dist names are intentionally short: upstream license paths plus ZIP
verification/staging can exceed legacy Windows MAX_PATH when long experiment
names are used. Named archival copies use extended Windows paths. Do not shorten
or remove license texts to work around the path limit.

Frozen `--packaging-acceptance <new-output-directory>` is an explicit offline
diagnostic path. It uses isolated INI settings, in-memory test credentials and
controlled scientific fixtures. It never runs Superflip/EDMA, submits inference,
signs in, or completes a real Jana handoff. Windows Qt and offscreen DPI captures
are separately identified. A successful diagnostic is not a real Jana import
or a controlled cold-start measurement.

The reviewed production public verification key is already pinned; normal
builds never generate or rotate signing keys. The
real-runtime transaction test exposed brief Windows rename denials after
extraction/verification; bounded atomic-rename retries now preserve the verified
tree, while permanent failures still trigger rollback. These retries do not
relax hash checks, ownership boundaries, process guards or signature policy.

Local evidence and the detailed Czech report are under
`build/optimization-internal/OPTIMIZATION_REPORT.md`. No production installation,
release tag or published asset is changed by these commands.
