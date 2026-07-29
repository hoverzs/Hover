from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bible_engine.hebrew_lexicon_translation_workflow import build_hebrew_lexicon_priority_audit  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the prioritized Hebrew/Aramaic lexicon translation audit.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit = build_hebrew_lexicon_priority_audit(output_path=args.output)
    print(f"Priority audit records: {len(audit['records'])}; output={args.output}")


if __name__ == "__main__":
    main()
