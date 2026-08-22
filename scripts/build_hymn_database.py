from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.hymn_sqlite import (
    DEFAULT_DATABASE_PATH,
    HymnalSourceConfig,
    import_dtx_hymnal_database,
    import_hymnals_database,
)


DEFAULT_ERE_SOURCE = ROOT / "data" / "raw" / "hymnals" / "ERE.dtx"
DEFAULT_RE21_SOURCE = ROOT / "data" / "raw" / "hymnals" / "RE21_master.docx"
RE21_TITLE = "Református Énekeskönyv 2021"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the local normalized hymn SQLite database from hymn sources."
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="Compatibility mode: build one DiaTar DTX source from this path.",
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
    parser.add_argument(
        "--ere-source",
        type=Path,
        default=DEFAULT_ERE_SOURCE,
        help="Path to the ERE DiaTar DTX source file.",
    )
    parser.add_argument(
        "--re21-source",
        type=Path,
        default=DEFAULT_RE21_SOURCE,
        help="Path to the official RÉ21 DOCX source file.",
    )
    args = parser.parse_args()

    if args.source:
        reports = (
            import_dtx_hymnal_database(
                args.source,
                args.output,
                hymnal_code=args.hymnal_code,
                source_version=args.source_version,
            ),
        )
    else:
        reports = import_hymnals_database(
            (
                HymnalSourceConfig(
                    code="ERE",
                    source_path=args.ere_source,
                    source_format="dtx",
                    source_version=args.source_version,
                ),
                HymnalSourceConfig(
                    code="RE21",
                    source_path=args.re21_source,
                    source_format="docx",
                    title=RE21_TITLE,
                    source_version=args.source_version,
                ),
            ),
            args.output,
        )

    for report in reports:
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
