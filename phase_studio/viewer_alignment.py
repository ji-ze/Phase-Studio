"""Constrained crystallographic presentation, never a structural refinement.

Only whole geometric components receive common space-group operations and
integer lattice translations. No atom-wise fitting, free rotation or continuous
origin shift is permitted. Matching is geometric, not chemical validation.
"""
from dataclasses import replace
from itertools import product
from pathlib import Path
import math
import numpy as np
import gemmi

POLICIES=(('Independent components','independent'),
          ('Crystallographic frame','crystallographic'),
          ('Reference-aligned · presentation only','reference'))
MATCH_RADIUS=1.0  # Angstrom; display diagnostic, independent of validation metrics.


def comparison_policy():
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance()
    return getattr(app,'_phase_comparison_policy','independent')


def _components(count,bonds):
    adjacency=[[] for _ in range(count)]
    for i,j in bonds:adjacency[i].append(j);adjacency[j].append(i)
    seen=set();groups=[]
    for seed in range(count):
        if seed in seen:continue
        group=[];stack=[seed];seen.add(seed)
        while stack:
            i=stack.pop();group.append(i)
            for j in adjacency[i]:
                if j not in seen:seen.add(j);stack.append(j)
        groups.append(sorted(group))
    return groups


def _frame(data,cell):
    from .autosolve_window import periodic_connectivity_unwrap,_cell_matrices
    atoms,coords,bonds,extended=periodic_connectivity_unwrap(data['atoms'],cell)
    orth,offset,inverse=_cell_matrices(cell)
    groups=_components(len(atoms),bonds)
    groups.sort(key=lambda group:(-len(group),tuple(np.mod(np.mean([atoms[i].frac for i in group],axis=0),1))))
    anchor=np.mean([atoms[i].frac for i in groups[0]],axis=0)
    target=anchor-np.floor(anchor+1e-10)
    transforms=[]
    for indices in groups:
        frac=np.asarray([atoms[i].frac for i in indices])
        delta=target-frac.mean(axis=0);nearest=np.rint(delta).astype(int)
        bound=np.linalg.norm(orth@(delta-nearest))/float(np.linalg.svd(orth,compute_uv=False)[-1])+1e-10
        low=np.ceil(delta-bound).astype(int);high=np.floor(delta+bound).astype(int)
        if int(np.prod(high-low+1))>100000:raise ValueError('Cell metric is too ill-conditioned for exact component placement')
        shift=np.asarray(min(product(*(range(int(a),int(b)+1) for a,b in zip(low,high))),
            key=lambda n:(round(float(np.linalg.norm(orth@(delta-n))),10),tuple(n))),dtype=int)
        for i in indices:atoms[i]=replace(atoms[i],frac=np.asarray(atoms[i].frac)+shift)
        coords[indices]+=orth@shift
        transforms.append(dict(sites=indices,symmetry_operation='x,y,z',lattice_translation=shift.tolist()))
    return atoms,coords,bonds,groups,orth,inverse,transforms,extended


def _matching(coords,reference,radius,allowed=None,metric=None):
    """Deterministic maximum-cardinality bipartite matching within the cutoff.

    Distance-ordered augmenting paths break ties reproducibly. This does not
    claim a globally minimum RMSD assignment or a chemical correspondence.
    """
    distance=np.linalg.norm(coords[:,None,:]-reference[None,:,:],axis=2)
    if metric is not None:
        inverse=np.linalg.inv(metric)
        for shift in _shifts(coords@inverse.T,reference@inverse.T,metric,radius):
            moved=coords+metric@np.asarray(shift)
            distance=np.minimum(distance,np.linalg.norm(moved[:,None,:]-reference[None,:,:],axis=2))
    permitted=set(range(len(reference))) if allowed is None else set(allowed)
    edges=[sorted((j for j in permitted if distance[i,j]<=radius+1e-10),key=lambda j:(distance[i,j],j))
           for i in range(len(coords))]
    owners={}
    def augment(i,visited):
        for j in edges[i]:
            if j in visited:continue
            visited.add(j)
            if j not in owners or augment(owners[j],visited):owners[j]=i;return True
        return False
    for i in sorted(range(len(coords)),key=lambda i:(len(edges[i]),tuple(coords[i]),i)):
        augment(i,set())
    return sorted((i,j,float(distance[i,j])) for j,i in owners.items())


