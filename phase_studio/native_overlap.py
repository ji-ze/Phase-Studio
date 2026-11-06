"""Native overlap authority for executed powder cycles, not approximate geometry.

Read only the completed executable's expanded reflection table. Widths never
become uncertainties; diagnostic Bragg estimates remain a separate capability.
"""
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import re


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def native_powder_keywords(extra, wavelength, separation_factor):
    from . import app as a
    if not math.isfinite(separation_factor) or separation_factor<=0:
        raise ValueError('Native powder separation factor must be finite and positive.')
    lines=a.powder_superflip_keywords(extra,wavelength).splitlines()
    lines=[line for line in lines if a.inflip_first_token(line) not in {'fwhmseparation','expandedlog'}]
    return '\n'.join(lines+[f'fwhmseparation {separation_factor:.12g}','expandedlog yes'])


def parse_native_membership(text):
    start='Reflections read from the input file and averaged:'
    if text.count(start)!=1:
        raise ValueError('Native overlap authority requires one complete expanded reflection table; enable expandedlog yes.')
    before,table=text.split(start)
    if table.count('Maximum indices in expanded reflection set:')!=1:
        raise ValueError('Native expanded reflection table is incomplete.')
    table=table.split('Maximum indices in expanded reflection set:')[0]
    count=re.search(r'Number of reflections in the input file\s*:\s*(\d+)',before)
    header=next((line for line in table.splitlines() if 'ArrayLocation' in line),None)
    if count is None or header is None:
        raise ValueError('Native reflection-table header/count is missing.')
    grouped=header.split()[-1]=='Group'
    columns=tuple(header.split()[4:])
    if columns not in {('F','ArrayLocation'),('F','ArrayLocation','Group'),
                       ('F','A','B','ArrayLocation'),('F','A','B','ArrayLocation','Group')}:
        raise ValueError('Unsupported native expanded reflection-table columns.')
    members={}
    for line in table.splitlines():
        match=re.match(r'^\s*(\d+):\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(.+)$',line)
        if not match:continue
        fields=match[5].split()
        if len(fields)!=len(columns):
            raise ValueError('Unsupported native expanded reflection-table layout.')
        key=tuple(map(int,match.group(2,3,4)))
        if key in members:raise ValueError('Duplicate HKL in native reflection table.')
        group=int(fields[-1]) if grouped else 0
        if group<0:raise ValueError('Negative native overlap group.')
        members[key]=group
    if len(members)!=int(count[1]):
        raise ValueError('Native input/table count differs; refused incomplete or averaged-over input.')
    sizes={group:sum(g==group for g in members.values()) for group in set(members.values()) if group}
    if any(size<2 for size in sizes.values()):raise ValueError('Native overlap group has fewer than two records.')
    if grouped:
        actual=re.search(r'Number of overlapping reflections\s*:\s*(\d+)',before)
        groups=re.search(r'Number of overlap groups\s*:\s*(\d+)',before)
        if actual is None or groups is None or int(actual[1])!=sum(sizes.values()) or int(groups[1])!=len(sizes):
            raise ValueError('Native reflection members disagree with native summary counts.')
    return tuple(sorted(members.items()))


@dataclass(frozen=True)
class NativeOverlap:
    membership: tuple
    widths: tuple
    cell: tuple
    wavelength: float
    separation_factor: float
    files: tuple
    executable_sha256: str

    def groups_for(self, reflections, cell, wavelength, separation_factor):
        from . import app as a
        # Compare the actual serialization, not a widened floating tolerance.
        serialized_cell=tuple(float(f'{v:.{6 if i<3 else 4}f}') for i,v in enumerate(cell.parameters))
        if serialized_cell!=self.cell or float(f'{wavelength:.12g}')!=self.wavelength or float(f'{separation_factor:.12g}')!=self.separation_factor:
            raise ValueError('Native overlap metadata differs from current cell, wavelength or separation factor. Rerun Superflip.')
        widths=tuple(sorted(((int(r.h),int(r.k),int(r.l)),a._phase_studio_float7(r.sigma)) for r in reflections))
        if widths!=self.widths:
            raise ValueError('Native overlap indices/widths differ from the feedback input. Rerun Superflip; estimated groups are not substituted.')
        if any(not Path(path).is_file() or digest(path)!=sha for path,sha in self.files):
            raise ValueError('Native overlap provenance changed after calculation. Rerun Superflip.')
        return {key:group for key,group in self.membership if group}

    def provenance(self):
        return dict(authority='Actual Superflip expanded reflection table',
                    native_executable_sha256=self.executable_sha256,
                    files=[dict(path=p,sha256=s) for p,s in self.files],
                    records=len(self.membership),members=sum(g>0 for _,g in self.membership),
                    groups=len({g for _,g in self.membership if g}),
                    wavelength=self.wavelength,separation_factor=self.separation_factor,
                    estimate_used=False)


def capture_native_overlap(input_path, log_path, observed_path, executable):
    from . import app as a
    input_path,log_path,observed_path=map(Path,(input_path,log_path,observed_path))
    mode=a.reflection_data_mode_from_inflip(input_path)
    if not a.reflection_mode_has_fwhm(mode):raise ValueError('Native overlap authority requires declared FWHM input.')
    context=a.parse_inflip_settings(input_path)
    cell,sg,hm,composition=a.parse_inflip_crystallography(input_path)
    membership=parse_native_membership(log_path.read_text(encoding='utf8',errors='strict'))
    raw=a.read_hkl(observed_path,*a.reflection_columns_for_mode(mode)[:2])
    a.validate_powder_reflections(raw,mode)
    widths=tuple(sorted(((r.h,r.k,r.l),a._phase_studio_float7(r.sigma)) for r in raw))
    if len(widths)!=len(set(key for key,_ in widths)) or {key for key,_ in widths}!={key for key,_ in membership}:
        raise ValueError('Native reflection set differs from the observed input; no estimated replacement is permitted.')
    # The generated .inflip contains these exact records. Verify before trusting
    # the table; intensity changes after this capture do not change widths/groups.
    source=input_path.read_text(encoding='utf8').split('fbegin',1)[1].split('endf',1)[0]
    parsed=[a.parse_reflection_line(line,4,5) for line in source.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    parsed=[r for r in parsed if r is not None]
    if [(r.h,r.k,r.l,r.value,r.sigma) for r in parsed]!=[(r.h,r.k,r.l,r.value,r.sigma) for r in raw]:
        raise ValueError('Native .inflip records differ from the observed reflection file.')
    return NativeOverlap(membership,widths,tuple(cell.parameters),float(context['powder_wavelength']),
        float(context.get('powder_separation_factor',.2)),
        tuple((str(p.resolve()),digest(p)) for p in (input_path,log_path,observed_path)),digest(executable))
