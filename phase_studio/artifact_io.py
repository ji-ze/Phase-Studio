"""Finalize reader-specific map representations without mutating their source."""
from pathlib import Path
import os
import tempfile


def normalize_map_atomically(source, destination, reader, writer, log=None, consumer='strict reader'):
    from .run_provenance import active_provenance, active_provenance_cycle, file_identity, record
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve() or (destination.exists() and source.samefile(destination)):
        raise ValueError('Map normalization requires a separate output path; preserve the original map.')
    before = file_identity(source, 'original map')
    data = reader(source)
    after = file_identity(source, 'original map')
    if before['status'] != 'Available' or before['sha256'] != after['sha256']:
        raise ValueError('The source map changed during normalization. Retry with a finalized original map.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix='.'+destination.name+'.', suffix='.tmp', dir=destination.parent)
    os.close(handle)
    temporary = Path(temporary)
    try:
        # Preserve the established writer, precision, grid, cell and axis order.
        writer(temporary, data, title=data.title, values_per_line=1)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    identity = file_identity(destination, consumer+' finalized map')
    provenance = active_provenance()
    if provenance is not None:
        record(provenance, 'event', 'map_representation_finalized', consumer, active_provenance_cycle(),
               dict(source=after, output=identity, numerical_policy='Existing XPLOR writer precision unchanged; separate representation.'))
    if log:
        log(f'XPLOR map normalized atomically for {consumer}: {source} -> {destination} · SHA-256 {identity["sha256"]}')
    return destination
