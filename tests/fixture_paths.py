"""Import paths shared by directly executed synthetic browser fixtures."""

from pathlib import Path
import sys


def validate_fixture_imports(root: Path) -> None:
    """Reject ambiguous filenames while pytest uses its default import mode."""
    names: dict[str, Path] = {}
    for directory in [root / "tests", *sorted((root / "modules").glob("*/tests"))]:
        for path in sorted(directory.glob("*.py")):
            name = path.stem.casefold()
            if name in {"__init__", "conftest"}:
                continue
            if name in names:
                previous = names[name].relative_to(root).as_posix()
                current = path.relative_to(root).as_posix()
                raise ValueError(f"Ambiguous test-helper import {name!r}: {previous} and {current}")
            names[name] = path


def configure_fixture_imports(root: Path) -> None:
    """Make project packages and the independent engine available outside pytest."""
    validate_fixture_imports(root)
    paths = [
        root,
        root / "modules/attribution/components/engine/src",
    ]
    sys.path[:0] = [str(path) for path in paths if str(path) not in sys.path]
