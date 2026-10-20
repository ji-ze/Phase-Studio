"""Windows process identities and an owned restart job; never kills Jana jobs."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as w
from dataclasses import dataclass,asdict
import os
from pathlib import Path
import subprocess

from .update_manifest import UpdateVerificationError

if os.name=='nt':
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    def bind(name,result,args):
        function=getattr(kernel,name);function.restype=result;function.argtypes=args;return function
    OpenProcess=bind('OpenProcess',w.HANDLE,[w.DWORD,w.BOOL,w.DWORD])
    CloseHandle=bind('CloseHandle',w.BOOL,[w.HANDLE])
    QueryImage=bind('QueryFullProcessImageNameW',w.BOOL,[w.HANDLE,w.DWORD,w.LPWSTR,ctypes.POINTER(w.DWORD)])
    GetTimes=bind('GetProcessTimes',w.BOOL,[w.HANDLE,*([ctypes.POINTER(w.FILETIME)]*4)])
    Wait=bind('WaitForSingleObject',w.DWORD,[w.HANDLE,w.DWORD])


@dataclass(frozen=True)
class ProcessIdentity:
    pid:int
    executable:str
    created:int

    def json(self):return asdict(self)


class ProcessGuard:
    def __init__(self,pid,expected=None):
        if os.name!='nt' or type(pid) is not int or pid<=0:
            raise UpdateVerificationError('A valid Windows process identity is required.')
        self.handle=OpenProcess(0x1000|0x00100000,False,pid)
        if not self.handle:
            error=UpdateVerificationError('The original application process is unavailable.')
            error.windows_error=ctypes.get_last_error();raise error
        try:
            size=w.DWORD(32768);buffer=ctypes.create_unicode_buffer(size.value)
            times=[w.FILETIME() for _ in range(4)]
            if not QueryImage(self.handle,0,buffer,ctypes.byref(size)) or not GetTimes(self.handle,*[ctypes.byref(t) for t in times]):
                raise UpdateVerificationError('Cannot verify the original application process.')
            created=times[0].dwLowDateTime|(times[0].dwHighDateTime<<32)
            self.identity=ProcessIdentity(pid,str(Path(buffer.value).resolve()),created)
            if expected is not None and (pid!=expected.pid or created!=expected.created or
                    os.path.normcase(self.identity.executable)!=os.path.normcase(str(Path(expected.executable).resolve()))):
                raise UpdateVerificationError('Application process identity changed.')
        except BaseException:self.close();raise

    def wait(self,timeout=180):
        if Wait(self.handle,int(timeout*1000))!=0:
            raise UpdateVerificationError('Application is still running; installation was not changed.')

    def close(self):
        if getattr(self,'handle',None):CloseHandle(self.handle);self.handle=None
    def __enter__(self):return self
    def __exit__(self,*_):self.close()


def process_identity(pid):
    with ProcessGuard(pid) as process:return process.identity


def validate_phase_studio_executable(path):
    import pefile
    try:
        with pefile.PE(str(path)) as image:
            names=[table.entries.get(b'ProductName',b'') for block in image.FileInfo
                for info in block if hasattr(info,'StringTable') for table in info.StringTable]
            if b'Phase Studio' not in names:raise ValueError
    except Exception:
        raise UpdateVerificationError('The running target is not a Phase Studio Windows executable.') from None


class _BasicLimits(ctypes.Structure):
    _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),('flags',w.DWORD),
        ('minimum',ctypes.c_size_t),('maximum',ctypes.c_size_t),('active',w.DWORD),
        ('affinity',ctypes.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
class _Counters(ctypes.Structure):
    _fields_=[(name,ctypes.c_ulonglong) for name in ('read','write','other','read_bytes','write_bytes','other_bytes')]
class _Limits(ctypes.Structure):
    _fields_=[('basic',_BasicLimits),('io',_Counters),('process_memory',ctypes.c_size_t),
        ('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
class _Startup(ctypes.Structure):
    _fields_=[('cb',w.DWORD),('reserved',w.LPWSTR),('desktop',w.LPWSTR),('title',w.LPWSTR),
        ('x',w.DWORD),('y',w.DWORD),('width',w.DWORD),('height',w.DWORD),
        ('chars_x',w.DWORD),('chars_y',w.DWORD),('fill',w.DWORD),('flags',w.DWORD),
        ('show',w.WORD),('reserved_size',w.WORD),('reserved_bytes',ctypes.POINTER(w.BYTE)),
        ('stdin',w.HANDLE),('stdout',w.HANDLE),('stderr',w.HANDLE)]
class _Process(ctypes.Structure):
    _fields_=[('process',w.HANDLE),('thread',w.HANDLE),('pid',w.DWORD),('tid',w.DWORD)]


def duplicate_restart_token(process_handle):
    """Retain the original user's non-elevated token across updater elevation."""
    advapi=ctypes.WinDLL('advapi32',use_last_error=True)
    open_token=advapi.OpenProcessToken;open_token.argtypes=[w.HANDLE,w.DWORD,ctypes.POINTER(w.HANDLE)];open_token.restype=w.BOOL
    duplicate=advapi.DuplicateTokenEx
    duplicate.argtypes=[w.HANDLE,w.DWORD,ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.POINTER(w.HANDLE)];duplicate.restype=w.BOOL
    token=w.HANDLE();linked=w.HANDLE();result=w.HANDLE()
    if not open_token(process_handle,0x000b,ctypes.byref(token)):
        raise UpdateVerificationError('Cannot preserve the original Windows user for restart.')
    try:
        information=advapi.GetTokenInformation
        information.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD,ctypes.POINTER(w.DWORD)];information.restype=w.BOOL
        elevation=w.DWORD();length=w.DWORD()
        source=token
        if information(token,18,ctypes.byref(elevation),ctypes.sizeof(elevation),ctypes.byref(length)) and elevation.value==2:
            if not information(token,19,ctypes.byref(linked),ctypes.sizeof(linked),ctypes.byref(length)):
                raise UpdateVerificationError('Cannot recover the original non-elevated Windows user token.')
            source=linked
        if not duplicate(source,0x02000000,None,2,1,ctypes.byref(result)):
            raise UpdateVerificationError('Cannot retain the original restart token.')
    finally:
        CloseHandle(token)
        if linked:CloseHandle(linked)
    return result


