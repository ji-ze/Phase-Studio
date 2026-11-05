"""Read-only plotting columns derived from the validated HKL diagnostic snapshot.

No filtering or reconstruction configuration changes occur in this module.
"""
import csv
import math
import json
from dataclasses import asdict
import numpy as np

CC_UNAVAILABLE = 'CC1/2 unavailable — unmerged observations or validated half-dataset statistics required.'
CUTOFF_METHOD = (
    'Shells use the existing reciprocal-radius boundaries (lo, hi]. At least 20 '
    'finite genuine-uncertainty records are required per shell. A cutoff requires '
    'an above-threshold shell followed by at least two populated below-threshold '
    'shells, with no later recovery or sparse gap. Linear interpolation in '
    'sinθ/λ between shell means estimates the crossing; the adjacent shell '
    'boundaries are the resolution bracket, not a statistical confidence interval. '
    'No crossing, sparse tails or nonmonotonic recovery yields unavailable. '
    'Diagnostic cutoffs never truncate reconstruction input.'
)


def significance_cutoff(rows, threshold, minimum=20):
    """Conservative sustained crossing; never extrapolate beyond populated shells."""
    means = [r['mean_significance'] for r in rows]
    valid = [r['significance_count'] >= minimum and m is not None and math.isfinite(m)
             for r, m in zip(rows, means)]
    for i in range(1, len(rows)-1):
        if not (valid[i-1] and all(valid[i:])):
            continue
        if means[i-1] >= threshold and all(m < threshold for m in means[i:]):
            left, right = rows[i-1], rows[i]
            t = (means[i-1]-threshold)/(means[i-1]-means[i])
            stl = left['center'] + t*(right['center']-left['center'])
            return dict(d=1/(2*stl), d_low=1/(2*right['hi']),
                        d_high=1/(2*left['lo']) if left['lo'] else None)
    return None


def analysis_rows(analysis, report):
    """Same shell domain as the authority, with explicit record-frequency columns."""
    from . import app as a
    raw = analysis.reflections_raw
    hkls = np.asarray([(r.h,r.k,r.l) for r in raw],dtype=np.int32).reshape(-1,3)
    stl = a.hkl_stl_array_from_metric(a.reciprocal_metric_tensor(analysis.cell), hkls)
    significance = np.asarray([a.reflection_primary_signal_to_noise(r,analysis.data_mode)
                              if report.available('significance') else None for r in raw],dtype=float)
    rows = []
    cumulative = cumulative_observed = cumulative_theory = 0
    for source in report.shells:
        row = dict(source)
        mask = (stl > row['lo']) & (stl <= row['hi']) & np.any(hkls != 0,axis=1)
        indices = np.flatnonzero(mask)
        finite_sig = significance[mask & np.isfinite(significance)]
        cumulative += len(indices)
        cumulative_observed += row['observed']
        cumulative_theory += row['theory']
        row.update(d=1/(2*row['center']), records=len(indices),
                   literal_unique=len({tuple(hkls[i]) for i in indices}),
                   record_density=len(indices)/(row['hi']-row['lo']),
                   cumulative_records=cumulative,
                   cumulative_coverage=100*cumulative_observed/cumulative_theory if cumulative_theory else None,
                   missing=row['theory']-row['observed'], significance_count=len(finite_sig),
                   fraction_above_2=float(np.mean(finite_sig>=2)) if len(finite_sig) else None,
                   fraction_above_3=float(np.mean(finite_sig>=3)) if len(finite_sig) else None)
        rows.append(row)
    return rows


def strict_full_resolution(analysis):
    """Exact theoretical boundaries, same orbit/Friedel and tolerance policy as d98."""
    return analysis.d_full_100


def export_rows(path, rows):
    with open(path, 'w', newline='', encoding='utf8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ['d'])
        writer.writeheader()
        writer.writerows(rows)


def import_half_dataset_statistics(path):
    """Import external statistics, retaining the producer's independence evidence.

    This validates the interchange, not the scientific truth of that evidence.
    Duplicate merged text records are never converted into half datasets here.
    """
    data = json.loads(open(path, encoding='utf8').read())
    for field in ('source', 'method', 'independence_evidence'):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise ValueError('External CC1/2 requires source, method and independence_evidence.')
    rows = data.get('shells', [])
    if not rows:
        raise ValueError('No external CC1/2 shells supplied.')
    previous = 0.0
    for row in rows:
        lo, hi, cc = (float(row[key]) for key in ('lo', 'hi', 'cc_half'))
        count = row['paired_orbits']
        if not all(math.isfinite(v) for v in (lo,hi,cc)) or lo < previous or hi <= lo or not -1 <= cc <= 1:
            raise ValueError('CC1/2 shells must be ordered, nonoverlapping reciprocal intervals with finite correlations in [-1,1].')
        if not isinstance(count,int) or isinstance(count,bool) or count < 3:
            raise ValueError('Each CC1/2 shell requires at least three independently paired orbits.')
        previous = hi
    return data


def analysis_payload(analysis, report, rows, limits, external_cc=None):
    """One full-precision diagnostic export, including original advanced fields."""
    return dict(diagnostics=asdict(report),
        crystal=dict(cell=list(analysis.cell.parameters),spacegroup=analysis.spacegroup_hm),
        resolution=dict(d_min=analysis.d_min,d98=analysis.d_full_98,d_full=analysis.d_full_100,
                        significance_cutoffs=limits,cutoff_method=CUTOFF_METHOD),
        shells=rows,external_half_dataset_statistics=external_cc or None,
        external_independence_verified_by_application=False)


def grouped_resolution_markers(markers):
    """Combine coincident display labels; diagnostic numerical values stay separate."""
    groups=[]
    for label,d in markers:
        if not d or not math.isfinite(d):continue
        for group in groups:
            if math.isclose(group[1],d,rel_tol=1e-10,abs_tol=1e-12):
                group[0]+=' / '+label
                break
        else:
            groups.append([label,d])
    return groups
