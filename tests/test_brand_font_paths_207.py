"""Real Qt font loading from Unicode and MAX_PATH-exceeding installations."""
import os
from pathlib import Path
import pytest

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
_application=None


@pytest.mark.parametrize('long_path',[False,True])
def test_bundled_face_loads_from_unicode_installation(tmp_path,monkeypatch,long_path):
    global _application
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontInfo
    from phase_studio import ui_branding as branding
    _application=QApplication.instance() or QApplication([])
    folder=tmp_path/'žluťoučký 密度'
    if long_path:
        while len(str(folder/'ScienceGothic-Variable.ttf'))<=310:
            folder=folder/('installation '+('x'*40))
        if os.name=='nt':folder=Path('\\\\?\\'+str(folder.absolute()))
    folder.mkdir(parents=True)
    target=folder/'ScienceGothic-Variable.ttf'
    target.write_bytes(branding.SCIENCE_GOTHIC_ASSET.read_bytes())
    monkeypatch.setattr(branding,'SCIENCE_GOTHIC_ASSET',target)
    monkeypatch.setattr(branding,'_science_gothic_font_id',None)
    monkeypatch.setattr(branding,'_science_gothic_families',())
    families=branding.register_science_gothic_font()
    assert 'Science Gothic' in families, 'Bundled face was not actually registered from the Unicode installation.'
    assert QFontInfo(branding.phase_studio_brand_font()).family()=='Science Gothic'
    assert not long_path or len(str(target))>260