class PathGuards:
    """Bind private input files and ancestors against write/delete/reparse races."""
    def __init__(self,files):
        self.handles=[]
        create=bind('CreateFileW',w.HANDLE,[w.LPCWSTR,w.DWORD,w.DWORD,ctypes.c_void_p,w.DWORD,w.DWORD,w.HANDLE])
        final=bind('GetFinalPathNameByHandleW',w.DWORD,[w.HANDLE,w.LPWSTR,w.DWORD,w.DWORD])
        attributes=bind('GetFileInformationByHandleEx',w.BOOL,[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD])
        directories=set()
        try:
            paths=[Path(p).absolute() for p in files]
            for path in paths:directories.update(path.parents)
            for path in [*paths,*sorted(directories,key=lambda p:len(p.parts),reverse=True)]:
                is_directory=path in directories
                handle=create(str(path),0x80 if is_directory else 0x80000000,
                    3 if is_directory else 1,None,3,0x00200000|(0x02000000 if is_directory else 0),None)
                if handle in (None,ctypes.c_void_p(-1).value):
                    error=UpdateVerificationError('Cannot lock update input paths safely.')
                    error.path=path;error.windows_error=ctypes.get_last_error()
                    raise error
                self.handles.append((handle,path))
            for handle,path in self.handles:
                info=(w.DWORD*2)()
                if not attributes(handle,9,ctypes.byref(info),ctypes.sizeof(info)) or info[0]&0x400:
                    raise UpdateVerificationError('Update input is a reparse point or cannot be inspected.')
                buffer=ctypes.create_unicode_buffer(32768)
                if not final(handle,buffer,32768,0):raise UpdateVerificationError('Cannot bind update input paths.')
                name=buffer.value
                if name.startswith('\\\\?\\UNC\\'):name='\\\\'+name[8:]
                elif name.startswith('\\\\?\\'):name=name[4:]
                if os.path.normcase(str(Path(name)))!=os.path.normcase(str(path)):
                    raise UpdateVerificationError('Update input path was redirected.')
        except BaseException:self.close();raise
    def close(self):
        for handle,_ in getattr(self,'handles',[]):CloseHandle(handle)
        self.handles=[]


