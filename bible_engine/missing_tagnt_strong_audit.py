from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bible_engine.lexicon_hu import DEFAULT_HUNGARIAN_LEXICON_PATH, load_hungarian_lexicon
from bible_engine.lexicon_translation_workflow import (
    DEFAULT_REVIEW_STATUS,
    DEFAULT_TRANSLATION_METHOD,
    SCHEMA_VERSION,
    TAGNT_UNRESOLVED_SOURCE_NAME,
)
from bible_engine.nt_lexicon_coverage import (
    DEFAULT_COVERAGE_REPORT_PATH,
    normalize_tagnt_strong_ids,
)
from bible_engine.tbesg_parser import normalize_greek_strong_id


ROOT = Path(__file__).parents[1]
DEFAULT_TAGNT_DATABASE_PATH = ROOT / "data" / "generated" / "tagnt_nt.sqlite3"
DEFAULT_TBESG_DATABASE_PATH = ROOT / "data" / "generated" / "tbesg_lexicon.sqlite3"
DEFAULT_MISSING_AUDIT_PATH = ROOT / "data" / "generated" / "missing_tagnt_strong_id_audit.json"
DEFAULT_ALIAS_CANDIDATES_PATH = ROOT / "data" / "generated" / "tagnt_strong_alias_candidates.json"
DEFAULT_UNRESOLVED_EXPORT_PATH = ROOT / "data" / "translation_batches" / "lexicon_tagnt_unresolved_0001.json"

CLASS_ALIAS = "alias_to_existing_strong"
CLASS_SUFFIX = "suffix_variant"
CLASS_TEXTUAL = "textual_variant"
CLASS_SAME_LEMMA = "same_lemma_existing_record"
CLASS_MISSING = "genuinely_missing_lexeme"
CLASS_MALFORMED = "malformed_or_unknown"
CLASS_REVIEW = "needs_manual_review"
_SUFFIX_RE = re.compile(r"^(G\d{4,5})([A-Z]+)$")
_BROAD_MORPH_RE = re.compile(r"^(?:G:)?(?P<kind>[A-Z]+)")


@dataclass(frozen=True)
class MissingStrongAuditResult:
    audit_path: str
    alias_candidates_path: str
    unresolved_export_path: str
    category_counts: dict[str, int]
    alias_candidate_count: int
    alias_token_frequency: int
    genuinely_missing_lexeme_count: int
    manual_review_count: int
    simulated_token_coverage_percent: float
    simulated_lexeme_coverage_percent: float
    unresolved_export_count: int


def split_tagnt_suffix(strong_id: str) -> tuple[str | None, str | None]:
    normalized = normalize_tagnt_strong_ids(strong_id)
    if not normalized:
        return None, None
    value = normalized[0]
    match = _SUFFIX_RE.fullmatch(value)
    if not match:
        return value, None
    base = normalize_greek_strong_id(match.group(1))
    return base, match.group(2)


