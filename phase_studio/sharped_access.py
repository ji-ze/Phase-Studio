"""Shared Jana2020-account onboarding for the existing personal-key protocol."""
from __future__ import annotations

from typing import Callable, Optional
import time
import logging
import hashlib

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, QTimer, QUrl, Signal, QRectF
from PySide6.QtGui import QAction, QIcon, QDesktopServices, QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget, QMessageBox,
)

from phase_studio import requirements as reqs
from phase_studio.credentials import credential_store, credential_origin
from phase_studio.sharped_server_client import DEFAULT_SERVER_URL


def connection_status(store, base_url=DEFAULT_SERVER_URL):
    """Session verification is distinct from possessing a persisted credential."""
    token = store.get(base_url)
    if not token:
        return 'Not connected'
    if store.is_oauth(token) and not store._oauth.usable():
        return 'Authentication expired'
    fingerprint = hashlib.sha256(token.encode('utf8')).hexdigest()
    verification = getattr(store, '_access_verification', {}).get(base_url)
    if verification and verification[0] == fingerprint:
        return verification[1]
    return 'Credentials available — not yet verified'


def account_state(store, base_url=DEFAULT_SERVER_URL, *, entered_token=None):
    """Independent credential/connection presentation; never consult the catalogue."""
    saved = store.get(base_url)
    token = saved if entered_token is None else entered_token
    status = connection_status(store, base_url) if token == saved else 'Credentials available — not yet verified'
    credentials = ('Not configured' if not token else
                   'Securely stored' if token == saved and store.remembered(base_url) else
                   'Available for the current session')
    connection = {
        'Not connected': 'Not checked',
        'Connected': 'Connected · Authorization verified',
        'Authentication expired': 'Authentication rejected or expired',
        'Connection unavailable': 'Unavailable',
        'Checking': 'Checking',
    }.get(status, 'Not checked')
    if status == 'Authentication expired':
        credentials = 'Invalid or rejected'
    return credentials, connection, status
from phase_studio.ui_branding import (
    activate_owned_dialog, apply_safe_dialog_geometry, create_phase_studio_brand_header,
)


class _ProbeSignals(QObject):
    completed = Signal(object)


def _account_icon() -> QPixmap:
    pixmap = QPixmap(28, 28)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#001170"), 1.8))
    painter.drawEllipse(QRectF(9, 3, 10, 10))
    shoulders = QPainterPath()
    shoulders.moveTo(4, 25)
    shoulders.cubicTo(4, 12, 24, 12, 24, 25)
    painter.drawPath(shoulders)
    painter.end()
    return pixmap


class _AccessProbe(QRunnable):
    def __init__(self, verify: Callable, token: str) -> None:
        super().__init__()
        self.verify, self.token = verify, token
        self.signals = _ProbeSignals()

    def run(self) -> None:
        try:
            status = self.verify(self.token)
        except Exception as exc:
            status = reqs._classify_sharped_error(exc)
        self.signals.completed.emit(status)


