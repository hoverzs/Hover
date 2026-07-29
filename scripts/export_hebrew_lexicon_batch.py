from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bible_engine.hebrew_lexicon_translation_workflow import export_hebrew_lexicon_batch  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a prioritized TBESH Hebrew/Aramaic lexicon translation batch.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()
    report = export_hebrew_lexicon_batch(args.output, limit=args.limit, offset=args.offset)
    print(f"Exported {report.records_exported} records to {report.output_path}; first={report.first_strong_id}; last={report.last_strong_id}")


if __name__ == "__main__":
    main()
