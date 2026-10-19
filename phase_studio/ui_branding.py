"""Shared Qt branding and window geometry, without scientific application imports."""
from __future__ import annotations
import math
import sys
from pathlib import Path
from typing import Callable, Optional
from PySide6.QtCore import Qt, QSize, QRect, QPoint, QTimer
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QIcon, QGuiApplication, QFont, QFontDatabase, QFontInfo
from PySide6.QtWidgets import QWidget, QApplication, QDialog, QHBoxLayout, QVBoxLayout, QLabel, QSizePolicy
from phase_studio.version import VERSION as __version__


SCIENCE_GOTHIC_FAMILY = "Science Gothic"
SCIENCE_GOTHIC_ASSET = Path(__file__).resolve().parent / "assets" / "fonts" / "ScienceGothic-Variable.ttf"
SCIENCE_GOTHIC_LICENSE = Path(__file__).resolve().parent / "assets" / "fonts" / "OFL-Science-Gothic.txt"
BRAND_LETTER_SPACING_EM = 0.0
_science_gothic_font_id: Optional[int] = None
_science_gothic_families: tuple[str, ...] = ()


def register_science_gothic_font() -> tuple[str, ...]:
    """Register the bundled OFL face once and return Qt's actual families."""
    global _science_gothic_font_id, _science_gothic_families
    if _science_gothic_font_id is not None:
        return _science_gothic_families
    _science_gothic_font_id = QFontDatabase.addApplicationFont(str(SCIENCE_GOTHIC_ASSET))
    if _science_gothic_font_id >= 0:
        _science_gothic_families = tuple(
            str(family) for family in QFontDatabase.applicationFontFamilies(_science_gothic_font_id)
        )
    return _science_gothic_families


def phase_studio_brand_font(base: Optional[QFont] = None) -> QFont:
    """Return the verified regular Science Gothic title face and tracking."""
    families = register_science_gothic_font()
    font = QFont(base) if base is not None else QFont()
    if SCIENCE_GOTHIC_FAMILY in families:
        font.setFamily(SCIENCE_GOTHIC_FAMILY)
    font.setWeight(QFont.Normal)
    # Zero absolute tracking preserves the regular face's native advances.
    pixel_size = max(1, int(QFontInfo(font).pixelSize()))
    font.setLetterSpacing(QFont.AbsoluteSpacing, BRAND_LETTER_SPACING_EM * pixel_size)
    return font


def phase_studio_brand_font_info(base: Optional[QFont] = None) -> tuple[str, int, float]:
    """Expose the resolved face used by runtime/frozen-build acceptance tests."""
    font = phase_studio_brand_font(base)
    info = QFontInfo(font)
    return info.family(), int(info.weight()), float(font.letterSpacing())


def phase_studio_brand_runtime_report(profile: str) -> dict[str, object]:
    """Return frozen/source acceptance evidence from the actual title widget."""
    header = create_phase_studio_brand_header()
    title = header.findChild(QLabel, "brandTitle")
    if title is None:
        raise RuntimeError("Shared Phase Studio brand title was not created.")
    font = title.font()
    info = QFontInfo(font)
    return {
        "profile": str(profile),
        "asset_exists": SCIENCE_GOTHIC_ASSET.is_file(),
        "license_exists": SCIENCE_GOTHIC_LICENSE.is_file(),
        "registered_families": list(register_science_gothic_font()),
        "requested_family": font.family(),
        "resolved_family": info.family(),
        "requested_weight": int(font.weight()),
        "resolved_weight": int(info.weight()),
        "letter_spacing_type": int(font.letterSpacingType().value),
        "letter_spacing": float(font.letterSpacing()),
        "title": title.text(),
    }


