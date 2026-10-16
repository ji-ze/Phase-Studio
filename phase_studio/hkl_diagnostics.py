"""Read-only HKL diagnostics. Parsing, symmetry and overlap use existing authorities.

No token, phasing, repartitioning or export-of-structures code belongs here.
Unknown provenance is deliberately not promoted to experimental observations.
"""
from collections import Counter
from contextlib import contextmanager
from concurrent.futures import CancelledError
from dataclasses import asdict, dataclass
from functools import lru_cache
import csv
import json
import math
import threading
from pathlib import Path
from typing import Optional

import numpy as np

D98_DEFINITION = (
    'd98 is the highest-resolution theoretical boundary at which cumulative '
    'allowed-HKL coverage from sin(theta)/lambda = 0 reaches at least 98%. '
    'It need not stay above 98% at every preceding boundary, depends on the '
    'input d_min domain, and is not an independent experimental quality cutoff.'
)
COVERAGE_DEFINITION = (
    'Distinct input HKL orbits intersected with theoretical symmetry-allowed '
    'orbits, divided by all allowed orbits from infinite d to the input d_min; '
    '000 and systematic absences excluded. Friedel pairs are combined by the '
    'existing coverage convention; this does not merge or modify input values. '
    'The d_min boundary is inclusive with relative reciprocal tolerance 1e-12 '
    '(at least 8 floating-point ULPs).'
)
OVERLAP_UNAVAILABLE = 'Overlap analysis unavailable — peak-width units or profile metadata are insufficient.'
_load_cache = {}
_analysis_cache = {}
_cache_lock = threading.RLock()
_cancellation = threading.local()


@contextmanager
def diagnostic_cancellation(event):
    previous = getattr(_cancellation,'event',None)
    _cancellation.event = event
    try:
        check_cancelled()
        yield
    finally:
        _cancellation.event = previous


def check_cancelled():
    event = getattr(_cancellation,'event',None)
    if event is not None and event.is_set():
        raise CancelledError('HKL diagnostics cancelled')


def cached_load_result(request):
    from . import app as a
    companion = a.resolve_jana_m90_path(Path(request.jana_text)) if request.jana_text else None
    files = tuple(source_identity(p) for p in (request.hkl_text,request.jana_text,companion)
                  if p and Path(p).is_file())
    metadata = request.metadata
    crystal = (tuple(metadata.cell.parameters),metadata.spacegroup.xhm(),metadata.source,str(metadata.source_path)) if metadata is not None else None
    key = (files,request.mode,request.hkl_text,request.jana_text,request.ref_text,request.work_text,request.configured_mode,crystal)
    with _cache_lock:
        if key not in _load_cache:
            result = a._build_uncached_hkl_load_result(request)
            _load_cache[key] = result
            if len(_load_cache)>3: _load_cache.pop(next(iter(_load_cache)))
        return _load_cache[key]


def cached_analysis(request, bin_count=12):
    from . import app as a
    load = cached_load_result(request)
    key = (source_identity(load.hkl_path),load.data_mode,tuple(load.cell.parameters),load.spacegroup.xhm(),bin_count,load.format_verified,load.source_note,id(load))
    with _cache_lock:
        if key not in _analysis_cache:
            _analysis_cache[key] = a.analyze_hkl_data(load.hkl_path,load.data_mode,load.cell,load.spacegroup,load.spacegroup_hm,load.source_note,bin_count,_loaded=load)
            if len(_analysis_cache)>2: _analysis_cache.pop(next(iter(_analysis_cache)))
        return _analysis_cache[key]


@dataclass(frozen=True)
class Capability:
    name: str
    available: bool
    reason: str


@dataclass(frozen=True)
class ParseAudit:
    rejected_records: int = 0
    invalid_indices: int = 0
    excluded_000: int = 0
    examples: tuple = ()


