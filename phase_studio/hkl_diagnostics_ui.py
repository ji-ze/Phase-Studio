"""Views of the common read-only diagnostic result; no scientific mutations."""
import math
from dataclasses import replace
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt, QTimer, QSize, QSettings, QRect
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QWidget,QLabel,
    QPushButton,QLineEdit,QTableWidget,QTableWidgetItem,QHeaderView,QSplitter,QScrollArea,QTabWidget,
    QFormLayout,QCheckBox,QComboBox,QSizePolicy,QDoubleSpinBox,QGridLayout,QToolButton,
    QAbstractItemView)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from .hkl_diagnostics import build_diagnostics, export_shell_csv
from .scientific_typography import scientific_text, scientific_tooltip, install_scientific_headers


def number(value):
    return 'n/a' if value is None or not math.isfinite(float(value)) else f'{value:.7g}'


def _report(result):
    if result.diagnostics is not None:
        return result.diagnostics
    report = build_diagnostics(result)
    if hasattr(result,'bins'):
        from dataclasses import replace
        from .hkl_diagnostics import shell_statistics
        report = replace(report,shells=shell_statistics(result,report))
    return report


DIRECT_LABEL = 'F/σ(F)'
DERIVED_LABEL = 'Derived I/σ(I) ≈ |F|/(2σ(F))'
D98_NOT_REACHED = 'Cumulative symmetry-allowed HKL coverage does not reach 98% within the analyzed resolution domain.'
SIGNED_CONVENTION = 'Direct F/σ(F) retains the sign of F. Negative amplitudes are not converted to absolute values. Only finite non-000 records with positive finite σ(F) contribute.'


def presentation_report(result):
    """Add direct amplitude display data without altering the validated report.

    Historical mean_significance fields retain their derived intensity meaning.
    Only the new explicitly named amplitude fields are added to analytical exports.
    """
    from . import app as a
    report = _report(result)
    if not (a.reflection_mode_is_amplitude(result.data_mode) and report.available('significance')):
        return report
    cached = getattr(result,'_hkl_presentation_cache',None)
    if cached is not None and cached[0] is report:
        return cached[1]
    raw = getattr(result,'reflections_raw',getattr(result,'reflections',()))
    direct = np.asarray([a.reflection_amplitude_signal_to_noise(r) if (r.h,r.k,r.l)!=(0,0,0) else None for r in raw],dtype=float)
    finite = direct[np.isfinite(direct)]
    stats = dict(report.statistics)
    stats.update(mean_f_over_sigma=float(np.mean(finite)) if len(finite) else None,
                 median_f_over_sigma=float(np.median(finite)) if len(finite) else None)
    shells = report.shells
    if shells:
        hkls = np.asarray([(r.h,r.k,r.l) for r in raw],dtype=np.int32)
        stl = a.hkl_stl_array_from_metric(a.reciprocal_metric_tensor(result.cell),hkls)
        updated = []
        for shell in shells:
            row = dict(shell)
            values = direct[(stl>row['lo']) & (stl<=row['hi']) & np.isfinite(direct)]
            row.update(mean_f_over_sigma=float(np.mean(values)) if len(values) else None,
                       median_f_over_sigma=float(np.median(values)) if len(values) else None)
            updated.append(tuple(row.items()))
        shells = tuple(updated)
    adapted = replace(report,statistics=tuple(stats.items()),shells=shells,methods=report.methods+(SIGNED_CONVENTION,))
    result._hkl_presentation_cache = (report,adapted)
    return adapted


def _interpretation(report):
    if report.data_type.startswith('Powder'):
        overlap = dict(report.overlap)
        status = 'Estimated geometric overlap' if overlap.get('estimated') else 'Authoritative overlap groups' if overlap['available'] else 'Overlap metadata unavailable'
        return 'Powder peak list · FWHM is not measurement uncertainty · '+status
    phase = 'Phases not supplied (expected)' if report.phase_status.startswith('Phases not supplied') else 'Phase provenance unverified'
    if report.statistic('mean_f_over_sigma') is not None:
        return 'Amplitude data · F/σ(F) available · '+phase
    if report.available('significance'):
        return 'Intensity data · I/σ(I) available · '+phase
    return report.data_type+' · Measurement significance unavailable'


def _top(win, dialog, result, report, completeness=False):
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(10,8,10,8)
    layout.setSpacing(3 if completeness else 5)
    invalid = report.count('invalid_values') + report.count('rejected_records')
    status = 'INVALID' if not report.count('parsed_records') else 'WARNINGS' if invalid or any(s=='WARNING' for s,_ in report.warnings) else 'PARSED'
    subtitle = report.data_type
    if 'synthetic' in report.source_note.lower():
        subtitle += ' · SYNTHETIC CONTROLLED FIXTURE'
    layout.addWidget(win._diagnostic_header('HKL COMPLETENESS' if completeness else 'HKL VALIDATION',subtitle,status,compact=True))
    top = QWidget()
    body = QVBoxLayout(top)
    body.setContentsMargins(0,0,0,0)
    body.setSpacing(3)
    symbol, symmetry_metadata = _spacegroup_display(result.spacegroup_hm)
    summary = win._diagnostic_input_summary(result.hkl_path,result.data_mode,result.cell,
        symbol,result.source_note,compact=True)
    if completeness:
        summary.setTitle('')
        summary.setStyleSheet('QGroupBox#diagnosticSection { margin-top:0; padding:2px 4px 1px 4px; }')
    for label in summary.findChildren(QLabel):
        if label.text() == symbol:
            label.setToolTip(symmetry_metadata)
    body.addWidget(summary)
    issues = sum(report.count(key) for key in ('invalid_values','invalid_auxiliary','phase_nonfinite','invalid_reciprocal_values','rejected_records','exact_duplicate_entries','conflicting_duplicate_groups'))
    count = QLabel(f'Parsed records: {report.count("parsed_records"):,} · Literal unique HKL: {report.count("literal_unique"):,} · '
                   f'Input-integrity issues: {issues:,}')
    count.setToolTip('Issue tally = invalid-value records + invalid auxiliary values + nonfinite phases + invalid reciprocal values + rejected records + exact duplicate entries + conflicting duplicate groups. Categories can overlap; this is not a count of distinct faulty records or a scientific validity verdict. '
                     f'Symmetry-independent orbits: {report.count("symmetry_orbits"):,}; Friedel pairs are combined for coverage.')
    dialog.hkl_integrity_summary = count
    count.setWordWrap(True)
    body.addWidget(count)
    interpretation = QLabel('Data interpretation: ' + _interpretation(report))
    interpretation.setWordWrap(True)
    interpretation.setToolTip('Open Advanced diagnostics and definitions for complete caveats and input provenance.')
    body.addWidget(interpretation)
    layout.addWidget(top)
    dialog.hkl_input_summary = summary
    dialog.hkl_interpretation = interpretation
    overlap = dict(report.overlap)
    if report.data_type.startswith('Powder') and report.fwhm_units=='degrees_2theta' and not overlap['available'] and not overlap.get('wavelength') and 'Wavelength missing' in overlap['reason']:
        prompt = QLabel('Wavelength required for peak overlap. Enter the measured wavelength; overlap numbers and graphs are hidden until it is known.')
        prompt.setWordWrap(True)
        layout.addWidget(prompt)
        row = QHBoxLayout()
        row.addWidget(QLabel('Wavelength (Å)'))
        spin = QDoubleSpinBox()
        spin.setRange(0,100)
        spin.setDecimals(6)
        spin.setSpecialValueText('Required')
        spin.setValue(0)
        row.addWidget(spin)
        apply = QPushButton('Analyze peak overlap')
        apply.setEnabled(False)
        spin.valueChanged.connect(lambda value:apply.setEnabled(value>0))
        row.addWidget(apply)
        row.addStretch(1)
        layout.addLayout(row)
        def analyze_supplied_wavelength():
            from .hkl_diagnostics import shell_statistics
            supplied = replace(result,diagnostics=None)
            supplied.powder_diagnostic_context = dict(
                source=overlap.get('input_source'),fwhm_units='degrees_2theta',
                wavelength=spin.value(),wavelength_source='user-entered diagnostic wavelength',
                separation_factor=overlap.get('separation_factor',.2),
                separation_source=overlap.get('separation_source'))
            updated = build_diagnostics(supplied)
            if completeness:
                updated = replace(updated,shells=shell_statistics(supplied,updated))
            supplied.diagnostics = updated
            review = win._build_hkl_completeness_dialog(supplied) if completeness else win._build_hkl_validation_dialog(supplied)
            dialog.hkl_wavelength_result = review
            review.exec()
        apply.clicked.connect(analyze_supplied_wavelength)
        dialog.hkl_wavelength_spin = spin
        dialog.hkl_wavelength_apply = apply
    return layout


