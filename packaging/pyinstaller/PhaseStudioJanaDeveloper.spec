# Reuse the established Jana runtime without changing its launcher protocol.
from pathlib import Path
root = Path(SPECPATH).resolve().parent.parent
developer_build = True
SPECPATH = str(root)
exec(compile((root / "superflip.spec").read_text(encoding="utf-8"), str(root / "superflip.spec"), "exec"))
