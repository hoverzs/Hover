"""Igehely-kereses regresszios tesztek."""

from __future__ import annotations

import json
from typing import Any

from passage_search_ai import (
    REQUIRED_COUNT,
    merge_exclude_list,
    normalize_passage_reference,
    normalize_passage_search_state,
    parse_passage_search_response,
    suggest_passages_for_occasion,
    validate_and_normalize_suggestions,
)
from passage_search_config import (
    MAX_COMMON_IN_BATCH,
    OCCASION_OPTIONS,
    common_references_for,
    get_passage_search_config,
)
from passage_search_ui import (
    SESSION_KEY,
    ensure_passage_search_state,
    workshop_material_present,
)


def _sug(
    reference: str,
    *,
    title: str = "Rovid predikalhato cim",
    reason: str = "Illik az alkalomhoz, mert a textus a kozosseget szolitja.",
    direction: str = "A hit Isten igeretere tekint, nem a korulmenyekre.",
    familiarity: str = "less_common",
) -> dict[str, Any]:
    return {
        "reference": reference,
        "title": title,
        "reason": reason,
        "homiletical_direction": direction,
        "familiarity": familiarity,
    }


def _payload(
    occasion: str, suggestions: list[dict[str, Any]], context: str = ""
) -> str:
    return json.dumps(
        {
            "occasion": occasion,
            "context_summary": context or occasion,
            "suggestions": suggestions,
        },
        ensure_ascii=False,
    )


_FUNERAL_EMPTY = [
    _sug("Job 19,23-27", title="Remenyseg a vesztesegben"),
    _sug("Zsolt 90,1-12", title="Az elet merteke Istennel"),
    _sug("Ezs 25,6-9", title="A gyasz levetel"),
    _sug("2Kor 4,16-18", title="Lathatatlan remenyseg"),
    _sug("1Pt 1,3-9", title="Elo remenyseg a gyaszban"),
]

_FUNERAL_SUDDEN = [
    _sug(
        "Job 19,23-27",
        reason=(
            "A gyasz valosagat nem kisebbíti, de a szenvedes kozepen "
            "megszolo remenysegét helyezi eloterbe."
        ),
        direction=(
            "A hit nem mindig erti a veszteseget, de Istenre bizhatja "
            "a vegso valaszt."
        ),
    ),
    _sug(
        "Zsolt 77,1-15",
        reason=(
            "A hirtelen fajdalom panaszat Isten ele vihetjuk anelkul, "
            "hogy magyarzatot eroltetnenk."
        ),
        direction=(
            "A gyaszolo kozosseg panaszat Isten hallja, meg ha a valasz "
            "kesik is."
        ),
    ),
    _sug(
        "Jn 11,32-44",
        reason=(
            "Jezus a sirnal sir egyutt a gyaszolokkal, mielott az elet "
            "szavat kimondana."
        ),
        direction="Krisztus jelenlete elobb egyutt sir, aztan remenysegét ad.",
    ),
    _sug(
        "Rom 8,18-27",
        reason=(
            "A sohajtozo teremtes es a Lelek kozbenjarasa a szavak "
            "nelkuli fajdalmat is Isten ele viszi."
        ),
        direction=(
            "A remenyseg nem magyarázza el a veszteseget, de kitart "
            "a feltamadasig."
        ),
    ),
    _sug(
        "Jel 21,1-5",
        reason=(
            "A vegso igeret Isten jelenletere es a konnyek letorlesere "
            "mutat, nem a halal okara."
        ),
        direction="A vigasztalas Isten jovobeli jelenleteben gyokerezik.",
    ),
]

_WEDDING = [
    _sug("1Moz 2,18-24", title="Szovetseges tarsasag"),
    _sug("Ef 5,21-33", title="Kolcsonos szolgalt"),
    _sug("Kol 3,12-17", title="Kegyelem a kozos eletben"),
    _sug("Rut 1,16-17", title="Huseg a szovetsegben"),
    _sug("1Kor 13,1-13", title="A szeretet utja", familiarity="common"),
]

_BAPTISM = [
    _sug(
        "1Moz 17,1-8",
        reason=(
            "A szovetseg igerete a gyermeket es a kozosseget egyutt szolitja."
        ),
        direction=(
            "A keresztseg Isten igeretere valaszol, nem magikus biztositek."
        ),
    ),
    _sug(
        "ApCsel 2,38-42",
        reason=(
            "A gyulekezet felelossege es a tanitvanysag egyutt jelenik meg."
        ),
        direction="A keresztseg a kozosseg gondozasaba helyez.",
    ),
    _sug(
        "Rom 6,3-11",
        reason=(
            "A kegyelem es az uj elet egysege a keresztseg teologiai magja."
        ),
        direction=(
            "Meghalni a bunnek es elni Istennek — ajandek, nem teljesitmeny."
        ),
    ),
    _sug(
        "Gal 3,26-29",
        reason="A szovetsegi orokseg Krisztusban minden hivore kiterjed.",
        direction="A keresztseg Krisztushoz tartozast hirdet.",
    ),
    _sug(
        "Mk 10,13-16",
        title="Gyermekek az Ur oleben",
        familiarity="common",
    ),
]

