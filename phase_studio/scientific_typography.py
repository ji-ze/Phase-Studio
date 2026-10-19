"""Display-only scientific notation; never apply to protocol or data fields."""
import html
import re

_SYMBOLS = {
    'd_min': ('<i>d</i><sub>min</sub>', r'$d_{\mathrm{min}}$'),
    'd98': ('<i>d</i><sub>98</sub>', r'$d_{98}$'),
    'Iobs': ('<i>I</i><sub>obs</sub>', r'$I_{\mathrm{obs}}$'),
    'Fobs': ('<i>F</i><sub>obs</sub>', r'$F_{\mathrm{obs}}$'),
    'sinθ/λ': ('sin <i>θ</i> / <i>λ</i>', r'$\sin\theta/\lambda$'),
}
for _letter in ('R', 'B'):
    for _sub in ('int', 'merge', 'meas', 'pim', 'work', 'free', 'iso', 'wp', 'exp'):
        _SYMBOLS[_letter+'_'+_sub] = (f'<i>{_letter}</i><sub>{_sub}</sub>', '$'+_letter+r'_{\mathrm{'+_sub+'}}$')
_SYMBOLS['CC1/2'] = ('<i>CC</i><sub>1/2</sub>', r'$CC_{1/2}$')
for _alias, _name in {'d_98':'d98', 'I_obs':'Iobs', 'F_obs':'Fobs',
                      'sin(theta)/lambda':'sinθ/λ', 'sinθ / λ':'sinθ/λ'}.items():
    _SYMBOLS[_alias] = _SYMBOLS[_name]
_SYMBOLS['2θ'] = ('2<i>θ</i>', r'$2\theta$')
_SYMBOLS['F²'] = ('<i>F</i><sup>2</sup>', r'$F^2$')
_SYMBOLS['Biso'] = _SYMBOLS['B_iso']
for _variable in ('I','F'):
    _SYMBOLS['sigma('+_variable+')'] = ('<i>σ</i>(<i>'+_variable+'</i>)', r'$\sigma('+_variable+')$')
for _char in 'IFσθλαβγ':
    _SYMBOLS[_char] = (f'<i>{_char}</i>', '$'+_char+'$')
for _char in 'abcdhkl':
    _SYMBOLS[_char] = (f'<i>{_char}</i>', '$'+_char+'$')
for _word, _symbol in {'lambda':'λ', 'theta':'θ', 'alpha':'α', 'beta':'β', 'gamma':'γ'}.items():
    _SYMBOLS[_word] = _SYMBOLS[_symbol]
_PATTERN = re.compile('|'.join(re.escape(k) for k in sorted(_SYMBOLS, key=len, reverse=True)))


def scientific_text(text, target='qt'):
    """Render variable tokens inline, escaping prose for Qt rich text."""
    text = str(text)
    pieces = []
    previous = 0
    for match in _PATTERN.finditer(text):
        start, end = match.span()
        if (start and (text[start-1].isalnum() or text[start-1] == '_')) or (end < len(text) and (text[end].isalnum() or text[end] == '_')):
            continue
        # The English article is prose, not a unit-cell variable. Cell labels,
        # assignments and the conventional a, b, c list remain mathematical.
        if match.group() == 'a' and text.strip() != 'a' and not re.match(r'\s*(?:=|,|\(Å\))', text[end:]):
            continue
        pieces.append(html.escape(text[previous:start]) if target == 'qt' else text[previous:start])
        pieces.append(_SYMBOLS[match.group()][target == 'plot'])
        previous = end
    pieces.append(html.escape(text[previous:]) if target == 'qt' else text[previous:])
    return ''.join(pieces).replace('\n', '<br>') if target == 'qt' else ''.join(pieces)


def scientific_tooltip(text, literal=False):
    """Rich tooltips share the label vocabulary; source strings stay untouched."""
    from .ui_style import _TOOLTIP_WRAP_PREFIX
    text = str(text)
    if text.startswith(_TOOLTIP_WRAP_PREFIX):
        return text
    body = html.escape(text) if literal else scientific_text(text)
    return _TOOLTIP_WRAP_PREFIX+'380px;">'+body+'</div>'


def install_scientific_headers(table):
    """Paint rich display headers while preserving plain item text and sorting."""
    from PySide6.QtCore import Qt, QSize
    from PySide6.QtGui import QTextDocument
    from PySide6.QtWidgets import QHeaderView, QStyleOptionHeader, QStyle

    class ScientificHeader(QHeaderView):
        def paintSection(self, painter, rect, index):
            if not rect.isValid():
                return
            painter.save()
            option = QStyleOptionHeader()
            self.initStyleOptionForIndex(option, index)
            option.rect = rect
            text = option.text
            option.text = ''
            self.style().drawControl(QStyle.CE_Header, option, painter, self)
            document = QTextDocument()
            document.setDefaultFont(self.font())
            document.setHtml(scientific_text(text))
            document.setTextWidth(max(1, rect.width()-12))
            painter.translate(rect.left()+6, rect.top()+max(0, (rect.height()-document.size().height())/2))
            document.drawContents(painter)
            painter.restore()

        def sizeHint(self):
            size = super().sizeHint()
            return QSize(size.width(), max(size.height(), 46))

    header = ScientificHeader(Qt.Horizontal, table)
    table.setHorizontalHeader(header)
    return header