def _windows_foreground_activation(
    window: QWidget, log: Optional[Callable[[str], None]] = None,
) -> bool:
    """Promote one shown Qt top-level window and verify its Windows HWND.

    Windows can reject SetForegroundWindow when Jana owns the foreground lock.
    AttachThreadInput is scoped to this call, and the final fallback toggles
    TOPMOST only around the promotion. The window is always returned to the
    ordinary NOTOPMOST z-order band.
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnd = int(window.winId())
    foreground_before = int(user32.GetForegroundWindow() or 0)
    target_thread = int(user32.GetWindowThreadProcessId(hwnd, None) or 0)
    foreground_thread = int(
        user32.GetWindowThreadProcessId(foreground_before, None) or 0
    ) if foreground_before else 0
    current_thread = int(user32.GetCurrentThreadId() or 0)
    show_command = 3 if window.isMaximized() else 5  # SW_MAXIMIZE / SW_SHOW
    attached = False
    temporary_topmost = False
    try:
        user32.ShowWindow(hwnd, show_command)
        if foreground_thread and current_thread and foreground_thread != current_thread:
            attached = bool(user32.AttachThreadInput(current_thread, foreground_thread, True))
        user32.BringWindowToTop(hwnd)
        user32.SetActiveWindow(hwnd)
        user32.SetFocus(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, foreground_thread, False)

    success = int(user32.GetForegroundWindow() or 0) == hwnd
    if not success:
        # SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW. This is a short z-order
        # transfer only; the matching HWND_NOTOPMOST call is unconditional.
        flags = 0x0001 | 0x0002 | 0x0040
        hwnd_topmost = wintypes.HWND(-1)
        hwnd_notopmost = wintypes.HWND(-2)
        temporary_topmost = True
        try:
            user32.SetWindowPos(hwnd, hwnd_topmost, 0, 0, 0, 0, flags)
            user32.BringWindowToTop(hwnd)
            user32.SetActiveWindow(hwnd)
            user32.SetFocus(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            user32.SetWindowPos(hwnd, hwnd_notopmost, 0, 0, 0, 0, flags)
        success = int(user32.GetForegroundWindow() or 0) == hwnd

    if log is not None:
        final_foreground = int(user32.GetForegroundWindow() or 0)
        log("Window activation diagnostics:")
        log(f"  Jana/previous foreground HWND: 0x{foreground_before:X}")
        log(f"  Phase Studio HWND: 0x{hwnd:X}")
        log(f"  show state: {'maximized' if window.isMaximized() else 'normal'}")
        log("  Qt activation attempted: yes")
        log("  native foreground fallback used: yes")
        log(f"  AttachThreadInput used: {'yes' if attached else 'no'}")
        log(f"  temporary topmost fallback used: {'yes' if temporary_topmost else 'no'}")
        log(f"  final foreground HWND: 0x{final_foreground:X}")
        log(f"  activation successful: {'yes' if success else 'no'}")
        log("  final topmost state: no")
    return success


def activate_user_launched_window(
    window: QWidget, *, windows_foreground: bool = False,
    diagnostic_log: Optional[Callable[[str], None]] = None,
) -> None:
    """Show and activate a window created by the user's current launch action.

    The queued passes matter on Windows: a QWidget can be visible before its
    native HWND is ready to participate in foreground activation.  The native
    fallback is deliberately opt-in and is used only by the Jana2020 launch
    route.  It never changes the always-on-top flag.
    """
    previous_foreground = 0
    if windows_foreground and sys.platform == "win32":
        try:
            import ctypes
            previous_foreground = int(ctypes.windll.user32.GetForegroundWindow() or 0)
        except (AttributeError, OSError, TypeError, ValueError):
            pass
    window.show()
    window.winId()
    diagnostics_written = False

    def activate() -> None:
        nonlocal diagnostics_written
        if not window.isVisible():
            return
        window.raise_()
        window.activateWindow()
        if windows_foreground and sys.platform == "win32":
            try:
                import ctypes

                user32 = ctypes.windll.user32
                hwnd = int(window.winId())
                attempt_log = diagnostic_log if not diagnostics_written else None
                if int(user32.GetForegroundWindow() or 0) != hwnd:
                    _windows_foreground_activation(window, attempt_log)
                elif attempt_log is not None:
                    attempt_log("Window activation diagnostics:")
                    attempt_log(f"  Jana/previous foreground HWND: 0x{previous_foreground:X}")
                    attempt_log(f"  Phase Studio HWND: 0x{hwnd:X}")
                    attempt_log(f"  show state: {'maximized' if window.isMaximized() else 'normal'}")
                    attempt_log("  Qt activation attempted: yes")
                    attempt_log("  native foreground fallback used: no")
                    attempt_log("  AttachThreadInput used: no")
                    attempt_log("  temporary topmost fallback used: no")
                    attempt_log(f"  final foreground HWND: 0x{hwnd:X}")
                    attempt_log("  activation successful: yes")
                    attempt_log("  final topmost state: no")
                if attempt_log is not None:
                    diagnostics_written = True
            except (AttributeError, OSError, TypeError, ValueError):
                pass

    activate()
    QTimer.singleShot(0, window, activate)
    QTimer.singleShot(120, window, activate)
    QTimer.singleShot(350, window, activate)


def transfer_user_foreground(
    source: Optional[QWidget], target: QWidget, *,
    windows_foreground: bool = False,
    diagnostic_log: Optional[Callable[[str], None]] = None,
) -> None:
    """Show and verify ``target`` before retiring the current Phase Studio window.

    Keeping ``source`` visible until the target HWND has been promoted prevents
    Windows from handing the foreground back to Jana in the gap between two
    Phase Studio top-level windows. The existing activation helper retains
    responsibility for the scoped native fallback and HWND_NOTOPMOST restore.
    """
    source_hwnd = int(source.winId()) if source is not None and source.isVisible() else 0
    if diagnostic_log is not None:
        diagnostic_log("Window foreground transfer:")
        diagnostic_log(f"  wizard/source HWND: 0x{source_hwnd:X}")

    target.show()
    target_hwnd = int(target.winId())
    if diagnostic_log is not None:
        diagnostic_log(f"  execution/target HWND: 0x{target_hwnd:X}")

    retired = False

    def retire_source_when_active() -> None:
        nonlocal retired
        if retired or not target.isVisible():
            return
        verified = True
        foreground = target_hwnd
        if windows_foreground and sys.platform == "win32":
            try:
                import ctypes

                foreground = int(ctypes.windll.user32.GetForegroundWindow() or 0)
                verified = foreground == target_hwnd
            except (AttributeError, OSError, TypeError, ValueError):
                verified = False
        elif QApplication.instance() is not None:
            active = QApplication.activeWindow()
            verified = active is target or target.isActiveWindow()
        if not verified:
            return
        if source is not None and source is not target and source.isVisible():
            source.hide()
        retired = True
        if diagnostic_log is not None:
            diagnostic_log(f"  foreground HWND after show: 0x{foreground:X}")
            diagnostic_log("  source hidden after target verification: yes")

    activate_user_launched_window(
        target, windows_foreground=windows_foreground,
        diagnostic_log=diagnostic_log,
    )
    retire_source_when_active()
    QTimer.singleShot(0, retire_source_when_active)
    QTimer.singleShot(120, retire_source_when_active)
    QTimer.singleShot(350, retire_source_when_active)


def activate_owned_dialog(
    dialog: QDialog, diagnostic_log: Optional[Callable[[str], None]] = None,
) -> None:
    """Raise a modal child after Qt has created its native owner relationship."""
    activate_user_launched_window(
        dialog, windows_foreground=True, diagnostic_log=diagnostic_log,
    )


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
    width_fraction: float = 0.95,
    height_fraction: float = 0.97,
) -> QSize:
    """Return an initial client size whose complete frame fits the usable desktop."""
    max_outer_width = max(1, int(math.floor(available_size.width() * width_fraction)))
    # On short high-DPI desktops, use the available work area rather than
    # sacrificing scientific plot height to a large decorative outer margin.
    # The native frame is still measured and kept wholly above the taskbar.
    max_outer_height = max(1, int(math.floor(available_size.height() * height_fraction)))
    client_width = min(preferred_size.width(), max(1, max_outer_width - max(0, frame_extra.width())))
    client_height = min(preferred_size.height(), max(1, max_outer_height - max(0, frame_extra.height())))
    return QSize(client_width, client_height)


def fit_dialog_to_available_screen(
    dialog: QDialog,
    preferred_size: QSize = QSize(1180, 835),
    *,
    width_fraction: float = 0.95,
    height_fraction: float = 0.97,
    center: bool = True,
) -> QRect:
    """Size and center a dialog inside its screen's availableGeometry()."""
    dialog.ensurePolished()
    dialog.winId()  # Ensure native frame margins are available before sizing.
    parent = dialog.parentWidget()
    screen = None
    if parent is not None:
        handle = parent.window().windowHandle()
        screen = handle.screen() if handle is not None else parent.screen()
    screen = screen or dialog.screen() or QGuiApplication.primaryScreen()
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
    target = fitted_dialog_client_size(
        available.size(), frame_extra, preferred_size, width_fraction, height_fraction,
    )
    dialog.setMinimumSize(min(760, target.width()), min(520, target.height()))
    dialog.resize(target)

    frame = dialog.frameGeometry()
    if center:
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
    install_screen_geometry_guard(dialog)
    return available


