"""Frozen source, legal-byte and four-scale real-widget acceptance; no API jobs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import types

ROOT=Path(__file__).resolve().parents[2]


def normalized(code):
    if isinstance(code,types.CodeType):
        return code.replace(co_filename='<source>',co_consts=tuple(normalized(c) for c in code.co_consts))
    if isinstance(code,tuple):return tuple(normalized(v) for v in code)
    return code


def verify_source(executable):
    from PyInstaller.archive.readers import CArchiveReader
    archive=CArchiveReader(str(executable)).open_embedded_archive('PYZ.pyz')
    names=[n for n in archive.toc if n=='phase_studio' or n.startswith('phase_studio.')]
    for name in names:
        path=ROOT/Path(*name.split('.'))
        path=path.with_suffix('.py') if path.with_suffix('.py').is_file() else path/'__init__.py'
        if not path.is_file():raise ValueError('Bundled module has no reviewed source: '+name)
        expected=compile(path.read_text(encoding='utf8'),str(path),'exec',dont_inherit=True)
        if normalized(archive.extract(name))!=normalized(expected):raise ValueError('Bundled source mismatch: '+name)
    required={'phase_studio.app','phase_studio.native_overlap','phase_studio.about_ui','phase_studio.input_analysis_ui'}
    if not required<=set(names):raise ValueError('Required application modules missing.')
    return len(names)


def clean_environment():
    env=dict(os.environ)
    for key in tuple(env):
        if key.upper().startswith(('PYTHON','QT_','PHASE_STUDIO_')):env.pop(key)
    windows=Path(os.environ.get('SystemRoot','C:/Windows'))
    env.update(PATH=str(windows/'System32')+os.pathsep+str(windows),QT_QPA_PLATFORM='offscreen',
               QT_QPA_FONTDIR=str(windows/'Fonts'),PHASE_STUDIO_STARTUP_PROBE='1')
    return env


def verify_profile(executable,output):
    executable=Path(executable).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    modules=verify_source(executable);scales=[]
    for scale in ('1','1.25','1.5','2'):
        target=output/('scale-'+scale)
        env=clean_environment()|{'QT_SCALE_FACTOR':scale,'PHASE_STUDIO_INPUT_UI_ACCEPTANCE':'1'}
        run=subprocess.run([str(executable),'--packaging-acceptance',str(target)],env=env,cwd=output,
            capture_output=True,text=True,timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
        (output/('scale-'+scale+'-process.txt')).write_text(run.stdout+'\n'+run.stderr,encoding='utf8')
        report=json.loads((target/'report.json').read_text(encoding='utf8'))
        if run.returncode or not report.get('passed') or not report.get('frozen'):raise ValueError('Frozen GUI acceptance failed: '+scale)
        if any(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest for name,digest in report['legal_file_sha256'].items()):
            raise ValueError('Frozen legal bytes differ from reviewed source.')
        scales.append(report)
    result=dict(passed=True,source_modules_verified=modules,scales=scales,physical_display_acceptance=False)
    (output/'profile.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--standalone',type=Path,required=True);parser.add_argument('--jana',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(verify_profile,exe,args.output/name) for name,exe in (('standalone',args.standalone),('jana',args.jana))]
        results=[job.result() for job in jobs]
    (args.output/'frozen-gui.json').write_text(json.dumps(dict(passed=True,profiles=results),indent=2),encoding='utf8')


if __name__=='__main__':main()
