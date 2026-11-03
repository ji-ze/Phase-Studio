"""Ancillary, versioned run provenance. Never invokes a scientific program/API.

All artifacts are local. Unknown historical/build/checkpoint identities remain
None with explanations; recording configuration is not a bitwise-reproducibility
claim. Mutable event streams are distinguished from completed artifact hashes.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict,is_dataclass
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit,urlunsplit
import csv,hashlib,io,json,math,os,platform,re,shutil,subprocess,sys,threading,time,uuid,zipfile

_active=ContextVar('phase_run_provenance',default=(None,None))
_reader=ContextVar('phase_observed_reader',default=None)
_PRIVATE=re.compile(r'token|password|secret|authorization|api.?key|access.?key|signing.?key|private.?key|oauth',re.I)


def timestamp():return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def safe(value,key=''):
    from .error_reporting import sanitize_error_details
    if _PRIVATE.search(str(key)):return '<redacted>'
    if is_dataclass(value):return safe(asdict(value))
    if isinstance(value,SimpleNamespace):return safe(vars(value))
    if isinstance(value,dict):return {str(k):safe(v,str(k)) for k,v in value.items()}
    if isinstance(value,(set,frozenset)):return [safe(v) for v in sorted(value,key=str)]
    if isinstance(value,(list,tuple)):return [safe(v) for v in value]
    if isinstance(value,Path):return str(value.expanduser().resolve())
    if value.__class__.__module__=='gemmi' and hasattr(value,'parameters'):return list(map(float,value.parameters))
    if value.__class__.__module__=='gemmi' and callable(getattr(value,'xhm',None)):
        return dict(hm=value.xhm(),number=value.number,hall=value.hall)
    if isinstance(value,float) and not math.isfinite(value):return None
    if isinstance(value,(str,bytes)):
        text=value.decode('utf8','replace') if isinstance(value,bytes) else value
        if text.startswith(('http://','https://')):
            try:
                parsed=urlsplit(text)
                host=parsed.hostname or ''
                if ':' in host:host='['+host+']'
                if parsed.port is not None:host+=':'+str(parsed.port)
                text=urlunsplit((parsed.scheme,host,parsed.path,'',''))
            except ValueError:return '<invalid or sensitive URL>'
        return sanitize_error_details(text)
    if value is None or isinstance(value,(int,float,bool)):return value
    return str(value)


def file_identity(path,role=None):
    result=dict(role=role,path=str(Path(path).expanduser().resolve()) if path else None,
                sha256=None,bytes=None,status='Unavailable')
    try:
        source=Path(path);before=source.stat()
        digest=hashlib.sha256()
        with source.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
        after=source.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
            raise ValueError('File changed while hashing')
        result.update(sha256=digest.hexdigest(),bytes=after.st_size,mtime_ns=after.st_mtime_ns,status='Available',format=source.suffix.lower())
    except (OSError,ValueError,TypeError) as exc:result['reason']=str(exc)
    return result


def native_identity(path,role):
    result=file_identity(path,role);result['version']=None
    result['version_detection']='Unavailable: no executable version resource; program was not launched for diagnostics.'
    if os.name=='nt' and result['status']=='Available':
        try:
            import ctypes
            from ctypes import wintypes
            version=ctypes.windll.version
            version.GetFileVersionInfoSizeW.argtypes=(wintypes.LPCWSTR,ctypes.POINTER(wintypes.DWORD))
            version.GetFileVersionInfoSizeW.restype=wintypes.DWORD
            version.GetFileVersionInfoW.argtypes=(wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p)
            version.VerQueryValueW.argtypes=(ctypes.c_void_p,wintypes.LPCWSTR,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(wintypes.UINT))
            size=version.GetFileVersionInfoSizeW(str(Path(path).resolve()),None)
            if size:
                block=ctypes.create_string_buffer(size)
                if version.GetFileVersionInfoW(str(Path(path).resolve()),0,size,block):
                    address=ctypes.c_void_p();length=wintypes.UINT()
                    if version.VerQueryValueW(block,'\\',ctypes.byref(address),ctypes.byref(length)) and length.value>=52:
                        words=ctypes.cast(address,ctypes.POINTER(wintypes.DWORD))
                        if words[0]==0xFEEF04BD:
                            result['version']='.'.join(map(str,(words[2]>>16,words[2]&65535,words[3]>>16,words[3]&65535)))
                            result['version_detection']='Windows fixed file-version resource'
        except Exception as exc:result['version_detection']='Unavailable: '+str(exc)
    return result


def application_identity():
    from .version import VERSION
    root=Path(__file__).resolve().parents[1]
    result=dict(version=VERSION,git_commit=None,source_dirty=None,build_id=None,build_date=None,
                release_asset_sha256=None,distribution_profile='development' if not getattr(sys,'frozen',False) else None,
                platform=platform.platform(),python=sys.version,implementation=platform.python_implementation())
    if (root/'.git').exists():
        try:
            result['git_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True,stderr=subprocess.DEVNULL).strip()
            result['source_dirty']=bool(subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=root,text=True,stderr=subprocess.DEVNULL).strip())
        except (OSError,subprocess.SubprocessError):pass
    sources=sorted(Path(__file__).parent.glob('*.py'))
    if sources:
        digest=hashlib.sha256()
        for source in sources:digest.update(source.name.encode('utf8'));digest.update(source.read_bytes())
        result['runtime_sources_sha256']=digest.hexdigest()
    else:result['runtime_sources_sha256']=None
    try:
        marker=json.loads(Path(__file__).with_name('distribution.json').read_text(encoding='utf8'))
        result['distribution_profile']=marker.get('profile');result['distribution_marker']=safe(marker)
    except (OSError,ValueError):pass
    if getattr(sys,'frozen',False):result['runtime_executable']=file_identity(sys.executable,'actual application executable')
    result['reproducibility_note']='Missing build metadata is unavailable, not inferred from file dates. Executable hashes do not establish bitwise reproducibility.'
    return result


def atomic_json(path,data):
    atomic_text(path,json.dumps(safe(data),indent=2,sort_keys=True,allow_nan=False)+'\n')


def atomic_text(path,text):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(text,encoding='utf8')
    os.replace(temporary,path)


def repair_event_stream(path):
    path=Path(path)
    if not path.exists():return None
    content=path.read_bytes();valid=[];invalid=0
    for line in content.splitlines():
        if not line.strip():continue
        try:json.loads(line);valid.append(line.decode('utf8')+'\n')
        except (ValueError,UnicodeDecodeError):invalid+=1
    if invalid:
        archive=path.with_name(path.stem+'.interrupted-'+hashlib.sha256(content).hexdigest()[:12]+'.raw')
        if not archive.exists():archive.write_bytes(content)
        atomic_text(path,''.join(valid))
        return dict(original_archive=str(archive),invalid_lines=invalid,recovered_records=len(valid))
    if content and not content.endswith(b'\n'):atomic_text(path,''.join(valid))
    return None


@contextmanager
def provenance_scope(provenance,cycle=None):
    token=_active.set((provenance,cycle))
    try:yield
    finally:_active.reset(token)


def observe_remote(kind,**fields):
    provenance,cycle=_active.get()
    if provenance is not None:
        try:provenance.remote(kind,cycle,fields)
        except Exception:pass  # Diagnostics must not change a scientific/API result.


def remote_identity(response):
    """Whitelist only server model/checkpoint identity, never job-access material."""
    result={}
    for key in ('model_id','checkpoint_id','checkpoint_sha256','model_version'):
        value=response.get(key)
        if isinstance(value,(str,int,float,bool)):result[key]=value
    for section,pairs in [('model',(('id','model_id'),('checkpoint_id','checkpoint_id'),('checkpoint_sha256','checkpoint_sha256'))),
                          ('checkpoint',(('id','checkpoint_id'),('sha256','checkpoint_sha256')))]:
        nested=response.get(section)
        if isinstance(nested,dict):
            for key,target in pairs:
                value=nested.get(key)
                if isinstance(value,(str,int,float,bool)):result.setdefault(target,value)
    return result


def observe_native_command(cmd,cwd,log_path):
    provenance,cycle=_active.get()
    if provenance is not None:record(provenance,'native_command',cmd,cwd,log_path,cycle)


def observe_reflection_read(phase,path,*,line=None,reflection=None,include_000=False):
    """Read-only counters at the authoritative parser's actual decisions."""
    provenance,cycle=_active.get()
    if provenance is None:return
    try:
        if phase=='start':
            record=dict(file=file_identity(path,'parsed reflections'),cycle=cycle,status='incomplete',
                lines=0,blank=0,comments=0,unparsed=0,origin_excluded=0,accepted=0,
                nonfinite_accepted=0,nonintegral_indices_accepted=0)
            with provenance.lock:provenance.manifest.setdefault('reflection_reads',[]).append(record)
            _reader.set(record)
        elif phase=='line':
            record=_reader.get()
            if record is None:return
            record['lines']+=1;stripped=line.strip()
            if not stripped:record['blank']+=1
            elif stripped.startswith(('#','!',';')):record['comments']+=1
            elif reflection is None:record['unparsed']+=1
            elif not include_000 and (reflection.h,reflection.k,reflection.l)==(0,0,0):record['origin_excluded']+=1
            else:
                record['accepted']+=1
                if not math.isfinite(float(reflection.value)):record['nonfinite_accepted']+=1
                if any(float(token)!=int(float(token)) for token in stripped.split()[:3]):record['nonintegral_indices_accepted']+=1
        elif phase=='finish' and _reader.get() is not None:
            _reader.get()['status']='completed';_reader.set(None)
    except Exception:pass


