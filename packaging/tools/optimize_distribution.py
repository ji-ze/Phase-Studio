"""Isolated, repeatable packaging experiments on one immutable source snapshot."""
from pathlib import Path
import argparse,csv,ctypes,hashlib,json,os,shutil,subprocess,sys,time

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'build/optimization-internal/r2'
SOURCE=ROOT/'build/o26b'
VARIANTS=('baseline','without-qtvscodestyle','without-qt-translations','without-mpl-sample-data','combined-safe','without-qt-quick-experimental')


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def snapshot():
    if SOURCE.exists():raise ValueError('Snapshot already exists; never replace it silently.')
    OUT.mkdir(parents=True,exist_ok=True);SOURCE.mkdir()
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    extra=subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    paths=sorted(set(p for p in tracked+extra if p and not p.startswith(('docs/workshop/','.git/'))))
    hashes={}
    for relative in paths:
        source=ROOT/relative
        if not source.is_file():continue
        dest=SOURCE/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest);hashes[relative]=digest(dest)
    environment=subprocess.check_output([sys.executable,'-c',"import json,sys,importlib.metadata as m; print(json.dumps(dict(python=sys.version,packages={p:m.version(p) for p in ['PyInstaller','PySide6','numpy','matplotlib','gemmi','cryptography']})))"],text=True)
    record=dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        status=subprocess.check_output(['git','status','--porcelain=v1'],cwd=ROOT,text=True),environment=json.loads(environment),files=hashes)
    (OUT/'source-snapshot.json').write_text(json.dumps(record,indent=2),encoding='utf8')


def measure(directory):
    files=[p for p in directory.rglob('*') if p.is_file()];runtime=directory/'_internal';inner=[p for p in runtime.rglob('*') if p.is_file()]
    return dict(total_bytes=sum(p.stat().st_size for p in files),internal_bytes=sum(p.stat().st_size for p in inner),
        total_files=len(files),internal_files=len(inner),internal_directories=sum(p.is_dir() for p in runtime.rglob('*')),
        dll_pyd=sum(p.suffix.lower() in ('.dll','.pyd') for p in inner),qt_plugins=sum('/PySide6/plugins/' in p.as_posix() and p.suffix=='.dll' for p in inner),
        manifest={p.relative_to(directory).as_posix():dict(bytes=p.stat().st_size,sha256=digest(p)) for p in files})


class MemoryCounters(ctypes.Structure):
    _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong),*[(name,ctypes.c_size_t) for name in
        ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]]


