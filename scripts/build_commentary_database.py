"""Build the isolated Commentary DB v1 SQLite store.

No network access by default. Creates an empty v1 database, imports a
local fixture JSON, or imports one or more real Calvin commentary ThML/XML
files (already on disk, or fetched on demand via --calvin-fetch using the
pinned source manifest). Source-independent schema: no Calvin-specific
field exists outside the Calvin-specific import path itself.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from textus_kb.importers.calvin_commentary_thml import (
    CalvinCommentaryImportError,
    import_calvin_commentary_sqlite,
)
from textus_kb.importers.calvin_source_fetch import (
    CalvinSourceFetchError,
    fetch_all_sources,
)
from textus_kb.importers.commentary_sqlite import (
    DEFAULT_DATABASE_PATH,
    DEFAULT_FIXTURE_PATH,
    CommentaryImportError,
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
    mode.add_argument(
        "--calvin-thml",
        nargs="+",
        metavar="PATH",
        help=(
            "Import one or more real Calvin commentary ThML/XML files "
            "(already on disk) into a single combined store."
        ),
    )
    mode.add_argument(
        "--calvin-fetch",
        action="store_true",
        help=(
            "Fetch every source in the Calvin commentary source manifest "
            "(textus_kb/data/calvin_commentary_source_manifest.json), "
            "verify each against its pinned raw_sha256, then import all of "
            "them into a single combined store."
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
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 0

    if args.fixture is not None:
        report = import_commentary_sqlite(
            fixture_path=args.fixture,
            database_path=args.output,
        )
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 0

    xml_paths: list[str] = []
    if args.calvin_fetch:
        try:
            results = fetch_all_sources()
        except CalvinSourceFetchError as exc:
            print(f"Calvin source fetch failed: {exc}", file=sys.stderr)
            return 1
        xml_paths = [str(result.local_path) for result in results]
    else:
        xml_paths = list(args.calvin_thml)

    try:
        report, parse_reports = import_calvin_commentary_sqlite(
            xml_paths, database_path=args.output
        )
    except (CalvinCommentaryImportError, CommentaryImportError) as exc:
        print(f"Calvin commentary import failed: {exc}", file=sys.stderr)
        return 1
    payload = report.to_dict()
    payload["calvin_sources"] = [pr.to_dict() for pr in parse_reports]
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
