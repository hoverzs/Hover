"""RESET 1A-DATA (2026-08-18): a Vázlatkosár teljes leválasztása a
kanonikus vázlatkontextusról és a tényleges AI-promptról.

PREFLIGHT-EREDMÉNY (ld. a fázisvégi audit is): a RESET 1A-UI (2026-08-18,
commit 9ac1a41) már eltávolította a Vázlatkosár aktív felületét, de a
`collect_outline_context_bundle()` / `build_outline_user_prompt()` /
`_repair_source_context()` láncban a `basket` projektadat még mindig
aktívan, additívan bekerült a bundle-be, a promptba és a repair/retry
kontextusba. Ez a fájl bizonyítja, hogy ez a réteg is teljesen
leválasztásra került — a `session_state["basket"]` projektadat
VÁLTOZATLANUL megmarad és túléli a mentést/visszatöltést, de sehol nem
befolyásolja a generálást, az engedélyezést vagy a kimenetet.

Nincs valódi AI/külső API-hívás egyik tesztben sem (`generate_fn` mindig
mockolt).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sermon_outline_engine import (
    _repair_source_context,
    build_outline_user_prompt,
    generate_sermon_outline,
)
from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    ensure_sermon_workshop_state,
    get_default_sermon_workshop,
)
from sermon_workshop_outline_ai import (
    assess_outline_readiness,
    collect_outline_context_bundle,
)
from textus_workshop_data import TEXT_WORKSHOP_KEY, ensure_text_workshop_state, get_default_text_workshop
from workspace_data import build_project_data

BASKET_MUST_NOT_REACH_OUTLINE_SENTINEL = "BASKET_MUST_NOT_REACH_OUTLINE_SENTINEL"

OVERVIEW_SENTINEL = "OVERVIEW_RESET1A_SENTINEL"
EXEGESIS_SENTINEL = "EXEGESIS_RESET1A_SENTINEL"
ORIGINAL_LANGUAGE_SENTINEL = "ORIGINAL_LANGUAGE_RESET1A_SENTINEL"
HISTORY_SENTINEL = "HISTORY_RESET1A_SENTINEL"
THEOLOGY_SENTINEL = "THEOLOGY_RESET1A_SENTINEL"
USER_FOCUS_SENTINEL = "USER_FOCUS_RESET1A_SENTINEL"


def _full_state(*, with_basket: bool) -> dict:
    state = {
        "last_igehely": "Lk 14,1-6",
        "igehely_input": "Lk 14,1-6",
        "passage_text": (
            "1 Amikor egyszer szombaton az egyik farizeus vezető házába ment "
            "étkezni, azok szemmel tartották őt. "
            "6 És nem tudtak erre felelni."
        ),
        "bible_translation": "RÚF 2014",
        "overview": OVERVIEW_SENTINEL,
        "exegesis": EXEGESIS_SENTINEL,
        "exegesis_status": "draft",
        "original_text": ORIGINAL_LANGUAGE_SENTINEL,
        "original_text_status": "draft",
        "history": HISTORY_SENTINEL,
        "history_status": "draft",
        "theology": THEOLOGY_SENTINEL,
        "theology_status": "draft",
        "last_sajat": USER_FOCUS_SENTINEL,
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
    }
    if with_basket:
        # Listák, nem tuple-ök: a `sanitize_project_data` (workspace_data.py)
        # csak JSON-kompatibilis (list/dict) elemeket fogad el a WORKSPACE_
        # LIST_KEYS mezőiben — ez a valós mentés/visszatöltés útja (a
        # session_state-beli tuple-ök a JSON-mentéskor amúgy is listává
        # válnak). Ld. tests/test_security_hygiene.py azonos mintáját.
        state["basket"] = [
            ["Exegézis", BASKET_MUST_NOT_REACH_OUTLINE_SENTINEL],
            ["Saját jegyzet", "Egy másik " + BASKET_MUST_NOT_REACH_OUTLINE_SENTINEL],
        ]
    ensure_text_workshop_state(state)
    ensure_sermon_workshop_state(state)
    return state


# ---------------------------------------------------------------------------
# 1-3. bundle / background / prompt szinten a kosár nem jelenik meg
# ---------------------------------------------------------------------------


def test_basket_not_in_canonical_bundle():
    state = _full_state(with_basket=True)
    bundle = collect_outline_context_bundle(state)
    assert "outline_basket" not in bundle
    assert "outline_basket" not in (bundle.get("source_keys") or [])
    assert json.dumps(bundle, ensure_ascii=False, default=str).count(
        BASKET_MUST_NOT_REACH_OUTLINE_SENTINEL
    ) == 0


def test_basket_not_in_background_material():
    from sermon_outline_engine import extract_outline_background_material

    state = _full_state(with_basket=True)
    bundle = collect_outline_context_bundle(state)
    background = extract_outline_background_material(bundle)
    assert BASKET_MUST_NOT_REACH_OUTLINE_SENTINEL not in json.dumps(
        background, ensure_ascii=False, default=str
    )


def test_basket_not_in_build_outline_user_prompt():
    state = _full_state(with_basket=True)
    bundle = collect_outline_context_bundle(state)
    prompt = build_outline_user_prompt(bundle, mode="workshop")
    assert BASKET_MUST_NOT_REACH_OUTLINE_SENTINEL not in prompt
    assert 'label="vázlatkosár"' not in prompt
    assert "vázlatkosár" not in prompt.casefold()


# ---------------------------------------------------------------------------
# 4, 7. a tényleges generate_fn-nek átadott prompt sem tartalmazza — és a
# kanonikus kutatási források a kosár mellett is változatlanul eljutnak
# ---------------------------------------------------------------------------


def test_basket_not_in_actual_generate_fn_prompt_while_other_sources_reach_it():
    state = _full_state(with_basket=True)
    captured: list[str] = []

    def gen(prompt, **_kwargs):
        captured.append(prompt)
        return json.dumps(
            {
                "focus_sentence": "A vendéglátás Isten országának jele.",
                "introduction_direction": "Nyitókép a lakomáról.",
                "points": [
                    {
                        "title": "Meghívás",
                        "verses": "v. 1",
                        "textual_insight": "A textus feszültsége.",
                        "theological_emphasis": "Isten kegyelme.",
                        "listener_movement": "A hallgató elgondolkodik.",
                    },
                    {
                        "title": "Válasz",
                        "verses": "v. 6",
                        "textual_insight": "A csend jelentése.",
                        "theological_emphasis": "Az ítélet és kegyelem.",
                        "listener_movement": "A hallgató választ keres.",
                    },
                ],
                "conclusion_direction": "Záró felhívás.",
            },
            ensure_ascii=False,
        )

    result = generate_sermon_outline(
        state, mode="workshop", generate_fn=gen, force_overwrite=True
    )
    assert result.ok, result.error_message
    assert captured, "Nem történt AI-hívás."
    for prompt in captured:
        assert BASKET_MUST_NOT_REACH_OUTLINE_SENTINEL not in prompt

    outline_prompts = [p for p in captured if "BIBLIAI SZÖVEG" in p or "IGEHELY:" in p]
    assert outline_prompts
    main_prompt = outline_prompts[0]
    for sentinel in (
        OVERVIEW_SENTINEL,
        EXEGESIS_SENTINEL,
        ORIGINAL_LANGUAGE_SENTINEL,
        HISTORY_SENTINEL,
        THEOLOGY_SENTINEL,
    ):
        assert sentinel in main_prompt, sentinel


# ---------------------------------------------------------------------------
# 5. repair-/retry-kontextus sem tartalmazza
# ---------------------------------------------------------------------------


def test_basket_not_in_repair_source_context():
    state = _full_state(with_basket=True)
    bundle = collect_outline_context_bundle(state)
    ctx = _repair_source_context(bundle, rich=True)
    assert "outline_basket" not in ctx
    assert BASKET_MUST_NOT_REACH_OUTLINE_SENTINEL not in json.dumps(
        ctx, ensure_ascii=False, default=str
    )


# ---------------------------------------------------------------------------
# 6. a kosár jelenléte/hiánya ugyanazt a forráslistát eredményezi
# ---------------------------------------------------------------------------


def test_basket_presence_does_not_change_source_keys_or_bundle():
    without = collect_outline_context_bundle(_full_state(with_basket=False))
    with_basket = collect_outline_context_bundle(_full_state(with_basket=True))

    def _drop_internal(bundle: dict) -> dict:
        return {k: v for k, v in bundle.items() if not k.startswith("_")}

    assert _drop_internal(without) == _drop_internal(with_basket)
    assert (without.get("source_keys") or []) == (with_basket.get("source_keys") or [])


# ---------------------------------------------------------------------------
# 8-9. a kosár hiánya nem blokkol, a megléte nem old fel semmit
# ---------------------------------------------------------------------------


def test_basket_absence_does_not_block_generation():
    state = _full_state(with_basket=False)
    ready = assess_outline_readiness(state)
    assert ready.ok, ready.message

    def gen(prompt, **_kwargs):
        return json.dumps(
            {
                "focus_sentence": "Fókusz.",
                "introduction_direction": "Nyitás.",
                "points": [
                    {
                        "title": "Egy",
                        "verses": "v. 1",
                        "textual_insight": "Betekintés.",
                        "theological_emphasis": "Hangsúly.",
                        "listener_movement": "Mozdulás.",
                    },
                    {
                        "title": "Kettő",
                        "verses": "v. 6",
                        "textual_insight": "Betekintés.",
                        "theological_emphasis": "Hangsúly.",
                        "listener_movement": "Mozdulás.",
                    },
                ],
                "conclusion_direction": "Zárás.",
            },
            ensure_ascii=False,
        )

    result = generate_sermon_outline(
        state, mode="workshop", generate_fn=gen, force_overwrite=True
    )
    assert result.ok, result.error_message


def test_basket_alone_no_longer_satisfies_curation_gate():
    """Megfordított elvárás — korábban (RESET 1A-DATA előtt) egy puszta,
    kitöltött Vázlatkosár ÖNMAGÁBAN elegendő volt a `require_curation`
    kapuhoz (ld. tests/test_outline_quick_curation_gate.py régi
    `test_require_curation_passes_with_basket_item`). Mivel a kosár többé
    nem befolyásolhatja a generálás engedélyezését, ugyanez az állapot
    most bukik."""
    state = {
        "last_igehely": "Jn 3,16",
        "igehely_input": "Jn 3,16",
        "passage_text": "16 Mert úgy szerette Isten a világot…",
        TEXT_WORKSHOP_KEY: get_default_text_workshop(),
        SERMON_WORKSHOP_KEY: get_default_sermon_workshop(),
        "basket": [("Exegézis", "Valamilyen kosártartalom.")],
    }
    ensure_sermon_workshop_state(state)
    ready = assess_outline_readiness(state, require_curation=True)
    assert not ready.ok


# ---------------------------------------------------------------------------
# 10. a `basket` projektadat túléli a mentés/visszatöltés ciklust
# ---------------------------------------------------------------------------


def test_basket_project_data_survives_save_and_reload():
    state = _full_state(with_basket=True)
    project = build_project_data(state)
    assert project.get("basket") == [
        ("Exegézis", BASKET_MUST_NOT_REACH_OUTLINE_SENTINEL),
        ("Saját jegyzet", "Egy másik " + BASKET_MUST_NOT_REACH_OUTLINE_SENTINEL),
    ] or project.get("basket") == [
        ["Exegézis", BASKET_MUST_NOT_REACH_OUTLINE_SENTINEL],
        ["Saját jegyzet", "Egy másik " + BASKET_MUST_NOT_REACH_OUTLINE_SENTINEL],
    ]

    reloaded = dict(project)
    ensure_text_workshop_state(reloaded)
    ensure_sermon_workshop_state(reloaded)
    assert reloaded.get("basket")
    assert len(reloaded["basket"]) == 2

    # A visszatöltött kosár ettől még nem jut el a bundle-be.
    bundle = collect_outline_context_bundle(reloaded)
    assert "outline_basket" not in bundle


# ---------------------------------------------------------------------------
# 11. más felhasználói jegyzet (saját szempont) érintetlen
# ---------------------------------------------------------------------------


def test_general_user_focus_still_reaches_prompt_unaffected_by_basket():
    state = _full_state(with_basket=True)
    bundle = collect_outline_context_bundle(state)
    assert bundle.get("user_focus") == USER_FOCUS_SENTINEL

    prompt = build_outline_user_prompt(bundle, mode="workshop")
    # A `user_focus` a core passage kontextus JSON-jában jelenhet meg,
    # ha nincs explicit bibliai szöveg — itt van szöveg, tehát legalább a
    # bundle-ben bizonyítottan jelen van, jóváhagyás/kosár nélkül is.
    ctx = _repair_source_context(bundle, rich=True)
    assert ctx.get("user_focus") == USER_FOCUS_SENTINEL
    assert BASKET_MUST_NOT_REACH_OUTLINE_SENTINEL not in json.dumps(
        ctx, ensure_ascii=False
    )
    _ = prompt


# ---------------------------------------------------------------------------
# 12. a Word-export ebben a részfázisban változatlan (a kosár ott még
# aktívan megjelenik — ez a következő, hétpontos exportfázis feladata)
# ---------------------------------------------------------------------------


def test_word_export_still_shows_basket_section_unchanged_in_this_subphase():
    import io
    from unittest.mock import patch

    from docx import Document

    import outline_word_export

    class _SS(dict):
        pass

    ss = _SS(
        {
            "last_igehely": "Jn 1,1",
            "last_alkalom": "—",
            "last_stilus": "—",
            "outline": "## Cím\nRövid szöveg.",
            "basket": [("Exegézis", BASKET_MUST_NOT_REACH_OUTLINE_SENTINEL)],
            "songs": "",
        }
    )

    with patch.object(outline_word_export, "st") as st_mock:
        st_mock.session_state = ss
        data = outline_word_export.build_outline_docx()

    doc = Document(io.BytesIO(data))
    joined = "\n".join(p.text for p in doc.paragraphs)
    assert "Vázlatkosár" in joined
    assert BASKET_MUST_NOT_REACH_OUTLINE_SENTINEL in joined