def audit_missing_tagnt_strong_ids(
    *,
    coverage_report_path: str | Path = DEFAULT_COVERAGE_REPORT_PATH,
    tagnt_database_path: str | Path = DEFAULT_TAGNT_DATABASE_PATH,
    tbesg_database_path: str | Path = DEFAULT_TBESG_DATABASE_PATH,
    hungarian_lexicon_path: str | Path = DEFAULT_HUNGARIAN_LEXICON_PATH,
    audit_output_path: str | Path = DEFAULT_MISSING_AUDIT_PATH,
    alias_output_path: str | Path = DEFAULT_ALIAS_CANDIDATES_PATH,
    unresolved_export_path: str | Path = DEFAULT_UNRESOLVED_EXPORT_PATH,
) -> MissingStrongAuditResult:
    missing_ids = _missing_tbesg_ids_from_coverage(coverage_report_path)
    tbesg_by_strong, tbesg_by_lemma = _load_tbesg_indexes(tbesg_database_path)
    hu_by_strong, hu_by_lemma = _load_hungarian_indexes(hungarian_lexicon_path)
    coverage_summary = _coverage_summary(coverage_report_path)

    records: list[dict[str, Any]] = []
    alias_candidates: list[dict[str, Any]] = []
    unresolved_records: list[dict[str, Any]] = []
    seen_alias_sources: set[str] = set()

    with sqlite3.connect(tagnt_database_path) as connection:
        for strong_id in missing_ids:
            token_rows = _tagnt_rows_for_strong(connection, strong_id)
            record = _audit_one(
                strong_id,
                token_rows,
                tbesg_by_strong,
                tbesg_by_lemma,
                hu_by_lemma,
            )
            records.append(record)
            alias = record.get("alias_candidate")
            if isinstance(alias, dict) and strong_id not in seen_alias_sources:
                alias_candidates.append(alias)
                seen_alias_sources.add(strong_id)
            if record["classification"] == CLASS_MISSING:
                unresolved_records.append(_unresolved_export_record(record))

    category_counts: dict[str, int] = {}
    for record in records:
        category = str(record["classification"])
        category_counts[category] = category_counts.get(category, 0) + 1

    alias_token_frequency = sum(int(candidate["token_frequency"]) for candidate in alias_candidates)
    unresolved_export = _unresolved_export_data(unresolved_records)
    simulation = _simulation(
        coverage_summary,
        alias_candidate_count=len(alias_candidates),
        alias_token_frequency=alias_token_frequency,
    )
    audit_data = {
        "created_at": datetime.now(UTC).isoformat(),
        "summary": {
            "missing_strong_id_count": len(missing_ids),
            "category_counts": category_counts,
            "alias_candidate_count": len(alias_candidates),
            "alias_token_frequency": alias_token_frequency,
            "genuinely_missing_lexeme_count": category_counts.get(CLASS_MISSING, 0),
            "manual_review_count": category_counts.get(CLASS_REVIEW, 0),
            **simulation,
            "suffix_notes": {
                "G_H_suffix_meaning": (
                    "In the local TAGNT data, trailing letters such as G and H are "
                    "Strong instance/sense suffixes embedded in the token strong_id. "
                    "They are separate from edition_flags. Most resolve to an existing "
                    "numeric base Strong ID or to another local record with the same lemma."
                )
            },
        },
        "records": records,
    }
    alias_data = {
        "created_at": datetime.now(UTC).isoformat(),
        "source": "TAGNT missing Strong ID audit",
        "records": alias_candidates,
    }

    _write_json(audit_output_path, audit_data)
    _write_json(alias_output_path, alias_data)
    _write_json(unresolved_export_path, unresolved_export)

    return MissingStrongAuditResult(
        audit_path=str(audit_output_path),
        alias_candidates_path=str(alias_output_path),
        unresolved_export_path=str(unresolved_export_path),
        category_counts=category_counts,
        alias_candidate_count=len(alias_candidates),
        alias_token_frequency=alias_token_frequency,
        genuinely_missing_lexeme_count=category_counts.get(CLASS_MISSING, 0),
        manual_review_count=category_counts.get(CLASS_REVIEW, 0),
        simulated_token_coverage_percent=float(simulation["simulated_token_coverage_percent"]),
        simulated_lexeme_coverage_percent=float(simulation["simulated_lexeme_coverage_percent"]),
        unresolved_export_count=len(unresolved_records),
    )


