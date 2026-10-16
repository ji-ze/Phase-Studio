"""Actual Qt HKL views: real ochlor and explicitly marked controlled fixtures."""
import os
import sys
from pathlib import Path
from dataclasses import replace
import json
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QSettings
from phase_studio import app as a
from phase_studio import hkl_diagnostics as d

app = QApplication([])
a.apply_phase_studio_style(app)
settings = tempfile.TemporaryDirectory()
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,settings.name)
win = a.IterativeSuperflipPipelineQtGUI()
scale = os.environ.get('QT_SCALE_FACTOR','1')
presentation = '--final-presentation' in sys.argv
out = ROOT/('docs/screenshots/2.0.4-hkl-presentation/after' if presentation else 'docs/screenshots/2.0.4-hkl-diagnostics')/('scale-'+scale)
out.mkdir(parents=True,exist_ok=True)
work = ROOT/'build/hkl-modernization/capture'
work.mkdir(parents=True,exist_ok=True)
records = {}


def capture(name,dialog,width=1120,height=900,advanced=False):
    dialog.show()
    dialog.resize(width,height)
    for _ in range(25): app.processEvents()
    before = dialog.hkl_plot_panel.geometry().getRect() if hasattr(dialog,'hkl_plot_panel') else None
    if advanced:
        dialog.hkl_advanced_button.setChecked(True)
        for _ in range(25):app.processEvents()
        dialog.hkl_advanced.grab().save(str(out/(name+'-details.png')))
    dialog.grab().save(str(out/(name+'.png')))
    info = dict(size=dialog.size().toTuple(),dpi=dialog.devicePixelRatioF(),source=dialog.full_source_path)
    if hasattr(dialog,'hkl_bins_table'):
        table = dialog.hkl_bins_table
        info['visible_bin_rows'] = sum(table.rowViewportPosition(i)>=0 and table.rowViewportPosition(i)+table.rowHeight(i)<=table.viewport().height() for i in range(table.rowCount()))
        info['table_size'] = table.size().toTuple()
        info['main_plot_geometry_before_details'] = before
        info['main_plot_geometry_after_details'] = dialog.hkl_plot_panel.geometry().getRect()
        info['tab_geometries'] = {}
        d.export_shell_csv(out/(name+'.csv'),dialog.diagnostics)
        dialog.hkl_figure.savefig(out/(name+'-plot.png'),dpi=120)
        if hasattr(dialog,'hkl_plot_tabs'):
            for index in range(1,dialog.hkl_plot_tabs.count()):
                dialog.hkl_plot_tabs.setCurrentIndex(index)
                for _ in range(15): app.processEvents()
                info['tab_geometries'][dialog.hkl_plot_tabs.tabText(index)] = dict(plot=dialog.hkl_plot_panel.geometry().getRect(),table=table.size().toTuple())
                suffix = '-overlap' if dialog.hkl_plot_tabs.tabText(index)=='Peak overlap' else '-derived'
                dialog.grab().save(str(out/(name+suffix+'.png')))
                if hasattr(dialog,'hkl_plot_figures'):
                    dialog.hkl_plot_figures[index].savefig(out/(name+suffix+'-plot.png'),dpi=120)
            if presentation and 'restricted' in name and hasattr(dialog,'hkl_chart_scroll'):
                dialog.hkl_plot_tabs.setCurrentIndex(0)
                for _ in range(15):app.processEvents()
                dialog.hkl_canvas.draw()
                dialog.hkl_chart_scroll.verticalScrollBar().setValue(dialog.hkl_chart_scroll.verticalScrollBar().maximum())
                for _ in range(15):app.processEvents()
                info['chart_scroll_bottom'] = dict(
                    position=dialog.hkl_chart_scroll.verticalScrollBar().value(),
                    maximum=dialog.hkl_chart_scroll.verticalScrollBar().maximum(),
                    canvas_height=dialog.hkl_canvas.height(),
                    label_bottom_pixels={key: axis.xaxis.label.get_window_extent(dialog.hkl_canvas.get_renderer()).y0
                                         for key,axis in dialog.hkl_axes.items()})
                dialog.grab().save(str(out/(name+'-charts-bottom.png')))
    dialog.diagnostics.export_json(out/(name+'.json'))
    records[name] = info
    dialog.close()


