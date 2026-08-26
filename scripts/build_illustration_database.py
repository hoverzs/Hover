from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from illustration_engine.illustration_sqlite import (
    DEFAULT_DATABASE_PATH,
    check_integrity,
    create_schema,
)
from illustration_engine.jataka_importer import import_jataka_book
from illustration_engine.jataka_parser import JATAKA_TALES_1912, MORE_JATAKA_TALES_1922
from illustration_engine.paths import RAW_DATA_DIR


DEFAULT_JATAKA_TALES_SOURCE = RAW_DATA_DIR / "pg62514_jataka_tales.txt"
DEFAULT_MORE_JATAKA_TALES_SOURCE = RAW_DATA_DIR / "pg7518_more_jataka_tales.txt"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build/update the local illustration SQLite database from configured sources."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="Path to the SQLite database (created if missing; existing data is kept).",
    )
    parser.add_argument(
        "--jataka-tales-source",
        type=Path,
        default=DEFAULT_JATAKA_TALES_SOURCE,
        help="Path to the raw PG #62514 'Jataka Tales' plain-text file.",
    )
    parser.add_argument(
        "--more-jataka-tales-source",
        type=Path,
        default=DEFAULT_MORE_JATAKA_TALES_SOURCE,
        help="Path to the raw PG #7518 'More Jataka Tales' plain-text file.",
    )
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(args.output)
    try:
        create_schema(connection)

        for spec, source_path in (
            (JATAKA_TALES_1912, args.jataka_tales_source),
            (MORE_JATAKA_TALES_1922, args.more_jataka_tales_source),
        ):
            if not source_path.exists():
                print(f"SKIP {spec.source_code}: raw source not found at {source_path}")
                continue
            report = import_jataka_book(connection, spec=spec, raw_text_path=source_path)
            print(
                f"Jataka import: source={report.source_code}, "
                f"parsed={report.parsed_count}, inserted={report.inserted_count}, "
                f"skipped_existing={report.skipped_existing_count}, "
                f"raw_sha256={report.raw_file_sha256}"
            )

        integrity = check_integrity(connection)
        if integrity != "ok":
            raise SystemExit(f"Integrity check failed after import: {integrity}")
        connection.commit()
        print(f"Database ready: {args.output} (integrity_check={integrity})")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
