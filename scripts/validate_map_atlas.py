from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from grid_map.atlas import validate_map_atlas


def main() -> int:
    errors = validate_map_atlas()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Map atlas is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
