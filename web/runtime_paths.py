"""Keep persistent research data separate from GitHub deployment checkouts."""
import os
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("SOCIALFLUX_DATA_ROOT", CODE_ROOT)).expanduser().resolve()
if not DATA_ROOT.is_dir():
    raise RuntimeError("SOCIALFLUX_DATA_ROOT must point to an existing project data directory")
