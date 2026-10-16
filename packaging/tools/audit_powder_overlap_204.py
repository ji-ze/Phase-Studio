import os
"""Local executable comparisons only; no phasing, network or project writes."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from phase_studio import app as a
from phase_studio.powder_diagnostics import superflip_overlap_groups

OUT=ROOT/'build/powder-final/parity'
OUT.mkdir(parents=True,exist_ok=True)
EXE=Path('C:/Jana2020/SUPERFLIP/superflip.exe')

def compare(name,rows,cell,wavelength,factor=.2, symmetry='x1 x2 x3',extra='',explicit=None):
    folder=OUT/name;folder.mkdir(exist_ok=True)
    header=f'''title read-only diagnostic comparison {name}
perform fourier
dimension 3
cell {' '.join(str(v) for v in cell.parameters)}
symmetry
{symmetry}
endsymmetry
reflectionlist unique
expandedlog yes
outputformat xplor
outputfile diagnostic.xplor
lambda {wavelength}
{extra}
'''
    if factor is not None: header+=f'fwhmseparation {factor}\n'
    header+='dataformat intensity phase '+('group' if explicit is not None else 'fwhm')+'\nfbegin\n'
    text=header+'\n'.join(f'{r.h:4d}{r.k:4d}{r.l:4d}{r.value:15.7f}{0:15.7f}{(explicit.get((r.h,r.k,r.l),0) if explicit is not None else r.sigma):15.7f}' for r in rows)+'\nendf\n'
    (folder/'diagnostic.inflip').write_text(text)
    p=subprocess.run([str(EXE),'diagnostic.inflip'],cwd=folder,capture_output=True,timeout=60)
    (folder/'stdout.txt').write_bytes(p.stdout+p.stderr)
    log=(folder/'diagnostic.sflog').read_text(errors='replace')
    membership={}
    for line in log.splitlines():
        m=re.match(r'^\s*\d+:\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(.+)$',line)
        if m:
            fields=m[4].split()
            # Input/averaged table ends with array location and group ID.
            if len(fields) in (4,5): membership[tuple(map(int,m.group(1,2,3)))]=int(fields[-1]) if len(fields)==5 else 0
    assert len(membership)==len(rows),(name,len(membership),len(rows))
    expected=explicit if explicit is not None else superflip_overlap_groups(rows,cell,wavelength,.2 if factor is None else factor)
    def components(groups):
        return {frozenset(key for key,val in groups.items() if val==group) for group in set(groups.values()) if group>0}
    observed=components(membership);ours=components(expected)
    assert observed==ours,(name,observed^ours)
    return dict(records=len(rows),overlap_groups=len(ours),affected=sum(map(len,ours)),membership_equal=True,wavelength=wavelength,separation_factor=.2 if factor is None else factor)

def main():
    results={}
    cell=a.gemmi.UnitCell(10,10,10,90,90,90)
    for name,width,wave,factor in [('separated',.001,1,.2),('identical',.1,1,.2),('transitive',7,1,1),('variable',1,1,.5),('wavelength',1,1.7,.5),('default',.1,1,None)]:
        hkls=[(1,0,0),(0,1,0),(2,0,0),(3,0,0),(3,1,0),(3,2,0)]
        if name=='separated':hkls=hkls[::2]
        rows=[a.Reflection(*h,100.,width*(i+1) if name=='variable' else width) for i,h in enumerate(hkls)]
        results[name]=compare(name,rows,cell,wave,factor)
    rows=[a.Reflection(1,0,0,100.,None),a.Reflection(2,0,0,100.,None),a.Reflection(3,0,0,100.,None)]
    results['explicit']=compare('explicit',rows,cell,1,explicit={(1,0,0):5,(2,0,0):5,(3,0,0):0})
    source=Path(os.environ.get('PHASE_STUDIO_TEST_INFLIP', str(ROOT / 'build/powder-final/wizard-input/ochlor_Superflip.inflip')))
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    request=a.build_hkl_analysis_request_from_inflip(source,work_dir=OUT/'load')
    load=a.build_hkl_load_result(request)
    context=load.powder_diagnostic_context
    symmetry='\n'.join(op.triplet().replace('x','x1').replace('y','x2').replace('z','x3') for op in load.spacegroup.operations())
    results['ochlor']=compare('ochlor',load.reflections,load.cell,context['wavelength'],context['separation_factor'],symmetry=symmetry)
    results['ochlor']['diagnostics']=dict(load.diagnostics.overlap)
    assert before==hashlib.sha256(source.read_bytes()).hexdigest()
    results['executable_sha256']=hashlib.sha256(EXE.read_bytes()).hexdigest()
    results['source_sha256']=before
    (OUT/'report.json').write_text(json.dumps(results,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in results.items() if k!='ochlor'},indent=2))
    print('ochlor:',{k:v for k,v in results['ochlor'].items() if k!='diagnostics'})

if __name__=='__main__':main()
