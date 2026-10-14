"""Author the illustrated tutorial Markdown from verified source inventories.

The resulting Markdown is the editable document source. PDF rebuilding reads
it directly; rerun this authoring tool only when intentionally refreshing prose.
"""
from pathlib import Path
import json
from collections import defaultdict

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/"docs/tutorials"
SOURCE=BASE/"sources"
SOURCE.mkdir(parents=True,exist_ok=True)
def page(title,text,image=None,**meta):
    return dict(title=title,text=text,image=image,**meta)
def write(name,title,subtitle,pages):
    lines=[f"# {title}",f"## {subtitle}","", "<!-- DOCUMENT "+json.dumps(dict(version="2.0.3",edition="Development-source review edition",filename=name),ensure_ascii=False)+" -->",""]
    illustrated=[]
    for entry in pages:
        illustrated.append(entry)
        if entry.get("landscape") and entry.get("image"):
            illustrated.append(page(entry["title"]+" · enlarged view", "Enlarged genuine application capture. For meaning, settings and fixture limitations, read the preceding page.",entry["image"],landscape=True,crop=entry.get("crop"),caption=entry.get("caption","Actual application UI; synthetic teaching input / labelled demonstration state.")))
    pages=illustrated
    for p in pages:
        text=p.pop("text");lines += ["<!-- PAGE "+json.dumps(p,ensure_ascii=False)+" -->",text.strip(),""]
    source_name={"PhaseStudio_FirstUse_Standalone.pdf":"first_use_standalone.md", "PhaseStudio_FirstUse_Jana2020.pdf":"first_use_jana2020.md", "PhaseStudio_Superflip_SharpED_Complete_Guide.pdf":"superflip_sharped_complete.md"}[name]
    (SOURCE/source_name).write_text("\n".join(lines),encoding="utf8")

S="screenshots/standalone/"
J="screenshots/jana2020/"
W="screenshots/workflow/"
WEB="screenshots/web/"
VERSION="""**Read this version note first.** These guides show the current 2.0.3 development-source interface, checked on 14 October 2026. The public release currently provides **v2.0.2**, with `PhaseStudio-2.0.2-x64.exe`. Some 2.0.3 setup, authentication and layout details differ. There is no published 2.0.3 binary in the verified release listing. Do not rename a 2.0.2 file to pretend it is 2.0.3.

Application screenshots are actual PySide6 renders. The teaching reflections and structures are synthetic and shareable, not a private or experimentally validated structure. Catalogue, prediction and staged-progress examples are identified as illustrative fixtures. Only the local Superflip/EDMA demonstration was actually calculated.

**Review edition:** native Jana2020 launch/return screenshots are awaiting approved capture; the authenticated SharpED token controls have been captured and sanitised. Their missing images are identified rather than replaced with invented screens. This edition is not final publication acceptance."""
ROLES="""**Phase Studio** is free, open-source crystallographic desktop software. It coordinates calculations, displays candidate structures and retains scientific outputs.

**Superflip** solves the crystallographic phase problem using charge flipping. **EDMA** locates atomic sites in electron-density maps. They are local, independently distributed programs with their own licences.

**SharpED** processes density maps online using machine learning. It uses your existing Jana2020 account; a separate SharpED registration is not needed. Free Phase Studio software does not imply free service inference or account entitlement.

Treat every model as a candidate. Check chemistry, symmetry and agreement with the original measured reflections, then refine independently. A convincing picture or a high apparent score is not proof of correctness."""
TOKEN="""1. In Phase Studio, click **Open SharpED token page**. The official destination is [https://sharped.fzu.cz/sharp-ed](https://sharped.fzu.cz/sharp-ed).
2. If redirected, sign in on the website with your existing Jana2020 account. Never enter your Jana password into Phase Studio.
3. On the SharpED Tool page, find **API tokens for desktop application** and click **Show**.
4. Enter a descriptive **New token name**, for example `Phase Studio laptop`, and click **Create token**.
5. Copy the newly generated access key, return to Phase Studio and paste it into **SharpED access key**.
6. Click **Connect to SharpED** to continue your original workflow.

**Verified website capture:** the accompanying authenticated-page crop shows the actual **API tokens for desktop application**, **Show**, **New token name** and **Create token** controls. Account identity, browser details and the existing-token table are excluded. No token was created or copied during documentation capture."""
SECURITY="""The access-key field is masked. **Show/Hide** changes only visibility; do not expose a key in screenshots. **Remember access on this device** explicitly enables Windows Credential Manager storage; otherwise the key stays in memory for the session. **Replace access key** and **Remove saved access** manage that access. **Back** returns with scientific settings preserved.

Connect checks service/catalogue reachability and retains the supplied key. The public catalogue request does **not** prove inference entitlement or authenticated token validity. An authenticated processing request can still reject the key or account permission.

There is no automatic OAuth browser-to-desktop token delivery in this version. Copy and paste the key yourself. The account website and the client Public API host are different: keep the preset API configuration; do not replace it with the token-page URL.

Only send data that you are authorised to share with the remote service. Check current provider terms and entitlement before inference. No permanent free-access promise or price is made in this guide."""
LINKS="""[Phase Studio repository](https://github.com/ji-ze/Phase-Studio) · [Public releases](https://github.com/ji-ze/Phase-Studio/releases) · [Issue tracker](https://github.com/ji-ze/Phase-Studio/issues)

[Jana2020](https://jana.fzu.cz/) · [SharpED token page](https://sharped.fzu.cz/sharp-ed) · [Official Superflip/EDMA distributions](https://superflip.fzu.cz/)

[Superflip licence](https://superflip.fzu.cz/download/license_superflip.txt) · [EDMA licence](https://superflip.fzu.cz/download/license_EDMA.txt) · [Phase Studio MIT licence](https://github.com/ji-ze/Phase-Studio/blob/main/LICENSE)

**SharpED terms:** read the current terms shown by the provider. The project supplied `SharpED_Online_Service_and_API_Terms_2026-10-13_FINAL.pdf`, but no independently verified direct public terms URL is available for this edition. No guessed terms link is included.

**Software author:** Jiří Zelenka, Institute of Physics of the Czech Academy of Sciences. **SharpED developers, separately:** Jiří Zelenka, Jan Rohlíček, Monika Kučeráková and Zdeněk Buk, at the same institute.

Phase Studio uses the MIT licence. Scientific citation guidance is separate from the licence: cite the software version you actually used, its author, institute and repository, together with relevant Superflip, EDMA and Jana references. No new Phase Studio DOI is asserted.

PDF body fonts are the openly licensed DejaVu Sans family. Screenshots preserve the authentic application wordmarks. No proprietary font files are distributed with these guides."""

