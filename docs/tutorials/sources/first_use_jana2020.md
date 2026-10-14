# Phase Studio — Getting Started
## Integrated with Jana2020

<!-- DOCUMENT {"version": "2.0.3", "edition": "Development-source review edition", "filename": "PhaseStudio_FirstUse_Jana2020.pdf"} -->

<!-- PAGE {"title": "Before you begin", "image": null} -->
**Read this version note first.** These guides show the current 2.0.3 development-source interface, checked on 14 October 2026. The public release currently provides **v2.0.2**, with `PhaseStudio-2.0.2-x64.exe`. Some 2.0.3 setup, authentication and layout details differ. There is no published 2.0.3 binary in the verified release listing. Do not rename a 2.0.2 file to pretend it is 2.0.3.

Application screenshots are actual PySide6 renders. The teaching reflections and structures are synthetic and shareable, not a private or experimentally validated structure. Catalogue, prediction and staged-progress examples are identified as illustrative fixtures. Only the local Superflip/EDMA demonstration was actually calculated.

**Review edition:** native Jana2020 launch/return screenshots are awaiting approved capture; the authenticated SharpED token controls have been captured and sanitised. Their missing images are identified rather than replaced with invented screens. This edition is not final publication acceptance.

<!-- PAGE {"title": "Phase Studio is supplied with integrated Jana", "image": "screenshots/jana2020/wizard-input.png", "crop": "wizard-summary"} -->
**Phase Studio** is free, open-source crystallographic desktop software. It coordinates calculations, displays candidate structures and retains scientific outputs.

**Superflip** solves the crystallographic phase problem using charge flipping. **EDMA** locates atomic sites in electron-density maps. They are local, independently distributed programs with their own licences.

**SharpED** processes density maps online using machine learning. It uses your existing Jana2020 account; a separate SharpED registration is not needed. Free Phase Studio software does not imply free service inference or account entitlement.

Treat every model as a candidate. Check chemistry, symmetry and agreement with the original measured reflections, then refine independently. A convincing picture or a high apparent score is not proof of correctness.

This guide is for a Jana2020 distribution containing the preinstalled Phase Studio integration. You do not install a separate Phase Studio Jana installer. If your Jana distribution lacks the component, obtain the integrated distribution/update from its provider rather than using an obsolete installer.

<!-- PAGE {"title": "1 · Know the supplied tool layout", "image": "screenshots/standalone/setup-superflip.png", "caption": "Troubleshooting state, not a normal installation requirement for a correctly integrated Jana distribution."} -->
The expected installed layout is:

`<JanaRoot>/SUPERFLIP/superflip.exe`

`<JanaRoot>/SUPERFLIP/EDMA.exe`

Phase Studio's integration may reside in `<JanaRoot>/SharpED/Phase_studio.exe` with its `_internal` runtime kept alongside it. The actual Jana root may be on any supported drive/location.

**Jana users normally do not need to download or configure Superflip and EDMA separately.** Phase Studio searches relative to the active Jana root, validates the supplied tools and proceeds silently when they work. It does not look under `SharpED/SUPERFLIP` or substitute an unrelated legacy original file.

If setup appears, use Back and check the installed Jana distribution/runtime. Locate a valid existing tool only if necessary. Do not manually overwrite Jana's scientific executables.

<!-- PAGE {"title": "2 · Launch from your Jana project", "image": "screenshots/jana2020/wizard-input.png", "caption": "Genuine Phase Studio Wizard on synthetic Jana-format input. This does not replace the missing native Jana launch capture."} -->
Open your intended Jana2020 project and prepare its crystallographic structure-solution input using that Jana distribution's documented integration action. Jana supplies the incoming `.inflip` and original project context; Phase Studio opens **JANA2020 WORKFLOW**.

**Native screenshot acceptance gap:** a current, approved native Jana launch/menu capture has not been supplied. The installed machine's legacy integration is not asserted to be a verified 2.0.3 GUI path. No exact Jana menu label is invented in this guide. The distributable edition needs the actual menu/action screenshot and its verified wording.

Check the displayed incoming filename before continuing. Do not reuse a standalone session or a different project's saved context for returning results to Jana.

For integrators only: Jana invokes the supplied Phase_studio executable with its actual project `.inflip`, keeping the project as the scientific working context. This is not a separate installer instruction.

