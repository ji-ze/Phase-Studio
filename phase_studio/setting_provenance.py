"""Observe setting origins without setting values or changing persistence."""
from copy import deepcopy


class SettingOrigins:
    def __init__(self,owner):
        self.owner=owner;self.records={}
        for key,widget in owner.inputs.items():
            if any(part in key.lower() for part in ('token','password','secret','api_key')):continue
            value=owner._widget_value_as_string(widget)
            self.records[key]=dict(application_default=value,current_displayed_value=value,
                                   source='Application default',persisted_value=None,preset=None)
            target=getattr(widget,'edit',widget)
            for signal in ('textChanged','valueChanged','currentIndexChanged','toggled'):
                event=getattr(target,signal,None)
                if event is not None:
                    event.connect(lambda *_,k=key:self.mark(k,'UI change; actor not recorded'))
                    break
            for signal in ('textEdited','activated','clicked','editingFinished'):
                event=getattr(target,signal,None)
                if event is not None:event.connect(lambda *_,k=key:self.mark(k,'User override'))

    def mark(self,key,source,preset=None):
        if key not in self.records:return
        self.records[key].update(source=source,preset=preset,
            current_displayed_value=self.owner._widget_value_as_string(self.owner.inputs[key]))

    def loaded(self,settings):
        for key,record in self.records.items():
            if key=='i_over_sigma_min':
                continue  # Legacy autosaved defaults are not explicit consent.
            if callable(getattr(settings,'contains',None)) and settings.contains('inputs/'+key):
                record.update(source='Persisted setting, after existing load-time normalization',
                    persisted_value=str(settings.value('inputs/'+key)),
                    current_displayed_value=self.owner._widget_value_as_string(self.owner.inputs[key]))

    def snapshot(self):
        for key,record in self.records.items():
            record['current_displayed_value']=self.owner._widget_value_as_string(self.owner.inputs[key])
        return deepcopy(self.records)