def _details(layout, dialog, report, result=None):
    button = QPushButton('Advanced diagnostics and definitions')
    button.setCheckable(True)
    layout.addWidget(button, 0, Qt.AlignRight)
    dialog.hkl_advanced_button = button
    dialog.hkl_advanced = None

    def toggle(opened):
        if dialog.hkl_advanced is None and opened:
            if not hasattr(dialog, 'hkl_resolution_summary') and result is not None:
                from . import app as a
                try:
                    analyzed = a.analyze_hkl_data(result.hkl_path, result.data_mode, result.cell,
                        result.spacegroup, result.spacegroup_hm, result.source_note, _loaded=result)
                except ValueError as error:
                    dialog.hkl_resolution_summary = [('Resolution summary', 'N/A — '+str(error))]
                else:
                    dialog.hkl_resolution_summary = _resolution_summary(analyzed)
            dialog.hkl_advanced = _detail_dialog(dialog, report)
            dialog.hkl_advanced.finished.connect(lambda _result: button.setChecked(False))
            dialog.finished.connect(dialog.hkl_advanced.close)
        if dialog.hkl_advanced is not None:
            if opened:
                dialog.hkl_advanced.show()
            else:
                dialog.hkl_advanced.close()
    button.toggled.connect(toggle)


class _DiagnosticRows(QWidget):
    """A compact, top-aligned information table shared by all detail pages."""
    def __init__(self, rows, parent=None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(7)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 3)
        self.values = {}
        for row, (key, value) in enumerate(rows):
            label = QLabel(scientific_text(key))
            label.setWordWrap(True)
            label.setMaximumWidth(280)
            label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            label.setStyleSheet('font-weight:400; color:#33456e;')
            text = value if isinstance(value, QWidget) else QLabel(str(value))
            if isinstance(text, QLabel):
                text.setTextFormat(Qt.RichText)
                if not isinstance(value, QWidget):
                    text.setText(scientific_text(value))
                if key == 'Full input path':
                    text.setTextFormat(Qt.PlainText)
                    text.setText(str(value))
                text.setWordWrap(True)
                text.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
                text.setFocusPolicy(Qt.StrongFocus)
                text.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            text.setAccessibleName(str(key))
            grid.addWidget(label, row, 0, Qt.AlignTop)
            grid.addWidget(text, row, 1)
            self.values[key] = text


def _disclosure(layout, title, content):
    button = QToolButton()
    button.setText(title)
    button.setCheckable(True)
    button.setAutoRaise(True)
    button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    button.setArrowType(Qt.RightArrow)
    content.setVisible(False)
    def expand(checked):
        content.setVisible(checked)
        button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
    button.toggled.connect(expand)
    layout.addWidget(button, 0, Qt.AlignLeft)
    layout.addWidget(content)
    return button


def _spacegroup_display(raw):
    """Shorten only a setting Gemmi can verify; retain the exact setting."""
    import gemmi
    try:
        group = gemmi.find_spacegroup_by_name(raw)
        if group is None:
            return raw, raw
        symbol = group.short_name().replace('21', '2₁').replace('31', '3₁').replace('32', '3₂')
        symbol = symbol.replace('41', '4₁').replace('42', '4₂').replace('43', '4₃')
        symbol = symbol.replace('61', '6₁').replace('62', '6₂').replace('63', '6₃').replace('64', '6₄').replace('65', '6₅')
        return f'{symbol} (#{group.number})', f'Original setting: {raw}\nHall: {group.hall}\nFull Hermann–Mauguin: {group.xhm()}'
    except (ValueError, RuntimeError):
        return raw, raw


def _cell_display(cell):
    if len(cell) != 6:
        return 'Not supplied'
    return (f'a = {cell[0]:.4f}, b = {cell[1]:.4f}, c = {cell[2]:.4f} Å\n'
            f'α = {cell[3]:.3f}°, β = {cell[4]:.3f}°, γ = {cell[5]:.3f}°')


def _file_provenance(report):
    note = report.source_note
    if 'fbegin/endf block exported from ' in note:
        return 'Jana2020 / Superflip input', 'Jana2020 / Superflip export'
    if 'synthetic' in note.lower() or 'fixture' in note.lower():
        return 'Controlled test fixture', 'Test fixture'
    if Path(report.source).suffix.lower() == '.inflip':
        return 'Superflip input', 'Not independently documented'
    return 'External HKL file', 'Not documented in the available input'


class _AdvancedDiagnosticsDialog(QDialog):
    def done(self, result):
        self.hkl_settings.setValue('hklAdvanced/geometry', self.saveGeometry())
        self.hkl_settings.setValue('hklAdvanced/size', self.size())
        self.hkl_settings.setValue('hklAdvanced/tab', self.hkl_details_tabs.currentIndex())
        self.hkl_settings.sync()
        super().done(result)


class _CapabilityTable(QTableWidget):
    """Viewport-proportional columns, with complete wrapped reasons."""
    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = self.viewport().width()
        if getattr(self, '_proportional_width', None) != width:
            self._proportional_width = width
            first, second = round(width*.25), round(width*.18)
            for column, size in enumerate((first,second,max(1,width-first-second))):
                self.setColumnWidth(column,size)
            self.resizeRowsToContents()
            height = sum(self.rowHeight(row) for row in range(self.rowCount())) + self.horizontalHeader().height() + 2*self.frameWidth()
            if self.height() != height:
                self.setFixedHeight(height)


