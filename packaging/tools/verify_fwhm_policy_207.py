"""Read-only historical inventory and local native compatibility; no inference."""
import argparse,csv,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import gemmi
from phase_studio import app as a

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def native_case(executable,out,mode,uncertainty_free=False):
    folder=out/(mode.replace(' ','_').replace('/','_')+('_no_sigma' if uncertainty_free else ''));folder.mkdir(parents=True,exist_ok=True)
    rows=[a.Reflection(h,k,l,value,None if uncertainty_free else .1,90. if a.reflection_mode_has_phase(mode) else None)
          for h,k,l,value in [(1,0,0,10),(0,1,0,12),(0,0,1,8),(1,1,0,0),(1,0,1,.01)]]
    observed=folder/'observed.hkl';a.write_observed_reflections(observed,rows,0,mode)
    if a.reflection_mode_has_phase(mode):
        rows[-1].phase=None
        a.write_observed_reflections(observed,rows,0,mode)
    cell=gemmi.UnitCell(10,11,12,90,90,90)
    context=a.ReferenceContext(folder/'ref.cif',folder/'work.cif',cell,gemmi.SpaceGroup('P 1'),'P 1','C2 O1',[])
    inp=folder/'check.inflip'
    a.write_superflip_input(inp_path=inp,prefix='check',ref_ctx=context,observed_hkl=observed,
        model_file=None,output_xplor='check.xplor',reference_file=None,reference_format='cif',
        perform_algorithm='fourier',output_format='xplor',write_auxiliary_outputs=False,
        export_superflip_xplor=True,export_superflip_ccp4=False,export_superflip_jana=False,
        voxel='0.5',bestdensities_count=1,bestdensities_metric='symmetry',bestdensities_symmetry=True,
        polish=False,maxcycles=1,repeatmode=1,randomseed='12345',delta='AUTO',weakratio='0',biso='0',
        reflection_data_mode=mode,normalize='none',nresshells=1,missing='zero',searchsymmetry='no',
        derivesymmetry='no',electrons='',dataitemwidths='auto',
        extra_superflip_keywords='lambda 1.0' if a.reflection_mode_has_fwhm(mode) else '',log=None)
    completed=subprocess.run([str(executable.resolve()),inp.name],cwd=folder,capture_output=True,timeout=30)
    (folder/'stdout.txt').write_bytes(completed.stdout+completed.stderr)
    assert completed.returncode==0,(mode,completed.returncode,completed.stdout.decode(errors='replace'))
    assert (folder/'check.xplor').is_file(),mode
    parsed=a.read_xplor_map(folder/'check.xplor')
    import numpy as np
    assert np.isfinite(parsed.data).all(),mode
    return dict(mode=mode,uncertainty_free=uncertainty_free,exit_code=completed.returncode,
        executable_sha256=digest(executable),input_sha256=digest(inp),map_sha256=digest(folder/'check.xplor'),
        note='Controlled Fourier compatibility check only; not a rerun of the recorded reconstruction.')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path);parser.add_argument('--native',type=Path)
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True);report={}
    if args.run:
        run=args.run.resolve()
        assert out!=run and run not in out.parents,'Output must be outside the original run'
        protected={p:digest(p) for p in run.rglob('*') if p.is_file()}
        mode=a.REFLECTION_DATA_MODE_INTENSITY_FWHM
        original=a.read_hkl(run/'cycle_001_superflip_embedded_reflections.hkl')
        old=a.read_hkl(run/'observed_unique_for_superflip.hkl');old_keys={(r.h,r.k,r.l) for r in old}
        corrected=a.filtered_reflections(original,mode,0)
        restored=[r for r in corrected if (r.h,r.k,r.l) not in old_keys]
        a.write_observed_reflections(out/'corrected_initial.hkl',original,0,mode)
        with (out/'formerly_excluded.csv').open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['h','k','l','I','FWHM_deg_2theta','new_status'])
            writer.writerows((r.h,r.k,r.l,r.value,r.sigma,'retained finite nonnegative intensity and valid measured width') for r in restored)
        report['historical']=dict(original=len(original),legacy_written=len(old),corrected_written=len(corrected),
            formerly_excluded_restored=len(restored),restored_zero=sum(r.value==0 for r in restored),
            restored_positive=sum(r.value>0 for r in restored),corrected_threshold=0,
            historical_effective_threshold='Unavailable; legacy ratio cutoff 2 reproduces the saved HKL set but is not independently serialized.',
            uncertainty='None supplied: fifth field is FWHM',
            unchanged_original_files=all(p.is_file() and digest(p)==value for p,value in protected.items()),
            protected_files=len(protected),reconstruction_rerun=False)
        assert report['historical']['unchanged_original_files']
    if args.native:
        modes=[a.REFLECTION_DATA_MODE_INTENSITY,a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
            a.REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA,a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA,
            a.REFLECTION_DATA_MODE_INTENSITY_FWHM,a.REFLECTION_DATA_MODE_AMPLITUDE_FWHM]
        report['native']=[native_case(args.native,out/'native',mode) for mode in modes]
        report['native'].append(native_case(args.native,out/'native',modes[0],True))
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