@dataclass(frozen=True)
class Diagnostics:
    source: str
    source_note: str
    data_type: str
    data_mode: str
    fwhm_units: str
    observation_kind: str
    phase_status: str
    significance_label: str
    capabilities: tuple
    cell: tuple
    spacegroup: str
    counts: tuple
    statistics: tuple
    warnings: tuple
    methods: tuple
    absence_examples: tuple
    duplicate_examples: tuple
    overlap: tuple
    shells: tuple = ()

    def count(self, name):
        return dict(self.counts).get(name, 0)

    def statistic(self, name):
        return dict(self.statistics).get(name)

    def available(self, name):
        return next(c.available for c in self.capabilities if c.name == name)

    def summary(self):
        lines = [self.data_type, self.source_note, self.phase_status]
        lines += [f'{k}: {v}' for k,v in self.counts]
        lines += [f'{k}: {v if v is not None else "n/a"}' for k,v in self.statistics]
        lines += [f'{severity}: {message}' for severity,message in self.warnings]
        lines += [f'{c.name}: {"available" if c.available else "unavailable"} — {c.reason}' for c in self.capabilities]
        lines += [str(x) for x in self.methods]
        if self.absence_examples:
            lines.append('Forbidden HKL examples: '+str(self.absence_examples))
        if self.duplicate_examples:
            lines.append('Repeated HKL examples: '+str(self.duplicate_examples))
        lines.append('Overlap: '+str(dict(self.overlap)))
        return '\n'.join(lines)

    def export_json(self, path, analysis=None):
        data = asdict(self)
        if analysis is not None:
            data['crystal'] = dict(cell=list(analysis.cell.parameters), spacegroup=analysis.spacegroup_hm)
            data['resolution'] = dict(d_min=analysis.d_min, d98=analysis.d_full_98)
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf8')


def source_identity(path):
    path = Path(path).resolve()
    stat = path.stat()
    return str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


@lru_cache(maxsize=3)
def _read_cached(identity, mode):
    from . import app as a
    value_col, sigma_col, include_000 = a.reflection_columns_for_mode(mode)
    records = []
    rejected = invalid = zeros = 0
    examples = []
    with Path(identity[0]).open(encoding='utf8', errors='replace') as stream:
        for number, line in enumerate(stream, 1):
            if number % 4096 == 0: check_cancelled()
            text = line.strip()
            if not text or text.startswith(a.COMMENT_PREFIXES):
                continue
            parts = text.split()
            # Non-data descriptive headers are not malformed observations.
            try:
                float(parts[0])
            except (ValueError, IndexError):
                if parts and parts[0].lower() not in {'h','dataformat','dataitemwidths','endf','fbegin'}:
                    rejected += 1
                    if len(examples)<8: examples.append((number,text[:180]))
                continue
            bad_index = False
            try:
                indices = [float(x) for x in parts[:3]]
                bad_index = len(indices)!=3 or any(not math.isfinite(x) or not x.is_integer() or abs(x)>2147483647 for x in indices)
            except ValueError:
                bad_index = True
            reflection = None if bad_index else a.parse_reflection_line(line,value_col,sigma_col)
            if reflection is None:
                rejected += 1
                invalid += int(bad_index)
                if len(examples)<8: examples.append((number,text[:180]))
                continue
            if not include_000 and (reflection.h,reflection.k,reflection.l)==(0,0,0):
                zeros += 1
                continue
            records.append(reflection)
    return tuple(records), ParseAudit(rejected,invalid,zeros,tuple(examples))


def read_diagnostic_reflections(path, mode):
    return _read_cached(source_identity(path), mode)


def _finite_stat(values, operation):
    values = np.asarray(values,dtype=float)
    values = values[np.isfinite(values)]
    return float(operation(values)) if len(values) else None


