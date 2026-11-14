"""Bounded, accessible metadata owned by one structural panel."""
from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import QLabel, QSizePolicy, QDialog, QVBoxLayout, QPlainTextEdit, QDialogButtonBox, QApplication


class PanelMetadataLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._full_text = ''
        self._max_lines = 3
        self.setTextFormat(Qt.PlainText)
        self.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        self.setContentsMargins(4, 2, 4, 2)
        self.setMaxLines(3)

    def setMaxLines(self, count):
        self._max_lines = max(1, int(count))
        metrics = self.fontMetrics()
        self.setFixedHeight(metrics.height()+(self._max_lines-1)*metrics.lineSpacing()+4)
        self._wrap()

    def setText(self, text):
        from PySide6.QtGui import QTextDocument
        if '<br>' in text or '<b>' in text:
            document=QTextDocument();document.setHtml(text);plain=document.toPlainText()
        else:plain=text
        self._full_text = plain
        self.setToolTip(text)
        self.setAccessibleName(plain)
        self._wrap()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange, QEvent.StyleChange) and hasattr(self, "_full_text"):
            self.setMaxLines(self._max_lines)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._wrap()

    def _wrap(self):
        metrics = self.fontMetrics()
        width = max(1, self.width()-8)
        words = self._full_text.replace('EDMA asymmetric-unit composition:', 'EDMA ASU:').split()
        lines = []
        truncated=False
        while words and len(lines) < self._max_lines-1:
            line = words.pop(0)
            while words and metrics.horizontalAdvance(line+' '+words[0]) <= width:
                line += ' '+words.pop(0)
            rendered=metrics.elidedText(line, Qt.ElideMiddle, width)
            truncated=truncated or rendered!=line
            lines.append(rendered)
        if words:
            final=' '.join(words)
            self._truncated=truncated or metrics.horizontalAdvance(final)>width
            suffix='  [Details]' if self._truncated and width>metrics.horizontalAdvance('  [Details]')+12 else ''
            lines.append(metrics.elidedText(final, Qt.ElideRight, width-metrics.horizontalAdvance(suffix))+suffix)
        else:
            self._truncated=truncated
            suffix='  [Details]'
            if truncated and lines and width>metrics.horizontalAdvance(suffix)+12:
                lines[-1]=metrics.elidedText(lines[-1],Qt.ElideRight,width-metrics.horizontalAdvance(suffix))+suffix
        self.setCursor(Qt.PointingHandCursor if self._truncated else Qt.ArrowCursor)
        self.setFocusPolicy(Qt.StrongFocus if self._truncated else Qt.NoFocus)
        self.setAccessibleDescription('Click or press Enter for complete panel text.' if self._truncated else '')
        super().setText('\n'.join(lines))

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and getattr(self,'_truncated',False):
            self.show_details();event.accept();return
        super().mousePressEvent(event)

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key_Return,Qt.Key_Enter):
            self.show_details();event.accept();return
        super().keyPressEvent(event)

    def show_details(self):
        original=self._full_text
        dialog=QDialog(self.window());dialog.setWindowTitle('Panel details')
        layout=QVBoxLayout(dialog)
        text=QPlainTextEdit();text.setReadOnly(True);text.setPlainText(original)
        text.setFont(QApplication.font());layout.addWidget(text)
        actions=QDialogButtonBox(QDialogButtonBox.Close)
        copy=actions.addButton('Copy full text',QDialogButtonBox.ActionRole)
        copy.clicked.connect(lambda:QApplication.clipboard().setText(original))
        actions.rejected.connect(dialog.reject);layout.addWidget(actions)
        from .ui_branding import fit_dialog_to_available_screen
        from PySide6.QtCore import QSize
        fit_dialog_to_available_screen(dialog,QSize(620,260))
        self._details_dialog=dialog
        dialog.setAttribute(Qt.WA_DeleteOnClose);dialog.open()
