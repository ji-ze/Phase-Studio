# Phase Studio 2.0.4 — ten-window acceptance index

Exactly ten PNG screenshots, captured from the current PySide6 widgets at 100% scaling with the offscreen Qt platform. Each image was inspected visually. These are application windows, not mockups. No browser, external inference, authentication, handoff or real project modification was performed.

| Image | Stage and data |
|---|---|
| [01](01_main_workflow.png) | Jana Wizard main page: real ochlor input copied to an isolated workspace, populated crystal/reflection summary and all four workflow choices. |
| [02](02_optional_input.png) | Same input, optional reference and initial-model fields expanded. |
| [03](03_hkl_validation.png) | Real ochlor, first-200-record preview, verified powder format and symmetry diagnostics. |
| [04](04_hkl_completeness.png) | Real ochlor, unchanged d_min/d98, constant-width summary, Peak overlap selected, group distribution and resolution-dependent fraction. |
| [05](05_superflip_sharped_config.png) | Superflip + SharpED settings and automatic three-cycle recommendation. The two-entry model catalogue is an explicit controlled offline fixture, not a server response. |
| [06](06_map_feedback_powder.png) | Real ochlor powder settings, wavelength recovered from the matching copied Jana `.m90`. No repartitioning was executed. |
| [07](07_map_feedback_single_crystal.png) | Controlled amplitude/phase/uncertainty fixture showing missing-reflection completion and weak-reflection correction. No processing was executed. |
| [08](08_sharped_connection.png) | Empty isolated credential store; existing browser sign-in interface. Sign-in was not attempted. |
| [09](09_execution.png) | Existing controlled execution-window fixture: two synthetic carbon structures, controls, progress and log. Running status is supplied UI state; no Superflip/SharpED inference occurred for this screenshot. |
| [10](10_result_selection.png) | Existing file-backed selector fixture with three candidates, supplied comparison metrics, two-site structure/model and final controls. No Jana publication was executed. |

The initial capture exposed a harness error: the real input summary could not create its derived workspace outside the permitted repository. Captures 01/02 were replaced after copying the source and matching `.m90` into `build/powder-final/wizard-input`; the source project was unchanged. The final images show actual parsed metadata. The initial narrow main-page capture was replaced with a 950 × 900 logical-pixel window so all four choices are visible. Configuration was captured after installing the offline model fixture, eliminating a misleading Loading models status.

All ten final images have readable controls and footers, no unexpected tooltips, and no credentials. The execution/selector fixtures are intentionally not evidence of real scientific success. The existing hierarchy/navigation tests cover Superflip only, Superflip + SharpED, Autosolve and Professional entry points; these screenshots do not execute all four workflows.

Manual physical-monitor and real Jana2020 acceptance remain required. The capture utility is `packaging/tools/capture_acceptance_204.py`; generated JSON sidecars contain local measurement paths and are not included in this screenshot package/commit.
