"""Display notation and record-based overlap bins must not mutate science."""
from dataclasses import replace
import sys
from pathlib import Path
import numpy as np
import pytest
from phase_studio.scientific_typography import scientific_text


@pytest.mark.parametrize('source,expected', [
    ('d_min','<i>d</i><sub>min</sub>'), ('d98','<i>d</i><sub>98</sub>'),
    ('Iobs','<i>I</i><sub>obs</sub>'), ('Fobs','<i>F</i><sub>obs</sub>'),
    ('R_free','<i>R</i><sub>free</sub>'), ('2θ','2<i>θ</i>'),
    ('σ(I)','<i>σ</i>(<i>I</i>)'), ('sinθ/λ','sin <i>θ</i> / <i>λ</i>')])
def test_scientific_inline_typography(source,expected):
    assert scientific_text(source)==expected
    assert scientific_text('HKL ASU EDMA FWHM Jana2020 Superflip SharpED')=='HKL ASU EDMA FWHM Jana2020 Superflip SharpED'


def test_mathtext_and_machine_identifiers():
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    figure=Figure(); canvas=FigureCanvasAgg(figure); axis=figure.subplots()
    axis.set_xlabel(scientific_text('sinθ/λ (Å⁻¹)', 'plot'))
    axis.set_title(scientific_text('Iobs, d_min, d98, σ(F), R_free', 'plot'))
    canvas.draw()
    assert r'\mathrm{min}' in axis.get_title()
    assert scientific_text('sigma_f coverage_pct iobs fobs')=='sigma_f coverage_pct iobs fobs'
    assert scientific_text('I < 3')=='<i>I</i> &lt; 3'
    assert scientific_text('a valid measurement')=='a valid measurement'
    assert scientific_text('a = 8 Å').startswith('<i>a</i> =')
    assert scientific_text('lambda, alpha, beta, gamma')=='<i>λ</i>, <i>α</i>, <i>β</i>, <i>γ</i>'


def test_cross_bin_membership_zero_denominator_and_unchanged_report():
    sys.path.insert(0,str(Path(__file__).parent))
    from test_hkl_diagnostics import DiagnosticsTests
    from phase_studio import app as a, hkl_diagnostics as d
    from phase_studio.hkl_diagnostics_ui import overlap_bin_rows
    fixture=DiagnosticsTests(); fixture.setUp()
    try:
        load=fixture.load('1 2 1 10 .1\n2 2 1 20 .2\n3 2 1 30 .3\n', overlap_groups={(1,2,1):1,(2,2,1):1})
        analysis=a.analyze_hkl_data(load.hkl_path,load.data_mode,load.cell,load.spacegroup,load.spacegroup_hm,_loaded=load)
        points=a.hkl_stl_array_from_metric(a.reciprocal_metric_tensor(load.cell),np.array([(r.h,r.k,r.l) for r in load.reflections]))
        edges=[0,points.min()/2,(points[0]+points[1])/2,(points[1]+points[2])/2,points.max()*1.01]
        analysis.bins=[dict(lo=lo,hi=hi,center=(lo+hi)/2,observed=0,theory=0,completeness=float('nan')) for lo,hi in zip(edges,edges[1:])]
        report=replace(load.diagnostics,shells=d.shell_statistics(analysis,load.diagnostics))
        before=repr(report)
        rows=overlap_bin_rows(analysis,report)
        assert sum(row['input'] for row in rows)==3
        assert sum(row['affected'] for row in rows)==2
        assert rows[0]['percent'] is None and rows[0]['intensity_percent'] is None
        assert rows[1]['percent']==rows[2]['percent']==100
        assert rows[3]['percent']==0
        assert [row['intensity_percent'] for row in rows]==[None,100,100,0]
        assert all('groups' not in row for row in rows)
        assert repr(report)==before and dict(report.overlap)['group_count']==1
        for row,shell in zip(rows,report.shells):
            fraction=dict(shell)['overlap_fraction']
            assert row['percent']==(100*fraction if fraction is not None else None)
        # Negative and zero physical intensity never produce fictitious ratios.
        analysis.reflections_raw=[replace(r,value=-1) for r in analysis.reflections_raw]
        assert all(row['intensity_percent'] is None for row in overlap_bin_rows(analysis,report))
        analysis.reflections_raw=[replace(r,value=0) for r in analysis.reflections_raw]
        assert all(row['intensity_percent'] is None for row in overlap_bin_rows(analysis,report))
    finally:
        fixture.tearDown()
