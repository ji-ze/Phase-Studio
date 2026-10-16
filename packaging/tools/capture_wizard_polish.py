"""Capture real Wizard widgets and logical geometry; no scientific execution."""
import os,sys,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QPoint,QSettings
from PySide6.QtWidgets import QApplication,QDialog
from PySide6.QtTest import QTest
from phase_studio.ui_style import apply_phase_studio_style
from phase_studio import jana_superflip as js
if '--baseline' in sys.argv:
 import subprocess,types
 baseline=types.ModuleType('phase_studio._wizard_before_polish')
 baseline.__file__=js.__file__
 sys.modules[baseline.__name__]=baseline
 code=subprocess.check_output(['git','show','HEAD:phase_studio/jana_superflip.py'],cwd=ROOT).decode('utf8')
 exec(compile(code,js.__file__,'exec'),baseline.__dict__)
 js=baseline
app=QApplication([]);apply_phase_studio_style(app)
settings=tempfile.TemporaryDirectory();QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,settings.name)
QDialog.exec=lambda self:QDialog.Rejected
js.application_dir=lambda:Path('C:/Jana2020/SharpED')
source=ROOT/'build/oauth-2.0.4-ochlor-run/ochlor.inflip'
w=js._JanaWorkflowWizard([],source if source.exists() else None);w.run();w._adjust_dialog_size=lambda:None
w.dialog.show()
def settle():
 for _ in range(20):app.processEvents()
 w._size_stack_to_current_page(w.dialog.width())
 for _ in range(20):app.processEvents()
settle()
scale=os.environ.get('QT_SCALE_FACTOR','1');phase=sys.argv[1] if len(sys.argv)>1 else 'after'
out=ROOT/'docs/screenshots/2.0.4-wizard-polish'/phase/f'scale-{scale}';out.mkdir(parents=True,exist_ok=True)
data={}
def capture(name,width=900,height=850):
 w.dialog.resize(width,height);settle();w.scroll_area.verticalScrollBar().setValue(0);settle()
 tiles=(w.original_superflip_tile,w.superflip_sharped_tile,w.autosolve_tile,w.professional_mode_tile)
 viewport=w.scroll_area.viewport()
 def visible(tile):
  p=tile.mapTo(viewport,QPoint());return viewport.rect().contains(p) and viewport.rect().contains(p+QPoint(tile.width()-1,tile.height()-1))
 data[name]={'dialog_logical':w.dialog.size().toTuple(),'device_pixel_ratio':w.dialog.devicePixelRatioF(),'screen_available_logical':w.dialog.screen().availableGeometry().size().toTuple(),'summary_height':w.input_summary_section.height(),'page_height':w.page1.height(),'content_height':w.content.height(),'viewport_height':viewport.height(),'scroll_maximum':w.scroll_area.verticalScrollBar().maximum(),'card_sizes':[t.size().toTuple() for t in tiles],'cards_fully_visible':[visible(t) for t in tiles],'footer_top':w.footer.y(),'summary':{k:getattr(w,k).text() for k in ('reflections_value','format_value','cell_value','spacegroup_value','composition_value')}}
 assert w.dialog.grab().save(str(out/f'{name}.png'))
capture('normal');capture('reference-900x820',height=820);capture('default-desktop',width=821,height=780)
w.files_toggle.setChecked(True);capture('optional-expanded');w.files_toggle.setChecked(False)
for name,tile in [('hover-superflip',w.original_superflip_tile),('hover-sharped',w.superflip_sharped_tile)]:
 QTest.mouseMove(tile,tile.rect().center());capture(name)
QTest.mouseMove(w.brand_header);w.original_superflip_tile.setFocus(Qt.TabFocusReason);capture('keyboard-focus')
capture('reduced-height',height=580);capture('narrow',width=640)
(out/'geometry.json').write_text(json.dumps(data,indent=2),encoding='utf8')
print(json.dumps({'phase':phase,'scale':scale,'normal':data['normal'],'narrow':data['narrow']},ensure_ascii=True))
w.dialog.close()
