"""Íróasztal munkakivonat-generálás — cache, grounding, izoláció."""

from __future__ import annotations

from pathlib import Path

from writing_desk_data import (
    WRITING_DESK_EXTRACT_KEYS,
    WRITING_DESK_KEY,
    fingerprint_source_text,
    set_writing_desk_extract,
)
from writing_desk_extracts import (
    EXTRACT_INCOMPLETE_MESSAGE,
    EXTRACT_LABELS,
    EXTRACT_MISSING_MESSAGES,
    EXTRACT_ROLE_INSTRUCTIONS,
    EXTRACT_SYSTEM_BUNDLE,
    MAX_OUTPUT_TOKENS,
    STATUS_MISSING_SOURCE,
    STATUS_READY,
    STATUS_STALE,
    STATUS_VALID,
    TAB_LABEL_EXTRACT,
    _EXTRACT_INCOMPLETE_SENTINEL,
    build_extract_prompt,
    current_extract_fingerprint,
    generate_writing_desk_extract,
    inspect_writing_desk_extract,
    source_text_for_extract,
)


ROOT = Path(__file__).resolve().parents[1]

SOURCE_ORIGINAL = (
    "A görög οὕτως itt a szeretet módját emeli ki. "
    "A világ Isten szeretetének tárgya, nem magától értődő közeg. "
    "Az egyszülött Fiú ajándéka a hit lehetőségét nyitja meg."
)
SOURCE_HISTORY = (
    "A jánosi közösség a zsinagógától való elszakadás után ír. "
    "A császárkultusz a hűség kérdését élezte. "
    "A szeretetnyelv a kirekesztett csoport identitását erősítette."
)
SOURCE_THEOLOGY = (
    "Isten szeretete kezdeményező, nem válasz a mi érdemünkre. "
    "A hit befogadó gesztus, nem teljesítmény. "
    "Az örök élet jelenvaló ajándék, nem csupán távoli ígéret."
)


def _session_with_sources(**overrides) -> dict:
    state = {
        "original_text": SOURCE_ORIGINAL,
        "history": SOURCE_HISTORY,
        "theology": SOURCE_THEOLOGY,
        "last_igehely": "Jn 3,16",
        "sermon_workshop": {"sermon_main_idea": "NE EZT KÜLDD"},
        "text_workshop": {"text_main_idea": "NE EZT SEM"},
    }
    state.update(overrides)
    return state


def _mock_generate(text: str, bucket: list | None = None):
    def _fn(prompt, **kwargs):
        if bucket is not None:
            bucket.append({"prompt": prompt, "kwargs": kwargs})
        return text

    return _fn


def test_extract_module_has_no_streamlit_or_supabase():
    src = (ROOT / "writing_desk_extracts.py").read_text(encoding="utf-8")
    assert "streamlit" not in src
    assert "supabase" not in src.casefold()
    assert "from app import" not in src


def test_original_text_extract_can_be_generated():
    session = _session_with_sources()
    calls: list[dict] = []
    result = generate_writing_desk_extract(
        session,
        "original_text",
        generate_fn=_mock_generate("Az οὕτως a szeretet módját emeli ki.", calls),
    )
    assert result.ok is True
    assert result.llm_called is True
    assert "οὕτως" in result.content
    assert result.source_fingerprint == current_extract_fingerprint(
        session, "original_text"
    )
    assert (
        session[WRITING_DESK_KEY]["extracts"]["original_text"]["content"]
        == result.content
    )
    assert "Eredeti szöveg" in calls[0]["prompt"]
    assert SOURCE_ORIGINAL in calls[0]["prompt"]
    assert SOURCE_HISTORY not in calls[0]["prompt"]
    assert SOURCE_THEOLOGY not in calls[0]["prompt"]
    assert "NE EZT KÜLDD" not in calls[0]["prompt"]
    assert calls[0]["kwargs"]["tab_label"] == TAB_LABEL_EXTRACT
    assert calls[0]["kwargs"]["max_output_tokens"] == MAX_OUTPUT_TOKENS == 8000
    assert calls[0]["kwargs"]["truncation_notice_mode"] == "never"
    assert (
        calls[0]["kwargs"]["incomplete_response_message"]
        == _EXTRACT_INCOMPLETE_SENTINEL
    )