def _audit_one(
    strong_id: str,
    token_rows: list[sqlite3.Row],
    tbesg_by_strong: dict[str, dict[str, Any]],
    tbesg_by_lemma: dict[str, list[dict[str, Any]]],
    hu_by_lemma: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    base, suffix = split_tagnt_suffix(strong_id)
    lemmas = _unique_text(row["lemma"] for row in token_rows)
    forms = _unique_text(row["greek_form"] for row in token_rows)
    morphs = _unique_text(row["morph_code"] for row in token_rows)
    edition_flags = _unique_text(row["edition_flags"] for row in token_rows)
    sample_references = [
        _reference(row) for row in token_rows[:10]
    ]
    lemma = lemmas[0] if len(lemmas) == 1 else (lemmas[0] if lemmas else "")
    lemma_key = _lemma_key(lemma)
    base_record = tbesg_by_strong.get(base or "")
    same_tbesg = [
        item for item in tbesg_by_lemma.get(lemma_key, []) if item["strong_id"] != strong_id
    ]
    same_hu = [
        item for item in hu_by_lemma.get(lemma_key, []) if item["strong_id"] != strong_id
    ]

    classification = CLASS_REVIEW
    reason = "multiple or uncertain evidence"
    alias_candidate: dict[str, Any] | None = None
    if not token_rows or not base:
        classification = CLASS_MALFORMED
        reason = "no TAGNT token rows or no parseable Greek Strong ID"
    elif len(lemmas) > 1:
        classification = CLASS_REVIEW
        reason = "multiple TAGNT lemmas for the same Strong ID"
    elif base_record is not None and _lemma_key(str(base_record["lemma"])) == lemma_key and _morph_compatible(morphs, str(base_record.get("morph") or "")):
        classification = CLASS_ALIAS
        reason = "suffix Strong ID has same lemma and compatible morphology as numeric base"
        alias_candidate = _alias_candidate(
            strong_id,
            str(base_record["strong_id"]),
            0.99,
            reason,
            len(token_rows),
            sample_references,
        )
    elif same_tbesg and len(same_tbesg) == 1 and _morph_compatible(morphs, str(same_tbesg[0].get("morph") or "")):
        classification = CLASS_SAME_LEMMA
        reason = "one TBESG record has the same lemma and compatible morphology"
        alias_candidate = _alias_candidate(
            strong_id,
            str(same_tbesg[0]["strong_id"]),
            0.94,
            reason,
            len(token_rows),
            sample_references,
        )
    elif same_hu and len(same_hu) == 1:
        classification = CLASS_SAME_LEMMA
        reason = "one Hungarian lexicon record has the same lemma"
        alias_candidate = _alias_candidate(
            strong_id,
            str(same_hu[0]["strong_id"]),
            0.9,
            reason,
            len(token_rows),
            sample_references,
        )
    elif suffix and base_record is not None:
        classification = CLASS_SUFFIX
        reason = "suffix variant has a numeric base, but lemma or morphology differs"
    elif suffix and _textual_variant_flags(edition_flags):
        classification = CLASS_TEXTUAL
        reason = "suffix appears only in text-critical edition flags"
    elif lemma:
        classification = CLASS_MISSING
        reason = "no safe local base, TBESG same-lemma, or Hungarian same-lemma record found"
    else:
        classification = CLASS_MALFORMED
        reason = "missing usable lemma"

    record = {
        "strong_id": strong_id,
        "base_strong_id": base,
        "suffix": suffix,
        "lemma": lemma,
        "lemmas": lemmas,
        "greek_forms": forms,
        "morph_codes": morphs,
        "tagnt_token_frequency": len(token_rows),
        "sample_references": sample_references,
        "edition_flags": edition_flags,
        "same_lemma_tbesg_records": [
            _compact_lexicon_record(item) for item in same_tbesg[:10]
        ],
        "same_lemma_hungarian_records": [
            _compact_lexicon_record(item) for item in same_hu[:10]
        ],
        "base_record": _compact_lexicon_record(base_record) if base_record else None,
        "classification": classification,
        "classification_reason": reason,
    }
    if alias_candidate is not None:
        record["alias_candidate"] = alias_candidate
    return record


def _tagnt_rows_for_strong(connection: sqlite3.Connection, strong_id: str) -> list[sqlite3.Row]:
    connection.row_factory = sqlite3.Row
    return list(
        connection.execute(
            """
            SELECT book, chapter, verse, word_index, greek_form, lemma, morph_code, strong_id, edition_flags
            FROM greek_tokens
            WHERE strong_id = ?
            ORDER BY book, chapter, verse, word_index
            """,
            (strong_id,),
        )
    )


def _load_tbesg_indexes(path: str | Path) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    by_strong: dict[str, dict[str, Any]] = {}
    by_lemma: dict[str, list[dict[str, Any]]] = {}
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT strong_id, lemma, morph, gloss, transliteration FROM greek_lexicon"
        ).fetchall()
    for strong_id, lemma, morph, gloss, transliteration in rows:
        item = {
            "strong_id": str(strong_id),
            "lemma": str(lemma or ""),
            "morph": str(morph or ""),
            "gloss": str(gloss or ""),
            "transliteration": str(transliteration or ""),
        }
        by_strong[item["strong_id"]] = item
        by_lemma.setdefault(_lemma_key(item["lemma"]), []).append(item)
    return by_strong, by_lemma


def _load_hungarian_indexes(path: str | Path) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    by_strong: dict[str, dict[str, Any]] = {}
    by_lemma: dict[str, list[dict[str, Any]]] = {}
    if not Path(path).exists():
        return by_strong, by_lemma
    for strong_id, entry in load_hungarian_lexicon(path).items():
        item = {
            "strong_id": strong_id,
            "lemma": entry.lemma,
            "morph": "",
            "gloss": entry.primary_gloss,
            "transliteration": "",
        }
        by_strong[strong_id] = item
        by_lemma.setdefault(_lemma_key(entry.lemma), []).append(item)
    return by_strong, by_lemma


