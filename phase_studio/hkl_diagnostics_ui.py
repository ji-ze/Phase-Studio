"""Views of the common read-only diagnostic result; no scientific mutations."""
import math
from dataclasses import replace
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QWidget,QLabel,
    QPushButton,QLineEdit,QTableWidget,QTableWidgetItem,QHeaderView,QSplitter,QScrollArea,QTabWidget,
    QFormLayout,QCheckBox,QComboBox,QSizePolicy,QDoubleSpinBox)
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


def _detail_dialog(parent, report):
    """Owned, nonmodal detail pages never participate in the main layout."""
    from . import app as a
    detail = QDialog(parent)
    detail.setWindowTitle('HKL advanced diagnostics and definitions')
    detail.setObjectName('hklAdvancedDiagnostics')
    detail.setModal(False)
    root = QVBoxLayout(detail)
    tabs = QTabWidget()
    root.addWidget(tabs,1)
    def page(title, rows):
        content = QWidget()
        form = QFormLayout(content)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        for key,value in rows:
            label = QLabel(str(key))
            label.setStyleSheet('font-weight:600; color:#33456e;')
            text = QLabel(str(value))
            text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(label,text)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setFrameShape(QScrollArea.NoFrame)
        tabs.addTab(scroll,title)
    counts = dict(report.counts)
    labels = {'parsed_records':'Parsed records','literal_unique':'Literal unique HKL',
              'symmetry_orbits':'Symmetry-independent orbits','systematic_absent_entries':'Systematically absent entries',
              'exact_duplicate_entries':'Exact duplicate entries','conflicting_duplicate_groups':'Conflicting duplicate groups',
              'equivalent_repeated_entries':'Symmetry-equivalent repeated entries','zero_000':'Protocol (0,0,0) records',
              'valid_widths_or_sigmas':'Positive finite auxiliary fields','phase_finite':'Finite phase fields',
              'absent_significant_3sigma':'Absent entries with derived/intensity significance ≥3'}
    def count_rows(keys):
        return [(labels.get(key,key.replace('_',' ').capitalize()),'n/a' if counts.get(key) is None else f'{counts[key]:,}') for key in keys]
    page('Input', [('Source',report.source),('Provenance',report.source_note),('Data type',report.data_type),
                   ('Declared format',report.data_mode),('Observation provenance',report.observation_kind),('Phase fields',report.phase_status)])
    page('Counts & symmetry',count_rows(['parsed_records','literal_unique','symmetry_orbits','zero_000','excluded_000'])+
         [('Space group',report.spacegroup),('Unit cell',' · '.join(number(v) for v in report.cell)),('Counting convention',report.methods[0])])
    page('Absences & duplicates',count_rows(['systematic_absent_entries','absent_nonzero_values','absent_significant_3sigma',
         'exact_duplicate_entries','equivalent_repeated_entries','conflicting_duplicate_groups'])+
         [('Forbidden HKL examples',report.absence_examples or 'None'),('Conflicting HKL examples',report.duplicate_examples or 'None'),
          ('Interpretation','Small nonzero forbidden values alone are not proof of experimental error. Repeated HKL alone does not establish unmerged observations.')])
    value_rows = (count_rows(['invalid_values','zero_values','negative_values','missing_auxiliary','invalid_auxiliary',
         'rejected_records','invalid_indices','invalid_reciprocal_values','phase_finite','phase_missing','phase_nonfinite'])+
         [(severity,message) for severity,message in report.warnings])
    value_rows += [('Mean input value',number(report.statistic('mean_value'))),('Median input value',number(report.statistic('median_value')))]
    if report.statistic('median_auxiliary') is not None:
        kind = 'FWHM ('+report.fwhm_units.replace('degrees_2theta','degrees 2θ')+')' if report.data_type.startswith('Powder') else 'positive finite auxiliary field'
        value_rows += [('Median '+kind,number(report.statistic('median_auxiliary'))),
                       ('Range of '+kind,number(report.statistic('minimum_auxiliary'))+' – '+number(report.statistic('maximum_auxiliary')))]
    page('Values',value_rows)
    resolution = [('Coverage definition',report.methods[0]),('d98 definition',report.methods[1])]
    if report.statistic('mean_f_over_sigma') is not None:
        resolution += [('Mean F/σ(F)',number(report.statistic('mean_f_over_sigma'))),
                       ('Median F/σ(F)',number(report.statistic('median_f_over_sigma'))),('Amplitude convention',SIGNED_CONVENTION)]
    if report.available('significance'):
        resolution += [(('Secondary ' if report.statistic('mean_f_over_sigma') is not None else 'Mean ')+report.significance_label,number(report.statistic('mean_significance')))]
        resolution += [('Median '+report.significance_label,number(report.statistic('median_significance')))]
        for key,val in report.statistics:
            if key.startswith('weak_fraction_below_'):
                ratio = 'derived I/σ(I)' if report.statistic('mean_f_over_sigma') is not None else 'I/σ(I)'
                resolution.append((f'Fraction with {ratio} < {key.removeprefix("weak_fraction_below_")}',f'{100*val:.3f}%'))
        if report.statistic('mean_f_over_sigma') is not None:
            resolution += [('Approximation','I ≈ F², σ(I) ≈ 2|F|σ(F). The approximation is unreliable near zero and is not directly measured I/σ(I).')]
    page('Resolution',resolution)
    overlap = dict(report.overlap)
    overlap_rows = [('Status','Estimated geometric overlap' if overlap.get('estimated') else 'Authoritative supplied groups' if overlap['available'] else 'Unavailable'),
                    ('Method and metadata',overlap['reason'])]
    if overlap['available']:
        overlap_rows += [('Indexed reflections',report.count('parsed_records')-report.count('zero_000')),
                         ('Total groups including singletons',overlap.get('total_groups',overlap['geometric_group_count'])),
                         ('Non-overlapping groups',overlap.get('non_overlapping_groups',0)),
                         ('Overlapping groups',overlap['group_count']),('Affected reflections',overlap['affected']),
                         ('Affected fraction',f'{100*overlap["fraction"]:.2f}%'),('Largest group',overlap['largest']),
                         ('Group-size distribution',', '.join(f'{size} HKL: {count} groups' for size,count in overlap['size_distribution']))]
        overlap_rows += [('Denominators','Affected fraction: original non-000 input records. Group sizes count records, not symmetry orbits or independently measured powder peaks.')]
        if 'integrated_intensity_fraction' in overlap:
            overlap_rows += [('Intensity in overlapping groups',f'{100*overlap["integrated_intensity_fraction"]:.3f}% of finite nonnegative physical input intensity')]
    overlap_rows.append(('Limitation','Geometric groups are not experimentally verified independent observations. No intensity repartitioning is performed.'))
    page('Peak overlap',overlap_rows)
    page('Limitations',[(cap.name.replace('_',' ').capitalize(),('Available. ' if cap.available else 'Unavailable. ')+cap.reason) for cap in report.capabilities]+
         [('Phase provenance',report.phase_status)]+[('Method',text) for text in report.methods[2:]])
    close = QPushButton('Close')
    close.clicked.connect(detail.close)
    root.addWidget(close,0,Qt.AlignRight)
    detail.hkl_details_tabs = tabs
    a.fit_dialog_to_available_screen(detail,QSize(900,650))
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
        status = 'Estimated geometric overlap' if overlap.get('estimated') else 'Authoritative supplied overlap groups'
        summary = QLabel(f'{status} · Indexed HKL: {report.count("parsed_records")-report.count("zero_000"):,} · '
            f'Groups: {overlap["group_count"]:,} · Affected: {overlap["affected"]:,} ({100*overlap["fraction"]:.1f}%) · Largest group: {overlap["largest"]}')
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
        else:
            size_axis.text(.5,.5,'No overlapping groups under the stated criterion',transform=size_axis.transAxes,ha='center',va='center',fontsize=8)
            size_axis.set_axis_off()
        fraction_axis.plot(centers,[row['overlap_fraction'] if row['overlap_fraction'] is not None else np.nan for row in rows],'o-',color='#2264b8')
        fraction_axis.set_xlabel('sinθ/λ (Å⁻¹)',fontsize=8)
        fraction_axis.set_ylabel('HKL overlap fraction',fontsize=8)
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