def build_diagnostics(result, *, observation_kind='unknown', friedel_policy='merge',
                      fwhm_units=None, wavelength=None, separation_factor=0.2, overlap_groups=None,
                      weak_thresholds=(1,2,3)):
    """Use original per-record values, never inverse-variance weights on widths.

    Optional provenance arguments are explicit evidence for controlled callers;
    current text HKL readers do not establish unmerged/scaled/profile provenance.
    """
    from . import app as a
    check_cancelled()
    validate_cell(result.cell)
    raw = getattr(result,'reflections_raw',getattr(result,'reflections',None))
    mode = result.data_mode
    verified = getattr(result,'format_verified',True)
    context = getattr(result,'powder_diagnostic_context',{})
    if context:
        fwhm_units = fwhm_units or context.get('fwhm_units')
        wavelength = wavelength if wavelength is not None else context.get('wavelength')
        separation_factor = context.get('separation_factor',separation_factor)
        overlap_groups = context.get('overlap_groups',overlap_groups)
    powder = a.reflection_mode_has_fwhm(mode) or 'overlap_groups' in context
    amplitude = a.reflection_mode_is_amplitude(mode)
    phase_column = a.reflection_mode_has_phase(mode)
    dummy = mode == a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA
    hkls = np.asarray([(r.h,r.k,r.l) for r in raw], dtype=np.int32).reshape(-1,3)
    values = np.asarray([r.value for r in raw],dtype=float)
    auxiliary = np.asarray([r.sigma if r.sigma is not None else np.nan for r in raw],dtype=float)
    phases = np.asarray([r.phase if r.phase is not None else np.nan for r in raw],dtype=float)
    nonzero = np.any(hkls != 0,axis=1)
    literal, inverse, frequency = np.unique(hkls,axis=0,return_inverse=True,return_counts=True)
    operations = result.spacegroup.operations()
    absent = operations.systematic_absences(hkls) & nonzero
    # Gemmi's reciprocal ASU is identical to the existing completeness provider.
    asu = hkls.copy()
    result.spacegroup.switch_to_asu(asu)
    check_cancelled()
    orbits = len(np.unique(asu[nonzero],axis=0))
    if friedel_policy != 'merge':
        # Exact SG operations, without adding inversion. Do not treat an
        # anomalous pair as repeated measurements merely because it is a pair.
        keys = [tuple(row) for row in hkls]
        canonical = [min(tuple(op.apply_to_hkl(row)) for op in operations) for row in keys]
        orbits = len({key for key,nz in zip(canonical,nonzero) if nz})
    finite = np.isfinite(values)
    good_aux = np.isfinite(auxiliary) & (auxiliary > 0)
    uncertainty = verified and not powder and not dummy and bool(np.any(good_aux & finite & nonzero))
    significance = np.full(len(raw),np.nan)
    if uncertainty:
        ok = good_aux & finite & nonzero
        significance[ok] = (np.abs(values[ok])/(2*auxiliary[ok]) if amplitude else values[ok]/auxiliary[ok])
    label = 'Derived I/σ(I) ≈ |F|/(2σ(F))' if amplitude else 'I/σ(I)'
    _, audit = read_diagnostic_reflections(result.hkl_path,mode)
    conflicting = []
    duplicate_ids = np.flatnonzero(frequency>1)
    # Sort groups once; avoid an O(N * number-of-duplicates) scan.
    ordered = np.argsort(inverse,kind='stable')
    starts = np.concatenate(([0],np.cumsum(frequency)))
    for group in duplicate_ids:
        if group % 4096 == 0: check_cancelled()
        group_values = values[ordered[starts[group]:starts[group+1]]]
        valid = group_values[np.isfinite(group_values)]
        if len(valid)>1 and not np.allclose(valid,valid[0],rtol=1e-7,atol=1e-12):
            conflicting.append(tuple(int(x) for x in literal[group]))
    physical_values = values[nonzero & finite]
    widths = auxiliary[nonzero & good_aux]
    constant = bool(len(widths) and np.allclose(widths,widths[0],rtol=1e-7,atol=1e-12))
    counts = dict(parsed_records=len(raw),literal_unique=len(literal),symmetry_orbits=orbits,
                  exact_duplicate_entries=int(np.sum(frequency-1)),conflicting_duplicate_groups=len(conflicting),
                  equivalent_repeated_entries=int(np.count_nonzero(nonzero)-orbits),
                  systematic_absent_entries=int(np.count_nonzero(absent)),
                  absent_nonzero_values=int(np.count_nonzero(absent & finite & (values!=0))),
                  absent_significant_3sigma=int(np.count_nonzero(absent & (significance>=3))) if uncertainty else None,
                  invalid_values=int(np.count_nonzero(~finite)),zero_values=int(np.count_nonzero(nonzero & finite & (values==0))),
                  negative_values=int(np.count_nonzero(nonzero & finite & (values<0))),
                  valid_widths_or_sigmas=int(np.count_nonzero(nonzero & good_aux)),
                  missing_auxiliary=sum(r.sigma is None for r in raw),
                  invalid_auxiliary=sum(r.sigma is not None and (not math.isfinite(r.sigma) or r.sigma<=0) for r in raw),
                  phase_finite=int(np.count_nonzero(np.isfinite(phases))),
                  phase_missing=sum(r.phase is None for r in raw) if phase_column else 0,
                  phase_nonfinite=sum(r.phase is not None and not math.isfinite(r.phase) for r in raw),
                  zero_000=int(np.count_nonzero(~nonzero)),rejected_records=audit.rejected_records,
                  invalid_indices=audit.invalid_indices,excluded_000=audit.excluded_000)
    stl = a.hkl_stl_array_from_metric(a.reciprocal_metric_tensor(result.cell),hkls)
    counts['invalid_reciprocal_values'] = int(np.count_nonzero(nonzero & (~np.isfinite(stl) | (stl<=0))))
    stats = dict(mean_value=_finite_stat(physical_values,np.mean),median_value=_finite_stat(physical_values,np.median),
                 median_auxiliary=_finite_stat(widths,np.median),minimum_auxiliary=_finite_stat(widths,np.min),
                 maximum_auxiliary=_finite_stat(widths,np.max),constant_fwhm=constant if powder and verified else None,
                 mean_significance=_finite_stat(significance,np.mean),median_significance=_finite_stat(significance,np.median))
    if uncertainty:
        for threshold in weak_thresholds:
            if not math.isfinite(float(threshold)) or threshold<=0:
                raise ValueError('Significance thresholds must be finite and positive.')
            stats[f'weak_fraction_below_{threshold:g}'] = float(np.mean(significance[np.isfinite(significance)]<threshold))
    phase_status = ('Phases not supplied — expected for this input format' if not phase_column else
                    f'Phase fields: {counts["phase_finite"]} finite (0° is populated); provenance unverified, not evidence of experimentally solved phases.')
    if not verified:
        phase_status = 'Phase-column meaning unverified; select the exact input layout. Numerical fields alone do not establish experimental phase provenance.'
    overlap = dict(available=False,reason=OVERLAP_UNAVAILABLE)
    if context:
        overlap.update(wavelength=wavelength,wavelength_source=context.get('wavelength_source'),
                       separation_factor=separation_factor,separation_source=context.get('separation_source'),input_source=context.get('source'))
        if context.get('error'):
            overlap_groups = None
            overlap['reason'] = context['error']
        elif a.reflection_mode_has_fwhm(mode) and not wavelength:
            overlap['reason'] = 'Standard Superflip FWHM units: degrees 2θ. Wavelength missing: provide lambda in the incoming .inflip or its matching Jana2020 .m90.'
    # Use authoritative existing grouping only with explicit compatible units.
    if verified and powder and not context.get('error') and overlap_groups is None and fwhm_units=='degrees_2theta' and wavelength and math.isfinite(wavelength) and wavelength>0:
        if np.all(good_aux[nonzero]) and len(literal)==len(raw) and np.all(finite):
            if all(a.bragg_two_theta_deg(a.reflection_d_spacing(result.cell,*tuple(row)),wavelength) is not None for row in hkls[nonzero]):
                from .powder_diagnostics import superflip_overlap_groups
                overlap_groups = superflip_overlap_groups(raw,result.cell,wavelength,separation_factor)
                overlap['estimated'] = True
                overlap['reason'] = f'Estimated peak overlap: wavelength={wavelength} Å ({context.get("wavelength_source","explicit metadata")}); widths in degrees 2θ; neighbor separation ≤ {separation_factor} × mean FWHM; transitive groups (Superflip FWHM2Groups convention). Geometric groups are not verified independent observations.'
            else:
                overlap['reason'] = 'Peak overlap unavailable: some Bragg positions are inaccessible at the supplied wavelength. Verify the measured wavelength and unit cell.'
        else:
            overlap['reason'] = 'Peak overlap unavailable: grouping requires unique literal HKL, finite input values and positive finite widths for every physical record. Review Validation warnings or supply authoritative groups.'
    if powder and overlap_groups is not None:
        groups = Counter(overlap_groups.get(tuple(row),0) for row in hkls[nonzero])
        groups.pop(0,None)
        affected = sum(size for size in groups.values() if size>1)
        sizes = [size for size in groups.values() if size>1]
        valid_groups = {key for key,size in groups.items() if size>1}
        overlap.update(available=True,group_count=len(sizes),affected=affected,
                       input_records=len(raw),physical_records=int(np.count_nonzero(nonzero)),
                       non_overlapping_groups=int(np.count_nonzero(nonzero))-affected,
                       total_groups=int(np.count_nonzero(nonzero))-affected+len(sizes),
                       fraction=affected/int(np.count_nonzero(nonzero)) if np.any(nonzero) else None,
                       geometric_group_count=int(np.count_nonzero(nonzero))-affected+len(sizes),
                       largest=max(sizes,default=1),size_distribution=tuple(sorted(Counter(sizes).items())),
                       groups=tuple((tuple(int(x) for x in row),int(overlap_groups.get(tuple(row),0)) if overlap_groups.get(tuple(row),0) in valid_groups else 0) for row in hkls[nonzero]))
        if not overlap.get('estimated'):
            overlap['reason'] = 'Explicit supplied overlap-group definitions; no intensity repartitioning performed.'
            overlap['supplied_groups'] = tuple((tuple(key),value) for key,value in overlap_groups.items())
        if not amplitude and np.all(physical_values>=0) and np.sum(physical_values)>0:
            mask = np.array([overlap_groups.get(tuple(row),0) in valid_groups for row in hkls]) & nonzero & finite
            overlap['integrated_intensity_fraction'] = float(np.sum(values[mask])/np.sum(physical_values))
    capabilities = (
        Capability('column_semantics',verified,'Declared Jana dataformat or explicitly selected external column layout required; AUTO filename/default guesses are not measurement provenance.'),
        Capability('significance',uncertainty,'Finite positive genuine uncertainty column required; FWHM and dummy sigmas excluded.'),
        Capability('overlap',bool(overlap['available']),overlap['reason']),
        Capability('merging_statistics',False,'CC1/2, R_int, R_merge, R_meas, R_pim and measurement multiplicity require verified unmerged, consistently scaled repeated observations; duplicate text HKL alone is insufficient.'),
        Capability('profile_statistics',False,'Rp, Rwp, Rexp and goodness of fit require observed/calculated profiles, weights and refinement degrees of freedom.'),
        Capability('anomalous_completeness',False,'Requires an explicit anomalous/Friedel policy and verified observation provenance; current coverage combines Friedel mates.'),
        Capability('wilson',False,'Requires suitable scaled intensities, composition and model assumptions; no physical B estimate from arbitrary values.'),
    )
    warnings = []
    if not verified: warnings.append(('WARNING','Column meanings were inferred, not verified. Select the exact reflection format before interpreting uncertainties or peak widths.'))
    if powder: warnings.append(('INFO','FWHM is a peak-width parameter, not measurement uncertainty. HKL coverage does not establish that overlapping reflections were independently measured or uniquely resolved.'))
    if amplitude and uncertainty: warnings.append(('INFO','Intensity significance is derived using I≈F² and σ(I)≈2|F|σ(F), a first-order approximation unreliable near zero; F/σ(F) remains available in the sample table.'))
    for key, description in [('systematic_absent_entries','Systematically forbidden indexed entries; nonzero alone does not establish an experimental error.'),('exact_duplicate_entries','Repeated literal indices; provenance is needed to distinguish repeat measurements from duplicated merged records.'),('invalid_values','Nonfinite values retained in raw records; excluded from numerical summaries.'),('invalid_auxiliary','Nonpositive/nonfinite widths or uncertainties; unavailable for derived metrics.'),('rejected_records','Unparseable/nonintegral-index records reported, not repaired. Examples: '+str(audit.examples))]:
        if counts[key]: warnings.append(('WARNING',f'{counts[key]} {description}'))
    if counts['negative_values']: warnings.append(('INFO','Negative input values are retained, not automatically discarded; negative estimated intensities are not automatically errors.'))
    return Diagnostics(str(result.hkl_path),result.source_note,
        ('HKL list — inferred columns, measurement type unverified' if not verified else 'Powder peak list' if powder else 'Amplitude HKL list' if amplitude else 'Intensity HKL list'),mode,fwhm_units or 'input units',
        observation_kind,phase_status,label,capabilities,tuple(result.cell.parameters),result.spacegroup.xhm(),tuple(counts.items()),tuple(stats.items()),tuple(warnings),
        (COVERAGE_DEFINITION,D98_DEFINITION,'Statistics use finite non-000 original per-record values. FWHM units: '+(fwhm_units or 'input units')+'.',
         'Presence of duplicates does not prove unmerged observations. Current text input merging/scaling provenance is unknown.'),
        tuple(tuple(int(x) for x in row) for row in hkls[absent][:8]),tuple(conflicting[:8]),tuple(overlap.items()))


