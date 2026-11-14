import importlib.util
import subprocess
from pathlib import Path
import gemmi
import numpy as np
import pytest
from phase_studio import app as a


@pytest.mark.parametrize('ccp4,jana,primary',[(True,False,'xplor'),(False,True,'xplor'),
    (True,True,'xplor'),(False,False,'ccp4'),(False,False,'jana'),(False,False,'m80')])
def test_native_export_format_matches_each_filename(tmp_path,ccp4,jana,primary):
    executable=Path('C:/Jana2020/SUPERFLIP/superflip.exe')
    if not executable.exists():pytest.skip('Actual native Superflip unavailable')
    spec=importlib.util.spec_from_file_location('native_export_fixture',Path(__file__).resolve().parents[1]/'packaging/tools/verify_fwhm_policy_207.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    mode=a.REFLECTION_DATA_MODE_INTENSITY
    helper.native_case(executable,tmp_path,mode,export_ccp4=ccp4,export_jana=jana,output_format=primary)
    folder=tmp_path/mode.replace(' ','_')
    xmap=a.read_xplor_map(folder/'check.xplor')
    if ccp4 or primary=='ccp4':
        native=gemmi.read_ccp4_map(str(folder/'check.ccp4'));native.setup(0.)
        actual=np.array(native.grid,copy=True).transpose(2,1,0).ravel()
        # Native WriteXPlor uses Fortran E12.5: five significant mantissa
        # digits. Derive the half-last-decimal bound per voxel; CCP4 is float32.
        magnitude=np.abs(xmap.data)
        exponent=np.floor(np.log10(np.where(magnitude>0,magnitude,1.)))
        decimal_bound=np.where(magnitude>0,.5*np.power(10.,exponent-4),0.)
        bound=decimal_bound+np.abs(actual)*np.finfo(np.float32).eps+1e-14
        assert actual.shape==xmap.data.shape
        assert np.all(np.abs(actual-xmap.data)<=bound)
    if jana or primary=='jana':
        produced=(folder/'check.m81').read_bytes()
        # A separately generated native Jana output is the format authority.
        source=(folder/'check.inflip').read_text()
        lines=source.splitlines()
        lines=[('outputfile authority.m81' if line.startswith('outputfile ') else
                'outputformat jana' if line.startswith('outputformat ') else line) for line in lines]
        control=folder/'authority.inflip';control.write_text('\n'.join(lines)+'\n')
        result=subprocess.run([str(executable),control.name],cwd=folder,capture_output=True,timeout=30)
        assert result.returncode==0
        assert produced==(folder/'authority.m81').read_bytes()
    if primary=='m80':assert (folder/'check.m80').stat().st_size>0
