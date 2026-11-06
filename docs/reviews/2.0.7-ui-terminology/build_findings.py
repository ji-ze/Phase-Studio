"""Maintain owner-review proposals separately from application wording."""
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(os.environ.get('PHASE_STUDIO_TERMINOLOGY_OUTPUT',str(ROOT/'build/ui-terminology-current')))
OUT.mkdir(parents=True,exist_ok=True)
settings={r['key']:r for r in json.loads((OUT/'settings.json').read_text(encoding='utf8'))}
rows=[
('i_over_sigma_min','Critical scientific correction','Minimum intensity significance I/σ(I) [only when uncertainties are available]',
 'The legacy writer actually divides value by the fifth field even in FWHM mode. A wording-only fix cannot repair that scientific defect. Separate mode-aware filtering decision required; existing algorithm unchanged. FWHM is an angular peak width, not uncertainty.','_passes_reflection_filters; write_observed_reflections'),
('reference_cif','Important clarification','Reference structure (evaluation and optional Superflip density alignment)',
 'Reference-backed validation is not independent evidence. Superflip referencefile also aligns resulting density. Distinguish evaluation, referencefile and modelfile roles.','pipeline_worker; resolve_superflip_referencefile'),
('damping_factor','Important clarification','New-map weight for XPLOR recycling',
 'The GUI inverse x is clipped to [0.001,1], converted to f=1/x, and the blend is (1-x) previous + x new where applicable. A help formula is clearer than the reciprocal alone.','effective_xplor_damping_factor; blend_xplor_maps'),
('map_feedback_intensity_damping','Important clarification','Intensity-correction weight',
 'Correction damping and XPLOR damping are different operations. Explain the existing applied intensity formula and limiting branch rather than implying equal meanings of damping.','apply_map_feedback_to_reflections'),
('map_feedback_intensity_max_i_over_sigma','Important clarification','Correct reflections below I/σ(I)',
 'Strictly-below weak-reflection gate; amplitude-mode significance uses F/[2σ(F)]. This differs from the input-filter cutoff and is unavailable for FWHM significance. Equality matters.','map_feedback_significance; apply_map_feedback_to_reflections'),
('powder_redistribution_mix','Important clarification','Map-predicted fraction of overlap repartitioning',
 'Mix=0 preserves observed ratios; mix=1 uses map ratios. Group sums remain fixed. It does not set a global map amplitude scale.','redistribute_overlap_reflections'),
('powder_separation_factor','Important clarification','Overlap-group separation factor',
 'Dimensionless factor used with angular separation and FWHM, not a physical separation in angstrom. Retain a tooltip defining the actual grouping inequality and units.','assign_powder_overlap_groups'),
('map_feedback_missing_percent_limit','Important clarification','Maximum added HKL (% of the existing reflection set)',
 'Name the actual denominator and distinguish absent original HKL from newly allowed/missing HKL and from reflections crossing the writer filter. Confirm denominator in the existing completion branch before accepting replacement.','complete_missing_reflections_from_map'),
('compute_omit_maps','Important clarification','Compute maps with a 5% reflection holdout',
 'Reflection holdout is distinct from an atom-omission model-bias experiment. Keep the existing OMIT term only with its specific reflection-based definition and immutable holdout explanation.','prepare_omit_holdout; map_quality.with_holdout_metrics'),
('compute_omit_rfree','Important clarification','Calculate holdout R on the excluded 5% reflections',
 'Do not imply independently refined R_free or independent validation when a reference/remote prediction influences evaluation. State amplitude/intensity convention and denominator used by compute_rfree.','compute_rfree; compute_omit_metrics'),
('plimit_superflip','Consistency improvement','Superflip EDMA peak threshold (σ)',
 'The two EDMA controls should both state density-standard-deviation units. This sigma is not an intensity measurement uncertainty.','run_edma_on_xplor'),
('plimit_deblur','Consistency improvement','SharpED EDMA peak threshold (σ)',
 'Identify peak extraction rather than implying a SharpED inference threshold. Existing EDMA sigma threshold behavior remains unchanged.','run_edma_on_xplor'),
('edma_numberofatoms','Important clarification','EDMA site-count selection',
 'Raw maxima, retained CIF sites, independent ASU sites and Jana m40 sites can differ. A detected peak is not a chemically validated atom.','run_edma_on_xplor; edma_peak_protocol'),
('biso','Important clarification','Superflip map-sharpening Biso (Å²)',
 'This overall map parameter is distinct from atom-specific physical displacement parameters. EDMA peak density must never be called an ADP. Verify the executable-specific keyword convention.','write_superflip_inflip; physical_displacement'),
('normalize','Important clarification','Requested normalization (backend compatibility applies)',
 'The existing compatibility path may omit normalize atoms rather than send it. A requested GUI value is not proof of the effective generated keyword; show that distinction in help.','write_superflip_inflip; clean_extra_superflip_keywords'),
('randomseed','Important clarification','Superflip random seed (AUTO uses system time)',
 'AUTO is uncontrolled unless the backend reports and provenance captures the actual seed. A saved configuration alone does not guarantee exact reproduction.','write_superflip_inflip'),
('sharped_model','Important clarification','SharpED model selection',
 'A catalog/display name is not an immutable model/checkpoint identity. Record actual API model identifier and server-supplied version separately.','sharped_server_client.model_selection; _upload_job'),
('sharped_outres','Important clarification','SharpED requested output resolution (Å)',
 'Inference request parameter is not measured experimental resolution, dmin, d98 or a guaranteed attained resolution.','sharped_server_client._upload_job'),
('bestdensities_metric','Important clarification','Superflip best-density selection criterion',
 'This selects retained native density attempts. It differs from Phase Studio candidate recommendation and from map feedback magnitude. reference and symmetry are distinct criteria.','write_superflip_inflip; result_selection recommendation'),
('workflow_preset','Optional stylistic improvement','Starting-parameter preset',
 'Recommended can imply scientific endorsement. Presets are editable initial values; preserve all numerical values and clearly state their scope and that existing untouched settings can persist.','_apply_workflow_preset'),
]
findings=[];checklist=['# Proposed text changes','','All owner decisions are **Pending**. No proposal in this file has been applied to the application. Scientific algorithm decisions are separate from wording approval.','']
review=['# Terminology review','','The 20 highest-priority findings below are a reviewed subset of the extracted inventory. The full application wording has **not** received individual scientific sign-off. No numerical/default/configuration changes are authorized by this terminology review.','',
 '## Critical scientific corrections','',
 'The FWHM-mode input ratio filter is a scientific behavior defect, not merely a label defect. The old `Initial atomic model: {len(ref_ctx.atoms)} sites` log message also counts reference-context sites, not proven initialization. The historical run had no first-cycle modelfile; referencefile aligned output density. See [run provenance audit](../../RUN_PROVENANCE_2_0_7.md) for exact evidence and qualifications.','',
 '## Highest-priority owner decisions','']