<!-- PAGE {"title": "3 · Read Input Summary", "image": "screenshots/jana2020/wizard-input.png", "crop": "wizard-summary"} -->
Check **Jana2020 input**, **Reflections**, **Format**, **Cell**, **Space group** and **Superflip input composition**. Parsed rows and unique reflections have different meanings; symmetry/Friedel merging can change the unique count.

The displayed cell and space group come from the interpreted input context. Search composition helps Superflip/EDMA; it need not equal the final EDMA-detected asymmetric-unit composition.

Expand **Show optional reference and initial model** only when needed. Reference and initial model have different roles. A reference aids metadata/evaluation; an explicit first-cycle model can supply a seed. Do not infer random phases merely from the phrase cycle 1.

<!-- PAGE {"title": "4 · Validate the reflections", "image": "screenshots/workflow/hkl-validation.png", "crop": "validation"} -->
Click **Validate HKL** and check the interpreted columns and counts. Successful parsing is a format/context check, not an experimental validation certificate.

**h k l · F · σ(F):** amplitude and amplitude uncertainty. **h k l · I · σ(I):** intensity and intensity uncertainty. **h k l · I · FWHM:** intensity and peak width. FWHM is not σ(I), so I/FWHM must not be interpreted as a significance ratio.

Phase columns use the selected displayed convention; the client converts degrees for its generated Superflip representation. Do not guess a phase/uncertainty column from its numerical size.

<!-- PAGE {"title": "5 · Analyze completeness", "image": "screenshots/workflow/hkl-completeness.png"} -->
Click **Analyze completeness**. Inspect resolution bins, completeness versus sinθ/λ, dmin, observed/theoretical unique-reflection counts and available intensity/uncertainty statistics.

The calculation depends on the selected cell, symmetry, observed bounds and resolution range. High completeness over that range does not establish correct measurements, correct symmetry or a correct model. Check bin coverage, not only one total percentage.

Significance plots require appropriate uncertainty data; FWHM-only data do not provide experimental σ(I). Statistics labelled for a width format must not be reused as I/σ(I).

<!-- PAGE {"title": "6 · Select the workflow", "image": "screenshots/jana2020/wizard-input.png", "crop": "wizard-workflows"} -->
**Superflip only:** conventional local charge-flipping solution; no SharpED account is needed for that local path.

**Superflip + SharpED:** charge flipping with remote neural-network map processing and supported iterative feedback/seeding.

**SharpED Autosolve · Experimental:** a distinct automated search/review policy. It has its own models and 1.00σ extraction defaults; do not transfer the normal 0.50σ policy to it.

**Professional mode:** opens full configuration without starting automatically. Configure it, then use manual Run phasing. It is not required merely to locate a missing executable.

Options needing inference require the existing Jana identity, an access key and applicable provider permission. The current four tiles are shown below.

