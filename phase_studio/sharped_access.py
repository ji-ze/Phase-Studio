"""Shared Jana2020-account onboarding for the existing personal-key protocol."""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, QTimer, QUrl, Signal, QRectF
from PySide6.QtGui import QDesktopServices, QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from phase_studio import requirements as reqs
from phase_studio.credentials import credential_store
from phase_studio.sharped_server_client import DEFAULT_SERVER_URL
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
        self.setObjectName("sharpedAccessDialog")
        self.setWindowTitle("Connect to SharpED")
        self.setModal(True)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(create_phase_studio_brand_header())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(6)
        title_row = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(_account_icon())
        title_row.addWidget(icon, 0, Qt.AlignTop)
        titles = QVBoxLayout()
        title = QLabel("Connect to SharpED")
        title.setStyleSheet('font-family:"Segoe UI"; font-size:17pt; font-weight:600; color:#001170;')
        titles.addWidget(title)
        subtitle = QLabel("Use your existing Jana2020 account")
        subtitle.setObjectName("sharpedAccountSubtitle")
        titles.addWidget(subtitle)
        title_row.addLayout(titles, 1)
        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 10, 20, 4)
        header_layout.addLayout(title_row)
        root.addWidget(header)

        def paragraph(text, name=""):
            label = QLabel(text)
            label.setWordWrap(True)
            if name:
                label.setObjectName(name)
            layout.addWidget(label)
            return label

        paragraph(
            "Connect to SharpED using your existing Jana2020 account. "
            "No separate SharpED account is required.", "sharpedAccountExplanation",
        )
        paragraph("<b>Get your access key</b>")
        paragraph(
            "1. Open the SharpED token page.<br>"
            "2. Sign in with your existing Jana2020 account if prompted. The website may first redirect you to Jana2020 sign-in.<br>"
            "3. On the SharpED Tool page, expand <b>API tokens for desktop application</b> using <b>Show</b>.<br>"
            "4. Enter a <b>New token name</b> (for example, Phase Studio laptop) and click <b>Create token</b>.<br>"
            "5. Copy the newly generated access key and paste it below.", "sharpedAccessInstructions",
        )
        account_row = QHBoxLayout()
        self.account_button = QPushButton("Open SharpED token page")
        self.account_button.setObjectName("requirementOpenAccountButton")
        self.account_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(reqs.SHARPED_ACCOUNT_URL)))
        account_row.addWidget(self.account_button)
        account_row.addStretch(1)
        layout.addLayout(account_row)
        label_row = QHBoxLayout()
        label_row.addWidget(QLabel("SharpED access key"))
        help_label = QLabel("?")
        help_label.setStyleSheet("color:#001170; border:1px solid #a9bad2; border-radius:7px;")
        help_label.setFixedSize(15, 15)
        help_label.setAlignment(Qt.AlignCenter)
        help_label.setToolTip(
            "An access key, also called an API token, is a private code associated with your "
            "Jana2020 account. Phase Studio uses it to authenticate requests to the SharpED service."
        )
        label_row.addWidget(help_label)
        label_row.addStretch(1)
        layout.addLayout(label_row)
        key_row = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setObjectName("requirementTokenEdit")
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("Paste your access key here")
        self.key_edit.setText(str(configured_value or ""))
        self.show_button = QPushButton("Show")
        self.show_button.setCheckable(True)
        self.show_button.toggled.connect(self._show_key)
        key_row.addWidget(self.key_edit, 1)
        key_row.addWidget(self.show_button)
        layout.addLayout(key_row)
        self.remember = QCheckBox("Remember access on this device")
        self.remember.setChecked(self.store.remembered(base_url))
        self.remember.setEnabled(self.store.persistent_available)
        layout.addWidget(self.remember)
        if not self.store.persistent_available:
            paragraph("Secure saving is unavailable here. Access is kept for this session only.")
        manage_row = QHBoxLayout()
        self.replace_button = QPushButton("Replace access key")
        self.remove_button = QPushButton("Remove saved access")
        self.replace_button.clicked.connect(self._replace_key)
        self.remove_button.clicked.connect(self._remove_key)
        self.remove_button.setEnabled(self.store.remembered(base_url))
        manage_row.addWidget(self.replace_button)
        manage_row.addWidget(self.remove_button)
        manage_row.addStretch(1)
        layout.addLayout(manage_row)
        paragraph(
            "The connection check sends no electron-density data. Access-key permission is "
            "confirmed when online processing starts.", "sharpedVerificationNote",
        )
        paragraph(
            "Electron-density data are sent to the SharpED online service when processing starts. "
            "Online access depends on your account permissions.", "sharpedDataDisclosure",
        )
        paragraph("Phase Studio is free and open source. Superflip-only processing does not require SharpED access.")
        self.feedback = paragraph("", "requirementFeedback")
        self.feedback.setVisible(False)
        layout.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        footer = QWidget()
        footer.setObjectName("wizardFooter")
        actions = QHBoxLayout(footer)
        actions.setContentsMargins(20, 10, 20, 12)
        self.back_button = QPushButton("Back")
        self.back_button.setObjectName("requirementSkipButton")
        self.back_button.clicked.connect(self.reject)
        actions.addWidget(self.back_button)
        actions.addStretch(1)
        self.connect_button = QPushButton("Connect to SharpED")
        self.connect_button.setObjectName("primaryButton")
        self.connect_button.clicked.connect(self._connect_access)
        actions.addWidget(self.connect_button)
        root.addWidget(footer)
        self.key_edit.returnPressed.connect(self._connect_access)
        self._footer = footer
        self._scroll = scroll
        if status is not None and status.state not in {reqs.RequirementState.TOKEN_MISSING, reqs.RequirementState.OK}:
            self.show_feedback(status.message)
        apply_safe_dialog_geometry(self, 630, 650, height_fraction=.94)
        activate_owned_dialog(self)

    def show_feedback(self, message: str) -> None:
        self.feedback.setText(message)
        self.feedback.setVisible(True)
        if hasattr(self, "_scroll"):
            QTimer.singleShot(0, self, lambda: self._scroll.ensureWidgetVisible(self.feedback))

    def _show_key(self, show: bool) -> None:
        self.key_edit.setEchoMode(QLineEdit.Normal if show else QLineEdit.Password)
        self.show_button.setText("Hide" if show else "Show")

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
        self.remove_button.setEnabled(False)
        self._replace_key()
        self.show_feedback("Saved SharpED access removed from this device.")

    def _set_connecting(self, connecting: bool) -> None:
        self._connecting = connecting
        for widget in (self.key_edit, self.show_button, self.replace_button, self.remove_button, self.connect_button):
            widget.setEnabled(not connecting)
        self.remember.setEnabled(not connecting and self.store.persistent_available)
        self.connect_button.setText("Connecting…" if connecting else "Connect to SharpED")
        if not connecting:
            self.remove_button.setEnabled(self.store.remembered(self.base_url))

    def _connect_access(self) -> None:
        if self._connecting:
            return
        token = self.key_edit.text().strip()
        if not token:
            self.show_feedback("Enter your SharpED access key to continue.")
            return
        self.store._redact(token)
        self._pending_key = token
        self._pending_remember = self.remember.isChecked()
        self._set_connecting(True)
        self.show_feedback("Connecting to SharpED…")
        self._probe = _AccessProbe(self.verify, token)
        self._probe.signals.completed.connect(self._probe_completed)
        QThreadPool.globalInstance().start(self._probe)

    def _probe_completed(self, status) -> None:
        if self._closed:
            return
        self._set_connecting(False)
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
        self.show_button.setChecked(False)
        super().done(result)


def show_sharped_access_dialog(parent, status, configured_value="", **kwargs) -> Optional[str]:
    dialog = SharpEDAccessDialog(parent, status, configured_value, **kwargs)
    dialog.exec()
    return dialog.selected_key