def validate_cell(cell):
    lengths = np.asarray(cell.parameters[:3],dtype=float)
    angles = np.asarray(cell.parameters[3:],dtype=float)
    cosines = np.cos(np.deg2rad(angles))
    ca,cb,cg = cosines
    determinant = 1-ca*ca-cb*cb-cg*cg+2*ca*cb*cg
    if (not np.all(np.isfinite(lengths)) or not np.all(lengths>0)
        or not np.all(np.isfinite(angles)) or not np.all((angles>0)&(angles<180))
        or not math.isfinite(float(determinant)) or determinant<=1e-12):
        raise ValueError('Invalid unit-cell geometry: positive lengths and a positive-definite cell metric are required for HKL diagnostics.')


def shell_statistics(analysis, report=None):
    from . import app as a
    raw = analysis.reflections_raw
    hkls = np.asarray([(r.h,r.k,r.l) for r in raw],dtype=np.int32)
    stl = a.hkl_stl_array_from_metric(a.reciprocal_metric_tensor(analysis.cell),hkls)
    values = np.asarray([r.value for r in raw],dtype=float)
    aux = np.asarray([r.sigma if r.sigma is not None else np.nan for r in raw],dtype=float)
    powder = a.reflection_mode_has_fwhm(analysis.data_mode)
    significance = np.array([a.reflection_primary_signal_to_noise(r,analysis.data_mode) if not powder else np.nan for r in raw],dtype=float)
    if analysis.data_mode == a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA:
        significance[:] = np.nan
    if report is not None and not report.available('significance'):
        significance[:] = np.nan
    overlap = dict(report.overlap) if report is not None else {}
    membership = dict(overlap.get('groups',()))
    affected = np.array([membership.get(tuple(row),0)>0 for row in hkls],dtype=bool)
    rows = []
    for item in analysis.bins:
        mask = (stl>item['lo']) & (stl<=item['hi']) & np.any(hkls!=0,axis=1)
        rows.append(dict(lo=item['lo'],hi=item['hi'],center=item['center'],observed=int(item['observed']),theory=int(item['theory']),
            coverage=float(item['completeness']) if item['theory'] else None,
            mean_value=_finite_stat(values[mask],np.mean),median_value=_finite_stat(values[mask],np.median),
            mean_fwhm=_finite_stat(aux[mask & np.isfinite(aux) & (aux>0)],np.mean) if powder and (report is None or report.available('column_semantics')) else None,
            mean_significance=_finite_stat(significance[mask],np.mean),median_significance=_finite_stat(significance[mask],np.median),
            overlap_fraction=float(np.mean(affected[mask])) if overlap.get('available') and np.any(mask) else None))
    return tuple(tuple(row.items()) for row in rows)


def export_shell_csv(path, report):
    rows = [dict(row) for row in report.shells]
    metadata = dict(source=report.source,data_mode=report.data_mode,data_type=report.data_type,
                    significance_available=report.available('significance'),significance_label=report.significance_label,
                    significance_unavailable_reason=next(c.reason for c in report.capabilities if c.name=='significance') if not report.available('significance') else '',
                    overlap_available=report.available('overlap'),fwhm_units=report.fwhm_units,
                    overlap_reason=dict(report.overlap)['reason'],
                    coverage_definition=COVERAGE_DEFINITION)
    with Path(path).open('w',newline='',encoding='utf8') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(metadata)+(list(rows[0]) if rows else ['lo','hi']))
        writer.writeheader()
        writer.writerows(metadata | {key:'n/a' if value is None else value for key,value in row.items()} for row in rows)