<!-- PAGE {"title": "7 · Connect your existing Jana account", "image": "screenshots/web/sharped-token-controls.png"} -->
1. In Phase Studio, click **Open SharpED token page**. The official destination is [https://sharped.fzu.cz/sharp-ed](https://sharped.fzu.cz/sharp-ed).
2. If redirected, sign in on the website with your existing Jana2020 account. Never enter your Jana password into Phase Studio.
3. On the SharpED Tool page, find **API tokens for desktop application** and click **Show**.
4. Enter a descriptive **New token name**, for example `Phase Studio laptop`, and click **Create token**.
5. Copy the newly generated access key, return to Phase Studio and paste it into **SharpED access key**.
6. Click **Connect to SharpED** to continue your original workflow.

**Verified website capture:** the accompanying authenticated-page crop shows the actual **API tokens for desktop application**, **Show**, **New token name** and **Create token** controls. Account identity, browser details and the existing-token table are excluded. No token was created or copied during documentation capture.

<!-- PAGE {"title": "8 · Protect the access key", "image": "screenshots/web/jana-login.png", "crop": "web-login"} -->
The access-key field is masked. **Show/Hide** changes only visibility; do not expose a key in screenshots. **Remember access on this device** explicitly enables Windows Credential Manager storage; otherwise the key stays in memory for the session. **Replace access key** and **Remove saved access** manage that access. **Back** returns with scientific settings preserved.

Connect checks service/catalogue reachability and retains the supplied key. The public catalogue request does **not** prove inference entitlement or authenticated token validity. An authenticated processing request can still reject the key or account permission.

There is no automatic OAuth browser-to-desktop token delivery in this version. Copy and paste the key yourself. The account website and the client Public API host are different: keep the preset API configuration; do not replace it with the token-page URL.

Only send data that you are authorised to share with the remote service. Check current provider terms and entitlement before inference. No permanent free-access promise or price is made in this guide.

<!-- PAGE {"title": "9 · Choose cycles and model", "image": "screenshots/workflow/configuration-multi-cycle.png"} -->
For normal combined Wizard processing, **Number of cycles** sets the outer Superflip/SharpED cycle budget. One cycle automatically recommends **PEAK A (model prediction)**; two or more recommend **SEED (cyclic CF)** when those exact IDs exist in the live catalogue.

Selecting a model explicitly creates a manual override. **Restore automatic** returns to the cycle policy. **Refresh** has the accessible name Refresh models and queries the current catalogue; available models are dynamic.

The next Map Feedback page controls optional derived reflection input for later cycles. Leave its optional methods disabled for a simple unmodified-data run. More cycles cost more time and do not guarantee improvement.

<!-- PAGE {"title": "10 · Follow execution", "image": "screenshots/workflow/execution-concurrent.png", "landscape": true, "caption": "Actual execution UI with a synthetic progress/prediction fixture, not a live neural-network job."} -->
The execution window separates **Charge-flipping solution** from **Model prediction**. It shows cycle/progress, current operations, log and completed structures. Work can overlap: EDMA for one completed map or a SharpED request may be active while another operation progresses.

Use the two panels independently. A completed candidate is not replaced by unfinished output. Graceful stopping after a cycle retains completed candidates for review. Wait for any selected interactive EDMA request to finish before handoff.

This combined-window image is an explicitly illustrative lifecycle fixture; no authenticated inference was performed for it.

<!-- PAGE {"title": "10 · Follow execution · enlarged view", "image": "screenshots/workflow/execution-concurrent.png", "landscape": true, "crop": null, "caption": "Actual execution UI with a synthetic progress/prediction fixture, not a live neural-network job."} -->
Enlarged genuine application capture. For meaning, settings and fixture limitations, read the preceding page.

<!-- PAGE {"title": "11 · Select the intended result", "image": "screenshots/workflow/selector-model-prediction.png", "landscape": true, "caption": "Actual selector with synthetic candidate/model and metric fixtures; no Jana transfer is executed."} -->
After a successful Wizard-launched workflow, **Result Selection** opens automatically. In Professional/full configuration, there is no automatic run; after manual completion, **Pass to Jana2020** opens the same selector.

Choose **Charge-flipping solution** or **Model prediction**, then the intended cycle row. The recommendation star is advice within that result family. Your selected row can differ from the recommendation.

Read provenance, EDMA threshold, detected/ASU counts and **Jana model** count. The displayed structure may contain symmetry images and is not necessarily the exact atom-count list imported into Jana.

<!-- PAGE {"title": "11 · Select the intended result · enlarged view", "image": "screenshots/workflow/selector-model-prediction.png", "landscape": true, "crop": null, "caption": "Actual selector with synthetic candidate/model and metric fixtures; no Jana transfer is executed."} -->
Enlarged genuine application capture. For meaning, settings and fixture limitations, read the preceding page.

<!-- PAGE {"title": "12 · Finish threshold review", "image": "screenshots/workflow/selector-edma-pending.png", "landscape": true, "caption": "Actual pending-extraction UI state, driven by an explicit asynchronous fixture."} -->
Use **+ atoms** to lower the detection threshold and **− atoms** to raise it. At the normal 0.50σ setting, the next steps are 0.40σ and 0.60σ. The step becomes smaller below 0.30σ; guided interactive limits are 0.10–3.00σ.

Threshold changes rerun EDMA on the unchanged selected scientific map, not Superflip or SharpED. The Pass action is disabled while the requested candidate-specific extraction is pending.

More detected sites do not guarantee better chemistry. A composition-constrained Jana model may keep the same atom list even when the raw EDMA/CIF peaks change. Use the completed candidate/threshold and check the reported Jana model count.

<!-- PAGE {"title": "12 · Finish threshold review · enlarged view", "image": "screenshots/workflow/selector-edma-pending.png", "landscape": true, "crop": null, "caption": "Actual pending-extraction UI state, driven by an explicit asynchronous fixture."} -->
Enlarged genuine application capture. For meaning, settings and fixture limitations, read the preceding page.

<!-- PAGE {"title": "13 · Pass to Jana2020", "image": "screenshots/workflow/selector-manual-candidate.png", "landscape": true, "caption": "Actual Phase Studio selection UI. A native Jana return image is explicitly missing."} -->
Confirm the chosen family, cycle and completed threshold, then click **Pass to Jana2020**. Phase Studio validates the chosen scientific map and corresponding model and publishes them in the original Jana project context. It does not pass a preview image or restart phasing/inference during return.

The map and atomic model must retain the same crystallographic frame. The original Jana context supplies expected names; you should not rename a preview or manually substitute files in the installation directory.

Continue the project in Jana and check the imported atoms against density, symmetry and the original experiment before refinement.

**Native return acceptance gap:** this edition has no approved screenshot of the selected map/model imported in Jana and normal continuation. Automated/file tests are not presented as native GUI acceptance. That capture and a real-machine handoff check are required before public acceptance of this tutorial.

<!-- PAGE {"title": "13 · Pass to Jana2020 · enlarged view", "image": "screenshots/workflow/selector-manual-candidate.png", "landscape": true, "crop": null, "caption": "Actual Phase Studio selection UI. A native Jana return image is explicitly missing."} -->
Enlarged genuine application capture. For meaning, settings and fixture limitations, read the preceding page.

<!-- PAGE {"title": "Troubleshooting Jana workflows", "image": null} -->
**Setup unexpectedly appears:** check the active installation's SUPERFLIP files and complete Phase Studio runtime. Do not replace them with an unrelated launcher.

**Wrong incoming project:** Back/Cancel and relaunch from the intended Jana project; do not use a stale standalone context.

**Pass disabled:** check that the candidate is completed, its scientific map/model exists and any interactive EDMA request has finished. Immediate cancellation is different from a graceful stop after a completed cycle.

**Different atom counts:** distinguish independent EDMA sites, ASU composition, symmetry-expanded displayed atoms and Jana model sites. More peaks need not mean a changed Jana model.

**Logs:** use Open log for project/run diagnostics. Logs do not belong in the installed SUPERFLIP directory. Redact private data before support.

See [the Complete Guide](PhaseStudio_Superflip_SharpED_Complete_Guide.pdf) for every setting and metric limitation.

<!-- PAGE {"title": "Useful links and attribution", "image": null} -->
[Phase Studio repository](https://github.com/ji-ze/Phase-Studio) · [Public releases](https://github.com/ji-ze/Phase-Studio/releases) · [Issue tracker](https://github.com/ji-ze/Phase-Studio/issues)

[Jana2020](https://jana.fzu.cz/) · [SharpED token page](https://sharped.fzu.cz/sharp-ed) · [Official Superflip/EDMA distributions](https://superflip.fzu.cz/)

[Superflip licence](https://superflip.fzu.cz/download/license_superflip.txt) · [EDMA licence](https://superflip.fzu.cz/download/license_EDMA.txt) · [Phase Studio MIT licence](https://github.com/ji-ze/Phase-Studio/blob/main/LICENSE)

**SharpED terms:** read the current terms shown by the provider. The project supplied `SharpED_Online_Service_and_API_Terms_2026-10-13_FINAL.pdf`, but no independently verified direct public terms URL is available for this edition. No guessed terms link is included.

**Software author:** Jiří Zelenka, Institute of Physics of the Czech Academy of Sciences. **SharpED developers, separately:** Jiří Zelenka, Jan Rohlíček, Monika Kučeráková and Zdeněk Buk, at the same institute.

Phase Studio uses the MIT licence. Scientific citation guidance is separate from the licence: cite the software version you actually used, its author, institute and repository, together with relevant Superflip, EDMA and Jana references. No new Phase Studio DOI is asserted.

PDF body fonts are the openly licensed DejaVu Sans family. Screenshots preserve the authentic application wordmarks. No proprietary font files are distributed with these guides.

[Standalone first use](PhaseStudio_FirstUse_Standalone.pdf) · [Complete Guide](PhaseStudio_Superflip_SharpED_Complete_Guide.pdf)