class SharpEDAccessDialog(QDialog):
    def __init__(self, parent=None, status=None, configured_value="", *,
                 base_url=DEFAULT_SERVER_URL, verify=None, store=None) -> None:
        super().__init__(parent)
        self.store = store if store is not None else credential_store
        self.base_url = base_url
        self.verify = verify or (lambda token: reqs.check_sharped_api(base_url, token))
        self.selected_key: Optional[str] = None
        self._closed = False
        self._connecting = False
        self._probe = None
        self._oauth_worker = None
        self._oauth_workers = []
        from phase_studio.oauth_ui import install_reauthorization
        install_reauthorization(self.store)
        self.setObjectName("sharpedAccessDialog")
        self.setWindowTitle("Connect to SharpED")
        self.setModal(True)
        self._authorization_url = None
        self._browser_failed = False
        self._saved_manual_key = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        branding = create_phase_studio_brand_header()
        branding.layout().setContentsMargins(16, 6, 16, 6)
        root.addWidget(branding)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(6)
        title_row = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(_account_icon())
        title_row.addWidget(icon, 0, Qt.AlignVCenter)
        self.heading = QLabel("Connect to SharpED")
        self.heading.setWordWrap(True)
        self.heading.setStyleSheet('font-family:"Segoe UI"; font-size:17pt; font-weight:600; color:#001170;')
        title_row.addWidget(self.heading, 1)
        layout.addLayout(title_row)

        def paragraph(text, name="", target=layout):
            label = QLabel(text)
            label.setWordWrap(True)
            if name:
                label.setObjectName(name)
            target.addWidget(label)
            return label

        self.description = paragraph(
            "Sign in with your existing Jana2020 account to use SharpED's online electron-density processing.",
            "sharpedAccountSubtitle",
        )
        self.sign_in_button = QPushButton("Sign in with Jana2020")
        self.sign_in_button.setObjectName("primaryButton")
        self.sign_in_button.setMinimumHeight(40)
        self.sign_in_button.setDefault(True)
        self.sign_in_button.clicked.connect(self._primary_action)
        layout.addWidget(self.sign_in_button)
        self.reassurance = paragraph("Opens your browser. Phase Studio continues automatically after sign-in.")
        self.reassurance.setStyleSheet("color:#526680; font-size:9pt;")

        self.progress = QLabel("Working…")
        self.progress.setStyleSheet("color:#526680;")
        self._busy_tick = 0
        self._busy_timer = QTimer(self)
        self._busy_timer.setInterval(300)
        self._busy_timer.timeout.connect(self._animate_busy)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.browser_actions = QWidget()
        browser_row = QHBoxLayout(self.browser_actions)
        browser_row.setContentsMargins(0, 0, 0, 0)
        self.reopen_button = QPushButton("Open browser again")
        self.reopen_button.clicked.connect(self._reopen_browser)
        self.reopen_button.setEnabled(False)
        self.cancel_sign_in_button = QPushButton("Cancel sign-in")
        self.cancel_sign_in_button.clicked.connect(self._cancel_sign_in)
        browser_row.addWidget(self.reopen_button)
        browser_row.addWidget(self.cancel_sign_in_button)
        layout.addWidget(self.browser_actions)
        self.browser_actions.hide()

        self.manual_button = QPushButton("Use an access key instead ▾")
        self.manual_button.setObjectName("otherSignInOptions")
        self.manual_button.setCheckable(True)
        self.manual_button.setStyleSheet(
            "QPushButton#otherSignInOptions { text-align:left; color:#526680; "
            "background:transparent; border:1px solid transparent; padding:3px 0; font-weight:400; }"
            "QPushButton#otherSignInOptions:hover { color:#001170; }"
            "QPushButton#otherSignInOptions:focus { border-color:#2264b8; }"
        )
        self.manual_button.setAccessibleDescription("Show alternative sign-in using an existing access key.")
        layout.addWidget(self.manual_button)
        self.manual_panel = QWidget()
        layout.addWidget(self.manual_panel)
        manual = QVBoxLayout(self.manual_panel)
        manual.setContentsMargins(0, 6, 0, 0)
        manual.setSpacing(6)
        self.manual_panel.hide()
        paragraph("<b>Use an access key</b>", target=manual)
        paragraph("Use this option if browser sign-in is unavailable.", target=manual)
        key_label = paragraph("SharpED access key", target=manual)
        key_row = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setObjectName("requirementTokenEdit")
        self.key_edit.setAccessibleName("SharpED access key")
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("Paste your access key")
        self.key_edit.setText("" if self.store.is_oauth(str(configured_value or "")) else str(configured_value or ""))
        key_label.setBuddy(self.key_edit)
        class _VisibilityAction(QAction):
            def click(self):
                self.trigger()
        eye = QPixmap(20, 20)
        eye.fill(Qt.transparent)
        painter = QPainter(eye)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#001170"), 1.5))
        painter.drawEllipse(QRectF(1, 5, 18, 10))
        painter.drawEllipse(QRectF(7, 7, 6, 6))
        painter.end()
        self.show_button = _VisibilityAction(QIcon(eye), "Show", self.key_edit)
        self.show_button.setCheckable(True)
        self.show_button.setVisible(False)
        self.show_button.setToolTip("Show access key")
        self.show_button.toggled.connect(self._show_key)
        self.key_edit.addAction(self.show_button, QLineEdit.TrailingPosition)
        from PySide6.QtWidgets import QToolButton
        for button in self.key_edit.findChildren(QToolButton):
            button.setFocusPolicy(Qt.StrongFocus)
        key_row.addWidget(self.key_edit, 1)
        manual.addLayout(key_row)
        self.remember = QCheckBox("Remember access on this device")
        self.remember.setChecked(self.store.persistent_available)
        self.remember.setEnabled(self.store.persistent_available)
        self.management_panel = QWidget()
        management = QVBoxLayout(self.management_panel)
        management.setContentsMargins(0, 0, 0, 0)
        management.addWidget(self.remember)
        paragraph(
            "Uncheck Remember for this session only. Use Remove saved access to delete a stored key."
            if self.store.persistent_available else
            "Secure storage is unavailable. Your access key will be used for this session only.",
            target=management,
        )
        if not self.store.persistent_available:
            paragraph("Your access key will be used for this session only.", target=manual)
        manage_row = QHBoxLayout()
        self.replace_button = QPushButton("Replace access key")
        self.remove_button = QPushButton("Remove saved access")
        self.replace_button.clicked.connect(self._replace_key)
        self.remove_button.clicked.connect(self._remove_key)
        self.remove_button.setEnabled(self.store.remembered(base_url))
        manage_row.addWidget(self.replace_button)
        manage_row.addWidget(self.remove_button)
        management.addLayout(manage_row)
        self.management_button = QPushButton("Manage saved access ▾" if self.store.remembered(base_url) else "Saving options ▾")
        self.management_button.setCheckable(True)
        self.management_button.setVisible(self.store.persistent_available or self.store.remembered(base_url))
        manual.addWidget(self.management_button)
        manual.addWidget(self.management_panel)
        self.management_panel.hide()
        self.management_button.toggled.connect(self._show_management)
        self.sign_out_button = QPushButton("Sign out")
        self.sign_out_button.clicked.connect(self._sign_out)
        self.sign_out_button.setVisible(self.store.authentication_method(base_url) == "oauth")
        manual.addWidget(self.sign_out_button)
        self.connect_button = QPushButton("Connect using access key")
        self.connect_button.clicked.connect(self._connect_access)
        manual.addWidget(self.connect_button)
        self.key_edit.returnPressed.connect(self._connect_access)
        self.account_button = QPushButton("Get an access key ↗")
        self.account_button.setObjectName("requirementOpenAccountButton")
        self.account_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(reqs.SHARPED_ACCOUNT_URL)))
        manual.addWidget(self.account_button)
        self.help_button = QPushButton("Show access-key instructions ▾")
        self.help_button.setCheckable(True)
        manual.addWidget(self.help_button)
        self.help_panel = QWidget()
        help_layout = QVBoxLayout(self.help_panel)
        help_layout.setContentsMargins(0, 0, 0, 0)
        paragraph(
            "1. Open the SharpED Tool page.<br>"
            "2. Sign in with your existing Jana2020 account if prompted. The website may first redirect you to Jana2020 sign-in.<br>"
            "3. Expand <b>API tokens for desktop application</b> using <b>Show</b>.<br>"
            "4. Enter a <b>New token name</b> and click <b>Create token</b>.<br>"
            "5. Copy your access key and paste it into Phase Studio.",
            "sharpedAccessInstructions", target=help_layout,
        )
        paragraph("The connection check sends no electron-density data. Access-key permission is confirmed when online processing starts.",
                  "sharpedVerificationNote", target=help_layout)
        manual.addWidget(self.help_panel)
        self.help_panel.hide()
        self.help_button.toggled.connect(self._show_help)
        for button in (self.account_button, self.help_button, self.management_button):
            button.setStyleSheet("QPushButton {text-align:left; color:#526680; background:transparent; border:1px solid transparent; padding:3px 0; font-weight:400;} QPushButton:focus {border-color:#2264b8;}")
        self.feedback = paragraph("", "requirementFeedback")
        self.feedback.hide()
        self._scroll.setWidget(body)
        root.addWidget(self._scroll, 1)

        self._footer = QWidget()
        self._footer.setObjectName("wizardFooter")
        actions = QHBoxLayout(self._footer)
        actions.setContentsMargins(20, 8, 20, 10)
        self.back_button = QPushButton("Back")
        self.back_button.setObjectName("requirementSkipButton")
        self.back_button.clicked.connect(self.reject)
        actions.addWidget(self.back_button)
        actions.addStretch(1)
        root.addWidget(self._footer)
        for button in self.findChildren(QPushButton):
            if button is not self.sign_in_button:
                button.setAutoDefault(False)
        self.manual_button.toggled.connect(self._show_manual)
        self._idle_state()
        if status is not None and status.state not in {reqs.RequirementState.TOKEN_MISSING, reqs.RequirementState.OK}:
            if status.state == reqs.RequirementState.ACCESS_DENIED:
                # A generic 403 does not establish a subscription/entitlement reason.
                self._present("denied", "SharpED did not allow this request. Check your access with the service administrator.")
            elif status.state in {reqs.RequirementState.SERVER_UNREACHABLE, reqs.RequirementState.SERVER_UNAVAILABLE}:
                self._present("api_network")
            else:self.show_feedback(status.message)
        self._fit_dialog()
        activate_owned_dialog(self)
        self.sign_in_button.setFocus(Qt.OtherFocusReason)

    def _fit_dialog(self):
        width = min(540, max(1, self.screen().availableGeometry().width() - 24))
        body_height = self._scroll.widget().layout().totalHeightForWidth(width)
        chrome = self.layout().itemAt(0).sizeHint().height() + (0 if self._footer.isHidden() else self._footer.sizeHint().height())
        state = getattr(self, "presentation_state", "initial")
        minimum = 300 if state in {"initial", "expired"} else 240
        height = max(minimum, body_height + chrome + 4)
        apply_safe_dialog_geometry(self, 540, height, height_fraction=.94)

    def _show_manual(self, expanded):
        self.manual_panel.setVisible(expanded)
        self.show_button.setVisible(expanded)
        if expanded and self._saved_manual_key is None:
            self._saved_manual_key = ""
            if self.store.backend is not None:
                try:self._saved_manual_key = self.store.backend.read(credential_origin(self.base_url)) or ""
                except (OSError, ValueError, UnicodeError):pass
            self.store._redact(self._saved_manual_key)
            self.remember.setChecked(self.store.persistent_available)
            self.remove_button.setEnabled(bool(self._saved_manual_key))
            self.management_button.setText("Manage saved access ▾" if self._saved_manual_key else "Saving options ▾")
        self.manual_button.setText("Use an access key instead ▴" if expanded else "Use an access key instead ▾")
        self.sign_in_button.setDefault(not expanded)
        self.connect_button.setDefault(expanded)
        self._fit_dialog()
        if expanded:
            self.key_edit.setFocus()
        else:
            self.show_button.setChecked(False)
            self.sign_in_button.setFocus()

    def _show_help(self, expanded):
        self.help_panel.setVisible(expanded)
        self.help_button.setText("Hide access-key instructions ▴" if expanded else "Show access-key instructions ▾")
        self._fit_dialog()

    def _show_management(self, expanded):
        self.management_panel.setVisible(expanded)
        self._fit_dialog()

    def _animate_busy(self):
        self._busy_tick = (self._busy_tick + 1) % 4
        self.progress.setText("Working" + "." * self._busy_tick)

    def _present(self, state, message=None):
        self.presentation_state = state
        self.authentication_state = {'initial':'Ready','expired':'Authentication expired',
            'opening':'Opening browser','waiting':'Waiting for browser authentication',
            'exchange':'Verifying credentials','connected':'Connected','cancelled':'Authentication cancelled',
            'error':'Authentication failed','denied':'Authentication failed','timeout':'Connection timed out',
            'network':'Connection unavailable','api_network':'Connection unavailable',
            'api_retry':'Verifying credentials'}[state]
        oauth_busy = state in {"opening", "waiting", "exchange"}
        busy = oauth_busy or state == "api_retry"
        headings = {"initial":"Connect to SharpED", "expired":"Reconnect to SharpED",
                    "opening":"Opening browser…", "waiting":"Waiting for Jana2020 sign-in…", "exchange":"Connecting to SharpED",
                    "network":"Could not connect to Jana2020", "api_network":"Could not connect to SharpED", "api_retry":"Connecting to SharpED",
                    "timeout":"Sign-in timed out", "error":"Sign-in could not be completed",
                    "denied":"SharpED access unavailable", "connected":"Jana2020 sign-in completed",
                    "cancelled":"Authentication cancelled"}
        descriptions = {
            "initial":"Use your existing Jana2020 account to access SharpED's online electron-density processing.",
            "expired":"Your previous connection has expired. Sign in with Jana2020 to continue.",
            "waiting":"Sign in with your Jana2020 account. Phase Studio will continue automatically.",
            "opening":"Opening your browser for secure Jana2020 sign-in…",
            "exchange":"Completing your secure connection…",
            "network":"Check your internet connection and try again.",
            "api_network":"Check your internet connection and try again.",
            "api_retry":"Checking your connection…",
            "timeout":"Your sign-in wasn't completed in time.",
            "error":"Sign-in could not be completed. Please try again.",
            "denied":"Your Jana2020 account is signed in, but SharpED processing is not currently available for this account.",
            "connected":"Continuing in Phase Studio…",
            "cancelled":"Your workflow settings are unchanged. You can sign in again when ready."}
        self.heading.setText(headings[state])
        self.description.setText(message or descriptions[state])
        self.sign_in_button.setText("Try again" if state in {"network","api_network","error"} else
                                    "Sign in again" if state == "timeout" else "Sign in with Jana2020")
        self.sign_in_button.setVisible(not oauth_busy and state not in {"denied","connected"})
        self.sign_in_button.setDefault(not self.sign_in_button.isHidden() and not self.manual_button.isChecked())
        self.back_button.setDefault(state == "denied")
        self.sign_in_button.setEnabled(True)
        self.reassurance.setVisible(state in {"initial","expired"})
        self.manual_button.setVisible(not busy and state != "connected")
        self.manual_button.setEnabled(True)
        self.back_button.setVisible(not oauth_busy)
        self._footer.setVisible(not oauth_busy)
        self.browser_actions.setVisible(oauth_busy)
        self.reopen_button.setVisible(state == "waiting")
        self.progress.setVisible(busy)
        if busy:self._busy_timer.start()
        else:self._busy_timer.stop()
        self.feedback.hide()
        if state != "connected":self._fit_dialog()

    def _idle_state(self):
        needs_renewal = self.store.authentication_method(self.base_url) == "oauth" and not self.store._oauth.usable()
        expired = needs_renewal and self.store._oauth.expires_at <= time.monotonic()
        self._present("expired" if needs_renewal else "initial",
                      "Continue with Jana2020 sign-in to renew your connection." if needs_renewal and not expired else None)
        self.connect_button.setEnabled(True)

    def _reopen_browser(self):
        if self._oauth_worker and self._authorization_url:
            if not QDesktopServices.openUrl(QUrl(self._authorization_url)):
                self.show_feedback("The browser could not be opened. Please retry.")

    def _primary_action(self):
        if self.presentation_state in {"denied", "connected"}:return
        token = self.store.get(self.base_url) or self.key_edit.text().strip()
        if (self.presentation_state == "api_network" and token
                and (not self.store.is_oauth(token) or self.store._oauth.usable())):
            if self._connecting:return
            self.store._redact(token)
            self._pending_key = token
            self._pending_remember = self.store.remembered(self.base_url)
            self._present("api_retry")
            self._set_connecting(True)
            self.sign_in_button.setText("Checking connection…")
            self._probe = _AccessProbe(self.verify, token)
            self._probe.signals.completed.connect(self._probe_completed)
            QThreadPool.globalInstance().start(self._probe)
        else:self._start_oauth()

    def _cancel_sign_in(self):
        if self._oauth_worker:
            self._oauth_worker.attempt.cancel()
        self._oauth_worker = None
        self._authorization_url = None
        self._idle_state()
        self._present('cancelled')
        self.feedback.hide()
        self._fit_dialog()
        self.sign_in_button.setFocus()
        self.reject()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self._oauth_worker:
            self._cancel_sign_in()
            return
        super().keyPressEvent(event)

    def _sign_out(self):
        if self._oauth_worker:
            self._cancel_sign_in()
        self.store.sign_out_oauth()
        self.selected_key = self.store.get(self.base_url)
        self.show_button.setChecked(False)
        self.key_edit.setText(self.selected_key)
        self.remember.setChecked(self.store.remembered(self.base_url))
        self.remove_button.setEnabled(self.store.remembered(self.base_url))
        self.sign_in_button.setText("Sign in with Jana2020")
        self.sign_out_button.hide()
        self._idle_state()
        self.show_feedback("Signed out of Phase Studio. Your Jana2020 browser session is unchanged.")

    def _start_oauth(self):
        if self._connecting or self._oauth_worker is not None:
            return
        from phase_studio.oauth_ui import OAuthWorker
        try:
            worker = OAuthWorker()
        except Exception:
            self.show_feedback("Jana2020 sign-in is unavailable. Please retry.")
            return
        self._oauth_worker = worker
        self._oauth_workers.append(worker)
        self._browser_failed = False
        self._authorization_url = None
        self.manual_button.setChecked(False)
        self._present("opening")
        self.sign_in_button.hide()
        self.manual_button.setEnabled(False)
        self.connect_button.setEnabled(False)
        self.reassurance.hide()
        self.progress.show()
        self.reopen_button.setEnabled(False)
        self.feedback.setText("Waiting for browser sign-in…")
        self.feedback.hide()
        self._fit_dialog()
        worker.signals.ready.connect(self._open_authorization, Qt.QueuedConnection)
        worker.signals.progress.connect(self._oauth_progress, Qt.QueuedConnection)
        worker.signals.finished.connect(self._oauth_completed, Qt.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    def _open_authorization(self, url):
        worker = self._oauth_worker
        if self.sender() is not None and (worker is None or self.sender() != worker.signals):
            return
        if self._closed or worker is None:
            if worker:
                worker.attempt.cancel()
            return
        self._authorization_url = url
        self.reopen_button.setEnabled(True)
        if not QDesktopServices.openUrl(QUrl(url)):
            self._browser_failed = True
            worker.attempt.cancel()
            self.show_feedback("The browser could not be opened. Please retry.")
        else:
            self._present("waiting")
            self.feedback.setText("Complete your Jana2020 sign-in in the browser.")

    def _oauth_progress(self, state):
        worker = self._oauth_worker
        if self.sender() is not None and (worker is None or self.sender() != worker.signals):
            return
        if not self._closed and worker:
            self._present("exchange")
            self.reopen_button.setEnabled(False)

    def _oauth_completed(self, credential, error):
        worker = self._oauth_worker
        sender = self.sender()
        finished = [item for item in self._oauth_workers
                    if item.signals == (sender if sender is not None else getattr(worker, "signals", None))]
        # Keep the signal sender alive through this queued slot. Releasing its
        # last Python owner inside the signal delivery can destroy the QObject.
        QTimer.singleShot(0, self, lambda: self._release_oauth_workers(finished))
        if self.sender() is not None and (worker is None or self.sender() != worker.signals):
            return
        if self._closed or self._oauth_worker is None:
            return
        self._oauth_worker = None
        self._authorization_url = None
        self._idle_state()
        if error:
            reason = getattr(error, "kind", "unknown")
            safe_reason = reason if reason in {"cancelled","timeout","network","configuration","exchange","response","browser","port"} else "unknown"
            logging.getLogger(__name__).debug("Jana2020 sign-in failed; reason=%s", safe_reason)
            if getattr(error, "kind", None) == "cancelled" and not self._browser_failed:
                self._present('cancelled')
                self.reject()
            else:
                kind = getattr(error, "kind", None)
                self._present("timeout" if kind == "timeout" else "network" if kind == "network" else "error",
                              "Your browser could not be opened. Please try again." if self._browser_failed else None)
            self._fit_dialog()
            return
        self.store.activate_oauth(credential, remember=self.store.persistent_available)
        if self.store.oauth_storage_error:
            logging.getLogger(__name__).warning("Jana2020 sign-in works for this session, but secure storage is unavailable.")
            QMessageBox.warning(self, "Sign-in could not be remembered",
                "You are signed in for this session. Windows secure storage could not save the sign-in; "
                "the next calculation may ask you to sign in again.")
        verification = getattr(self.store, '_access_verification', {})
        verification[self.base_url] = (hashlib.sha256(credential.access_token.encode('utf8')).hexdigest(),'Connected')
        self.store._access_verification = verification
        self.selected_key = credential.access_token
        self.checked_status = reqs.RequirementStatus(reqs.RequirementKind.SHARPED, reqs.RequirementState.OK)
        self._present("connected")
        self.sign_in_button.hide()
        self.manual_button.hide()
        self.reassurance.hide()
        self.feedback.hide()
        activate_owned_dialog(self)
        self.accept()

    def _release_oauth_workers(self, finished):
        self._oauth_workers = [item for item in self._oauth_workers if item not in finished]

    def show_feedback(self, message: str) -> None:
        self.feedback.setText(message)
        self.feedback.setVisible(True)
        if hasattr(self, "_scroll"):
            self._fit_dialog()
            QTimer.singleShot(0, self, lambda: self._scroll.ensureWidgetVisible(self.feedback))

    def _show_key(self, show: bool) -> None:
        self.key_edit.setEchoMode(QLineEdit.Normal if show else QLineEdit.Password)
        self.show_button.setText("Hide" if show else "Show")
        self.show_button.setToolTip("Hide access key" if show else "Show access key")

    def _replace_key(self) -> None:
        self.show_button.setChecked(False)
        self.key_edit.clear()
        self.key_edit.setFocus()

    def _remove_key(self) -> None:
        try:
            self.store.remove(self.base_url)
        except OSError:
            self.show_feedback("Saved access could not be removed. Please try again.")
            return
        self.remember.setChecked(False)
        self._saved_manual_key = ""
        self.remove_button.setEnabled(False)
        self._replace_key()
        self.show_feedback("Saved SharpED access removed from this device.")

    def _set_connecting(self, connecting: bool) -> None:
        self._connecting = connecting
        for widget in (self.key_edit, self.show_button, self.replace_button, self.remove_button, self.connect_button):
            widget.setEnabled(not connecting)
        self.remember.setEnabled(not connecting and self.store.persistent_available)
        self.sign_in_button.setEnabled(not connecting)
        self.manual_button.setEnabled(not connecting)
        self.connect_button.setText("Connecting…" if connecting else "Connect using access key")
        if not connecting:
            self.remove_button.setEnabled(bool(self._saved_manual_key) or self.store.remembered(self.base_url))

    def _connect_access(self) -> None:
        if self._connecting or self._oauth_worker is not None:
            return
        token = self.key_edit.text().strip()
        if not token:
            self.show_feedback("Enter your SharpED access key to continue.")
            return
        saved = self._saved_manual_key or ""
        if not saved and self.store.backend is not None:
            try:saved = self.store.backend.read(credential_origin(self.base_url)) or ""
            except (OSError, ValueError, UnicodeError):pass
        if saved and token != saved and self.management_panel.isHidden():
            self.management_button.setChecked(True)
            self.show_feedback("Review saving options before replacing your saved access key, then connect again.")
            return
        self.store._redact(token)
        self._pending_key = token
        self._pending_remember = self.remember.isChecked()
        self._set_connecting(True)
        self.authentication_state = 'Verifying credentials'
        self.show_feedback("Verifying credentials…")
        self._probe = _AccessProbe(self.verify, token)
        self._probe.signals.completed.connect(self._probe_completed)
        QThreadPool.globalInstance().start(self._probe)

    def _probe_completed(self, status) -> None:
        if self._closed:
            return
        self._set_connecting(False)
        verification = getattr(self.store, '_access_verification', {})
        # The legacy manual-key preflight checks the PUBLIC catalogue, not
        # token validity. Never turn that response into verified authentication.
        state = ('Credentials available — not yet verified' if status.ok else 'Authentication expired'
                 if status.state == reqs.RequirementState.TOKEN_REJECTED else 'Connection unavailable')
        verification[self.base_url] = (hashlib.sha256(self._pending_key.encode('utf8')).hexdigest(),state)
        self.store._access_verification = verification
        self.authentication_state = state
        if self.presentation_state == "api_retry":
            if status.ok:
                self.selected_key = self._pending_key
                self.checked_status = status
                self.accept()
            elif status.state == reqs.RequirementState.ACCESS_DENIED:
                self._present("denied", "SharpED did not allow this request. Check your access with the service administrator.")
            elif status.state == reqs.RequirementState.TOKEN_REJECTED:
                self._present("error", "Your connection could not be verified. Sign in with Jana2020 again.")
            else:self._present("api_network")
            return
        if not status.ok:
            self.show_feedback(status.message)
            return
        try:
            self.store.set(self._pending_key, remember=self._pending_remember, base_url=self.base_url)
        except (OSError, ValueError):
            self.show_feedback("Access could not be saved securely. Uncheck Remember to use it for this session only, then retry.")
            return
        self.selected_key = self._pending_key
        self.checked_status = status
        self.accept()

    def done(self, result: int) -> None:
        self._closed = True
        self._busy_timer.stop()
        if self._oauth_worker:
            self._oauth_worker.attempt.cancel()
        self.show_button.setChecked(False)
        super().done(result)


def show_sharped_access_dialog(parent, status, configured_value="", **kwargs) -> Optional[str]:
    store = kwargs.get("store") or credential_store
    from phase_studio.oauth_ui import install_reauthorization
    install_reauthorization(store)
    base_url = kwargs.get("base_url", DEFAULT_SERVER_URL)
    if (store.authentication_method(base_url) == "oauth" and store._oauth.usable()
            and (status is None or status.state == reqs.RequirementState.TOKEN_MISSING)):
        return store.get(base_url)
    active = getattr(store, '_active_access_dialog', None)
    if active is not None:
        active.raise_()
        active.activateWindow()
        return None  # The owning request resumes when its single dialog completes.
    dialog = SharpEDAccessDialog(parent, status, configured_value, **kwargs)
    store._active_access_dialog = dialog
    try:
        dialog.exec()
        return dialog.selected_key
    finally:
        store._active_access_dialog = None
        dialog.deleteLater()
