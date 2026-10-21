"""Check the actual frozen helper, profiles, ownership inventory and ZIP."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from PyInstaller.archive.readers import CArchiveReader
from phase_studio.update_manifest import UpdateAsset,TRUSTED_KEYS
from phase_studio.update_package import extract_jana_package
from phase_studio.update_transaction import verify_inventory


def probe(executable,flag,output):
    environment=os.environ|{'QT_QPA_PLATFORM':'offscreen','PHASE_STUDIO_STARTUP_PROBE':'1'}
    result=subprocess.run([str(executable),flag,str(output)],capture_output=True,text=True,timeout=90,
        env=environment,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:raise ValueError('Frozen runtime check failed.')
    return json.loads(output.read_text(encoding='utf8'))


def verify(dist,version):
    dist=Path(dist).resolve()
    standalone=dist/'release'/f'PhaseStudio-{version}-x64.exe'
    jana=dist/f'PhaseStudio-Jana2020-{version}'/'Phase_studio.exe'
    helper=ROOT/'build/updater/PhaseStudioUpdater.exe'
    reader=CArchiveReader(str(helper));pyz=reader.open_embedded_archive('PYZ.pyz')
    if {'phase_studio.app','PySide6','numpy','gemmi','matplotlib'} & set(pyz.toc):
        raise ValueError('Updater imports GUI/scientific runtime.')
    trust=pyz.extract('phase_studio.update_trust').co_consts
    with tempfile.TemporaryDirectory(dir=dist) as directory:
        temp=Path(directory)
        if temp.parent.resolve()!=dist:raise ValueError('Invalid verification workspace.')
        report=probe(helper,'--self-check',temp/'helper.json')
        if report!={'protocol':1,'public_install_enabled':bool(TRUSTED_KEYS),'frozen':True}:
            raise ValueError('Frozen helper configuration differs.')
        for profile,exe in [('standalone-onefile',standalone),('jana2020-onedir',jana)]:
            image=CArchiveReader(str(exe));modules=image.open_embedded_archive('PYZ.pyz')
            if modules.extract('phase_studio.update_trust').co_consts!=trust:
                raise ValueError('Application and updater trust keys differ.')
            result=probe(exe,'--update-runtime-check',temp/(profile+'.json'))
            if not result.get('ok') or result.get('profile')!=profile or result.get('version')!=version:
                raise ValueError('Frozen distribution profile or version differs.')
            if result['helper_sha256']!=hashlib.sha256(helper.read_bytes()).hexdigest():
                raise ValueError('Bundled helper differs from authoritative helper.')
        verify_inventory(jana.parent/'_internal')
        archive=dist/'release'/f'PhaseStudio-Jana2020-{version}.zip'
        asset=UpdateAsset('jana2020-onedir',archive.name,archive.stat().st_size,hashlib.sha256(archive.read_bytes()).hexdigest())
        extracted=extract_jana_package(archive,temp/'extracted',asset,version)
        verify_inventory(extracted/'_internal')
        result=probe(extracted/'Phase_studio.exe','--update-runtime-check',temp/'extracted.json')
        if not result.get('ok'):raise ValueError('Extracted Jana runtime cannot start.')
    print('PASS: independent helper, pinned trust parity, both frozen profiles and complete extracted Jana runtime.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--dist',type=Path,required=True);parser.add_argument('--version',required=True)
    args=parser.parse_args();verify(args.dist,args.version)