_SUNDAY = [
    _sug("Ezs 55,1-11", title="Isten szavanak utja"),
    _sug("Mk 4,35-41", title="Viharban is Ur"),
    _sug("Lk 15,1-10", title="Az elveszett megkeresese"),
    _sug("Fil 2,1-11", title="Alazat es felmagasztalas"),
    _sug("Jel 3,14-22", title="Kopogtatas a kapun"),
]


def test_config_editable_and_not_banlist():
    cfg = get_passage_search_config()
    assert "Temetés" in cfg["common_references_by_occasion"]
    assert cfg["max_common_in_batch"] == MAX_COMMON_IN_BATCH == 1
    assert any("Zsolt 23" in x for x in common_references_for("Temetés"))
    assert "Vasárnapi istentisztelet" in OCCASION_OPTIONS


def test_funeral_empty_five_valid_varied():
    raw = _payload("Temetés", _FUNERAL_EMPTY)
    parsed = parse_passage_search_response(raw, occasion="Temetés")
    assert parsed.ok, parsed.warnings
    assert len(parsed.suggestions) == REQUIRED_COUNT
    refs = [s.reference for s in parsed.suggestions]
    assert len(set(refs)) == REQUIRED_COUNT
    for s in parsed.suggestions:
        normalize_passage_reference(s.reference)
    common_n = sum(1 for s in parsed.suggestions if s.familiarity == "common")
    assert common_n <= 1


def test_funeral_detailed_context_full_hu_book_names_and_history():
    """Regresszió: Temetés + részletes kontextus + history exclude.

    A modell gyakran teljes magyar könyvnevet ad (Róma, 2 Timóteus, Jelenések).
    Korábban ezek elvetése + cooldown a fill híváson → generic hibaüzenet.
    """
    from passage_search_ai import MIN_ACCEPTABLE_COUNT

    context = "egy 84 éves nő varrasztójára keresek igét"
    history = [
        "Zsolt 23",
        "Jn 14,1-6",
        "Job 19,23-27",
        "1Thess 4,13-18",
        "Róm 8,38-39",
        "Jn 11,25-26",
    ]
    batch = [
        _sug("Ézs 40,28-31", title="Az Orokkévalo Isten"),
        _sug("Zsolt 71,1-9", title="Remenyseg idos korban"),
        _sug("Jn 12,23-26", title="Mag a foldben"),
        _sug("Róma 8,31-37", title="Semmi el nem valaszthat"),
        _sug("2 Timóteus 4,6-8", title="A hit harca befejezve"),
    ]
    seen_kwargs: list[dict[str, Any]] = []

    def gen(prompt, **kwargs):
        seen_kwargs.append(dict(kwargs))
        assert "84" in prompt or "varraszt" in prompt.casefold() or context[:10] in prompt
        assert "Temetés" in prompt
        return _payload("Temetés", batch, context=context)

    result = suggest_passages_for_occasion(
        occasion="Temetés",
        context=context,
        history_exclude_references=history,
        generate_fn=gen,
    )
    assert result.ok, (result.warnings, result.error_message)
    assert MIN_ACCEPTABLE_COUNT <= len(result.suggestions) <= REQUIRED_COUNT
    refs = [s.reference for s in result.suggestions]
    assert any(r.startswith("Róm") for r in refs)
    assert any("2Tim" in r for r in refs)
    # Fill/repair nem kell, ha az aliasok miatt megvan az 5.
    assert len(seen_kwargs) == 1
    assert seen_kwargs[0].get("bypass_cooldown") is True


def test_funeral_accepts_four_when_fill_blocked_by_cooldown_message():
    """Ha a fill cooldown-üzenetet kap, 4 érvényes javaslat mégis siker."""
    from passage_search_ai import MIN_ACCEPTABLE_COUNT

    context = "egy 84 éves nő varrasztójára keresek igét"
    history = ["Zsolt 23", "Jn 14,1-6", "Job 19,23-27", "1Thess 4,13-18"]
    # 4 valid + 1 invalid (ismeretlen könyv) → fill kellene
    batch = [
        _sug("Ézs 40,28-31"),
        _sug("Zsolt 71,1-9"),
        _sug("Jn 12,23-26"),
        _sug("Kol 3,1-4"),
        _sug("NemLetezoKonyv 9,1-3"),
    ]
    calls = {"n": 0}
    seen_bypass: list[bool] = []

    def gen(prompt, **kwargs):
        calls["n"] += 1
        seen_bypass.append(bool(kwargs.get("bypass_cooldown")))
        if calls["n"] == 1:
            return _payload("Temetés", batch, context=context)
        return (
            "⏳ **Kérlek várj néhány másodpercet az újabb generálás előtt.** "
            "(Még kb. 8 másodperc.)"
        )

    result = suggest_passages_for_occasion(
        occasion="Temetés",
        context=context,
        history_exclude_references=history,
        generate_fn=gen,
    )
    assert calls["n"] == 2
    assert result.ok, (result.warnings, result.error_message)
    assert len(result.suggestions) == MIN_ACCEPTABLE_COUNT
    assert all(seen_bypass)