def _shifts(frac,reference_frac,orth,radius):
    """Complete lattice hypotheses that can place any site within radius.

    ||A v|| >= sigma_min(A)||v|| gives a rigorous integer search bound,
    including skew cells. Oversized searches fail explicitly, never approximate.
    """
    bound=radius/float(np.linalg.svd(orth,compute_uv=False)[-1])+1e-10
    delta=(reference_frac[None,:,:]-frac[:,None,:]).reshape(-1,3)
    low=np.ceil(delta-bound).astype(int);high=np.floor(delta+bound).astype(int)
    shifts=set()
    for d,lo,hi in zip(delta,low,high):
        if np.any(lo>hi):continue
        size=int(np.prod(hi-lo+1))
        if size>100000:raise ValueError('Cell metric is too ill-conditioned for bounded presentation matching')
        for shift in product(*(range(int(a),int(b)+1) for a,b in zip(lo,hi))):
            if np.linalg.norm(orth@(d-np.asarray(shift)))<=radius+1e-10:shifts.add(shift)
    return sorted(shifts)


def _site_provenance(raw,displayed,cell,sg):
    """Verify every drawn site against a source orbit; retain source coordinates."""
    from .autosolve_window import _cell_matrices
    orth,_,_=_cell_matrices(cell)
    ops=list(sg.operations());result=[];buckets={};scale=1000000
    for source_index,source in enumerate(raw):
        for op in ops:
            mapped=np.asarray(op.apply_to_xyz(list(map(float,source.frac))))
            key=(source.element,*np.floor(np.mod(mapped,1)*scale).astype(int))
            buckets.setdefault(key,[]).append((source_index,source,op,mapped))
    for index,site in enumerate(displayed):
        found=None
        base=np.floor(np.mod(site.frac,1)*scale).astype(int)
        candidates=[]
        for offset in product((-1,0,1),repeat=3):
            key=(site.element,*((base+offset)%scale))
            candidates.extend(buckets.get(key,[]))
        for source_index,source,op,mapped in sorted(candidates,key=lambda item:(item[0],item[2].triplet())):
                delta=np.asarray(site.frac)-mapped;shift=np.rint(delta).astype(int)
                if np.linalg.norm(orth@(delta-shift))<1e-5:
                    found=dict(source_index=source_index,source_label=source.label,
                        source_fractional=list(map(float,source.frac)),symmetry_operation=op.triplet(),
                        lattice_translation=shift.tolist());break
        if found is None:raise ValueError(f'Displayed site {site.label} has no verified source-space-group equivalent')
        result.append(found|dict(display_index=index,display_label=site.label,
                                 displayed_fractional=list(map(float,site.frac))))
    return result


def _heavy_presentation(data):
    """Count and match the same visible population used by every renderer."""
    indices=[i for i,atom in enumerate(data['atoms']) if atom.element not in {'H','D','He'}]
    mapping={old:new for new,old in enumerate(indices)}
    return dict(data,atoms=[data['atoms'][i] for i in indices],coords=np.asarray(data['coords'])[indices],
        displayed=len(indices),bonds=[(mapping[i],mapping[j]) for i,j in data['bonds'] if i in mapping and j in mapping])


