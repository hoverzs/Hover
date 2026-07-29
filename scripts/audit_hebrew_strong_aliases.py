from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bible_engine.hebrew_parser import strip_hebrew_accents  # noqa: E402
from bible_engine.hebrew_sqlite import DEFAULT_TAHOT_DATABASE_PATH, DEFAULT_TBESH_DATABASE_PATH  # noqa: E402
from bible_engine.paths import GENERATED_DATA_DIR  # noqa: E402


_STRONG_RE = re.compile(r"H\d{4}[A-Z]?", re.IGNORECASE)
_SUFFIX_RE = re.compile(r"^(H\d{4})([A-Z])$")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit TAHOT Strong/STEP IDs against TBESH.")
    parser.add_argument("--tahot-database", type=Path, default=DEFAULT_TAHOT_DATABASE_PATH)
    parser.add_argument("--tbesh-database", type=Path, default=DEFAULT_TBESH_DATABASE_PATH)
    parser.add_argument("--tbesh-source", type=Path, default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=GENERATED_DATA_DIR / "tahot_strong_alias_audit.json",
    )
    parser.add_argument(
        "--decisions-output",
        type=Path,
        default=GENERATED_DATA_DIR / "hebrew_strong_alias_decisions.json",
    )
    args = parser.parse_args()
    audit = audit_hebrew_strong_aliases(args.tahot_database, args.tbesh_database, args.tbesh_source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(audit["summary"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.decisions_output.parent.mkdir(parents=True, exist_ok=True)
    args.decisions_output.write_text(
        json.dumps(audit["decisions"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = audit["summary"]
    print(f"Unique Strong/STEP IDs: {summary['unique_strong_ids']}")
    print(f"Direct TBESH matches: {summary['direct_tbesh_matches']}")
    print(f"Alias matches: {summary['alias_matches']}")
    print(f"Unresolved IDs: {summary['unresolved_strong_ids_count']}")
    print(f"Token coverage: {summary['token_coverage_percent']:.2f}%")
    print(f"Unique ID coverage: {summary['unique_id_coverage_percent']:.2f}%")
    print(f"Decisions: {args.decisions_output}")


def audit_hebrew_strong_aliases(
    tahot_database: Path,
    tbesh_database: Path,
    tbesh_source: Path | None = None,
) -> dict[str, object]:
    with sqlite3.connect(tahot_database) as tahot, sqlite3.connect(tbesh_database) as tbesh:
        join_column = _token_strong_join_column(tahot)
        token_counts = Counter(
            {
                row[0]: int(row[1])
                for row in tahot.execute(
                    f"""
                    SELECT strong_id, COUNT(DISTINCT {join_column})
                    FROM token_strong_ids
                    GROUP BY strong_id
                    """
                )
            }
        )
        metadata = _metadata_by_strong(tahot)
        tbesh_entries = _tbesh_entries(tbesh)
    tbesh_ids = set(tbesh_entries)
    legacy_raw_ids = _legacy_raw_tbesh_ids(tbesh_source) if tbesh_source and tbesh_source.exists() else set()
    decision_ids = set(token_counts)
    if legacy_raw_ids:
        decision_ids = {strong_id for strong_id in token_counts if strong_id not in legacy_raw_ids}

    decisions = [
        _decision_record(strong_id, token_counts[strong_id], metadata[strong_id], tbesh_entries, legacy_raw_ids)
        for strong_id in sorted(decision_ids, key=lambda item: (-token_counts[item], item))
    ]
    direct_ids = {strong_id for strong_id in token_counts if strong_id in tbesh_ids}
    missing_ids = [strong_id for strong_id in token_counts if strong_id not in tbesh_ids]
    total_token_refs = sum(token_counts.values())
    missing_token_refs = sum(token_counts[strong_id] for strong_id in missing_ids)
    summary = {
        "unique_strong_ids": len(token_counts),
        "direct_tbesh_matches": len(direct_ids),
        "alias_matches": 0,
        "high_confidence_alias_candidates": 0,
        "unresolved_strong_ids_count": len(missing_ids),
        "unresolved_token_count": missing_token_refs,
        "token_coverage_percent": 100.0 * (total_token_refs - missing_token_refs) / total_token_refs,
        "unique_id_coverage_percent": 100.0 * len(direct_ids) / len(token_counts),
        "legacy_unresolved_or_parser_affected_ids": len(decision_ids),
        "decision_counts": dict(Counter(item["decision"] for item in decisions)),
        "evidence_type_counts": dict(Counter(item["evidence_type"] for item in decisions)),
        "records": [
            item for item in decisions if item["decision"] not in {"direct_after_tbesh_normalization"}
        ],
    }
    return {"summary": summary, "decisions": decisions}


def _metadata_by_strong(connection: sqlite3.Connection) -> dict[str, dict[str, object]]:
    join_column = _token_strong_join_column(connection)
    data: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "lemmas": Counter(),
            "languages": Counter(),
            "morphology": Counter(),
            "examples": [],
        }
    )
    for row in connection.execute(
        f"""
        SELECT s.strong_id, t.stable_token_key, t.book, t.chapter, t.verse, t.surface,
               t.lemma, t.language, t.morphology_code
        FROM token_strong_ids s
        JOIN tokens t ON t.{join_column} = s.{join_column}
        ORDER BY t.token_index
        """
    ):
        strong_id = row[0]
        data[strong_id]["lemmas"][row[6] or ""] += 1  # type: ignore[index]
        data[strong_id]["languages"][row[7] or ""] += 1  # type: ignore[index]
        data[strong_id]["morphology"][row[8] or ""] += 1  # type: ignore[index]
        examples = data[strong_id]["examples"]
        if isinstance(examples, list) and len(examples) < 10:
            examples.append(
                {
                    "stable_token_key": row[1],
                    "reference": f"{row[2]} {row[3]}:{row[4]}",
                    "surface": row[5],
                    "morphology_code": row[8],
                }
            )
    return data


def _token_strong_join_column(connection: sqlite3.Connection) -> str:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(token_strong_ids)")}
    return "token_id" if "token_id" in columns else "stable_token_key"


def _tbesh_entries(connection: sqlite3.Connection) -> dict[str, dict[str, str]]:
    return {
        row[0]: {"hebrew": row[1] or "", "morph": row[2] or "", "gloss": row[3] or ""}
        for row in connection.execute("SELECT strong_id, hebrew, morph, gloss FROM lexicon_entries")
    }


def _legacy_raw_tbesh_ids(source: Path | None) -> set[str]:
    if source is None:
        return set()
    ids: set[str] = set()
    for raw_line in source.read_text(encoding="utf-8-sig").splitlines():
        if not raw_line.strip() or raw_line.startswith(("=", "$", "eStrong#")):
            continue
        fields = next(csv.reader([raw_line.rstrip("\n")], delimiter="\t"))
        for field in fields[:3]:
            value = field.strip().upper()
            if value:
                ids.add(value)
    return ids


def _decision_record(
    strong_id: str,
    count: int,
    metadata: dict[str, object],
    tbesh_entries: dict[str, dict[str, str]],
    legacy_raw_ids: set[str],
) -> dict[str, object]:
    base = _base_candidate(strong_id)
    lemmas = metadata["lemmas"].most_common()  # type: ignore[union-attr]
    languages = metadata["languages"].most_common()  # type: ignore[union-attr]
    morphology = metadata["morphology"].most_common()  # type: ignore[union-attr]
    lemma = lemmas[0][0] if lemmas else ""
    language = languages[0][0] if languages else ""
    direct = strong_id in tbesh_entries
    candidate = _candidate_target(strong_id, base, lemma, tbesh_entries)
    candidate_exists = candidate in tbesh_entries
    evidence_type, evidence, confidence, decision = _classify(
        strong_id,
        direct,
        base,
        candidate,
        candidate_exists,
        lemma,
        language,
        tbesh_entries,
        legacy_raw_ids,
    )
    return {
        "source_id": strong_id,
        "normalized_base_candidate": base,
        "lemma": lemma,
        "language": language,
        "occurrence_count": count,
        "affected_tokens": count,
        "direct_tbesh_match": direct,
        "candidate_target": candidate,
        "candidate_target_exists": candidate_exists,
        "evidence_type": evidence_type,
        "evidence": evidence,
        "confidence": confidence,
        "decision": decision,
        "morphology_examples": [item[0] for item in morphology[:10]],
        "example_references": metadata["examples"],
    }


def _base_candidate(strong_id: str) -> str:
    match = _SUFFIX_RE.match(strong_id)
    return match.group(1) if match else ""


def _candidate_target(
    strong_id: str,
    base: str,
    lemma: str,
    tbesh_entries: dict[str, dict[str, str]],
) -> str:
    if strong_id in tbesh_entries:
        return strong_id
    if base and base in tbesh_entries:
        return base
    normalized_lemma = strip_hebrew_accents(lemma)
    matches = [
        strong_id
        for strong_id, entry in tbesh_entries.items()
        if normalized_lemma and strip_hebrew_accents(entry["hebrew"]) == normalized_lemma
    ]
    return matches[0] if len(matches) == 1 else ""


def _classify(
    strong_id: str,
    direct: bool,
    base: str,
    candidate: str,
    candidate_exists: bool,
    lemma: str,
    language: str,
    tbesh_entries: dict[str, dict[str, str]],
    legacy_raw_ids: set[str],
) -> tuple[str, str, str, str]:
    if direct and legacy_raw_ids and strong_id not in legacy_raw_ids:
        return (
            "tbesh_strong_field_normalization",
            "The corrected TBESH parser extracts Strong IDs from annotated TBESH fields, so this ID is now direct.",
            "high",
            "direct_after_tbesh_normalization",
        )
    if direct:
        return ("direct_tbesh", "Direct normalized TBESH record exists.", "high", "direct")
    if not lemma:
        return (
            "source_or_parser_variant",
            "TAHOT token has no lemma in the parsed expanded Strong field; keep unresolved for manual source review.",
            "low",
            "source_or_parser_review",
        )
    if language == "aramaic":
        return (
            "hebrew_aramaic_distinction",
            "Aramaic token points to a Hebrew-numbered extended ID; do not alias without documented TBESH target.",
            "low",
            "manual_review",
        )
    if candidate_exists and base and candidate == base:
        return (
            "base_exists_same_lemma",
            "Base Strong exists and the lemma is compatible, but the suffix may mark a homograph or semantic distinction.",
            "medium",
            "manual_review",
        )
    if candidate_exists:
        return (
            "same_lemma_other_record",
            "A TBESH record with matching lemma exists under another ID, but this may be a homograph distinction.",
            "medium",
            "manual_review",
        )
    if base and not candidate_exists:
        return (
            "own_lexical_record_needed",
            "No direct TBESH record and no safe target record exists for the normalized base candidate.",
            "low",
            "separate_lexeme_or_source_review",
        )
    return (
        "malformed_or_nonstandard_id",
        "The ID does not match a standard uppercase extended Strong suffix shape after normalization.",
        "low",
        "source_or_parser_review",
    )


if __name__ == "__main__":
    main()