def test_history_extract_can_be_generated():
    session = _session_with_sources()
    result = generate_writing_desk_extract(
        session,
        "history",
        generate_fn=_mock_generate("A zsinagógától való elszakadás formálta a szöveget."),
    )
    assert result.ok is True
    assert inspect_writing_desk_extract(session, "history").status == STATUS_VALID
    assert "zsinagógától" in session[WRITING_DESK_KEY]["extracts"]["history"]["content"]


def test_theology_extract_can_be_generated():
    session = _session_with_sources()
    result = generate_writing_desk_extract(
        session,
        "theology",
        generate_fn=_mock_generate("Isten szeretete kezdeményező ajándék."),
    )
    assert result.ok is True
    assert inspect_writing_desk_extract(session, "theology").status == STATUS_VALID
    assert "kezdeményező" in result.content


def test_missing_source_does_not_call_llm():
    session = {"original_text": "", "history": "  ", "theology": None}
    calls: list[dict] = []
    for key in WRITING_DESK_EXTRACT_KEYS:
        result = generate_writing_desk_extract(
            session,
            key,
            generate_fn=_mock_generate("NE HÍVD", calls),
        )
        assert result.ok is False
        assert result.llm_called is False
        assert inspect_writing_desk_extract(session, key).status == STATUS_MISSING_SOURCE
        assert result.error_message == EXTRACT_MISSING_MESSAGES[key]
    assert calls == []


def test_matching_fingerprint_reuses_saved_extract_without_llm():
    session = _session_with_sources()
    set_writing_desk_extract(
        session,
        "history",
        content="Mentett kortörténeti kivonat.",
        source_fingerprint=current_extract_fingerprint(session, "history"),
    )
    calls: list[dict] = []
    result = generate_writing_desk_extract(
        session,
        "history",
        generate_fn=_mock_generate("új szöveg", calls),
    )
    assert result.ok is True
    assert result.llm_called is False
    assert result.used_cache is True
    assert result.content == "Mentett kortörténeti kivonat."
    assert calls == []


def test_changed_source_is_stale_and_not_valid():
    session = _session_with_sources()
    set_writing_desk_extract(
        session,
        "theology",
        content="Régi teológiai kivonat.",
        source_fingerprint=fingerprint_source_text("régi forrás"),
    )
    view = inspect_writing_desk_extract(session, "theology")
    assert view.status == STATUS_STALE
    assert view.content == ""
    assert view.saved_content == "Régi teológiai kivonat."


def test_successful_generation_stores_content_and_fingerprint():
    session = _session_with_sources()
    result = generate_writing_desk_extract(
        session,
        "original_text",
        generate_fn=_mock_generate("Első mondat.\nMásodik mondat.\nHarmadik mondat."),
    )
    stored = session[WRITING_DESK_KEY]["extracts"]["original_text"]
    assert stored["content"] == result.content
    assert stored["source_fingerprint"] == current_extract_fingerprint(
        session, "original_text"
    )
    assert stored["source_fingerprint"] == result.source_fingerprint
    assert inspect_writing_desk_extract(session, "original_text").status == STATUS_VALID


def test_llm_error_does_not_overwrite_previous_extract():
    session = _session_with_sources()
    previous = "Érvényes, de elavult kivonat."
    set_writing_desk_extract(
        session,
        "history",
        content=previous,
        source_fingerprint=fingerprint_source_text("régi kortörténet"),
    )
    assert inspect_writing_desk_extract(session, "history").status == STATUS_STALE

    result = generate_writing_desk_extract(
        session,
        "history",
        generate_fn=_mock_generate("⚠️ **Hiányzó API kulcs.**"),
    )
    assert result.ok is False
    assert result.llm_called is True
    stored = session[WRITING_DESK_KEY]["extracts"]["history"]
    assert stored["content"] == previous
    assert stored["source_fingerprint"] == fingerprint_source_text("régi kortörténet")

    def _boom(*args, **kwargs):
        raise RuntimeError("network down")

    again = generate_writing_desk_extract(session, "history", generate_fn=_boom)
    assert again.ok is False
    assert session[WRITING_DESK_KEY]["extracts"]["history"]["content"] == previous


