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
| [09](09_execution.png) | Offline replay of actual completed ochlor Cycle 3 maps, freshly audited local EDMA generations at 0.50σ and historical measured-map metrics. Header and progress show completed 3/3; the log explicitly identifies offline replay. No new inference. |
| [10](10_result_selection.png) | The same completed ochlor Cycle 3 Structure prediction, actual historical reference-free metrics and corresponding EDMA/Jana model. Only this available cycle is loaded; the table is not presented as a new three-cycle comparison. No publication from the viewer. |

The initial capture exposed a harness error: the real input summary could not create its derived workspace outside the permitted repository. Captures 01/02 were replaced after copying the source and matching `.m90` into `build/powder-final/wizard-input`; the source project was unchanged. The final images show actual parsed metadata. The initial narrow main-page capture was replaced with a 950 × 900 logical-pixel window so all four choices are visible. Configuration was captured after installing the offline model fixture, eliminating a misleading Loading models status.

The final consistency pass refreshed 04–10. Powder summary labels distinguish multi-record groups, all groups, isolated and affected records, and intensity fraction. Configuration, Feedback and authentication use their content sizes. Wizard captures simulate a 1920 × 1040 logical-pixel available desktop rather than the offscreen plugin's 800 × 800 default; the widgets and layout are actual production PySide6. Restricted/DPI behavior is tested separately without adding PNGs to this package.

All ten final images have readable controls and footers, no unexpected tooltips, and no credentials. Historical data in 09/10 is real; UI replay and the catalogue/single-crystal setup fixtures do not establish a newly executed workflow or live SharpED access. The existing hierarchy/navigation tests cover Superflip only, Superflip + SharpED, Autosolve and Professional entry points; these screenshots do not execute all four workflows. At 0.50σ the actual example has more raw EDMA sites than composition-constrained Jana model sites; the differing counts are shown explicitly rather than relabeled or concealed.

Manual physical-monitor and real Jana2020 acceptance remain required. The capture utility is `packaging/tools/capture_acceptance_204.py`; generated JSON sidecars contain local measurement paths and are not included in this screenshot package/commit.
