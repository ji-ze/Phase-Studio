# Phase Studio 2.0.3

Phase Studio 2.0.3 improves setup, workflow configuration and result review for
Superflip, EDMA and SharpED, building on the first public 2.x release, 2.0.2.

## What's changed

- **Jana2020 Wizard:** clearer input summary, grouped workflow choices,
  responsive layout and optional reference/initial-model controls.
- **Superflip + SharpED configuration:** simpler cycle/model selection,
  automatic recommendations with manual override, and advanced account access.
- **Map Feedback:** distinct single-crystal and powder controls, restored
  weak-reflection correction, and explicit uncertainty/FWHM limitations.
- **Execution window:** separate charge-flipping and model-prediction views,
  completed-cycle browsing, camera controls, Complete molecules/Full cell,
  interactive EDMA thresholds and clearer progress/logging.
- **Result Selection:** candidate provenance, separate result families,
  recommendations, scientific metrics and threshold-specific model review
  before passing the selected result to Jana2020.
- **SharpED access:** confirmed token-page instructions using an existing
  Jana2020 account, masked keys, optional Windows Credential Manager storage,
  and redacted error details. Scientific settings remain preserved when
  opening the browser or returning from account setup.
- **Local tools:** one setup dialog validates the required Superflip/EDMA
  programs and locates existing installations. Unapproved automatic tool
  downloads are not offered.
- **Documentation:** three illustrated review tutorials, editable sources and
  genuine screenshots are included in the repository.

## Windows download

The **only attached release asset** is **PhaseStudio-2.0.3-x64.exe**.
It is a standalone Windows x64 ONEFILE with its Python/Qt runtime included.
Use Windows 10 1903 or newer, or Windows 11. Superflip and EDMA remain separately
 distributed scientific programs; SharpED requires appropriate service access.
No scientific binaries, model weights, personal keys or Jana installer are bundled.

SHA-256:

```text
521412d2ce3602a9c061f52ff8126b6b59dcb74c65bdac52a6814643b2e95d21
```

No ZIP, checksum text file, release-note file, PDF or screenshot is attached as
a release asset. Notes and images are presented here; the repository retains
the editable documentation and capture tooling.

## Screenshots

These are genuine current application renders with public synthetic teaching
data or explicitly staged UI fixtures. They illustrate the interface, not
scientific validity or successful remote inference/native Jana acceptance.

### Jana2020 workflow Wizard

![Jana2020 workflow Wizard](https://raw.githubusercontent.com/ji-ze/Phase-Studio/v2.0.3/docs/tutorials/screenshots/jana2020/wizard-input.png)

### Superflip + SharpED configuration

![Superflip and SharpED cycle/model configuration](https://raw.githubusercontent.com/ji-ze/Phase-Studio/v2.0.3/docs/tutorials/screenshots/workflow/configuration-multi-cycle.png)

### Execution and structure review

![Execution window and structure viewers](https://raw.githubusercontent.com/ji-ze/Phase-Studio/v2.0.3/docs/tutorials/screenshots/workflow/execution-completed.png)

### Result Selection

![Jana2020 Result Selection](https://raw.githubusercontent.com/ji-ze/Phase-Studio/v2.0.3/docs/tutorials/screenshots/workflow/selector-model-prediction.png)

## Validation and remaining acceptance

The build passed 56 direct regression suites (2,356 reported checks), pytest
(184 passed and five subtests passed), scientific golden and Jana map-alignment
checks, frozen version checks and distribution-boundary validation. One opt-in
real-project metadata test was skipped. Both executable and Windows file
versions identify 2.0.3.

Native Jana2020 launch, selected scientific map/model import and normal
continuation still require real-machine acceptance for this version. The
illustrated tutorials remain explicitly labelled review editions. SharpED
Autosolve remains experimental; validate candidates against original measured
data and independent crystallographic refinement.

## Documentation and access

- [Illustrated tutorials and review status](https://github.com/ji-ze/Phase-Studio/tree/v2.0.3/docs/tutorials)
- [SharpED access instructions](https://github.com/ji-ze/Phase-Studio/blob/v2.0.3/docs/SHARPED_ACCESS.md)
- [Official SharpED token page](https://sharped.fzu.cz/sharp-ed)
- [Source and build instructions](https://github.com/ji-ze/Phase-Studio/tree/v2.0.3)

Phase Studio is MIT-licensed. Superflip, EDMA, Jana2020 and SharpED retain their
own licences/service terms. Free Phase Studio software does not imply free
SharpED inference entitlement.
