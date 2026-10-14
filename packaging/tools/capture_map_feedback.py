"""Capture actual 2.0.3 Map Feedback widgets without executing a workflow.

Optional PHASE_STUDIO_TEST_INFLIP is copied locally before parsing. All other
inputs and scientific executables below are explicitly synthetic fixtures.
Run separate processes at QT_SCALE_FACTOR=1, 1.25 and 1.5.
"""
import os
import sys
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication,QDialog
from phase_studio.ui_style import apply_phase_studio_style
from phase_studio import jana_superflip as js

work=ROOT/'build/map-feedback-capture'
work.mkdir(parents=True,exist_ok=True)
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(work/'settings'))
tools=work/'JanaActive/SUPERFLIP'
tools.mkdir(parents=True,exist_ok=True)
(tools/'superflip.exe').write_bytes(b'not executable; UI resolution fixture only')
(tools/'EDMA.exe').write_bytes(b'not executable; UI resolution fixture only')
js.application_dir=lambda:tools.parent
app=QApplication([])
apply_phase_studio_style(app)
QDialog.exec=lambda self:QDialog.Rejected
source=os.environ.get('PHASE_STUDIO_TEST_INFLIP')
def fixture(name,mode,rows):
    path=work/name
    path.write_text('title feedback_fixture\nperform CF\noutputformat xplor\ndimension 3\n'
        'cell 10 10 10 90 90 90\nspacegroup P1\ncomposition C2\n'
        f'dataformat {mode}\nfbegin\n'+rows+'\nendf\n',encoding='utf8')
    return path
if source:
    original=Path(source)
    powder=work/original.name
    powder.write_bytes(original.read_bytes())
    if original.with_suffix('.m90').is_file():
        powder.with_suffix('.m90').write_bytes(original.with_suffix('.m90').read_bytes())
else:
    powder=fixture('powder-fixture.inflip','intensity fwhm','1 0 0 10 .1\n0 1 0 20 .1')
intensity=fixture('measured-intensity-fixture.inflip','intensity','1 0 0 10 2\n0 1 0 20 5')
amplitude=fixture('measured-amplitude-fixture.inflip','amplitude','1 0 0 4 1\n0 1 0 6 2')
out=ROOT/'build/map-feedback-2.0.3'/('scale-'+os.environ.get('QT_SCALE_FACTOR','1'))
out.mkdir(parents=True,exist_ok=True)
def wizard(path):
    w=js._JanaWorkflowWizard([],path)
    w.run()
    w.dialog.show()
    for _ in range(20):app.processEvents()
    models=['PEAK A (model prediction)','SEED (cyclic CF)']
    w.model.clear();w.model.addItems(models)
    w.model_catalog['values']=tuple(models);w.model_cache['loaded']=True
    w.workflow_state['key']=js.WORKFLOW_SUPERFLIP_SHARPED
    w.cycles.setValue(3)
    w.model_policy_error=''
    w._go_to_map_feedback()
    w._adjust_dialog_size=lambda:None
    return w
def capture(w,name,height=820):
    w.dialog.resize(900,height)
    for _ in range(10):app.processEvents()
    w._size_stack_to_current_page(w.dialog.width())
    w.scroll_area.verticalScrollBar().setValue(0)
    for _ in range(10):app.processEvents()
    assert w.dialog.grab().save(str(out/(name+'.png')))
    print(name,'size',w.dialog.size().toTuple(),'scroll',w.scroll_area.verticalScrollBar().maximum(),
        'format',w.reflection_format_value.text(),'sigma',w.feedback_has_uncertainty,flush=True)
w=wizard(powder)
w.cycles.setValue(1);w.model_policy_error=''
capture(w,'01-powder-one-cycle')
w.cycles.setValue(3);w.model_policy_error=''
capture(w,'02-powder-three-cycles')
w.powder_enabled_checkbox.setChecked(True)
capture(w,'03-powder-enabled-auto-wavelength')
w.powder_enabled_checkbox.setChecked(False)
w.intensity_enabled_checkbox.setChecked(True);w.intensity_damping_spin.setValue(.5)
capture(w,'05-powder-no-sigma-zero-mode')
w.powder_enabled_checkbox.setChecked(True)
if w._map_feedback_wavelength()[0]<=0:
    # An explicitly entered demonstration wavelength for the synthetic fixture.
    w.powder_wavelength_spin.setValue(1.)
capture(w,'06-both-enabled')
capture(w,'08-expanded-short',height=580)
w.dialog.close()
w=wizard(intensity)
w.intensity_enabled_checkbox.setChecked(True)
w.intensity_damping_spin.setValue(.5);w.intensity_sigma_spin.setValue(3.)
capture(w,'04-measured-intensity-sigma')
w.dialog.close()
w=wizard(amplitude)
w.intensity_enabled_checkbox.setChecked(True)
w.intensity_damping_spin.setValue(.5);w.intensity_sigma_spin.setValue(3.)
capture(w,'07-single-crystal-amplitude-sigma')
w.dialog.close()
