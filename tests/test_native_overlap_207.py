"""Actual native membership is the execution oracle, not count matching."""
from pathlib import Path
from dataclasses import replace
import hashlib
import json
import math
import re
import subprocess
import numpy as np
import pytest
from phase_studio import app as a
from phase_studio.native_overlap import (native_powder_keywords,parse_native_membership,
    capture_native_overlap)

EXE=Path('C:/Jana2020/SUPERFLIP/superflip.exe')


def write_native_fixture(inp,observed,cell,factor):
    context=a.ReferenceContext(inp,inp,cell,a.gemmi.SpaceGroup('P 1'),'P 1','C1',[])
    # Use a supported, seeded phase-retrieval calculation, not a handwritten
    # unphased Fourier input. All membership/conservation assertions stay exact.
    a.write_superflip_input(inp_path=inp,prefix='native',ref_ctx=context,observed_hkl=observed,
        model_file=None,output_xplor='native.xplor',reference_file=None,reference_format='cif',
        perform_algorithm='CF',output_format='xplor',write_auxiliary_outputs=False,
        export_superflip_xplor=True,export_superflip_ccp4=False,export_superflip_jana=False,
        voxel='0.5',bestdensities_count=1,bestdensities_metric='symmetry',bestdensities_symmetry=True,
        polish=False,maxcycles=20,repeatmode=1,randomseed='12345',delta='AUTO',weakratio='0',biso='0',
        reflection_data_mode=a.REFLECTION_DATA_MODE_INTENSITY_FWHM,normalize='none',nresshells=1,
        missing='zero',searchsymmetry='no',derivesymmetry='no',electrons='',dataitemwidths='auto',
        extra_superflip_keywords=native_powder_keywords('',1,factor),log=None)


@pytest.fixture
def native(tmp_path):
    if not EXE.is_file():pytest.skip('Installed native Superflip required for independent executable acceptance.')
    rows=[a.Reflection(1,0,0,0,.1),a.Reflection(0,1,0,25,.1),a.Reflection(2,0,0,1e6,.1)]
    observed=tmp_path/'observed.hkl'
    a.write_observed_reflections(observed,rows,0,a.REFLECTION_DATA_MODE_INTENSITY_FWHM)
    inp=tmp_path/'native.inflip'
    write_native_fixture(inp,observed,a.gemmi.UnitCell(10,10,10,90,90,90),.2)
    result=subprocess.run([str(EXE),inp.name],cwd=tmp_path,capture_output=True,timeout=30)
    assert result.returncode==0 and (tmp_path/'native.xplor').is_file(),result.stdout
    authority=capture_native_overlap(inp,tmp_path/'native.sflog',observed,EXE)
    return authority,rows,tmp_path,a.gemmi.UnitCell(10,10,10,90,90,90)


def test_factor_propagation_is_unique_and_preserves_other_keywords():
    extra='lambda .5\nfwhmseparation .7\nexpandedlog no\nterminal no'
    result=native_powder_keywords(extra,1.541866,.3)
    assert result.splitlines()==['lambda 1.541866','terminal no','fwhmseparation 0.3','expandedlog yes']
    for factor in (0,-1,float('nan'),float('inf')):
        with pytest.raises(ValueError):native_powder_keywords('',1,factor)


def test_membership_matches_independent_native_records(native):
    authority,rows,folder,cell=native
    # Independent extraction by the literal table's columns, not the app parser.
    table=(folder/'native.sflog').read_text().split('Reflections read from the input file and averaged:')[1].split('Maximum indices')[0]
    expected={tuple(map(int,fields[1:4])):int(fields[-1]) for line in table.splitlines()
              if (fields:=line.split()) and fields[0].rstrip(':').isdigit()}
    assert dict(authority.membership)==expected
    assert authority.groups_for(rows,cell,1,.2)=={(1,0,0):1,(0,1,0):1}
    assert authority.provenance()['estimate_used'] is False


