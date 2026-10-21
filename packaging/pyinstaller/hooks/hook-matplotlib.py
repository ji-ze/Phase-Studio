"""Keep the installed upstream hook, narrowing only its sample-data collection."""
from pathlib import Path
import runpy
import PyInstaller
from PyInstaller.utils.hooks import collect_data_files

upstream=Path(PyInstaller.__file__).parent/'hooks/hook-matplotlib.py'
authority=runpy.run_path(str(upstream))
binaries=authority.get('binaries',[])
datas=[]
for source,destination in authority.get('datas',[]):
    if destination.replace('\\','/')=='matplotlib/mpl-data':
        datas+=collect_data_files('matplotlib',includes=['mpl-data/**'],excludes=['mpl-data/sample_data/**'])
    else:datas.append((source,destination))
