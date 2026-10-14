# Phase Studio — Getting Started
## Standalone Windows Application

<!-- DOCUMENT {"version": "2.0.3", "edition": "Development-source review edition", "filename": "PhaseStudio_FirstUse_Standalone.pdf"} -->

<!-- PAGE {"title": "Before you begin", "image": null} -->
**Read this version note first.** These guides show the current 2.0.3 development-source interface, checked on 14 October 2026. The public release currently provides **v2.0.2**, with `PhaseStudio-2.0.2-x64.exe`. Some 2.0.3 setup, authentication and layout details differ. There is no published 2.0.3 binary in the verified release listing. Do not rename a 2.0.2 file to pretend it is 2.0.3.

Application screenshots are actual PySide6 renders. The teaching reflections and structures are synthetic and shareable, not a private or experimentally validated structure. Catalogue, prediction and staged-progress examples are identified as illustrative fixtures. Only the local Superflip/EDMA demonstration was actually calculated.

**Review edition:** native Jana2020 launch/return screenshots are awaiting approved capture; the authenticated SharpED token controls have been captured and sanitised. Their missing images are identified rather than replaced with invented screens. This edition is not final publication acceptance.

<!-- PAGE {"title": "What each program does", "image": "screenshots/standalone/standalone-input.png", "crop": "configuration"} -->
**Phase Studio** is free, open-source crystallographic desktop software. It coordinates calculations, displays candidate structures and retains scientific outputs.

**Superflip** solves the crystallographic phase problem using charge flipping. **EDMA** locates atomic sites in electron-density maps. They are local, independently distributed programs with their own licences.

**SharpED** processes density maps online using machine learning. It uses your existing Jana2020 account; a separate SharpED registration is not needed. Free Phase Studio software does not imply free service inference or account entitlement.

Treat every model as a candidate. Check chemistry, symmetry and agreement with the original measured reflections, then refine independently. A convincing picture or a high apparent score is not proof of correctness.

