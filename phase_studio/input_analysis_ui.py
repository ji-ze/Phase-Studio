"""Unified data analysis, reusing the immutable diagnostic authority."""
from pathlib import Path
import math
import json
import numpy as np
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget,
    QWidget, QPushButton, QComboBox, QScrollArea, QFileDialog, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QDoubleSpinBox, QSizePolicy)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from .input_analysis import (analysis_rows, significance_cutoff, strict_full_resolution,
                             export_rows, CUTOFF_METHOD, CC_UNAVAILABLE, import_half_dataset_statistics,
                             analysis_payload, grouped_resolution_markers)
from .hkl_diagnostics_ui import (presentation_report, _detail_dialog, number, _overlap_metrics,
                                 overlap_group_dialog, _PlotHover, _BinPoint)

TABS = ('Overview', 'Resolution', 'Intensity & Amplitude', 'Signal & Uncertainty',
        'Symmetry & Coverage', 'Powder & Peak Overlap', 'Advanced Diagnostics')


def analyze_data_dialog(win, analysis):
    from . import app as a
    from .ui_branding import fit_dialog_to_available_screen
    report = presentation_report(analysis)
    rows = analysis_rows(analysis, report)
    limits = {n:significance_cutoff(rows,n) for n in (2,3)}
    d_full = strict_full_resolution(analysis)
    powder = report.data_type.startswith('Powder')
    dialog = QDialog(win)
    dialog.setWindowTitle('Analyze data')
    dialog.setWindowFlag(Qt.WindowMaximizeButtonHint,True)
    root = QVBoxLayout(dialog)
    integrity = 'Warnings' if report.warnings else 'Parsed'
    root.addWidget(win._diagnostic_header('ANALYZE DATA',
        f'{Path(analysis.hkl_path).name} · {report.data_type} · {analysis.spacegroup_hm}', integrity, compact=True))
    overlap = dict(report.overlap)
    metadata = QLabel('Wavelength: ' + (f'{overlap["wavelength"]:.8g} Å · {overlap.get("wavelength_source", "input metadata")}'
                       if overlap.get('wavelength') else 'unavailable / not established in this diagnostic snapshot'))
    metadata.setWordWrap(True)
    root.addWidget(metadata)
    cards = [(str(report.count('parsed_records')), 'Input records'),
             (str(sum(r['observed'] for r in rows)), 'Allowed indexed orbits'),
             (number(analysis.d_min)+' Å','d_min'),
             (number(analysis.d_full_98)+' Å' if analysis.d_full_98 else 'Not reached','d98 ≥98%'),
             (number(d_full)+' Å' if d_full else 'Not reached','d_full 100%')]
    for threshold in (2,3):
        cards.append((number(limits[threshold]['d'])+' Å' if limits[threshold] else 'Unavailable',
                      f'd(mean I/σ(I)={threshold})' + (' · derived' if a.reflection_mode_is_amplitude(analysis.data_mode) else '')))
    metrics = win._diagnostic_metric_grid(cards,compact=True,row_columns=(4,3))
    metrics.setToolTip(CUTOFF_METHOD)
    root.addWidget(metrics)
    tabs = QTabWidget()
    tabs.setUsesScrollButtons(True)
    root.addWidget(tabs,1)
    pages = []
    for name in TABS:
        page = QWidget()
        layout = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        tabs.addTab(scroll,name)
        pages.append(layout)
    def note(index,text):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        pages[index].addWidget(label)
        return label
    note(0,f'{report.data_type} · {report.data_mode}\nSource: {report.source}\n{report.source_note}')
    note(0,'Unit cell: '+', '.join(number(v) for v in analysis.cell.parameters))
    note(0,'Literal unique HKL: '+str(report.count('literal_unique')))
    pages[0].addWidget(win._diagnostic_metric_grid([
        (number(report.statistic('mean_value')),'Mean observed value'),
        (number(report.statistic('median_value')),'Median observed value'),
        (str(report.count('symmetry_orbits')),'Symmetry orbits (incl. forbidden indices)'),
        (str(report.count('zero_values')),'Zero values'),
        (str(report.count('negative_values')),'Negative values'),
        (number(report.statistic('mean_significance')),'Mean I/σ(I)' + (' · derived' if a.reflection_mode_is_amplitude(analysis.data_mode) else '')),
    ],compact=True,row_columns=(3,3)))
    note(0,'\n'.join(f'{severity}: {text}' for severity,text in report.warnings))
    note(0,'Diagnostics are read-only. Original records, reconstruction filters and RunConfig remain unchanged.')
    method_note = note(1,CUTOFF_METHOD)
    coverage_note = note(1,'d_min is the observed accepted-domain boundary. d_full is the last exact theoretical reciprocal-radius boundary with 100% cumulative allowed-orbit coverage from infinite d. d98 retains its existing ≥98% definition. Friedel mates combined; 000 and systematic absences excluded; equal-radius boundaries grouped within 1e-12 sinθ/λ. Neither is an independent experimental quality cutoff.')
    method_note.hide();coverage_note.hide()
    definitions = QPushButton('Resolution definitions and cutoff method')
    definitions.setCheckable(True)
    definitions.toggled.connect(method_note.setVisible)
    definitions.toggled.connect(coverage_note.setVisible)
    pages[1].insertWidget(0,definitions)
    for threshold,limit in limits.items():
        if limit:
            upper = str(limit['d_high']) if limit['d_high'] is not None else '∞'
            note(1,f'Mean I/σ(I) = {threshold}: {limit["d"]:.7g} Å; adjacent-shell bracket {limit["d_low"]} to {upper} Å (not a confidence interval).')
    note(1,CC_UNAVAILABLE)
    external_status = note(6,'External half-dataset statistics may be imported with source, method and independence evidence. The application validates the interchange, not the truth of the producer’s provenance claim.')
    import_cc = QPushButton('Import external CC1/2 statistics')
    pages[6].addWidget(import_cc)
    external_cc = {}
    cc_threshold = QDoubleSpinBox()
    cc_threshold.setRange(-1,1)
    cc_threshold.setDecimals(3)
    cc_threshold.setValue(.3)
    cc_threshold.setPrefix('External CC1/2 cutoff: ')
    cc_threshold.setToolTip('User-selected criterion, not a universal crystallographic threshold. Sustained crossing uses at least 20 paired orbits per shell; a bracket is not a confidence interval.')
    pages[6].addWidget(cc_threshold)
    cc_limit = note(6,'CC1/2 cutoff unavailable until external statistics are imported.')
    note(3,('Derived I/σ(I) ≈ |F|/(2σ(F)), unreliable near zero amplitudes. Direct F/σ(F) is signed.'
            if a.reflection_mode_is_amplitude(analysis.data_mode) and report.available('significance') else
            'Genuine measured σ(I) is used.' if report.available('significance') else
            'Significance unavailable: genuine measured uncertainties are absent or column semantics are unverified. FWHM and dummy sigma are excluded.'))
    note(4,'Indexed HKL coverage is not independent experimental completeness for powder data. '+report.methods[0])
    note(5,'Geometry-based overlap is an estimate, not proof of measured peak separation. '+overlap.get('reason',''))
    if powder:
        note(5,('Constant' if report.statistic('constant_fwhm') else 'Variable or incomplete')+' FWHM · units: '+report.fwhm_units+' · finite positive widths: '+str(report.count('valid_widths_or_sigmas')))
    if powder and overlap.get('available'):
        pages[5].addWidget(_overlap_metrics(report))
        note(5,'Isolated reflections: '+str(overlap.get('non_overlapping_groups')))
        inspect = QPushButton('Inspect overlap groups and constituent records')
        def inspect_groups():
            child=overlap_group_dialog(dialog,analysis,report)
            dialog.overlap_inspection=child
            child.show()
        inspect.clicked.connect(inspect_groups)
        pages[5].addWidget(inspect)
    note(6,'\n'.join(report.methods))
    table = QTableWidget(len(rows),len(rows[0]) if rows else 0)
    if rows:
        table.setHorizontalHeaderLabels(list(rows[0]))
        for i,row in enumerate(rows):
            for j,value in enumerate(row.values()):
                item = QTableWidgetItem('Unavailable' if value is None else repr(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(i,j,item)
    table.setMinimumHeight(170)
    pages[6].addWidget(table)
    # Preserve all existing technical fields, samples, assumptions and exports.
    details = _detail_dialog(dialog,report)
    details.layout().removeWidget(details.hkl_details_tabs)
    pages[6].addWidget(details.hkl_details_tabs)
    details.hkl_details_tabs.setParent(pages[6].parentWidget())
    dialog.advanced_source = details
    controls = QHBoxLayout()
    axis_mode = QComboBox()
    axis_mode.addItems(['d (Å) · high resolution to the right','sin θ / λ (Å⁻¹)'])
    frequency = QComboBox()
    frequency.addItems(['Input records','Literal unique HKL','Allowed indexed orbits','Records per unit sin θ / λ'])
    counts = QComboBox()
    counts.addItems(['Linear counts','Log counts'])
    plot_pair = QComboBox()
    plot_pair.addItems(['Primary plots','Additional plots','External / amplitude plots'])
    histogram_range = QComboBox()
    histogram_range.addItems(['Full histogram range','Detail histogram: 1–99%'])
    histogram_range.setToolTip('Display-only range. Original values and reconstruction inputs are retained. The graph CSV describes the displayed histogram bins.')
    for control in (axis_mode,frequency,counts,plot_pair): controls.addWidget(control)
    controls.addWidget(histogram_range)
    root.insertLayout(3,controls)
    figures = {}
    canvases = {}
    toolbars = {}
    rendered = set()
    graph_data = {}
    hover = {}
    value_label = a.reflection_value_label(analysis.data_mode)
    raw = analysis.reflections_raw
    values = np.asarray([r.value for r in raw if (r.h,r.k,r.l)!=(0,0,0) and math.isfinite(r.value)])
    auxiliary = np.asarray([r.sigma for r in raw if (r.h,r.k,r.l)!=(0,0,0) and r.sigma is not None and math.isfinite(r.sigma) and r.sigma>0])
    def render(index, force=False):
        if index in (0,6) or index in rendered and not force: return
        if index==3 and not report.available('significance'):
            return
        if index==5 and not powder:
            return
        if index not in figures:
            fig = Figure(figsize=(10,6),layout='constrained')
            canvas = FigureCanvasQTAgg(fig)
            canvas.setMinimumSize(0,300)
            canvas.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Ignored)
            toolbar = NavigationToolbar2QT(canvas,dialog)
            pages[index].addWidget(toolbar)
            pages[index].addWidget(canvas,1)
            figures[index],canvases[index],toolbars[index] = fig,canvas,toolbar
        fig = figures[index]
        fig.clear()
        x = np.asarray([r['d'] if axis_mode.currentIndex()==0 else r['center'] for r in rows])
        specs = {
            1:[('frequency','Reflection frequency vs resolution'),('coverage','Indexed/symmetry-allowed coverage'),('cumulative_records','Cumulative input records'),('mean_significance','Mean intensity significance')],
            2:[('hist',value_label+' distribution'),('frequency','Reflection frequency vs resolution'),('mean_value','Mean '+value_label),('median_value','Median '+value_label)],
            3:[('mean_significance','Mean I/σ(I)' + (' · derived' if a.reflection_mode_is_amplitude(analysis.data_mode) else '')),('median_significance','Median I/σ(I)'),('fraction_above_2','Fraction ≥2'),('sigma','Genuine uncertainty distribution')],
            4:[('coverage','Indexed/symmetry-allowed coverage (%)'),('cumulative_coverage','Cumulative coverage (%)'),('observed','Indexed vs allowed orbits'),('missing','Missing allowed orbits')],
            5:[('mean_fwhm','Mean FWHM ('+report.fwhm_units+')'),('frequency','Reflection frequency vs resolution'),('overlap_fraction','Fraction in overlap groups'),('groups','Overlap-group size distribution')],
        }[index]
        if index==1 and not report.available('significance'):
            specs = [pair for pair in specs if pair[0]!='mean_significance']
        if index==3 and report.statistic('mean_f_over_sigma') is not None:
            specs += [('mean_f_over_sigma','Direct signed F/σ(F)'),('median_f_over_sigma','Median direct F/σ(F)')]
        if index==1 and external_cc:
            specs += [('cc_half','Imported CC1/2 · supplied independence provenance')]
        offset = plot_pair.currentIndex()*2
        specs = specs[offset:offset+2] or specs[:2]
        plot_rows = 1
        graph_data[index] = []
        for j,(key,title) in enumerate(specs):
            ax = fig.add_subplot(plot_rows,2,j+1)
            ax.set_title(title,fontsize=9)
            unavailable = ((index==3 or key=='mean_significance') and not report.available('significance')) or (index==5 and not powder) or (key in ('overlap_fraction','groups') and not overlap.get('available'))
            if unavailable:
                ax.text(.5,.5,'Unavailable\n'+('Genuine measured uncertainties required' if index==3 or key=='mean_significance' else 'Applicable powder metadata required'),ha='center',va='center',wrap=True,transform=ax.transAxes,fontsize=8)
                ax.set_axis_off()
                continue
            if key in ('hist','sigma'):
                sample = values if key=='hist' else auxiliary
                if histogram_range.currentIndex()==1 and len(sample):
                    low,high = np.percentile(sample,[1,99])
                    sample = sample[(sample>=low)&(sample<=high)]
                    ax.set_title(title+' · detail 1–99%',fontsize=9)
                heights,edges,_ = ax.hist(sample,bins=min(100,max(1,int(np.sqrt(len(values))))))
                for left,right,height in zip(edges[:-1],edges[1:],heights):
                    graph_data[index].append(dict(series=key,x=float(left),x_end=float(right),y=float(height)))
                ax.set_xlabel(value_label if key=='hist' else a.reflection_sigma_label(analysis.data_mode))
                ax.set_ylabel('Original input records')
            elif key=='groups':
                size_frequency = dict(overlap.get('size_distribution',()))
                ax.bar(list(size_frequency),list(size_frequency.values()))
                graph_data[index] += [dict(series=key,x=k,x_end=None,y=v) for k,v in size_frequency.items()]
                ax.set_xlabel('Reflections per group'); ax.set_ylabel('Groups')
            elif key=='cc_half':
                xx = [(r['lo']+r['hi'])/2 for r in external_cc['shells']]
                if axis_mode.currentIndex()==0: xx = [1/(2*v) for v in xx]
                yy = [r['cc_half'] for r in external_cc['shells']]
                ax.plot(xx,yy,'o-')
                ax.set_xlabel('d (Å)' if axis_mode.currentIndex()==0 else 'sin θ / λ (Å⁻¹)')
                if axis_mode.currentIndex()==0: ax.invert_xaxis()
                graph_data[index] += [dict(series=key,x=u,x_end=None,y=v) for u,v in zip(xx,yy)]
            else:
                selected_key = ('records','literal_unique','observed','record_density')[frequency.currentIndex()] if key=='frequency' else key
                y = [r.get(selected_key) if r.get(selected_key) is not None else np.nan for r in rows]
                ax.plot(x,y,'o-',markersize=3,label=selected_key)
                graph_data[index] += [dict(series=selected_key,x=float(u),x_end=None,y=v) for u,v in zip(x,y)]
                if key=='observed':
                    ax.plot(x,[r['theory'] for r in rows],label='Allowed'); ax.legend(fontsize=7)
                    graph_data[index] += [dict(series='theory',x=float(u),x_end=None,y=r['theory']) for u,r in zip(x,rows)]
                ax.set_xlabel('d (Å)' if axis_mode.currentIndex()==0 else 'sin θ / λ (Å⁻¹)')
                if axis_mode.currentIndex()==0: ax.invert_xaxis()
                ax.set_ylabel(selected_key.replace('_',' '))
                markers = [('d_min',analysis.d_min),('d98',analysis.d_full_98),('d_full',d_full)] + [(f'I/σ={n}',limits[n]['d'] if limits[n] else None) for n in (2,3)]
                for label,d in grouped_resolution_markers(markers):
                    if d and math.isfinite(d):
                        position = d if axis_mode.currentIndex()==0 else 1/(2*d)
                        ax.axvline(position,linestyle=':',alpha=.4,label=label)
                        ax.annotate(label,(position,1),xycoords=('data','axes fraction'),rotation=90,va='top',fontsize=6)
            if counts.currentIndex()==1 and key in ('hist','sigma','groups','frequency','cumulative_records','observed','missing'):
                ax.set_yscale('log',nonpositive='mask')
            ax.grid(alpha=.15)
        entries=[]
        for ax in fig.axes:
            for line in ax.lines:
                if len(line.get_xdata())<=2: continue
                for i,(u,v) in enumerate(zip(line.get_xdata(),line.get_ydata())):
                    if np.isfinite(u) and np.isfinite(v):
                        entries.append(((id(line),i),ax,_BinPoint(line,i),lambda u=u,v=v,label=line.get_label():f'{label}\nx: {u!r}\ny: {v!r}'))
            for bar in ax.patches:
                entries.append(((id(bar),0),ax,bar,lambda bar=bar:f'Interval: {bar.get_x()!r} to {bar.get_x()+bar.get_width()!r}\nCount: {bar.get_height()!r}'))
        hover[index]=_PlotHover(canvases[index],entries)
        canvases[index].draw_idle()
        rendered.add(index)
    def load_cc():
        filename,_ = QFileDialog.getOpenFileName(dialog,'Import external CC1/2 statistics','','JSON (*.json)')
        if not filename: return
        try:
            data = import_half_dataset_statistics(filename)
        except (ValueError,KeyError,TypeError,OSError) as error:
            QMessageBox.warning(dialog,'CC1/2 import rejected',str(error))
            return
        external_cc.clear(); external_cc.update(data)
        external_status.setText('Imported source: '+data['source']+' · Method: '+data['method']+' · Supplied independence evidence: '+data['independence_evidence'])
        render(1,True)
    import_cc.clicked.connect(load_cc)
    def update_cc_limit():
        if not external_cc: return
        cc_rows = [dict(r,center=(r['lo']+r['hi'])/2,mean_significance=r['cc_half'],significance_count=r['paired_orbits']) for r in external_cc['shells']]
        limit = significance_cutoff(cc_rows,cc_threshold.value())
        upper = str(limit['d_high']) if limit and limit['d_high'] is not None else '∞'
        cc_limit.setText('Imported CC1/2 criterion: '+(f'{limit["d"]:.7g} Å · bracket {limit["d_low"]} to {upper} Å' if limit else 'Unavailable — no supported sustained crossing.'))
    import_cc.clicked.connect(update_cc_limit)
    cc_threshold.valueChanged.connect(update_cc_limit)
    tabs.currentChanged.connect(render)
    def refresh():
        for index in tuple(rendered): render(index,True)
    for control in (axis_mode,frequency,counts,plot_pair,histogram_range): control.currentIndexChanged.connect(refresh)
    buttons = QHBoxLayout()
    json_button = QPushButton('Export diagnostics JSON')
    def save_diagnostics():
        filename,_ = QFileDialog.getSaveFileName(dialog,'Export diagnostics','','JSON (*.json)')
        if filename:
            Path(filename).write_text(json.dumps(analysis_payload(analysis,report,rows,limits,external_cc),indent=2,ensure_ascii=False,allow_nan=False),encoding='utf8')
    json_button.clicked.connect(save_diagnostics)
    buttons.addWidget(json_button)
    csv_button = QPushButton('Export graph data CSV')
    def save_csv():
        filename,_ = QFileDialog.getSaveFileName(dialog,'Export analysis data','','CSV (*.csv)')
        if filename:
            index = tabs.currentIndex()
            export_rows(filename,graph_data[index] if index in graph_data else rows)
    csv_button.clicked.connect(save_csv)
    buttons.addWidget(csv_button)
    image_button = QPushButton('Export plot PNG/SVG')
    def save_image():
        if tabs.currentIndex() not in figures: return
        filename,_ = QFileDialog.getSaveFileName(dialog,'Export plot','','PNG (*.png);;SVG (*.svg)')
        if filename: figures[tabs.currentIndex()].savefig(filename,dpi=180)
    image_button.clicked.connect(save_image)
    buttons.addWidget(image_button)
    close = QPushButton('Close'); close.clicked.connect(dialog.close); buttons.addWidget(close)
    root.addLayout(buttons)
    for index in (0,3,5): pages[index].addStretch()
    dialog.analysis_rows,dialog.analysis_limits = rows,limits
    dialog.analysis_tabs,dialog.analysis_figures = tabs,figures
    dialog.analysis_report = report
    dialog.analysis_graph_data = graph_data
    dialog.analysis_table = table
    dialog.analysis_plot_pair = plot_pair
    dialog.analysis_histogram_range = histogram_range
    dialog.analysis_canvas = canvases
    fit_dialog_to_available_screen(dialog,QSize(1400,980))
    return dialog