standalone=[
page("Before you begin",VERSION),
page("What each program does",ROLES,S+"standalone-input.png",crop="configuration"),
page("1 · Download the Windows application","""Open the [verified v2.0.2 release](https://github.com/ji-ze/Phase-Studio/releases/tag/v2.0.2). Find the Assets section and download **PhaseStudio-2.0.2-x64.exe**. The standalone Windows x64 ONEFILE includes its Python/Qt runtime; no separate Python installation is needed.

Use a compatible Windows x64 machine (Windows 10 1903 or newer, or Windows 11). Check the release's own requirements and filename. This guide's updated 2.0.3 screens are source previews, not a claim that this download contains those changes.

Do not download an obsolete separate Jana installer for this standalone exercise. If Windows raises a security warning, verify the official repository, release and file integrity first. Use a provider-published SHA-256/signature where available; calculating your own hash alone does not establish authenticity. The current public release API lists only the EXE, not a separate checksum asset. Its published asset SHA-256 is `139886f97ccc743ab360fd48a0d36ae43697523763d660d7c567afa6c6dee55e`. In PowerShell run `Get-FileHash .\\PhaseStudio-2.0.2-x64.exe -Algorithm SHA256` and compare all digits before launch. Do not bypass warnings blindly.""",WEB+"github-assets.png",crop="github-assets",caption="Live public v2.0.2 release page. The guide’s source UI version is 2.0.3."),
page("2 · Launch and recognise the main window","""Launch the downloaded EXE from a trusted location. The main window contains **Basic** and **Advanced** configuration, the run actions, progress/metrics, structure viewers and Execution Log.

Opening Phase Studio does not start a calculation. Start with **Basic → Input**. **Run phasing** starts a configured workflow; **Continue run** is for a compatible interrupted run with saved state. Leave continuation and advanced settings alone for your first exercise.

The working directory belongs to your project and stores generated inputs, maps, structures, metrics and logs. Keep it separate from the application installation directory.""",S+"standalone-input.png",landscape=True),
page("3 · Locate Superflip and EDMA","""Superflip is required for charge-flipping structure solution. EDMA is required when the selected workflow extracts atomic sites from density maps. A purely local Superflip + EDMA calculation does not need SharpED access.

Phase Studio validates an explicit path first, then the active Jana installation when applicable, a persistent managed installation, supported known locations and finally PATH. Bare legacy program names are PATH discovery, not priority over active Jana. Compatible installed tools are detected before a setup dialog appears.

For a missing tool, click **Official download page**, follow the authors' installation/licence instructions, and return to **Locate existing Superflip/EDMA**. Select the actual program file. Phase Studio checks identity, runtime and a bounded launch, then resumes the original request. Filename alone is insufficient. **Back** returns without skipping a required tool.

**Automatic installation is unavailable in this source version:** approved distribution integrity and automated-download permission are not established. No Download and set up promise is made.""",S+"setup-both.png",caption="Actual combined setup dialog. It appears only for local tools needed by the requested workflow."),
page("4 · Open the SharpED account step",TOKEN,WEB+"sharped-token-controls.png"),
page("5 · Sign in only on the website","""The browser may first show this Jana2020 login page. Use your existing Jana identity and sign in there, not inside Phase Studio. The pictured fields are deliberately empty.

After sign-in, follow the token-section procedure on the previous page. The preceding page includes a sanitised authenticated token-control crop; no token is included.

You can skip connecting to SharpED when running a local workflow with **Run SharpED** disabled. You cannot skip it when the selected workflow genuinely requires remote processing.""",WEB+"jana-login.png",crop="web-login",caption="Actual public Jana login page, captured with a fresh browser profile; no credentials entered."),
page("6 · Keep the key private",SECURITY,S+"connect-sharped.png",crop="account-controls"),
page("7 · Select the demonstration input","""Use the accompanying **demo/tutorial_intensity.hkl** and **demo/tutorial_reference.cif**. These are generated synthetic reflections and a mathematical six-carbon ring in P1; they are not a measured or validated structure.

Choose **Input mode: External HKL + CIF reference**, select the HKL, choose **HKL format: h k l · I · σ(I)**, and use **Metadata source: Reference structure** with the supplied CIF. The CIF supplies the 10 × 10 × 10 Å cell, 90° angles, P1 and C6 composition.

The **Reference model** supplies metadata/evaluation context; it is not automatically the **Initial model (cycle 1)**. Leave that initial-model field empty for this demonstration. Validate the interpreted columns before phasing. Your real experiment must use its own correct cell, symmetry, composition and column meaning.""",S+"standalone-input.png",crop="configuration"),
page("8 · Validate the HKL interpretation","""Click **Validate HKL**. Check parsed/unique counts, indices, values, uncertainty and any phase column. A successful parse means the selected format can be read; it does not certify measurement quality, correctness of the space group or completeness.

For the teaching file, the displayed values are synthetic intensities with σ(I). **F** is an amplitude, **I** is an intensity, and **FWHM** is a peak width. Choose the format that matches your file, not whichever gives a desirable score.

**Analyze completeness** checks coverage within the observed reciprocal-space/resolution range using the selected symmetry. The complete guide explains its plots and limitations.""",W+"hkl-validation.png",crop="validation"),
page("9 · Configure a short local run","""For the first teaching calculation choose **Phasing method: Superflip**, **Cycles: 1**, enable **Run EDMA on Superflip map**, and disable **Run SharpED** and **Run EDMA on SharpED map**. Use **Output → Working directory** for a new project folder.

For a fast synthetic exercise, set **Advanced → Superflip → Maximum iterations: 100**, **Repeat mode: 1**, and **Voxel grid: 32 32 32**. These demonstration limits are not recommended defaults for a real structure solution. The real local capture used **Normalization: none**. Normal full-configuration defaults differ and are documented in the complete guide.

Click **Run phasing**. This produces a candidate map/model; completion is not a guarantee of a chemically correct six-site solution. For a combined run, enable Run SharpED, connect your account and read the Complete Guide first.""",S+"standalone-workflow.png",crop="configuration"),
page("10 · Watch the calculation","""The run status shows overall workflow progress and the current operation. Superflip may perform several internal iterations/trials inside one Phase Studio cycle. Completed structures can appear before all work is finished.

Use **Execution Log**, **Expand log** and **Open log** for diagnostics. **Stop after current cycle** requests a graceful stop; **Stop immediately** cancels active work. A completed candidate remains distinct from a partially running stage.

The image comes from an actual local Superflip/EDMA calculation on the public synthetic file, with no SharpED request.""",S+"local-run-active.png",landscape=True,caption="Genuine local calculation; any personal diagnostic paths are explicitly redacted."),
page("11 · Inspect and save the result","""Review the **Charge-flipping solution** and its EDMA model. Rotate/pan/zoom, and use Fit to inspect the full displayed structure. A lower EDMA threshold can reveal more sites, but noise peaks do not become chemically correct atoms merely because they are visible.

After completion, **Save map and model** exports the available result using supported selected formats. Generated scientific inputs, internal XPLOR maps/CIF structures and metrics remain in the working run folder. **Output → Map format/Structure format** controls additional exported formats; it does not replace required internal workflow files.

A standalone session has no incoming Jana return context. It must not hand results to an arbitrary Jana project. Use the Jana-integrated guide for a context-preserving return.

For cycles, model choice, Map Feedback, viewer controls and scientific scores, see [the Complete Guide](PhaseStudio_Superflip_SharpED_Complete_Guide.pdf).""",S+"local-run-completed.png",landscape=True,caption="Actual completed Superflip + EDMA demonstration; synthetic input does not imply independent experimental validation."),
page("Common problems · local tools and input","""**Superflip/EDMA not found:** use the corresponding setup step and locate the authors' real program. An active Jana installation normally already provides the tools. Do not select a Phase Studio launcher as Superflip or replace Jana-owned programs.

**Found but incompatible / cannot launch:** choose a compatible installation and repair missing supporting runtime files. Phase Studio does not accept a file solely because its name ends in `.exe`.

**Unsupported input / missing metadata:** check Input mode, HKL format, cell, symmetry and composition. Empty/manual unset fields are not valid crystallographic metadata. Validate HKL before running.

**No atomic sites:** inspect the map and selected threshold, whether EDMA was enabled and whether extraction completed. Adjusting a completed candidate reruns EDMA only. Do not assume empty output means a correct absence of atoms.""",S+"setup-edma.png"),
page("Common problems · access and diagnostics","""**Missing key:** open Account access and follow the verified token-page procedure. **Invalid key:** replace it with a newly generated key from the proper account; do not send passwords or keys in a support report.

**Account permission denied:** a key and a reachable catalogue do not prove inference entitlement. Check the provider's current access conditions. **Service unavailable/network error:** retry later or check the connection; these errors are not evidence that the scientific input is wrong.

Detailed logs belong to the selected project/run directory; the normal Execution Log is a compact summary. Jana integration writes project-local diagnostics, not `C:/Jana2020/SUPERFLIP`. Open log reveals the active file. Review/redact credentials, local usernames and unpublished data before sharing it.""",S+"service-unavailable.png"),
page("Useful links and attribution",LINKS+"\n\n[Getting Started with Jana2020](PhaseStudio_FirstUse_Jana2020.pdf) · [Complete workflow and settings guide](PhaseStudio_Superflip_SharpED_Complete_Guide.pdf)")]

