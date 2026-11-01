"""Bounded, accessible metadata owned by one structural panel."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy


class PanelMetadataLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._full_text = ''
        self.setTextFormat(Qt.PlainText)
        self.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        self.setContentsMargins(4, 2, 4, 2)
        self.setFixedHeight(self.fontMetrics().lineSpacing()*3+4)

    def setText(self, text):
        from PySide6.QtGui import QTextDocument
        if '<br>' in text or '<b>' in text:
            document=QTextDocument();document.setHtml(text);plain=document.toPlainText()
        else:plain=text
        self._full_text = plain
        self.setToolTip(text)
        self.setAccessibleName(plain)
        self._wrap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._wrap()

    def _wrap(self):
        metrics = self.fontMetrics()
        width = max(1, self.width()-8)
        words = self._full_text.replace('EDMA asymmetric-unit composition:', 'EDMA ASU:').split()
        lines = []
        while words and len(lines) < 2:
            line = words.pop(0)
            while words and metrics.horizontalAdvance(line+' '+words[0]) <= width:
                line += ' '+words.pop(0)
            lines.append(metrics.elidedText(line, Qt.ElideMiddle, width))
        if words:
            lines.append(metrics.elidedText(' '.join(words), Qt.ElideRight, width))
        super().setText('\n'.join(lines))
