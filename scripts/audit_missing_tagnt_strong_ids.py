from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.missing_tagnt_strong_audit import (  # noqa: E402
    DEFAULT_ALIAS_CANDIDATES_PATH,
    DEFAULT_MISSING_AUDIT_PATH,
    DEFAULT_UNRESOLVED_EXPORT_PATH,
    audit_missing_tagnt_strong_ids,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Classify TAGNT Strong IDs that are missing from the local TBESG lexicon."
    )
    parser.add_argument("--coverage-report", type=Path, default=None)
    parser.add_argument("--tagnt-database", type=Path, default=None)
    parser.add_argument("--tbesg-database", type=Path, default=None)
    parser.add_argument("--hungarian-lexicon", type=Path, default=None)
    parser.add_argument("--audit-output", type=Path, default=DEFAULT_MISSING_AUDIT_PATH)
    parser.add_argument("--alias-output", type=Path, default=DEFAULT_ALIAS_CANDIDATES_PATH)
    parser.add_argument("--unresolved-output", type=Path, default=DEFAULT_UNRESOLVED_EXPORT_PATH)
    args = parser.parse_args()

    kwargs = {
        "audit_output_path": args.audit_output,
        "alias_output_path": args.alias_output,
        "unresolved_export_path": args.unresolved_output,
    }
    if args.coverage_report is not None:
        kwargs["coverage_report_path"] = args.coverage_report
    if args.tagnt_database is not None:
        kwargs["tagnt_database_path"] = args.tagnt_database
    if args.tbesg_database is not None:
        kwargs["tbesg_database_path"] = args.tbesg_database
    if args.hungarian_lexicon is not None:
        kwargs["hungarian_lexicon_path"] = args.hungarian_lexicon

    result = audit_missing_tagnt_strong_ids(**kwargs)

    print("Missing TAGNT Strong ID audit")
    print("=============================")
    print("Category counts:")
    for category, count in sorted(result.category_counts.items()):
        print(f"- {category}: {count}")
    print(f"Safe alias candidates: {result.alias_candidate_count}")
    print(f"Alias-covered TAGNT tokens: {result.alias_token_frequency}")
    print(f"Genuinely missing lexemes: {result.genuinely_missing_lexeme_count}")
    print(f"Manual review items: {result.manual_review_count}")
    print(f"Simulated token coverage: {result.simulated_token_coverage_percent:.2f}%")
    print(f"Simulated lexeme coverage: {result.simulated_lexeme_coverage_percent:.2f}%")
    print(f"Unresolved export records: {result.unresolved_export_count}")
    print(f"Audit JSON: {result.audit_path}")
    print(f"Alias candidates JSON: {result.alias_candidates_path}")
    print(f"Unresolved export JSON: {result.unresolved_export_path}")


if __name__ == "__main__":
    main()
