from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bible_engine.hebrew_lexicon_translation_workflow import (  # noqa: E402
    DEFAULT_LANGUAGE_AUDIT_PATH,
    build_tbesh_language_normalization_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the TBESH language normalization audit.")
    parser.add_argument("--output", type=Path, default=DEFAULT_LANGUAGE_AUDIT_PATH)
    args = parser.parse_args()
    audit = build_tbesh_language_normalization_audit(output_path=args.output)
    print(json.dumps(audit["summary"], ensure_ascii=False, indent=2))
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
