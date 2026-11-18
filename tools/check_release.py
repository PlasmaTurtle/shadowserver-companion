"""Check version consistency and the manual home-validation release gate."""

import ast
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workbench.release import load_release, check_output_name as check_output_name


def verify(root=ROOT):
    release = load_release(root)
    tree = ast.parse((root / "workbench/__init__.py").read_text(encoding="utf-8"))
    versions = [
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets)
    ]
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))
    versions += [package["version"], lock["version"], lock["packages"][""]["version"]]
    if len(versions) != 4 or any(v != release["version"] for v in versions):
        raise ValueError("Python and frontend package versions must match VERSION")
    return release


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
