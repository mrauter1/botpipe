from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_PARENT = Path(__file__).resolve().parents[2]

for entry in (str(PACKAGE_ROOT), str(REPO_PARENT)):
    while entry in sys.path:
        sys.path.remove(entry)

for entry in (str(REPO_PARENT), str(PACKAGE_ROOT)):
    sys.path.insert(0, entry)
