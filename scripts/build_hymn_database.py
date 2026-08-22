from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.hymn_sqlite import DEFAULT_DATABASE_PATH, import_dtx_hymnal_database


DEFAULT_SOURCE = ROOT / "data" / "raw" / "hymnals" / "ERE.dtx"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the local normalized hymn SQLite database from DiaTar DTX sources."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Path to the DiaTar DTX source file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="Path to the generated SQLite database.",
    )
    parser.add_argument(
        "--hymnal-code",
        default="ERE",
        help="Stable hymnal code to store in the database.",
    )
    parser.add_argument(
        "--source-version",
        default="",
        help="Optional source version label stored in hymnals/import_meta.",
    )
    args = parser.parse_args()

    report = import_dtx_hymnal_database(
        args.source,
        args.output,
        hymnal_code=args.hymnal_code,
        source_version=args.source_version,
    )

    print(
        "Hymn import complete: "
        f"hymnal_code={report.hymnal_code}, "
        f"hymns={report.hymn_count}, "
        f"base_numbers={report.base_number_count}, "
        f"sections={report.section_count}, "
        f"stanzas={report.stanza_count}, "
        f"parser_warnings={report.parser_warning_count}, "
        f"source_checksum={report.source_checksum}, "
        f"database={report.database_path}"
    )


if __name__ == "__main__":
    main()
