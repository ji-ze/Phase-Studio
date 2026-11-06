import pytest
from phase_studio import app as a


@pytest.mark.parametrize('quantity',['amplitude','intensity'])
@pytest.mark.parametrize('auxiliary',[' dummy',''])
def test_native_dummy_is_not_a_measurement_uncertainty(tmp_path,quantity,auxiliary):
    source=tmp_path/'source.inflip'
    source.write_text(f'dataformat {quantity}{auxiliary}\nfbegin\n1 0 0 12 0.1\nendf\n')
    extracted=a.extract_embedded_hkl_from_inflip(source,tmp_path/'work')
    row=a.read_hkl(extracted)[0]
    assert row.value==12
    assert row.sigma is None, 'Superflip dummy has no declared measurement-uncertainty meaning'
    mode=a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA if quantity=='amplitude' else a.REFLECTION_DATA_MODE_INTENSITY
    with pytest.raises(ValueError,match='uncertaint'):
        a.write_observed_reflections(tmp_path/'filtered.hkl',[row],2,mode)
    with pytest.raises(ValueError,match='uncertaint'):
        a.write_standardized_hkl_with_phase(tmp_path/'phased.hkl',[row],0,mode)


@pytest.mark.parametrize('auxiliary',['',' dummy'])
def test_native_phases_without_sigma_are_converted_to_degrees(tmp_path,auxiliary):
    source=tmp_path/'source.inflip'
    source.write_text('dataformat amplitude phase'+auxiliary+'\nfbegin\n1 0 0 12 0.25'+(' 123' if auxiliary else '')+'\nendf\n')
    path=a.extract_embedded_hkl_from_inflip(source,tmp_path/'work')
    row=a.read_hkl(path,4,6,True)[0]
    assert row.phase==90
    assert row.sigma is None


@pytest.mark.parametrize('layout',['intensity sigma fwhm','amplitude dummy fwhm','phase amplitude','intensity group'])
def test_unsupported_native_columns_are_rejected_before_extraction(tmp_path,layout):
    source=tmp_path/'source.inflip'
    source.write_text(f'dataformat {layout}\nfbegin\n1 0 0 12 1 2\nendf\n')
    output=tmp_path/'work'
    with pytest.raises(ValueError,match='Unsupported native reflection dataformat'):
        a.extract_embedded_hkl_from_inflip(source,output)
    assert not output.exists()
