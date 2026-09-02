"""Illustration source registry: jogi-státusz modell és validáció.

A `data/illustrations/sources.json` az egyetlen ember által szerkesztett,
verziókezelt "igazságforrás" az illusztrációs adatbázis forrásainak jogi
metaadataihoz (nem tartalmaz bulk szöveget, csak provenance/licenc
adatokat). Ez a modul kizárólag betölt és validál — SQLite-ba írást az
`illustration_sqlite.insert_source` végzi, saját, szándékosan duplikált
jogállás-ellenőrzéssel (védelmi rétegek egymástól függetlenül).

FAIL-CLOSED SZABÁLY: egy story csak akkor kaphat 'published' állapotot,
ha a forrásának `license_status`-a a `PUBLISHABLE_LICENSE_STATUSES`
halmazban van. A 'public_domain_assumed_by_age' SZÁNDÉKOSAN NINCS ebben
a halmazban — ez csak vizsgálati/köztes állapot, amíg a ténylegesen
felhasznált digitális forrás jogállása emberi ellenőrzéssel meg nem
erősül ('public_domain_confirmed'-re vagy 'permission_granted'-re).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from illustration_engine.paths import SOURCE_REGISTRY_PATH


LICENSE_STATUSES = frozenset(
    {
        "public_domain_confirmed",
        "public_domain_assumed_by_age",
        "permission_granted",
        "unknown",
        "restricted",
    }
)

PUBLISHABLE_LICENSE_STATUSES = frozenset(
    {
        "public_domain_confirmed",
        "permission_granted",
    }
)

RELIABILITY_TIERS = frozenset({"high", "medium", "low"})

_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_]*$")


class SourceRegistryError(ValueError):
    """Egy vagy több forrásbejegyzés nem érvényes a registry-ben."""


@dataclass(frozen=True)
class SourceRecord:
    code: str
    title: str
    author: str | None
    orig_language: str
    publication_year: int | None
    edition_reference: str | None
    license_status: str
    license_basis_hu: str
    rights_holder: str | None
    source_url: str | None
    retrieved_at: str | None
    reliability_tier: str
    notes_hu: str | None
    # Phase 3A: the cultural/religious/literary tradition the WHOLE source
    # belongs to (e.g. "talmudi/midrási (aggadikus) elbeszélés", "magyar
    # népmese") — a Phase 2O retrieval-facet gap. Free text, not a fixed
    # enum (deliberately, to match `reliability_tier`'s own convention and
    # avoid premature bikeshedding over exact category names); optional
    # since it does not affect legal/technical validity of a source.
    tradition: str | None = None


def is_publishable_license(license_status: str) -> bool:
    return license_status in PUBLISHABLE_LICENSE_STATUSES


def validate_source_record(record: SourceRecord) -> list[str]:
    errors: list[str] = []
    if not _CODE_PATTERN.match(record.code or ""):
        errors.append(
            f"code invalid: {record.code!r} (expected upper-snake, e.g. 'PESTI_ESOPUS_1536')"
        )
    if not (record.title or "").strip():
        errors.append("title is required")
    if not (record.orig_language or "").strip():
        errors.append("orig_language is required")
    if record.license_status not in LICENSE_STATUSES:
        errors.append(f"license_status invalid: {record.license_status!r}")
    if not (record.license_basis_hu or "").strip():
        errors.append("license_basis_hu is required (legal justification must be explicit)")
    if record.reliability_tier not in RELIABILITY_TIERS:
        errors.append(f"reliability_tier invalid: {record.reliability_tier!r}")
    if record.publication_year is not None and not isinstance(record.publication_year, int):
        errors.append("publication_year must be an integer or null")
    return errors


def load_source_registry(path: str | Path | None = None) -> list[SourceRecord]:
    """Betölti és validálja a forrás-regisztryt. Fail-closed: bármilyen
    hibás bejegyzés esetén a TELJES betöltés meghiúsul (nem enged át
    részlegesen érvényes állapotot), az összes talált hiba felsorolásával.
    """
    registry_path = Path(path) if path is not None else SOURCE_REGISTRY_PATH
    if not registry_path.is_file():
        raise SourceRegistryError(f"Source registry file not found: {registry_path}")
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceRegistryError(f"Invalid JSON in source registry: {exc}") from exc

    entries = raw.get("sources") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        raise SourceRegistryError("Source registry must be a JSON object with a 'sources' array")

    records: list[SourceRecord] = []
    all_errors: list[str] = []
    seen_codes: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            all_errors.append(f"sources[{index}] is not a JSON object")
            continue
        try:
            record = SourceRecord(
                code=str(entry.get("code") or ""),
                title=str(entry.get("title") or ""),
                author=_opt_str(entry.get("author")),
                orig_language=str(entry.get("orig_language") or ""),
                publication_year=entry.get("publication_year"),
                edition_reference=_opt_str(entry.get("edition_reference")),
                license_status=str(entry.get("license_status") or ""),
                license_basis_hu=str(entry.get("license_basis_hu") or ""),
                rights_holder=_opt_str(entry.get("rights_holder")),
                source_url=_opt_str(entry.get("source_url")),
                retrieved_at=_opt_str(entry.get("retrieved_at")),
                reliability_tier=str(entry.get("reliability_tier") or ""),
                notes_hu=_opt_str(entry.get("notes_hu")),
                tradition=_opt_str(entry.get("tradition")),
            )
        except Exception as exc:  # noqa: BLE001 - malformed entry must fail closed with context
            all_errors.append(f"sources[{index}] malformed: {exc}")
            continue
        errors = validate_source_record(record)
        if errors:
            all_errors.extend(f"sources[{index}] ({record.code or '?'}): {e}" for e in errors)
            continue
        if record.code in seen_codes:
            all_errors.append(f"sources[{index}]: duplicate code {record.code!r}")
            continue
        seen_codes.add(record.code)
        records.append(record)

    if all_errors:
        raise SourceRegistryError(
            "Source registry validation failed:\n" + "\n".join(f"- {e}" for e in all_errors)
        )
    return records


def _opt_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "LICENSE_STATUSES",
    "PUBLISHABLE_LICENSE_STATUSES",
    "RELIABILITY_TIERS",
    "SourceRecord",
    "SourceRegistryError",
    "is_publishable_license",
    "load_source_registry",
    "validate_source_record",
]