def _missing_tbesg_ids_from_coverage(path: str | Path) -> list[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [str(value) for value in data.get("missing_tbesg_strong_ids", [])]


def _coverage_summary(path: str | Path) -> dict[str, Any]:
    return dict(json.loads(Path(path).read_text(encoding="utf-8")).get("summary", {}))


def _alias_candidate(
    source: str,
    target: str,
    confidence: float,
    evidence: str,
    frequency: int,
    sample_references: list[str],
) -> dict[str, Any]:
    return {
        "source_strong_id": source,
        "target_strong_id": target,
        "confidence": confidence,
        "evidence": evidence,
        "token_frequency": frequency,
        "sample_references": sample_references,
    }


def _unresolved_export_record(record: dict[str, Any]) -> dict[str, object]:
    morphs = record["morph_codes"]
    return {
        "strong_id": record["strong_id"],
        "lemma": record["lemma"],
        "transliteration": "",
        "morph": morphs[0] if len(morphs) == 1 else "",
        "gloss_en": "",
        "meaning_plain_en": "",
        "nt_frequency": record["tagnt_token_frequency"],
        "sample_references": record["sample_references"],
        "primary_gloss_hu": "",
        "senses_hu": [],
        "note_hu": "",
        "review_status": DEFAULT_REVIEW_STATUS,
        "translation_method": DEFAULT_TRANSLATION_METHOD,
        "source_name": TAGNT_UNRESOLVED_SOURCE_NAME,
        "source_version": None,
    }


def _unresolved_export_data(records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "source": TAGNT_UNRESOLVED_SOURCE_NAME,
        "batch": {
            "source": TAGNT_UNRESOLVED_SOURCE_NAME,
            "order_by": "tagnt_token_frequency",
            "total_unresolved_records": len(records),
        },
        "records": sorted(records, key=lambda item: (-int(item["nt_frequency"]), str(item["strong_id"]))),
    }


def _simulation(
    summary: dict[str, Any],
    *,
    alias_candidate_count: int,
    alias_token_frequency: int,
) -> dict[str, int | float]:
    total_tokens = int(summary.get("tagnt_total_tokens", 0))
    covered_tokens = int(summary.get("tagnt_tokens_with_hungarian_lexicon", 0))
    unique_strong = int(summary.get("tagnt_unique_strong_ids", 0))
    covered_lexemes = int(summary.get("tagnt_strong_ids_found_in_hungarian", 0))
    simulated_tokens = covered_tokens + alias_token_frequency
    simulated_lexemes = covered_lexemes + alias_candidate_count
    return {
        "alias_token_frequency": alias_token_frequency,
        "simulated_tokens_with_hungarian_or_alias": simulated_tokens,
        "simulated_lexemes_with_hungarian_or_alias": simulated_lexemes,
        "simulated_token_coverage_percent": round((simulated_tokens / total_tokens) * 100, 2)
        if total_tokens
        else 0.0,
        "simulated_lexeme_coverage_percent": round((simulated_lexemes / unique_strong) * 100, 2)
        if unique_strong
        else 0.0,
    }


def _unique_text(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        text = "" if value is None else unicodedata.normalize("NFC", str(value).strip())
        if text and text not in result:
            result.append(text)
    return result


def _lemma_key(value: str) -> str:
    return unicodedata.normalize("NFC", value or "").casefold().strip()


def _reference(row: sqlite3.Row) -> str:
    return f"{row['book']} {row['chapter']}:{row['verse']}#{row['word_index']}"


def _compact_lexicon_record(item: dict[str, Any] | None) -> dict[str, str] | None:
    if item is None:
        return None
    return {
        "strong_id": str(item.get("strong_id", "")),
        "lemma": str(item.get("lemma", "")),
        "morph": str(item.get("morph", "")),
        "gloss": str(item.get("gloss", "")),
    }


def _morph_compatible(token_morphs: list[str], lexicon_morph: str) -> bool:
    if not token_morphs or not lexicon_morph:
        return True
    lexicon_kind = _broad_morph_kind(lexicon_morph)
    if not lexicon_kind:
        return True
    token_kinds = {_broad_morph_kind(morph) for morph in token_morphs}
    token_kinds.discard("")
    return not token_kinds or lexicon_kind in token_kinds or (lexicon_kind == "N" and "T" in token_kinds)


def _broad_morph_kind(value: str) -> str:
    text = (value or "").strip()
    match = _BROAD_MORPH_RE.match(text)
    if not match:
        return ""
    kind = match.group("kind")
    if kind.startswith("N"):
        return "N"
    if kind.startswith("V"):
        return "V"
    if kind.startswith("A"):
        return "A"
    if kind.startswith("T"):
        return "T"
    if kind.startswith("ADV"):
        return "ADV"
    return kind


def _textual_variant_flags(flags: list[str]) -> bool:
    return bool(flags) and all(flag != "NKO" for flag in flags)


def _write_json(path: str | Path, data: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

