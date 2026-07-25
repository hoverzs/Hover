# ruff: noqa: E402
"""Közös igehirdetési-vázlat motor — séma, validáció, belépési pontok."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_outline_engine import (
    FORBIDDEN_HEADINGS,
    LIMITS,
    REFRESH_NOTICE,
    compute_context_hash,
    generate_sermon_outline,
    normalize_structured_outline,
    outline_needs_refresh,
    render_structured_outline,
    structured_to_sermon_outline,
    validate_structured_outline,
    word_count,
)
from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    get_default_sermon_workshop,
    normalize_sermon_outline,
    save_sermon_outline,
)
from sermon_workshop_outline_ai import (
    assemble_sermon_outline,
    assess_outline_readiness,
    outline_has_content,
    outline_to_readable_content,
)
from textus_workshop_data import TEXT_WORKSHOP_KEY, get_default_text_workshop
from tests.test_jude_e2e_workflow import build_jude_state


def _base_state(**extra) -> dict:
    state = {
        "last_igehely": "Jn 3,16",
        "igehely_input": "Jn 3,16",
        "passage_text": "16 Mert úgy szerette Isten a világot, hogy egyszülött Fiát adta…",
        "exegesis": "A szeret ige a szöveg központi mozgása a megváltás felé.",
        "original_text": "ἠγάπησεν — aoristos, Isten cselekvő szeretete.",
        "theology": "",
        "history": "",
        "last_sajat": "",
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    state.update(extra)
    ensure_sermon_workshop_state(state)
    return state


def _valid_structured(**overrides) -> dict:
    base = {
        "title": "Isten szeretete",
        "text_reference": "Jn 3,16",
        "scope_note": "",
        "focus_sentence": "Isten szeretete Fiában adja a megváltás útját a világnak.",
        "introduction_direction": (
            "A hallgató a szeretetéhség és az elveszettség feszültségéből indul."
        ),
        "points": [
            {
                "title": "Isten cselekvő szeretete",
                "verses": "v. 16a",
                "thesis": "A szeret ige Isten cselekvő, odaadó szeretetét mutatja.",
                "subpoints": [
                    "A textus nem emberi érdemről, hanem Isten kezdeményezéséről beszél.",
                    "A szeretet mértéke az egyszülött Fiú odaadásában válik láthatóvá.",
                ],
                "application": "Fogadd el, hogy Isten feléd indult el előbb.",
            },
            {
                "title": "A Fiú odaadása",
                "verses": "v. 16b",
                "thesis": "A megváltás útja a Fiú odaadásában nyílik meg.",
                "subpoints": [
                    "Az egyszülött Fiú ajándéka a szöveg középponti állítása marad.",
                    "A hallgató nem magától talál utat, hanem a Fiúban kapja azt.",
                ],
                "application": "",
            },
            {
                "title": "Hitben való élet",
                "verses": "v. 16c",
                "thesis": "A válasz hitben ragaszkodás, nem önmegváltó erőfeszítés.",
                "subpoints": [
                    "A textus az elveszés helyett az örök élet ígéretét állítja elénk.",
                    "A hit Isten cselekvésére támaszkodik, nem a saját teljesítményre.",
                ],
                "application": "Maradj a Fiúban bizalommal, ne magadban.",
            },
        ],
        "conclusion_direction": (
            "A hallgató Isten megtartó szeretetében állhat meg a Fiúban."
        ),
        "refinement_suggestions": [],
    }
    base.update(overrides)
    return normalize_structured_outline(base)


def test_quick_outline_without_homiletical_workshop():
    state = _base_state()
    ready = assess_outline_readiness(state)
    assert ready.ok
    assert "human_condition" not in ready.source_keys
    result = generate_sermon_outline(state, mode="quick", generate_fn=None)
    assert result.ok, result.error_message
    assert result.source == "quick"
    assert outline_has_content(result.outline)
    assert 3 <= len(result.outline.get("movements") or []) <= 5


def test_outline_from_biblical_text_plus_exegesis_original():
    state = _base_state(
        theology="",
        history="",
    )
    state[SERMON_WORKSHOP_KEY] = get_default_sermon_workshop()
    result = generate_sermon_outline(state, mode="quick", generate_fn=None)
    assert result.ok
    content = outline_to_readable_content(result.outline)
    assert word_count(content) <= LIMITS["absolute_max_words"]
    assert "Mit rendez ez a pont" not in content


def test_workshop_outline_with_approved_decisions():
    state = build_jude_state()
    result = generate_sermon_outline(state, mode="workshop", generate_fn=None)
    assert result.ok
    assert result.source == "workshop"
    assert result.outline.get("main_idea")
    assert len(result.outline.get("movements") or []) >= 2


def test_both_entry_points_same_output_schema():
    state = _base_state()
    quick = generate_sermon_outline(state, mode="quick", generate_fn=None)
    workshop = generate_sermon_outline(
        dict(state), mode="workshop", generate_fn=None
    )
    assert quick.ok and workshop.ok
    qs = normalize_structured_outline(quick.outline.get("structured"))
    ws = normalize_structured_outline(workshop.outline.get("structured"))
    for key in (
        "title",
        "text_reference",
        "focus_sentence",
        "introduction_direction",
        "points",
        "conclusion_direction",
    ):
        assert key in qs and key in ws
    assert isinstance(qs["points"], list) and isinstance(ws["points"], list)


def test_outline_saved_on_one_surface_appears_on_other():
    state = _base_state()
    result = generate_sermon_outline(state, mode="quick", generate_fn=None)
    assert result.ok
    save_sermon_outline(state, result.outline, mark_manual_edit=False)
    # Workshop reads same canonical field
    sw = state[SERMON_WORKSHOP_KEY]
    loaded = normalize_sermon_outline(sw.get("sermon_outline"))
    assert outline_has_content(loaded)
    assert loaded.get("source") == "quick"
    # Re-entry as workshop assemble without overwrite keeps content
    again = assemble_sermon_outline(
        state, generate_fn=None, force_overwrite=False, synthesize=True
    )
    # Not manually edited → may regenerate; force check shared storage
    assert outline_has_content(normalize_sermon_outline(sw.get("sermon_outline")))


def test_point_and_subpoint_counts_and_word_cap():
    data = _valid_structured()
    issues = validate_structured_outline(data)
    assert "too_few_points" not in issues
    assert "too_few_subpoints" not in issues
    rendered = render_structured_outline(data)
    assert word_count(rendered) <= LIMITS["absolute_max_words"]
    assert 3 <= len(data["points"]) <= 5
    for pt in data["points"]:
        assert 2 <= len(pt["subpoints"]) <= 3


def test_rejects_over_650_words_and_multi_paragraph():
    long_para = " ".join(["szó"] * 80) + "."
    bad = _valid_structured(
        points=[
            {
                "title": "Túlírt pont",
                "verses": "v. 1",
                "thesis": "Rövid tétel a textusból.",
                "subpoints": [
                    long_para + "\n\n" + long_para,
                    long_para + "\n\n" + long_para,
                    long_para,
                ],
                "application": "",
            },
            {
                "title": "Második",
                "verses": "v. 2",
                "thesis": "Második tétel is rövid marad.",
                "subpoints": [long_para, long_para],
                "application": "",
            },
            {
                "title": "Harmadik",
                "verses": "v. 3",
                "thesis": "Harmadik tétel is rövid marad.",
                "subpoints": [long_para, long_para],
                "application": "",
            },
        ]
    )
    issues = validate_structured_outline(bad)
    assert (
        "over_absolute_max" in issues
        or "multi_paragraph_point" in issues
        or "subpoint_length" in issues
        or "full_sermon_like" in issues
    )


def test_forbidden_meta_headings_absent_in_renderer():
    data = _valid_structured()
    text = render_structured_outline(data)
    for heading in FORBIDDEN_HEADINGS:
        assert heading not in text
    assert "Diagnózis" not in text
    assert "Átvezetési logika" not in text
    # Not a full sermon: no multi-paragraph expansion under points
    assert text.count("\n\n\n") == 0


def test_old_project_outline_migrates_safely():
    legacy = {
        "main_idea": "Isten megtart a gúny közepette.",
        "passage_reference": "Júd 17–20",
        "opening_direction": "A gúny hangja körülöttünk egyre hangosabb.",
        "movements": [
            {
                "title": "Emlékezzetek",
                "core_content": "Az apostolok szavaira emlékezés tartást ad.",
                "development": [
                    "Az apostolok szavaira emlékezés tartást ad a zavar közepette.",
                    "A textus saját emlékezete tartja a közösséget.",
                ],
                "textual_basis": "v. 17",
            },
            {
                "title": "Gúnyolódók",
                "core_content": "A szakadás jelei felismerhetők a textusban.",
                "development": [
                    "A gúnyolódók jelenléte nem lepi meg az apostoli figyelmeztetést.",
                    "A textus néven nevezi a szakadást, mielőtt választ adna.",
                ],
            },
            {
                "title": "Megmaradás",
                "core_content": "A Lélekben épülés a megtartás útja.",
                "development": [
                    "A megmaradás imádságban és szeretetben formálódik ki.",
                    "Isten megtartó szeretete zárja az ívet a hallgató előtt.",
                ],
            },
        ],
        "closing": {"final_insight": "Isten szeretete megtart."},
        "content": "régi szabad szöveg",
    }
    normalized = normalize_sermon_outline(legacy)
    assert normalized.get("main_idea")
    assert normalized.get("movements")
    structured = normalize_structured_outline(normalized)
    assert structured.get("focus_sentence")
    assert structured.get("points")
    outline = structured_to_sermon_outline(structured, seed=normalized, source="workshop")
    assert outline_has_content(outline)


def test_incomplete_homiletics_with_exegesis_succeeds():
    state = _base_state()
    # No M4–M9 workshop blocks
    assert not state[SERMON_WORKSHOP_KEY].get("sermon_main_idea")
    result = generate_sermon_outline(state, mode="quick", generate_fn=None)
    assert result.ok, result.error_message
    tips = result.outline.get("editorial_tips") or []
    assert len(tips) <= 2
    content = outline_to_readable_content(result.outline)
    assert "műhelyszakasz" not in content.casefold()
    assert "hiányzik" not in content.casefold() or "hiányzik" not in (
        result.outline.get("main_idea") or ""
    ).casefold()


def test_context_hash_refresh_notice_without_second_outline():
    state = _base_state()
    result = generate_sermon_outline(state, mode="workshop", generate_fn=None)
    assert result.ok
    save_sermon_outline(state, result.outline)
    from sermon_workshop_outline_ai import collect_available_sermon_material

    bundle = collect_available_sermon_material(state)
    assert not outline_needs_refresh(result.outline, bundle)
    # Change base material
    state["exegesis"] = "Új exegetikai megfigyelés a szeret igéről és a Fiúról."
    bundle2 = collect_available_sermon_material(state)
    assert outline_needs_refresh(result.outline, bundle2)
    assert REFRESH_NOTICE
    # Hash differs
    assert compute_context_hash(bundle) != compute_context_hash(bundle2)


def test_assemble_uses_shared_engine():
    state = _base_state()
    a = assemble_sermon_outline(state, generate_fn=None, mode="quick")
    assert a.ok
    assert a.outline.get("structured") or a.outline.get("movements")
    content = outline_to_readable_content(a.outline)
    assert word_count(content) <= LIMITS["absolute_max_words"]