class RestartJob:
    """Launch suspended, assign before any child can start, then resume.

    Failure kills only this newly launched process tree. Successful health
    acknowledgement releases the tree; the helper does not own Jana/Superflip.
    """
    def __init__(self,executable,arguments,cwd,*,token=None):
        if os.name!='nt':raise UpdateVerificationError('Windows restart support is unavailable.')
        create_job=bind('CreateJobObjectW',w.HANDLE,[ctypes.c_void_p,w.LPCWSTR])
        self.set_limits=bind('SetInformationJobObject',w.BOOL,[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD])
        assign=bind('AssignProcessToJobObject',w.BOOL,[w.HANDLE,w.HANDLE])
        create=bind('CreateProcessW',w.BOOL,[w.LPCWSTR,w.LPWSTR,ctypes.c_void_p,ctypes.c_void_p,w.BOOL,w.DWORD,
            ctypes.c_void_p,w.LPCWSTR,ctypes.POINTER(_Startup),ctypes.POINTER(_Process)])
        resume=bind('ResumeThread',w.DWORD,[w.HANDLE])
        self.job=create_job(None,None);self.info=_Process()
        if not self.job:raise UpdateVerificationError('Cannot create restart process isolation.')
        limits=_Limits();limits.basic.flags=0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.set_limits(self.job,9,ctypes.byref(limits),ctypes.sizeof(limits)):
            self.abort();raise UpdateVerificationError('Cannot configure restart process isolation.')
        startup=_Startup();startup.cb=ctypes.sizeof(startup)
        command=ctypes.create_unicode_buffer(subprocess.list2cmdline([str(executable),*arguments]))
        if token is not None:
            advapi=ctypes.WinDLL('advapi32',use_last_error=True)
            with_token=advapi.CreateProcessWithTokenW
            with_token.argtypes=[w.HANDLE,w.DWORD,w.LPCWSTR,w.LPWSTR,w.DWORD,ctypes.c_void_p,w.LPCWSTR,ctypes.POINTER(_Startup),ctypes.POINTER(_Process)]
            with_token.restype=w.BOOL
            created=with_token(token,1,str(executable),command,0x4|0x08000000,None,str(cwd),ctypes.byref(startup),ctypes.byref(self.info))
        else:
            created=create(str(executable),command,None,None,False,0x4|0x08000000,None,str(cwd),ctypes.byref(startup),ctypes.byref(self.info))
        if not created:
            self.abort();raise UpdateVerificationError('The updated application could not start.')
        if not assign(self.job,self.info.process):
            terminate=bind('TerminateProcess',w.BOOL,[w.HANDLE,w.UINT]);terminate(self.info.process,1)
            self.abort();raise UpdateVerificationError('Cannot isolate the updated application process.')
        if resume(self.info.thread)==0xffffffff:
            self.abort();raise UpdateVerificationError('Cannot resume the updated application.')

    def alive(self):return bool(self.info.process) and Wait(self.info.process,0)==258
    def wait(self,seconds):
        if Wait(self.info.process,int(seconds*1000))!=0:raise UpdateVerificationError('Updated application startup timed out.')
        code=w.DWORD();get_code=bind('GetExitCodeProcess',w.BOOL,[w.HANDLE,ctypes.POINTER(w.DWORD)])
        if not get_code(self.info.process,ctypes.byref(code)):raise UpdateVerificationError('Cannot verify startup result.')
        return code.value
    @property
    def pid(self):return self.info.pid

    def abort(self):
        if getattr(self,'job',None):CloseHandle(self.job);self.job=None
        if getattr(self,'info',None) is not None:
            if self.info.process:Wait(self.info.process,10000)
            self._close_process_handles()

    def _close_process_handles(self):
        for field in ('thread','process'):
            handle=getattr(self.info,field)
            if handle:CloseHandle(handle);setattr(self.info,field,None)

    def commit(self):
        limits=_Limits()
        if not self.set_limits(self.job,9,ctypes.byref(limits),ctypes.sizeof(limits)):
            # Caller still holds the old backup and aborts this job before rollback.
            raise UpdateVerificationError('Restart succeeded, but process isolation could not be released.')
        CloseHandle(self.job);self.job=None;self._close_process_handles()


class _ProcessEntry(ctypes.Structure):
    _fields_=[('size',w.DWORD),('usage',w.DWORD),('pid',w.DWORD),('heap',ctypes.c_size_t),
        ('module',w.DWORD),('threads',w.DWORD),('parent',w.DWORD),('priority',w.LONG),
        ('flags',w.DWORD),('name',w.WCHAR*260)]


def process_entries():
    snapshot=bind('CreateToolhelp32Snapshot',w.HANDLE,[w.DWORD,w.DWORD])(2,0)
    if snapshot in (None,ctypes.c_void_p(-1).value):raise UpdateVerificationError('Cannot inspect running application processes.')
    first=bind('Process32FirstW',w.BOOL,[w.HANDLE,ctypes.POINTER(_ProcessEntry)])
    next_process=bind('Process32NextW',w.BOOL,[w.HANDLE,ctypes.POINTER(_ProcessEntry)])
    entries={};entry=_ProcessEntry();entry.size=ctypes.sizeof(entry)
    try:
        valid=first(snapshot,ctypes.byref(entry))
        while valid:
            entries[entry.pid]=(entry.parent,entry.name)
            valid=next_process(snapshot,ctypes.byref(entry))
    finally:CloseHandle(snapshot)
    return entries


def running_at(executable):
    executable=Path(executable).resolve()
    for pid,(_parent,name) in process_entries().items():
        if name.casefold()!=executable.name.casefold():continue
        try:
            with ProcessGuard(pid) as process:
                if Wait(process.handle,0)==0:continue
                if os.path.normcase(process.identity.executable)==os.path.normcase(str(executable)):return True
        except UpdateVerificationError as exc:
            if getattr(exc,'windows_error',None) in (87,1168):continue
            return True  # Cannot prove it is safe to replace.
    return False


def elevate(executable,plan,*,recovery=False):
    shell=ctypes.WinDLL('shell32',use_last_error=True)
    execute=shell.ShellExecuteW
    execute.argtypes=[w.HWND,w.LPCWSTR,w.LPCWSTR,w.LPCWSTR,w.LPCWSTR,ctypes.c_int]
    execute.restype=ctypes.c_void_p
    result=execute(None,'runas',str(executable),subprocess.list2cmdline([
        '--recover-plan' if recovery else '--apply-plan',str(plan),'--elevated']),str(Path(plan).parent),0)
    if not result or result<=32:raise UpdateVerificationError('Administrator permission was not granted. Installation is unchanged.')
