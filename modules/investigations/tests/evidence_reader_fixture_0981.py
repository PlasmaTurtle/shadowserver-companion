"""Generate only synthetic portable evidence for the focused file:// browser check."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT)]
from tests.fixture_paths import configure_fixture_imports

configure_fixture_imports(ROOT)

from modules.investigations.tests.support.evidence_workspace import evidence_package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    if args.workspace.exists():
        raise SystemExit("Use a new synthetic package directory")
    evidence_package(args.workspace)
    print(args.workspace / "Evidence_Record.html")


if __name__ == "__main__":
    main()