@pytest.mark.parametrize('mode',[a.REFLECTION_DATA_MODE_INTENSITY_FWHM,a.REFLECTION_DATA_MODE_AMPLITUDE_FWHM])
@pytest.mark.parametrize('mix',[0,.25,1])
def test_native_groups_conserve_serialized_I_or_squared_F(native,mode,mix):
    authority,rows,folder,cell=native
    if mode==a.REFLECTION_DATA_MODE_AMPLITUDE_FWHM:
        rows=[replace(r,value=math.sqrt(r.value)) for r in rows]
    # This actual seeded native CF map supplies real predictions.
    output,_=a.redistribute_overlap_reflections(rows,mode,folder/'native.xplor',cell,1,.2,mix,lambda _:None,native_grouping=authority)
    observed=folder/'corrected.hkl'
    assert a.write_observed_reflections(observed,output,0,mode)==3
    written=a.read_hkl(observed)
    intensity=lambda r:r.value*r.value if mode==a.REFLECTION_DATA_MODE_AMPLITUDE_FWHM else r.value
    assert sum(intensity(r) for r in written[:2])==pytest.approx(25,rel=0,abs=1.1e-6)
    assert intensity(written[2])==1e6
    assert [r.sigma for r in written]==[r.sigma for r in rows]


@pytest.mark.parametrize('change',['cell','wavelength','factor','width','indices','log','input','observed'])
def test_native_authority_rejects_stale_or_mismatched_metadata(native,change):
    authority,rows,folder,cell=native
    wave,factor=1,.2
    if change=='cell':cell=a.gemmi.UnitCell(10,10,11,90,90,90)
    elif change=='wavelength':wave=1.1
    elif change=='factor':factor=.3
    elif change=='width':rows=[replace(rows[0],sigma=.11)]+rows[1:]
    elif change=='indices':rows=rows[:-1]
    else:
        path=folder/{'log':'native.sflog','input':'native.inflip','observed':'observed.hkl'}[change]
        path.write_text(path.read_text()+'\n# changed after calculation\n')
    with pytest.raises(ValueError):authority.groups_for(rows,cell,wave,factor)


def test_incomplete_duplicate_and_unsupported_tables_fail(native):
    authority,rows,folder,cell=native
    source=(folder/'native.sflog').read_text()
    with pytest.raises(ValueError):parse_native_membership(source.replace('ArrayLocation','UnknownColumn'))
    with pytest.raises(ValueError):parse_native_membership(source+source)
    with pytest.raises(ValueError):parse_native_membership(source.split('Maximum indices in expanded reflection set:')[0])
    with pytest.raises(ValueError):parse_native_membership(source.replace('Number of reflections in the input file:         3','Number of reflections in the input file:         4'))


@pytest.mark.parametrize('factor,expected',[(.2,{}),(1,{(1,0,0):1,(0,1,0):1})])
def test_actual_native_nondefault_factor_changes_membership(tmp_path,factor,expected):
    if not EXE.is_file():pytest.skip('Installed native Superflip required.')
    rows=[a.Reflection(1,0,0,0,.1),a.Reflection(0,1,0,1e12,.1)]
    observed=tmp_path/'observed.hkl'
    a.write_observed_reflections(observed,rows,0,a.REFLECTION_DATA_MODE_INTENSITY_FWHM)
    inp=tmp_path/'native.inflip'
    write_native_fixture(inp,observed,a.gemmi.UnitCell(10,10.1,11,90,90,90),factor)
    result=subprocess.run([str(EXE),inp.name],cwd=tmp_path,capture_output=True,timeout=30)
    assert result.returncode==0 and (tmp_path/'native.xplor').is_file()
    authority=capture_native_overlap(inp,tmp_path/'native.sflog',observed,EXE)
    cell=a.gemmi.UnitCell(10,10.1,11,90,90,90)
    assert authority.groups_for(rows,cell,1,factor)==expected
    for mode in (a.REFLECTION_DATA_MODE_INTENSITY_FWHM,a.REFLECTION_DATA_MODE_AMPLITUDE_FWHM):
        source=rows if mode==a.REFLECTION_DATA_MODE_INTENSITY_FWHM else [replace(r,value=math.sqrt(r.value)) for r in rows]
        output,_=a.redistribute_overlap_reflections(source,mode,tmp_path/'native.xplor',cell,1,factor,1,lambda _:None,native_grouping=authority)
        values=[r.value if mode==a.REFLECTION_DATA_MODE_INTENSITY_FWHM else r.value**2 for r in output]
        assert all(math.isfinite(v) and v>=0 for v in values)
        assert sum(values)==pytest.approx(1e12,rel=1e-12,abs=1e-9)
