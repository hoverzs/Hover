#!/usr/bin/env python3
"""CLI for the biblical place import pipeline.

Examples:
  python scripts/import_biblical_places.py --dry-run
  python scripts/import_biblical_places.py
  python scripts/import_biblical_places.py --no-download
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biblical_map_import.pipeline import places_file_fingerprint, run_import


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import biblical pilot places")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing outputs")
    parser.add_argument("--no-download", action="store_true", help="Use existing raw files only")
    parser.add_argument("--force-download", action="store_true", help="Re-download raw sources")
    parser.add_argument(
        "--check-idempotent",
        action="store_true",
        help="Run twice and fail if pilot_places.json changes on the second pass",
    )
    args = parser.parse_args(argv)

    report = run_import(
        dry_run=args.dry_run,
        download=not args.no_download,
        force_download=args.force_download,
    )
    for message in report.messages:
        print(message)
    for warning in report.warnings:
        print("WARNING:", warning)
    for error in report.errors:
        print("ERROR:", error)

    if args.check_idempotent and not args.dry_run:
        before = places_file_fingerprint()
        second = run_import(dry_run=False, download=False, force_download=False)
        after = places_file_fingerprint()
        if before != after:
            print("ERROR: idempotency check failed; second run changed pilot_places.json")
            for error in second.errors:
                print("ERROR:", error)
            return 2
        print("Idempotency check passed.")

    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
