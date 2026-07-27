from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.tbesg_sqlite import import_tbesg_lexicon, validate_tbesg_database


DEFAULT_OUTPUT = ROOT / "data" / "generated" / "tbesg_lexicon.sqlite3"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a local SQLite database for the STEPBible TBESG Greek lexicon."
    )
    parser.add_argument(
        "--source",
        required=True,
        type=Path,
        help="Path to the official TBESG TSV file",
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
    if not args.source.exists():
        raise SystemExit(f"TBESG source file not found: {args.source}")

    report = import_tbesg_lexicon(
        source_path=args.source,
        database_path=args.output,
        source_version=args.source_version,
    )
    validation = validate_tbesg_database(args.output)
    database_size = args.output.stat().st_size if args.output.exists() else 0

    print(
        "Import complete: "
        f"rows_read={report.rows_read}, "
        f"rows_imported={report.rows_imported}, "
        f"rows_skipped={report.rows_skipped}, "
        f"parse_errors={report.parse_errors}, "
        f"duplicate_rows={report.duplicate_rows}, "
        f"missing_strong_rows={report.missing_strong_rows}, "
        f"entry_count={validation.entry_count}, "
        f"database_size={database_size}, "
        f"database={report.database_path}"
    )


if __name__ == "__main__":
    main()
