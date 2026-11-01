"""Independent Bragg-law check of diagnostic-only metadata fallback."""
import math
from dataclasses import replace
from phase_studio import app as a


def test_wizard_diagnostics_snapshot_current_reference_and_wavelength(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from phase_studio import jana_superflip as js
    from phase_studio.jana_superflip import _JanaWorkflowWizard
    installation = tmp_path / 'Jana'
    (installation / 'SUPERFLIP').mkdir(parents=True)
    (installation / 'SUPERFLIP/superflip.exe').write_bytes(b'Path fixture; never executed')
    monkeypatch.setattr(js, 'application_dir', lambda: installation)
    source = tmp_path / 'sample.inflip'
    source.write_text('dimension 3\ncell 10 10 10 90 90 90\nspacegroup P1\ncomposition C2\ndataformat intensity fwhm\nfbegin\n1 0 0 10 .1\n2 0 0 20 .1\nendf\n')
    reference = tmp_path / 'reference.cif'
    reference.write_text('data_ref\n_diffrn_radiation_wavelength 0.39986\n')
    state = SimpleNamespace(inflip_path=source,
        reference_file=SimpleNamespace(text=lambda: str(reference)),
        powder_wavelength_spin=SimpleNamespace(value=lambda: .61))
    request = _JanaWorkflowWizard._hkl_diagnostic_request(state)
    request.work_text = str(tmp_path / 'work')
    result = a.build_hkl_load_result(request)
    assert request.ref_text == str(reference) and request.powder_wavelength == .61
    assert request.metadata.source == a.METADATA_SOURCE_INFLIP
    overlap = dict(result.diagnostics.overlap)
    assert overlap['wavelength'] == .61 and overlap['wavelength_source'] == 'manual entry'


def test_reference_wavelength_fallback_and_cache(tmp_path):
    source = tmp_path / 'sample.inflip'
    source.write_text('dimension 3\ncell 10 10 10 90 90 90\nspacegroup P1\ncomposition C2\ndataformat intensity fwhm\nfbegin\n1 0 0 10 .1\n2 0 0 20 .1\nendf\n')
    ref = tmp_path / 'reference.cif'
    ref.write_text('data_ref\n_diffrn_radiation_wavelength 0.39986\n')
    original = source.read_bytes()
    request = a.build_hkl_analysis_request_from_inflip(source, ref, tmp_path / 'work')
    result = a.build_hkl_load_result(request)
    overlap = dict(result.diagnostics.overlap)
    assert overlap['wavelength'] == .39986
    assert 'reference file' in overlap['wavelength_source']
    # Independent Bragg-law calculation for cubic (100), d = a = 10 Å.
    expected = 2 * math.asin(.39986 / 20) * 180 / math.pi
    assert math.isclose(a.bragg_two_theta_deg(10, overlap['wavelength']), expected, abs_tol=1e-12)
    ref.write_text('data_ref\n_diffrn_radiation_wavelength 0.51234567\n')
    updated = a.build_hkl_load_result(request)
    assert updated is not result
    assert dict(updated.diagnostics.overlap)['wavelength'] == .51234567
    entered = a.build_hkl_load_result(replace(request, powder_wavelength=.61))
    assert dict(entered.diagnostics.overlap)['wavelength'] == .61
    # Existing incoming metadata priority and every reflection remain intact.
    source.write_text(source.read_text().replace('dimension 3', 'dimension 3\nlambda 1.2'))
    incoming = a.build_hkl_load_result(request)
    assert dict(incoming.diagnostics.overlap)['wavelength'] == 1.2
    assert [(r.h, r.value, r.sigma) for r in result.reflections] == [(1, 10, .1), (2, 20, .1)]
    assert original.decode().splitlines() == [line for line in source.read_text().splitlines() if line != 'lambda 1.2']


