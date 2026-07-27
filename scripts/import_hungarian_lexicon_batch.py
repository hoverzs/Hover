from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.lexicon_translation_workflow import import_hungarian_lexicon_batch


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import a reviewed offline Hungarian lexicon translation batch."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=None)

    args = parser.parse_args()
    report = import_hungarian_lexicon_batch(
        input_path=args.input,
        output_path=args.output,
    )

    print(
        "Import complete: "
        f"records_read={report.records_read}, "
        f"records_imported={report.records_imported}, "
        f"records_skipped={report.records_skipped}, "
        f"errors={len(report.errors)}, "
        f"output={report.output_path}"
    )
    for error in report.errors:
        print(f"Error: {error}")
    for warning in report.warnings:
        print(f"Warning: {warning}")


if __name__ == "__main__":
    main()
