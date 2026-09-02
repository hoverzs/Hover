"""Build the isolated Commentary DB v1 SQLite store.

No network access. Creates an empty v1 database or imports a local fixture
JSON. Source-independent: no Calvin-specific (or any other author-specific)
import path exists here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from textus_kb.importers.commentary_sqlite import (
    DEFAULT_DATABASE_PATH,
    DEFAULT_FIXTURE_PATH,
    create_empty_commentary_database,
    import_commentary_sqlite,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the local Commentary DB v1 SQLite store."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--empty",
        action="store_true",
        help="Create an empty v1 schema with store_metadata only.",
    )
    mode.add_argument(
        "--fixture",
        nargs="?",
        const=str(DEFAULT_FIXTURE_PATH),
        metavar="PATH",
        help=(
            "Import a local fixture JSON. "
            f"Defaults to {DEFAULT_FIXTURE_PATH.as_posix()} when PATH is omitted."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="Path to the generated SQLite database.",
    )
    args = parser.parse_args(argv)

    if args.empty:
        report = create_empty_commentary_database(args.output)
    else:
        report = import_commentary_sqlite(
            fixture_path=args.fixture,
            database_path=args.output,
        )
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
