"""Shared Qt branding and window geometry, without scientific application imports."""
from __future__ import annotations
import math
from typing import Optional
from PySide6.QtCore import Qt, QSize, QRect, QPoint
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QIcon, QGuiApplication
from PySide6.QtWidgets import QWidget, QApplication, QDialog, QHBoxLayout, QVBoxLayout, QLabel, QSizePolicy
from phase_studio.version import VERSION as __version__


def close_bootloader_splash() -> None:
    """Close PyInstaller's early splash after the first Qt surface is visible."""
    try:
        import pyi_splash  # type: ignore[import-not-found]

        if pyi_splash.is_alive():
            pyi_splash.close()
    except (ImportError, RuntimeError):
        # Source runs and Store/ONEDIR builds do not provide pyi_splash.
        pass

def fitted_dialog_client_size(
    available_size: QSize,
    frame_extra: QSize = QSize(0, 0),
    preferred_size: QSize = QSize(1180, 835),
) -> QSize:
    """Return an initial client size whose complete frame fits the usable desktop."""
    max_outer_width = max(1, int(math.floor(available_size.width() * 0.95)))
    # On short high-DPI desktops, use the available work area rather than
    # sacrificing scientific plot height to a large decorative outer margin.
    # The native frame is still measured and kept wholly above the taskbar.
    max_outer_height = max(1, int(math.floor(available_size.height() * 0.97)))
    client_width = min(preferred_size.width(), max(1, max_outer_width - max(0, frame_extra.width())))
    client_height = min(preferred_size.height(), max(1, max_outer_height - max(0, frame_extra.height())))
    return QSize(client_width, client_height)