def clamp_window_to_available_screen(
    window: QWidget, screen=None, *, width_fraction: float = 1.0,
    height_fraction: float = 1.0, center_if_resized: bool = False,
) -> QRect:
    """Keep a top-level native frame wholly inside one monitor's work area."""
    screen = screen or window.screen() or QGuiApplication.primaryScreen()
    if screen is None:
        return QRect(window.frameGeometry())
    available = screen.availableGeometry()
    frame = window.frameGeometry()
    client = window.geometry()
    extra_w = max(0, frame.width() - client.width())
    extra_h = max(0, frame.height() - client.height())
    max_client_w = max(1, int(available.width() * width_fraction) - extra_w)
    max_client_h = max(1, int(available.height() * height_fraction) - extra_h)
    resized = window.width() > max_client_w or window.height() > max_client_h
    if resized:
        window.resize(min(window.width(), max_client_w), min(window.height(), max_client_h))
        frame = window.frameGeometry()
    if resized and center_if_resized:
        target = QPoint(
            available.x() + max(0, (available.width() - frame.width()) // 2),
            available.y() + max(0, (available.height() - frame.height()) // 2),
        )
        window.move(window.pos() + target - frame.topLeft())
        frame = window.frameGeometry()
    dx = max(available.left() - frame.left(), 0) - max(frame.right() - available.right(), 0)
    dy = max(available.top() - frame.top(), 0) - max(frame.bottom() - available.bottom(), 0)
    if dx or dy:
        window.move(window.pos() + QPoint(dx, dy))
    return QRect(available)


def jana_launch_parent_rect() -> Optional[QRect]:
    """Read a verified Jana launch window's frame; never change native focus."""
    active=QApplication.activeWindow()
    if active is not None and active.windowTitle().casefold().startswith('jana2020'):
        return QRect(active.frameGeometry())
    if sys.platform!='win32' or QApplication.platformName()=='offscreen':
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user32=ctypes.windll.user32
        user32.GetForegroundWindow.restype=wintypes.HWND
        user32.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT]
        user32.GetAncestor.restype=wintypes.HWND
        user32.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
        user32.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
        hwnd=user32.GetForegroundWindow()
        for candidate in (hwnd,user32.GetAncestor(hwnd,3)):
            title=ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(candidate,title,len(title))
            if title.value.casefold().startswith('jana2020'):
                hwnd=candidate;break
        else:
            return None
        rect=wintypes.RECT()
        if not user32.GetWindowRect(hwnd,ctypes.byref(rect)):return None
        class MonitorInfo(ctypes.Structure):
            _fields_=[('size',wintypes.DWORD),('monitor',wintypes.RECT),('work',wintypes.RECT),
                      ('flags',wintypes.DWORD),('device',wintypes.WCHAR*32)]
        user32.MonitorFromWindow.argtypes=[wintypes.HWND,wintypes.DWORD]
        user32.MonitorFromWindow.restype=wintypes.HANDLE
        user32.GetMonitorInfoW.argtypes=[wintypes.HANDLE,ctypes.POINTER(MonitorInfo)]
        info=MonitorInfo();info.size=ctypes.sizeof(info)
        if not user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd,2),ctypes.byref(info)):return None
        screen=next((s for s in QGuiApplication.screens() if s.name().casefold()==info.device.casefold()),None)
        if screen is None:return None
        dpr=screen.devicePixelRatio();origin=screen.geometry().topLeft()
        result=QRect(origin.x()+round((rect.left-info.monitor.left)/dpr),
            origin.y()+round((rect.top-info.monitor.top)/dpr),round((rect.right-rect.left)/dpr),round((rect.bottom-rect.top)/dpr))
        return result if result.isValid() else None
    except (AttributeError,OSError,ValueError):
        return None


