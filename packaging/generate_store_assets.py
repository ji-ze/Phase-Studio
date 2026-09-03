"""Generate MSIX Store visual assets from Phase Studio's own vector logo.

Phase Studio does not ship a raster logo file: its brand mark
(create_phase_studio_logo_pixmap in phase_studio/app.py) is drawn procedurally
with QPainter at whatever resolution is requested. Every asset below is
therefore rendered fresh at its own exact target size -- never upscaled from
the small taskbar-sized phase_studio.ico, which would look soft/blurry at
Store tile sizes (particularly Square310x310Logo and SplashScreen).

Usage:
    python packaging/generate_store_assets.py

Requires PySide6 (already a Phase Studio dependency) and a display or
QT_QPA_PLATFORM=offscreen (set automatically below if not already set).
Writes directly into packaging/msix/Assets/, overwriting any previous copies
there; build_store_msix.ps1 then copies them into the MSIX staging layout
unchanged.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Square assets: Phase Studio's own optically-centered square composition
# (create_phase_studio_app_icon), rendered directly at each target size.
SQUARE_ASSETS = {
    "StoreLogo.png": 50,
    "Square44x44Logo.png": 44,
    "Square71x71Logo.png": 71,
    "Square150x150Logo.png": 150,
    "Square310x310Logo.png": 310,
}

# Wide/splash assets: the full (uncropped) monitor-mark logo, centered on a
# canvas of the exact target aspect ratio with the same light frame
# background the logo itself already uses -- not a stretched/distorted fit.
WIDE_ASSETS = {
    "Wide310x150Logo.png": (310, 150),
    "SplashScreen.png": (620, 300),
}

BACKGROUND_COLOR = "#F2F4F9"


def main() -> int:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QPixmap, QPainter, QColor
    from PySide6.QtCore import Qt

    from phase_studio.app import create_phase_studio_app_icon, create_phase_studio_logo_pixmap

    app = QApplication.instance() or QApplication([sys.argv[0]])

    out_dir = REPO_ROOT / "packaging" / "msix" / "Assets"
    out_dir.mkdir(parents=True, exist_ok=True)

    generated = []

    for filename, size in SQUARE_ASSETS.items():
        icon = create_phase_studio_app_icon(size)
        pixmap = icon.pixmap(size, size)
        out_path = out_dir / filename
        if not pixmap.save(str(out_path), "PNG"):
            print(f"FAILED to write {out_path}", file=sys.stderr)
            return 1
        generated.append(out_path)

    for filename, (target_w, target_h) in WIDE_ASSETS.items():
        canvas = QPixmap(target_w, target_h)
        canvas.fill(QColor(BACKGROUND_COLOR))
        # Render the logo at a generous width so it stays crisp, then fit it
        # to the canvas with margin -- never upscale a smaller bitmap.
        logo_width = int(target_h * 339.0 / 255.0 * 0.86)
        logo = create_phase_studio_logo_pixmap(logo_width)
        scaled = logo.scaled(
            int(target_w * 0.86), int(target_h * 0.72),
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        painter = QPainter(canvas)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            x = (target_w - scaled.width()) // 2
            y = (target_h - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        finally:
            painter.end()
        out_path = out_dir / filename
        if not canvas.save(str(out_path), "PNG"):
            print(f"FAILED to write {out_path}", file=sys.stderr)
            return 1
        generated.append(out_path)

    print(f"Generated {len(generated)} Store assets in {out_dir}:")
    for path in generated:
        print(f"  {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