def fit_dialog_to_available_screen(
    dialog: QDialog,
    preferred_size: QSize = QSize(1180, 835),
) -> QRect:
    """Size and center a dialog inside its screen's availableGeometry()."""
    dialog.ensurePolished()
    dialog.winId()  # Ensure native frame margins are available before sizing.
    screen = dialog.screen() or QGuiApplication.primaryScreen()
    if screen is None:
        fallback = QRect(0, 0, preferred_size.width(), preferred_size.height())
        dialog.resize(preferred_size)
        return fallback

    available = screen.availableGeometry()
    frame = dialog.frameGeometry()
    client = dialog.geometry()
    frame_extra = QSize(
        max(0, frame.width() - client.width()),
        max(0, frame.height() - client.height()),
    )
    target = fitted_dialog_client_size(available.size(), frame_extra, preferred_size)
    dialog.setMinimumSize(min(760, target.width()), min(520, target.height()))
    dialog.resize(target)

    frame = dialog.frameGeometry()
    target_frame_top_left = QPoint(
        available.x() + max(0, (available.width() - frame.width()) // 2),
        available.y() + max(0, (available.height() - frame.height()) // 2),
    )
    dialog.move(dialog.pos() + target_frame_top_left - frame.topLeft())

    # A window manager may adjust frame margins after the first move. Clamp a
    # second time so the full native frame, including its title bar, stays in
    # the usable rectangle above the taskbar.
    frame = dialog.frameGeometry()
    dx = max(available.left() - frame.left(), 0) - max(frame.right() - available.right(), 0)
    dy = max(available.top() - frame.top(), 0) - max(frame.bottom() - available.bottom(), 0)
    if dx or dy:
        dialog.move(dialog.pos() + QPoint(dx, dy))

    dialog.available_geometry_at_open = QRect(available)  # type: ignore[attr-defined]
    dialog.initial_client_size = QSize(dialog.size())  # type: ignore[attr-defined]
    return available

def create_phase_studio_logo_pixmap(width: int = 96) -> QPixmap:
    """Render the supplied Phase Studio monitor mark without an external asset dependency."""
    width = max(40, int(width))
    height = max(30, int(round(width * 255.0 / 339.0)))
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.Antialiasing, True)
        sx = width / 339.0
        sy = height / 255.0

        def rect(x: float, y: float, w: float, h: float, color: str, radius: float = 0.0) -> None:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(int(x * sx), int(y * sy), int(w * sx), int(h * sy), radius * sx, radius * sy)

        frame_pen = QPen(QColor("#001170"), max(2.0, 7.0 * sx))
        frame_pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(frame_pen)
        painter.setBrush(QColor("#F2F4F9"))
        painter.drawRoundedRect(int(19 * sx), int(11 * sy), int(286 * sx), int(177 * sy), 2.5 * sx, 2.5 * sy)
        painter.drawLine(int(159 * sx), int(188 * sy), int(159 * sx), int(238 * sy))
        painter.drawLine(int(82 * sx), int(239 * sy), int(237 * sx), int(239 * sy))

        rect(104, 49, 30, 17, "#001170", 5)
        rect(132, 69, 19, 16, "#001170", 5)
        rect(72, 87, 61, 13, "#001170", 6)
        rect(80, 106, 25, 21, "#001170", 5)
        rect(118, 109, 17, 42, "#001170", 5)
        rect(149, 107, 21, 22, "#001170", 5)
        rect(151, 47, 44, 20, "#1FA5FF", 5)
        rect(194, 69, 33, 16, "#1FA5FF", 7)
        rect(172, 87, 90, 13, "#44B7FF", 6)
        rect(190, 106, 42, 21, "#1FA5FF", 6)
        rect(146, 134, 64, 15, "#1FA5FF", 7)
    finally:
        painter.end()
    return pixmap


def create_phase_studio_app_icon(size: int = 64) -> QIcon:
    """Create a square, optically centered application/taskbar icon."""
    size = max(32, int(size))
    source = create_phase_studio_logo_pixmap(size)
    cropped = source.copy(
        int(source.width() * 0.04),
        int(source.height() * 0.025),
        int(source.width() * 0.88),
        int(source.height() * 0.95),
    )
    target = QPixmap(size, size)
    target.fill(Qt.transparent)
    scaled = cropped.scaled(
        int(size * 0.90), int(size * 0.90), Qt.KeepAspectRatio, Qt.SmoothTransformation
    )
    painter = QPainter(target)
    try:
        painter.drawPixmap((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
    finally:
        painter.end()
    return QIcon(target)


def apply_phase_studio_app_icon(app: "QApplication") -> None:
    """Stamp the Phase Studio icon onto the whole application.

    Set on the QApplication rather than per window: QWidget.windowIcon() falls
    back to the application icon, so this is what gives the Jana2020 Wizard,
    the result selector and every other top-level dialog a real title-bar,
    taskbar and Alt+Tab icon instead of the generic Qt fallback. Uses the one
    existing icon helper -- no second asset, no per-window duplication.
    """
    try:
        if app is not None and app.windowIcon().isNull():
            app.setWindowIcon(create_phase_studio_app_icon(256))
    except Exception:
        # A missing icon must never prevent the application from starting.
        pass


def create_phase_studio_brand_header() -> QWidget:
    """The "PHASE STUDIO" branded header (logo, title, version badge,
    subtitle) -- shared by the main window and any other Phase Studio
    surface (the Jana2020 Wizard, its result selector, ...) that should
    visually read as the same application rather than a generic dialog."""
    brand_header = QWidget()
    brand_header.setObjectName("brandHeader")
    brand_layout = QHBoxLayout(brand_header)
    brand_layout.setContentsMargins(12, 6, 12, 7)
    brand_layout.setSpacing(10)
    brand_logo = QLabel()
    brand_logo.setObjectName("brandLogo")
    brand_logo_pixmap = create_phase_studio_logo_pixmap(58)
    brand_logo.setPixmap(brand_logo_pixmap)
    brand_logo.setFixedSize(brand_logo_pixmap.size())
    brand_logo.setToolTip("Phase Studio")
    brand_text_layout = QVBoxLayout()
    brand_text_layout.setContentsMargins(0, 0, 0, 0)
    brand_text_layout.setSpacing(1)
    brand_title_row = QHBoxLayout()
    brand_title_row.setSpacing(8)
    brand_title = QLabel("PHASE STUDIO")
    brand_title.setObjectName("brandTitle")
    version_badge = QLabel(__version__)
    version_badge.setObjectName("versionBadge")
    version_badge.setAlignment(Qt.AlignCenter)
    brand_title_row.addWidget(brand_title, 1)
    brand_title_row.addWidget(version_badge)
    brand_subtitle = QLabel("Superflip · SharpED · EDMA workflow")
    brand_subtitle.setObjectName("brandSubtitle")
    brand_subtitle.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    brand_text_layout.addLayout(brand_title_row)
    brand_text_layout.addWidget(brand_subtitle)
    brand_layout.addWidget(brand_logo, 0, Qt.AlignVCenter)
    brand_layout.addLayout(brand_text_layout, 1)
    return brand_header


def create_phase_studio_context_banner(title: str, subtitle: str, badge: Optional[QWidget] = None) -> QWidget:
    """A compact navy context banner using the same visual language as the
    main window's "RUN OVERVIEW" banner (#dashboardHeader/#dashboardTitle/
    #dashboardSubtitle in ui_style.py), reused for Jana2020 Wizard page
    context and the Jana2020 result selector so both read as the same
    application as the main window rather than an unrelated dialog."""
    banner = QWidget()
    banner.setObjectName("dashboardHeader")
    banner_layout = QHBoxLayout(banner)
    banner_layout.setContentsMargins(12, 5, 12, 5)
    banner_text = QVBoxLayout()
    banner_text.setSpacing(0)
    banner_title = QLabel(title)
    banner_title.setObjectName("dashboardTitle")
    banner_subtitle = QLabel(subtitle)
    banner_subtitle.setObjectName("dashboardSubtitle")
    banner_subtitle.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    banner_text.addWidget(banner_title)
    banner_text.addWidget(banner_subtitle)
    banner_layout.addLayout(banner_text, 1)
    if badge is not None:
        banner_layout.addWidget(badge)
    return banner


def create_callout_label(title: str, text: str, kind: str = "note", *, compact: bool = False) -> QLabel:
    """kind is one of "warning" (scientific caveat, always prominent), "note"
    (concise operational clarification, the default) or "tip" (optional
    workflow advice, visually the lightest) -- see QLabel#settingsCallout's
    kind-specific QSS rules in ui_style.py. The shared callout label used by
    the settings pages, Help pages, and any other Phase Studio surface (the
    Result Selection dialog, ...) that needs the same warning/note/tip
    presentation without a main-window `self` reference."""
    label = QLabel(f"<b>{title}</b><br>{text}" if title else text)
    label.setObjectName("settingsCallout")
    label.setProperty("calloutKind", kind)
    if compact:
        label.setProperty("compactPadding", "true")
    label.setTextFormat(Qt.RichText)
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    return label


def apply_safe_dialog_geometry(dialog: QWidget, width: int, height: int) -> None:
    """Int-based convenience wrapper around the existing
    fit_dialog_to_available_screen() (frame-aware: measures the dialog's
    actual native frame, not an approximate margin, and double-clamps after
    the window manager settles) -- the one shared safe top-level-window
    geometry helper for the Jana2020 Wizard, the Jana2020 result selector,
    HKL Validation/Completeness, and any other Phase Studio dialog, rather
    than each maintaining its own hard-coded/partial sizing logic."""
    fit_dialog_to_available_screen(dialog, QSize(width, height))
