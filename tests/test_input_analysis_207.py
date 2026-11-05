"""Independent counting, uncertainty and cutoff checks; no remote inference."""
import csv
import json
import math
from pathlib import Path
import numpy as np
import pytest
import gemmi
from phase_studio import app as a
from phase_studio.input_analysis import (analysis_rows, significance_cutoff,
    strict_full_resolution, export_rows, import_half_dataset_statistics)
from phase_studio.hkl_diagnostics_ui import presentation_report
import test_hkl_diagnostics as fixtures


@pytest.fixture
def fixture():
    f = fixtures.DiagnosticsTests()
    f.setUp()
    yield f
    f.tearDown()


@pytest.mark.parametrize('mode,records,available',[
    (a.REFLECTION_DATA_MODE_INTENSITY,'1 2 1 12 2\n2 2 1 -4 2\n3 2 1 0 1\n',True),
    (a.REFLECTION_DATA_MODE_INTENSITY,'1 2 1 12\n2 2 1 0\n',False),
    (a.REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA,'1 2 1 12 90 2\n',True),
    (a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA,'1 2 1 12 90 2\n',True),
    (a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,'1 2 1 12 2\n',False),
    (a.REFLECTION_DATA_MODE_INTENSITY_FWHM,'1 2 1 12 .02\n',False),
    (a.REFLECTION_DATA_MODE_AMPLITUDE_FWHM,'1 2 1 12 .02\n',False),
])
def test_real_modes_and_original_records(fixture,mode,records,available,tmp_path):
    load = fixture.load(records,mode)
    original = load.hkl_path.read_bytes()
    analysis = a.analyze_hkl_data(load.hkl_path,mode,load.cell,load.spacegroup,load.spacegroup_hm,_loaded=load)
    report = presentation_report(analysis)
    rows = analysis_rows(analysis,report)
    assert sum(r['records'] for r in rows) == len(records.splitlines())
    assert sum(r['significance_count'] for r in rows) == (len(records.splitlines()) if available else 0)
    if available:
        first = next(r for r in rows if r['significance_count'])
        expected = 3 if mode==a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA else 6
        assert first['mean_significance'] == expected
    out = tmp_path/'rows.csv'
    export_rows(out,rows)
    csv_rows = list(csv.DictReader(out.open(encoding='utf8')))
    assert [int(r['records']) for r in csv_rows] == [r['records'] for r in rows]
    assert load.hkl_path.read_bytes() == original


def shell(lo,hi,mean,count=25):
    return dict(lo=lo,hi=hi,center=(lo+hi)/2,mean_significance=mean,significance_count=count)


def test_cutoff_linear_interpolation_independent_hand_calculation():
    rows = [shell(.1,.2,4),shell(.2,.3,0),shell(.3,.4,1)]
    cutoff = significance_cutoff(rows,2)
    assert cutoff['d'] == pytest.approx(2.5)  # crossing at reciprocal radius .2
    assert cutoff['d_low'] == pytest.approx(1/.6)
    assert cutoff['d_high'] == pytest.approx(5)


@pytest.mark.parametrize('rows',[
    [shell(.1,.2,4),shell(.2,.3,1)], # only one outer shell
    [shell(.1,.2,4),shell(.2,.3,1,1),shell(.3,.4,1)], # sparse crossing
    [shell(.1,.2,4),shell(.2,.3,1),shell(.3,.4,3)], # recovery
    [shell(.1,.2,4),shell(.2,.3,1),shell(.3,.4,None,0)], # missing outer evidence
    [shell(.1,.2,4),shell(.2,.3,4),shell(.3,.4,4)],
    [shell(.1,.2,1),shell(.2,.3,1),shell(.3,.4,1)],
])
def test_no_unsupported_cutoff(rows):
    assert significance_cutoff(rows,2) is None


def test_varying_widths_and_nonorthogonal_metric(fixture):
    load = fixture.load('1 2 1 10 .02\n2 2 1 20 .03\n1 2 1 30 .04\n')
    load.cell = gemmi.UnitCell(8,9,11,73,88,105)
    analysis = a.analyze_hkl_data(load.hkl_path,load.data_mode,load.cell,load.spacegroup,load.spacegroup_hm,_loaded=load)
    report = presentation_report(analysis)
    rows = analysis_rows(analysis,report)
    # Independent real-space Gram inverse, not the application's metric helper.
    lengths = np.array([8,9,11])
    ca,cb,cg = np.cos(np.deg2rad([73,88,105]))
    gram = np.outer(lengths,lengths)*np.array([[1,cg,cb],[cg,1,ca],[cb,ca,1]])
    reciprocal = np.linalg.inv(gram)
    hkls = np.array([[1,2,1],[2,2,1],[1,2,1]])
    stl = np.sqrt(np.einsum('ni,ij,nj->n',hkls,reciprocal,hkls))/2
    for row in rows:
        count = sum(row['lo'] < v <= row['hi'] for v in stl)
        assert row['records']==count
        assert row['record_density']==pytest.approx(count/(row['hi']-row['lo']))