jana=[
page("Before you begin",VERSION),
page("Phase Studio is supplied with integrated Jana",ROLES+"\n\nThis guide is for a Jana2020 distribution containing the preinstalled Phase Studio integration. You do not install a separate Phase Studio Jana installer. If your Jana distribution lacks the component, obtain the integrated distribution/update from its provider rather than using an obsolete installer.",J+"wizard-input.png",crop="wizard-summary"),
page("1 · Know the supplied tool layout","""The expected installed layout is:

`<JanaRoot>/SUPERFLIP/superflip.exe`

`<JanaRoot>/SUPERFLIP/EDMA.exe`

Phase Studio's integration may reside in `<JanaRoot>/SharpED/Phase_studio.exe` with its `_internal` runtime kept alongside it. The actual Jana root may be on any supported drive/location.

**Jana users normally do not need to download or configure Superflip and EDMA separately.** Phase Studio searches relative to the active Jana root, validates the supplied tools and proceeds silently when they work. It does not look under `SharpED/SUPERFLIP` or substitute an unrelated legacy original file.

If setup appears, use Back and check the installed Jana distribution/runtime. Locate a valid existing tool only if necessary. Do not manually overwrite Jana's scientific executables.""",S+"setup-superflip.png",caption="Troubleshooting state, not a normal installation requirement for a correctly integrated Jana distribution."),
page("2 · Launch from your Jana project","""Open your intended Jana2020 project and prepare its crystallographic structure-solution input using that Jana distribution's documented integration action. Jana supplies the incoming `.inflip` and original project context; Phase Studio opens **JANA2020 WORKFLOW**.

**Native screenshot acceptance gap:** a current, approved native Jana launch/menu capture has not been supplied. The installed machine's legacy integration is not asserted to be a verified 2.0.3 GUI path. No exact Jana menu label is invented in this guide. The distributable edition needs the actual menu/action screenshot and its verified wording.

Check the displayed incoming filename before continuing. Do not reuse a standalone session or a different project's saved context for returning results to Jana.

For integrators only: Jana invokes the supplied Phase_studio executable with its actual project `.inflip`, keeping the project as the scientific working context. This is not a separate installer instruction.""",J+"wizard-input.png",caption="Genuine Phase Studio Wizard on synthetic Jana-format input. This does not replace the missing native Jana launch capture."),
page("3 · Read Input Summary","""Check **Jana2020 input**, **Reflections**, **Format**, **Cell**, **Space group** and **Superflip input composition**. Parsed rows and unique reflections have different meanings; symmetry/Friedel merging can change the unique count.

The displayed cell and space group come from the interpreted input context. Search composition helps Superflip/EDMA; it need not equal the final EDMA-detected asymmetric-unit composition.

Expand **Show optional reference and initial model** only when needed. Reference and initial model have different roles. A reference aids metadata/evaluation; an explicit first-cycle model can supply a seed. Do not infer random phases merely from the phrase cycle 1.""",J+"wizard-input.png",crop="wizard-summary"),
page("4 · Validate the reflections","""Click **Validate HKL** and check the interpreted columns and counts. Successful parsing is a format/context check, not an experimental validation certificate.

**h k l · F · σ(F):** amplitude and amplitude uncertainty. **h k l · I · σ(I):** intensity and intensity uncertainty. **h k l · I · FWHM:** intensity and peak width. FWHM is not σ(I), so I/FWHM must not be interpreted as a significance ratio.

Phase columns use the selected displayed convention; the client converts degrees for its generated Superflip representation. Do not guess a phase/uncertainty column from its numerical size.""",W+"hkl-validation.png",crop="validation"),
page("5 · Analyze completeness","""Click **Analyze completeness**. Inspect resolution bins, completeness versus sinθ/λ, dmin, observed/theoretical unique-reflection counts and available intensity/uncertainty statistics.

The calculation depends on the selected cell, symmetry, observed bounds and resolution range. High completeness over that range does not establish correct measurements, correct symmetry or a correct model. Check bin coverage, not only one total percentage.

Significance plots require appropriate uncertainty data; FWHM-only data do not provide experimental σ(I). Statistics labelled for a width format must not be reused as I/σ(I).""",W+"hkl-completeness.png"),
page("6 · Select the workflow","""**Superflip only:** conventional local charge-flipping solution; no SharpED account is needed for that local path.

**Superflip + SharpED:** charge flipping with remote neural-network map processing and supported iterative feedback/seeding.

**SharpED Autosolve · Experimental:** a distinct automated search/review policy. It has its own models and 1.00σ extraction defaults; do not transfer the normal 0.50σ policy to it.

**Professional mode:** opens full configuration without starting automatically. Configure it, then use manual Run phasing. It is not required merely to locate a missing executable.

Options needing inference require the existing Jana identity, an access key and applicable provider permission. The current four tiles are shown below.""",J+"wizard-input.png",crop="wizard-workflows"),
page("7 · Connect your existing Jana account",TOKEN,WEB+"sharped-token-controls.png"),
page("8 · Protect the access key",SECURITY,WEB+"jana-login.png",crop="web-login"),
page("9 · Choose cycles and model","""For normal combined Wizard processing, **Number of cycles** sets the outer Superflip/SharpED cycle budget. One cycle automatically recommends **PEAK A (model prediction)**; two or more recommend **SEED (cyclic CF)** when those exact IDs exist in the live catalogue.

Selecting a model explicitly creates a manual override. **Restore automatic** returns to the cycle policy. **Refresh** has the accessible name Refresh models and queries the current catalogue; available models are dynamic.

The next Map Feedback page controls optional derived reflection input for later cycles. Leave its optional methods disabled for a simple unmodified-data run. More cycles cost more time and do not guarantee improvement.""",W+"configuration-multi-cycle.png"),
page("10 · Follow execution","""The execution window separates **Charge-flipping solution** from **Model prediction**. It shows cycle/progress, current operations, log and completed structures. Work can overlap: EDMA for one completed map or a SharpED request may be active while another operation progresses.

Use the two panels independently. A completed candidate is not replaced by unfinished output. Graceful stopping after a cycle retains completed candidates for review. Wait for any selected interactive EDMA request to finish before handoff.

This combined-window image is an explicitly illustrative lifecycle fixture; no authenticated inference was performed for it.""",W+"execution-concurrent.png",landscape=True,caption="Actual execution UI with a synthetic progress/prediction fixture, not a live neural-network job."),
page("11 · Select the intended result","""After a successful Wizard-launched workflow, **Result Selection** opens automatically. In Professional/full configuration, there is no automatic run; after manual completion, **Pass to Jana2020** opens the same selector.

Choose **Charge-flipping solution** or **Model prediction**, then the intended cycle row. The recommendation star is advice within that result family. Your selected row can differ from the recommendation.

Read provenance, EDMA threshold, detected/ASU counts and **Jana model** count. The displayed structure may contain symmetry images and is not necessarily the exact atom-count list imported into Jana.""",W+"selector-model-prediction.png",landscape=True,caption="Actual selector with synthetic candidate/model and metric fixtures; no Jana transfer is executed."),
page("12 · Finish threshold review","""Use **+ atoms** to lower the detection threshold and **− atoms** to raise it. At the normal 0.50σ setting, the next steps are 0.40σ and 0.60σ. The step becomes smaller below 0.30σ; guided interactive limits are 0.10–3.00σ.

Threshold changes rerun EDMA on the unchanged selected scientific map, not Superflip or SharpED. The Pass action is disabled while the requested candidate-specific extraction is pending.

More detected sites do not guarantee better chemistry. A composition-constrained Jana model may keep the same atom list even when the raw EDMA/CIF peaks change. Use the completed candidate/threshold and check the reported Jana model count.""",W+"selector-edma-pending.png",landscape=True,caption="Actual pending-extraction UI state, driven by an explicit asynchronous fixture."),
page("13 · Pass to Jana2020","""Confirm the chosen family, cycle and completed threshold, then click **Pass to Jana2020**. Phase Studio validates the chosen scientific map and corresponding model and publishes them in the original Jana project context. It does not pass a preview image or restart phasing/inference during return.

The map and atomic model must retain the same crystallographic frame. The original Jana context supplies expected names; you should not rename a preview or manually substitute files in the installation directory.

Continue the project in Jana and check the imported atoms against density, symmetry and the original experiment before refinement.

**Native return acceptance gap:** this edition has no approved screenshot of the selected map/model imported in Jana and normal continuation. Automated/file tests are not presented as native GUI acceptance. That capture and a real-machine handoff check are required before public acceptance of this tutorial.""",W+"selector-manual-candidate.png",landscape=True,caption="Actual Phase Studio selection UI. A native Jana return image is explicitly missing."),
page("Troubleshooting Jana workflows","""**Setup unexpectedly appears:** check the active installation's SUPERFLIP files and complete Phase Studio runtime. Do not replace them with an unrelated launcher.

**Wrong incoming project:** Back/Cancel and relaunch from the intended Jana project; do not use a stale standalone context.

**Pass disabled:** check that the candidate is completed, its scientific map/model exists and any interactive EDMA request has finished. Immediate cancellation is different from a graceful stop after a completed cycle.

**Different atom counts:** distinguish independent EDMA sites, ASU composition, symmetry-expanded displayed atoms and Jana model sites. More peaks need not mean a changed Jana model.

**Logs:** use Open log for project/run diagnostics. Logs do not belong in the installed SUPERFLIP directory. Redact private data before support.

See [the Complete Guide](PhaseStudio_Superflip_SharpED_Complete_Guide.pdf) for every setting and metric limitation."""),
page("Useful links and attribution",LINKS+"\n\n[Standalone first use](PhaseStudio_FirstUse_Standalone.pdf) · [Complete Guide](PhaseStudio_Superflip_SharpED_Complete_Guide.pdf)")]

