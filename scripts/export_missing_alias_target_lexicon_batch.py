from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.lexicon_translation_workflow import (
    DEFAULT_MISSING_ALIAS_TARGET_BATCH_PATH,
    export_missing_alias_target_lexicon_batch,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export untranslated Hungarian lexicon records for missing alias targets."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_MISSING_ALIAS_TARGET_BATCH_PATH)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--offset", type=int, default=0)

    args = parser.parse_args()
    report = export_missing_alias_target_lexicon_batch(
        output_path=args.output,
        limit=args.limit,
        offset=args.offset,
    )

    print("Missing alias target lexicon export")
    print("===================================")
    print(f"Unique alias targets: {report.unique_alias_targets}")
    print(f"Targets already in Hungarian lexicon: {report.targets_already_in_hungarian}")
    print(f"Targets missing from Hungarian lexicon: {report.targets_missing_hungarian}")
    print(f"Targets exportable from TBESG: {report.targets_exportable_from_tbesg}")
    print(f"Targets missing from TBESG: {report.targets_missing_from_tbesg}")
    print(f"Records exported: {report.records_exported}")
    print(f"First Strong ID: {report.first_strong_id or '-'}")
    print(f"Last Strong ID: {report.last_strong_id or '-'}")
    print(f"Exported alias-token frequency: {report.exported_token_frequency}")
    print(f"JSON batch: {report.output_path}")


if __name__ == "__main__":
    main()
