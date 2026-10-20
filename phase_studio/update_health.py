"""Acknowledge visible startup of a verified update; never resume a calculation."""
import json
import os
from pathlib import Path

_pending=None


def consume(arguments):
    global _pending
    if '--update-health' not in arguments:return
    index=arguments.index('--update-health')
    if index+1>=len(arguments):raise ValueError('Missing update health acknowledgement path.')
    path=Path(arguments[index+1]).absolute()
    from .update_plan import workspace_root
    from .update_transaction import reject_links
    reject_links(path)
    if path.name!='startup.json' or path.parent.parent.resolve()!=workspace_root().resolve():
        raise ValueError('Invalid update health workspace.')
    import uuid
    if str(uuid.UUID(path.parent.name))!=path.parent.name:raise ValueError('Invalid update health session.')
    _pending=path
    del arguments[index:index+2]


def visible(window):
    global _pending
    if _pending is None or not window.isVisible():return
    from .version import VERSION
    path=_pending;_pending=None
    try:
        with path.open('x',encoding='utf8') as stream:json.dump({'version':VERSION,'pid':os.getpid()},stream)
    except OSError:pass  # Helper times out and restores the previous executable.
