"""Actual Qt gestures and rendered axes, never a stored-angle-only check."""
import os,sys,tempfile,hashlib
from pathlib import Path
from unittest.mock import patch
ROOT=Path(os.environ.get('PS207_GUI_SOURCE',Path(__file__).resolve().parents[1]));sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint,QSettings
from PySide6.QtTest import QTest
from phase_studio import app as a
import test_jana_completion as fixture

settings=tempfile.TemporaryDirectory()
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,settings.name)
qt=QApplication([]);a.apply_phase_studio_style(qt)
def events():
    for _ in range(8):qt.processEvents()
def angles(axis):return tuple(round(float(getattr(axis,k)),7) for k in ('elev','azim','roll'))
with patch.multiple(a.IterativeSuperflipPipelineQtGUI,load_settings=lambda self:None,
                   save_settings=lambda self:None,refresh_sharped_models=lambda self:None):
    window,results=fixture.build_window(a)
window.timer.stop();window.results=results
atoms=a.parse_cif_atoms(Path(results[0].superflip_edma_cif))
for role,attribute in [('reference','reference_atoms_for_plot'),('superflip','superflip_atoms_for_plot'),('deblur','deblur_atoms_for_plot')]:
    setattr(window,attribute,list(atoms))
# Exercise the real RunConfig path with Map Feedback off, not just the resolver.
source=Path(results[0].superflip_edma_cif).parent/'ochlor.inflip'
source.write_text('cell 10 10 10 90 90 90\nspacegroup P1\ncomposition C2\ndataformat intensity fwhm\nfbegin\n1 0 0 10 .1\nendf\n')
source.with_suffix('.m90').write_text('lambda 1.541866\nend\n')
original_path=window._path_value;original_combo=window._combo_value
with patch.object(window,'_path_value',side_effect=lambda key: str(source) if key=='jana_inflip' else ('' if key in ('hkl','reference_cif','first_cycle_modelfile') else original_path(key))),patch.object(window,'_combo_value',side_effect=lambda key: a.INPUT_MODE_INFLIP if key=='input_source_mode' else original_combo(key)),patch.object(window,'_resolve_crystal_metadata_from_inputs',return_value=window.last_run_config.crystal_metadata):
    window.inputs['redistribute_overlaps'].setChecked(False)
    cfg=window.get_config()
    assert not cfg.redistribute_overlaps and cfg.powder_wavelength==1.541866
    assert 'ochlor.m90' in cfg.wavelength_source
    assert a.powder_superflip_keywords('',cfg.powder_wavelength)=='lambda 1.541866'
# Missing wavelength opens the editable setting, not an executable picker.
report=a.ErrorReport('input_validation','input','Wavelength missing','Superflip FWHM requires wavelength','','')
actions=window._error_actions(report)
assert [action.label for action in actions]==['Set measured wavelength']
actions[0].callback()
window.resize(1600,1050);window._update_structure_views();window.show();events();window.resize(1600,1050);events();window.structure_canvas.draw()
initial_paths={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in {Path(r.superflip_edma_cif) for r in results}}
for index in range(3):
    axes=window._structure_interactive_axes;canvas=window.structure_canvas
    for axis in axes:axis.view_init(elev=23,azim=41,roll=17)
    canvas.draw();box=axes[index].get_window_extent();ratio=canvas.device_pixel_ratio
    p=QPoint(int((box.x0+box.width*.4)/ratio),int((canvas.figure.bbox.height-box.y0-box.height*.5)/ratio))
    before=angles(axes[index]);limits=[window._structure_axis_limits(axis) for axis in axes]
    QTest.mousePress(canvas,Qt.LeftButton,Qt.NoModifier,p)
    for dx,dy in [(12,8),(27,19),(42,26)]:QTest.mouseMove(canvas,p+QPoint(dx,dy),30);events()
    QTest.mouseRelease(canvas,Qt.LeftButton,Qt.NoModifier,p+QPoint(42,26));events()
    if os.environ.get('PS207_GUI_CAPTURE'):
        import json
        folder=Path(os.environ['PS207_GUI_CAPTURE']);folder.mkdir(parents=True,exist_ok=True)
        window.grab().save(str(folder/f'drag-panel-{index}.png'))
        (folder/f'drag-panel-{index}.json').write_text(json.dumps([angles(axis) for axis in axes]))
    assert angles(axes[index])!=before,'Qt drag did not rotate active rendered axis'
    assert len({angles(axis) for axis in axes})==1,('Rendered panels diverged',index,[angles(axis) for axis in axes])
    assert [window._structure_axis_limits(axis) for axis in axes]==limits,'Rotation changed local limits'
    expected=angles(axes[index]);window._update_structure_views();events()
    assert all(angles(axis)==expected for axis in window._structure_interactive_axes),'Result refresh reset camera'
label=window.structure_metadata_labels[0]
label.setStyleSheet('font-size: 18pt');label.setText('Composition: '+('C123 N45 O67 S89 · independent heavy ASU sites · '*8));events()
need=label.fontMetrics().height()+(label.text().count('\n'))*label.fontMetrics().lineSpacing()
if os.environ.get('PS207_GUI_CAPTURE'):window.grab().save(str(Path(os.environ['PS207_GUI_CAPTURE'])/'metadata.png'))
assert label.contentsRect().height()>=need,('Metadata clipped',label.height(),need)
assert label.toolTip() and label.accessibleName()
assert all(hashlib.sha256(p.read_bytes()).hexdigest()==value for p,value in initial_paths.items())
window.close();events();print('Actual Qt drag, rendered roll/orientation, refresh and metadata passed.')