def observe_pipeline(method):
    """Bind the existing run worker's observations, including its initial parser."""
    from functools import wraps
    @wraps(method)
    def wrapped(owner,cfg,resume_state=None):
        config=resume_state.cfg if resume_state is not None else cfg
        diagnostic=getattr(owner,'_run_diagnostic_log',None)
        provenance=getattr(diagnostic,'provenance',None)
        expected=str(getattr(config,'run_id','') or Path(getattr(config,'work_dir','.')).name)
        if provenance is not None and provenance.run_id!=expected:provenance=None
        if resume_state is not None:
            resume_state.provenance=provenance
            resume_state.diagnostic_log=diagnostic if provenance is not None else None
        owner._run_event_context.cycle=None
        if provenance is not None and resume_state is not None:record(provenance,'refresh_config',config)
        with provenance_scope(provenance):
            try:return method(owner,cfg,resume_state)
            except BaseException:
                if provenance is not None:
                    try:provenance.finish('failed')
                    except Exception:pass
                raise
    return wrapped


def active_provenance():return _active.get()[0]


def record(provenance,method,*args,**kwargs):
    if provenance is None:return None
    try:return getattr(provenance,method)(*args,**kwargs)
    except Exception as exc:
        provenance.manifest.setdefault('provenance_errors',[]).append(dict(method=method,error=safe(str(exc))))
        return None


