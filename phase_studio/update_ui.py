"""One per-application background update service, shared by all launch modes."""
import os
from pathlib import Path
import threading
import time
import weakref
import logging
from datetime import datetime, timezone

from PySide6.QtCore import QObject, Signal, Slot, Qt, QTimer, QSettings, QLockFile, QStandardPaths, QPoint, QSize
from PySide6.QtGui import QDesktopServices, QAction
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QCheckBox, QToolButton, QMenu, QWidget)

from .update_checker import (Release, VERSION, RELEASES_URL, CHECK_INTERVAL, parse_version,
                             is_newer, fetch_latest_release, fetch_release_check, CheckResult,
                             RETRY_INTERVAL, validated_release_url)


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
            previous = self.timestamp('lastSuccess')
            elapsed = now - previous
            retry = self.timestamp('retryAt')
            if not manual and (not self.enabled() or previous and -CHECK_INTERVAL <= elapsed < CHECK_INTERVAL
                               or now < retry <= now+CHECK_INTERVAL):
                return False
            self.settings.setValue('updates/lastAttempt', now)
            self.settings.setValue('updates/retryAt', now+RETRY_INTERVAL)
            return True
        return self._locked(claim)

    def cache(self, release, now):
        def save():
            if release is not None:
                self.settings.setValue('updates/latestStable', release.label)
                self.settings.setValue('updates/releaseUrl', validated_release_url(release.url))
            else:
                self.settings.remove('updates/latestStable')
                self.settings.remove('updates/releaseUrl')
            self.settings.setValue('updates/lastSuccess', now)
            self.settings.remove('updates/retryAt')
            self.settings.remove('updates/failureCount')
            return True
        self._locked(save)

    def cached(self, now):
        self.settings.sync()
        version = parse_version(self.settings.value('updates/latestStable', ''))
        age = now - self.timestamp('lastSuccess')
        return Release(version,validated_release_url(self.settings.value('updates/releaseUrl',''))) if version and 0 <= age < CHECK_INTERVAL else None

    def failed(self, now, retry_after=0, reason=''):
        def save():
            try:count=min(8,max(0,int(self.settings.value('updates/failureCount',0))))
            except (TypeError,ValueError):count=0
            delay=min(CHECK_INTERVAL,max(RETRY_INTERVAL*2**count,retry_after))
            self.settings.setValue('updates/failureCount',count+1)
            self.settings.setValue('updates/lastFailure',now)
            self.settings.setValue('updates/retryAt',now+delay)
            if reason:
                try:
                    path=self.lock_path.parent/'updates.log'
                    mode='w' if path.exists() and path.stat().st_size>256*1024 else 'a'
                    with path.open(mode,encoding='utf8') as stream:
                        stream.write(f'{datetime.fromtimestamp(now,timezone.utc).isoformat()} Phase Studio {VERSION}: {reason}\n')
                except (OSError,ValueError,OverflowError):
                    pass  # A diagnostic-file failure must not affect the workflow.
            return True
        self._locked(save)

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
    def __init__(self, parent, *, release=None, mode='standalone', failed=False, browser=None, error=''):
        super().__init__(parent)
        self.setObjectName('phaseStudioUpdateNotice')
        self.setWindowTitle('Phase Studio updates')
        self.setWindowModality(Qt.NonModal)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.release = release
        self.update_mode = mode
        self.browser = browser or QDesktopServices.openUrl
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        title = QLabel('A new Phase Studio version is available' if release else 'Unable to check for updates' if failed else 'Phase Studio is up to date')
        self.title = title
        title.setWordWrap(True)
        title.setStyleSheet('font-weight:600; color:#001170; border-bottom:2px solid #36b5ed; padding-bottom:8px;')
        layout.addWidget(title)
        message = (f'Phase Studio {release.label} is available. You are using version {VERSION}.' if release
                   else 'GitHub is temporarily unavailable. Please try again later.' if failed and error in {'service','rate-limit'}
                   else 'GitHub returned incomplete release information. Please try again later.' if failed and error.startswith('metadata')
                   else 'Check your internet connection and try again.' if failed
                   else f'Installed version: {VERSION}. No newer stable release is available.')
        self.message = QLabel(message)
        self.message.setTextFormat(Qt.PlainText)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        if release and mode == 'jana':
            clarification = QLabel('The Jana2020 integration package updates Phase Studio only. Direct Jana sessions must be closed and reopened from Jana2020; scientific handoff files are not replaced.')
            clarification.setWordWrap(True)
            layout.addWidget(clarification)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.later_button = QPushButton('Later' if release else 'Close')
        self.later_button.clicked.connect(self.reject)
        buttons.addWidget(self.later_button)
        self.view_button = None
        self.update_button = None
        if release:
            self.view_button = QPushButton('View release on GitHub')
            self.view_button.setObjectName('primaryButton')
            self.view_button.clicked.connect(self._open_release)
            buttons.addWidget(self.view_button)
            from .update_runtime import public_installation_status
            allowed,reason=public_installation_status()
            self.update_button=QPushButton('Update now')
            self.update_button.setEnabled(allowed)
            self.update_button.setToolTip(reason or 'Download, verify and review this update before installation.')
            self.update_button.clicked.connect(self._install_update)
            if allowed:
                self.view_button.setObjectName('')
                self.update_button.setObjectName('primaryButton')
            buttons.addWidget(self.update_button)
            if reason:
                installation_note=QLabel(reason);installation_note.setWordWrap(True)
                layout.addWidget(installation_note)
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
        self.browser(QUrl(validated_release_url(self.release.url,version=self.release.version)))
        self.accept()

    def _install_update(self):
        from .update_install_ui import UpdateInstallDialog
        app=QApplication.instance()
        previous=getattr(app,'_phase_studio_install_dialog',None)
        if previous is not None and previous.isVisible():previous.raise_();previous.activateWindow();return
        dialog=UpdateInstallDialog(self.parentWidget(),self.release,jana=(getattr(self,'update_mode','standalone')=='jana'))
        app._phase_studio_install_dialog=dialog
        dialog.finished.connect(lambda _result:setattr(app,'_phase_studio_install_dialog',None))
        dialog.show();self.accept()


