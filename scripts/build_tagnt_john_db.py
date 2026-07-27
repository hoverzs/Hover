from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.tagnt_sqlite import import_tagnt_book


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a local SQLite database for TAGNT John tokens."
    )
    parser.add_argument("source", type=Path, help="Path to the TAGNT Mat-Jhn TSV file")
    parser.add_argument("output", type=Path, help="Path to the output SQLite database")
    parser.add_argument("--book", default="Jhn", help="TAGNT book code to import")
    parser.add_argument(
        "--source-name",
        default="STEPBible TAGNT Mat-Jhn",
        help="Source label stored with imported rows",
    )
    parser.add_argument(
        "--source-version",
        default=None,
        help="Optional source version label stored with imported rows",
    )

    args = parser.parse_args()
    report = import_tagnt_book(
        source_path=args.source,
        database_path=args.output,
        book=args.book,
        source_name=args.source_name,
        source_version=args.source_version,
    )

    print(
        "Import complete: "
        f"book={report.book}, "
        f"rows_read={report.rows_read}, "
        f"rows_imported={report.rows_imported}, "
        f"rows_skipped={report.rows_skipped}, "
        f"parse_errors={report.parse_errors}, "
        f"duplicate_rows={report.duplicate_rows}"
    )


if __name__ == "__main__":
    main()
