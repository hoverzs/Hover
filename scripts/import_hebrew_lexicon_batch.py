from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bible_engine.hebrew_lexicon_translation_workflow import import_hebrew_lexicon_batch  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a validated Hebrew Hungarian lexicon translation batch.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = import_hebrew_lexicon_batch(args.input, output_path=args.output)
    print(f"Read {report.records_read}; imported={report.records_imported}; skipped={report.records_skipped}; errors={len(report.errors)}")
    for error in report.errors:
        print(error)


if __name__ == "__main__":
    main()
