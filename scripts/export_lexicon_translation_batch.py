from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.lexicon_translation_workflow import export_untranslated_lexicon_batch


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export untranslated TBESG lexicon records for offline Hungarian translation."
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--order-by", default="nt_frequency", choices=("nt_frequency", "strong_id"))
    parser.add_argument("--tbesg-database", type=Path, default=None)
    parser.add_argument("--tagnt-database", type=Path, default=None)

    args = parser.parse_args()
    report = export_untranslated_lexicon_batch(
        output_path=args.output,
        limit=args.limit,
        offset=args.offset,
        order_by=args.order_by,
        tbesg_database_path=args.tbesg_database,
        tagnt_database_path=args.tagnt_database,
    )

    print(
        "Export complete: "
        f"records={report.records_exported}, "
        f"first={report.first_strong_id}, "
        f"last={report.last_strong_id}, "
        f"output={report.output_path}"
    )
    for warning in report.warnings:
        print(f"Warning: {warning}")


if __name__ == "__main__":
    main()
