"""Guard the narrow packaging experiment boundaries, not scientific algorithms."""
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('_distribution_options',ROOT/'packaging/pyinstaller/distribution_options.py')
options=importlib.util.module_from_spec(spec);spec.loader.exec_module(options)


def test_default_contains_only_verified_low_risk_exclusions(monkeypatch):
    monkeypatch.delenv('PHASE_STUDIO_PACKAGING_VARIANT',raising=False)
    assert options.options()=={'style','translations','samples'}


def test_each_low_risk_experiment_is_independent(monkeypatch):
    for name,expected in [('baseline',set()),('without-qtvscodestyle',{'style'}),('without-qt-translations',{'translations'}),('without-mpl-sample-data',{'samples'})]:
        monkeypatch.setenv('PHASE_STUDIO_PACKAGING_VARIANT',name)
        assert options.options()==expected
    monkeypatch.setenv('PHASE_STUDIO_PACKAGING_VARIANT','unsupported')
    with pytest.raises(ValueError):options.options()


def test_qt_collection_excludes_only_already_disabled_keyboard(monkeypatch):
    from PyInstaller.utils.hooks import qt
    from types import SimpleNamespace
    entry=SimpleNamespace(translations=['qtbase'])
    fake=SimpleNamespace(python_modules={'QtCore':entry},shared_libraries={'qt6core':entry},collect_plugins=lambda kind:[
        ('C:/Qt/qtvirtualkeyboardplugin.dll',kind),('C:/Qt/qwindows.dll',kind),('C:/Qt/qsvg.dll',kind)])
    monkeypatch.setattr(qt,'pyside6_library_info',fake)
    monkeypatch.setenv('PHASE_STUDIO_PACKAGING_VARIANT','without-qt-translations');options.configure_qt()
    assert entry.translations==[] and len(fake.collect_plugins('platforms'))==3
    monkeypatch.setenv('PHASE_STUDIO_PACKAGING_VARIANT','without-qt-quick-experimental');options.configure_qt()
    assert [Path(p).name for p,_ in fake.collect_plugins('platforms')]==['qwindows.dll','qsvg.dll']


def test_matplotlib_fonts_and_public_image_formats_remain():
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    assert {'png','pdf','svg','avif'}<=FigureCanvasAgg.get_supported_filetypes().keys()
    source=(ROOT/'packaging/pyinstaller/hooks/hook-matplotlib.py').read_text()
    assert "excludes=['mpl-data/sample_data/**']" in source
    assert 'fonts/**' not in source and 'stylelib/**' not in source
    for path in ('superflip.spec','packaging/pyinstaller/PhaseStudio.spec'):
        source=(ROOT/path).read_text()
        assert 'configure_qt()' in source and 'custom_hooks(' in source
        assert 'opengl32sw.dll' not in source