complete=[
page("Edition, evidence and limitations",VERSION),
page("The workflow in one page",ROLES+"\n\nOne normal cycle runs charge flipping, produces a scientific map, processes it with SharpED when enabled, and extracts structures with EDMA according to selected options. A later cycle can receive a completed map/model seed and optionally derived reflections. These are separate mechanisms: map/model seeding is not the same as altering measured reflection input.",W+"execution-completed.png",landscape=True,caption="Actual GUI; combined processing state and scores are illustrative fixtures."),
page("1 · Verify input and optional models","""Read Input Summary and expand optional files only when needed. The incoming .inflip supplies the Jana context; standalone external HKL requires validated manual/reference metadata.

Input composition is the Superflip search composition. EDMA ASU composition is calculated from the selected candidate; it is not a relabelled search composition.

A **Reference model** is evaluation/metadata context; **Initial model (cycle 1)** supplies a deliberate seed. An initial model may change cycle 1 from random phases. Later-cycle provenance identifies the actual reused source; cycle number alone cannot prove which seed was used.""",J+"wizard-input.png",crop="wizard-summary"),
page("2 · Validate HKL before phasing","""Validate HKL reports how rows/columns, uncertainties, phases and symmetry-unique reflections were interpreted. Check the selected layout and samples, not only a green status.

Amplitude formats use F and σ(F); intensity formats use I and σ(I). Intensity is converted to amplitude when required by crystallographic comparisons; phase-bearing formats keep their specified convention. FWHM formats store a peak width and do not supply a significance uncertainty.

Standalone manual metadata needs positive cell lengths, angles strictly between 0° and 180°, a resolvable space group and composition. Manual empty/Not set values are not physical metadata.""",W+"hkl-validation.png",crop="validation"),
page("3 · Understand completeness","""Analyze completeness enumerates theoretical symmetry-unique reflections within the observed reciprocal-space/resolution bounds and compares observed unique coverage in sinθ/λ bins. It reports dmin and the available coverage/statistical summaries, including the 98% cumulative point where defined.

Intensity/uncertainty curves depend on the selected format and available uncertainty. A width column cannot substitute for σ(I). Coverage outside the analyzed bounds is not demonstrated by the plot.

Use completeness to identify gaps and format/context issues. It does not independently validate phases, chemical connectivity or a neural prediction.""",W+"hkl-completeness.png"),
page("4 · One cycle versus multiple cycles","""**Number of cycles** is 1–999 in the Wizard; its fresh combined-workflow Wizard default is 5, matching full configuration; Superflip-only recommends 1. Saved settings and imported context can override these values. One cycle is a single pass and cannot apply feedback to a later cycle.

Multiple cycles repeat the outer scientific stages. The first may use random phases or an explicit initial model; subsequent runs may use a completed SharpED map, another supported map, a structure seed or no seed according to actual configuration/provenance.

Superflip's **Maximum iterations** and **Repeat mode** are internal budgets, not the outer cycle count. When a model file seeds a Superflip cycle, the generated-input code forces repeatmode to 1. Do not multiply a displayed repeat preference blindly by every seeded cycle.

More cycles/trials take longer. Inspect candidates and independent diffraction agreement; extra computation is not proof of a better solution.""",W+"configuration-one-cycle.png"),
page("5 · Automatic model selection","""In the normal combined Wizard: 1 cycle → **PEAK A (model prediction)**; 2 or more → **SEED (cyclic CF)**, using exact catalogue IDs. The displayed catalogue is fetched dynamically and is not a permanent model list.

**Refresh** queries available models; its accessible name is Refresh models. The GUI reports the number available and any policy/catalogue error. If the required automatic model is unavailable, correct that condition rather than inventing a substitute.

Professional/full configuration has its own **Model: default** option, which resolves the server default. Do not mistake that explicit server-default choice for the Wizard's automatic PEAK A/SEED cycle policy.""",W+"configuration-multi-cycle.png"),
page("6 · Manual model selection","""Choosing a model in the dropdown marks it **Manually selected**. Changing cycle count does not replace an available manual override. **Restore automatic** opts back into the cycle policy.

On refresh, a manual choice is preserved if the exact model remains available. If it disappears, the current implementation restores automatic mode and displays the removal notice. Do not assume the same catalogue exists on every date.

Model choice affects remote inference and may affect seeds/derived data used by later cycles. It is not merely a colour or camera preference. Model names do not reveal a scientifically verified architecture/training explanation; use provider documentation for those details.""",W+"configuration-manual.png"),
page("7 · Wizard SharpED settings","""The actual disclosure is **Advanced SharpED settings**. It exposes a masked **SharpED access key** and **Account access…**. The normal Wizard does not expose a server URL editor, output-resolution editor, element constraints or RS/BL controls.

Account access opens the reusable Connect dialog without launching a scientific workflow. The key is session-only unless explicitly remembered securely. Back/browser round trips preserve the configured scientific fields.

For output sampling, elements, value transform and network controls, use **Professional mode → Advanced → SharpED** when that broader configuration is required. Do not invent desktop fields from web-only options.""",W+"wizard-sharped-settings.png"),
page("8 · Generate the SharpED access key",TOKEN,WEB+"sharped-token-controls.png"),
page("9 · Authentication and entitlement",SECURITY,WEB+"jana-login.png",crop="web-login"),
page("10 · Advanced inference controls","""**Elements:** blank derives unique non-H elements from the configured composition/reference; an explicit element list constrains the submitted inference request. Check chemistry rather than restricting elements to force a desired answer.

**Output resolution (Å):** 0.001–10.0; constructor default 0.2. It is sent as `outres`. The client describes requested sampling/resolution; it does not establish that the network creates new experimental information. Detailed server interpretation requires provider clarification.

**Map value exponent:** 0–10; the live default is listed in the parameter reference. A signed power transform sign(x)|x|^a is applied before submission and inverted on the returned map. 1 is identity; 0 disables the transform. It changes voxel values for processing, not cell/grid/origin. A changed exponent can still change the nonlinear inference output.

No RS/BL fields are present in this desktop configuration. Their scientific meaning is not guessed here.""",W+"professional-sharped.png",crop="configuration"),
page("11 · Transfer and network limits","""**Upload limit (MB):** 0–100000, default 100; 0 disables the client's limit check. If the voxel grid was omitted, the workflow can choose a coarser native grid before map calculation to fit the limit. Oversized maps may use the existing tiled submission/reassembly path; do not assume this changes the scientific frame.

**HTTP timeout (s):** 600–7200, default 600. **Polling interval (s):** 1–3600, default 2. **Maximum polls:** −1–1000000, default −1 (Unlimited). These affect waiting/transport, not the charge-flipping mathematics; too short a wait/limit may fail a legitimate long inference.

Keep the preset API endpoint. The token website is `https://sharped.fzu.cz/sharp-ed`; the current client Public API defaults to `https://jana.fzu.cz/`. Some inherited tooltips mention the web host; the actual client constant and request code are authoritative.""",W+"professional-sharped.png",crop="configuration"),
page("12 · Map Feedback changes later input","""Map Feedback uses a completed processed map to prepare derived reflections for subsequent cycles. The original measured dataset and frozen validation context remain distinguishable from the derived HKL files. It is not the same as supplying a next-cycle phase seed.

Methods are optional and initially off. **Start after cycle** means the completed cycle whose map first feeds the next one; useful choices need a subsequent cycle. In the Wizard the maximum is the preceding cycle of the budget. For one cycle the controls are unavailable while remembered values are retained.

When both supported methods are enabled, the implemented order is missing completion/intensity correction, then powder overlap repartitioning, then write the next-cycle input. Validate every changed-input result against the original measurement, not just the derived input.""",W+"feedback-one-cycle-disabled.png"),
page("13 · Missing-reflection completion","""**Enable missing-reflection completion:** off by default. **Start after cycle:** default 1; outer-cycle dependent. **Maximum added reflections (%):** 0–100, default 0.

Candidate missing HKLs are selected within the existing observed index bounds and resolution limit. Positive map-predicted intensities are scaled to the observed data and ranked; additions are capped by the specified fraction of the current count. Zero percent adds no reflections, even if the checkbox is on.

These are inferred values, not newly measured reflections. Additions can influence later cycles and must not be treated as independent observations validating the model that supplied them.""",W+"feedback-missing-reflections.png"),
page("14 · Weak-reflection correction with σ","""**Enable weak-reflection intensity correction** is off initially. **Start after cycle** defaults to 1. **Correction damping** is 0–1, default 0. A positive **Apply when value/σ <** threshold selects eligible positive finite values with finite positive matching uncertainty.

For I/σ(I) data the filter is I/σ(I). For F/σ(F) data it is F/σ(F), not a renamed intensity ratio. The correction itself blends intensities, with F converted through its intensity representation and converted back.

Inew = (1 − d)Iobs + d × scaled Imap. The scale uses the median of positive observed/predicted intensity ratios. d=0 is no correction; d=1 uses the scaled map prediction for eligible rows. A significance cutoff is strict: a ratio equal to the threshold is not selected.

Use a nonzero cutoff only when the input actually supplies the correct experimental uncertainty.""",W+"feedback-single-crystal.png"),
page("15 · Threshold zero and width-only data","""**Apply when value/σ < = 0** means uncertainty-independent correction, not I/σ(I)<0. It bypasses the significance test and applies where the map predicts a positive intensity. The implementation can also affect zero observed values; do not interpret older “non-zero reflections” copy as a restriction excluding them.

For **h k l · I · FWHM**, no σ(I) is supplied. The significance field is unavailable; the verified threshold-zero correction remains possible with positive damping. FWHM is never silently used as an experimental uncertainty.

The powder screenshot states the missing-uncertainty condition explicitly. This is a distinct mode, not evidence that every weak-reflection operation is valid for every format.""",W+"feedback-powder.png"),
page("16 · Powder overlap repartitioning","""Available only for supported FWHM formats. **Enable powder overlap repartitioning (FWHM data)** is off initially. **Start after cycle** defaults to 1. **Wavelength (Å)** is 0–10, default 0 (automatic); the resolved value must be positive.

Automatic wavelength uses the relevant Jana .m90, then input wavelength declarations, then the reference wavelength where available. Enter the actual experiment's wavelength if it cannot be resolved. The pictured 1.00000 Å is a synthetic teaching value.

**Separation factor:** 0.001–100, default 0.2. Adjacent Bragg peaks are grouped transitively when Δ(2θ) < factor × (FWHM1+FWHM2)/2; widths must use consistent angular units.

**Map ratio mix:** 0–1, default 1. It blends observed within-group shares with shares implied by map-predicted intensities. Zero retains observed shares; one uses predicted shares. Each overlap group's total observed intensity is conserved. This still changes individual reflection inputs for later cycles.""",W+"feedback-powder.png",crop="powder-controls"),
page("17 · Cross-validation is an opt-in","""**Compute OMIT validation maps** is unchecked for a fresh Wizard job and is not silently inherited from old job settings. It freezes a symmetry/Friedel-orbit-safe 5% holdout and excludes those HKLs from all work-data/feedback stages of the omit branch.

**Calculate R_free** follows the OMIT choice automatically and is not independently editable in that Wizard state. Extra omit Superflip/SharpED work roughly increases the per-cycle cost; exact time depends on the job.

The holdout must genuinely be withheld. Metrics of an arbitrary imported map that may have used those reflections are not automatically independent. In full configuration these are the corresponding Optional processing settings; preserve their actual dependency rules.""",W+"configuration-multi-cycle.png"),
page("18 · EDMA threshold and atomic sites","""Normal Charge-flipping solution and Model prediction extraction defaults are **0.50σ**. The threshold is applied relative to the map's standard-deviation scale in the generated EDMA workflow, not as a probability that a peak is an atom.

**+ atoms** lowers the threshold; from 0.50σ it requests 0.40σ. **− atoms** raises it to 0.60σ. Step policy is 0.20σ at/above the 0.80σ boundary, 0.10σ below it and 0.05σ below 0.30σ, with direction-aware boundary handling and guided range 0.10–3.00σ.

Lower thresholds may reveal additional sites or noise. Higher thresholds may remove weak real sites. The interaction reruns EDMA only on the completed candidate's unchanged scientific map; it does not rerun Superflip/SharpED or silently change candidate family/cycle.""",W+"selector-edma-pending.png",landscape=True),
page("19 · Four different atom counts","""**Raw EDMA peaks** are extraction output before cleanup. **EDMA candidate sites** are the retained independent sites in the actual selected structure. **ASU composition** reduces that candidate using its symmetry. **Displayed atoms** may include periodic/symmetry images. **Jana model sites** are the composition-constrained list in the actual returned model.

These counts can differ legitimately. No display expansion creates independent measured atoms. More EDMA peaks after lowering a threshold do not imply that every new peak is written as a Jana atom.

If the Jana model is “prepared during handoff,” an exact count is not asserted yet. A completed/sealed model's reported count is authoritative. The screenshot deliberately illustrates a count distinction using fixture artifacts, not an accepted native Jana import.""",W+"selector-model-prediction.png",landscape=True),
page("20 · Read execution progress","""**Charge-flipping solution** is the Superflip map/EDMA result; **Model prediction** is the SharpED-processed map/EDMA result. The panels track their own selected completed source/cycle and camera.

Overall progress counts the outer workflow budget; current-operation progress identifies active stages. Superflip repeat progress is an internal trial counter. Server processing may have an indeterminate interval when no meaningful percentage is available.

Completed structures can appear during other work. Concurrent labels describe active operations, not a claim that every stage starts simultaneously. Use **Execution Log**, **Expand log** and **Open log** for current messages and project-local details.""",W+"execution-concurrent.png",landscape=True),
page("21 · Rotate, pan, zoom and Fit","""Drag with the left mouse button to rotate. Middle/right drag or Shift+left drag pans. The mouse wheel zooms the pointed panel. **Fit** reframes displayed content without changing orientation; **Reset view** restores the default camera. F and R are their keyboard shortcuts, and Space toggles Auto rotate where supported.

**Auto rotate** animates the camera, not atomic coordinates. Turn it off for careful comparison. **Fullscreen** opens the selected structure in a detached viewer retaining its current orientation; it does not create a new candidate.

Each result panel preserves its own camera during ordinary redraw. A different candidate/representation can warrant an automatic fit. Camera transformations never modify fractional coordinates, occupancy, symmetry or exported models.""",W+"viewer-complete-molecules.png",landscape=True),
page("22 · Complete molecules versus Full cell","""**Complete molecules** assembles compact periodic fragments from the selected density-derived sites for viewing. Atoms may cross unit-cell boundaries so the connected fragment can be inspected. It does not prove that a disconnected peak cloud is a chemically valid molecule; finite framework fragments have their own display policy.

**Full cell** shows the symmetry-expanded cell representation and unit-cell frame. Repeated/symmetry-related images are display atoms, not additional independent EDMA detections.

Use both views to inspect boundary connectivity, duplicates and symmetry. Neither changes the selected candidate's scientific coordinates or the returned Jana context.""",W+"viewer-full-cell.png",landscape=True),
page("23 · Browse completed candidates","""Use the available previous/next candidate controls to inspect completed cycles. **Latest** follows the newest completed candidate for that panel; it is not necessarily the recommended/best candidate. A manual selection can be inspected while another cycle runs.

Do not infer seed provenance from the row number. Read **Superflip initialization** and **Reflection input** metadata: an explicitly supplied first-cycle model, reused map/model or derived-reflection input changes scientific lineage.

A running threshold update does not replace the authoritative last completed candidate. Wait for its candidate-specific completion before passing the requested new threshold.""",W+"execution-completed.png",landscape=True),
page("24 · Choose a family and cycle","""Result Selection uses separate **Charge-flipping solution** and **Model prediction** families, with candidate cycle rows and an independent recommendation per family. A recommendation star does not lock your choice.

Click a row, then check selected-family/cycle summary, EDMA threshold, ASU composition, Jana model and provenance. Returning to Phase Studio is a review/navigation action, not a handoff.

The **Pass to Jana2020** action operates on the selected completed candidate, even when it differs from the recommendation. It remains unavailable for an incomplete/invalid/pending candidate. A standalone result context does not expose Jana handoff.""",W+"selector-manual-candidate.png",landscape=True),
page("25 · What R factor and Amplitude CC mean","""For finite nonnegative observed amplitudes Fo and Fourier-derived map amplitudes Fc, the client fits a nonnegative scale s = max(0, ΣFoFc/ΣFc²), then calculates R = Σ|Fo − sFc|/ΣFo. Fo comes from the frozen original measured reflections, including the existing intensity-to-amplitude conversion.

**Amplitude CC** is Pearson correlation of those same observed/calculated amplitude arrays; it is unavailable when there are too few pairs or insufficient variance. It is not an independent atomic refinement residual.

If Superflip imposed the observed amplitudes, R≈0 and CC≈1 can follow by construction even with incorrect phases. Different phase maps can have the same amplitude scores. Rounded equal scores need not be an internal ranking tie.

No universal correctness cutoff is supplied. Interpret these values with provenance, phase-sensitive information and independent crystallographic validation.""",W+"selector-charge-flipping.png",landscape=True),
page("26 · C3, holdout and recommendations","""**C3** is the weighted mean cos[φ(h)+φ(k)−φ(h+k)] from the map Fourier phases. Triplet weights are products of original measured amplitudes normalised by their RMS; the deterministic set is bounded by 64 strong seeds and 50,000 triplets. C3 is not an amplitude correlation or refinement residual and does not prove a correct structure.

With a genuine frozen holdout, R_free/CC_free compare excluded original amplitudes to Fourier amplitudes from the relevant omit result; R_free requires at least three usable pairs. Reference-based profiles may show reference match/phase agreement and RMSD instead. A reference that seeded the run is not independent evidence.

Ranking uses the active profile's ordered, directional criteria and tie-breakers, not a universal combined score. Families have separate recommendations. Check the scientific warning and why a candidate is recommended rather than choosing the largest-looking number.""",W+"selector-model-prediction.png",landscape=True),
page("27 · Graceful stop and early handoff","""**Stop after current cycle** completes the current cycle and retains valid completed results; **Stop immediately** cancels active work. Previously completed valid candidates can remain available, but unfinished output is not a valid replacement.

The execution-window Pass action can request early handoff when a valid completed candidate exists. The confirmation stops further scientific work, waits for a safe terminal state, then opens result review. It does not send an arbitrary half-finished map immediately.

Confirm a completed candidate in the selector. No source family/cycle/threshold should be inferred solely from whichever panel happened to look newest. Native early-return acceptance still needs real Jana verification.""",W+"execution-completed.png",landscape=True),
page("28 · Return the scientific map and model","""**Pass to Jana2020** validates and transfers the actual selected map, matching structure/model and original context. It checks candidate identity and scientific files rather than using preview geometry. Completed EDMA threshold selection is respected; raw extra peaks need not alter the composition-constrained Jana atom list.

The map grid/origin and atomic coordinate frame must remain aligned. No Superflip/SharpED recomputation occurs just to pass a completed candidate. Output names derive from the incoming Jana .inflip declarations, not a fixed standalone naming guess.

**Acceptance gap:** native Jana launch, imported map/model alignment and normal continuation require approved real-machine screenshots/testing. The fixture selector below does not claim that those checks have been completed.""",W+"selector-manual-candidate.png",landscape=True),
page("29 · Interpreting your results","""Charge flipping is a crystallographic structure-solution method; SharpED is machine-learning map processing. Both outputs still require crystallographic interpretation. Neural predictions may contain artifacts, missing sites or plausible but incorrect density.

EDMA peaks must be judged against chemistry, symmetry, connectivity and original diffraction information. Additional display atoms or attractive molecular fragments do not add independent evidence. A high apparent score can reflect imposed amplitudes or a reused reference.

Preserve the original experiment separately from feedback-modified inputs. Compare candidates, inspect uncertainty/coverage and refine independently in an appropriate crystallographic program. No screenshot or synthetic demonstration in this guide is an experimentally established new structure."""),
page("30 · Professional mode: use it deliberately","""Professional mode exposes full Basic/Advanced control without auto-running. The following parameter reference covers every stored input control present in the current full GUI, including options unavailable in normal Superflip + SharpED processing.

Defaults are constructor values in a fresh full configuration, unless marked imported/context-dependent. Wizard defaults, presets, saved settings and .inflip imports can override them. Disabled options are not silently active just because a remembered value is displayed.

Most scientific controls feed external program keywords. Where the client only passes a keyword and does not establish a complete numerical interpretation, that limitation is stated; consult the applicable official Superflip/EDMA manual rather than inferring a scientific guarantee from a label.""",W+"professional-superflip.png",crop="configuration")]

