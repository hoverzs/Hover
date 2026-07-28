from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bible_engine.hebrew_morphology import audit_morphology_codes, load_tehmc_expansions  # noqa: E402
from bible_engine.hebrew_sqlite import DEFAULT_TAHOT_DATABASE_PATH  # noqa: E402
from bible_engine.paths import GENERATED_DATA_DIR  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Hebrew morphology code coverage.")
    parser.add_argument("--tahot-database", type=Path, default=DEFAULT_TAHOT_DATABASE_PATH)
    parser.add_argument("--tehmc-source", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=GENERATED_DATA_DIR / "hebrew_morphology_coverage.json",
    )
    args = parser.parse_args()

    expansions = load_tehmc_expansions(args.tehmc_source)
    with sqlite3.connect(args.tahot_database) as connection:
        codes = [
            row[0]
            for row in connection.execute(
                "SELECT morphology_code FROM tokens WHERE COALESCE(morphology_code, '') <> ''"
            )
        ]
    audit = audit_morphology_codes(codes, expansions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Unique morphology codes: {audit['unique_morphology_codes']}")
    print(f"Fully decoded: {audit['fully_decoded_codes']}")
    print(f"Partially decoded: {audit['partially_decoded_codes']}")
    print(f"Unresolved: {audit['unresolved_codes']}")
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