class UpdateService(QObject):
    completed = Signal(object)
    busy_changed = Signal(bool)
    enabled_changed = Signal(bool)
    release_changed = Signal(object)

    def __init__(self, app, *, state=None, fetcher=None, clock=None, automatic_allowed=None, browser=None):
        super().__init__(app)
        self.state = state or UpdateState()
        self.fetcher = fetcher or fetch_release_check
        self.clock = clock or time.time
        self.automatic_allowed = (QApplication.platformName() != 'offscreen' and
            os.environ.get('PHASE_STUDIO_STARTUP_PROBE') != '1') if automatic_allowed is None else automatic_allowed
        self.browser = browser
        self.busy = False
        self.known_release = None
        self.notice = None
        self._windows = []
        self._context = None
        self._session_notified = set()
        self._last_attempt = None
        self.completed.connect(self._finished, Qt.QueuedConnection)

    def set_enabled(self, enabled):
        self.state.set_enabled(enabled)
        self.enabled_changed.emit(enabled)
        if not enabled and self.notice is not None and getattr(self.notice,'automatic',False):
            self.notice.close()

    @staticmethod
    def mode(window, mode):
        if mode:
            return mode
        if getattr(window, '_phase_studio_distribution', None) == 'jana':
            return 'jana'
        return 'jana' if getattr(window, 'autosolve_is_jana', lambda: False)() else 'standalone'

    def attach(self, window, mode=None, automatic=True):
        from .update_health import visible
        QTimer.singleShot(500,window,lambda:visible(window))
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
            if not self.state.claim_check(now):
                cached = self.state.cached(now)
                if cached:
                    self.known_release = cached if is_newer(cached) else None
                    self.release_changed.emit(self.known_release)
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
                result = self.fetcher()
                if isinstance(result,Release):result=CheckResult(result)
                if not isinstance(result,CheckResult):result=CheckResult(error='network')
                if result.error:result=CheckResult(error=result.error,retry_after=result.retry_after,detail=result.detail)
                if result.release is not None and (not isinstance(result.release,Release) or parse_version(result.release.label)!=result.release.version):
                    result=CheckResult(error='metadata-version')
            except Exception:
                result = CheckResult(error='network')
            try:
                self.completed.emit(result)
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
    def _finished(self, result):
        self.busy = False
        self.busy_changed.emit(False)
        reference, mode, manual = self._context
        window = self._visible(reference)
        release=result.release
        self.known_release = release if not result.error and release is not None and is_newer(release) else None
        self._verified_release_at = self.clock() if self.known_release is not None else None
        self.release_changed.emit(self.known_release)
        if not result.error:
            self.state.cache(release, self.clock())
        else:
            self.state.failed(self.clock(),result.retry_after,f'{result.error} {result.detail}'.strip())
            logging.getLogger(__name__).warning('GitHub release check failed: %s %s',result.error,result.detail)
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
            self._show(window, mode, failed=bool(result.error),error=result.error)

    def _offer(self, window, mode, release, manual=False):
        if not is_newer(release) or not window.isVisible():
            return
        if not manual and (release.version in self._session_notified or not self.state.enabled()):
            return
        claimed = self.state.claim_notification(release, manual=manual)
        if not manual and not claimed:
            return
        self._session_notified.add(release.version)
        self._show(window, mode, release=release,automatic=not manual)

    def _show(self, window, mode, **options):
        if self.notice is not None:
            self.notice.close()
        automatic=options.pop('automatic',False)
        dialog = UpdateNotice(window, mode=self.mode(window, mode), browser=self.browser, **options)
        dialog.automatic=automatic
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


class _CheckingState(QObject):
    @Slot(bool)
    def apply(self,busy):
        control=self.parent()
        control.setEnabled(not busy)
        control.setText('Checking for updates…' if busy else 'Check for updates')