for n,(key,severity,suggestion,reason,symbol) in enumerate(rows,1):
    row=settings[key];identifier=f'UI-{n:03}'
    finding=dict(id=identifier,setting=key,current=row['label'],suggested=suggestion,severity=severity,reason=reason,backend_symbols=symbol,owner_decision='Pending')
    findings.append(finding)
    classification='Scientific correction' if severity.startswith('Critical') else 'Consistency' if severity.startswith('Consistency') else 'Clarity'
    checklist += [f'## {identifier} — {row["label"]}','','Current:','',f'`{row["label"]}`','','Suggested:','',f'`{suggestion}`','','Reason:','',reason,'','Classification:','',classification,'','Owner decision:','','`Pending`','']
    review += [f'### {identifier}: {row["label"]}','','Severity: '+severity+'.','',
        'Original: `'+row['label']+'`. Proposed: `'+suggestion+'`.','',reason,'',
        'Implementation to inspect: `'+symbol+'`. Setting key: `'+key+'`. Exact controls/options/defaults are in settings.json; source helper calls and backend configuration are in settings-source.json.','']
review += ['## Metric and structural terminology checked against implementation','',
 'F0.5 is the peak-matching F score with β=0.5: `(1+β²)PR/(β²P+R)`. It is not a phase figure of merit. Matched-peak RMSD uses matched sites and angstrom; unmatched sites must be reported separately. The weighted reference phase-agreement statistic, map correlations and R factors are different quantities. Reference-free and reference-backed ranking use the existing map_quality validation profiles; a recommendation is not a guarantee of structural correctness.','',
 'Asymmetric unit, molecule and unit cell are different objects. The real P21/c reference has Z=8 and Z′=2, with 70 independent heavy sites in two molecules; one-molecule mode must not imply that the ASU always contains one molecule. Opt-in comparison alignment retains all independent heavy sites and reports geometric components without claiming chemical identity.','',
 'Legacy avg_intensity_change_per_group is an equal-weight average of group means of member-wise absolute relative changes, using only original intensities >1e-12. It is neither total-intensity change nor accuracy; weak denominators can yield >1000%. Signed and absolute changes, stage and cumulative comparisons, and N→N+1 assignment remain distinct.','',
 'Reflection completeness, allowed HKL and indexed peak coverage have different denominators. Resolution dmin is a reciprocal-space cutoff; d98 is a distribution percentile determined by its existing implementation, not a universal substitute for the diffraction limit. These labels require denominator/method context wherever shown.','',
 'FWHM in the powder branch is in degrees of 2θ. Sigma(I) and sigma(F) are measurement uncertainties, and EDMA peak sigma is a map-density threshold. None is interchangeable with another. Intensity I and amplitude F are converted only by the existing declared-mode pathways; the audit does not alter them.','',
 '## Primary references','',
 '* [IUCr powder dictionary, FWHM and angular units](https://www.iucr.org/__data/iucr/cif/dictionaries/cif_pd_1.0.1.dic.pdf).',
 '* [IUCr Z and Z′](https://dictionary.iucr.org/Z_and_Z%27).',
 '* [Superflip manual: modelfile, randomseed, referencefile](https://superflip.fzu.cz/download/superflip_user_manual.pdf).',
 '* [IUCr statistical nomenclature recommendations](https://www.iucr.org/resources/commissions/crystallographic-nomenclature/statdes/recomm.html).','',
 '## Coverage and unverified states','',
 'See coverage.json for counts. Static extraction retains every non-docstring Python string literal and dynamic f-string template from phase_studio/*.py in static-literals.json, with source/line/symbol/context. The main table is a conservative candidate subset; unclassified literals remain searchable for residual review. It can contain UI helper internal arguments and does not prove display reachability.','',
 'Runtime inspection covers the shared configuration, Result Selection in standalone and Jana contexts, and Autosolve on controlled local completed-result fixtures. All registered 87 main configuration settings are captured with exact displayed options/internal values, numerical ranges/steps/precision/sentinel text, pre-persistence defaults, current fixture values, tooltips and persistence keys. Preset differences and the full RunConfig definition are retained separately. Personal persisted defaults and credentials were deliberately not read.','',
 'The following remain unverified at runtime: first-run onboarding/update/error dialogs; every Wizard transition; live server catalog/authentication and account-dependent states; every native failure/holdout/experimental branch; native Superflip/EDMA/Jana-owned text; OS file dialogs; post-install frozen-profile-only differences; non-main configurable controls and all secondary context-menu states. These are covered only where static literals or existing GUI authority tests provide evidence. There is no single exact count of unreachable dynamic states; these eight families are explicitly open. Per-setting backend/dependency/persistence semantics beyond the reviewed findings still need individual sign-off.','',
 '**Coverage status: substantial review package, not a certified exhaustive semantic audit.** The inventories explicitly mark unresolved rows Not verified. No blanket OK labels or fabricated runtime coverage are used. Approval of individual wording changes does not resolve these coverage gaps or the scientific filter defect.','']
(OUT/'findings.json').write_text(json.dumps(findings,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
(OUT/'PROPOSED_TEXT_CHANGES.md').write_text('\n'.join(checklist),encoding='utf8')
(OUT/'TERMINOLOGY_REVIEW.md').write_text('\n'.join(review),encoding='utf8')
