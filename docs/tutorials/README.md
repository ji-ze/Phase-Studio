# Illustrated Phase Studio tutorials

These are 2.0.3 development-source **review editions**, dated 14 October 2026. The verified public Windows release is 2.0.2. Native Jana launch/return captures and packaged 2.0.3 workstation acceptance remain pending. See [REPORT.md](REPORT.md).

- [Standalone first use](PhaseStudio_FirstUse_Standalone.pdf)
- [Jana2020 first use](PhaseStudio_FirstUse_Jana2020.pdf)
- [Complete Superflip + SharpED guide](PhaseStudio_Superflip_SharpED_Complete_Guide.pdf)

Editable Markdown lives in `sources/`; genuine original application captures and sanitized website crops live in `screenshots/`. `demo/` contains generated, shareable teaching input. Catalogue, prediction, metrics and staged progress examples are labelled UI fixtures, not live SharpED inference. The local Superflip/EDMA completion was calculated using the installed programs.

## Rebuild

Run from the repository root, using its application build environment:

```powershell
.venv-build\Scripts\python.exe -m pip install --target build/tutorial-deps reportlab==5.0.1 pymupdf==1.28.2
.venv-build\Scripts\python.exe packaging/tools/build_tutorial_pdfs.py
.venv-build\Scripts\python.exe packaging/tools/validate_tutorial_pdfs.py
```

The renderer reads the editable Markdown directly. Do not rerun `make_tutorial_sources.py` after editing Markdown unless deliberately regenerating the authored text. Font files come from the environment's Matplotlib DejaVu Sans installation. The official font licence is retained in `assets/` and attached inside each PDF.

Only the three PDFs are copied into `dist/documentation/`. Rendered pages and contact sheets stay under ignored `build/tutorials/`. PDF dates/identifiers can vary on rebuild; compare extracted content and images as well as file hashes.

## Refresh application captures

```powershell
$env:QT_QPA_PLATFORM='offscreen:configfile=docs/tutorials/assets/qt-screen.json'
$env:QT_SCALE_FACTOR='1.5'
.venv-build\Scripts\python.exe packaging/tools/capture_tutorials.py
.venv-build\Scripts\python.exe packaging/tools/capture_tutorial_results.py
```

Capture processes isolate QSettings and use synthetic inputs and catalogue fixtures. They do not change production code. The local-run capture requires verified installed Superflip/EDMA executables; inspect that script's paths before running. It performs a genuine local calculation and writes its work only under `build/tutorials/`.

The authenticated website crop was captured from the user's identified Chrome page with authorization. It excludes browser details, account identity and the existing-token table. No token was created or copied. It is deliberately not reproduced by an automated login script. The earlier QWebEngine web-capture helper could not reliably render GitHub; the final public web assets were captured with fresh isolated Edge headless profiles. Do not overwrite them with a blank failed capture.

`control_inventory.json`, `control_screenshot_inventory.json`, `step_screenshot_inventory.json`, the provenance inventories, `pdf_manifest.json` and `validation.json` support review and reproducibility.
