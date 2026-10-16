"""One per-application background update service, shared by all launch modes."""
import os
from pathlib import Path
import threading
import time
import weakref

from PySide6.QtCore import QObject, Signal, Slot, Qt, QTimer, QSettings, QLockFile, QStandardPaths
from PySide6.QtGui import QDesktopServices, QAction
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QCheckBox, QToolButton, QMenu)

from .update_checker import (Release, VERSION, RELEASES_URL, CHECK_INTERVAL, parse_version,
                             is_newer, fetch_latest_release)


class UpdateState:
    """Dedicated QSettings keys; short process lock makes claims atomic."""
    def __init__(self, settings=None, lock_path=None):
        self.settings = settings if settings is not None else QSettings(
            QSettings.defaultFormat(), QSettings.UserScope, 'PhaseStudio', 'PhaseStudio')
        self.lock_path = Path(lock_path) if lock_path else Path(QStandardPaths.writableLocation(
            QStandardPaths.GenericDataLocation)) / 'PhaseStudio' / 'updates.lock'

    def enabled(self):
        self.settings.sync()
        return str(self.settings.value('updates/enabled', True)).lower() not in {'false', '0'}

    def set_enabled(self, value):
        self.settings.setValue('updates/enabled', bool(value))
        self.settings.sync()

    def _locked(self, action):
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock = QLockFile(str(self.lock_path))
            if not lock.tryLock(0):
                return False
            try:
                self.settings.sync()
                if self.settings.status() != QSettings.NoError:
                    return False
                value = action()
                self.settings.sync()
                return value if self.settings.status() == QSettings.NoError else False
            finally:
                lock.unlock()
        except OSError:
            return False

    def timestamp(self, key):
        try:
            value = float(self.settings.value('updates/' + key, 0))
            return value if 0 < value < float('inf') else 0
        except (ValueError, TypeError):
            return 0

    def claim_check(self, now, manual=False):
        def claim():
            previous = self.timestamp('lastAttempt')
            elapsed = now - previous
            if not manual and (not self.enabled() or previous and -CHECK_INTERVAL <= elapsed < CHECK_INTERVAL):
                return False
            self.settings.setValue('updates/lastAttempt', now)
            return True
        return self._locked(claim)

    def cache(self, release, now):
        def save():
            self.settings.setValue('updates/latestStable', release.label)
            self.settings.setValue('updates/lastSuccess', now)
            return True
        self._locked(save)

    def cached(self, now):
        self.settings.sync()
        version = parse_version(self.settings.value('updates/latestStable', ''))
        age = now - self.timestamp('lastSuccess')
        return Release(version) if version and 0 <= age < CHECK_INTERVAL else None

    def claim_notification(self, release, manual=False):
        def claim():
            notified = parse_version(self.settings.value('updates/notifiedVersion', ''))
            if not manual and (not self.enabled() or notified and release.version <= notified):
                return False
            if not notified or release.version > notified:
                self.settings.setValue('updates/notifiedVersion', release.label)
            return True
        return self._locked(claim)


class UpdateNotice(QDialog):
    def __init__(self, parent, *, release=None, mode='standalone', failed=False, browser=None):
        super().__init__(parent)
        self.setObjectName('phaseStudioUpdateNotice')
        self.setWindowTitle('Phase Studio updates')
        self.setWindowModality(Qt.NonModal)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.release = release
        self.browser = browser or QDesktopServices.openUrl
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        title = QLabel('A new version of Phase Studio is available' if release else 'Phase Studio updates')
        title.setWordWrap(True)
        title.setStyleSheet('font-weight:600; color:#001170; border-bottom:2px solid #36b5ed; padding-bottom:8px;')
        layout.addWidget(title)
        message = (f'Phase Studio {release.label} is available. You are using version {VERSION}.' if release
                   else 'Unable to check for updates. Please check your internet connection and try again.' if failed
                   else 'You are using the latest released version of Phase Studio.')
        self.message = QLabel(message)
        self.message.setTextFormat(Qt.PlainText)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        if release and mode == 'jana':
            clarification = QLabel('The version integrated into Jana2020 may be updated through a Jana2020 software release.')
            clarification.setWordWrap(True)
            layout.addWidget(clarification)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.later_button = QPushButton('Later' if release else 'Close')
        self.later_button.clicked.connect(self.reject)
        buttons.addWidget(self.later_button)
        self.view_button = None
        if release:
            self.view_button = QPushButton('View release on GitHub')
            self.view_button.setObjectName('primaryButton')
            self.view_button.clicked.connect(self._open_release)
            buttons.addWidget(self.view_button)
        layout.addLayout(buttons)
        self._fit()
        QTimer.singleShot(0, self, self._fit)

    def _fit(self):
        self.ensurePolished()
        layout = self.layout()
        layout.invalidate()
        layout.activate()
        from .ui_branding import apply_safe_dialog_geometry
        apply_safe_dialog_geometry(self, 500, max(180, layout.sizeHint().height(), layout.totalHeightForWidth(500)))

    def _open_release(self):
        self.browser(QUrl(RELEASES_URL))
        self.accept()