# Explicit authority corrections where inherited help copy is insufficient.
overrides={
"sharped_base_url":"Actual client default is https://jana.fzu.cz/. This is a Public API base, not the https://sharped.fzu.cz/sharp-ed account page. Leave it unchanged for the normal service. The inherited web-host tooltip is stale; the client constant/request code is authoritative.",
"sharped_api_token":"Private access key for the existing Jana account. Empty until supplied; session-only unless explicitly remembered in Windows Credential Manager. Never publish it. Catalogue reachability is not token/inference-entitlement validation.",
"normalize":"Constructor default is atoms. The current compatibility writer omits the normalize keyword for EVERY selection (atoms, wilson, local and none). This stored choice currently has no emitted normalization effect; the inherited tooltip is not the writer authority.",
"modelfile_source":"Controls the actual seed for cycle 2 onward: Superflip map (XPLOR), SharpED map (XPLOR), SharpED structure (EDMA CIF), or None. Constructor default is SharpED map. None forces a one-cycle workflow; XPLOR damping is irrelevant for CIF/None. Selection/provenance, not cycle number alone, determines the seed.",
"damping_factor":"Inverse XPLOR damping 1/x, not Map Feedback correction damping. x=1 has no damping; x=.5 gives factor 2. Existing map blending uses the reciprocal factor and is relevant only to XPLOR next-cycle seeds. CIF/None disable/ignore it.",
"map_feedback_intensity_max_i_over_sigma":"Strict positive-cutoff significance filter uses I/σ(I) or F/σ(F) according to the input. Zero bypasses the significance filter: eligible rows have positive map-predicted intensity and can include zero observed values. A nonzero cutoff is unavailable for FWHM-only data without experimental uncertainty.",
"run_edma_recycle_final":"Applies to the beta/experimental phase-recycling methods, not ordinary Superflip cycling; it is disabled/hidden in the standard workflow. Enabling it extracts the final recycling map, not every standard cycle.",
"perform_algorithm":"External Superflip perform keyword. CF is normal charge flipping; alternatives AAR, lde, general, fourier and symmetry invoke distinct external operations. Keep CF for this tutorial. The client does not fully define every algorithm mathematically; use the official manual/version-specific interface before changing it.",
"manual_cell_a":"Manual unit-cell a length in Å; 0 means Not set. A valid calculation needs a positive physical value. Used only with Manual metadata.",
"manual_cell_b":"Manual unit-cell b length in Å; 0 means Not set. A valid calculation needs a positive physical value. Used only with Manual metadata.",
"manual_cell_c":"Manual unit-cell c length in Å; 0 means Not set. A valid calculation needs a positive physical value. Used only with Manual metadata.",
"manual_cell_alpha":"Manual cell angle α in degrees; 0 is Not set, not a valid angle. Physical angles must be strictly between 0 and 180. Used only with Manual metadata.",
"manual_cell_beta":"Manual cell angle β in degrees; 0 is Not set, not a valid angle. Physical angles must be strictly between 0 and 180. Used only with Manual metadata.",
"manual_cell_gamma":"Manual cell angle γ in degrees; 0 is Not set, not a valid angle. Physical angles must be strictly between 0 and 180. Used only with Manual metadata.",
"manual_spacegroup_number":"International space-group number 1–230; displayed 0 is Not set. Resolve a consistent number/symbol for Manual metadata.",
"manual_spacegroup_symbol":"Space-group symbol entered for Manual metadata; it must resolve consistently with any supplied number. An empty/unresolvable symbol is not validated symmetry.",
"manual_composition":"Element/count composition for Manual metadata; blank is unset. Supply a valid formula for the actual crystallographic cell/search context. It is not a promise that EDMA will detect that exact ASU composition.",
"extra_superflip_keywords":"Additional documented Superflip keyword lines before fbegin. Blank by default. No GUI numerical range; invalid/version-unsupported syntax can fail the external run. Do not override generated context blindly.",
"extra_edma_keywords":"Additional documented EDMA keyword lines. Blank by default. No GUI numeric range; only supported external syntax is meaningful. These affect structure extraction and can change candidate models, not merely the camera.",
"plimit_superflip":"Threshold for EDMA extraction from the Superflip scientific map, in map σ units. Normal default .50. Changes extracted candidate sites; it does not rerun phasing or imply chemical validity.",
"plimit_deblur":"Threshold for EDMA extraction from the SharpED scientific map, in map σ units. Normal default .50. Relevant only when that extraction stage is enabled. Guided Autosolve has its own 1.00σ policy.",
"sharped_outres":"Requested server output sampling/resolution scalar in Å, sent as outres. Default .2. Server-specific numerical interpretation is not fully established by client code; ask the provider rather than claiming new experimental resolution.",
"i_over_sigma_min":"Pre-run observed value/uncertainty filter, distinct from Map Feedback's later correction cutoff. It uses the selected reflection representation when writing scientific input; do not treat a FWHM width as measurement significance.",
"workflow_preset":"Loads a group of settings rather than one scientific scalar. Recommended is the constructor choice; confirm resulting values because a preset/import can override individual constructor defaults. It does not itself certify result quality.",
"show_beta_features":"Off initially. Reveals otherwise hidden beta/experimental phasing methods and their controls. It does not make those methods equivalent to the normal Superflip + SharpED workflow or scientifically validated.",
}
domain_notes={
"Input":"Changes input interpretation/metadata or the first seed; affects scientific computation. Disabled context fields are ignored. Change only to match the actual experiment/model, not to improve the displayed score.",
"Workflow":"Changes enabled stages, cycle budget or next-cycle seeding. Review dependent controls after changing it; one-cycle/disabled-stage values are not silently active. Use only when the required local tools/account/data exist.",
"Output":"Changes output location or additional external file formats, not camera/atomic coordinates. Required internal scientific files remain. Choose a new project-local folder and formats appropriate for the receiving program.",
"Map feedback":"Affects derived reflection input for subsequent cycles only when the corresponding method is enabled and a later cycle exists. Original measured reflections remain distinct. Validate the changed-input result against them.",
"Setup":"Configures program/service access or exposes optional UI features. It does not alter measured reflection values merely by being edited. Use verified installed programs/current service settings.",
"Superflip":"Controls external phasing input/trials/map construction, not just display. Imported .inflip/preset values may replace fresh defaults. For optional/raw keyword syntax and scientific use consult the official manual for the actual executable.",
"EDMA":"Controls structure extraction/model export from the completed map, not neural inference or the camera. Parameters apply only to enabled extraction stages; raw sites and composition-constrained Jana sites can differ.",
"SharpED":"Controls remote processing, pre/post map transform or transport as described. Inactive SharpED stages ignore these values. Data submission needs the correct account entitlement and authorisation to share the map.",
}
page_names={"_build_advanced_setup_tab":"Setup","_build_advanced_superflip_tab":"Superflip","_build_advanced_edma_tab":"EDMA","_build_advanced_sharped_tab":"SharpED","_build_input_tab":"Input","_build_workflow_tab":"Workflow","_build_output_tab":"Output","_build_map_feedback_tab":"Map feedback"}
fields=json.loads((SOURCE/"control_inventory.json").read_text(encoding="utf8"))
groups=defaultdict(list)
for f in fields:groups[page_names.get(f["page"],f["page"] or "Input")].append(f)
def field_text(f,group):
    key=f["key"]
    default=f.get("constructor_default","context-dependent")
    if default=="context-dependent":default=f.get("default","imported/context-dependent")
    if key in ("manual_spacegroup_number",*tuple(k for k in overrides if k.startswith("manual_cell"))):default=0
    if key in ("manual_spacegroup_symbol","manual_composition","extra_superflip_keywords","extra_edma_keywords","sharped_api_token"):default="blank"
    if key in ("plimit_superflip","plimit_deblur"):default=.5
    if key=="sharped_base_url":default="https://jana.fzu.cz/"
    if key=="metadata_source":default="Jana2020 .inflip"
    if key=="nresshells":overrides[key]="Stored resolution-shell count. The writer omits every normalize keyword; this setting has no emitted normalization effect in the current implementation."
    if key in ("hkl","jana_inflip","reference_cif","first_cycle_modelfile","work_dir"):default="project/input dependent; no universal personal path"
    if key in ("superflip_exe","edma_exe"):default="active/validated installation; no single drive is required"
    allowed=(f"{f['minimum']} to {f['maximum']}" if "minimum" in f else "; ".join(f.get("values",[])) or "valid text/path/keyword syntax; no GUI numeric interval")
    if f.get("type")=="QCheckBox" or isinstance(default,bool):allowed="On / Off"
    if isinstance(default,bool):default="on" if default else "off"
    detail=overrides.get(key,f.get("tooltip","") or "The stored input is supplied to the corresponding source-implemented operation; numerical scientific meaning is not inferred beyond the verified interface.")
    return f"**{f['label']}** · `{key}`\n\n**Allowed:** {allowed}. **Fresh full-configuration default:** {default}.\n\n{detail}\n\n{domain_notes.get(group,domain_notes['Input'])}"