def test_strict_full_and_98_remain_distinct(fixture):
    fixture.cell = gemmi.UnitCell(10,10,10,90,90,90)
    fixture.sg = gemmi.SpaceGroup('P 1')
    # Complete first two reciprocal-radius spheres, one missing third-sphere orbit.
    records = []
    for h in range(-1,2):
        for k in range(-1,2):
            for l in range(-1,2):
                if not (h or k or l) or (h,k,l)==(1,1,1) or (h,k,l)==(-1,-1,-1):continue
                records.append(f'{h} {k} {l} 1 1')
    load=fixture.load('\n'.join(records),a.REFLECTION_DATA_MODE_INTENSITY)
    result=a.analyze_hkl_data(load.hkl_path,load.data_mode,load.cell,load.spacegroup,load.spacegroup_hm,_loaded=load)
    assert strict_full_resolution(result)==pytest.approx(10/math.sqrt(2))
    assert result.d_min==pytest.approx(10/math.sqrt(3))


def test_external_half_dataset_import_is_provenance_gated(tmp_path):
    path=tmp_path/'cc.json'
    valid=dict(source='Independent integration run',method='Correlate verified independent scaled half means',
               independence_evidence='Observation assignment manifest abc123',
               shells=[dict(lo=0,hi=.1,cc_half=.9,paired_orbits=30)])
    path.write_text(json.dumps(valid),encoding='utf8')
    assert import_half_dataset_statistics(path)==valid
    for change in ({'independence_evidence':''},{'shells':[dict(lo=.2,hi=.1,cc_half=.5,paired_orbits=30)]},
                   {'shells':[dict(lo=0,hi=.1,cc_half=1.1,paired_orbits=30)]}):
        path.write_text(json.dumps(valid|change),encoding='utf8')
        with pytest.raises(ValueError):import_half_dataset_statistics(path)


def test_large_repeated_input_counts_are_not_independent_peaks(fixture):
    load=fixture.load('1 2 1 10 .02\n'*100000)
    analysis=a.analyze_hkl_data(load.hkl_path,load.data_mode,load.cell,load.spacegroup,load.spacegroup_hm,_loaded=load)
    rows=analysis_rows(analysis,presentation_report(analysis))
    assert sum(r['records'] for r in rows)==100000
    assert sum(r['literal_unique'] for r in rows)==1
    assert sum(r['observed'] for r in rows)==1
    assert all(r['significance_count']==0 for r in rows)


def test_existing_analysis_math_unchanged_except_new_strict_coverage():
    import ast
    import inspect
    import subprocess
    before=subprocess.check_output(['git','show','2eae1ecd0c83dc6e19d9a99b302d3f479282fc70:phase_studio/app.py']).decode('utf8')
    old=next(n for n in ast.parse(before).body if isinstance(n,ast.FunctionDef) and n.name=='analyze_hkl_data')
    current=ast.parse(inspect.getsource(a.analyze_hkl_data)).body[0]
    addition=ast.parse('d_full_100: Optional[float] = None').body[0]
    condition=ast.parse('if theory_cum_count and observed_cum_count == theory_cum_count:\n    d_full_100 = 1.0 / (2.0 * edge) if edge > 0 else None').body[0]
    assert sum(ast.dump(n)==ast.dump(addition) for n in current.body)==1
    current.body=[n for n in current.body if ast.dump(n)!=ast.dump(addition)]
    removed=0
    for node in ast.walk(current):
        if isinstance(node,ast.While):
            removed+=sum(ast.dump(n)==ast.dump(condition) for n in node.body)
            node.body=[n for n in node.body if ast.dump(n)!=ast.dump(condition)]
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='HklAnalysis':
            keywords=[k for k in node.keywords if k.arg=='d_full_100']
            assert len(keywords)==1 and ast.dump(keywords[0].value)==ast.dump(ast.Name(id='d_full_100',ctx=ast.Load()))
            node.keywords=[k for k in node.keywords if k.arg!='d_full_100']
    assert removed==1
    assert ast.dump(current)==ast.dump(old)
