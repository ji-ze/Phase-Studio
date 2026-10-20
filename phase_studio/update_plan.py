"""User-bound DPAPI update plans and private temporary workspaces."""
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import subprocess
import csv
import uuid

from .update_manifest import UpdateVerificationError


def workspace_root():
    if os.name!='nt' or not os.environ.get('LOCALAPPDATA'):
        raise UpdateVerificationError('Windows user-local update storage is unavailable.')
    return Path(os.environ['LOCALAPPDATA'])/'PhaseStudio'/'Updates'


def create_workspace():
    from .update_transaction import reject_links
    root=workspace_root();reject_links(root);root.mkdir(parents=True,exist_ok=True)
    directory=root/str(uuid.uuid4());directory.mkdir()
    result=subprocess.run(['whoami','/user','/fo','csv','/nh'],capture_output=True,text=True,check=True)
    sid=next(csv.reader(result.stdout.splitlines()))[1]
    subprocess.run(['icacls',str(directory),'/inheritance:r','/grant:r',f'*{sid}:(OI)(CI)F'],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
    return directory


class _Blob(ctypes.Structure):
    _fields_=[('size',w.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data,protect):
    if os.name!='nt':raise UpdateVerificationError('DPAPI update plans require Windows.')
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    free=kernel.LocalFree;free.argtypes=[ctypes.c_void_p];free.restype=ctypes.c_void_p
    storage=ctypes.create_string_buffer(data);incoming=_Blob(len(data),ctypes.cast(storage,ctypes.POINTER(ctypes.c_ubyte)))
    entropy_bytes=b'PhaseStudio/update-plan/v1'
    entropy_buffer=ctypes.create_string_buffer(entropy_bytes)
    entropy=_Blob(len(entropy_bytes),ctypes.cast(entropy_buffer,ctypes.POINTER(ctypes.c_ubyte)))
    outgoing=_Blob()
    if protect:
        function=crypt.CryptProtectData
        function.argtypes=[ctypes.POINTER(_Blob),w.LPCWSTR,ctypes.POINTER(_Blob),ctypes.c_void_p,ctypes.c_void_p,w.DWORD,ctypes.POINTER(_Blob)]
        args=(ctypes.byref(incoming),'Phase Studio update',ctypes.byref(entropy),None,None,1,ctypes.byref(outgoing))
    else:
        function=crypt.CryptUnprotectData
        function.argtypes=[ctypes.POINTER(_Blob),ctypes.c_void_p,ctypes.POINTER(_Blob),ctypes.c_void_p,ctypes.c_void_p,w.DWORD,ctypes.POINTER(_Blob)]
        args=(ctypes.byref(incoming),None,ctypes.byref(entropy),None,None,1,ctypes.byref(outgoing))
    function.restype=w.BOOL
    if not function(*args):raise UpdateVerificationError('The update plan could not be authenticated for this Windows user.')
    try:return ctypes.string_at(outgoing.data,outgoing.size)
    finally:free(outgoing.data)


def write_plan(directory,document):
    path=Path(directory)/'update.psupdate'
    encoded=json.dumps(document,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')
    with path.open('xb') as stream:stream.write(_crypt(encoded,True))
    return path


def read_plan(path):
    from .update_transaction import reject_links
    path=reject_links(Path(path).absolute())
    root=workspace_root().resolve()
    if path.name!='update.psupdate' or path.parent.parent.resolve()!=root:
        raise UpdateVerificationError('Update plan is outside its private workspace.')
    if str(uuid.UUID(path.parent.name))!=path.parent.name or path.stat().st_size>2*1024*1024:
        raise UpdateVerificationError('Invalid update plan identity or size.')
    try:
        document=json.loads(_crypt(path.read_bytes(),False).decode('utf8'))
        if not isinstance(document,dict) or document.get('schema')!=1 or document.get('session')!=path.parent.name:raise ValueError
        return document
    except (ValueError,UnicodeError):raise UpdateVerificationError('Invalid authenticated update plan.') from None
