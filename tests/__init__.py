import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "app" / "src", ROOT / "01-region-sweep"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
