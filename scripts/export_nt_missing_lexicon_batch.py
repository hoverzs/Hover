from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.nt_lexicon_coverage import export_nt_missing_lexicon_batch  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export untranslated TBESG records whose Strong IDs occur in TAGNT NT tokens."
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--tagnt-database", type=Path, default=None)
    parser.add_argument("--tbesg-database", type=Path, default=None)
    parser.add_argument("--hungarian-lexicon", type=Path, default=None)
    args = parser.parse_args()

    kwargs = {
        "output_path": args.output,
        "limit": args.limit,
        "offset": args.offset,
        "tagnt_database_path": args.tagnt_database,
        "tbesg_database_path": args.tbesg_database,
    }
    if args.hungarian_lexicon is not None:
        kwargs["hungarian_lexicon_path"] = args.hungarian_lexicon

    report = export_nt_missing_lexicon_batch(**kwargs)

    print(
        "NT missing export complete: "
        f"records={report.records_exported}, "
        f"total_missing_nt_records={report.total_missing_nt_records}, "
        f"limit={report.limit}, "
        f"offset={report.offset}, "
        f"first={report.first_strong_id}, "
        f"last={report.last_strong_id}, "
        f"output={report.output_path}"
    )
    for warning in report.warnings:
        print(f"Warning: {warning}")


if __name__ == "__main__":
    main()
