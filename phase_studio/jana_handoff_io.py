"""Private native conversion staging and Windows-safe local protocol IO."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from contextvars import ContextVar

_archive_current = ContextVar('jana_handoff_archive', default=None)


def archive_handoff_staging():
    """Archive native evidence while publication can still be rolled back."""
    archive = _archive_current.get()
    if archive is not None:
        archive(True)


class JanaProjectMetadataError(RuntimeError):
    """The original Jana project context is absent or invalid; no substitute exists."""


def filesystem_path(path, *, force=False):
    """Use the Windows extended namespace for IO, without changing identity keys."""
    path = Path(path).absolute()
    text = str(path)
    if os.name == 'nt' and not text.startswith('\\\\?\\') and (force or len(text) >= 240):
        return Path('\\\\?\\UNC\\' + text[2:] if text.startswith('\\\\') else '\\\\?\\' + text)
    return path


def copy_protocol_file(source, target):
    """Copy original bytes atomically, including long/Unicode source and target paths."""
    source, target = filesystem_path(source), filesystem_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix='.psj-', suffix='.tmp', dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        shutil.copyfile(source, temporary)
        with source.open('rb') as stream:
            expected = hashlib.file_digest(stream, 'sha256').digest()
        with temporary.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').digest() != expected:
                raise OSError('Jana2020 protocol copy failed its source checksum check.')
        os.replace(temporary, target)
    except OSError as error:
        error.add_note(f'Local Jana2020 copy source: {source}\nLocal Jana2020 copy destination: {target}')
        raise
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def handoff_staging(work_dir, candidate_id, longest_name):
    """Keep ordinary evidence in-run; move only long native paths to private temp.

    A retry receives a new directory. No existing job or evidence is deleted.
    Short native working directories are archived before their scoped cleanup.
    """
    root = filesystem_path(Path(work_dir) / 'jana_handoff')
    if len(str(root))>190:root=filesystem_path(root,force=True)
    root.mkdir(parents=True, exist_ok=True)
    token = hashlib.sha256(str(candidate_id).encode('utf8')).hexdigest()[:12]
    evidence = Path(tempfile.mkdtemp(prefix='candidate-'+token+'-',dir=root))
    use_short = len(str(evidence)) + int(longest_name) + 40 >= 240
    if not use_short:
        yield evidence
        return
    with tempfile.TemporaryDirectory(prefix='psjh-') as temporary:
        stage = Path(temporary)
        archived = False
        def archive(completed):
            nonlocal archived
            for source in stage.iterdir():
                if source.is_file():
                    copy_protocol_file(source, evidence / source.name)
            filesystem_path(evidence / 'staging.json').write_text(json.dumps({
                'candidate_id': str(candidate_id), 'short_native_staging': True,
                'completed': completed, 'native_directory': str(stage),
            }, indent=2), encoding='utf8')
            archived = True
        token = _archive_current.set(archive)
        try:
            yield stage
            if not archived:
                archive(True)
        finally:
            # Archive only this attempt's own files. Original project outputs,
            # other candidates and previous attempts are never cleanup targets.
            _archive_current.reset(token)
            if not archived:
                archive(False)
