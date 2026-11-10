"""Normalize only reviewed readiness/metadata additions; retain numerical ASTs."""
import ast


def restore_reviewed_readiness(node):
    def block(current, historical):
        expected = ast.parse(current).body
        matches = [i for i in range(len(node.body) - len(expected) + 1)
                   if list(map(ast.dump, node.body[i:i + len(expected)])) == list(map(ast.dump, expected))]
        assert len(matches) == 1, (node.name, 'reviewed block changed')
        i = matches[0]
        node.body[i:i + len(expected)] = ast.parse(historical).body

    if node.name == 'normalize_reflection_data_mode':
        block('if raw == "h k l · F · σ(F)":\n return REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA', '')
        aliases = [n for n in ast.walk(node) if isinstance(n, ast.Dict)
                   and any(isinstance(k, ast.Constant) and k.value == 'hkl_f_measured_sigma' for k in n.keys)]
        assert len(aliases) == 1
        aliases = aliases[0]
        for key in ('hkl_f_measured_sigma', 'amplitude_measured_sigma'):
            indices = [i for i, k in enumerate(aliases.keys) if isinstance(k, ast.Constant) and k.value == key]
            assert len(indices) == 1
            i = indices[0]
            assert ast.dump(aliases.values[i]) == ast.dump(ast.Name(id='REFLECTION_DATA_MODE_AMPLITUDE_MEASURED_SIGMA', ctx=ast.Load()))
            del aliases.keys[i], aliases.values[i]
    counts = {'normalize_reflection_data_mode': 1, 'reflection_mode_is_amplitude': 1,
              'map_feedback_intensity_significance': 2}
    if node.name in counts:
        found = 0
        for group in [n for n in ast.walk(node) if isinstance(n, ast.Set)]:
            additions = [n for n in group.elts if isinstance(n, ast.Name)
                         and n.id == 'REFLECTION_DATA_MODE_AMPLITUDE_MEASURED_SIGMA']
            if additions:
                assert len(additions) == 1
                assert any(isinstance(n, ast.Name) and n.id == 'REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA' for n in group.elts)
                group.elts.remove(additions[0]); found += 1
        assert found == counts[node.name]
    if node.name == 'observed_hkl_name_for_mode':
        current = ast.parse('mode in (REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA, REFLECTION_DATA_MODE_AMPLITUDE_MEASURED_SIGMA)', mode='eval').body
        condition = node.body[1]
        assert isinstance(condition, ast.If) and ast.dump(condition.test) == ast.dump(current)
        condition.test = ast.parse('mode == REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA', mode='eval').body
    if node.name == 'filtered_reflections':
        block('from phase_studio.reflection_readiness import validate_loaded_significance\n'
              'validate_loaded_significance(data_mode, threshold, reflections)',
              'validate_reflection_filter_policy(data_mode,threshold)\n'
              'if threshold>0 and reflections and not any(r.sigma is not None and math.isfinite(float(r.sigma)) and r.sigma>0 for r in reflections):\n'
              " raise ValueError('Significance filtering requires genuine finite positive measurement uncertainties. Set Minimum observed value/σ to 0 for uncertainty-free input, or supply sigma(I)/sigma(F).')")
    if node.name == 'extract_embedded_hkl_from_inflip':
        block("source_stem = Path(inflip_path).stem\n"
              "if len(source_stem) > 64:\n import hashlib\n source_stem = source_stem[:40] + '_' + hashlib.sha256(Path(inflip_path).name.encode('utf8')).hexdigest()[:12]\n"
              'out = output_dir / f"{source_stem}_embedded_reflections.hkl"',
              'out = output_dir / f"{Path(inflip_path).stem}_embedded_reflections.hkl"')
