"""Frozen distribution identity and the independent, prebuilt updater."""
import hashlib
import json
from pathlib import Path


def updater_datas(project_dir,profile,version):
    project_dir=Path(project_dir)
    if profile not in ('standalone-onefile','jana2020-onedir'):return []
    helper=project_dir/'build/updater/PhaseStudioUpdater.exe'
    if not helper.is_file():raise FileNotFoundError('Build the independent updater before the public distribution.')
    generated=project_dir/'build'/('profile-'+profile);generated.mkdir(parents=True,exist_ok=True)
    marker=generated/'distribution.json'
    marker.write_text(json.dumps({'schema':1,'profile':profile,'version':version,
        'helper_sha256':hashlib.sha256(helper.read_bytes()).hexdigest()},sort_keys=True),encoding='utf8')
    return [(str(marker),'phase_studio'),(str(helper),'phase_studio/updater')]
