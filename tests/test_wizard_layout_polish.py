"""Actual Qt layout, interaction and metadata guards in isolated DPI processes."""
from pathlib import Path
import os,sys,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def run_checks():
 from PySide6.QtCore import Qt,QPoint,QSettings
 from PySide6.QtWidgets import QApplication,QDialog,QLabel,QHBoxLayout
 from PySide6.QtTest import QTest
 from phase_studio.ui_style import apply_phase_studio_style
 from phase_studio import jana_superflip as js
 from test_wizard_text_clipping import write_inflip
 app=QApplication([]);apply_phase_studio_style(app)
 with tempfile.TemporaryDirectory() as tmp:
  base=Path(tmp);source=write_inflip(base);original=source.read_bytes()
  jana=base/'Jana';(jana/'SUPERFLIP').mkdir(parents=True)
  for name in ('superflip.exe','EDMA.exe'):(jana/'SUPERFLIP'/name).write_bytes(b'active scientific executable')
  js.application_dir=lambda:jana
  QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,tmp)
  imports=js._qt_imports
  js._qt_imports=lambda:imports()|{'QSettings':lambda org,name:QSettings(str(base/(name+'.ini')),QSettings.IniFormat)}
  QDialog.exec=lambda self:QDialog.Rejected
  w=js._JanaWorkflowWizard([str(source)],source);w.run();w._adjust_dialog_size=lambda:None;w.dialog.show()
  def settle():
   for _ in range(20):app.processEvents()
   w._size_stack_to_current_page(w.dialog.width())
   for _ in range(20):app.processEvents()
  settle();metadata=[getattr(w,n).text() for n in ('reflections_value','format_value','cell_value','spacegroup_value','composition_value')]
  assert metadata[0]=='432 HKL records · 432 unique indices'
  assert 'not symmetry-independent' in w.reflections_value.toolTip()
  from phase_studio.scientific_typography import scientific_text
  assert metadata[2].count('<td ')==6 and metadata[2].count('<tr>')==2
  for text in ('a = 24.352 Å','b = 35.561 Å','c = 26.032 Å','alpha = 90°','beta = 91.02°','gamma = 90°'):
   assert scientific_text(text).replace(' ','&nbsp;') in metadata[2]
  assert w.data_type_value.text()=='Single crystal'
  assert metadata[3]=='P2\u2081/n (#14)' and metadata[4]=='Ag₁₂₄ S₈₈ B₇₆₈ H₇₀₄ O₄₀'
  tiles=(w.original_superflip_tile,w.superflip_sharped_tile,w.autosolve_tile,w.professional_mode_tile)
  for width,height in ((900,850),(900,1000),(900,820),(821,780),(820,850),(900,580),(640,850)):
   w.dialog.resize(width,height);settle();w.scroll_area.verticalScrollBar().setValue(0);settle()
   viewport=w.scroll_area.viewport();footer=w.footer.mapTo(w.dialog,QPoint()).y()
   assert viewport.mapTo(w.dialog,QPoint()).y()+viewport.height()<=footer
   assert not w.scroll_area.isAncestorOf(w.cancel_button) and w.cancel_button.isVisible()
   assert w.scroll_area.horizontalScrollBar().maximum()==0
   for pair in (tiles[:2],tiles[2:]):assert pair[0].height()==pair[1].height()
   for tile in tiles:
    assert tile.rect().contains(tile.icon_label.geometry()) and tile.rect().contains(tile.chevron_label.geometry())
    for label in (tile.title_label,tile.subtitle_label,tile.secondary_label,tile.runtime_label):
     if not label.isVisible():continue
     need=max(label.fontMetrics().height(),label.heightForWidth(label.width()) if label.wordWrap() else label.fontMetrics().height())
     assert label.height()>=need,(tile.title_label.text(),label.text(),label.size().toTuple(),need)
    assert tile.subtitle_label.alignment() & Qt.AlignTop
   if height>=780 and width>=820:
    assert w.scroll_area.verticalScrollBar().maximum()==0,(width,height,w.scroll_area.verticalScrollBar().maximum(),w.input_summary_section.height(),w.input_summary_outer.direction(),w.input_summary_columns.direction(),w.summary_wide_minimum_width)
    for tile in tiles:
     p=tile.mapTo(viewport,QPoint());assert viewport.rect().contains(p) and viewport.rect().contains(p+QPoint(tile.width()-1,tile.height()-1))
   if height==580:
    assert w.scroll_area.verticalScrollBar().maximum()>0
    before=w.footer.geometry();w.scroll_area.verticalScrollBar().setValue(w.scroll_area.verticalScrollBar().maximum());settle();assert w.footer.geometry()==before
   for button in (w.validate_hkl_button,w.analyze_completeness_button):assert button.isEnabled() and button.height()>=36
   assert w.validate_hkl_button.width()==w.analyze_completeness_button.width()
   assert metadata==[getattr(w,n).text() for n in ('reflections_value','format_value','cell_value','spacegroup_value','composition_value')]
  w.dialog.resize(900,850);settle();size=w.dialog.size()
  assert tiles[2].height()==tiles[3].height() and tiles[2].height()>=94
  w.files_toggle.click();settle();assert w.files_form_widget.isVisible() and w.dialog.size()==size
  w.files_toggle.click();settle();assert not w.files_form_widget.isVisible() and w.scroll_area.verticalScrollBar().maximum()==0
  assert w.backing_window_holder['win'] is None
  calls=[]
  class Diagnostics:
   def test_hkl_load_dialog(self):calls.append('validate')
   def open_hkl_completeness_dialog(self):calls.append('completeness')
  w._get_backing_window=lambda:Diagnostics()
  w.validate_hkl_button.click();w.analyze_completeness_button.click();assert calls==['validate','completeness']
  tile=tiles[0];tile._on_click=lambda:calls.append('activate')
  tile.setFocus(Qt.TabFocusReason);QTest.keyClick(tile,Qt.Key_Space);assert calls[-1]=='activate'
  QTest.qWait(360);QTest.mouseClick(tile,Qt.LeftButton,pos=tile.rect().center());assert calls.count('activate')==2
  assert tile.hasFocus()
  w.inflip_info.full_text='Jana2020 input: '+('very_long_name_'*80)+'.inflip';w.inflip_info.setAccessibleName(w.inflip_info.full_text)
  w.dialog.resize(820,850);settle();assert w.inflip_info.width()<=w.content.width()
  assert w.inflip_info.accessibleName().endswith('.inflip')
  w.cancel_button.click();assert not w.dialog.isVisible()
  assert source.read_bytes()==original
 print('Workflow polish geometry, metadata, diagnostic controls, disclosure, mouse, keyboard and Cancel passed.')

def test_workflow_polish_dpi():
 for scale in ('1','1.25','1.5'):
  result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child'],cwd=ROOT,env=os.environ|{'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':scale},capture_output=True,text=True,timeout=60)
  assert result.returncode==0,f'Scale {scale}: {result.stdout}\n{result.stderr}'

if __name__=='__main__':
 if '--child' in sys.argv:run_checks()
 else:test_workflow_polish_dpi();print('All three DPI profiles passed.')