def test_generating_one_extract_does_not_change_the_others():
    session = _session_with_sources()
    set_writing_desk_extract(
        session,
        "original_text",
        content="Eredeti kivonat.",
        source_fingerprint=fingerprint_source_text(SOURCE_ORIGINAL),
    )
    set_writing_desk_extract(
        session,
        "theology",
        content="Teológiai kivonat.",
        source_fingerprint=fingerprint_source_text(SOURCE_THEOLOGY),
    )
    generate_writing_desk_extract(
        session,
        "history",
        generate_fn=_mock_generate("Új kortörténeti kivonat."),
    )
    extracts = session[WRITING_DESK_KEY]["extracts"]
    assert extracts["original_text"]["content"] == "Eredeti kivonat."
    assert extracts["theology"]["content"] == "Teológiai kivonat."
    assert extracts["history"]["content"] == "Új kortörténeti kivonat."


def test_prompt_contains_only_the_requested_source_module():
    prompt = build_extract_prompt("theology", SOURCE_THEOLOGY)
    assert SOURCE_THEOLOGY in prompt
    assert SOURCE_ORIGINAL not in prompt
    assert SOURCE_HISTORY not in prompt
    assert "sermon_workshop" not in prompt
    assert "UNTRUSTED_DATA" in prompt
    assert EXTRACT_LABELS["theology"] in prompt
    assert "3–5" in prompt or "3-5" in prompt
    assert "teológiai forrásréteg" in prompt
    history_prompt = build_extract_prompt("history", SOURCE_HISTORY)
    assert "történeti vagy kulturális" in history_prompt
    assert "dogmatikai" in history_prompt
    original_prompt = build_extract_prompt("original_text", SOURCE_ORIGINAL)
    assert "nyelvi és szövegi" in original_prompt
    assert EXTRACT_ROLE_INSTRUCTIONS["history"]
    assert inspect_writing_desk_extract(
        {"theology": SOURCE_THEOLOGY}, "theology"
    ).status == STATUS_READY
    assert "saját emlékezetből" in EXTRACT_SYSTEM_BUNDLE


def test_source_text_for_extract_reads_only_matching_field():
    session = _session_with_sources()
    assert source_text_for_extract(session, "history") == SOURCE_HISTORY
    assert SOURCE_ORIGINAL not in source_text_for_extract(session, "history")


_PARTIAL_EXTRACT = (
    "Az ἀσώτως (asótós) határozószó nem csupán a tékozló pénzszórásra utal, "
    "hanem egy olyan mértéktelen élet"
)
_DEFAULT_TRUNCATION_NOTE = (
    "> ⚠️ **A válasz a modell kimeneti korlátjánál megszakadt.** "
    "Kérlek, próbáld újra vagy bontsd kisebb részekre a kérést; "
    "részletekért használd a **finomítás chatet**."
)


def test_output_limit_sentinel_does_not_save_extract():
    session = _session_with_sources()
    result = generate_writing_desk_extract(
        session,
        "original_text",
        generate_fn=_mock_generate(_EXTRACT_INCOMPLETE_SENTINEL),
    )
    assert result.ok is False
    assert result.llm_called is True
    assert result.error_message == EXTRACT_INCOMPLETE_MESSAGE
    stored = session.get(WRITING_DESK_KEY, {}).get("extracts", {}).get("original_text", {})
    assert stored.get("content", "") == ""
    assert inspect_writing_desk_extract(session, "original_text").status == STATUS_READY


def test_output_limit_partial_text_is_not_saved():
    session = _session_with_sources()
    payload = f"{_PARTIAL_EXTRACT}\n\n---\n\n{_DEFAULT_TRUNCATION_NOTE}"
    result = generate_writing_desk_extract(
        session,
        "history",
        generate_fn=_mock_generate(payload),
    )
    assert result.ok is False
    assert result.error_message == EXTRACT_INCOMPLETE_MESSAGE
    stored = session.get(WRITING_DESK_KEY, {}).get("extracts", {}).get("history", {})
    assert stored.get("content", "") == ""
    assert _PARTIAL_EXTRACT not in str(stored.get("content", ""))
    assert inspect_writing_desk_extract(session, "history").status == STATUS_READY
    assert inspect_writing_desk_extract(session, "history").content == ""


