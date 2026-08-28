"""Expose the Chemistry Lab Agent through the main WeSmartFlow API."""

import sys
from pathlib import Path

_course_dir = Path(__file__).resolve().parents[2] / "examples" / "chemastry_lab"
if str(_course_dir) not in sys.path:
    sys.path.insert(0, str(_course_dir))

from chemistry_lab_api import router  # noqa: E402,F401
