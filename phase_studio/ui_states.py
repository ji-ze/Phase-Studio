"""Neutral, compact information for scientifically unavailable analyses."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QSizePolicy


class UnavailableState(QWidget):
    def __init__(self, title, reason, available, required, *, action=None, parent=None):
        super().__init__(parent)
        self.setObjectName('analysisUnavailableState')
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        for text, heading in ((title, True), (reason, False), ('Available: '+available, False), ('Required: '+required, False)):
            label = QLabel(text)
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            if heading:label.setObjectName('sectionLabel')
            layout.addWidget(label)
        if action:
            button = QPushButton(action[0])
            button.clicked.connect(action[1])
            layout.addWidget(button, alignment=Qt.AlignLeft)
