from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.tagnt_sqlite import import_tagnt_new_testament


DEFAULT_OUTPUT = ROOT / "data" / "generated" / "tagnt_nt.sqlite3"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a local SQLite database for TAGNT New Testament tokens."
    )
    parser.add_argument(
        "--mat-jhn-source",
        required=True,
        type=Path,
        help="Path to the official TAGNT Mat-Jhn TSV file",
    )
    parser.add_argument(
        "--act-rev-source",
        required=True,
        type=Path,
        help="Path to the official TAGNT Act-Rev TSV file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to the output SQLite database",
    )
    parser.add_argument(
        "--source-version",
        default=None,
        help="Optional source version label stored with imported rows",
    )

    args = parser.parse_args()
    report = import_tagnt_new_testament(
        mat_jhn_source_path=args.mat_jhn_source,
        act_rev_source_path=args.act_rev_source,
        database_path=args.output,
        source_version=args.source_version,
    )

    print(
        "Import complete: "
        f"books_imported={len(report.books_imported)}, "
        f"rows_read={report.rows_read}, "
        f"rows_imported={report.rows_imported}, "
        f"rows_skipped={report.rows_skipped}, "
        f"parse_errors={report.parse_errors}, "
        f"duplicate_rows={report.duplicate_rows}, "
        f"database={report.database_path}"
    )


if __name__ == "__main__":
    main()
