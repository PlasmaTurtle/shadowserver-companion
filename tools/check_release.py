"""Check version consistency and the manual home-validation release gate."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from modules.workspace.components.release import (
    load_release,
    check_output_name as check_output_name,
)


def verify(root=ROOT):
    # VERSION supplies the Python runtime version. RELEASE.json deliberately
    # binds channel and acceptance metadata to that version; npm is dev tooling.
    return load_release(root)


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
