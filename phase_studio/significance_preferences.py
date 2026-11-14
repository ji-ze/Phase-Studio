"""Explicit, compatible advanced significance preferences; legacy defaults are not consent."""
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
import weakref
from PySide6.QtCore import QObject,Slot


def preference_key(profile, sources):
    identity='\n'.join([profile,str(sources[0]),*[str(Path(p).expanduser().absolute()) if p else '' for p in sources[1:]]])
    return hashlib.sha256(identity.encode('utf8')).hexdigest()


def quantity(mode):
    from . import app as a
    mode=a.normalize_reflection_data_mode(mode)
    if mode in (a.REFLECTION_DATA_MODE_INTENSITY,a.REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA):return 'measured-intensity'
    if mode in (a.REFLECTION_DATA_MODE_AMPLITUDE_MEASURED_SIGMA,a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA):return 'measured-amplitude'
    return None


def load_explicit(settings,profile,project,mode):
    group=quantity(mode)
    if group is None:return 0.0,'unavailable'
    for key,origin in [(f'significance/v1/projects/{project}','project'),
                       (f'significance/v1/last/{profile}/{group}','last explicit')]:
        try:
            value=json.loads(str(settings.value(key,'')))
            number=float(value['value'])
            if value.get('explicit') is True and (value.get('quantity')==group or (origin=='project' and number==0)) and math.isfinite(number) and 0<=number<=100:
                return number,origin
        except (ValueError,TypeError,KeyError):pass
    return 0.0,'zero default'


def save_explicit(settings,profile,project,mode,value):
    value=float(value);group=quantity(mode)
    if not math.isfinite(value) or not 0<=value<=100 or (value>0 and group is None):
        raise ValueError('A positive threshold requires compatible measured uncertainties.')
    # A zero project record must take precedence over a previous positive last
    # value when the user explicitly resets this project.
    record=json.dumps(dict(explicit=True,quantity=group,value=value))
    settings.setValue(f'significance/v1/projects/{project}',record)
    if group:settings.setValue(f'significance/v1/last/{profile}/{group}',record)
    settings.sync()


class SignificancePreferenceController(QObject):
    def __init__(self,win):
        super().__init__(win)
        from .input_readiness import InputReadinessLoader
        self._win=weakref.ref(win);self.internal=False
        self.loader=InputReadinessLoader(win)
        self.loader.completed.connect(self.completed)
        self.loader.failed.connect(self.failed)
        self.widget.valueChanged.connect(self.user_value_changed)
        win.significance_save_button.clicked.connect(self.save)
        win.significance_reset_button.clicked.connect(self.reset)
        for name in ['jana_inflip','hkl']:
            win.inputs[name].edit.editingFinished.connect(self.reload)
        for name in ['input_source_mode','reflection_data_mode']:
            win.inputs[name].activated.connect(self.reload)

    @property
    def win(self):return self._win()

    @property
    def widget(self):return self.win.inputs['i_over_sigma_min']

    @Slot(float)
    def user_value_changed(self,_value):
        if not self.internal:self.loader.cancel()

    def scope(self):
        win=self.win
        profile='jana-full' if win.jana_wizard_context.launched_from_jana_wizard else 'standalone-advanced'
        sources=(win._combo_value('input_source_mode'),win._path_value('jana_inflip'),win._path_value('hkl'))
        project=preference_key(profile,sources)
        mode=win._resolve_configured_data_mode_for_ui()
        cfg=SimpleNamespace(input_source_mode=sources[0],jana_inflip=Path(sources[1]) if sources[1] else None,
            hkl=Path(sources[2]) if sources[2] else Path(),reflection_data_mode=win._combo_value('reflection_data_mode'),
            i_over_sigma_min=self.widget.value())
        return profile,project,mode,cfg

    def set_value(self,value):
        self.internal=True
        try:self.widget.setValue(value)
        finally:self.internal=False

    def mark(self,source):
        origins=getattr(self.win,'_setting_origins',None)
        if origins is not None:origins.mark('i_over_sigma_min',source)

    def sync_enabled(self):
        _,_,mode,_=self.scope()
        locked=getattr(self.win,'_configuration_locked',False)
        enabled=not locked and quantity(mode) is not None and self.win.jana_wizard_context.launch_mode not in ('phase_recycling','autosolve')
        self.widget.setEnabled(enabled);self.win.significance_save_button.setEnabled(enabled)
        self.win.significance_reset_button.setEnabled(not locked)
        if locked:self.loader.cancel()

    @Slot()
    def reload(self,*_args):
        self.loader.cancel()
        profile,project,mode,cfg=self.scope()
        self.set_value(0)
        self.mark('Zero default; unconfirmed legacy autosave ignored')
        simple=self.win.jana_wizard_context.launch_mode in ('phase_recycling','autosolve')
        enabled=not simple and quantity(mode) is not None
        self.widget.setEnabled(enabled);self.win.significance_save_button.setEnabled(enabled)
        self.win.significance_status.setText('No significance filtering (0).'+
            ('' if enabled else ' Requires measured uncertainties in Full Configuration.'))
        if not enabled:return
        value,origin=load_explicit(self.win.settings,profile,project,mode)
        if value<=0:return
        cfg.i_over_sigma_min=value
        self.start('load',profile,project,mode,cfg,origin)

    def start(self,action,profile,project,mode,cfg,origin):
        from .reflection_readiness import configuration_identity,validate_configuration_significance
        try:identity=configuration_identity(cfg,mode) if cfg.i_over_sigma_min>0 else None
        except (OSError,TypeError) as error:
            if action=='save':self.failed(error)
            return
        current=self.widget.value()
        def validate(_metadata):
            validate_configuration_significance(cfg,mode)
            return action,profile,project,mode,cfg.i_over_sigma_min,origin,identity,current
        self.loader.start((action,project,mode,identity),validate)

    @Slot()
    def save(self):
        profile,project,mode,cfg=self.scope()
        if cfg.i_over_sigma_min<=0:
            save_explicit(self.win.settings,profile,project,mode,0)
            self.mark('User-confirmed project reset to zero')
            self.win.significance_status.setText('Saved explicit zero for this project.');return
        self.start('save',profile,project,mode,cfg,'confirmed edit')

    @Slot()
    def reset(self):
        self.loader.cancel();self.set_value(0)
        self.save()

    @Slot(object)
    def completed(self,payload):
        from .reflection_readiness import configuration_identity
        action,profile,project,mode,value,origin,identity,current=payload
        now_profile,now_project,now_mode,cfg=self.scope()
        if getattr(self.win,'_configuration_locked',False) or (profile,project,mode)!=(now_profile,now_project,now_mode) or self.widget.value()!=current:return
        try:
            if identity is not None and identity!=configuration_identity(cfg,mode):return
        except (OSError,TypeError):
            self.win.significance_status.setText('Threshold preference not applied: input changed during validation.')
            return
        if action=='save':
            save_explicit(self.win.settings,profile,project,mode,value)
            self.mark('User-confirmed compatible project threshold')
        else:
            self.set_value(value)
            self.mark('Validated '+origin+' significance preference')
        self.win.significance_status.setText(f'{value:.3f} · validated {origin} threshold; direct observed value/σ.')

    @Slot(object)
    def failed(self,error):
        from .error_reporting import build_error_report
        self.win.significance_status.setText('Threshold preference not applied: measured uncertainties could not be verified.')
        # A background restore retains the zero default. An explicit invalid
        # edit stays visible and receives actionable validation without saving.
        if self.widget.value()>0:self.win._show_error_report(build_error_report(error,subsystem='Input',operation='Save significance threshold'))
