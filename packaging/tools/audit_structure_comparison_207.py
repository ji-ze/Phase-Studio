"""Read-only inventory of stored CIF/EDMA results and constrained display matching."""
import argparse,json,csv,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from phase_studio import app as a
from phase_studio.autosolve_window import build_complete_molecule_view
from phase_studio.viewer_alignment import present_structure
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('run',type=Path);parser.add_argument('reference',type=Path);parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args();root=args.run.resolve();out=args.output.resolve()
if root==out or root in out.parents:parser.error('Output must be outside the original run')
out.mkdir(parents=True,exist_ok=True)
paths=[(None,'reference',args.reference)]
for directory in sorted(root.glob('cycle_[0-9][0-9][0-9]')):
    cycle=int(directory.name.split('_')[1])
    for source,folder,suffix in [('superflip','edma_superflip','superflip'),('sharped','edma_deblurred','deblurred')]:
        path=directory/folder/f'{directory.name}_{suffix}_edma.cif'
        if path.is_file():paths.append((cycle,source,path))
protected={p for _,_,p in paths}|set(root.glob('cycle_*/*.xplor'))
hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
rows=[];details=[]
metric=a.parse_cif_cell_and_sg(root/'phase_studio_reference_for_metrics.cif')[0]
for cycle,source,path in paths:
    raw=a.parse_cif_atoms(path);cell,sg,_=a.parse_cif_cell_and_sg(path)
    old=build_complete_molecule_view(raw,cell,sg)
    data=present_structure(path,policy='reference',reference_path=args.reference,metric_cell=metric)
    info=data['alignment'];coo=path.with_suffix('.coo')
    raw_edma=len(a.parse_edma_coo(coo)[0]) if coo.is_file() else None
    row=dict(cycle=cycle,source=source,raw_cif_sites=len(raw),raw_heavy_sites=sum(x.element not in {'H','D','He'} for x in raw),
             raw_edma_peaks=raw_edma,independent_asu_sites=data.get('independent_asu_sites'),
             previous_primary_displayed=len(old.atoms),previous_secondary_displayed=len(old.secondary_atoms),
             aligned_displayed=len(data['atoms']),geometric_components=info.get('geometric_components'),
             matched_reference_sites=info.get('matched_reference_sites'),unmatched_displayed_sites=info.get('unmatched_displayed_sites'),
             unmatched_reference_sites=info.get('unmatched_reference_sites'),matching_radius_angstrom=1.,status=info['status'])
    rows.append(row);print(json.dumps(row),flush=True)
    details.append(row|dict(source_file=str(path),source_inventory=[dict(label=x.label,element=x.element,
        fractional=list(map(float,x.frac))) for x in raw],alignment=info))
for name,digest in hashes.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
(out/'inventory.json').write_text(json.dumps(details,indent=2),encoding='utf8')
(out/'unchanged-scientific-files.json').write_text(json.dumps(hashes,indent=2),encoding='utf8')
with (out/'summary.csv').open('w',newline='',encoding='utf8') as stream:
    writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