def test_funeral_sudden_sensitive_reasons():
    raw = _payload(
        "Temetés",
        _FUNERAL_SUDDEN,
        context="fiatalon es varatlanul elhunyt",
    )
    parsed = parse_passage_search_response(raw, occasion="Temetés")
    assert parsed.ok, parsed.warnings
    blob = " ".join(
        f"{s.reason} {s.homiletical_direction}" for s in parsed.suggestions
    ).casefold()
    banned = (
        "udvozult",
        "üdvözült",
        "jobb helyen van",
        "minden okkal tortent",
        "ne sirjatok",
    )
    for b in banned:
        assert b not in blob
    assert "gyasz" in blob or "gyász" in blob or "remeny" in blob


def test_wedding_not_only_1cor13():
    raw = _payload("Esketés", _WEDDING)
    parsed = parse_passage_search_response(raw, occasion="Esketés")
    assert parsed.ok, parsed.warnings
    refs = [s.reference for s in parsed.suggestions]
    cor13 = [r for r in refs if "1Kor 13" in r]
    assert len(cor13) <= 1
    assert len(refs) == 5
    assert any("1Kor 13" not in r for r in refs)


def test_baptism_covenant_and_community_language():
    raw = _payload("Keresztelés", _BAPTISM)
    parsed = parse_passage_search_response(raw, occasion="Keresztelés")
    assert parsed.ok, parsed.warnings
    blob = " ".join(
        f"{s.reason} {s.homiletical_direction}" for s in parsed.suggestions
    ).casefold()
    assert "szovetseg" in blob or "igeret" in blob
    assert "gyulekezet" in blob or "kozosseg" in blob or "tanitvan" in blob


def test_sunday_coherent_pericopes_not_motto_verses():
    raw = _payload("Vasárnapi istentisztelet", _SUNDAY)
    parsed = parse_passage_search_response(
        raw, occasion="Vasárnapi istentisztelet"
    )
    assert parsed.ok, parsed.warnings
    for s in parsed.suggestions:
        assert "," in s.reference or "-" in s.reference or "–" in s.reference