def present_structure(path,view_mode='molecule',composition='',composition_label='Composition',
                      *,policy='independent',reference_path=None,radius=MATCH_RADIUS,metric_cell=None):
    """Shared presentation authority for comparison, selector and fullscreen."""
    from .autosolve_window import prepare_structure_presentation,build_complete_molecule_view,_bounding_sphere,_cell_matrices
    from .app import parse_cif_atoms,parse_cif_cell_and_sg,edma_asu_atoms
    data=_heavy_presentation(prepare_structure_presentation(path,view_mode,composition,composition_label))
    if not data['atoms']:return data
    path=Path(path);raw=parse_cif_atoms(path);cell,sg,_=parse_cif_cell_and_sg(path)
    heavy=[a for a in raw if a.element not in {'H','D','He'}]
    data['independent_heavy_asu_sites']=len(edma_asu_atoms(heavy,cell,sg))
    data=dict(data);data['alignment']=dict(policy=policy,status='Independent components',presentation_only=True,
        matching_radius_angstrom=radius,matching_criterion='Element-agnostic, one-to-one geometric matches; not chemical validation',
        continuous_origin_shift=None)
    reference=Path(reference_path) if reference_path is not None else None
    try:
        ref_cell=ref_sg=None
        if reference is not None and reference.is_file():ref_cell,ref_sg,_=parse_cif_cell_and_sg(reference)
        display_cell=metric_cell or (ref_cell if policy=='reference' and ref_cell is not None else cell)
        def compatible(first,second):
            return (np.allclose(first.parameters[:3],second.parameters[:3],rtol=2e-4,atol=1e-5)
                    and np.allclose(first.parameters[3:],second.parameters[3:],rtol=0,atol=.02))
        if policy!='independent' and not compatible(cell,display_cell):
            raise ValueError('Reference/candidate unit-cell metrics differ; alignment and matching unavailable')
        data['alignment'].update(display_cell=list(display_cell.parameters),
            metric_compatibility='Cell lengths within 0.02%; angles within 0.02 degrees. Fractional coordinates unchanged by adopting the documented display metric.')
        if policy!='independent' and view_mode!='cell':
            # Retain every independent heavy site; noise is never hidden to improve agreement.
            full=build_complete_molecule_view(raw,cell,sg,retain_all_sites=True,max_atoms=max(64,2*len(heavy)))
            data.update(atoms=full.atoms,coords=full.coords,displayed=len(full.atoms),bonds=[])
            atoms,coords,bonds,groups,orth,inverse,transforms,extended=_frame(data,display_cell)
            data.update(atoms=atoms,coords=coords)
            data['alignment'].update(status='Deterministic crystallographic component frame',
                transforms=transforms,geometric_components=len(groups),extended_periodic_graph=extended)
        else:
            atoms=data['atoms'];coords=data['coords'];orth,_,inverse=_cell_matrices(cell)
            # Components remain geometric diagnostics even when EDMA bond drawing is disabled.
            _,_,bonds,extended=__import__('phase_studio.autosolve_window',fromlist=['periodic_connectivity_unwrap']).periodic_connectivity_unwrap(atoms,cell)
            groups=_components(len(atoms),bonds)
            data['alignment'].update(geometric_components=len(groups),extended_periodic_graph=extended)
        if view_mode=='cell' and policy!='independent':
            old_inverse=_cell_matrices(cell)[2];orth,_,inverse=_cell_matrices(display_cell)
            if tuple(cell.parameters)!=tuple(display_cell.parameters):
                coords=np.asarray([a.frac for a in atoms])@orth.T
                data['coords']=coords
                data['cell_segments']=[np.asarray(segment)@old_inverse.T@orth.T for segment in data['cell_segments']]
                data['fit']=_bounding_sphere(np.vstack([coords,*data['cell_segments']]))
        if reference is not None and reference.is_file():
            if not compatible(cell,ref_cell):
                raise ValueError('Reference/candidate unit-cell metrics differ; alignment and matching unavailable')
            ref=_heavy_presentation(prepare_structure_presentation(reference,view_mode))
            if policy!='independent' and view_mode!='cell':
                ref_raw=parse_cif_atoms(reference)
                ref_full=build_complete_molecule_view(ref_raw,ref_cell,ref_sg,retain_all_sites=True,max_atoms=max(64,2*len(ref_raw)))
                ref=ref|dict(atoms=ref_full.atoms,coords=ref_full.coords,bonds=ref_full.bonds)
            if policy=='reference' and view_mode!='cell':
                ref_atoms,ref_coords,_,ref_groups,orth,inverse,_,_=_frame(ref,display_cell)
                ref_frac=np.asarray([atom.frac for atom in ref_atoms])
                common={op.triplet() for op in ref_sg.operations()}
                operations=sorted((op for op in sg.operations() if op.triplet() in common),key=lambda op:op.triplet())
                if not operations:raise ValueError('No verified common space-group operations')
                remaining=set(range(len(ref_coords)));transforms=[]
                ordering=sorted(groups,key=lambda g:(-len(g),tuple(np.mean(coords[g],axis=0)),tuple(g)))
                for indices in ordering:
                    frac=np.asarray([atoms[i].frac for i in indices]);best=None
                    for op in operations:
                        rotation=np.asarray(op.rot,dtype=float)/op.DEN
                        metric_rotation=orth@rotation@inverse
                        if not np.allclose(metric_rotation.T@metric_rotation,np.eye(3),atol=1e-6):continue
                        transformed=np.asarray([op.apply_to_xyz(list(map(float,f))) for f in frac])
                        for shift in _shifts(transformed,ref_frac,orth,radius):
                            candidate=(transformed+shift)@orth.T
                            pairs=_matching(candidate,ref_coords,radius,remaining)
                            score=(-len(pairs),round(sum(d*d for _,_,d in pairs),12),op.triplet(),shift)
                            if best is None or score<best[0]:best=(score,op,shift,transformed,pairs)
                    if best is not None and best[4]:
                        _,op,shift,transformed,pairs=best
                        for i,f in zip(indices,transformed+shift):atoms[i]=replace(atoms[i],frac=f.copy())
                        coords[indices]=(transformed+shift)@orth.T
                        remaining.difference_update(j for _,j,_ in pairs)
                        transforms.append(dict(sites=indices,symmetry_operation=op.triplet(),lattice_translation=list(shift)))
                    else:transforms.append(dict(sites=indices,symmetry_operation='x,y,z',lattice_translation=[0,0,0],unmatched=True))
                data.update(atoms=atoms,coords=coords,bonds=[])
                data['alignment'].update(status='Reference-aligned · presentation only',transforms=transforms,
                    display_cell=list(display_cell.parameters),common_operations=[op.triplet() for op in operations])
            elif policy!='independent' and view_mode!='cell':
                frame=_frame(ref,display_cell);ref_coords=frame[1];ref_groups=frame[3]
            else:
                ref_coords=ref['coords'];ref_groups=_components(len(ref_coords),ref['bonds'])
                if view_mode=='cell' and policy!='independent' and tuple(ref_cell.parameters)!=tuple(display_cell.parameters):
                    ref_coords=np.asarray([a.frac for a in ref['atoms']])@orth.T
            pairs=_matching(coords,ref_coords,radius,metric=orth if view_mode=='cell' else None)
            data['alignment'].update(matched_reference_sites=len(pairs),unmatched_displayed_sites=len(coords)-len(pairs),
                unmatched_reference_sites=len(ref_coords)-len(pairs),reference_matching_population=len(ref_coords),
                matched_pairs=[dict(display_site=i,reference_site=j,distance_angstrom=d) for i,j,d in pairs],
                matched_rmsd_angstrom=math.sqrt(sum(d*d for _,_,d in pairs)/len(pairs)) if pairs else None)
            matched={j for _,j,_ in pairs}
            reference_atoms_for_matching=ref_atoms if policy=='reference' and view_mode!='cell' else ref['atoms']
            data['alignment']['reference_component_matches']=[dict(reference_component=index,
                reference_sites=len(group),matched_sites=len(set(group)&matched),unmatched_sites=len(set(group)-matched))
                for index,group in enumerate(ref_groups)]
            for item,group in zip(data['alignment']['reference_component_matches'],ref_groups):
                item['reference_site_indices']=list(group)
                item['reference_labels']=[reference_atoms_for_matching[j].label for j in group]
        elif policy=='reference':data['alignment']['status']='Reference unavailable; deterministic crystallographic frame'
        if view_mode=='cell':data['alignment']['status']='Full cell · original crystallographic frame; alignment not applied'
        data['alignment']['sites']=_site_provenance(raw,data['atoms'],cell,sg)
        if view_mode!='cell':data['fit']=_bounding_sphere(np.asarray(data['coords']))
    except (ValueError,RuntimeError,TypeError) as exc:
        data['alignment'].update(status='Unavailable',reason=str(exc))
    data['alignment'].update(source_path=str(path),source_cell=list(cell.parameters),source_space_group=sg.xhm(),
        source_sites=len(raw),displayed_sites=len(data['atoms']),hydrogen_deuterium_helium_hidden=len(raw)-len(heavy),
        independent_heavy_asu_sites=data['independent_heavy_asu_sites'],
        visually_suppressed_heavy_sites=max(0,data['independent_heavy_asu_sites']-len(data['atoms'])))
    return data


def panel_summary(data):
    info=data.get('alignment',{})
    text=f'{len(data.get("atoms",[]))} displayed non-H/D/He sites · {data.get("independent_heavy_asu_sites",0)} independent heavy ASU sites'
    if 'matched_reference_sites' in info:
        text+=f' · {info["matched_reference_sites"]}/{info["reference_matching_population"]} reference sites matched within {info["matching_radius_angstrom"]:g} Å'
    return text+' · '+info.get('status','Independent components')
