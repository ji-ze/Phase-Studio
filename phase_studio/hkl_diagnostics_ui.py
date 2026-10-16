"""Views of the common read-only diagnostic result; no scientific mutations."""
import math
from dataclasses import replace
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt, QTimer, QSize, QSettings
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QWidget,QLabel,
    QPushButton,QLineEdit,QTableWidget,QTableWidgetItem,QHeaderView,QSplitter,QScrollArea,QTabWidget,
    QFormLayout,QCheckBox,QComboBox,QSizePolicy,QDoubleSpinBox,QGridLayout,QToolButton,
    QAbstractItemView)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from .hkl_diagnostics import build_diagnostics, export_shell_csv


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
    layout.setSpacing(5)
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
    summary = win._diagnostic_input_summary(result.hkl_path,result.data_mode,result.cell,
        f'{result.spacegroup_hm} (#{result.spacegroup.number})',result.source_note,compact=True)
    body.addWidget(summary)
    count = QLabel(f'Parsed records: {report.count("parsed_records"):,} · Literal unique HKL: {report.count("literal_unique"):,} · '
                   f'Symmetry-independent orbits: {report.count("symmetry_orbits"):,} · Friedel pairs combined for coverage')
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


def _details(layout, dialog, report):
    button = QPushButton('Advanced diagnostics and definitions')
    button.setCheckable(True)
    layout.addWidget(button)
    dialog.hkl_advanced_button = button
    dialog.hkl_advanced = None

    def toggle(opened):
        if dialog.hkl_advanced is None and opened:
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
        grid.setColumnStretch(1, 1)
        self.values = {}
        for row, (key, value) in enumerate(rows):
            label = QLabel(str(key))
            label.setWordWrap(True)
            label.setFixedWidth(230)
            label.setStyleSheet('font-weight:600; color:#33456e;')
            text = value if isinstance(value, QWidget) else QLabel(str(value))
            if isinstance(text, QLabel):
                text.setTextFormat(Qt.PlainText)
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
    def explanation(text):
        label = QLabel(text)
        label.setTextFormat(Qt.PlainText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        return label
    def disclose(body, title, values):
        widget = _DiagnosticRows(values)
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
    name.setToolTip(report.source)
    filename_row.addWidget(name, 1)
    copy_path = QPushButton('Copy full path')
    copy_path.setAccessibleName('Copy full input path')
    copy_path.clicked.connect(lambda: QApplication.clipboard().setText(report.source))
    filename_row.addWidget(copy_path)
    detail.hkl_copy_path = copy_path
    detail.full_source_path = report.source
    rows(body, [('Input filename', filename), ('Data type', report.data_type), ('Declared data format', report.data_mode),
                ('Space group', group), ('Unit cell', _cell_display(report.cell)), ('Phases', phases),
                ('File provenance', file_kind), ('Source application', application),
                ('Observation-processing provenance', 'Not documented in the available input' if report.observation_kind == 'unknown' else report.observation_kind)])
    disclose(body, 'Detailed source provenance', [('Full input path', report.source), ('Source details', report.source_note),
                                                ('Exact symmetry setting', raw_sg)])
    body.addStretch(1)

    body = page('Counts && &symmetry')
    table = rows(body, count_rows(['parsed_records','literal_unique','symmetry_orbits','zero_000','excluded_000']) +
                 [('Space group', sg), ('Unit cell', _cell_display(report.cell))])
    table.values['Space group'].setToolTip(raw_sg)
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
        body.addWidget(explanation('No reflection-index, systematic-absence or duplication issues detected.'))
    rows(body, count_rows(issue_keys[:6]) + [('Forbidden HKL examples', report.absence_examples or 'None'),
                                           ('Conflicting HKL examples', report.duplicate_examples or 'None')])
    body.addWidget(explanation('Small nonzero forbidden values alone are not proof of experimental error. Repeated HKL alone does not establish unmerged observations.'))
    body.addStretch(1)

    body = page('&Values')
    integrity = count_rows(['invalid_values','zero_values','negative_values','missing_auxiliary','invalid_auxiliary',
                           'rejected_records','invalid_indices','invalid_reciprocal_values'])
    if phase_defined:
        integrity += count_rows(['phase_finite','phase_missing','phase_nonfinite'])
    else:
        integrity += [('Phase diagnostics', 'N/A — phase column not supplied' if report.available('column_semantics')
                       else 'N/A — phase-column meaning unverified')]
    rows(body, integrity, 'Input integrity')
    powder = report.data_type.startswith('Powder')
    amplitude = a.reflection_mode_is_amplitude(report.data_mode)
    value_kind = ('value (column meaning unverified)' if not report.available('column_semantics')
                  else 'intensity' if powder or not amplitude else 'amplitude')
    statistics = [('Mean input '+value_kind, number(report.statistic('mean_value'))),
                  ('Median input '+value_kind, number(report.statistic('median_value')))]
    if powder:
        units = '° 2θ' if report.fwhm_units == 'degrees_2theta' else report.fwhm_units
        statistics += [(f'Median FWHM ({units})', number(report.statistic('median_auxiliary'))),
                       (f'FWHM range ({units})', number(report.statistic('minimum_auxiliary'))+' – '+number(report.statistic('maximum_auxiliary'))),
                       ('Verified FWHM units', 'degrees 2θ' if report.fwhm_units == 'degrees_2theta' else 'Not verified; '+report.fwhm_units)]
    elif report.available('significance'):
        statistics += [('Median measurement uncertainty', number(report.statistic('median_auxiliary'))),
                       ('Measurement uncertainty range', number(report.statistic('minimum_auxiliary'))+' – '+number(report.statistic('maximum_auxiliary')))]
    elif report.statistic('median_auxiliary') is not None:
        statistics += [('Median auxiliary (not measurement uncertainty)', number(report.statistic('median_auxiliary'))),
                       ('Auxiliary range', number(report.statistic('minimum_auxiliary'))+' – '+number(report.statistic('maximum_auxiliary')))]
    rows(body, statistics, 'Intensity and width statistics' if powder else 'Value and uncertainty statistics')
    if report.warnings:
        disclose(body, 'Input diagnostic notes', report.warnings)
    body.addStretch(1)

    body = page('&Resolution')
    rows(body, [('HKL coverage', 'Fraction of symmetry-allowed reflection orbits represented in the input within the analyzed resolution range.'),
                ('d98', 'Highest-resolution boundary where cumulative HKL coverage reaches at least 98% within the analyzed domain.')])
    if powder:
        body.addWidget(explanation('HKL coverage does not establish that overlapping powder reflections were independently measured or experimentally resolved.'))
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
    methodology = [('Full HKL coverage definition', report.methods[0]), ('Full d98 definition', report.methods[1])]
    if direct:
        methodology += [('Amplitude convention', SIGNED_CONVENTION), ('Approximation', 'I ≈ F², σ(I) ≈ 2|F|σ(F). Unreliable near zero; not directly measured I/σ(I).')]
    disclose(body, 'Resolution methodology', methodology)
    body.addStretch(1)

    body = page('Peak &overlap')
    overlap = dict(report.overlap)
    body.addWidget(explanation('Estimated geometric overlap' if overlap.get('estimated') else 'Authoritative supplied groups' if overlap['available'] else 'Peak overlap unavailable'))
    if overlap['available']:
        metrics = QWidget()
        metric_grid = QGridLayout(metrics)
        metric_grid.setContentsMargins(0, 0, 0, 0)
        fraction = overlap.get('fraction')
        intensity = overlap.get('integrated_intensity_fraction')
        for col, (label, value) in enumerate([
            ('Overlapping groups', f'{overlap["group_count"]:,}'), ('Affected HKL', f'{100*fraction:.2f}%' if fraction is not None else 'N/A'),
            ('Intensity in overlapping groups', f'{100*intensity:.3f}%' if intensity is not None else 'N/A'), ('Largest group size', str(overlap['largest']))]):
            heading = explanation(label)
            metric_grid.addWidget(heading, 0, col)
            metric = explanation(value)
            metric.setStyleSheet('font-size:17pt; font-weight:600; color:#001170;')
            metric_grid.addWidget(metric, 1, col)
            metric_grid.setColumnStretch(col, 1)
        body.addWidget(metrics)
        rows(body, [('Indexed reflections', f'{report.count("parsed_records")-report.count("zero_000"):,}'),
                    ('Total groups', f'{overlap.get("total_groups", overlap["geometric_group_count"]):,}'),
                    ('Non-overlapping groups', f'{overlap.get("non_overlapping_groups", 0):,}'),
                    ('Overlapping groups', f'{overlap["group_count"]:,}'), ('Affected reflections', f'{overlap["affected"]:,}'),
                    ('Affected HKL fraction', f'{100*fraction:.3f}%' if fraction is not None else 'N/A'),
                    ('Intensity fraction', f'{100*intensity:.3f}%' if intensity is not None else 'N/A — finite nonnegative physical intensity required'),
                    ('Largest group', str(overlap['largest'])),
                    ('Group-size distribution', ' · '.join(f'{size} reflections: {count} groups' for size, count in overlap['size_distribution']) or 'No overlapping groups')])
    else:
        body.addWidget(explanation(overlap['reason']))
    disclose(body, 'Overlap methodology', [('Method and metadata', overlap['reason']),
        ('Wavelength (Å)', number(overlap.get('wavelength'))), ('Wavelength source', overlap.get('wavelength_source') or 'Not supplied'),
        ('FWHM units', report.fwhm_units.replace('degrees_2theta','degrees 2θ')),
        ('Separation factor', number(overlap.get('separation_factor'))),
        ('Denominators', 'Fractions and group sizes count original non-000 input records, not symmetry orbits or independently measured powder peaks. Intensity fraction uses finite nonnegative physical input intensity.')])
    body.addWidget(explanation('Geometric grouping does not establish experimentally independent observations. No intensity repartitioning is performed.'))
    body.addStretch(1)

    body = page('&Availability && limitations')
    capabilities = QTableWidget(len(report.capabilities), 3)
    capabilities.setObjectName('hklCapabilityTable')
    capabilities.setHorizontalHeaderLabels(['Analysis', 'Status', 'Reason'])
    capabilities.setEditTriggers(QAbstractItemView.NoEditTriggers)
    capabilities.setSelectionBehavior(QAbstractItemView.SelectRows)
    capabilities.setSelectionMode(QAbstractItemView.SingleSelection)
    capabilities.setWordWrap(True)
    capabilities.verticalHeader().hide()
    capabilities.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
    capabilities.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
    capabilities.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
    capabilities.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
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
            item.setToolTip(cap.reason)
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
            reason.setText(names.get(cap.name, cap.name)+': '+cap.reason)
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
    a.fit_dialog_to_available_screen(detail, QSize(1000, 570))
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
    return detail



def _footer(win, layout, dialog, report, analysis=None, figure=None):
    from .app import QFileDialog
    footer = QHBoxLayout()
    copy = QPushButton('Copy summary')
    copy.clicked.connect(lambda: QApplication.clipboard().setText(dialog.summary_text))
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
    summary = QLabel(f'Systematically absent: {report.count("systematic_absent_entries")} '
        f'(nonzero: {report.count("absent_nonzero_values")}{significant_absences}) · '
        f'Exact duplicate entries: {report.count("exact_duplicate_entries")} · '
        f'Conflicting groups: {report.count("conflicting_duplicate_groups")} · '
        f'Invalid values: {report.count("invalid_values")} · Rejected records: {report.count("rejected_records")}')
    summary.setWordWrap(True)
    layout.addWidget(summary)
    _details(layout,dialog,report)
    search = QLineEdit()
    search.setPlaceholderText('Find HKL: enter h k l (all parsed records; up to 200 matches shown)')
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
    headers += ['d (Å)','sinθ/λ']
    derived = QCheckBox('Show derived intensity approximation')
    derived.setToolTip('Secondary approximation: I ≈ F² and σ(I) ≈ 2|F|σ(F), unreliable near zero; not directly measured I/σ(I).')
    derived.setVisible(sig and amplitude)
    layout.addWidget(derived)
    table = QTableWidget(0,len(headers))
    win._configure_diagnostic_table(table)
    table.setHorizontalHeaderLabels(headers)
    for column in range(len(headers)):
        table.horizontalHeader().setSectionResizeMode(column,QHeaderView.ResizeToContents if column<3 else QHeaderView.Stretch)
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
            table.horizontalHeader().setSectionResizeMode(column,QHeaderView.ResizeToContents if column<3 else QHeaderView.Stretch)
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
    dialog.summary_text = 'HKL VALIDATION\n'+report.summary()
    _footer(win,layout,dialog,report)
    dialog.hkl_table = table
    dialog.hkl_search = search
    dialog.hkl_preview_label = label
    dialog.hkl_derived_checkbox = derived
    dialog.diagnostics = report
    a.fit_dialog_to_available_screen(dialog,QSize(1060,760))
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


def completeness_dialog(win, analysis):
    from . import app as a
    report = presentation_report(analysis)
    powder = report.data_type.startswith('Powder')
    direct = report.statistic('mean_f_over_sigma') is not None
    significance_key = 'mean_f_over_sigma' if direct else 'mean_significance'
    significance_label = DIRECT_LABEL if direct else report.significance_label
    dialog = QDialog(win)
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
    if len(panels)>=3:
        # In short windows keep chart typography intact instead of squeezing
        # four axes into strips. Only the chart canvas scrolls when necessary.
        canvas.setMinimumHeight(280)
        chart_scroll = QScrollArea()
        chart_scroll.setFrameShape(QScrollArea.NoFrame)
        chart_scroll.setWidgetResizable(True)
        chart_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        chart_scroll.setMinimumHeight(190)
        chart_scroll.setWidget(canvas)
        main_layout.addWidget(chart_scroll,1)
        dialog.hkl_chart_scroll = chart_scroll
    else:
        main_layout.addWidget(canvas,1)
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
        main_layout.removeWidget(canvas)
        canvas.hide()
        main_layout.addWidget(empty)
    def count_scale():
        if 'distribution' in axes:
            axes['distribution'].set_yscale('log' if scale.currentIndex()==0 else 'linear')
            axes['distribution'].relim()
            axes['distribution'].autoscale_view()
            canvas.draw_idle()
    scale.currentIndexChanged.connect(lambda _index:count_scale())
    count_scale()
    tabs.addTab(main,'Analysis')
    figures = {0:figure}
    overlap = dict(report.overlap)
    if overlap['available']:
        overlap_page = QWidget()
        overlap_layout = QVBoxLayout(overlap_page)
        overlap_layout.setContentsMargins(0,0,0,0)
        status = 'Estimated geometric peak overlap' if overlap.get('estimated') else 'Authoritative supplied overlap groups'
        physical = report.count('parsed_records')-report.count('zero_000')
        intensity = overlap.get('integrated_intensity_fraction')
        summary = QLabel(f'{status}\nOverlapping groups: {overlap["group_count"]:,} · Total groups: {overlap["geometric_group_count"]:,} · '
            f'Isolated reflections: {physical-overlap["affected"]:,}\nReflections affected: {overlap["affected"]:,} / {physical:,} ({100*overlap["fraction"]:.1f}%) · '
            + (f'Intensity in overlapping groups: {100*intensity:.1f}% · ' if intensity is not None else '')
            + f'Largest group: {overlap["largest"]} reflections')
        summary.setToolTip('Groups here means multi-record overlap groups. Singletons and total group count are reported in Advanced diagnostics. Fractions count original non-000 input records, not symmetry orbits.')
        summary.setWordWrap(True)
        overlap_layout.addWidget(summary)
        criterion = QLabel(overlap['reason'])
        criterion.setWordWrap(True)
        overlap_layout.addWidget(criterion)
        overlap_figure = Figure(figsize=(9,3),dpi=100,layout='constrained')
        overlap_canvas = FigureCanvasQTAgg(overlap_figure)
        overlap_canvas.setMinimumHeight(190)
        size_axis,fraction_axis = overlap_figure.subplots(1,2)
        sizes = overlap['size_distribution']
        if sizes:
            size_axis.bar([x[0] for x in sizes],[x[1] for x in sizes],color='#2264b8')
            size_axis.set_xlabel('HKL per overlap group',fontsize=8)
            size_axis.set_ylabel('Groups',fontsize=8)
            size_axis.set_title('Overlapping group sizes',fontsize=9)
        else:
            size_axis.text(.5,.5,'No overlapping groups under the stated criterion',transform=size_axis.transAxes,ha='center',va='center',fontsize=8)
            size_axis.set_axis_off()
        fraction_axis.plot(centers,[row['overlap_fraction'] if row['overlap_fraction'] is not None else np.nan for row in rows],'o-',color='#2264b8')
        fraction_axis.set_xlabel('sinθ/λ (Å⁻¹)',fontsize=8)
        fraction_axis.set_ylabel('HKL overlap fraction',fontsize=8)
        fraction_axis.set_title('Affected input records vs resolution',fontsize=9)
        fraction_axis.set_ylim(0,1.05)
        for axis in (size_axis,fraction_axis):axis.tick_params(labelsize=8)
        overlap_layout.addWidget(overlap_canvas,1)
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
    splitter.addWidget(tabs)
    bins_panel = QWidget()
    bins_layout = QVBoxLayout(bins_panel)
    bins_layout.setContentsMargins(0,0,0,0)
    bins_title = QLabel('RESOLUTION BINS · undefined coverage = n/a')
    bins_layout.addWidget(bins_title)
    columns = [('lo','sinθ/λ min'),('hi','sinθ/λ max'),('observed','Input HKL'),('theory','Allowed HKL'),('coverage','Coverage (%)'),
               ('mean_value',f'Mean {value}'),('median_value',f'Median {value}')]
    if powder and report.count('valid_widths_or_sigmas'):
        columns.append(('mean_fwhm','Mean FWHM'))
    elif report.available('significance'):
        columns += [(significance_key,'Mean '+significance_label)]
    table = QTableWidget(len(rows),len(columns))
    win._configure_diagnostic_table(table)
    table.verticalHeader().setDefaultSectionSize(24)
    table.setHorizontalHeaderLabels([label for _,label in columns])
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    for j,(key,label) in enumerate(columns):
        table.horizontalHeaderItem(j).setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        table.horizontalHeaderItem(j).setToolTip('FWHM units: '+units if key=='mean_fwhm' else SIGNED_CONVENTION if key=='mean_f_over_sigma' else report.methods[0] if key in {'observed','theory','coverage'} else label+'; full precision is retained in CSV and JSON exports.')
    for i,row in enumerate(rows):
        for j,(key,_) in enumerate(columns):
            val = row[key]
            text = str(int(val)) if key in {'observed','theory'} else _display_number(val,5 if key in {'lo','hi','mean_fwhm'} else 3)
            item = _NumericItem(text,val)
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            item.setToolTip(repr(val))
            table.setItem(i,j,item)
    table.setMinimumHeight(120)
    bins_layout.addWidget(table,1)
    splitter.addWidget(bins_panel)
    splitter.setSizes([320,225])
    splitter.setStretchFactor(0,1)
    splitter.setStretchFactor(1,1)
    layout.addWidget(splitter,1)
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
    dialog.hkl_distribution_values = values
    dialog.hkl_bins_title = bins_title
    dialog.hkl_content_splitter = splitter
    a.fit_dialog_to_available_screen(dialog,QSize(1120,900))
    return dialog
