# Jana2020 developer integration — Phase Studio 2.0.5

The ZIP contains `PhaseStudio-Jana2020-2.0.5/Phase_studio.exe` and the complete
`_internal/` directory. Keep the pair together. Do not distribute only the EXE,
rename it to Superflip, or overwrite the scientific `SUPERFLIP/superflip.exe`.

## Placement and invocation

Recommended dedicated location:

```text
<JanaRoot>/SharpED/Phase_studio.exe
<JanaRoot>/SharpED/_internal/...
<JanaRoot>/SUPERFLIP/superflip.exe
<JanaRoot>/SUPERFLIP/EDMA.exe
```

Deployment beside Jana's executable is also supported if `_internal` can be
kept intact without colliding with other installed components. Scientific
executables are resolved relative to the active Jana installation, not a
developer's private path or a different installation found on PATH.

Invoke with the incoming `.inflip` pathname, preferably absolute and quoted;
the working directory is the scientific project directory:

```text
"<JanaRoot>/SharpED/Phase_studio.exe" "<ProjectDirectory>/project_Superflip.inflip"
```

Jana must generate its normal context, including original project `.m50`,
outputfile, outputbase and writem40 declarations. The launcher remains the
existing Jana Wizard. Selecting Professional opens configuration without
automatic execution; normal workflows do not expose an unintended Professional
window. A legacy in-place installer remains historical source only.

## Scientific return contract

Return paths come from the actual incoming `.inflip`: M80/M81 from outputfile,
M40/M50 from outputbase and the EDMA model destination from writem40. Names are
not guessed from a preview. The selected source/cycle/threshold's map, CIF and
sealed EDMA m40 are validated before one transactional publication. The original
M50 context is preserved. The selected map's original grid and origin are
retained in the format conversion; no phasing/inference is restarted at handoff.

The project receives its scientific output set and a Jana-ready XPLOR sidecar.
Detailed logs, incoming input copies and candidate handoff manifests belong to
the project/run directory, not the installation. Normal GUI logs do not contain
tokens or per-atom diagnostics.

## Prerequisites and checks

Use Windows x64 and the complete supplied runtime. Superflip/EDMA/Jana retain
their own licenses. SharpED workflows need the user's accepted current service
terms, personal API token and applicable access entitlement; Superflip-only
does not require that service.

- `Phase_studio.exe --version` reports 2.0.5.
- `--release-ui-check <output.json>` exercises isolated offline HKL parsing,
  Wizard navigation, model policy, account UI and the update menu. It does not
  run scientific programs or establish native Jana acceptance.
- `--brand-font-check <output.json>` is an automated offscreen resource check.
- Validate the intact `_internal` runtime and required native imports.
- On an actual Jana workstation, test Superflip-only, both EDMA result
  families, a completed threshold override, graceful stopping, manual candidate
  selection and a second run. Verify nonzero model import, aligned density/atoms
  without origin adjustment, correct context, one handoff and normal continuation.

Automated/file/numerical checks are not actual Jana GUI acceptance. The latter
remains explicitly pending until performed and recorded on a real workstation.