for group in ("Input","Workflow","Map feedback","Output","Setup","Superflip","EDMA","SharpED"):
    controls=groups[group]
    for index in range(0,len(controls),2):
        selected=controls[index:index+2]
        image=(S+"standalone-"+group.lower().replace(" ","-")+".png" if group in ("Input","Workflow","Map feedback","Output") else W+"professional-"+group.lower()+".png")
        complete.append(page(f"Parameter reference · {group} · {index//2+1}","\n\n---\n\n".join(field_text(f,group) for f in selected),image,crop="configuration",reference=True,keys=[f["key"] for f in selected]))

complete += [
page("Technical appendix · native Jana files","""The incoming Jana .inflip determines return names: outputfile controls the scientific map destination(s), outputbase supplies companion model/context names, and writem40 identifies the EDMA model target. Phase Studio validates this original context instead of substituting a stale standalone project.

The native protocol uses M40 atomic-model records, M50 project/crystallographic context and M80/M81 density/map-related outputs. The original M50 context is preserved. The selected actual map's grid/origin is retained during conversion; a preview or temporary screenshot is not a scientific density input.

Corresponding EDMA exports preserve coordinates/occupancy/site identity and normalise physical displacement parameters. Biso is converted by Uiso = Biso/(8π²), then finite exported Uiso is bounded to 0.010–0.150 Å². PDB writes the corresponding B factor, not Uiso directly. These export safeguards do not validate a chemically correct atom assignment.

Candidate identity, source/cycle/threshold and file hashes guard the one selected return. This file-level mechanism does not replace native GUI acceptance of the imported map/model and continuing refinement."""),
page("Troubleshooting and unresolved definitions","""Missing/incompatible local tools: use the validated setup flow, not a silent skip or arbitrary replacement in Jana. Missing/rejected key: follow the exact token-page process; unreachable/5xx service failures are separate from authentication or bad science.

Unavailable automatic model: refresh the live catalogue; use a deliberate manual available model only when scientifically appropriate. Disabled Map Feedback: check cycle count, reflection format, experimental uncertainty, checkbox and positive resolved wavelength. No detected atoms: inspect extraction completion/map/threshold/chemistry rather than assuming a solved empty structure.

**Definitions requiring provider/manual clarification:** output-resolution server interpretation, individual neural model architecture/training, and complete mathematics/version compatibility of raw Superflip/EDMA keywords. RS/BL are not desktop controls. No quality-score cutoffs are invented.

**Image/acceptance gaps:** the actual current native Jana launch menu and returned model/map view with normal continuation, and packaged 2.0.3 workstation acceptance. These guides remain a review edition until those gaps are closed."""),
page("Useful links, sources and attribution",LINKS+"\n\n[Standalone first use](PhaseStudio_FirstUse_Standalone.pdf) · [Jana2020 first use](PhaseStudio_FirstUse_Jana2020.pdf)\n\nImplementation authorities: jana_superflip.py (Wizard/context/model policy); requirements.py/scientific_tools.py (tools); sharped_access.py/credentials.py (account/key); app.py (input, feedback, external stages, outputs); map_quality.py (scores/profiles); result_selection.py/autosolve_window.py/structure_camera.py (review/viewers); autosolve_review.py (guided policy). The settings inventory records the actual current stored fields and constructor lines. These are local source references, not claims about a future interface.")]

write("PhaseStudio_FirstUse_Standalone.pdf","Phase Studio — Getting Started","Standalone Windows Application",standalone)
write("PhaseStudio_FirstUse_Jana2020.pdf","Phase Studio — Getting Started","Integrated with Jana2020",jana)
write("PhaseStudio_Superflip_SharpED_Complete_Guide.pdf","Phase Studio — Superflip + SharpED","Complete Workflow and Settings Guide",complete)
print("Authored",len(standalone),len(jana),len(complete),"content pages; covers",len(fields),"stored full-GUI inputs")