def fixture(name,rows,mode):
    path = work/(name+'.hkl')
    path.write_text(rows,encoding='utf8')
    metadata = a.CrystalMetadata(a.gemmi.UnitCell(10,12,14,90,96,90),a.gemmi.SpaceGroup('P 1 21/n 1'),'P 1 21/n 1','','manual',None)
    load = a.build_hkl_load_result(a.HklAnalysisRequest('external',str(path),'','',str(work),mode,metadata))
    load = replace(load,source_note='SYNTHETIC CONTROLLED FIXTURE — '+name)
    load.diagnostics = d.build_diagnostics(load)
    return load


def analysis(load):
    return a.analyze_hkl_data(load.hkl_path,load.data_mode,load.cell,load.spacegroup,load.spacegroup_hm,load.source_note,_loaded=load)


real = a.build_hkl_load_result(a.build_hkl_analysis_request_from_inflip(Path('C:/Users/honzi/Documents/ochlor/ochlor_Superflip.inflip'),work_dir=work/'ochlor'))
capture('01-real-ochlor-validation',win._build_hkl_validation_dialog(real),height=780)
x = analysis(real)
capture('02-real-ochlor-completeness-constant-fwhm',win._build_hkl_completeness_dialog(x))
capture('03-real-ochlor-advanced-overlap-unavailable',win._build_hkl_completeness_dialog(x),advanced=True)
capture('04-real-ochlor-narrow',win._build_hkl_completeness_dialog(x),width=760,height=800)
single = fixture('amplitudes-with-zero-phase', '\n'.join(f'{h} {k} 1 {abs(h*k)+2} 0 1.2' for h in range(1,9) for k in range(1,7)),a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA)
capture('05-synthetic-single-crystal-validation',win._build_hkl_validation_dialog(single),height=780)
capture('06-synthetic-single-crystal-derived-significance',win._build_hkl_completeness_dialog(analysis(single)))
variable = fixture('variable-width-powder','\n'.join(f'{h} {k} 1 {abs(h*k)+2} {0.04+0.002*h}' for h in range(1,9) for k in range(1,7)),a.REFLECTION_DATA_MODE_INTENSITY_FWHM)
capture('07-synthetic-variable-fwhm',win._build_hkl_completeness_dialog(analysis(variable)))
overlapping = fixture('known-unit-overlap-powder','\n'.join(f'{h} {k} 1 {abs(h*k)+2} 1.0' for h in range(1,9) for k in range(1,7)),a.REFLECTION_DATA_MODE_INTENSITY_FWHM)
overlapping.diagnostics = d.build_diagnostics(overlapping,fwhm_units='degrees_2theta',wavelength=1.0,separation_factor=1.0)
assert dict(overlapping.diagnostics.overlap)['group_count']>0
capture('08-synthetic-estimated-overlap',win._build_hkl_completeness_dialog(analysis(overlapping)),advanced=True)
warnings = fixture('symmetry-duplicates-invalid-values','0 1 0 10 .05\n0 2 0 -3 .05\n1 0 0 5 .05\n1 0 0 7 .05\n2 0 1 nan -1\n',a.REFLECTION_DATA_MODE_INTENSITY_FWHM)
capture('09-synthetic-symmetry-warnings',win._build_hkl_validation_dialog(warnings),advanced=True)
large_request = a.build_hkl_analysis_request_from_inflip(Path('C:/Users/honzi/Documents/flipovani-phase-studio/2int3total.inflip'),work_dir=work/'2int3total')
large = a.build_hkl_load_result(large_request)
capture('10-real-2int3total-validation',win._build_hkl_validation_dialog(large),height=800)
capture('11-real-2int3total-completeness',win._build_hkl_completeness_dialog(d.cached_analysis(large_request)))
if presentation:
    capture('12-real-2int3total-details-open',win._build_hkl_completeness_dialog(d.cached_analysis(large_request)),advanced=True)
    capture('13-real-ochlor-restricted-height',win._build_hkl_completeness_dialog(x),height=700,advanced=True)
    capture('14-synthetic-overlap-restricted-height',win._build_hkl_completeness_dialog(analysis(overlapping)),height=700,advanced=True)
    capture('15-real-2int3total-restricted-height',win._build_hkl_completeness_dialog(d.cached_analysis(large_request)),height=700,advanced=True)
(out/'geometry.json').write_text(json.dumps(records,indent=2),encoding='utf8')
win.timer.stop()
win.close()
print(out)
