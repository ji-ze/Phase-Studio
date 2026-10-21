"""Explicit, reproducible packaging experiments; no application runtime policy."""
import os
from pathlib import Path

VARIANTS={
    'baseline':frozenset(),
    'without-qtvscodestyle':frozenset({'style'}),
    'without-qt-translations':frozenset({'translations'}),
    'without-mpl-sample-data':frozenset({'samples'}),
    'combined-safe':frozenset({'style','translations','samples'}),
    'without-qt-quick-experimental':frozenset({'style','translations','samples','quick'}),
}


def options():
    name=os.environ.get('PHASE_STUDIO_PACKAGING_VARIANT','combined-safe')
    if name not in VARIANTS:raise ValueError('Unknown packaging variant: '+name)
    return VARIANTS[name]


def configure_qt():
    """Trim collection before Analysis/bindepend, never delete deployed DLLs.

    PyInstaller 6.20's Qt helper exposes module translation lists and plugin
    collection. Fail on a changed helper contract rather than silently ignoring
    these requested exclusions. Existing post-analysis safety filters remain.
    """
    selected=options()
    if not selected.intersection({'translations','quick'}):return
    from PyInstaller.utils.hooks.qt import pyside6_library_info as info
    if 'translations' in selected:
        for entry in [*info.python_modules.values(),*info.shared_libraries.values()]:entry.translations=[]
    if 'quick' in selected:
        original=info.collect_plugins
        def collect(plugin_type):
            # This already-excluded plugin is the root of the unused QML graph.
            return [(source,dest) for source,dest in original(plugin_type)
                if Path(source).name.lower()!='qtvirtualkeyboardplugin.dll']
        info.collect_plugins=collect


def custom_hooks(directory):
    return [str(Path(directory)/'hooks')] if 'samples' in options() else []