def _detail_dialog(parent, report):
    """Read-only presentation: reports, counters and export schemas are untouched."""
    from . import app as a
    from .ui_branding import clamp_window_to_available_screen
    detail = _AdvancedDiagnosticsDialog(parent)
    detail.setWindowTitle('HKL advanced diagnostics and definitions')
    detail.setObjectName('hklAdvancedDiagnostics')
    detail.setModal(False)
    detail.hkl_settings = QSettings(QSettings.defaultFormat(), QSettings.UserScope, 'PhaseStudio', 'PhaseStudio')
    root = QVBoxLayout(detail)
    root.setContentsMargins(12, 10, 12, 10)
    root.setSpacing(8)
    tabs = QTabWidget()
    tabs.setUsesScrollButtons(True)
    tabs.setElideMode(Qt.ElideNone)
    tabs.tabBar().setAccessibleName('Diagnostic categories')
    root.addWidget(tabs, 1)
    detail.hkl_detail_rows = {}
    detail.hkl_disclosures = {}
    def page(title):
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(12, 12, 12, 12)
        body.setSpacing(12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(content)
        tabs.addTab(scroll, title)
        return body
    def rows(body, values, section=None):
        if section:
            label = QLabel(section)
            label.setStyleSheet('font-weight:600; color:#33456e; padding-top:3px;')
            body.addWidget(label)
        widget = _DiagnosticRows(values)
        body.addWidget(widget)
        detail.hkl_detail_rows.update(widget.values)
        return widget
    def explanation(text, muted=False):
        label = QLabel(text)
        label.setTextFormat(Qt.RichText)
        label.setText(scientific_text(text))
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        if muted:
            label.setStyleSheet('color:#52627d;')
        return label
    def disclose(body, title, values):
        widget = _DiagnosticRows(values)
        widget.setStyleSheet('QLabel { color:#52627d; }')
        detail.hkl_detail_rows.update(widget.values)
        detail.hkl_disclosures[title] = _disclosure(body, title, widget)
    counts = dict(report.counts)
    labels = {'parsed_records':'Parsed input records', 'literal_unique':'Literally unique HKL triplets',
              'symmetry_orbits':'Symmetry-independent reflection orbits',
              'systematic_absent_entries':'Systematically absent entries',
              'exact_duplicate_entries':'Exact duplicate entries', 'conflicting_duplicate_groups':'Conflicting duplicate groups',
              'equivalent_repeated_entries':'Symmetry-equivalent repeated entries', 'zero_000':'Protocol (0,0,0) records',
              'absent_nonzero_values':'Nonzero systematically absent values',
              'phase_finite':'Finite phase fields', 'phase_missing':'Missing phase values', 'phase_nonfinite':'Nonfinite phase values',
              'absent_significant_3sigma':'Absent reflections with significance ≥3'}
    def count_rows(keys):
        return [(labels.get(key, key.replace('_', ' ').capitalize()),
                 'N/A — no genuine measurement uncertainties' if key == 'absent_significant_3sigma' and not report.available('significance')
                 else 'N/A' if counts.get(key) is None else f'{counts[key]:,}') for key in keys]
    sg, raw_sg = _spacegroup_display(report.spacegroup)
    group = explanation(sg)
    group.setToolTip(raw_sg)
    file_kind, application = _file_provenance(report)
    phase_defined = a.reflection_mode_has_phase(report.data_mode) and report.available('column_semantics')
    phases = ('Not supplied (expected for this format)' if not a.reflection_mode_has_phase(report.data_mode)
              and report.available('column_semantics') else report.phase_status)
    body = page('&Input')
    filename = QWidget()
    filename_row = QHBoxLayout(filename)
    filename_row.setContentsMargins(0, 0, 0, 0)
    name = explanation(Path(report.source).name or 'Not supplied')
    name.setTextFormat(Qt.PlainText)
    name.setText(Path(report.source).name or 'Not supplied')
    name.setProperty('literalPath', True)
    name.setToolTip(report.source)
    filename_row.addWidget(name, 1)
    copy_path = QPushButton('Copy full path')
    copy_path.setAccessibleName('Copy full input path')
    copy_path.clicked.connect(lambda: QApplication.clipboard().setText(report.source))
    filename_row.addWidget(copy_path)
    detail.hkl_copy_path = copy_path
    detail.full_source_path = report.source
    rows(body, [('Input filename', filename), ('Data type', report.data_type), ('Declared data format', report.data_mode)])
    rows(body, [('Space group', group), ('Unit cell', _cell_display(report.cell)), ('Phases', phases)])
    provenance = rows(body, [('File provenance', file_kind), ('Source application', application),
                ('Observation-processing provenance', 'Not documented in the available input' if report.observation_kind == 'unknown' else report.observation_kind)])
    provenance.setStyleSheet('QLabel { color:#52627d; }')
    disclose(body, 'Detailed source provenance', [('Full input path', report.source), ('Source details', report.source_note),
                                                ('Exact symmetry setting', raw_sg)])
    body.addStretch(1)

    body = page('Counts && &symmetry')
    sections = QHBoxLayout()
    left, right = QVBoxLayout(), QVBoxLayout()
    sections.addLayout(left, 1)
    sections.addLayout(right, 1)
    body.addLayout(sections)
    table = rows(left, count_rows(['parsed_records','literal_unique','symmetry_orbits','zero_000','excluded_000']), 'Reflection counts')
    table.values['Parsed input records'].setStyleSheet('font-size:17pt; font-weight:600; color:#001170;')
    cell_rows = ([(name, f'{value:.4f} Å' if index<3 else f'{value:.3f}°')
                  for index,(name,value) in enumerate(zip(('a','b','c','α','β','γ'),report.cell))]
                 if len(report.cell)==6 else [('Unit cell', 'Not supplied')])
    symmetry = rows(right, [('Space group', sg)]+cell_rows, 'Crystal symmetry')
    symmetry.values['Space group'].setToolTip(raw_sg)
    for key, tip in [('Parsed input records','Parsed original records, including any retained protocol 000 record; not necessarily independent measurements.'),
                     ('Literally unique HKL triplets','Distinct integer (h,k,l) triplets, before symmetry equivalence.'),
                     ('Symmetry-independent reflection orbits','Non-000 equivalence classes under the actual input symmetry and established Friedel convention.')]:
        table.values[key].setToolTip(tip)
    disclose(body, 'Counting methodology', [('Coverage and Friedel convention', report.methods[0]), ('Exact symmetry setting', raw_sg)])
    body.addStretch(1)

    body = page('Absences && &duplicates')
    issue_keys = ['systematic_absent_entries','absent_nonzero_values','absent_significant_3sigma',
                  'exact_duplicate_entries','equivalent_repeated_entries','conflicting_duplicate_groups',
                  'invalid_indices','rejected_records','invalid_values','invalid_auxiliary','invalid_reciprocal_values',
                  'missing_auxiliary','phase_missing','phase_nonfinite']
    if not any(counts.get(key) for key in issue_keys) and not any(severity == 'WARNING' for severity, _ in report.warnings):
        status = explanation('No reflection-index, systematic-absence or duplication issues detected.')
        status.setStyleSheet('font-weight:600; color:#33456e;')
        body.addWidget(status)
    rows(body, count_rows(issue_keys[:6]) + [('Forbidden HKL examples', report.absence_examples or 'None'),
                                           ('Conflicting HKL examples', report.duplicate_examples or 'None')])
    body.addWidget(explanation('Small nonzero forbidden values alone are not proof of experimental error. Repeated HKL alone does not establish unmerged observations.', muted=True))
    body.addStretch(1)

    body = page('&Values')
    integrity = count_rows(['invalid_values','zero_values','negative_values','missing_auxiliary','invalid_auxiliary',
                           'rejected_records','invalid_indices','invalid_reciprocal_values'])
    if phase_defined:
        phase_rows = count_rows(['phase_finite','phase_missing','phase_nonfinite'])
    else:
        phase_rows = [('Phase diagnostics', 'N/A — phase column not supplied' if report.available('column_semantics')
                       else 'N/A — phase-column meaning unverified')]
    rows(body, integrity, 'Input integrity')
    rows(body, phase_rows, 'Phase diagnostics')
    powder = report.data_type.startswith('Powder')
    amplitude = a.reflection_mode_is_amplitude(report.data_mode)
    value_kind = ('value (column meaning unverified)' if not report.available('column_semantics')
                  else 'intensity Iobs' if powder or not amplitude else 'amplitude Fobs')
    statistics = [('Mean input '+value_kind, number(report.statistic('mean_value'))),
                  ('Median input '+value_kind, number(report.statistic('median_value')))]
    if powder:
        units = '°' if report.fwhm_units == 'degrees_2theta' else report.fwhm_units
        statistics += [(f'Median FWHM ({units})', number(report.statistic('median_auxiliary'))),
                       (f'FWHM range ({units})', number(report.statistic('minimum_auxiliary'))+' – '+number(report.statistic('maximum_auxiliary'))),
                       ('Verified FWHM units', 'degrees 2θ' if report.fwhm_units == 'degrees_2theta' else 'Not verified; '+report.fwhm_units)]
    elif report.available('significance'):
        statistics += [('Median measurement uncertainty', number(report.statistic('median_auxiliary'))),
                       ('Measurement uncertainty range', number(report.statistic('minimum_auxiliary'))+' – '+number(report.statistic('maximum_auxiliary')))]
    elif report.statistic('median_auxiliary') is not None:
        statistics += [('Median auxiliary (not measurement uncertainty)', number(report.statistic('median_auxiliary'))),
                       ('Auxiliary range', number(report.statistic('minimum_auxiliary'))+' – '+number(report.statistic('maximum_auxiliary')))]
    statistics_widget = rows(body, statistics, 'Intensity and width statistics' if powder else 'Value and uncertainty statistics')
    if powder and report.fwhm_units == 'degrees_2theta':
        for key, value in statistics_widget.values.items():
            if 'FWHM' in key:
                value.setToolTip('Angular peak width along the 2θ axis, in degrees; not measurement uncertainty.')
    if report.warnings:
        disclose(body, 'Input diagnostic notes', report.warnings)
    body.addStretch(1)

    body = page('&Resolution')
    resolution = getattr(parent, 'hkl_resolution_summary', None)
    if resolution is not None:
        detail.hkl_resolution_values = rows(body, resolution, 'Resolution summary').values
    rows(body, [('HKL coverage', 'Fraction of symmetry-allowed reflection orbits represented in the input within the analyzed resolution range.'),
                ('d98', 'Highest-resolution boundary where cumulative HKL coverage reaches at least 98% within the analyzed domain.')])
    if powder:
        body.addWidget(explanation('HKL coverage does not establish that overlapping powder reflections were independently measured or experimentally resolved.', muted=True))
    significance = []
    direct = report.statistic('mean_f_over_sigma') is not None
    if direct:
        significance += [('Mean F/σ(F)', number(report.statistic('mean_f_over_sigma'))),
                         ('Median F/σ(F)', number(report.statistic('median_f_over_sigma')))]
    if report.available('significance'):
        significance += [('Mean '+report.significance_label, number(report.statistic('mean_significance'))),
                         ('Median '+report.significance_label, number(report.statistic('median_significance')))]
        for key, value in report.statistics:
            if key.startswith('weak_fraction_below_'):
                significance.append((f'Fraction with {"derived I/σ(I)" if direct else "I/σ(I)"} < {key.removeprefix("weak_fraction_below_")}', f'{100*value:.3f}%'))
    if significance:
        rows(body, significance, 'Measurement significance')
    methodology = [('Full HKL coverage definition', report.methods[0]), ('Full d98 definition', report.methods[1]),
                   ('Equivalent reciprocal-space range', '0 ≤ sinθ/λ ≤ 1 / (2 d_min); the established inclusive boundary tolerance applies.')]
    if direct:
        methodology += [('Amplitude convention', SIGNED_CONVENTION), ('Approximation', 'I ≈ F², σ(I) ≈ 2|F|σ(F). Unreliable near zero; not directly measured I/σ(I).')]
    disclose(body, 'Resolution methodology', methodology)
    body.addStretch(1)

    body = page('Peak &overlap')
    overlap = dict(report.overlap)
    body.addWidget(explanation('Estimated geometric overlap' if overlap.get('estimated') else 'Authoritative supplied groups' if overlap['available'] else 'Peak overlap unavailable'))
    if overlap['available']:
        metrics = _overlap_metrics(report)
        body.addWidget(metrics)
        distribution = ' · '.join(f'{size} HKL: {count:,} '+('group' if count == 1 else 'groups') for size,count in overlap['size_distribution']) or 'No overlapping groups'
        detail.hkl_group_distribution = explanation('Group-size distribution: '+distribution)
        body.addWidget(detail.hkl_group_distribution)
        body.addWidget(explanation(_overlap_metadata(report)))
        disclose(body, 'Group details', [
            ('Indexed reflections', f'{report.count("parsed_records")-report.count("zero_000"):,}'),
            ('Total groups', str(overlap['geometric_group_count'])),
            ('Non-overlapping groups', str(overlap.get('non_overlapping_groups', 0))),
            ('Group-size distribution', 'Group size → Number of groups' if overlap['size_distribution'] else 'No overlapping groups')]
            + [(f'{size} reflections', f'{count:,} '+('group' if count == 1 else 'groups')) for size,count in overlap['size_distribution']])
    else:
        body.addWidget(explanation(overlap['reason']))
    disclose(body, 'Overlap methodology', [('Method and metadata', overlap['reason']),
        ('Wavelength (Å)', number(overlap.get('wavelength'))), ('Wavelength source', overlap.get('wavelength_source') or 'Not supplied'),
        ('FWHM units', report.fwhm_units.replace('degrees_2theta','degrees 2θ')),
        ('Separation factor', number(overlap.get('separation_factor'))),
        ('Denominators', 'Fractions and group sizes count original non-000 input records, not symmetry orbits or independently measured powder peaks. Intensity fraction uses finite nonnegative physical input intensity.')])
    body.addWidget(explanation('Geometric grouping does not establish experimentally independent observations. No intensity repartitioning is performed.', muted=True))
    body.addStretch(1)

    body = page('&Availability && limitations')
    capabilities = _CapabilityTable(len(report.capabilities), 3)
    capabilities.setObjectName('hklCapabilityTable')
    capabilities.setHorizontalHeaderLabels(['Analysis', 'Status', 'Reason'])
    capabilities.setEditTriggers(QAbstractItemView.NoEditTriggers)
    capabilities.setSelectionBehavior(QAbstractItemView.SelectRows)
    capabilities.setSelectionMode(QAbstractItemView.SingleSelection)
    capabilities.setWordWrap(True)
    capabilities.verticalHeader().hide()
    capabilities.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
    capabilities.setStyleSheet('QTableWidget { selection-background-color:#e8f0fa; selection-color:#153c70; } QTableWidget::item:selected { background:#e8f0fa; color:#153c70; } QTableWidget::item:focus { border:1px solid #447fc1; }')
    capabilities.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    capabilities.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    names = {'column_semantics':'Column semantics', 'overlap':'Peak overlap', 'significance':'Significance',
             'merging_statistics':'Merging statistics', 'profile_statistics':'Profile statistics',
             'anomalous_completeness':'Anomalous completeness', 'wilson':'Wilson analysis'}
    reasons = {'column_semantics': 'Declared or explicitly selected input format' if report.available('column_semantics') else 'Column layout not verified',
               'overlap': ('Estimated geometry; wavelength and FWHM verified' if overlap.get('estimated')
                           else 'Explicit supplied groups' if overlap['available']
                           else 'Measured wavelength required' if 'Wavelength missing' in overlap['reason']
                           else 'Compatible widths and overlap metadata required'),
               'significance': 'Positive finite measurement uncertainties' if report.available('significance') else 'No verified genuine measurement uncertainties',
               'merging_statistics':'No verified unmerged, consistently scaled observations',
               'profile_statistics':'Profiles, weights and refinement information required',
               'anomalous_completeness':'Friedel policy and observation provenance insufficient',
               'wilson':'Scaled intensities, composition and model assumptions required'}
    for row, cap in enumerate(report.capabilities):
        limited = cap.available and ((cap.name == 'overlap' and overlap.get('estimated')) or
                  (cap.name == 'significance' and any(counts.get(key) for key in ('missing_auxiliary','invalid_auxiliary','invalid_values'))))
        status = 'Limited' if limited else 'Available' if cap.available else 'Unavailable'
        for col, text in enumerate((names.get(cap.name,cap.name.replace('_',' ').capitalize()), status, reasons.get(cap.name,cap.reason))):
            item = QTableWidgetItem(text)
            item.setToolTip(scientific_tooltip(cap.reason))
            capabilities.setItem(row, col, item)
    capabilities.verticalHeader().setDefaultSectionSize(30)
    capabilities.setFixedHeight(len(report.capabilities)*30 + capabilities.horizontalHeader().sizeHint().height() + 4)
    body.addWidget(capabilities)
    reason = explanation('')
    reason.setMinimumHeight(48)
    reason.setAccessibleName('Selected analysis scientific explanation')
    body.addWidget(reason)
    def selected_reason(row, _column, *_previous):
        if row >= 0:
            cap = report.capabilities[row]
            reason.setText(scientific_text(names.get(cap.name, cap.name)+': '+cap.reason))
    capabilities.currentCellChanged.connect(selected_reason)
    capabilities.setCurrentCell(0, 0)
    detail.hkl_capability_table = capabilities
    detail.hkl_capability_reason = reason
    disclose(body, 'Methodology and data provenance', [('Phase provenance', report.phase_status)]+
             [('Method', text) for text in report.methods[2:]])
    body.addStretch(1)
    close = QPushButton('&Close')
    close.clicked.connect(detail.close)
    root.addWidget(close, 0, Qt.AlignRight)
    detail.hkl_close_button = close
    detail.hkl_details_tabs = tabs
    a.fit_dialog_to_available_screen(detail, QSize(1050, 530))
    saved = detail.hkl_settings.value('hklAdvanced/geometry')
    if saved:
        detail.restoreGeometry(saved)
        saved_size = detail.hkl_settings.value('hklAdvanced/size')
        if isinstance(saved_size, QSize) and saved_size.isValid():
            detail.resize(saved_size)
        clamp_window_to_available_screen(detail)
    try:
        tabs.setCurrentIndex(max(0, min(tabs.count()-1, int(detail.hkl_settings.value('hklAdvanced/tab', 0)))))
    except (TypeError, ValueError):
        pass
    for label in detail.findChildren(QLabel):
        if label.toolTip():
            label.setToolTip(scientific_tooltip(label.toolTip(), literal=bool(label.property('literalPath'))))
    return detail



def _footer(win, layout, dialog, report, analysis=None, figure=None):
    from .app import QFileDialog
    footer = QHBoxLayout()
    copy = QPushButton('Copy summary')
    def copy_summary():
        from PySide6.QtCore import QMimeData
        mime = QMimeData()
        mime.setText(dialog.summary_text)
        mime.setHtml(scientific_text(dialog.summary_text))
        QApplication.clipboard().setMimeData(mime)
    copy.clicked.connect(copy_summary)
    footer.addWidget(copy)
    def save_json():
        path,_ = QFileDialog.getSaveFileName(dialog,'Export diagnostics','hkl_diagnostics.json','JSON (*.json)')
        if path: report.export_json(path,analysis)
    structured = QPushButton('Export diagnostics')
    structured.clicked.connect(save_json)
    footer.addWidget(structured)
    if analysis is not None:
        def save_csv():
            path,_ = QFileDialog.getSaveFileName(dialog,'Export resolution bins','hkl_completeness.csv','CSV (*.csv)')
            if path: export_shell_csv(path,report)
        csv_button = QPushButton('Export CSV')
        csv_button.clicked.connect(save_csv)
        footer.addWidget(csv_button)
        def save_plot():
            path,_ = QFileDialog.getSaveFileName(dialog,'Export completeness plot','hkl_completeness.png','PNG (*.png);;PDF (*.pdf);;SVG (*.svg)')
            active = dialog.hkl_plot_figures.get(dialog.hkl_plot_tabs.currentIndex(),figure) if hasattr(dialog,'hkl_plot_figures') else figure
            if path: active.savefig(path,dpi=200,bbox_inches='tight')
        plot_button = QPushButton('Export plot')
        plot_button.clicked.connect(save_plot)
        footer.addWidget(plot_button)
    footer.addStretch(1)
    close = QPushButton('Close')
    close.clicked.connect(dialog.accept)
    footer.addWidget(close)
    layout.addLayout(footer)
    dialog.full_source_path = str(analysis.hkl_path) if analysis is not None else report.source


def validation_dialog(win, result):
    from . import app as a
    report = presentation_report(result)
    dialog = QDialog(win)
    dialog.setObjectName('hklValidationDialog')
    dialog.setWindowTitle('HKL Validation')
    layout = _top(win,dialog,result,report)
    significant_absences = (f'; significance ≥3: {number(report.count("absent_significant_3sigma"))}'
                            if report.available('significance') else '')
    detail_text = (f'Systematically absent: {report.count("systematic_absent_entries")} '
        f'(nonzero: {report.count("absent_nonzero_values")}{significant_absences}) · '
        f'Exact duplicate entries: {report.count("exact_duplicate_entries")} · '
        f'Conflicting groups: {report.count("conflicting_duplicate_groups")} · '
        f'Invalid values: {report.count("invalid_values")} · Rejected records: {report.count("rejected_records")}')
    summary = QLabel(f'Systematically absent: {report.count("systematic_absent_entries")} · Exact duplicate entries: {report.count("exact_duplicate_entries")} · Conflicting groups: {report.count("conflicting_duplicate_groups")}')
    summary.setToolTip(detail_text+' · Counts are input diagnostics, not a declaration of scientific validity.')
    summary.setWordWrap(True)
    layout.addWidget(summary)
    _details(layout,dialog,report,result)
    search = QLineEdit()
    search.setPlaceholderText('Find reflection (h k l), e.g. 0 2 0')
    search.setClearButtonEnabled(True)
    search.setAccessibleName('Find reflection in all parsed records')
    search.setToolTip('Enter one, two or three signed integer indices. Prefix searches are supported; at most 200 matches are displayed.')
    search.setStyleSheet('QLineEdit { background:white; border:1px solid #8fa9cc; padding:7px 10px; } QLineEdit:focus { border:2px solid #2264b8; padding:6px 9px; }')
    layout.addWidget(search)
    phase = a.reflection_mode_has_phase(result.data_mode)
    sig = report.available('significance')
    amplitude = a.reflection_mode_is_amplitude(result.data_mode)
    verified = report.available('column_semantics')
    headers = ['h','k','l',a.reflection_value_label(result.data_mode) if verified else 'Input value (unverified)',
               a.reflection_sigma_label(result.data_mode) if verified else 'Auxiliary (unverified)']
    if result.data_mode == a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA:
        headers[-1] = 'Auxiliary (dummy σ)'
    if phase: headers.append('Phase (°)')
    if sig: headers += (['F/σ(F)'] if amplitude else [report.significance_label])
    headers += ['d (Å)','sinθ/λ (Å⁻¹)']
    derived = QCheckBox('Show derived intensity approximation')
    derived.setToolTip('Secondary approximation: I ≈ F² and σ(I) ≈ 2|F|σ(F), unreliable near zero; not directly measured I/σ(I).')
    derived.setVisible(sig and amplitude)
    layout.addWidget(derived)
    table = QTableWidget(0,len(headers))
    win._configure_diagnostic_table(table)
    table.setSelectionMode(QAbstractItemView.ExtendedSelection)
    install_scientific_headers(table)
    table.setHorizontalHeaderLabels(headers)
    for column in range(len(headers)):
        table.horizontalHeader().setSectionResizeMode(column,QHeaderView.Fixed if column<3 else QHeaderView.Stretch)
        if column<3: table.setColumnWidth(column,48)
    table.horizontalHeader().setStretchLastSection(False)
    table.horizontalHeader().setSortIndicator(-1,Qt.AscendingOrder)
    label = QLabel()
    label.setWordWrap(True)
    layout.addWidget(label)
    def populate():
        text = search.text().split()
        rows = result.reflections
        if text:
            try:
                keys = tuple(int(x) for x in text)
                rows = [r for r in rows if len(keys)<=3 and (r.h,r.k,r.l)[:len(keys)] == keys]
            except ValueError:
                rows = []
        shown = rows[:200]
        table.setSortingEnabled(False)
        current_headers = headers + ([DERIVED_LABEL] if derived.isChecked() and sig and amplitude else [])
        table.setColumnCount(len(current_headers))
        table.setHorizontalHeaderLabels(current_headers)
        for column in range(len(current_headers)):
            table.horizontalHeader().setSectionResizeMode(column,QHeaderView.Fixed if column<3 else QHeaderView.Stretch)
            if column<3: table.setColumnWidth(column,48)
        table.setRowCount(len(shown))
        for row,r in enumerate(shown):
            values = [r.h,r.k,r.l,r.value,r.sigma]
            if phase: values.append(r.phase)
            if sig:
                values.append(a.reflection_amplitude_signal_to_noise(r) if amplitude else a.reflection_primary_signal_to_noise(r,result.data_mode))
            values.append(a.reflection_d_spacing(result.cell,r.h,r.k,r.l) if (r.h,r.k,r.l)!=(0,0,0) else None)
            values.append(a.reflection_sintheta_over_lambda(result.cell,r.h,r.k,r.l) if (r.h,r.k,r.l)!=(0,0,0) else None)
            if derived.isChecked() and sig and amplitude:
                values.append(a.reflection_primary_signal_to_noise(r,result.data_mode))
            for col,value in enumerate(values):
                text_value = str(int(value)) if col<3 else _display_number(value)
                if value is not None and not math.isfinite(float(value)):
                    text_value = str(value)+' (invalid)'
                item = _NumericItem(text_value,value)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item.setToolTip(repr(value))
                table.setItem(row,col,item)
        table.setSortingEnabled(True)
        label.setText(f'Showing first {len(shown):,} of {len(rows):,} '+('matching records' if text else 'records')+
                      (f' ({len(result.reflections):,} total)' if text else '')+' · Search covers all parsed records')
    timer = QTimer(dialog)
    timer.setSingleShot(True)
    timer.setInterval(180)
    timer.timeout.connect(populate)
    search.textChanged.connect(lambda: timer.start())
    derived.toggled.connect(lambda _checked: populate())
    populate()
    layout.addWidget(table,1)
    copy_rows = QPushButton('Copy selected rows')
    copy_rows.setEnabled(False)
    def selected_text():
        selected = sorted({index.row() for index in table.selectionModel().selectedRows()})
        if not selected:
            return ''
        lines = ['\t'.join(table.horizontalHeaderItem(c).text() for c in range(table.columnCount()))]
        for row in selected:
            lines.append('\t'.join('' if table.item(row,c).numeric_value is None else str(table.item(row,c).numeric_value) for c in range(table.columnCount())))
        return '\n'.join(lines)
    def copy_selected():
        text = selected_text()
        if text: QApplication.clipboard().setText(text)
    copy_rows.clicked.connect(copy_selected)
    table.itemSelectionChanged.connect(lambda:copy_rows.setEnabled(bool(table.selectionModel().selectedRows())))
    shortcut = QShortcut(QKeySequence.Copy,table)
    shortcut.setContext(Qt.WidgetWithChildrenShortcut)
    shortcut.activated.connect(copy_selected)
    # Keep secondary actions alongside the summary, outside the scrolling table.
    layout.removeWidget(dialog.hkl_advanced_button)
    actions = QHBoxLayout()
    actions.addWidget(copy_rows)
    actions.addStretch(1)
    actions.addWidget(dialog.hkl_advanced_button)
    layout.insertLayout(2,actions)
    dialog.hkl_copy_selected_button = copy_rows
    dialog.hkl_copy_selected = copy_selected
    dialog.summary_text = 'HKL VALIDATION\n'+report.summary()
    _footer(win,layout,dialog,report)
    dialog.hkl_table = table
    dialog.hkl_search = search
    dialog.hkl_preview_label = label
    dialog.hkl_derived_checkbox = derived
    dialog.diagnostics = report
    a.fit_dialog_to_available_screen(dialog,QSize(1060,760))
    for label in dialog.findChildren(QLabel):
        if label.textFormat() != Qt.RichText and '</' not in label.text():
            label.setText(scientific_text(label.text()))
            label.setTextFormat(Qt.RichText)
        if label.toolTip():
            label.setToolTip(scientific_tooltip(label.toolTip()))
    for control in dialog.findChildren(QWidget):
        if control.toolTip() and not control.toolTip().startswith('<qt>'):
            control.setToolTip(scientific_tooltip(control.toolTip()))
    return dialog


def _display_number(value, digits=4):
    if value is None or not math.isfinite(float(value)):
        return 'n/a'
    if value and (abs(value)>=1e7 or abs(value)<1e-4):
        return f'{value:.4e}'
    return f'{value:.{digits}f}'


class _NumericItem(QTableWidgetItem):
    def __init__(self,text,value):
        super().__init__(text)
        self.numeric_value = value

    def __lt__(self,other):
        def key(item):
            value = item.numeric_value
            return float(value) if value is not None and math.isfinite(float(value)) else math.inf
        return key(self)<key(other)


def overlap_bin_rows(analysis, report):
    """Read-only record statistics on the existing (lo, hi] shell boundaries.

    Group counts deliberately omitted: groups may span shells. Every record
    contributes once in its own interval; original global membership is reused.
    """
    from . import app as a
    raw = analysis.reflections_raw
    hkls = np.asarray([(r.h,r.k,r.l) for r in raw], dtype=np.int32)
    stl = a.hkl_stl_array_from_metric(a.reciprocal_metric_tensor(analysis.cell), hkls)
    values = np.asarray([r.value for r in raw], dtype=float)
    membership = dict(dict(report.overlap).get('groups', ()))
    affected = np.asarray([membership.get(tuple(hkl), 0)>0 for hkl in hkls])
    result = []
    for shell in report.shells:
        row = dict(shell)
        mask = (stl>row['lo']) & (stl<=row['hi']) & np.any(hkls!=0, axis=1)
        count = int(np.count_nonzero(mask))
        hit = int(np.count_nonzero(mask & affected))
        valid = values[mask]
        physical = len(valid)>0 and np.all(np.isfinite(valid)) and np.all(valid>=0)
        denominator = float(np.sum(valid)) if physical else 0
        result.append(dict(lo=row['lo'], hi=row['hi'], input=count, affected=hit,
            percent=100*hit/count if count else None,
            intensity_percent=100*float(np.sum(values[mask & affected]))/denominator if denominator>0 else None))
    return result


def _resolution_summary(analysis):
    from . import app as a
    rows = analysis.bins
    denominator = sum(row['theory'] for row in rows)
    numerator = sum(row['observed'] for row in rows)
    minimum = a.format_resolution_d(analysis.d_min).replace(' A',' Å')
    return [('d_min', minimum),
        ('d98', a.format_resolution_d(analysis.d_full_98).replace(' A',' Å') if analysis.d_full_98 is not None else 'N/A — '+D98_NOT_REACHED),
        ('HKL coverage', number(100*numerator/denominator)+'%' if denominator else 'N/A — no theoretical reflections'),
        ('Analyzed resolution range', 'd ≥ '+minimum)]


def _overlap_metadata(report):
    overlap = dict(report.overlap)
    return (f'Wavelength λ = {number(overlap.get("wavelength"))} Å · FWHM: degrees 2θ · '
            f'Neighbor separation ≤ {number(overlap.get("separation_factor"))} × mean FWHM · '
            'Transitive grouping · Superflip FWHM2Groups convention'
            if overlap.get('estimated') else overlap['reason'])


def _overlap_metrics(report):
    overlap = dict(report.overlap)
    physical = report.count('parsed_records')-report.count('zero_000')
    fraction, intensity = overlap.get('fraction'), overlap.get('integrated_intensity_fraction')
    widget = QWidget()
    layout = QGridLayout(widget)
    layout.setContentsMargins(4,4,4,4)
    metrics = [('Overlapping groups', f'{overlap["group_count"]:,}'),
        ('Affected reflections', f'{overlap["affected"]:,} / {physical:,} ({100*fraction:.2f}%)' if fraction is not None else 'N/A'),
        ('Input intensity in overlapping groups', f'{100*intensity:.3f}%' if intensity is not None else 'N/A'),
        ('Largest group', f'{overlap["largest"]} reflections')]
    for column,(title,value) in enumerate(metrics):
        heading, metric = QLabel(title), QLabel(value)
        heading.setWordWrap(True)
        metric.setWordWrap(True)
        metric.setStyleSheet('font-size:13pt; font-weight:600; color:#001170;')
        layout.addWidget(heading,0,column)
        layout.addWidget(metric,1,column)
        layout.setColumnStretch(column,1)
    return widget


class _CompletenessDialog(QDialog):
    """Persist only presentation geometry; always clamp restored native frames."""
    def __init__(self,parent):
        super().__init__(parent)
        self.hkl_settings = QSettings(QSettings.defaultFormat(),QSettings.UserScope,'PhaseStudio','PhaseStudio')
        self.finished.connect(self._save_presentation)

    def restore_presentation(self):
        from .ui_branding import clamp_window_to_available_screen
        settings = self.hkl_settings
        rect = settings.value('hklCompleteness/windowRect')
        if isinstance(rect,QRect) and rect.width()>=640 and rect.height()>=400:
            self.setGeometry(rect)
            clamp_window_to_available_screen(self)
        self.layout().activate()
        sizes = settings.value('hklCompleteness/splitter')
        try:
            sizes = [int(x) for x in sizes]
            if len(sizes)==2 and min(sizes)>0: self.hkl_content_splitter.setSizes(sizes)
        except (TypeError,ValueError): pass

    def _save_presentation(self,_result):
        settings = self.hkl_settings
        settings.setValue('hklCompleteness/windowRect',self.normalGeometry() if self.isMaximized() else self.geometry())
        settings.setValue('hklCompleteness/splitter',self.hkl_content_splitter.sizes())


def completeness_dialog(win, analysis):
    from . import app as a
    report = presentation_report(analysis)
    powder = report.data_type.startswith('Powder')
    direct = report.statistic('mean_f_over_sigma') is not None
    significance_key = 'mean_f_over_sigma' if direct else 'mean_significance'
    significance_label = DIRECT_LABEL if direct else report.significance_label
    dialog = _CompletenessDialog(win)
    dialog.setWindowFlag(Qt.WindowMaximizeButtonHint,True)
    dialog.setObjectName('hklCompletenessDialog')
    dialog.setWindowTitle('HKL Completeness')
    layout = _top(win,dialog,analysis,report,True)
    value = a.reflection_value_label(analysis.data_mode) if report.available('column_semantics') else 'Input value'
    units = report.fwhm_units.replace('degrees_2theta','degrees 2θ')
    d_min_text = a.format_resolution_d(analysis.d_min).replace(' A',' Å')
    d98_text = a.format_resolution_d(analysis.d_full_98).replace(' A',' Å') if analysis.d_full_98 is not None else 'Not reached'
    cards = [(d_min_text,'d_min'),(d98_text,'d98 · cumulative ≥98%'),
             (number(report.statistic('median_value')),f'Median {value}'),(number(report.statistic('mean_value')),f'Mean {value}')]
    if report.available('significance'):
        cards.append((number(report.statistic('median_f_over_sigma' if direct else 'median_significance')),'Median '+significance_label))
    metrics = win._diagnostic_metric_grid(cards,compact=True,row_columns=(len(cards),))
    for label in metrics.findChildren(QLabel):
        if label.text()==d98_text:
            label.setToolTip(D98_NOT_REACHED if analysis.d_full_98 is None else report.methods[1])
    layout.addWidget(metrics)
    rows = [dict(row) for row in report.shells]
    centers = [row['center'] for row in rows]
    populated_coverage = [row['coverage'] for row in rows if row['coverage'] is not None]
    complete = bool(populated_coverage) and all(math.isclose(c,100,abs_tol=1e-9) for c in populated_coverage)
    compact = []
    if complete:
        compact.append('Symmetry-allowed HKL coverage: 100% across the analyzed resolution domain')
    if powder and report.statistic('constant_fwhm'):
        compact.append(f'FWHM constant: {number(report.statistic("median_auxiliary"))} ({units}), '
                       f'{report.count("valid_widths_or_sigmas"):,}/{report.count("parsed_records"):,} reflections')
    elif powder and not report.count('valid_widths_or_sigmas'):
        compact.append('FWHM unavailable: no positive finite widths')
    if compact:
        compact_label = QLabel(' · '.join(compact))
        compact_label.setWordWrap(True)
        compact_label.setToolTip('HKL coverage does not establish independently measured or resolved powder reflections. Full definitions are in Advanced diagnostics.')
        layout.addWidget(compact_label)
        dialog.hkl_compact_summary = compact_label
    _details(layout,dialog,report)
    layout.removeWidget(dialog.hkl_advanced_button)
    splitter = QSplitter(Qt.Vertical)
    splitter.setChildrenCollapsible(False)
    tabs = QTabWidget()
    tabs.setObjectName('hklPlotTabs')
    main = QWidget()
    main_layout = QVBoxLayout(main)
    main_layout.setContentsMargins(0,0,0,0)
    toolbar = QHBoxLayout()
    raw = analysis.reflections_raw
    values = np.asarray([r.value for r in raw if (r.h,r.k,r.l)!=(0,0,0) and math.isfinite(r.value)])
    distribution_summary = QLabel(f'{value} distribution · zero: {np.count_nonzero(values==0):,} · negative: {np.count_nonzero(values<0):,} · full finite range retained')
    distribution_summary.setWordWrap(True)
    toolbar.addWidget(distribution_summary,1)
    scale = QComboBox()
    scale.addItems(['Log counts','Linear counts'])
    scale.setCurrentIndex(0 if a.reflection_mode_is_amplitude(analysis.data_mode) else 1)
    scale.setToolTip('Only the count axis changes. The amplitude/intensity axis includes zero, negative values and the entire high-value tail. Zero-count bins are masked on a log count axis.')
    toolbar.addWidget(scale)
    focus = QComboBox()
    focus.addItems(['Full range','Focus on main distribution'])
    focus.setToolTip('View only: focus shows the 1st–99th percentile x-range. Values outside it remain in the histogram bins, statistics and exports. No records are removed and no rebinning occurs.')
    toolbar.addWidget(focus)
    tabs.setCornerWidget(dialog.hkl_advanced_button,Qt.TopRightCorner)
    main_layout.addLayout(toolbar)
    figure = Figure(figsize=(10,4),dpi=100,layout='constrained')
    canvas = FigureCanvasQTAgg(figure)
    canvas.setObjectName('hklCompletenessCanvas')
    canvas.setMinimumHeight(190)
    panels = []
    if not complete and populated_coverage:
        panels.append('coverage')
    if any(row['mean_value'] is not None for row in rows):
        panels.append('intensity')
    if powder and not report.statistic('constant_fwhm') and report.count('valid_widths_or_sigmas'):
        panels.append('width')
    elif not powder and report.available('significance'):
        panels.append('significance')
    if len(values):
        panels.append('distribution')
    # The viewport may shrink below the legible canvas height. This also
    # protects two-panel plots on a 1080p monitor at 150% DPI: a canvas clipped
    # directly by a QTabWidget has no way to expose its bottom axis labels.
    if len(panels)>=3:
        canvas.setMinimumHeight(280)
    chart_scroll = QScrollArea()
    chart_scroll.setFrameShape(QScrollArea.NoFrame)
    chart_scroll.setWidgetResizable(True)
    chart_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    chart_scroll.setMinimumHeight(90)
    chart_scroll.setWidget(canvas)
    main_layout.addWidget(chart_scroll,1)
    dialog.hkl_chart_scroll = chart_scroll
    axes = {}
    if len(panels)<=2:
        grid = figure.add_gridspec(1,max(1,len(panels)))
        positions = [grid[0,i] for i in range(len(panels))]
    else:
        grid = figure.add_gridspec(2,2)
        positions = [grid[0,0],grid[0,1],grid[1,:]] if len(panels)==3 else [grid[0,0],grid[0,1],grid[1,0],grid[1,1]]
    for panel,position in zip(panels,positions):
        axis = figure.add_subplot(position)
        axes[panel] = axis
        if panel=='coverage':
            axis.plot(centers,[row['coverage'] if row['coverage'] is not None else np.nan for row in rows],'o-',color='#2264b8',markersize=3)
            axis.set_title('Symmetry-allowed HKL coverage',fontsize=9)
            axis.set_ylabel('Coverage (%)',fontsize=8)
            axis.set_ylim(0,105)
            axis.text(.02,.03,f'd_min: {d_min_text}\nd98: {d98_text}',transform=axis.transAxes,fontsize=7,va='bottom',bbox=dict(facecolor='white',edgecolor='none',alpha=.9))
        elif panel=='intensity':
            axis.plot(centers,[row['mean_value'] for row in rows],'o-',color='#001170',markersize=3)
            axis.set_title(f'Mean {value} vs resolution',fontsize=9)
            axis.set_ylabel(value,fontsize=8)
        elif panel=='width':
            axis.plot(centers,[row['mean_fwhm'] for row in rows],'o-',color='#2264b8',markersize=3)
            axis.set_title('FWHM vs resolution',fontsize=9)
            axis.set_ylabel('Mean FWHM ('+units+')',fontsize=8)
        elif panel=='significance':
            axis.plot(centers,[row[significance_key] for row in rows],'o-',color='#2264b8',markersize=3)
            axis.set_title('Mean '+significance_label+' vs resolution',fontsize=9)
            axis.set_ylabel('Mean '+significance_label,fontsize=8)
        else:
            # Freedman–Diaconis width with a display-size cap, chosen before
            # allocating edges so a remote outlier cannot create millions of bins.
            q25,q75 = np.percentile(values,[25,75])
            width = 2*(q75-q25)/np.cbrt(len(values))
            bin_count = min(160,max(1,math.ceil((float(values.max())-float(values.min()))/width))) if width>0 else min(160,max(1,int(np.sqrt(len(values)))))
            edges = np.histogram_bin_edges(values,bins=bin_count)
            axis.hist(values,bins=edges,color='#2264b8',alpha=.75)
            axis.set_title(value+' distribution · full range',fontsize=9)
            axis.set_xlabel(value,fontsize=8)
            axis.set_ylabel('Records',fontsize=8)
        if panel!='distribution':
            axis.set_xlabel('sinθ/λ (Å⁻¹)',fontsize=8)
        axis.tick_params(labelsize=8)
        axis.grid(axis='y',alpha=.15)
    if not panels:
        empty = QLabel('No finite physical statistics are available. See Advanced diagnostics for input warnings.')
        empty.setWordWrap(True)
        main_layout.removeWidget(chart_scroll)
        chart_scroll.hide()
        main_layout.addWidget(empty)
    def count_scale():
        if 'distribution' in axes:
            axes['distribution'].set_yscale('log' if scale.currentIndex()==0 else 'linear')
            axes['distribution'].relim()
            axes['distribution'].autoscale_view()
            canvas.draw_idle()
    scale.currentIndexChanged.connect(lambda _index:count_scale())
    count_scale()
    if 'distribution' in axes:
        histogram = axes['distribution']
        full_xlim = histogram.get_xlim()
        full_title = histogram.get_title()
        focused_xlim = tuple(np.quantile(values,[.01,.99]))
        def focus_range(index):
            limits = focused_xlim if index and focused_xlim[0]<focused_xlim[1] else full_xlim
            histogram.set_xlim(limits)
            histogram.set_title(scientific_text(value+' distribution · focused view (tails retained)','plot') if index and limits==focused_xlim else full_title)
            canvas.draw_idle()
        focus.currentIndexChanged.connect(focus_range)
    else:
        focus.setEnabled(False)
    tabs.addTab(main,'Analysis')
    figures = {0:figure}
    overlap = dict(report.overlap)
    if overlap['available']:
        overlap_page = QWidget()
        overlap_layout = QVBoxLayout(overlap_page)
        overlap_layout.setContentsMargins(0,0,0,0)
        summary = _overlap_metrics(report)
        overlap_layout.addWidget(summary)
        criterion = QLabel(scientific_text(_overlap_metadata(report)))
        criterion.setWordWrap(True)
        overlap_layout.addWidget(criterion)
        overlap_figure = Figure(figsize=(9,3),dpi=100,layout='constrained')
        overlap_canvas = FigureCanvasQTAgg(overlap_figure)
        overlap_canvas.setMinimumHeight(240)
        size_axis,fraction_axis = overlap_figure.subplots(1,2)
        sizes = overlap['size_distribution']
        if sizes:
            bars = size_axis.bar([str(x[0])+' HKL' for x in sizes],[x[1] for x in sizes],color='#2264b8')
            size_axis.bar_label(bars, padding=3, fontsize=8)
            size_axis.margins(y=.18)
            size_axis.set_xlabel('HKL per overlap group',fontsize=8)
            size_axis.set_ylabel('Groups',fontsize=8)
            from matplotlib.ticker import MaxNLocator
            size_axis.yaxis.set_major_locator(MaxNLocator(integer=True))
            size_axis.set_title('Overlapping group sizes',fontsize=9)
        else:
            size_axis.text(.5,.5,'No overlapping groups under the stated criterion',transform=size_axis.transAxes,ha='center',va='center',fontsize=8)
            size_axis.set_axis_off()
        fraction_axis.plot(centers,[100*row['overlap_fraction'] if row['overlap_fraction'] is not None else np.nan for row in rows],'o-',color='#2264b8')
        fraction_axis.set_xlabel('sinθ/λ (Å⁻¹)',fontsize=8)
        fraction_axis.set_ylabel('Reflections in overlapping groups (%)',fontsize=8)
        fraction_axis.set_title('Reflections in overlapping groups (%)',fontsize=9)
        fraction_axis.set_ylim(0,105)
        for axis in (size_axis,fraction_axis):axis.tick_params(labelsize=8)
        overlap_scroll = QScrollArea()
        overlap_scroll.setFrameShape(QScrollArea.NoFrame)
        overlap_scroll.setWidgetResizable(True)
        overlap_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        overlap_scroll.setMinimumHeight(90)
        overlap_scroll.setWidget(overlap_canvas)
        overlap_layout.addWidget(overlap_scroll,1)
        dialog.hkl_overlap_canvas = overlap_canvas
        dialog.hkl_overlap_scroll = overlap_scroll
        index = tabs.addTab(overlap_page,'Peak overlap')
        figures[index] = overlap_figure
        dialog.hkl_overlap_figure = overlap_figure
        dialog.hkl_overlap_summary = summary
    if direct:
        derived_page = QWidget()
        derived_layout = QVBoxLayout(derived_page)
        derived_layout.setContentsMargins(0,0,0,0)
        explanation = QLabel('Secondary approximation: I ≈ F²; σ(I) ≈ 2|F|σ(F). Unreliable near zero amplitudes; not equivalent to directly measured I/σ(I).')
        explanation.setWordWrap(True)
        derived_layout.addWidget(explanation)
        derived_figure = Figure(figsize=(9,3),dpi=100,layout='constrained')
        derived_canvas = FigureCanvasQTAgg(derived_figure)
        derived_canvas.setMinimumHeight(190)
        derived_axis = derived_figure.subplots()
        derived_axis.plot(centers,[row['mean_significance'] for row in rows],'o-',color='#2264b8',markersize=3)
        derived_axis.set_title(DERIVED_LABEL,fontsize=9)
        derived_axis.set_xlabel('sinθ/λ (Å⁻¹)',fontsize=8)
        derived_axis.set_ylabel('Mean derived significance',fontsize=8)
        derived_axis.tick_params(labelsize=8)
        derived_layout.addWidget(derived_canvas,1)
        index = tabs.addTab(derived_page,'Derived intensity significance')
        figures[index] = derived_figure
        dialog.hkl_derived_figure = derived_figure
    for plot in figures.values():
        for axis in plot.axes:
            axis.set_xlabel(scientific_text(axis.get_xlabel(), 'plot'))
            axis.set_ylabel(scientific_text(axis.get_ylabel(), 'plot'))
            axis.set_title(scientific_text(axis.get_title(), 'plot'))
            for annotation in axis.texts:
                annotation.set_text(scientific_text(annotation.get_text(), 'plot'))
    splitter.addWidget(tabs)
    bins_panel = QWidget()
    bins_layout = QVBoxLayout(bins_panel)
    bins_layout.setContentsMargins(0,0,0,0)
    bins_title = QLabel('RESOLUTION BINS · undefined coverage = n/a')
    bins_layout.addWidget(bins_title)
    columns = [('lo','Low'),('hi','High'),('observed','Input HKL'),('theory','Allowed HKL'),('coverage','Coverage (%)'),
               ('mean_value',f'Mean {value}'),('median_value',f'Median {value}')]
    if powder and report.count('valid_widths_or_sigmas'):
        columns.append(('mean_fwhm','Mean FWHM'))
    elif report.available('significance'):
        columns += [(significance_key,'Mean '+significance_label)]
    table = QTableWidget(len(rows),len(columns))
    win._configure_diagnostic_table(table)
    table.verticalHeader().setDefaultSectionSize(24)
    install_scientific_headers(table)
    table.setHorizontalHeaderLabels([label for _,label in columns])
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    for j,(key,label) in enumerate(columns):
        table.horizontalHeaderItem(j).setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        table.horizontalHeaderItem(j).setToolTip(scientific_tooltip('FWHM units: '+units if key=='mean_fwhm' else SIGNED_CONVENTION if key=='mean_f_over_sigma' else report.methods[0] if key in {'observed','theory','coverage'} else label+'; full precision is retained in CSV and JSON exports.'))
    for i,row in enumerate(rows):
        for j,(key,_) in enumerate(columns):
            val = row[key]
            text = str(int(val)) if key in {'observed','theory'} else _display_number(val,5 if key in {'lo','hi','mean_fwhm'} else 3)
            item = _NumericItem(text,val)
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            item.setToolTip(repr(val))
            table.setItem(i,j,item)
    analysis_columns = list(columns)
    overlap_rows = overlap_bin_rows(analysis, report) if overlap['available'] else []
    overlap_columns = [('lo','Low'), ('hi','High'), ('input','Input HKL'),
                       ('affected','Affected HKL'), ('percent','Overlap (%)'),
                       ('intensity_percent','Affected intensity in bin (%)')]
    def contextual_bins(index):
        is_overlap = tabs.tabText(index) == 'Peak overlap'
        selected_columns = overlap_columns if is_overlap else analysis_columns
        selected_rows = overlap_rows if is_overlap else rows
        table.setSortingEnabled(False)
        table.clearContents()
        table.setColumnCount(len(selected_columns))
        table.setRowCount(len(selected_rows))
        table.setHorizontalHeaderLabels([label for _, label in selected_columns])
        for column,(key,title) in enumerate(selected_columns):
            tip = ('100 × sum of original input intensities of affected HKL records in this interval / sum of all original input intensities in this same interval. Requires all intensities in the interval finite and nonnegative and a positive denominator; otherwise N/A. This is not the fraction of the entire dataset intensity.' if key=='intensity_percent' else
                   'Input HKL records belonging to geometric overlap groups; not independently measured powder peaks.' if key in {'affected','percent'} else
                   'Theoretical symmetry-allowed index coverage; not independent experimental powder information.' if key=='coverage' else
                   'Interval (Low, High] in sinθ/λ (Å⁻¹); original shell boundaries are unchanged.' if key in {'lo','hi'} else
                   'FWHM in degrees 2θ, not measurement uncertainty.' if key=='mean_fwhm' and report.fwhm_units=='degrees_2theta' else
                   SIGNED_CONVENTION if key=='mean_f_over_sigma' else title+'; original precision is retained in CSV and JSON exports.')
            table.horizontalHeaderItem(column).setToolTip(scientific_tooltip(tip))
            table.horizontalHeaderItem(column).setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for i, record in enumerate(selected_rows):
            for j, (key, _) in enumerate(selected_columns):
                value = record[key]
                text = str(int(value)) if key in {'input','affected','observed','theory'} else _display_number(value, 5 if key in {'lo','hi','mean_fwhm'} else 3)
                if key == 'percent' and value is not None:
                    text = f'{value:.1f}' if record['input']<100 else f'{value:.2f}'
                if is_overlap and value is None:
                    text = 'N/A'
                item = _NumericItem(text, value)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item.setToolTip(repr(value))
                table.setItem(i,j,item)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        bins_title.setText(scientific_text('RESOLUTION BINS · sinθ/λ (Å⁻¹) · ' + ('overlap: original records; undefined denominator = N/A' if is_overlap else 'undefined coverage = n/a')))
        bins_title.setToolTip('Intervals are (lower, upper], identical to the plot. Cross-bin groups contribute each record in its own interval. Group counts are omitted: no new group-to-bin convention. Intensity fraction uses finite nonnegative input intensity within the interval.')
        dialog.hkl_bin_columns = selected_columns
    tabs.currentChanged.connect(contextual_bins)
    contextual_bins(0)
    dialog.hkl_overlap_bin_rows = overlap_rows
    table.setMinimumHeight(144)
    bins_layout.addWidget(table,1)
    splitter.addWidget(bins_panel)
    splitter.setSizes([390,260])
    splitter.setStretchFactor(0,3)
    splitter.setStretchFactor(1,2)
    layout.addWidget(splitter,1)
    dialog.hkl_resolution_summary = _resolution_summary(analysis)
    dialog.hkl_plot_figures = figures
    dialog.hkl_plot_tabs = tabs
    dialog.summary_text = 'HKL COMPLETENESS\n'+report.summary()+f'\nd_min: {analysis.d_min}\nd98: {analysis.d_full_98}'
    _footer(win,layout,dialog,report,analysis,figure)
    dialog.diagnostics = report
    dialog.hkl_bins_table = table
    dialog.hkl_bin_columns = columns
    dialog.hkl_metrics_panel = metrics
    dialog.hkl_plot_panel = tabs
    dialog.hkl_figure = figure
    dialog.hkl_canvas = canvas
    dialog.hkl_axes = axes
    dialog.hkl_resolution_axes = tuple(axis for name,axis in axes.items() if name!='distribution')
    dialog.hkl_histogram_axis = axes.get('distribution')
    dialog.hkl_histogram_scale = scale
    dialog.hkl_histogram_focus = focus
    dialog.hkl_distribution_values = values
    dialog.hkl_bins_title = bins_title
    dialog.hkl_content_splitter = splitter
    a.fit_dialog_to_available_screen(dialog,QSize(1120,900))
    dialog.restore_presentation()
    for label in dialog.findChildren(QLabel):
        if label.textFormat() != Qt.RichText and '</' not in label.text():
            label.setText(scientific_text(label.text()))
            label.setTextFormat(Qt.RichText)
        if label.toolTip():
            label.setToolTip(scientific_tooltip(label.toolTip()))
    for control in dialog.findChildren(QWidget):
        if control.toolTip() and not control.toolTip().startswith('<qt>'):
            control.setToolTip(scientific_tooltip(control.toolTip()))
    return dialog
