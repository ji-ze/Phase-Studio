"""Actual distribution detection and consent-driven authenticated preparation."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import http.client
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import threading
import time
from urllib.parse import quote,urlsplit

from .version import VERSION
from .update_checker import REPOSITORY,parse_version
from .update_manifest import TRUSTED_KEYS,verify_manifest,UpdateVerificationError,MAX_MANIFEST_BYTES
from .update_download import download,DownloadCancelled,validate_download_url
from .update_transaction import digest,reject_links,verify_inventory


@dataclass(frozen=True)
class Installation:
    profile:str
    executable:Path
    helper:Path
    helper_sha256:str


def installation(*,executable=None,resource=None,frozen=None):
    if not (getattr(sys,'frozen',False) if frozen is None else frozen):
        raise UpdateVerificationError('Automatic installation is available in the Windows distribution only.')
    executable=reject_links(Path(executable or sys.executable).absolute())
    resource=Path(resource or Path(__file__).parent)
    try:
        if (resource/'distribution.json').stat().st_size>4096:raise ValueError
        marker=json.loads((resource/'distribution.json').read_text(encoding='utf8'))
        if set(marker)!={'schema','profile','version','helper_sha256'} or marker['schema']!=1 or marker['version']!=VERSION:
            raise ValueError
        profile=marker['profile']
        if profile not in ('standalone-onefile','jana2020-onedir'):raise ValueError
        helper=reject_links(resource/'updater/PhaseStudioUpdater.exe')
        if not helper.is_file() or digest(helper)!=marker['helper_sha256']:raise ValueError
        if profile=='jana2020-onedir':
            if executable.name!='Phase_studio.exe' or resource.resolve()!= (executable.parent/'_internal/phase_studio').resolve():raise ValueError
            if not (executable.parent/'_internal/phase_studio/installation.json').is_file():raise ValueError
        return Installation(profile,executable,helper,marker['helper_sha256'])
    except (OSError,ValueError,KeyError,TypeError):
        raise UpdateVerificationError('This installation has no valid updater ownership metadata. Use the one-time manual migration.') from None


def public_installation_status():
    if not TRUSTED_KEYS:return False,'Automatic installation is not configured. Version checks and manual downloads remain available.'
    try:installation();return True,''
    except UpdateVerificationError as exc:return False,str(exc)


def frozen_check(output):
    report={'version':VERSION,'ok':False,'public_install_enabled':bool(TRUSTED_KEYS)}
    try:
        current=installation()
        report.update(ok=True,profile=current.profile,helper_sha256=current.helper_sha256)
    except UpdateVerificationError as exc:report['reason']=str(exc)
    Path(output).write_text(json.dumps(report,sort_keys=True),encoding='utf8')
    return 0 if report['ok'] else 1


@dataclass(frozen=True)
class ReleaseOffer:
    version:str
    published:str
    notes:str
    assets:dict


def fetch_offer(expected_version,*,connection_factory=None):
    factory=connection_factory or http.client.HTTPSConnection
    connection=factory('api.github.com',timeout=15,context=ssl.create_default_context())
    try:
        connection.request('GET',f'/repos/{REPOSITORY}/releases/latest',headers={
            'User-Agent':f'PhaseStudio/{VERSION}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
        response=connection.getresponse()
        if response.status!=200:raise UpdateVerificationError('GitHub release information is temporarily unavailable.')
        raw=response.read(2*1024*1024+1)
        if len(raw)>2*1024*1024:raise ValueError
        data=json.loads(raw.decode('utf8'))
        version=parse_version(data.get('tag_name'))
        if (data.get('draft') is not False or data.get('prerelease') is not False or version is None
                or '.'.join(map(str,version))!=expected_version or not data.get('published_at')):
            raise UpdateVerificationError('The release changed or is not stable. Check for updates again.')
        from datetime import datetime
        published=datetime.fromisoformat(data['published_at'].replace('Z','+00:00'))
        if published.tzinfo is None:raise ValueError
        expected={f'PhaseStudio-{expected_version}-x64.exe',f'PhaseStudio-Jana2020-{expected_version}.zip',
            'release-manifest.json','release-manifest.sig','SHA256SUMS.txt',f'RELEASE_NOTES_{expected_version}.md'}
        records=data['assets']
        if not isinstance(records,list) or len(records)!=6:raise ValueError
        assets={}
        for item in records:
            name=item['name'];size=item['size'];url=item['browser_download_url']
            if name not in expected or name in assets or type(size) is not int or not 0<size<=1024*1024*1024:raise ValueError
            validate_download_url(url)
            prefix=f'/{REPOSITORY}/releases/download/{quote(data["tag_name"],safe="")}/{quote(name,safe="")}'
            if urlsplit(url).path!=prefix:raise ValueError
            assets[name]={'name':name,'size':size,'url':url}
        if set(assets)!=expected:raise ValueError
        notes=data.get('body') or ''
        if not isinstance(notes,str):raise ValueError
        return ReleaseOffer(expected_version,data['published_at'],notes[:16000],assets)
    except (ValueError,KeyError,TypeError,UnicodeError,OSError,http.client.HTTPException) as exc:
        if isinstance(exc,UpdateVerificationError):raise
        raise UpdateVerificationError('The release does not provide a complete supported update package.') from None
    finally:connection.close()


def clean_environment():
    allowed={'SYSTEMROOT','WINDIR','COMSPEC','PATH','TEMP','TMP','LOCALAPPDATA','APPDATA','USERPROFILE',
        'USERNAME','USERDOMAIN','PROGRAMDATA','PROGRAMFILES','PROGRAMFILES(X86)','HOMEDRIVE','HOMEPATH',
        'QT_QPA_PLATFORM','QT_SCALE_FACTOR'}
    return {key:value for key,value in os.environ.items() if key.upper() in allowed}


class UpdateSession:
    def __init__(self,version,*,jana=False):
        self.version=version;self.jana=bool(jana);self.cancel=threading.Event()
        self.current=installation();self.workspace=None;self.offer=None;self.manifest=None
        if not TRUSTED_KEYS:raise UpdateVerificationError('No public release verification key is configured. Installation is disabled.')
        if parse_version(version) is None or parse_version(version)<=parse_version(VERSION):
            raise UpdateVerificationError('No newer supported release is available.')

    def stop(self):
        self.cancel.set()
        if self.workspace is not None:
            try:(self.workspace/'cancelled').touch(exist_ok=True)
            except OSError:pass

    def prepare(self,progress):
        from .update_plan import create_workspace
        self.offer=fetch_offer(self.version)
        self.workspace=create_workspace()
        def fetch(name,maximum):
            item=self.offer.assets[name]
            if item['size']>maximum:raise UpdateVerificationError('Update metadata exceeds its size limit.')
            progress('Downloading '+name,0,item['size'])
            return download(item['url'],self.workspace/name,expected_size=item['size'],cancel=self.cancel,
                progress=lambda done,total:progress('Downloading '+name,done,total))
        manifest=fetch('release-manifest.json',MAX_MANIFEST_BYTES)
        signature=fetch('release-manifest.sig',64)
        progress('Verifying release signature',0,0)
        self.manifest=verify_manifest(manifest.read_bytes(),signature.read_bytes(),release_version=self.version)
        checksums=fetch('SHA256SUMS.txt',4096).read_text(encoding='ascii')
        expected=''.join(f'{asset.sha256}  {asset.name}\n' for asset in self.manifest.assets)
        if checksums!=expected:raise UpdateVerificationError('Checksums do not match the authenticated manifest.')
        asset=self.manifest.asset(self.current.profile)
        if self.offer.assets[asset.name]['size']!=asset.size:raise UpdateVerificationError('GitHub asset size differs from signed metadata.')
        package=fetch(asset.name,1024*1024*1024)
        progress('Verifying downloaded package',0,0)
        from .update_package import verify_package
        verify_package(package,asset)
        if asset.profile=='jana2020-onedir':
            import zipfile
            from .update_package import _members
            with zipfile.ZipFile(package) as archive:
                files=_members(archive,self.version)
                metadata=f'PhaseStudio-Jana2020-{self.version}/_internal/phase_studio/installation.json'
                if archive.getinfo(metadata).file_size>2*1024*1024:raise UpdateVerificationError('Runtime ownership metadata is too large.')
                inventory=json.loads(archive.read(metadata).decode('utf8'))
                expected={str(relative)[len('_internal/'):] for _entry,relative in files
                    if str(relative).startswith('_internal/') and str(relative)!='_internal/phase_studio/installation.json'}
                if inventory.get('schema')!=1 or set(inventory.get('files',{}))!=expected:
                    raise UpdateVerificationError('The package has no complete runtime ownership inventory.')
        if self.cancel.is_set():raise DownloadCancelled()
        progress('Ready to install',asset.size,asset.size)
        return self.offer

    def launch_helper(self):
        if self.manifest is None:raise UpdateVerificationError('No authenticated package is ready.')
        if self.cancel.is_set():raise DownloadCancelled()
        from .update_plan import write_plan
        from .update_windows import process_identity,process_entries
        from .update_transaction import _journal_path
        if _journal_path(self.current.executable).exists():
            raise UpdateVerificationError('An interrupted update needs recovery before another update can start. See the recovery instructions.')
        original=process_identity(os.getpid())
        if os.path.normcase(original.executable)!=os.path.normcase(str(self.current.executable)):
            raise UpdateVerificationError('The running process does not own this installation.')
        parents=[original]
        try:
            outer=process_identity(os.getppid())
            if os.path.normcase(outer.executable)==os.path.normcase(original.executable):parents.append(outer)
        except UpdateVerificationError:pass
        jana_wait=[]
        if self.jana:
            for pid,(_parent,name) in process_entries().items():
                if name.casefold().startswith('jana') and name.lower().endswith('.exe'):
                    jana_wait.append(process_identity(pid))
            if len(jana_wait)>8:raise UpdateVerificationError('Close Jana2020 instances before preparing this update.')
        copied=self.workspace/'PhaseStudioUpdater.exe'
        if digest(self.current.helper)!=self.current.helper_sha256:raise UpdateVerificationError('Bundled updater changed.')
        shutil.copyfile(self.current.helper,copied)
        if digest(copied)!=self.current.helper_sha256:raise UpdateVerificationError('Copied updater integrity failed.')
        asset=self.manifest.asset(self.current.profile)
        plan={'schema':1,'session':self.workspace.name,'created':time.time(),
            'target':str(self.current.executable),'old_sha256':digest(self.current.executable),'profile':self.current.profile,
            'version':self.version,'source_version':VERSION,'manifest':base64.b64encode((self.workspace/'release-manifest.json').read_bytes()).decode('ascii'),
            'signature':base64.b64encode((self.workspace/'release-manifest.sig').read_bytes()).decode('ascii'),
            'package':str(self.workspace/asset.name),'parents':[p.json() for p in parents],
            'jana_wait':[p.json() for p in jana_wait],'cwd':str(Path.cwd().resolve()),
            'restart':not self.jana,'jana':self.jana,'helper_sha256':self.current.helper_sha256}
        path=write_plan(self.workspace,plan)
        (self.workspace/'Recover update.cmd').write_text('@echo off\r\n"%~dp0PhaseStudioUpdater.exe" --recover-plan "%~dp0update.psupdate"\r\n',encoding='ascii')
        subprocess.Popen([str(copied),'--apply-plan',str(path)],cwd=self.workspace,env=clean_environment(),
            creationflags=subprocess.CREATE_NO_WINDOW,close_fds=True)
        deadline=time.monotonic()+120  # Includes explicit UAC consent; no application is closed yet.
        while time.monotonic()<deadline:
            result=self.workspace/'update-result.json'
            if result.exists():
                document=json.loads(result.read_text(encoding='utf8'))
                if not document.get('ok'):raise UpdateVerificationError(document.get('message','Update helper could not start.'))
            ready=self.workspace/'helper-ready.json'
            if ready.exists():
                document=json.loads(ready.read_text(encoding='utf8'))
                if document.get('session')!=self.workspace.name:raise UpdateVerificationError('Updater readiness identity differs.')
                helper=process_identity(document['pid'])
                if Path(helper.executable).resolve()!=copied.resolve():raise UpdateVerificationError('Another process reported updater readiness.')
                return document
            if self.cancel.is_set():
                # Do not kill an elevated helper. Leaving the original application
                # open makes its bounded parent wait expire without replacement.
                raise DownloadCancelled()
            threading.Event().wait(.1)
        raise UpdateVerificationError('The updater did not become ready. Keep Phase Studio open and try again later.')
