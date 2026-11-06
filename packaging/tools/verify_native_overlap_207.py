"""Read completed native evidence, check every group, then execute corrected inputs.

No inference or historical reconstruction is run. New 20-cycle CF checks are explicit. Original pilots stay read-only.
The independent table extraction below does not call the application's parser.
"""
import argparse,csv,hashlib,json,math,subprocess,sys
from dataclasses import replace
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from phase_studio import app as a
from phase_studio.native_overlap import capture_native_overlap,native_powder_keywords

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def independent_table(log):
    block=log.split('Reflections read from the input file and averaged:')[1].split('Maximum indices in expanded reflection set:')[0]
    result={}
    for line in block.splitlines():
        fields=line.split()
        if fields and fields[0].endswith(':') and fields[0][:-1].isdigit():
            key=tuple(map(int,fields[1:4]))
            assert key not in result
            result[key]=int(fields[-1])
    return result

def verify(pilots,evidence,native,out):
    out.mkdir(parents=True,exist_ok=False);report=[]
    for name in ('selexipag','ochlor'):
        original=pilots/name;folder=evidence/name
        observed=original/'observed.hkl';source=original/'pilot.inflip'
        hashes={str(p):sha(p) for p in (observed,source)}
        cell,sg,hm,composition=a.parse_inflip_crystallography(source)
        context=a.ReferenceContext(source,source,cell,sg,hm,composition,[])
        wave=float(a.parse_inflip_settings(source)['powder_wavelength'])
        inp=folder/'grouping.inflip';log=folder/'grouping.sflog'
        authority=capture_native_overlap(inp,log,observed,native)
        rows=a.read_hkl(observed);groups=authority.groups_for(rows,cell,wave,.2)
        independent=independent_table(log.read_text())
        assert dict(authority.membership)==independent
        estimate=a.assign_powder_overlap_groups(rows,cell,wave,.2)
        target=out/name;target.mkdir()
        with (target/'membership.csv').open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['h','k','l','native_group','execution_group','estimated_group','FWHM_deg_2theta'])
            writer.writerows((r.h,r.k,r.l,independent[(r.h,r.k,r.l)],groups.get((r.h,r.k,r.l),0),estimate.get((r.h,r.k,r.l),0),r.sigma) for r in rows)
        cases=[]
        for mode in (a.REFLECTION_DATA_MODE_INTENSITY_FWHM,a.REFLECTION_DATA_MODE_AMPLITUDE_FWHM):
            for mix in (0,.25,1):
                case=target/(('I' if mode==a.REFLECTION_DATA_MODE_INTENSITY_FWHM else 'F')+'-'+str(mix));case.mkdir()
                before=rows if mode==a.REFLECTION_DATA_MODE_INTENSITY_FWHM else [replace(r,value=math.sqrt(r.value)) for r in rows]
                after,_=a.redistribute_overlap_reflections(before,mode,folder/'grouping.xplor',cell,wave,.2,mix,lambda _:None,native_grouping=authority)
                corrected=case/'corrected.hkl';assert a.write_observed_reflections(corrected,after,0,mode)==len(rows)
                written=a.read_hkl(corrected);errors=[];serialized_errors=[]
                for gid in set(groups.values()):
                    indexes=[i for i,r in enumerate(rows) if groups.get((r.h,r.k,r.l))==gid]
                    old=sum(a.reflection_value_as_intensity(before[i],mode) for i in indexes)
                    new=sum(a.reflection_value_as_intensity(after[i],mode) for i in indexes)
                    disk=sum(a.reflection_value_as_intensity(written[i],mode) for i in indexes)
                    assert math.isclose(new,old,rel_tol=1e-12,abs_tol=1e-9),(name,mode,mix,gid,old,new)
                    # Seven decimal-place output: exact rounding bound for each I or F^2.
                    bound=sum(5.000001e-8 if mode==a.REFLECTION_DATA_MODE_INTENSITY_FWHM else 2*abs(after[i].value)*5.000001e-8+(5.000001e-8)**2 for i in indexes)
                    assert abs(disk-new)<=bound+abs(new)*2e-15,(gid,disk,new,bound)
                    errors.append(abs(new-old));serialized_errors.append(abs(disk-old))
                assert [r.sigma for r in written]==[r.sigma for r in rows]
                next_input=case/'next.inflip'
                a.write_superflip_input(inp_path=next_input,prefix='next',ref_ctx=context,observed_hkl=corrected,
                    model_file=None,output_xplor='grouping.xplor',reference_file=None,reference_format='cif',
                    perform_algorithm='CF',output_format='xplor',write_auxiliary_outputs=False,
                    export_superflip_xplor=True,export_superflip_ccp4=False,export_superflip_jana=False,
                    voxel='0.5',bestdensities_count=1,bestdensities_metric='symmetry',bestdensities_symmetry=True,
                    polish=False,maxcycles=20,repeatmode=1,randomseed='12345',delta='AUTO',weakratio='0',biso='0',
                    reflection_data_mode=mode,normalize='none',nresshells=1,missing='zero',searchsymmetry='no',
                    derivesymmetry='no',electrons='',dataitemwidths='auto',
                    extra_superflip_keywords=native_powder_keywords('',wave,.2),log=None)
                try:
                    result=subprocess.run([str(native.resolve()),next_input.name],cwd=case,capture_output=True,timeout=60,input=b'\n',creationflags=subprocess.CREATE_NO_WINDOW)
                except subprocess.TimeoutExpired as error:
                    (case/'timeout-output.txt').write_bytes((error.stdout or b'')+(error.stderr or b''))
                    raise
                (case/'stdout.txt').write_bytes(result.stdout+result.stderr)
                assert result.returncode==0 and (case/'grouping.xplor').is_file()
                next_authority=capture_native_overlap(next_input,case/'next.sflog',corrected,native)
                assert dict(next_authority.membership)==independent
                import numpy as np
                assert np.isfinite(a.read_xplor_map(case/'grouping.xplor').data).all()
                cases.append(dict(mode=mode,mix=mix,groups_checked=len(errors),records_written=len(written),max_group_error=max(errors),max_serialized_group_error=max(serialized_errors),native_next_CF_exit=result.returncode,native_next_membership_equal=True,input_sha256=sha(next_input),map_sha256=sha(case/'grouping.xplor')))
        assert all(sha(Path(p))==value for p,value in hashes.items())
        report.append(dict(dataset=name,records=len(rows),groups=len(set(groups.values())),members=len(groups),exact_native_membership=True,estimated_members=len(estimate),original_hashes=hashes,originals_unchanged=True,cases=cases))
    (out/'report.json').write_text(json.dumps(report,indent=2))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('pilots','evidence','native','output'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();print(json.dumps(verify(args.pilots,args.evidence,args.native,args.output),indent=2))