<!-- PAGE {"title": "1 · Download the Windows application", "image": "screenshots/web/github-assets.png", "crop": "github-assets", "caption": "Live public v2.0.2 release page. The guide’s source UI version is 2.0.3."} -->
Open the [verified v2.0.2 release](https://github.com/ji-ze/Phase-Studio/releases/tag/v2.0.2). Find the Assets section and download **PhaseStudio-2.0.2-x64.exe**. The standalone Windows x64 ONEFILE includes its Python/Qt runtime; no separate Python installation is needed.

Use a compatible Windows x64 machine (Windows 10 1903 or newer, or Windows 11). Check the release's own requirements and filename. This guide's updated 2.0.3 screens are source previews, not a claim that this download contains those changes.

Do not download an obsolete separate Jana installer for this standalone exercise. If Windows raises a security warning, verify the official repository, release and file integrity first. Use a provider-published SHA-256/signature where available; calculating your own hash alone does not establish authenticity. The current public release API lists only the EXE, not a separate checksum asset. Its published asset SHA-256 is `139886f97ccc743ab360fd48a0d36ae43697523763d660d7c567afa6c6dee55e`. In PowerShell run `Get-FileHash .\PhaseStudio-2.0.2-x64.exe -Algorithm SHA256` and compare all digits before launch. Do not bypass warnings blindly.

<!-- PAGE {"title": "2 · Launch and recognise the main window", "image": "screenshots/standalone/standalone-input.png", "landscape": true} -->
Launch the downloaded EXE from a trusted location. The main window contains **Basic** and **Advanced** configuration, the run actions, progress/metrics, structure viewers and Execution Log.

Opening Phase Studio does not start a calculation. Start with **Basic → Input**. **Run phasing** starts a configured workflow; **Continue run** is for a compatible interrupted run with saved state. Leave continuation and advanced settings alone for your first exercise.

The working directory belongs to your project and stores generated inputs, maps, structures, metrics and logs. Keep it separate from the application installation directory.

<!-- PAGE {"title": "2 · Launch and recognise the main window · enlarged view", "image": "screenshots/standalone/standalone-input.png", "landscape": true, "crop": null, "caption": "Actual application UI; synthetic teaching input / labelled demonstration state."} -->
Enlarged genuine application capture. For meaning, settings and fixture limitations, read the preceding page.

<!-- PAGE {"title": "3 · Locate Superflip and EDMA", "image": "screenshots/standalone/setup-both.png", "caption": "Actual combined setup dialog. It appears only for local tools needed by the requested workflow."} -->
Superflip is required for charge-flipping structure solution. EDMA is required when the selected workflow extracts atomic sites from density maps. A purely local Superflip + EDMA calculation does not need SharpED access.

Phase Studio validates an explicit path first, then the active Jana installation when applicable, a persistent managed installation, supported known locations and finally PATH. Bare legacy program names are PATH discovery, not priority over active Jana. Compatible installed tools are detected before a setup dialog appears.

For a missing tool, click **Official download page**, follow the authors' installation/licence instructions, and return to **Locate existing Superflip/EDMA**. Select the actual program file. Phase Studio checks identity, runtime and a bounded launch, then resumes the original request. Filename alone is insufficient. **Back** returns without skipping a required tool.

**Automatic installation is unavailable in this source version:** approved distribution integrity and automated-download permission are not established. No Download and set up promise is made.

<!-- PAGE {"title": "4 · Open the SharpED account step", "image": "screenshots/web/sharped-token-controls.png"} -->
1. In Phase Studio, click **Open SharpED token page**. The official destination is [https://sharped.fzu.cz/sharp-ed](https://sharped.fzu.cz/sharp-ed).
2. If redirected, sign in on the website with your existing Jana2020 account. Never enter your Jana password into Phase Studio.
3. On the SharpED Tool page, find **API tokens for desktop application** and click **Show**.
4. Enter a descriptive **New token name**, for example `Phase Studio laptop`, and click **Create token**.
5. Copy the newly generated access key, return to Phase Studio and paste it into **SharpED access key**.
6. Click **Connect to SharpED** to continue your original workflow.

**Verified website capture:** the accompanying authenticated-page crop shows the actual **API tokens for desktop application**, **Show**, **New token name** and **Create token** controls. Account identity, browser details and the existing-token table are excluded. No token was created or copied during documentation capture.

<!-- PAGE {"title": "5 · Sign in only on the website", "image": "screenshots/web/jana-login.png", "crop": "web-login", "caption": "Actual public Jana login page, captured with a fresh browser profile; no credentials entered."} -->
The browser may first show this Jana2020 login page. Use your existing Jana identity and sign in there, not inside Phase Studio. The pictured fields are deliberately empty.

After sign-in, follow the token-section procedure on the previous page. The preceding page includes a sanitised authenticated token-control crop; no token is included.

You can skip connecting to SharpED when running a local workflow with **Run SharpED** disabled. You cannot skip it when the selected workflow genuinely requires remote processing.

<!-- PAGE {"title": "6 · Keep the key private", "image": "screenshots/standalone/connect-sharped.png", "crop": "account-controls"} -->
The access-key field is masked. **Show/Hide** changes only visibility; do not expose a key in screenshots. **Remember access on this device** explicitly enables Windows Credential Manager storage; otherwise the key stays in memory for the session. **Replace access key** and **Remove saved access** manage that access. **Back** returns with scientific settings preserved.

Connect checks service/catalogue reachability and retains the supplied key. The public catalogue request does **not** prove inference entitlement or authenticated token validity. An authenticated processing request can still reject the key or account permission.

There is no automatic OAuth browser-to-desktop token delivery in this version. Copy and paste the key yourself. The account website and the client Public API host are different: keep the preset API configuration; do not replace it with the token-page URL.

Only send data that you are authorised to share with the remote service. Check current provider terms and entitlement before inference. No permanent free-access promise or price is made in this guide.

<!-- PAGE {"title": "7 · Select the demonstration input", "image": "screenshots/standalone/standalone-input.png", "crop": "configuration"} -->
Use the accompanying **demo/tutorial_intensity.hkl** and **demo/tutorial_reference.cif**. These are generated synthetic reflections and a mathematical six-carbon ring in P1; they are not a measured or validated structure.

Choose **Input mode: External HKL + CIF reference**, select the HKL, choose **HKL format: h k l · I · σ(I)**, and use **Metadata source: Reference structure** with the supplied CIF. The CIF supplies the 10 × 10 × 10 Å cell, 90° angles, P1 and C6 composition.

The **Reference model** supplies metadata/evaluation context; it is not automatically the **Initial model (cycle 1)**. Leave that initial-model field empty for this demonstration. Validate the interpreted columns before phasing. Your real experiment must use its own correct cell, symmetry, composition and column meaning.

<!-- PAGE {"title": "8 · Validate the HKL interpretation", "image": "screenshots/workflow/hkl-validation.png", "crop": "validation"} -->
Click **Validate HKL**. Check parsed/unique counts, indices, values, uncertainty and any phase column. A successful parse means the selected format can be read; it does not certify measurement quality, correctness of the space group or completeness.

For the teaching file, the displayed values are synthetic intensities with σ(I). **F** is an amplitude, **I** is an intensity, and **FWHM** is a peak width. Choose the format that matches your file, not whichever gives a desirable score.

**Analyze completeness** checks coverage within the observed reciprocal-space/resolution range using the selected symmetry. The complete guide explains its plots and limitations.

<!-- PAGE {"title": "9 · Configure a short local run", "image": "screenshots/standalone/standalone-workflow.png", "crop": "configuration"} -->
For the first teaching calculation choose **Phasing method: Superflip**, **Cycles: 1**, enable **Run EDMA on Superflip map**, and disable **Run SharpED** and **Run EDMA on SharpED map**. Use **Output → Working directory** for a new project folder.

For a fast synthetic exercise, set **Advanced → Superflip → Maximum iterations: 100**, **Repeat mode: 1**, and **Voxel grid: 32 32 32**. These demonstration limits are not recommended defaults for a real structure solution. The real local capture used **Normalization: none**. Normal full-configuration defaults differ and are documented in the complete guide.

Click **Run phasing**. This produces a candidate map/model; completion is not a guarantee of a chemically correct six-site solution. For a combined run, enable Run SharpED, connect your account and read the Complete Guide first.

<!-- PAGE {"title": "10 · Watch the calculation", "image": "screenshots/standalone/local-run-active.png", "landscape": true, "caption": "Genuine local calculation; any personal diagnostic paths are explicitly redacted."} -->
The run status shows overall workflow progress and the current operation. Superflip may perform several internal iterations/trials inside one Phase Studio cycle. Completed structures can appear before all work is finished.

Use **Execution Log**, **Expand log** and **Open log** for diagnostics. **Stop after current cycle** requests a graceful stop; **Stop immediately** cancels active work. A completed candidate remains distinct from a partially running stage.

The image comes from an actual local Superflip/EDMA calculation on the public synthetic file, with no SharpED request.

<!-- PAGE {"title": "10 · Watch the calculation · enlarged view", "image": "screenshots/standalone/local-run-active.png", "landscape": true, "crop": null, "caption": "Genuine local calculation; any personal diagnostic paths are explicitly redacted."} -->
Enlarged genuine application capture. For meaning, settings and fixture limitations, read the preceding page.

<!-- PAGE {"title": "11 · Inspect and save the result", "image": "screenshots/standalone/local-run-completed.png", "landscape": true, "caption": "Actual completed Superflip + EDMA demonstration; synthetic input does not imply independent experimental validation."} -->
Review the **Charge-flipping solution** and its EDMA model. Rotate/pan/zoom, and use Fit to inspect the full displayed structure. A lower EDMA threshold can reveal more sites, but noise peaks do not become chemically correct atoms merely because they are visible.

After completion, **Save map and model** exports the available result using supported selected formats. Generated scientific inputs, internal XPLOR maps/CIF structures and metrics remain in the working run folder. **Output → Map format/Structure format** controls additional exported formats; it does not replace required internal workflow files.

A standalone session has no incoming Jana return context. It must not hand results to an arbitrary Jana project. Use the Jana-integrated guide for a context-preserving return.

For cycles, model choice, Map Feedback, viewer controls and scientific scores, see [the Complete Guide](PhaseStudio_Superflip_SharpED_Complete_Guide.pdf).

<!-- PAGE {"title": "11 · Inspect and save the result · enlarged view", "image": "screenshots/standalone/local-run-completed.png", "landscape": true, "crop": null, "caption": "Actual completed Superflip + EDMA demonstration; synthetic input does not imply independent experimental validation."} -->
Enlarged genuine application capture. For meaning, settings and fixture limitations, read the preceding page.

<!-- PAGE {"title": "Common problems · local tools and input", "image": "screenshots/standalone/setup-edma.png"} -->
**Superflip/EDMA not found:** use the corresponding setup step and locate the authors' real program. An active Jana installation normally already provides the tools. Do not select a Phase Studio launcher as Superflip or replace Jana-owned programs.

**Found but incompatible / cannot launch:** choose a compatible installation and repair missing supporting runtime files. Phase Studio does not accept a file solely because its name ends in `.exe`.

**Unsupported input / missing metadata:** check Input mode, HKL format, cell, symmetry and composition. Empty/manual unset fields are not valid crystallographic metadata. Validate HKL before running.

**No atomic sites:** inspect the map and selected threshold, whether EDMA was enabled and whether extraction completed. Adjusting a completed candidate reruns EDMA only. Do not assume empty output means a correct absence of atoms.

<!-- PAGE {"title": "Common problems · access and diagnostics", "image": "screenshots/standalone/service-unavailable.png"} -->
**Missing key:** open Account access and follow the verified token-page procedure. **Invalid key:** replace it with a newly generated key from the proper account; do not send passwords or keys in a support report.

**Account permission denied:** a key and a reachable catalogue do not prove inference entitlement. Check the provider's current access conditions. **Service unavailable/network error:** retry later or check the connection; these errors are not evidence that the scientific input is wrong.

Detailed logs belong to the selected project/run directory; the normal Execution Log is a compact summary. Jana integration writes project-local diagnostics, not `C:\Jana2020\SUPERFLIP`. Open log reveals the active file. Review/redact credentials, local usernames and unpublished data before sharing it.

<!-- PAGE {"title": "Useful links and attribution", "image": null} -->
[Phase Studio repository](https://github.com/ji-ze/Phase-Studio) · [Public releases](https://github.com/ji-ze/Phase-Studio/releases) · [Issue tracker](https://github.com/ji-ze/Phase-Studio/issues)

[Jana2020](https://jana.fzu.cz/) · [SharpED token page](https://sharped.fzu.cz/sharp-ed) · [Official Superflip/EDMA distributions](https://superflip.fzu.cz/)

[Superflip licence](https://superflip.fzu.cz/download/license_superflip.txt) · [EDMA licence](https://superflip.fzu.cz/download/license_EDMA.txt) · [Phase Studio MIT licence](https://github.com/ji-ze/Phase-Studio/blob/main/LICENSE)

**SharpED terms:** read the current terms shown by the provider. The project supplied `SharpED_Online_Service_and_API_Terms_2026-10-13_FINAL.pdf`, but no independently verified direct public terms URL is available for this edition. No guessed terms link is included.

**Software author:** Jiří Zelenka, Institute of Physics of the Czech Academy of Sciences. **SharpED developers, separately:** Jiří Zelenka, Jan Rohlíček, Monika Kučeráková and Zdeněk Buk, at the same institute.

Phase Studio uses the MIT licence. Scientific citation guidance is separate from the licence: cite the software version you actually used, its author, institute and repository, together with relevant Superflip, EDMA and Jana references. No new Phase Studio DOI is asserted.

PDF body fonts are the openly licensed DejaVu Sans family. Screenshots preserve the authentic application wordmarks. No proprietary font files are distributed with these guides.

[Getting Started with Jana2020](PhaseStudio_FirstUse_Jana2020.pdf) · [Complete workflow and settings guide](PhaseStudio_Superflip_SharpED_Complete_Guide.pdf)
