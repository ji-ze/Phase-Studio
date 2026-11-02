"""Presentation matching must preserve orbit equivalence, populations and bytes."""
import hashlib
from pathlib import Path
import numpy as np
import gemmi
import pytest
from phase_studio.viewer_alignment import present_structure,_shifts

BASE=np.array([[.95,.2,.2],[1.02,.2,.2],[1.09,.2,.2],[.4,.7,.6],[.47,.7,.6],[.54,.7,.6]])


def cif(path,points,sg='P 21/c',length=20):
    path.write_text(f"data_fixture\n_cell_length_a {length}\n_cell_length_b 15\n_cell_length_c 25\n"
        "_cell_angle_alpha 90\n_cell_angle_beta 100\n_cell_angle_gamma 90\n"
        f"_space_group_name_H-M_alt '{sg}'\nloop_\n_atom_site_label\n_atom_site_type_symbol\n"
        "_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\n"+
        '\n'.join(f'C{i+1} C '+ ' '.join(f'{v:.10f}' for v in p) for i,p in enumerate(points))+'\n')
    return path


@pytest.mark.parametrize('indices', [list(range(6)),[0,1,3,4],[0,1,2]])
def test_two_independent_incomplete_or_absent_components(tmp_path,indices):
    ref=cif(tmp_path/'reference.cif',BASE)
    points=BASE[indices].copy()
    operation=gemmi.Op('-x,y+1/2,-z+1/2')
    for i,source in enumerate(indices):
        if source<3:points[i]=np.asarray(operation.apply_to_xyz(list(points[i])))+[2,-1,3]
        else:points[i]+=[-2,1,-3]
    candidate=cif(tmp_path/'candidate_edma.cif',points)
    hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (ref,candidate)]
    data=present_structure(candidate,policy='reference',reference_path=ref,radius=.3)
    info=data['alignment']
    assert info['status']=='Reference-aligned · presentation only',info
    assert len(data['atoms'])==len(indices) and not data['bonds']
    assert info['matched_reference_sites']==len(indices)
    assert info['unmatched_reference_sites']==6-len(indices)
    assert len(info['sites'])==len(indices)
    for site in info['sites']:
        source=np.asarray(site['source_fractional'])
        mapped=np.asarray(gemmi.Op(site['symmetry_operation']).apply_to_xyz(list(source)))+site['lattice_translation']
        np.testing.assert_allclose(mapped,site['displayed_fractional'],atol=1e-8)
    assert hashes==[hashlib.sha256(p.read_bytes()).hexdigest() for p in (ref,candidate)]


def test_reference_free_integer_translation_and_noisy_peaks(tmp_path):
    first=cif(tmp_path/'first.cif',BASE)
    shifted=cif(tmp_path/'shifted.cif',BASE+[5,-4,3])
    one=present_structure(first,policy='reference')
    two=present_structure(shifted,policy='reference')
    assert 'Reference unavailable' in one['alignment']['status']
    np.testing.assert_allclose(sorted(map(tuple,np.round(one['coords'],7))),sorted(map(tuple,np.round(two['coords'],7))))
    noise=cif(tmp_path/'noise_edma.cif',np.vstack([BASE,[[.1,.1,.7]]]))
    result=present_structure(noise,policy='reference',reference_path=first,radius=.2)
    assert len(result['atoms'])==7
    assert result['alignment']['unmatched_displayed_sites']>=1


def test_full_cell_and_cell_mismatch(tmp_path):
    ref=cif(tmp_path/'ref.cif',BASE)
    with ref.open('a') as stream:stream.write('H100 H 0.81 0.82 0.83\n')
    aligned=present_structure(ref,'cell',policy='reference',reference_path=ref)
    ordinary=present_structure(ref,'cell')
    np.testing.assert_array_equal(aligned['coords'],ordinary['coords'])
    assert len(aligned['atoms'])==24 and aligned['alignment']['matched_reference_sites']==24
    assert aligned['alignment']['hydrogen_deuterium_helium_hidden']==1
    assert 'alignment not applied' in aligned['alignment']['status']
    different=cif(tmp_path/'different.cif',BASE,length=22)
    data=present_structure(different,policy='reference',reference_path=ref)
    assert data['alignment']['status']=='Unavailable' and 'metrics differ' in data['alignment']['reason']


def test_lattice_hypotheses_are_complete_in_a_skew_metric():
    orth=np.array([[10,9.8,0],[0,.5,0],[0,0,6.]])
    frac=np.array([[.1,.1,.1]]);ref=np.array([[.9,.9,.1]])
    actual=set(_shifts(frac,ref,orth,.6))
    expected={tuple(n) for n in __import__('itertools').product(range(-5,6),repeat=3)
              if np.linalg.norm(orth@(ref[0]-frac[0]-np.array(n)))<=.6+1e-10}
    assert actual==expected


def test_shared_gui_alignment_and_scientific_identity():
    import os,sys,subprocess
    root=Path(__file__).resolve().parents[1]
    child=subprocess.run([sys.executable,str(root/'tests/alignment_gui_207.py')],cwd=root,
        env=os.environ|{'QT_QPA_PLATFORM':'offscreen'},capture_output=True,text=True,timeout=90)
    assert child.returncode==0,child.stdout+child.stderr