def test_failed_generation_leaves_previous_valid_extract_intact():
    session = _session_with_sources()
    previous = "Érvényes, teljes mondatos kortörténeti kivonat."
    set_writing_desk_extract(
        session,
        "history",
        content=previous,
        source_fingerprint=fingerprint_source_text("régi kortörténet"),
    )
    payload = f"{_PARTIAL_EXTRACT}\n\n---\n\n{_DEFAULT_TRUNCATION_NOTE}"
    result = generate_writing_desk_extract(
        session,
        "history",
        generate_fn=_mock_generate(payload),
    )
    assert result.ok is False
    stored = session[WRITING_DESK_KEY]["extracts"]["history"]
    assert stored["content"] == previous
    assert stored["source_fingerprint"] == fingerprint_source_text("régi kortörténet")
    view = inspect_writing_desk_extract(session, "history")
    assert view.status == STATUS_STALE
    assert view.content == ""
    assert view.saved_content == previous


def test_previously_saved_truncated_extract_is_not_treated_as_valid():
    session = _session_with_sources()
    payload = f"{_PARTIAL_EXTRACT}\n\n---\n\n{_DEFAULT_TRUNCATION_NOTE}"
    set_writing_desk_extract(
        session,
        "theology",
        content=payload,
        source_fingerprint=fingerprint_source_text(SOURCE_THEOLOGY),
    )
    view = inspect_writing_desk_extract(session, "theology")
    assert view.status == STATUS_READY
    assert view.content == ""

    calls: list[dict] = []
    result = generate_writing_desk_extract(
        session,
        "theology",
        generate_fn=_mock_generate("Teljes, rövid teológiai megállapítás.", calls),
    )
    assert result.ok is True
    assert result.llm_called is True
    assert calls, "a csonka mentett kivonat nem lehet cache-hit"
    assert session[WRITING_DESK_KEY]["extracts"]["theology"]["content"] == (
        "Teljes, rövid teológiai megállapítás."
    )


def test_lk15_theology_extract_is_stale_on_jn316_passage():
    lk_theology = (
        "Az elébesiető Atya ünneppel fogadja a hazatérő fiút: "
        "a halott él, az elveszett megtaláltatott."
    )
    lk_session = {
        "last_igehely": "Lk 15,11–24",
        "bible_translation": "RÚF 2014",
        "passage_text": "Egy embernek volt két fia.",
        "theology": lk_theology,
        "original_text": "Az ἀσώτως mértéktelen életmódot jelöl.",
        "history": "Az örökség előre kérése megszégyenítés volt.",
    }
    for key, source in (
        ("theology", lk_theology),
        ("original_text", lk_session["original_text"]),
        ("history", lk_session["history"]),
    ):
        set_writing_desk_extract(
            lk_session,
            key,
            content=f"Lk 15 {key} kivonat.",
            source_fingerprint=current_extract_fingerprint(lk_session, key),
        )
        assert inspect_writing_desk_extract(lk_session, key).status == STATUS_VALID

    jn_session = dict(lk_session)
    jn_session["last_igehely"] = "Jn 3,16"
    jn_session["passage_text"] = "Mert úgy szerette Isten a világot."
    for key in WRITING_DESK_EXTRACT_KEYS:
        view = inspect_writing_desk_extract(jn_session, key)
        assert view.status == STATUS_STALE
        assert view.content == ""
        assert "Lk 15" in view.saved_content


def test_source_only_fingerprint_is_not_valid_across_textus():
    session = {
        "last_igehely": "Jn 3,16",
        "passage_text": "Mert úgy szerette Isten a világot.",
        "theology": (
            "Az elébesiető Atya ünneppel fogadja a hazatérő fiút: "
            "a halott él, az elveszett megtaláltatott."
        ),
    }
    leftover = session["theology"]
    set_writing_desk_extract(
        session,
        "theology",
        content="Lk 15 teológiai kivonat, ne ezt mutasd Jn 3,16-ként.",
        source_fingerprint=fingerprint_source_text(leftover),
    )
    view = inspect_writing_desk_extract(session, "theology")
    assert view.status == STATUS_STALE
    assert view.content == ""
