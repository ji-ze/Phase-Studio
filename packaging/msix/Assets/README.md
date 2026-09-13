# MSIX visual assets

Generate these with:

```powershell
python packaging\generate_store_assets.py
```

This renders every asset directly from Phase Studio's own **vector** brand
mark (`create_phase_studio_logo_pixmap`/`create_phase_studio_app_icon` in
`phase_studio/app.py`, drawn procedurally with QPainter) at each exact target
resolution -- not upscaled from the small taskbar-sized
`phase_studio/assets/phase_studio.ico`, which would look soft at Store tile
sizes (particularly `Square310x310Logo.png` and `SplashScreen.png`).
`packaging\build_store_msix.ps1` validates that all of the files below exist
here and fails with a clear message listing any that are missing; it does
not generate them itself.

| File                     | Size      | Composition                              |
|--------------------------|-----------|-------------------------------------------|
| `StoreLogo.png`          | 50x50     | square icon, transparent background       |
| `Square44x44Logo.png`    | 44x44     | square icon, transparent background       |
| `Square71x71Logo.png`    | 71x71     | square icon, transparent background       |
| `Square150x150Logo.png`  | 150x150   | square icon, transparent background       |
| `Square310x310Logo.png`  | 310x310   | square icon, transparent background       |
| `Wide310x150Logo.png`    | 310x150   | full logo centered on brand background    |
| `SplashScreen.png`       | 620x300   | full logo centered on brand background    |

Re-run the generator (and re-run `build_store_msix.ps1`) whenever the brand
mark itself changes in `phase_studio/app.py`; do not hand-edit the PNGs.
