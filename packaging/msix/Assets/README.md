# MSIX visual assets

Generate these from `phase_studio/assets/phase_studio.ico` (the existing
Phase Studio icon/branding -- do not invent a new visual identity) and place
them in this directory before running `packaging\build_store_msix.ps1`,
which validates they all exist and fails with a clear message listing any
that are missing.

| File                     | Size      |
|--------------------------|-----------|
| `StoreLogo.png`          | 50x50     |
| `Square44x44Logo.png`    | 44x44     |
| `Square71x71Logo.png`    | 71x71     |
| `Square150x150Logo.png`  | 150x150   |
| `Square310x310Logo.png`  | 310x310   |
| `Wide310x150Logo.png`    | 310x150   |
| `SplashScreen.png`       | 620x300   |

Any reproducible tool (Pillow, ImageMagick, the Windows SDK's own asset
generator) can produce all of these from the single source `.ico` in one
script -- do not hand-duplicate or hand-edit them individually.