def install_screen_geometry_guard(window: QWidget) -> None:
    """Re-clamp only when a monitor change leaves part of the window inaccessible."""
    if getattr(window, "_phase_studio_screen_guard", False):
        return
    window.winId()
    handle = window.windowHandle()
    if handle is None:
        return
    def changed(screen) -> None:
        # Monitor changes only correct inaccessible geometry.  A normally
        # fitting user-resized window must not jump merely because DPI changed.
        clamp_window_to_available_screen(window, screen, center_if_resized=True)
    handle.screenChanged.connect(changed)
    window._phase_studio_screen_guard = True  # type: ignore[attr-defined]
    window._phase_studio_screen_guard_callback = changed  # type: ignore[attr-defined]

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


# --- Established icon inventory (2.0.0) ---
# The ONLY icon sources Phase Studio's own UI may use. Phase Studio's
# visual language is textual/scientific: before 2.0.0 the application used
# exactly these and nothing else. A new action reuses the closest entry here
# or stays text-only -- it never introduces its own artwork.
# tests/test_jana_wizard_tile_icons.py fails if an action carries an icon that
# does not come from this inventory, or if new icon artwork/assets appear.
ESTABLISHED_ICON_INVENTORY = {
    "application_menu": "Requested horizontal ellipsis for the application header menu.",
    "workflow_superflip": "Charge-flipping electron-density profile.",
    "workflow_sharped": "Broad-to-sharp electron-density restoration peaks.",
    "workflow_autosolve": "Approved Variant B: atomic structure inside a focus frame.",
    "workflow_settings": "Three scientific parameter sliders.",
    "phase_studio_mark": (
        "The Phase Studio monitor mark (create_phase_studio_logo_pixmap / "
        "create_phase_studio_app_icon; packaged as assets/phase_studio.ico) -- "
        "application, title-bar and taskbar icon, brand header logo."
    ),
    "external_link": (
        "Chain glyph (IterativeSuperflipPipelineQtGUI._external_link_icon) -- "
        "external web links to the Superflip and SharpED project pages."
    ),
    "qt_warning": (
        "Qt standard QStyle.SP_MessageBoxWarning -- scientific/predictive-step "
        "warnings in the Jana2020 Wizard."
    ),
    "qt_information": (
        "Qt standard QMessageBox.Information -- the requirements confirmation dialog."
    ),
    # Qt standard (Fusion) monochrome glyphs for the four primary Wizard
    # action tiles. Phase Studio has no action-icon family of its own; these
    # are the platform's shipped icons, never custom artwork, chosen from a
    # single monochrome family so the four tiles read as one set.
    "qt_media_play": "Qt standard QStyle.SP_MediaPlay -- Original Superflip (one run).",
    "qt_media_seek_forward": "Qt standard QStyle.SP_MediaSeekForward -- Autosolve (automatic repeated cycles).",
    "qt_file_dialog_detailed_view": (
        "Qt standard QStyle.SP_FileDialogDetailedView -- Solve the phase problem (measured data unchanged)."
    ),
    "qt_file_dialog_list_view": (
        "Qt standard QStyle.SP_FileDialogListView -- Predict the structure model."
    ),
}
# Inventory entries that are Qt standard icons, by QStyle.StandardPixmap name.
QT_STANDARD_ICON_SOURCES = {
    "qt_warning": "SP_MessageBoxWarning",
    "qt_information": "SP_MessageBoxInformation",
    "qt_media_play": "SP_MediaPlay",
    "qt_media_seek_forward": "SP_MediaSeekForward",
    "qt_file_dialog_detailed_view": "SP_FileDialogDetailedView",
    "qt_file_dialog_list_view": "SP_FileDialogListView",
}
# Dynamic property recording which inventory entry a widget's icon came from.
ICON_SOURCE_PROPERTY = "phaseStudioIconSource"