class UpdateService(QObject):
    completed = Signal(object)
    busy_changed = Signal(bool)
    enabled_changed = Signal(bool)

    def __init__(self, app, *, state=None, fetcher=None, clock=None, automatic_allowed=None, browser=None):
        super().__init__(app)
        self.state = state or UpdateState()
        self.fetcher = fetcher or fetch_latest_release
        self.clock = clock or time.time
        self.automatic_allowed = (QApplication.platformName() != 'offscreen' and
            os.environ.get('PHASE_STUDIO_STARTUP_PROBE') != '1') if automatic_allowed is None else automatic_allowed
        self.browser = browser
        self.busy = False
        self.notice = None
        self._windows = []
        self._context = None
        self._session_notified = set()
        self._last_attempt = None
        self.completed.connect(self._finished, Qt.QueuedConnection)

    def set_enabled(self, enabled):
        self.state.set_enabled(enabled)
        self.enabled_changed.emit(enabled)

    @staticmethod
    def mode(window, mode):
        if mode:
            return mode
        if getattr(window, '_phase_studio_distribution', None) == 'jana':
            return 'jana'
        return 'jana' if getattr(window, 'autosolve_is_jana', lambda: False)() else 'standalone'

    def attach(self, window, mode=None, automatic=True):
        if not any(ref() is window for ref, _mode in self._windows):
            self._windows.append((weakref.ref(window), mode))
        if automatic:
            QTimer.singleShot(1500, window, lambda: self.check(window, mode=mode))

    def check(self, window, *, mode=None, manual=False):
        if not manual and (not self.automatic_allowed or not self.state.enabled()):
            return
        if self.notice is not None and self.notice.isVisible():
            if not manual:
                return
            self.notice.close()
        if self.busy:
            if manual:
                self._context = (weakref.ref(window), mode, True)
            return
        now = self.clock()
        if not manual:
            if self._last_attempt is not None and -CHECK_INTERVAL <= now - self._last_attempt < CHECK_INTERVAL:
                cached = self.state.cached(now)
                if cached:
                    self._offer(window, mode, cached)
                return
            if not self.state.claim_check(now):
                cached = self.state.cached(now)
                if cached:
                    self._offer(window, mode, cached)
                return
        else:
            self.state.claim_check(now, manual=True)
        self._last_attempt = now
        self._context = (weakref.ref(window), mode, manual)
        self.busy = True
        self.busy_changed.emit(True)
        def work():
            try:
                release = self.fetcher()
                if not isinstance(release, Release) or parse_version(release.label) != release.version:
                    release = None
            except Exception:
                release = None
            try:
                self.completed.emit(release)
            except RuntimeError:
                pass  # Application already closed; the daemon never delays exit.
        threading.Thread(target=work, name='PhaseStudio-release-check', daemon=True).start()

    @staticmethod
    def _visible(reference):
        window = reference()
        try:
            return window if window is not None and window.isVisible() else None
        except RuntimeError:
            return None

    @Slot(object)
    def _finished(self, release):
        self.busy = False
        self.busy_changed.emit(False)
        reference, mode, manual = self._context
        window = self._visible(reference)
        if release is not None:
            self.state.cache(release, self.clock())
        if window is None and not manual:
            for candidate, candidate_mode in reversed(self._windows):
                window = self._visible(candidate)
                if window is not None:
                    mode = candidate_mode
                    break
        if window is None:
            return
        if release is not None and is_newer(release):
            self._offer(window, mode, release, manual=manual)
        elif manual:
            self._show(window, mode, failed=release is None)

    def _offer(self, window, mode, release, manual=False):
        if not is_newer(release) or not window.isVisible():
            return
        if not manual and (release.version in self._session_notified or not self.state.enabled()):
            return
        claimed = self.state.claim_notification(release, manual=manual)
        if not manual and not claimed:
            return
        self._session_notified.add(release.version)
        self._show(window, mode, release=release)

    def _show(self, window, mode, **options):
        if self.notice is not None:
            self.notice.close()
        dialog = UpdateNotice(window, mode=self.mode(window, mode), browser=self.browser, **options)
        self.notice = dialog
        def closed(_result):
            if self.notice is dialog:
                self.notice = None
        dialog.finished.connect(closed)
        dialog.show()  # No exec(), modal loop, activation or browser launch.


def update_service():
    app = QApplication.instance()
    if not hasattr(app, '_phase_studio_updates'):
        app._phase_studio_updates = UpdateService(app)
    return app._phase_studio_updates


def add_update_controls(layout, window):
    service = update_service()
    row = QHBoxLayout()
    check = QPushButton('Check for updates')
    check.clicked.connect(lambda: service.check(window, manual=True))
    check.setEnabled(not service.busy)
    service.busy_changed.connect(check.setDisabled)
    row.addWidget(check)
    row.addStretch(1)
    layout.addLayout(row)
    enabled = QCheckBox('Notify me when new versions are available')
    enabled.setChecked(service.state.enabled())
    enabled.toggled.connect(service.set_enabled)
    service.enabled_changed.connect(enabled.setChecked)
    layout.addWidget(enabled)
    window.update_check_button = check
    window.update_notifications_checkbox = enabled


def wizard_update_menu(window):
    service = update_service()
    button = QToolButton(window)
    button.setText('Updates')
    button.setPopupMode(QToolButton.InstantPopup)
    button.setMinimumHeight(36)
    button.setMinimumWidth(button.sizeHint().width() + 20)
    menu = QMenu(button)
    check = menu.addAction('Check for updates')
    check.triggered.connect(lambda: service.check(window, mode='jana', manual=True))
    check.setEnabled(not service.busy)
    service.busy_changed.connect(check.setDisabled)
    enabled = QAction('Notify me when new versions are available', menu)
    enabled.setCheckable(True)
    enabled.setChecked(service.state.enabled())
    enabled.toggled.connect(service.set_enabled)
    service.enabled_changed.connect(enabled.setChecked)
    menu.addAction(enabled)
    button.setMenu(menu)
    service.attach(window, mode='jana')
    return button
