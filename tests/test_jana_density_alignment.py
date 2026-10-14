"""Actual-file guards for origin-preserving Jana density conversion."""
from __future__ import annotations
import os, sys, tempfile, subprocess
from pathlib import Path
import numpy as np
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phase_studio import app
from phase_studio.xplor_io import XplorMap, read_xplor_map, write_xplor_map
from phase_studio.jana_density import origin_preserving_conversion_lines, validate_converted_density, validate_jana_density_pair


def main():
    checks = 0
    def check(label, condition):
        nonlocal checks
        checks += 1
        if not condition: raise AssertionError(label)
    def rejected(callback):
        try: callback()
        except (ValueError, RuntimeError): return True
        return False
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        z,y,x = np.indices((16,16,16))/16
        for label, cell, shift in (
            ('P1 aligned', (10,11,12,90,90,90),0),
            ('P-1 non-grid origin', (10,11,12,90,90,90),0.137),
            ('triclinic', (10,11,12,82,93,104),0.137),
            ('boundary molecule', (10,11,12,90,90,90),0.99),
            ('equivalent origin', (10,11,12,90,90,90),0.5),
        ):
            density=1+np.cos(2*np.pi*(x-shift))+0.4*np.sin(2*np.pi*y)+0.2*np.cos(2*np.pi*z)
            source=root/'selected.xplor'
            xmap=XplorMap(label,(16,0,15,16,0,15,16,0,15),cell,'ZYX',density.ravel())
            write_xplor_map(source,xmap)
            before=source.read_bytes()
            lines=origin_preserving_conversion_lines(['perform symmetry','maxcycles 0','searchsymmetry average','derivesymmetry yes','voxel 8 8 8','referencefile wrong.cif'],source)
            check(label+': no origin search or averaging', 'searchsymmetry no' in lines and 'searchsymmetry average' not in lines and 'derivesymmetry no' in lines)
            check(label+': source grid explicit', 'voxel 16 16 16' in lines and 'voxel 8 8 8' not in lines)
            check(label+': stale reference removed', not any(line.startswith('referencefile') for line in lines))
            target=root/'converted.xplor'
            write_xplor_map(target,xmap)
            report=validate_converted_density(source,target)
            check(label+': aligned map has zero transformation', report['relative_l2']==0 and report['fractional_origin_shift']==[0,0,0])
            check(label+': source bytes unchanged',source.read_bytes()==before)
            moved=XplorMap(label,xmap.grid,cell,'ZYX',np.roll(density,3,axis=2).ravel())
            write_xplor_map(target,moved)
            check(label+': output origin mismatch rejected',rejected(lambda: validate_converted_density(source,target)))
        write_xplor_map(target,XplorMap(label,xmap.grid,cell,'ZYX',density[:, :, ::-1].ravel()))
        check('inversion mismatch rejected',rejected(lambda: validate_converted_density(source,target)))
        write_xplor_map(target,XplorMap(label,xmap.grid,cell,'ZYX',(density*2).ravel()))
        check('scaling rejected',rejected(lambda: validate_converted_density(source,target)))
        write_xplor_map(target,XplorMap(label,xmap.grid,(20,11,12,82,93,104),'ZYX',density.ravel()))
        check('cell mismatch rejected',rejected(lambda: validate_converted_density(source,target)))
        exe_candidates=[Path('build/real_jana_protocol_probe/bin/superflip_original.exe'),Path(r'C:\Jana2020\backup\superflip.exe')]
        exe=next((p.resolve() for p in exe_candidates if p.is_file()),None)
        if exe:
            for centro in ('no','yes'):
                source=root/'selected.xplor'
                density=1+np.cos(2*np.pi*(x-0.137))+0.4*np.sin(2*np.pi*(y-.09))+.2*np.cos(2*np.pi*z)
                write_xplor_map(source,XplorMap('binary probe',(16,0,15,16,0,15,16,0,15),(10,11,12,82,93,104),'ZYX',density.ravel()))
                header=['title probe','perform CF','outputformat jana','dimension 3','cell 10 11 12 82 93 104',f'centro {centro}','centers','0 0 0','endcenters','symmetry','x1 x2 x3']
                if centro=='yes': header.append('-x1 -x2 -x3')
                header.append('endsymmetry')
                lines=app._jana_conversion_lines(header,'density','selected.xplor','density.m81','density.m80','density.xplor')
                lines=origin_preserving_conversion_lines(lines,source)
                (root/'convert.inflip').write_text('\n'.join(lines)+'\n')
                run=subprocess.run([str(exe),'convert.inflip'],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30)
                check(f'centro {centro}: installed Superflip returns success',run.returncode==0)
                report=validate_converted_density(source,root/'density.xplor')
                check(f'centro {centro}: preserves non-grid origin and density',report['correlation']>0.999999)
                pair=validate_jana_density_pair(root/'density.xplor',root/'density.m81',root/'density.m80')
                check(f'centro {centro}: actual M80 phases/amplitudes match M81',pair['m80_relative_error']<5e-4 and pair['m81_relative_l2']<5e-4)
                original=(root/'density.m80').read_text()
                # The checked complex calculated field is columns 8/9.
                first=original.splitlines()[0]
                changed=original.splitlines()
                changed[0]=first[:53]+' 0.00000E+00'+first[65:]
                (root/'density.m80').write_text('\n'.join(changed)+'\n')
                check(f'centro {centro}: mixed M80/M81 fails validation',rejected(lambda:validate_jana_density_pair(root/'density.xplor',root/'density.m81',root/'density.m80')))
        else:
            print('Installed Superflip probes unavailable; run separately on Jana workstation')
    print(f'Jana density alignment checks passed: {checks}')

if __name__=='__main__': main()