def established_icon(source: str, style=None) -> QIcon:
    """The QIcon for one ESTABLISHED_ICON_INVENTORY entry."""
    if source in {"workflow_superflip", "workflow_sharped", "workflow_autosolve", "workflow_settings", "application_menu"}:
        from PySide6.QtSvg import QSvgRenderer
        asset = Path(__file__).resolve().parent / "assets" / (source + ".svg")
        renderer = QSvgRenderer(str(asset))
        if not renderer.isValid():
            raise ValueError(f"Invalid workflow SVG resource: {source}")
        pixmap = QPixmap(144, 144)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        try:
            renderer.render(painter)
        finally:
            painter.end()
        return QIcon(pixmap)
    if source == "phase_studio_mark":
        return create_phase_studio_app_icon(64)
    if source in QT_STANDARD_ICON_SOURCES:
        from PySide6.QtWidgets import QStyle

        style = style or QApplication.style()
        return style.standardIcon(getattr(QStyle.StandardPixmap, QT_STANDARD_ICON_SOURCES[source]))
    raise ValueError(f"{source!r} is not an established Phase Studio icon")


def apply_established_icon(widget: QWidget, source: str, *, size: Optional[int] = None, style=None) -> None:
    """Put an established inventory icon on a button (setIcon) or a QLabel
    (setPixmap), and tag the widget with its inventory source."""
    icon = established_icon(source, style)
    if isinstance(widget, QLabel):
        extent = int(size or 16)
        if source.startswith("workflow_"):
            ratio = widget.devicePixelRatioF()
            pixmap = icon.pixmap(round(extent * ratio), round(extent * ratio))
            pixmap.setDevicePixelRatio(ratio)
            widget.setPixmap(pixmap)
        else:
            widget.setPixmap(icon.pixmap(extent, extent))
    else:
        widget.setIcon(icon)
        if size is not None:
            widget.setIconSize(QSize(int(size), int(size)))
    widget.setProperty(ICON_SOURCE_PROPERTY, source)


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
    # Resolve the stylesheet's title size before calculating absolute tracking.
    # Otherwise the spacing is derived from the smaller application font.
    register_science_gothic_font()
    brand_title.ensurePolished()
    title_font = phase_studio_brand_font(brand_title.font())
    brand_title.setFont(title_font)
    # Qt's stylesheet font rule overrides setFont's spacing after polishing.
    # Put the calculated absolute spacing in that same rendering authority.
    brand_title.setStyleSheet(f"letter-spacing: {title_font.letterSpacing():.6f}px;")
    brand_title.setProperty("resolvedBrandFontFamily", QFontInfo(brand_title.font()).family())
    version_badge = QLabel(__version__)
    version_badge.setObjectName("versionBadge")
    version_badge.setAlignment(Qt.AlignCenter)
    brand_title_row.addWidget(brand_title, 1)
    brand_title_row.addWidget(version_badge)
    brand_subtitle = QLabel(
        '<span style="color:#52658b;">by </span>'
        '<span style="color:#001170; font-family:Science Gothic; font-weight:400; letter-spacing:0px;">Sharp</span>'
        '<span style="color:#1fa5ff; font-family:Science Gothic; font-weight:400; letter-spacing:0px;">ED</span>'
    )
    brand_subtitle.setObjectName("brandSubtitle")
    brand_subtitle.setTextFormat(Qt.RichText)
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


def apply_safe_dialog_geometry(
    dialog: QWidget, width: int, height: int, *,
    width_fraction: float = 0.95, height_fraction: float = 0.97,
) -> None:
    """Int-based convenience wrapper around the existing
    fit_dialog_to_available_screen() (frame-aware: measures the dialog's
    actual native frame, not an approximate margin, and double-clamps after
    the window manager settles) -- the one shared safe top-level-window
    geometry helper for the Jana2020 Wizard, the Jana2020 result selector,
    HKL Validation/Completeness, and any other Phase Studio dialog, rather
    than each maintaining its own hard-coded/partial sizing logic."""
    fit_dialog_to_available_screen(
        dialog, QSize(width, height), width_fraction=width_fraction,
        height_fraction=height_fraction,
    )