class _VersionMenu(QMenu):
    def showEvent(self,event):
        super().showEvent(event)
        button=self.parentWidget()
        available=button.screen().availableGeometry()
        anchor=button.mapToGlobal(QPoint(button.width(),button.height()))
        self.move(max(available.left(),min(anchor.x()-self.width(),available.right()-self.width()+1)),
                  max(available.top(),min(anchor.y(),available.bottom()-self.height()+1)))


class _VersionButton(QToolButton):
    def __init__(self, window, service):
        super().__init__(window)
        self._service = service
        self._indicator_expiry = QTimer(self)
        self._indicator_expiry.setSingleShot(True)
        self._indicator_expiry.timeout.connect(lambda: self.show_release(None))

    @Slot(object)
    def show_release(self, release):
        verified_at = getattr(self._service, '_verified_release_at', None)
        age = self._service.clock() - verified_at if verified_at is not None else CHECK_INTERVAL
        self.update_available = release is not None and is_newer(release) and 0 <= age < CHECK_INTERVAL
        self._indicator_expiry.stop()
        if self.update_available:
            self._indicator_expiry.start(max(1, int((CHECK_INTERVAL - age) * 1000)))
        self.setToolTip('Updates and application information')
        self.setAccessibleDescription(f'Version {release.label} available' if self.update_available else '')
        self.update()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            event.accept()
            self.showMenu()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if getattr(self, 'update_available', False):
            from PySide6.QtGui import QColor, QPainter
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor('#2468cb'))
            painter.drawEllipse(self.width() - 7, 3, 4, 4)
            painter.end()


def add_update_controls(layout, window):
    service = update_service()
    row = QHBoxLayout()
    check = QPushButton('Check for updates')
    check.clicked.connect(lambda: service.check(window, manual=True))
    presentation=_CheckingState(check)
    presentation.apply(service.busy)
    service.busy_changed.connect(presentation.apply)
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


def wizard_update_menu(window, *, mode='jana', automatic=True):
    service = update_service()
    button = _VersionButton(window, service)
    button.show_release(service.known_release)
    service.release_changed.connect(button.show_release)
    from .ui_branding import apply_established_icon
    apply_established_icon(button, 'application_menu', size=16)
    button.setText('')
    button.setToolButtonStyle(Qt.ToolButtonIconOnly)
    button.setIconSize(QSize(16, 16))
    button.setArrowType(Qt.NoArrow)
    button.setAccessibleName('Phase Studio menu')
    button.setFocusPolicy(Qt.StrongFocus)
    button.setCursor(Qt.PointingHandCursor)
    button.setPopupMode(QToolButton.InstantPopup)
    button.setFixedSize(30, 30)
    button.setStyleSheet('QToolButton { background:transparent; border:2px solid transparent; padding:0; }'
        'QToolButton:hover { background:#eaf2ff; }'
        'QToolButton:focus { border-color:#2264b8; }'
        'QToolButton:pressed { background:#dceaf8; }'
        'QToolButton::menu-indicator { image:none; width:0px; height:0px; }')
    menu = _VersionMenu(button)
    check = menu.addAction('Check for updates')
    check.triggered.connect(lambda: service.check(window, mode=mode, manual=True))
    presentation=_CheckingState(check)
    presentation.apply(service.busy)
    service.busy_changed.connect(presentation.apply)
    enabled = QAction('Notify me when new versions are available', menu)
    enabled.setCheckable(True)
    enabled.setChecked(service.state.enabled())
    enabled.toggled.connect(service.set_enabled)
    service.enabled_changed.connect(enabled.setChecked)
    menu.addAction(enabled)
    button.setMenu(menu)
    service.attach(window, mode=mode,automatic=automatic)
    return button


def install_application_header_menu(header, window, *, about, mode='jana', automatic=True):
    """Replace only an interactive header badge; other branded dialogs stay unchanged."""
    badge = header.findChild(QLabel, 'versionBadge')
    if badge is None:
        raise ValueError('Application header has no version badge slot')
    controls = QWidget(header)
    controls.setObjectName('applicationHeaderControls')
    controls.setStyleSheet('QWidget#applicationHeaderControls { background:transparent; border:0; }')
    row = QHBoxLayout(controls)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    row.setAlignment(Qt.AlignVCenter)
    label = QLabel('v' + VERSION)
    label.setObjectName('applicationVersionLabel')
    label.setFont(QApplication.font())
    label.setStyleSheet('color:#52658b; background:transparent; border:0; padding:0; font-size:13px; font-weight:400;')
    label.setFocusPolicy(Qt.NoFocus)
    label.setTextInteractionFlags(Qt.NoTextInteraction)
    label.setAccessibleName('Phase Studio version ' + VERSION)
    button = wizard_update_menu(window, mode=mode, automatic=automatic)
    button.setObjectName('applicationMenuButton')
    button.menu().addSeparator()
    button.menu().addAction('About Phase Studio').triggered.connect(about)
    row.addWidget(label, 0, Qt.AlignVCenter)
    row.addWidget(button, 0, Qt.AlignVCenter)
    badge.parentWidget().layout().replaceWidget(badge, controls)
    badge.hide()
    controls.version_label, controls.menu_button = label, button
    return controls
