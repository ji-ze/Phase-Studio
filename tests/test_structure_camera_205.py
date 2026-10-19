"""Projected direct manipulation and immutable rendering geometry, offline Qt."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication,QWidget
from mpl_toolkits.mplot3d import proj3d
from phase_studio import structure_camera as camera
from phase_studio.fullscreen_viewer import SingleStructureViewerWindow

@pytest.fixture
def viewer(tmp_path):
    owns_application=QApplication.instance() is None
    app=QApplication.instance() or QApplication([])
    settings=QSettings(str(tmp_path/'camera.ini'),QSettings.IniFormat)
    owner=QWidget();owner.show()
    points=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]])
    data={'atoms':[SimpleNamespace(element='C',label=str(i)) for i in range(3)],'coords':points,
          'bonds':[(0,1),(0,2)],'cell_segments':[],'title':'Controlled camera fixture'}
    with patch.object(camera,'QSettings',lambda *args:settings):
        window=SingleStructureViewerWindow(owner,'fixture',lambda:data,color_for=lambda e:'#ce6677')
        window.resize(1000,700);window.show();window.activateWindow()
        for _ in range(12):app.processEvents()
        window.canvas.draw()
        yield window, settings, data
        window.close();owner.close();window.deleteLater();owner.deleteLater()
        from PySide6.QtCore import QCoreApplication,QEvent
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        if owns_application:
            import shiboken6
            shiboken6.delete(app)

def pixel(axis,point):
    x,y,_=proj3d.proj_transform(*point,axis.get_proj())
    return axis.transData.transform((x,y))


def test_camera_menu_palette_and_sensitivity_are_visual_preferences(viewer):
    window,settings,data=viewer
    from PySide6.QtWidgets import QToolButton
    from phase_studio.app import element_color
    before=data['coords'].copy()
    menu=next(b for b in window.findChildren(QToolButton) if b.text()=='Camera').menu()
    sensitivity=next(a.menu() for a in menu.actions() if a.text()=='Rotation sensitivity')
    next(a for a in sensitivity.actions() if 'Fast' in a.text()).trigger()
    assert float(settings.value('viewer/rotationSensitivity'))==2.
    axis=window.figure.axes[0]
    window._camera._press(SimpleNamespace(inaxes=axis,button=1,key='',x=300,y=300,dblclick=False))
    assert window._camera._drag['sensitivity']==2.
    window._camera._release(None)
    palette=next(a.menu() for a in menu.actions() if a.text()=='Element colors')
    next(a for a in palette.actions() if 'CPK' in a.text()).trigger()
    try:
        assert element_color('C')=='#808080' and element_color('N')=='#3050F8'
        assert element_color('O')=='#FF0D0D' and element_color('Cl')=='#1FF01F'
        assert np.array_equal(data['coords'],before)
        assert settings.value('viewer/elementPalette')=='cpk'
    finally:next(a for a in palette.actions() if 'Current' in a.text()).trigger()

@pytest.mark.parametrize('dx,dy',[(30,0),(-30,0),(0,30),(0,-30),(25,-25)])
def test_front_features_follow_projected_drag(viewer,dx,dy):
    window,settings,data=viewer
    axis=window.figure.axes[0]
    origin=np.mean([[*axis.get_xlim3d()],[*axis.get_ylim3d()],[*axis.get_zlim3d()]],axis=1)
    feature=origin+camera.camera_basis(axis.elev,axis.azim,axis.roll)[2]*.3
    before=pixel(axis,feature)
    rect=axis.get_position(original=True).transformed(axis.figure.transFigure)
    x,y=rect.x0+rect.width/2,rect.y0+rect.height/2
    window._camera._press(SimpleNamespace(inaxes=axis,button=1,key='',x=x,y=y,dblclick=False))
    window._camera._motion(SimpleNamespace(x=x+dx,y=y+dy))
    window._camera._release(None)
    after=pixel(axis,feature)
    if dx: assert (after[0]-before[0])*dx>0
    if dy: assert (after[1]-before[1])*dy>0
    assert window._camera._drag is None

def test_matrix_adapter_survives_poles_and_wraparound():
    for elev in (-90,-89.999,0,89.999,90):
        for azim in (-720,-179,0,179,720):
            for roll in (-170,0,123):
                basis=camera.camera_basis(elev,azim,roll)
                angles=camera.camera_angles(basis)
                np.testing.assert_allclose(camera.camera_basis(*angles),basis,atol=1e-9)
                assert np.linalg.det(basis)==pytest.approx(1)

def test_coalescing_inversion_artist_reuse_and_final_position(viewer):
    window,settings,data=viewer
    axis=window.figure.axes[0];original=data['coords'].copy()
    collections=tuple(map(id,axis.collections))
    button=camera.camera_settings_button(window)
    button.menu().actions()[0].setChecked(True)
    assert settings.value('viewer/invertMouseRotation',type=bool)
    calls=[];callback=window._camera._orientation_changed
    window._camera._orientation_changed=lambda *args:(calls.append(args),callback(*args))
    rect=axis.get_position(original=True).transformed(axis.figure.transFigure)
    x,y=rect.x0+rect.width/2,rect.y0+rect.height/2
    initial=camera.camera_basis(axis.elev,axis.azim,axis.roll)
    center=np.array([np.mean(axis.get_xlim3d()),np.mean(axis.get_ylim3d()),np.mean(axis.get_zlim3d())])
    feature=center+initial[2]*.3
    before=pixel(axis,feature)
    window._camera._press(SimpleNamespace(inaxes=axis,button=1,key='',x=x,y=y,dblclick=False))
    for i in range(500):window._camera._motion(SimpleNamespace(x=x+i*.1,y=y))
    assert calls==[]
    window._camera._release(None)
    assert len(calls)==1
    assert pixel(axis,feature)[0]<before[0]
    assert not window._camera.allow_auto_rotation()
    for _ in range(10):window.render()
    assert tuple(map(id,axis.collections))==collections and window.figure.axes[0] is axis
    np.testing.assert_array_equal(data['coords'],original)
    window.hide();window._camera._last_input=-float('inf')
    assert not window._camera.allow_auto_rotation()

@pytest.mark.parametrize('button,key',[(3,''),(2,''),(1,'shift')])
def test_pan_zoom_release_outside_and_fit(viewer,button,key):
    window,settings,data=viewer;axis=window.figure.axes[0]
    initial=axis.get_xlim3d()
    window._camera._press(SimpleNamespace(inaxes=axis,button=button,key=key,x=400,y=350,dblclick=False))
    window._camera._motion(SimpleNamespace(x=430,y=365))
    window._camera._release(SimpleNamespace(inaxes=None))
    assert axis.get_xlim3d()!=initial and window._camera._drag is None
    span=np.ptp(axis.get_xlim3d())
    window._camera._scroll(SimpleNamespace(inaxes=axis,step=1))
    assert np.ptp(axis.get_xlim3d())<span
    window._camera._press(SimpleNamespace(inaxes=axis,button=1,key='',x=400,y=350,dblclick=True))
    assert np.isfinite(axis.get_proj()).all()

def test_periodic_boundary_and_special_position_preserve_files(tmp_path):
    from phase_studio.autosolve_window import prepare_structure_presentation
    from test_result_selection_viewer import cif_text
    path=tmp_path/'boundary.cif'
    text=cif_text('C2','C','C').replace('P -1','P 1').replace('0.10 0.10 0.10','0.96 0.10 0.10').replace('0.20 0.10 0.10','0.04 0.10 0.10')
    path.write_text(text,encoding='utf8');before=path.read_bytes()
    data=prepare_structure_presentation(path,'molecule')
    assert len(data['bonds'])==1 and len(data['atoms'])==2
    a,b=data['bonds'][0]
    assert np.linalg.norm(data['coords'][a]-data['coords'][b])==pytest.approx(.8)
    assert path.read_bytes()==before
    special=tmp_path/'special.cif'
    special.write_text(cif_text('C','C','C').replace('A1 C 0.10 0.10 0.10','A1 C 0 0 0').replace('B1 C 0.20 0.10 0.10',''),encoding='utf8')
    full=prepare_structure_presentation(special,'cell')
    assert len(full['atoms'])==1 and len(full['cell_segments'])==12

def test_multiple_unwraps_and_separate_molecules(tmp_path):
    from phase_studio.autosolve_window import prepare_structure_presentation
    from test_result_selection_viewer import cif_text
    header=cif_text('C','C','C').replace('P -1','P 1').split('A1 C')[0]
    for name,rows,bonds,count in (
        ('chain','A1 C .84 .1 .1\nB1 C .96 .1 .1\nC1 C .08 .1 .1\n',2,3),
        ('separate','A1 C .10 .1 .1\nB1 C .22 .1 .1\nC1 C .60 .1 .1\nD1 C .72 .1 .1\n',2,4),
    ):
        path=tmp_path/(name+'.cif');path.write_text(header+rows,encoding='utf8');before=path.read_bytes()
        data=prepare_structure_presentation(path,'molecule')
        assert len(data['atoms'])==count and len(data['bonds'])==bonds
        for i,j in data['bonds']:
            assert np.linalg.norm(data['coords'][i]-data['coords'][j])==pytest.approx(1.2)
        assert path.read_bytes()==before

def test_manual_pause_keeps_auto_preference_and_repeated_rotations(viewer):
    window,settings,data=viewer;axis=window.figure.axes[0]
    window.auto_rotate_button.click()
    rect=axis.get_position(original=True).transformed(axis.figure.transFigure)
    x,y=rect.x0+rect.width/2,rect.y0+rect.height/2
    for index in range(80):
        window._camera._press(SimpleNamespace(inaxes=axis,button=1,key='',x=x,y=y,dblclick=False))
        window._camera._motion(SimpleNamespace(x=x+18,y=y+8))
        before=(axis.elev,axis.azim,axis.roll)
        window._rotate_camera()
        assert (axis.elev,axis.azim,axis.roll)==before
        window._camera._release(None)
        assert np.linalg.det(camera.camera_basis(axis.elev,axis.azim,axis.roll))==pytest.approx(1)
    assert window.auto_rotate_button.isChecked()
    window.hide()
    assert not window._rotation_timer.isActive()