class RunProvenance:
    def __init__(self,directory,cfg):
        from .error_reporting import register_private_value
        register_private_value(getattr(cfg,'sharped_api_token',''))
        self.directory=Path(directory).resolve();self.directory.mkdir(parents=True,exist_ok=True)
        self.run_id=str(getattr(cfg,'run_id','') or self.directory.name)
        slug=re.sub(r'[^A-Za-z0-9_.-]','_',self.run_id)[:120] or 'run'
        self.session=self.directory/'provenance'/slug;self.session.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.started=time.perf_counter();self._sequence=0
        self.session_id=uuid.uuid4().hex
        path=self.session/'run_manifest.json'
        try:
            old=json.loads(path.read_text(encoding='utf8'))
            if (not isinstance(old,dict) or old.get('schema')!=1 or old.get('run_id')!=self.run_id
                or not all(isinstance(old.get(key),dict) for key in ('cycles','inputs','external_programs'))
                or not all(isinstance(old.get(key),list) for key in ('operations','sharped_requests','selections','handoffs','warnings','limitations'))):
                raise ValueError('Incompatible provenance manifest')
            self.manifest=old
        except (OSError,ValueError):
            if path.is_file():
                previous=path.read_bytes()
                archive=path.with_name('run_manifest.invalid-'+hashlib.sha256(previous).hexdigest()[:12]+'.raw')
                if not archive.exists():archive.write_bytes(previous)
            self.manifest=dict(schema=1,run_id=self.run_id,started=timestamp(),finished=None,status='prepared',
                application=application_identity(),requested_config=safe(cfg),effective_config=None,
                setting_origins=safe(getattr(cfg,'setting_provenance',None)),inputs={},external_programs={},
                input_roles={},cycles={},operations=[],sharped_requests=[],selections=[],handoffs=[],
                warnings=[],limitations=['Remote immutable checkpoint identity unavailable unless the server supplies it.',
                'No bitwise-reproducibility claim. Automatic random seeds may be uncontrolled.',
                'The manifest is an audit record, not a replacement for the execution checkpoint/recovery authority.'])
        self.manifest['artifact_directory']=str(self.session)
        self.manifest['previous_session_status']=self.manifest['status']
        self.manifest['status']='prepared'
        self.manifest.setdefault('reflection_reads',[])
        self.manifest.setdefault('incomplete_cycles',{})
        self.manifest['missing_value_semantics']='JSON null means unavailable or inapplicable, never measured zero. Status/reason fields distinguish these cases.'
        self.manifest['units']=dict(timestamps='ISO 8601 UTC, millisecond precision',durations='seconds',
            rmsd='angstrom',phase_agreement='dimensionless as computed',relative_intensity_change='percent; denominator defined in feedback record')
        for stream_path in (self.session/'events.jsonl',self.directory/'events.jsonl'):
            recovery=repair_event_stream(stream_path)
            if recovery:self.manifest.setdefault('event_stream_recovery',[]).append(recovery)
        self._events=(self.session/'events.jsonl').open('a',encoding='utf8')
        self.event('session_opened','Workflow',None,dict(previous_status=self.manifest['previous_session_status']))
        self.refresh_config(cfg,status=self.manifest['status'])

    def event(self,event_type,component,cycle,payload,severity='INFO'):
        with self.lock:
            self._sequence+=1
            record=dict(schema=1,timestamp=timestamp(),run_id=self.run_id,session_id=self.session_id,session_sequence=self._sequence,
                        cycle=cycle,component=str(component),event_type=event_type,severity=severity,payload=safe(payload))
            self._events.write(json.dumps(record,sort_keys=True,allow_nan=False)+'\n');self._events.flush()
            if severity in {'WARNING','ERROR','CRITICAL'}:
                self.manifest['warnings'].append(dict(timestamp=record['timestamp'],cycle=cycle,component=component,
                    severity=severity,payload=safe(payload)))
            # Root stream is the complete run-index stream, including explicit run IDs.
            with (self.directory/'events.jsonl').open('a',encoding='utf8') as stream:
                stream.write(json.dumps(record,sort_keys=True,allow_nan=False)+'\n')
            return record

    def refresh_config(self,cfg,*,status='running'):
        with self.lock:
            current=safe(cfg);self.manifest['effective_config']=current
            self.manifest['status']=status;self.manifest['configured_cycles']=getattr(cfg,'cycles',None)
            if status in {'prepared','running','resuming'}:self.manifest['finished']=None
            requested=self.manifest.get('requested_config') or {}
            self.manifest['resolved_overrides']={key:dict(requested=requested.get(key),effective=value)
                for key,value in current.items() if isinstance(current,dict) and requested.get(key)!=value} if isinstance(current,dict) else {}
            inverse=getattr(cfg,'damping_factor',None)
            if inverse is not None:
                from .app import effective_xplor_damping_factor
                factor=effective_xplor_damping_factor(inverse)
                self.manifest['xplor_blending']=dict(configured_inverse=inverse,effective_factor=factor,
                    previous_map_coefficient=(factor-1.)/factor,new_map_coefficient=1./factor,
                    applicability='Only the existing XPLOR-model damping branch; CIF/none and other reconstruction branches may bypass it.',
                    formula='((factor - 1) * previous + new) / factor')
            for key,role in [('jana_inflip','original Jana input'),('hkl','reflection source, possibly extracted/copied'),
                ('reference_cif','external reference'),('first_cycle_modelfile','explicit initial model')]:
                path=getattr(cfg,key,None)
                self.manifest['inputs'][key]=file_identity(path,role)
            if 'original_input_identities' not in self.manifest:
                self.manifest['original_input_identities']=json.loads(json.dumps(self.manifest['inputs']))
            for key,role in [('superflip_exe','Superflip'),('edma_exe','EDMA')]:
                old=self.manifest['external_programs'].get(role)
                configured=getattr(cfg,key,None);resolved=str(Path(configured).resolve()) if configured else None
                if not old or old.get('path')!=resolved:
                    self.manifest['external_programs'][role]=native_identity(getattr(cfg,key,None),role)
            self.manifest['sharped']=dict(endpoint=safe(getattr(cfg,'sharped_base_url',None)),
                selected_model_display=getattr(cfg,'sharped_model',None),immutable_checkpoint=None,
                immutable_checkpoint_status='Unavailable until explicitly supplied by a server response',
                inference_parameters={name:safe(getattr(cfg,name,None),name) for name in (
                    'sharped_elements','sharped_outres','sharped_map_value_exponent','sharped_max_upload_mb',
                    'sharped_timeout_seconds','sharped_poll_seconds','sharped_max_polls')})
            seed=str(getattr(cfg,'randomseed','') or '')
            self.manifest['reproducibility']=dict(configuration='effective settings recorded',
                random_seed='uncontrolled/automatic' if not seed or seed.upper()=='AUTO' else 'explicit syntax recorded; backend semantics retained',
                external_binaries='verified hashes' if all(x.get('sha256') for x in self.manifest['external_programs'].values()) else 'one or more identities unavailable',
                remote_checkpoint='unavailable',bitwise_reproducible=False)
            self.checkpoint()

    def prepared(self,cfg,state,parsed_reflections,original_count=None):
        from .app import _passes_reflection_filters
        self.refresh_config(cfg)
        mode=state.configured_data_mode;written=state.observed_hkls.get(mode)
        from .hkl_diagnostics import read_diagnostic_reflections
        actual=list(read_diagnostic_reflections(written,mode)[0])
        kept={(r.h,r.k,r.l) for r in actual}
        counts=dict(parsed_records=original_count,unique_records=len(parsed_reflections),
            duplicates_merged=(original_count-len(parsed_reflections)) if original_count is not None else None,
            written_records=len(actual),zero_values=sum(r.value==0 for r in parsed_reflections),
            negative_values=sum(r.value<0 for r in parsed_reflections),
            nonfinite_in_parsed_array=sum(not math.isfinite(float(r.value)) for r in parsed_reflections),
            parser_rejections=None,holdout_excluded=len(state.omit_test_hkls),
            absent_from_written=sum((r.h,r.k,r.l) not in kept for r in parsed_reflections))
        reads=[r for r in self.manifest['reflection_reads'] if r['file'].get('path')==str(Path(cfg.hkl).resolve())]
        if reads:
            counts['parser_inventory']=safe(reads[-1])
            counts['parser_rejections']=reads[-1]['unparsed']+reads[-1]['origin_excluded']
        expected=[r for r in parsed_reflections if (r.h,r.k,r.l) not in state.omit_test_hkls and
            _passes_reflection_filters(r,cfg.i_over_sigma_min,state.ref_ctx.cell,cfg.resolution_d_min,mode)]
        counts['reconciled_by_existing_filter_and_holdout']=set((r.h,r.k,r.l) for r in expected)==kept
        counts['filter_rules']=dict(policy_version='207-fwhm-corrected-v1',mode_native_value_over_uncertainty_limit=cfg.i_over_sigma_min,
            resolution_min_angstrom=cfg.resolution_d_min,data_mode=mode,
            note='Positive threshold requires measured uncertainties; FWHM requires threshold 0. Finite nonnegative values only; FWHM widths must be finite positive. Zero values are retained when the threshold is disabled.')
        counts['actual_input']=file_identity(written,'initial written Superflip reflections')
        self.manifest['reflection_inventory']=counts
        self.manifest['input_roles']=dict(experimental=self.manifest['inputs']['hkl'],
            evaluation_reference=self.manifest['inputs']['reference_cif'],
            initial_model=dict(explicit_file=self.manifest['inputs']['first_cycle_modelfile'],
                effective_first_cycle='Recorded from generated input, not inferred from reference atom count'),
            superflip_reference=dict(mode=state.referencefile_mode,explicit=file_identity(state.explicit_superflip_referencefile,'Superflip referencefile'),
                note='Referencefile and modelfile are separate roles; generated inflip keywords below establish actual usage.'),
            iterative_models=dict(mode=cfg.modelfile_source,source='Per-cycle generated input and model identity'))
        self.event('inputs_prepared','Workflow',None,counts);self.checkpoint()

    def operation(self,phase,component,cycle,*,status=None,seconds=None):
        item=dict(phase=phase,component=component,cycle=cycle,status=status,seconds=seconds,timestamp=timestamp())
        with self.lock:
            self.manifest['operations'].append(item)
            if cycle is not None:
                self.manifest['incomplete_cycles'][str(cycle)]=dict(status='failed' if status=='failed' else 'running',
                    last_component=component,last_event=phase,timestamp=item['timestamp'])
        self.event('operation_'+phase,component,cycle,item,severity='ERROR' if status=='failed' else 'INFO')
        self.checkpoint()

    def native_command(self,cmd,cwd,log_path,cycle):
        executable=Path(cmd[0])
        if not executable.is_absolute():
            local=Path(cwd)/executable
            resolved=local if local.is_file() else shutil.which(str(executable))
            executable=Path(resolved) if resolved else executable
        name=str(executable.resolve())
        current=file_identity(executable)
        if name not in self.manifest['external_programs'] or self.manifest['external_programs'][name].get('sha256')!=current.get('sha256'):
            self.manifest['external_programs'][name]=native_identity(executable,'actual native command')
        arguments=[];hidden=False
        for argument in cmd:
            if hidden:arguments.append('<redacted>');hidden=False
            elif _PRIVATE.search(str(argument)):
                arguments.append('<redacted option>');hidden='=' not in str(argument)
            else:arguments.append(safe(str(argument)))
        self.event('native_command','Native executable',cycle,dict(executable=self.manifest['external_programs'][name],
            arguments=arguments,working_directory=str(Path(cwd).resolve()),raw_log_path=str(Path(log_path).resolve())))
        self.checkpoint()

    def remote(self,kind,cycle,fields):
        fields=dict(fields)
        if 'file' in fields:fields['artifact']=file_identity(fields.pop('file'),'SharpED '+kind)
        checkpoint=fields.get('checkpoint_sha256') or fields.get('checkpoint_id')
        with self.lock:
            self.manifest['sharped_requests'].append(dict(cycle=cycle,event=kind,**safe(fields)))
            if checkpoint:
                self.manifest['sharped']['immutable_checkpoint']=safe(checkpoint)
                self.manifest['sharped']['immutable_checkpoint_status']='Server-supplied; not independently verified against checkpoint bytes'
                self.manifest['reproducibility']['remote_checkpoint']='server supplied identity (checkpoint bytes unavailable)'
        self.event('remote_'+kind,'SharpED',cycle,fields);self.checkpoint()

    def completed_cycle(self,state,result):
        record=dict(schema=1,run_id=self.run_id,source_cycle=result.cycle,target_cycle=result.cycle+1 if result.cycle<state.cfg.cycles else None,
            status='results available; continuation pending',recorded=timestamp(),reflection_input=file_identity(state.observed_hkls.get(state.configured_data_mode),'actual Superflip input'),
            reflection_mode=state.configured_data_mode,initialization_source=result.model_source,
            initialization_model=file_identity(result.model_in,'actual initialization model/map'),
            result=safe(result),artifacts={},generated_superflip_input=None)
        original=self.manifest.get('reflection_inventory',{}).get('actual_input',{})
        previous=(self.manifest['cycles'].get(str(result.cycle-1),{}).get('map_feedback') or {})
        if original.get('sha256')==record['reflection_input'].get('sha256'):
            record['reflection_input']['records']=self.manifest.get('reflection_inventory',{}).get('written_records')
        elif previous.get('next_input',{}).get('sha256')==record['reflection_input'].get('sha256'):
            record['reflection_input']['records']=previous.get('next_input_records')
        else:record['reflection_input']['records']=None
        for key in ('superflip_map','deblur_map','superflip_edma_cif','deblur_edma_cif'):
            record['artifacts'][key]=file_identity(getattr(result,key,None),key)
        directory=Path(state.cfg.work_dir)/f'cycle_{result.cycle:03d}'
        inflip=directory/f'cycle_{result.cycle:03d}_superflip.inflip'
        record['generated_superflip_input']=file_identity(inflip,'actual generated Superflip input')
        try:
            header=inflip.read_text(encoding='utf8',errors='replace').split('fbegin',1)[0]
            record['generated_keywords']=[line.strip() for line in header.splitlines() if line.strip() and not line.lstrip().startswith('#')]
        except OSError:record['generated_keywords']=None
        keywords={}
        for line in record['generated_keywords'] or []:
            tokens=line.split(None,1)
            if len(tokens)==2:keywords[tokens[0].lower()]=tokens[1]
        record['reference_and_seed_roles']=dict(
            referencefile=keywords.get('referencefile'),modelfile=keywords.get('modelfile'),
            reference_density_alignment='referencefile' in keywords,
            initial_model_or_phases=('modelfile' in keywords and keywords.get('perform','').lower()!='symmetry'),
            reference_ranked_superflip_density=keywords.get('bestdensities','').lower().endswith('reference'),
            randomseed=keywords.get('randomseed'),
            qualification='Superflip referencefile is documented to align resulting density. It is distinct from modelfile initialization. Reference-backed evaluation/recommendation is not independent validation.')
        for source in ('superflip','deblurred'):
            cif_path=getattr(result,'superflip_edma_cif' if source=='superflip' else 'deblur_edma_cif',None)
            if cif_path:
                record['artifacts'][source+'_jana_model']=file_identity(Path(cif_path).with_suffix('.m40'),'corresponding Jana peak model')
                sidecar=Path(cif_path).with_name(Path(cif_path).stem+'_site_counts.json')
                record['artifacts'][source+'_site_counts']=file_identity(sidecar,'existing EDMA site-count provenance')
                try:
                    metadata=json.loads(sidecar.read_text(encoding='utf8'))
                    record[source+'_site_lineage']={key:metadata.get(key) for key in ('raw_edma_sites','cif_sites','independent_asu_sites','jana_m40_sites','threshold_sigma','displacement_parameter')}
                except (OSError,ValueError,TypeError):record[source+'_site_lineage']=None
        with self.lock:
            previous=self.manifest['cycles'].get(str(result.cycle))
            if previous is not None:
                encoded=json.dumps(safe(previous),sort_keys=True,allow_nan=False).encode('utf8')
                archive=self.session/'history'/f'cycle_{result.cycle:03d}.{hashlib.sha256(encoded).hexdigest()}.json'
                if not archive.exists():atomic_json(archive,previous)
                self.manifest.setdefault('cycle_record_history',[]).append(file_identity(archive,'superseded cycle provenance; source scientific files may have been replaced by an explicit retry'))
            self.manifest['cycles'][str(result.cycle)]=record
            atomic_json(self.session/f'cycle_{result.cycle:03d}.json',record)
            existing=Path(state.cfg.work_dir)/'metrics.csv'
            if existing.is_file():
                for destination in (self.directory/'cycle_metrics.csv',self.session/'cycle_metrics.csv'):
                    temporary=destination.with_suffix('.csv.tmp');shutil.copyfile(existing,temporary);os.replace(temporary,destination)
        self.event('cycle_results_available','Workflow',result.cycle,dict(record_path=str(self.session/f'cycle_{result.cycle:03d}.json')))
        self.checkpoint()

    def feedback(self,report):
        cycle=str(report['source_cycle'])
        with self.lock:
            record=self.manifest['cycles'].get(cycle)
            if record is not None:
                record['map_feedback']=dict(source_cycle=report['source_cycle'],target_cycle=report['target_cycle'],
                    diagnostic_record=file_identity(report.get('detail_path'),'authoritative Map Feedback diagnostics'),
                    next_input=file_identity(report.get('next_cycle_reflection_file') or (report.get('target_input') or {}).get('file'),'next-cycle written reflections'),
                    next_input_records=report.get('written_reflections') if report.get('written_reflections') is not None else (report.get('target_input') or {}).get('written_reflections'),
                    operations=[{k:v for k,v in op.items() if k not in ('rows','group_conservation')} for op in report['operations']])
                atomic_json(self.session/f'cycle_{int(cycle):03d}.json',record)
        self.event('feedback_completed','Map Feedback',int(cycle),dict(target_cycle=report['target_cycle'],detail_path=report.get('detail_path')))
        self.checkpoint()

    def cycle_finished(self,cycle):
        with self.lock:
            item=self.manifest['cycles'].get(str(cycle))
            if item is not None:
                item['status']='completed';item['completed']=timestamp()
                atomic_json(self.session/f'cycle_{cycle:03d}.json',item)
            self.manifest['incomplete_cycles'].pop(str(cycle),None)
        self.event('cycle_pipeline_completed','Workflow',cycle,dict(status='completed'))
        self.checkpoint()

    def handoff(self,status,candidate,reason=None):
        item=dict(timestamp=timestamp(),status=status,cycle=candidate.cycle,family=candidate.source,
            candidate_id=candidate.candidate_id,map=file_identity(candidate.map_path,'selected map'),
            cif=file_identity(candidate.structure_path,'corresponding selected CIF'),
            jana_model=file_identity(candidate.jana_model_path,'corresponding selected Jana model'),
            threshold=candidate.edma_sigma,reason=safe(reason),refinement_status='not observed')
        with self.lock:
            if status=='requested':self.manifest['selections'].append(item)
            self.manifest['handoffs'].append(item)
        self.event('handoff_'+status,'Jana2020',candidate.cycle,item,severity='ERROR' if status=='failed' else 'INFO')
        self.checkpoint()

    def selection(self,candidate,context):
        item=dict(timestamp=timestamp(),context=context,cycle=candidate.cycle,family=candidate.source,
            candidate_id=candidate.candidate_id,map=file_identity(candidate.map_path,'selected map'),
            cif=file_identity(candidate.structure_path,'selected corresponding structure'),
            jana_model=file_identity(candidate.jana_model_path,'selected corresponding Jana model'))
        with self.lock:self.manifest['selections'].append(item)
        self.event('candidate_selected','Results',candidate.cycle,item);self.checkpoint()

    def finish(self,outcome):
        with self.lock:
            completed={key for key,item in self.manifest['cycles'].items() if item['status']=='completed'}
            count=len(completed);expected=self.manifest.get('configured_cycles')
            complete=expected is not None and completed=={str(n) for n in range(1,int(expected)+1)}
            status='completed' if outcome=='complete' and complete else 'partial' if outcome=='complete' else outcome
            if self.manifest.get('finished') is not None and self.manifest['status']==status:return
            self.manifest.update(status=status,finished=timestamp(),observed_session_seconds=time.perf_counter()-self.started,
                                 completed_cycles=count)
            durations={}
            for op in self.manifest['operations']:
                if op['phase']=='finished' and op.get('seconds') is not None:
                    durations[op['component']]=durations.get(op['component'],0.)+op['seconds']
            self.manifest['observed_operation_seconds_by_component']=durations
        self.event('workflow_finished','Workflow',None,dict(status=status,outcome=outcome,completed_cycles=count))
        self.checkpoint()

    def checkpoint(self):
        with self.lock:
            self.manifest['completed_cycles']=sum(item['status']=='completed' for item in self.manifest['cycles'].values())
            self.manifest['snapshot_timestamp']=timestamp()
            for destination in (self.session/'run_manifest.json',self.directory/'run_manifest.json'):atomic_json(destination,self.manifest)
            summary=self.summary()
            for destination in (self.session/'summary.md',self.directory/'summary.md'):atomic_text(destination,summary)
            identities=[];unsealed=[]
            def collect(value):
                if isinstance(value,dict):
                    if value.get('sha256') and value.get('path'):
                        try:
                            stat=Path(value['path']).stat()
                            if value.get('mtime_ns')==stat.st_mtime_ns and value.get('bytes')==stat.st_size:
                                identities.append((value['path'],value['sha256']))
                            else:unsealed.append(dict(path=value['path'],captured_sha256=value['sha256'],reason='File metadata changed since capture; historical identity retained, not claimed as current.'))
                        except OSError:unsealed.append(dict(path=value['path'],captured_sha256=value['sha256'],reason='No longer readable; captured identity retained.'))
                    for child in value.values():collect(child)
                elif isinstance(value,list):
                    for child in value:collect(child)
            collect(self.manifest)
            self.manifest['unsealed_artifacts']=unsealed
            for destination in (self.session/'run_manifest.json',self.directory/'run_manifest.json'):atomic_json(destination,self.manifest)
            for path in (self.session/'run_manifest.json',self.session/'summary.md'):
                identity=file_identity(path);identities.append((str(path),identity['sha256']))
            text=''.join(f'{digest}  {name}\n' for name,digest in sorted(set(identities)) if digest)
            atomic_text(self.session/'checksums.sha256',text)
            atomic_text(self.directory/'checksums.sha256',text)

    def summary(self):
        m=self.manifest
        def show(value):return 'Unavailable' if value is None else str(value).replace('|','\\|').replace('\n',' ')
        lines=[f'# Phase Studio run {self.run_id}',f'\nStatus: {m["status"]}. Started: {m["started"]}. Finished: {show(m.get("finished"))}.',
            '\nEffective configuration and full hashes: `run_manifest.json`. Detailed chronology: `events.jsonl` and `diagnostic.log`.',
            '\n## Recorded scientific results',
            '\n| Cycle | Cycle status | Family | F0.5 | RMSD (A) | Phase agreement | Reference TP / FP | Extracted CIF sites | Feedback feeding this cycle | Input |',
            '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
        cfg=m.get('effective_config') or {}
        setup=['\n## Run setup',
            f'Input: {show((m["inputs"].get("hkl") or {}).get("path"))}',
            f'Workflow: {show(cfg.get("reconstruction_mode"))}; configured cycles: {show(cfg.get("cycles"))}; SharpED model: {show(cfg.get("sharped_model"))}.',
            'Enabled optional operations: '+', '.join(key for key in ('run_sharped','run_edma_superflip','run_edma_deblurred',
                'map_feedback_missing_enabled','map_feedback_intensity_enabled','redistribute_overlaps','compute_omit_maps') if cfg.get(key)),
            'Evaluation reference: '+show((m.get('inputs',{}).get('reference_cif') or {}).get('path')),
            'Explicit first-cycle model: '+show((m.get('inputs',{}).get('first_cycle_modelfile') or {}).get('path')),
            'Effective referencefile/modelfile roles are recorded from each generated input; an atom count alone is not evidence of a phasing seed.',
            '\n## Execution summary',f'Completed cycles: {show(m.get("completed_cycles"))}; incomplete cycles: '+json.dumps(m['incomplete_cycles'],sort_keys=True),
            f'Observed session duration (s): {show(m.get("observed_session_seconds"))}; component totals (s, may overlap): '+json.dumps(m.get('observed_operation_seconds_by_component'),sort_keys=True)]
        lines[3:3]=setup
        for _,record in sorted(m['cycles'].items(),key=lambda item:int(item[0])):
            result=record['result']
            preceding=m['cycles'].get(str(record['source_cycle']-1),{}).get('map_feedback') or {}
            feedback='No preceding step; initial filtered input' if record['source_cycle']==1 else 'Unavailable'
            if preceding.get('target_cycle')==record['source_cycle']:
                feedback='; '.join(f'{op["operation"]}: {op["status"]}, stage mean absolute relative {show(op.get("mean_absolute_relative_percent"))}%' for op in preceding.get('operations',[]) if op['status']!='Disabled') or 'Disabled'
            for family,key in [('Superflip','superflip_quality'),('SharpED','deblur_quality')]:
                metrics=result.get(key) or {}
                lines.append('| '+' | '.join(map(show,[record['source_cycle'],record['status'],family,metrics.get('reference_f05'),
                    metrics.get('reference_rmsd'),metrics.get('reference_phase_agreement'),
                    show(metrics.get('reference_tp'))+' / '+show(metrics.get('reference_fp')),
                    (record.get('superflip_site_lineage' if family=='Superflip' else 'deblurred_site_lineage') or {}).get('cif_sites'),
                    feedback,
                    record['reflection_input'].get('path')]))+' |')
        lines+=['\n## Input and execution','```json',json.dumps(safe(m.get('reflection_inventory')),indent=2),'```',
            '\n## Recommendation and later actions',
            'Recommendations remain governed by the existing validation-profile ranking. This logger does not rerank feedback changes.',
            'No selection or handoff is implied by completing a run.',
            json.dumps(safe(dict(selections=m['selections'],handoffs=m['handoffs'])),indent=2),
            '\n## Reproducibility limits',*['- '+item for item in m['limitations']],
            '\nHashes identify completed files at the recorded checkpoint. Mutable live logs/events are not immutable scientific inputs.']
        lines+=['\n## Warnings and failures']
        seen=set()
        for warning in m['warnings']:
            key=(warning['component'],warning['severity'],json.dumps(warning['payload'],sort_keys=True))
            if key not in seen:
                lines.append(f'- {warning["severity"]} · {warning["component"]} · cycle {show(warning["cycle"])}: '+key[2]);seen.add(key)
        if not seen:lines.append('No warnings or failures recorded.')
        if m.get('provenance_errors'):lines.append('Provenance write/observation failures: '+json.dumps(m['provenance_errors']))
        return '\n'.join(lines)+'\n'

    def export_sanitized(self,path):
        """Local metadata-only ZIP; never includes CIF/HKL/maps, raw responses or credentials."""
        self.checkpoint()
        aliases={}
        def path_alias(value):
            normalized=value.replace('\\\\','\\')
            if normalized not in aliases:aliases[normalized]=f'<LOCAL_PATH_{len(aliases)+1:04d}>'
            return aliases[normalized]
        def sanitize_text(text):
            from .error_reporting import sanitize_error_details
            text=sanitize_error_details(text)
            for local,alias in sorted(aliases.items(),key=lambda item:-len(item[0])):text=text.replace(local,alias)
            text=re.sub(r'[A-Za-z]:[\\/][^\r\n"<>]*',lambda match:path_alias(match.group()),text)
            text=re.sub(r'/(?:Users|home)/[^\s"<>]+',lambda match:path_alias(match.group()),text)
            text=re.sub(r'(?i)(job[_ -]?id["\s:=>]*)(\d+)',r'\1<REMOTE_ID>',text)
            return text
        def sanitized(value,key=''):
            if re.search(r'(?i)(?:job|request|inference)[_ -]?id',key):return '<REMOTE_ID>'
            if isinstance(value,dict):
                return {path_alias(str(k)) if re.match(r'^[A-Za-z]:[\\/]|^/(?:Users|home)/',str(k)) else str(k):sanitized(v,str(k)) for k,v in value.items()}
            if isinstance(value,list):return [sanitized(v,key) for v in value]
            if isinstance(value,str):
                if re.match(r'^[A-Za-z]:[\\/]|^/(?:Users|home)/',value):return path_alias(value)
                return sanitize_text(value)
            return value
        data={}
        with self.lock:
            for name in ('run_manifest.json','summary.md','events.jsonl','cycle_metrics.csv'):
                source=self.session/name
                if source.is_file():
                    text=source.read_text(encoding='utf8')
                    if name.endswith('.json'):data[name]=json.dumps(sanitized(json.loads(text)),indent=2,sort_keys=True,allow_nan=False)
                    elif name.endswith('.jsonl'):
                        data[name]=''.join(json.dumps(sanitized(json.loads(line)),sort_keys=True,allow_nan=False)+'\n' for line in text.splitlines() if line.strip())
                    elif name.endswith('.csv'):
                        reader=csv.DictReader(io.StringIO(text));buffer=io.StringIO()
                        writer=csv.DictWriter(buffer,fieldnames=reader.fieldnames);writer.writeheader()
                        writer.writerows(sanitized(row) for row in reader);data[name]=buffer.getvalue()
                    else:data[name]=sanitize_text(text)
            for name in ('log.txt','diagnostic.log'):
                source=self.directory/name
                if source.is_file():data[name]=sanitize_text(source.read_text(encoding='utf8'))
        checksums=''.join(f'{hashlib.sha256(value.encode("utf8")).hexdigest()}  {key}\n' for key,value in sorted(data.items()))
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
            for key,value in sorted(data.items()):archive.writestr(key,value)
            archive.writestr('checksums.sha256',checksums)
            archive.writestr('README.txt','Sanitized metadata-only diagnostic bundle. No scientific input/output arrays or structures. Exact local paths and remote job identifiers removed.\n')

    def close(self):
        with self.lock:
            if self.manifest['status'] in {'prepared','running','resuming'}:
                self.manifest['status']='interrupted';self.manifest['finished']=timestamp();self.checkpoint()
            self._events.flush();self._events.close()
