from pathlib import Path

store_build = True
shared_spec = Path(SPECPATH) / "PhaseStudio.spec"
exec(compile(shared_spec.read_text(encoding="utf-8"), str(shared_spec), "exec"))
