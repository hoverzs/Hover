"""A vázlat-sémaverzió normalizálásának konzisztencia-javítása (2026-08-13).

Gyökérok: `sermon_workshop_data.normalize_sermon_outline()` egy elavult,
hardkódolt `"pulpit_outline_v7"` sztringhez hasonlította a mentett vázlat
`schema_version` mezőjét, miközben a vázlatmotor tényleges kanonikus,
aktuális értéke `sermon_outline_engine.SCHEMA_VERSION == "pulpit_outline_v8"`
(a motor saját `outline_needs_refresh()` függvénye már korábban is helyesen
ehhez hasonlított, ld. sermon_outline_engine.py:2251-2252). Emiatt egy ma,
szabályosan legenerált (v8 sémájú), jóváhagyott vázlat a normalizálás után
tévesen "needs_refresh" belső státuszt kapott.

Javítás: `sermon_workshop_data._canonical_outline_schema_version()` egy
lusta importtal (körkörös import nélkül, mert a `sermon_outline_engine`
modul-szinten importálja a `sermon_workshop_data`-t) mindig a tényleges
kanonikus `SCHEMA_VERSION`-t olvassa, biztonsági-háló fallback-kel import-
hiba esetére. Ez a modul KIZÁRÓLAG ezt a normalizálási logikát teszteli —
az Igehirdetési műhely UI-ját, a vázlatmotor promptját, a háttérkutatást
és a heurisztikus fallbacket nem érinti.
"""

from __future__ import annotations

import copy

from sermon_outline_engine import SCHEMA_VERSION
from sermon_workshop_data import (
    _canonical_outline_schema_version,
    get_default_sermon_workshop,
    normalize_sermon_outline,
)


def _sw_with_outline(*, schema_version: str | None, status: str = "approved") -> dict:
    sw = get_default_sermon_workshop()
    sw["sermon_outline"]["content"] = "Bevezetés: Isten hűsége.\n\nZárás: Bízzunk benne."
    sw["sermon_outline"]["status"] = status
    if schema_version is not None:
        sw["sermon_outline"]["schema_version"] = schema_version
    return sw["sermon_outline"]


# ---------------------------------------------------------------------------
# A kanonikus érték egyetlen, tényleges forrásból származik
# ---------------------------------------------------------------------------


def test_canonical_schema_version_matches_engine_constant():
    assert _canonical_outline_schema_version() == SCHEMA_VERSION
    assert SCHEMA_VERSION == "pulpit_outline_v8"


# ---------------------------------------------------------------------------
# 1-2. Aktuális v8 + approved megmarad, nem lesz needs_refresh
# ---------------------------------------------------------------------------


def test_current_v8_approved_outline_stays_approved():
    raw = _sw_with_outline(schema_version="pulpit_outline_v8", status="approved")
    normalized = normalize_sermon_outline(raw)
    assert normalized["status"] == "approved"
    assert normalized["status"] != "needs_refresh"


def test_current_v8_draft_outline_stays_draft_not_needs_refresh():
    raw = _sw_with_outline(schema_version="pulpit_outline_v8", status="draft")
    normalized = normalize_sermon_outline(raw)
    assert normalized["status"] == "draft"


# ---------------------------------------------------------------------------
# 3. Régi (v7) vagy más elavult séma helyesen "needs_refresh"
# ---------------------------------------------------------------------------


def test_legacy_v7_schema_flagged_needs_refresh():
    raw = _sw_with_outline(schema_version="pulpit_outline_v7", status="approved")
    normalized = normalize_sermon_outline(raw)
    assert normalized["status"] == "needs_refresh"
    # A tartalom nem vész el a jelöléskor.
    assert normalized["content"] == "Bevezetés: Isten hűsége.\n\nZárás: Bízzunk benne."


def test_very_old_v3_schema_flagged_needs_refresh():
    raw = _sw_with_outline(schema_version="pulpit_outline_v3", status="approved")
    normalized = normalize_sermon_outline(raw)
    assert normalized["status"] == "needs_refresh"


def test_unknown_future_schema_string_flagged_needs_refresh():
    """Egy ismeretlen (pl. elgépelt vagy jövőbeli) séma is konzervatívan
    frissítendőnek minősül — csak a ténylegesen aktuális érték kivétel."""
    raw = _sw_with_outline(schema_version="pulpit_outline_v99_unknown", status="approved")
    normalized = normalize_sermon_outline(raw)
    assert normalized["status"] == "needs_refresh"


# ---------------------------------------------------------------------------
# 4. Hiányzó schema_version nem okoz kivételt
# ---------------------------------------------------------------------------


def test_missing_schema_version_does_not_raise_and_flags_needs_refresh():
    raw = _sw_with_outline(schema_version=None, status="approved")
    assert "schema_version" not in raw or raw.get("schema_version") == ""
    normalized = normalize_sermon_outline(raw)  # nem szabad kivételt dobnia
    assert normalized["status"] == "needs_refresh"
    assert normalized["content"] == "Bevezetés: Isten hűsége.\n\nZárás: Bízzunk benne."


def test_empty_outline_with_no_schema_version_does_not_raise():
    """Teljesen üres, régi projektből származó vázlat (nincs tartalom sem)
    — a has_body védelem miatt nem kap needs_refresh jelölést feleslegesen,
    és semmiképp sem dob kivételt."""
    normalized = normalize_sermon_outline({})
    assert normalized["status"] in ("draft", "empty", "")


# ---------------------------------------------------------------------------
# 5. Régi mentett vázlat tartalma nem vész el
# ---------------------------------------------------------------------------


def test_old_outline_content_preserved_across_schema_reclassification():
    original_content = "1. Belépés\n2. Alaphelyzet\n...\n7. Megérkezés"
    raw = _sw_with_outline(schema_version="pulpit_outline_v6", status="approved")
    raw["content"] = original_content
    normalized = normalize_sermon_outline(raw)
    assert normalized["content"] == original_content
    assert normalized["status"] == "needs_refresh"


# ---------------------------------------------------------------------------
# 6. A normalizálás idempotens
# ---------------------------------------------------------------------------


def test_normalize_sermon_outline_is_idempotent_for_current_schema():
    raw = _sw_with_outline(schema_version="pulpit_outline_v8", status="approved")
    once = normalize_sermon_outline(raw)
    twice = normalize_sermon_outline(copy.deepcopy(once))
    assert once == twice
    assert twice["status"] == "approved"


def test_normalize_sermon_outline_is_idempotent_for_legacy_schema():
    """A needs_refresh jelölés stabil — újranormalizálás nem lengeti ide-oda
    az állapotot, és nem törli a tartalmat."""
    raw = _sw_with_outline(schema_version="pulpit_outline_v7", status="approved")
    once = normalize_sermon_outline(raw)
    twice = normalize_sermon_outline(copy.deepcopy(once))
    assert once == twice
    assert twice["status"] == "needs_refresh"
    assert twice["content"] == once["content"]


def test_normalize_sermon_outline_idempotent_for_missing_schema():
    raw = _sw_with_outline(schema_version=None, status="approved")
    once = normalize_sermon_outline(raw)
    twice = normalize_sermon_outline(copy.deepcopy(once))
    assert once == twice
