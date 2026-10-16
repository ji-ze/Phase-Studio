"""Read-only Superflip powder metadata and grouping, separate from Map Feedback.

Local authority: sf_input.f90 FWHM2Groups, sf_modules.f90 FWHMlim;
superflip_user_manual sections dataformat, lambda and fwhmseparation.
"""
import math
from pathlib import Path


def standard_powder_context(path):
    """Only an actual declared Superflip block establishes standard width units.

    A plain external five-column file never acquires this provenance by name.
    Missing wavelength remains unavailable; the executable's internal .710 is
    not evidence about the experiment.
    """
    from . import app as a
    path = Path(path)
    directives = {}
    records = []
    inside = False
    for line in path.read_text(encoding='utf8', errors='replace').splitlines():
        parts = a.split_inflip_line(line)
        if not parts:
            continue
        key = parts[0].lower()
        if key == 'endf':
            break
        if inside:
            records.append(parts)
        elif key == 'fbegin':
            if not ({'fwhm','group'} & {v.lower() for v in directives.get('dataformat',[])}):
                return {}  # Do not tokenize a large single-crystal reflection block.
            inside = True
        else:
            directives[key] = parts[1:]
    columns = [v.lower() for v in directives.get('dataformat', [])]
    if not records or not ({'fwhm', 'group'} & set(columns)):
        return {}
    context = dict(source=str(path), fwhm_units='degrees_2theta' if 'fwhm' in columns else None,
                   separation_factor=.2, separation_source='Superflip default (sf_modules.f90 FWHMlim)',
                   wavelength=None, wavelength_source='unavailable')
    if tuple(columns) not in {('intensity','fwhm'),('amplitude','fwhm'),('intensity','group'),('amplitude','group')}:
        context.update(unsupported_layout=True,error='Unsupported diagnostic powder column order. Use declared intensity/amplitude followed by fwhm or group; additional/reordered columns require an explicit supported mapping.')
        return context
    if 'fwhm' in columns and 'group' in columns:
        context['error'] = 'Superflip dataformat cannot combine fwhm and group.'
        return context
    if 'fwhmseparation' in directives:
        try:
            factor = float(directives['fwhmseparation'][0])
            if not math.isfinite(factor) or factor <= 0:
                raise ValueError()
            context.update(separation_factor=factor, separation_source='incoming .inflip fwhmseparation')
        except (ValueError, IndexError):
            context['error'] = 'Invalid fwhmseparation; supply a finite positive value.'
            return context
    for key in ('lambda', 'wavelength'):
        if key in directives:
            try:
                value = float(directives[key][0])
                if not math.isfinite(value) or value <= 0:
                    raise ValueError()
                context.update(wavelength=value, wavelength_source='incoming .inflip '+key)
            except (ValueError, IndexError):
                context['error'] = 'Invalid incoming wavelength; supply a finite positive value in Å.'
            break
    if context['wavelength'] is None and 'error' not in context:
        companion = a.resolve_jana_m90_path(path)
        if companion is not None:
            value = a.parse_m90_wavelength(companion)
            if math.isfinite(value) and value > 0:
                context.update(wavelength=value, wavelength_source='matching Jana2020 .m90: '+companion.name)
    if 'group' in columns:
        groups = {}
        try:
            column = 3 + columns.index('group')
            for row in records:
                indices = tuple(int(v) for v in row[:3])
                value = float(row[column]) if len(row)>column else 0.
                if not math.isfinite(value) or value < 0 or value != int(value) or indices in groups:
                    raise ValueError()
                groups[indices] = int(value)
            context['overlap_groups'] = groups
        except (ValueError, IndexError):
            context['error'] = 'Invalid/duplicate explicit group records; provide nonnegative integral group IDs and unique HKL.'
    return context


def superflip_overlap_groups(reflections, cell, wavelength, separation_factor):
    """Sorted adjacent 2θ, inclusive boundary, transitive connected components.

    Groups refer to input records, not symmetry orbits. Invalid widths or Bragg
    positions raise rather than silently changing the scientific denominator.
    Existing numerical Map Feedback grouping is deliberately untouched.
    """
    from . import app as a
    if not math.isfinite(wavelength) or wavelength <= 0 or not math.isfinite(separation_factor) or separation_factor <= 0:
        raise ValueError('Positive finite wavelength and separation factor required.')
    entries = []
    seen = set()
    for reflection in reflections:
        key = (reflection.h, reflection.k, reflection.l)
        if key == (0, 0, 0):
            continue
        if key in seen:
            raise ValueError('Repeated literal HKL require explicit provenance before grouping.')
        seen.add(key)
        width = reflection.sigma
        angle = a.bragg_two_theta_deg(a.reflection_d_spacing(cell, *key), wavelength)
        if width is None or not math.isfinite(width) or width <= 0 or angle is None:
            raise ValueError('Every physical record needs positive finite FWHM and an accessible Bragg angle.')
        entries.append((angle, width, key))
    entries.sort(key=lambda row: row[0])
    groups = {}
    component = []
    group_id = 0
    def finish():
        nonlocal group_id
        if len(component) > 1:
            group_id += 1
            groups.update((row[2], group_id) for row in component)
    for row in entries:
        if component:
            previous = component[-1]
            if row[0]-previous[0] > separation_factor*(row[1]+previous[1])/2:
                finish()
                component = []
        component.append(row)
    finish()
    return groups
