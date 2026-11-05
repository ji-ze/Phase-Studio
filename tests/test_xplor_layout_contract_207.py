"""Unsupported map coordinates must fail, rather than silently move density."""
import pytest
from phase_studio.xplor_io import read_xplor_map


@pytest.mark.parametrize('order,grid',[('XYZ',(3,0,2,3,0,2,3,0,2)),
                                      ('ZYX',(3,1,3,3,0,2,3,0,2))])
def test_noncanonical_map_layout_is_explicitly_rejected(tmp_path,order,grid):
    path=tmp_path/'noncanonical.xplor'
    # Hand-written fixture: three cubic sections; a nonzero point makes axis
    # permutations/origin shifts observable, unlike a constant or centered map.
    lines=['','       1','explicit noncanonical layout',' '.join(map(str,grid)),
           '10 10 10 90 90 90',order]
    for section in range(3):
        lines.append(str(section))
        lines.extend(str(1. if section==1 and index==2 else 0.) for index in range(9))
    lines.extend(['-9999','0 1'])
    path.write_text('\n'.join(lines)+'\n')
    with pytest.raises(RuntimeError,match='zero-origin ZYX'):
        read_xplor_map(path)
