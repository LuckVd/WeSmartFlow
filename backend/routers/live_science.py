"""Expose the live_science（知识之境）API through the main WeSmartFlow API."""

import sys
from pathlib import Path

_live_dir = Path(__file__).resolve().parents[2] / "examples" / "live_science"
if str(_live_dir) not in sys.path:
    sys.path.insert(0, str(_live_dir))

from live_science_api import router  # noqa: E402,F401