def probe(exe,directory,*,scale='1',startup=False,native=True):
    directory.mkdir(parents=True,exist_ok=False)
    env=os.environ.copy();env.update(QT_QPA_PLATFORM='windows' if native else 'offscreen',QT_SCALE_FACTOR=scale,
        PHASE_STUDIO_STARTUP_PROBE='1',PHASE_STUDIO_ACCEPTANCE_STARTUP_ONLY='1' if startup else '0',
        MPLCONFIGDIR=str(directory.parent/'isolated-matplotlib-cache'))
    for key in list(env):
        if any(word in key.upper() for word in ('TOKEN','SECRET','SIGNING_KEY')):env.pop(key)
    log=(directory/'process.log').open('w',encoding='utf8');start=time.perf_counter()
    process=subprocess.Popen([str(exe),'--packaging-acceptance',str(directory)],env=env,cwd=directory,stdout=log,stderr=subprocess.STDOUT)
    ready=None;peak=0;deadline=time.monotonic()+100
    sys.path.insert(0,str(ROOT))
    from phase_studio.update_windows import process_entries,ProcessGuard
    memory=ctypes.WinDLL('psapi').GetProcessMemoryInfo
    memory.argtypes=[ctypes.c_void_p,ctypes.POINTER(MemoryCounters),ctypes.c_ulong];memory.restype=ctypes.c_int
    while process.poll() is None:
        if ready is None:
            entries=process_entries();owned={process.pid}
            for _ in range(4):owned.update(pid for pid,(parent,_name) in entries.items() if parent in owned)
            current=0
            for pid in owned:
                try:
                    with ProcessGuard(pid) as guard:
                        counters=MemoryCounters();counters.cb=ctypes.sizeof(counters)
                        if memory(guard.handle,ctypes.byref(counters),counters.cb):current+=counters.PeakWorkingSetSize
                except Exception:pass
            peak=max(peak,current)
            visible=directory/'visible.json'
            if visible.exists():
                try:ready=json.loads(visible.read_text());ready['wall_to_visible_seconds']=time.perf_counter()-start
                except json.JSONDecodeError:pass
        if time.monotonic()>deadline:raise TimeoutError('Frozen acceptance exceeded its bound; inspect the owned process log.')
        time.sleep(.025)
    log.close()
    report=json.loads((directory/'acceptance.json').read_text(encoding='utf8'))
    result=dict(returncode=process.returncode,ready=ready,peak_startup_working_set_bytes=peak,report=report)
    (directory/'measurement.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    if process.returncode or not report.get('ok'):raise ValueError('Frozen acceptance failed: '+str(directory))
    return result


def build(variant,*,standalone=False):
    record=json.loads((OUT/'source-snapshot.json').read_text())
    for relative,sha in record['files'].items():
        if digest(SOURCE/relative)!=sha:raise ValueError('Source snapshot changed: '+relative)
    case=OUT/variant
    if (case/'metrics.json').exists():raise ValueError('Variant already measured; keep its evidence.')
    case.mkdir(exist_ok=True)
    # Keep extraction beneath MAX_PATH even for long upstream license names.
    # Public-facing named copies are made with extended Windows paths below.
    short=dict(zip(VARIANTS,('b','a','t','m','c','q')))[variant]
    dist=SOURCE/'dist'/short
    if dist.exists():raise ValueError('Variant output already exists; never replace an accepted artifact.')
    env=os.environ.copy();env['PATH']=str(ROOT/'.venv-build/Scripts')+os.pathsep+env['PATH'];env['PHASE_STUDIO_PACKAGING_VARIANT']=variant
    with (case/'build.log').open('a',encoding='utf8') as log:
        log.write('\nControlled build destination: '+str(dist)+'\n');log.flush()
        result=subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','packaging/build_windows.ps1',
            '-Target','All' if standalone else 'JanaDeveloper','-DistRoot',str(dist)],cwd=SOURCE,env=env,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError('Variant build failed: '+variant)
    version='2.0.6';product=dist/f'PhaseStudio-Jana2020-{version}'
    metrics=measure(product);metrics.update(variant=variant,build_output=str(dist),source_commit=record['commit'],source_snapshot_sha256=digest(OUT/'source-snapshot.json'),
        zip_bytes=(dist/'release'/f'PhaseStudio-Jana2020-{version}.zip').stat().st_size,variant_environment=variant,cold_start='not measured; Windows filesystem cache not flushed')
    (case/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf8')
    # Preserve the analysis proving why files were collected before the next run.
    for name in ('Analysis-00.toc','PYZ-00.toc','COLLECT-00.toc','warn-PhaseStudioJanaDeveloper.txt','xref-PhaseStudioJanaDeveloper.html'):
        p=SOURCE/'build/PhaseStudioJanaDeveloper'/name
        if p.exists():shutil.copyfile(p,case/name)
    first=probe(product/'Phase_studio.exe',case/'native-first',native=True)
    warm=[probe(product/'Phase_studio.exe',case/('warm-'+str(i)),startup=True,native=True) for i in range(5)]
    metrics['native_first']=first;metrics['warm_starts']=warm
    for scale in ('1','1.25','1.5'):probe(product/'Phase_studio.exe',case/('dpi-'+scale),scale=scale,native=False)
    if standalone:
        exe=dist/'release'/f'PhaseStudio-{version}-x64.exe'
        metrics['standalone_bytes']=exe.stat().st_size
        metrics['standalone_native']=probe(exe,case/'standalone-native',native=True)
        for scale in ('1','1.25','1.5'):probe(exe,case/('standalone-dpi-'+scale),scale=scale,native=False)
        with (case/'frozen-updater.log').open('w',encoding='utf8') as log:
            subprocess.run([sys.executable,'packaging/tools/verify_update_build.py','--dist',str(dist),'--version',version],cwd=SOURCE,stdout=log,stderr=subprocess.STDOUT,check=True)
    (case/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf8')
    output=ROOT/'dist/optimization-2.0.6'/OUT.name/variant
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise ValueError('Named variant destination already exists; refuse replacement.')
    destination='\\\\?\\'+str(output) if os.name=='nt' else output
    shutil.copytree(dist,destination)
    print(variant,'PASS',metrics['internal_files'],metrics['internal_bytes'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--snapshot',action='store_true');parser.add_argument('--variant',choices=VARIANTS);parser.add_argument('--all',action='store_true')
    parser.add_argument('--snapshot-root',type=Path);parser.add_argument('--evidence-root',type=Path)
    args=parser.parse_args()
    if args.snapshot_root:SOURCE=args.snapshot_root.resolve()
    if args.evidence_root:OUT=args.evidence_root.resolve()
    if not SOURCE.is_relative_to(ROOT/'build') or not OUT.is_relative_to(ROOT/'build'):
        raise ValueError('Snapshot and evidence roots must stay under repository build.')
    if args.snapshot:snapshot()
    if args.all:
        for variant in VARIANTS:build(variant,standalone=variant in ('baseline','combined-safe'))
    elif args.variant:build(args.variant,standalone=args.variant in ('baseline','combined-safe'))