def test_invalid_model_reference_dropped_and_repaired():
    bad_batch = [
        _sug("NemLetezoKonyv 99,1-5"),
        *_FUNERAL_EMPTY[:4],
    ]
    call_count = {"n": 0}

    def gen(prompt, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _payload("Temetés", bad_batch)
        return _payload("Temetés", _FUNERAL_EMPTY)

    result = suggest_passages_for_occasion(
        occasion="Temetés",
        context="",
        generate_fn=gen,
    )
    assert call_count["n"] == 2
    assert result.ok, result.warnings
    assert len(result.suggestions) == 5
    for s in result.suggestions:
        assert "NemLetezo" not in s.reference


def test_more_requests_excludes_previous_five():
    batch_a = list(_FUNERAL_EMPTY)
    batch_b = [
        _sug("Ezs 40,1-11"),
        _sug("Jn 14,27-31"),
        _sug("2Kor 1,3-7"),
        _sug("Zsolt 46,1-11"),
        _sug("1Thess 4,13-18"),
    ]
    calls = {"n": 0}

    def gen_a(prompt, **kwargs):
        return _payload("Temetés", batch_a)

    def gen_b(prompt, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            polluted = [_sug(batch_a[0]["reference"]), *batch_b[1:]]
            return _payload("Temetés", polluted)
        return _payload("Temetés", batch_b)

    r1 = suggest_passages_for_occasion(occasion="Temetés", generate_fn=gen_a)
    assert r1.ok, r1.warnings
    exclude = merge_exclude_list(r1.suggestions, [])
    assert len(exclude) == 5

    r2 = suggest_passages_for_occasion(
        occasion="Temetés",
        exclude_references=exclude,
        generate_fn=gen_b,
    )
    assert r2.ok, (r2.warnings, calls)
    r2_refs = {s.reference for s in r2.suggestions}
    r1_refs = {s.reference for s in r1.suggestions}
    assert r1_refs.isdisjoint(r2_refs)


def test_selection_updates_canonical_igehely_field():
    from passage_search_ui import (
        PENDING_APPLY_KEY,
        apply_pending_passage_search_before_widget,
    )
    import passage_search_ui as psu

    class _SS(dict):
        pass

    ss = _SS()
    ss["last_igehely"] = ""
    ss["igehely_input"] = ""
    ss[SESSION_KEY] = normalize_passage_search_state(
        {
            "suggestions": _FUNERAL_EMPTY,
            "status": "ready",
            "occasion": "Temetés",
        }
    )
    ss[PENDING_APPLY_KEY] = {
        "reference": "Job 19,23-27",
        "mark_stale": False,
        "load_ruf": False,
    }

    real_ss = psu.st.session_state
    psu.st.session_state = ss
    try:
        apply_pending_passage_search_before_widget()
        assert ss["igehely_input"] == ss["last_igehely"]
        assert "19" in ss["last_igehely"]
        assert ss[SESSION_KEY]["suggestions"] == []
        flash = (ss.get("_passage_search_select_flash") or {}).get("text", "")
        assert "kiv" in flash.casefold()
    finally:
        psu.st.session_state = real_ss


def test_existing_workshop_material_no_silent_overwrite():
    from passage_search_ui import PENDING_CONFIRM_KEY, request_select_suggestion
    import passage_search_ui as psu

    class FakeSS(dict):
        pass

    fake = FakeSS(
        {
            "last_igehely": "Jn 3,16-21",
            "igehely_input": "Jn 3,16-21",
            "overview": "Korabbi attekintes szovege.",
            "exegesis": "",
        }
    )
    assert workshop_material_present(fake)
    fake[SESSION_KEY] = ensure_passage_search_state(fake)
    real = psu.st.session_state
    reruns: list[int] = []

    def fake_rerun():
        reruns.append(1)

    psu.st.session_state = fake
    psu.st.rerun = fake_rerun
    try:
        request_select_suggestion("Job 19,23-27")
        assert PENDING_CONFIRM_KEY in fake
        assert fake["last_igehely"] == "Jn 3,16-21"
        assert reruns
    finally:
        psu.st.session_state = real


def test_api_error_preserves_prior_suggestions_and_context():
    prior = normalize_passage_search_state(
        {
            "occasion": "Temetés",
            "context": "idos ember temetese",
            "suggestions": _FUNERAL_EMPTY,
            "status": "ready",
            "generated_at": "2026-01-01T00:00:00Z",
        }
    )

    def boom(*a, **k):
        return "⚠️ API hiba: timeout"

    result = suggest_passages_for_occasion(
        occasion=prior["occasion"],
        context=prior["context"],
        generate_fn=boom,
    )
    assert not result.ok
    assert "igehelyeket keresni" in result.error_message.casefold()

    state = dict(prior)
    if not (result.ok and result.suggestions):
        state["status"] = "error"
        state["last_error"] = result.error_message
    assert state["suggestions"]
    assert state["context"] == "idos ember temetese"


def test_streamlit_rerun_suggestions_persist_in_session_state():
    ss: dict[str, Any] = {}
    ss[SESSION_KEY] = normalize_passage_search_state(
        {
            "occasion": "Temetés",
            "context": "teszt",
            "suggestions": _FUNERAL_EMPTY,
            "excluded_references": ["Zsolt 23"],
            "generated_at": "2026-07-22T10:00:00Z",
            "status": "ready",
        }
    )
    again = ensure_passage_search_state(ss)
    assert len(again["suggestions"]) == 5
    assert again["context"] == "teszt"
    assert again["excluded_references"] == ["Zsolt 23"]


def test_no_duplicate_widget_keys_in_ui_module():
    import inspect
    import re

    import passage_search_ui as psu

    src = inspect.getsource(psu)
    keys = re.findall(r'key\s*=\s*["\']([^"\']+)["\']', src)
    static = [k for k in keys if not k.startswith("passage_search_pick_")]
    assert len(static) == len(set(static)), static


def test_common_cap_drops_extra_classics():
    raw_list = [
        _sug("Zsolt 23", familiarity="common"),
        _sug("Jn 11,25-26", familiarity="common"),
        _sug("Job 19,23-27"),
        _sug("Ezs 25,6-9"),
        _sug("2Kor 4,16-18"),
        _sug("1Pt 1,3-9"),
    ]
    out, warnings = validate_and_normalize_suggestions(
        raw_list, occasion="Temetés"
    )
    common_n = sum(1 for s in out if s.familiarity == "common")
    assert common_n <= 1
    assert any("elvetve" in w.casefold() for w in warnings)


def test_api_error_message_exact():
    r = suggest_passages_for_occasion(
        occasion="Temetés",
        generate_fn=lambda *a, **k: "⚠️ hiba",
    )
    assert "igehelyeket keresni" in r.error_message.casefold()
    assert "megmaradtak" in r.error_message.casefold()
