"""Create an empty SQLite copy of the published NC business-registration layout."""

import argparse
from contextlib import closing
from pathlib import Path
import sqlite3


SCHEMA = Path(__file__).resolve().parents[1] / "databases" / "nc_business_registration.sql"


def create_database(path: Path) -> None:
    schema = SCHEMA.read_text(encoding="utf-8")
    # Reserve a new file so this command cannot alter an existing case or registry.
    path.touch(exist_ok=False)
    try:
        with closing(sqlite3.connect(path)) as connection:
            connection.executescript(schema)
    except BaseException:
        path.unlink()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, help="New file in an existing directory")
    args = parser.parse_args()
    try:
        create_database(args.database)
    except (OSError, sqlite3.Error) as exc:
        parser.exit(1, f"Could not create the registry database: {exc}\n")
    print(f"Created empty NC business-registration database: {args.database}")


if __name__ == "__main__":
    main()
