from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.nt_lexicon_coverage import (  # noqa: E402
    DEFAULT_COVERAGE_REPORT_PATH,
    audit_nt_lexicon_coverage,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit Hungarian lexicon coverage for Strong IDs used in TAGNT NT tokens."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_COVERAGE_REPORT_PATH)
    parser.add_argument("--tagnt-database", type=Path, default=None)
    parser.add_argument("--tbesg-database", type=Path, default=None)
    parser.add_argument("--hungarian-lexicon", type=Path, default=None)
    parser.add_argument("--strong-aliases", type=Path, default=None)
    args = parser.parse_args()

    kwargs = {
        "output_path": args.output,
        "tagnt_database_path": args.tagnt_database,
        "tbesg_database_path": args.tbesg_database,
    }
    if args.hungarian_lexicon is not None:
        kwargs["hungarian_lexicon_path"] = args.hungarian_lexicon
    if args.strong_aliases is not None:
        kwargs["strong_aliases_path"] = args.strong_aliases

    report = audit_nt_lexicon_coverage(**kwargs)
    summary = report.summary

    print("NT lexicon coverage audit")
    print("=========================")
    print(f"TAGNT total tokens: {summary['tagnt_total_tokens']}")
    print(f"TAGNT unique Strong IDs: {summary['tagnt_unique_strong_ids']}")
    print(f"TAGNT tokens without Strong ID: {summary['tagnt_tokens_without_strong_id']}")
    print(f"TAGNT Strong IDs found in TBESG: {summary['tagnt_strong_ids_found_in_tbesg']}")
    print(f"TAGNT Strong IDs missing from TBESG: {summary['tagnt_strong_ids_missing_from_tbesg']}")
    print(
        "TAGNT Strong IDs found in Hungarian lexicon: "
        f"{summary['tagnt_strong_ids_found_in_hungarian']}"
    )
    print(
        "TAGNT Strong IDs missing from Hungarian lexicon: "
        f"{summary['tagnt_strong_ids_missing_from_hungarian']}"
    )
    print(
        "TAGNT tokens with Hungarian lexicon: "
        f"{summary['tagnt_tokens_with_hungarian_lexicon']}"
    )
    print(
        "TAGNT tokens without Hungarian lexicon: "
        f"{summary['tagnt_tokens_without_hungarian_lexicon']}"
    )
    print(
        "Token-based Hungarian coverage: "
        f"{summary['tagnt_token_hungarian_coverage_percent']:.2f}%"
    )
    print(
        "Lexeme-based Hungarian coverage: "
        f"{summary['tagnt_lexeme_hungarian_coverage_percent']:.2f}%"
    )
    print(
        "Hungarian lexicon records not used in TAGNT NT: "
        f"{summary['hungarian_strong_ids_not_used_in_tagnt']}"
    )
    print(
        "Alias Hungarian coverage: "
        f"{summary['alias_hungarian_token_count']} tokens, "
        f"{summary['alias_hungarian_lexeme_count']} Strong IDs"
    )
    print(f"Effective token coverage: {summary['effective_token_coverage']:.2f}%")
    print(f"Effective lexeme coverage: {summary['effective_lexeme_coverage']:.2f}%")
    print(f"Unresolved Strong IDs: {summary['unresolved_strong_id_count']}")
    print(f"Unresolved token count: {summary['unresolved_token_count']}")
    if report.missing_tbesg_strong_ids:
        print(
            "Missing TBESG Strong IDs: "
            + ", ".join(report.missing_tbesg_strong_ids[:50])
            + (" ..." if len(report.missing_tbesg_strong_ids) > 50 else "")
        )
    print(f"JSON report: {report.output_path}")


if __name__ == "__main__":
    main()
