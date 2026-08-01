"""Regressziós tesztek a közös exegetikai maghoz (§12–20)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from exegetical_core import (
    LINKED_PASSAGE_OUTPUT_KEYS,
    SESSION_CORE_KEY,
    SESSION_PASSAGE_FP_KEY,
    SOURCE_DATA_VERSION,
    ClaimKind,
    ExegeticalCoreResult,
    SelectedExpression,
    SourceReference,
    build_exegetical_core,
    compute_exegetical_fingerprint,
    compute_passage_fingerprint,
    core_to_outline_brief,
    ensure_exegetical_core,
    get_cached_core,
    invalidate_core_if_stale,
    select_keyword_candidates,
    store_core,
    validate_core_result,
)
from exegetical_enrichment import (
    CautiousModelSynthesisService,
    NullEnrichmentService,
    _parse_enrichment_payload,
)


JUDE_TOKENS = [
    {
        "language": "greek",
        "verse": 24,
        "chapter": 1,
        "book": "JUD",
        "tokens": [
            {"form": "φυλάξαι", "lemma": "φυλάσσω", "morph": "V-AAN", "strong": "G5442", "index": 1},
            {"form": "ἀπταίστους", "lemma": "ἄπταιστος", "morph": "A-APM", "strong": "G679", "index": 2},
            {"form": "καί", "lemma": "καί", "morph": "CONJ", "strong": "G2532", "index": 3},
            {"form": "στῆσαι", "lemma": "ἵστημι", "morph": "V-AAN", "strong": "G2476", "index": 4},
            {"form": "ἀμώμους", "lemma": "ἄμωμος", "morph": "A-APM", "strong": "G299", "index": 5},
            {"form": "ἐνώπιον", "lemma": "ἐνώπιον", "morph": "PREP", "strong": "G1799", "index": 6},
            {"form": "δόξης", "lemma": "δόξα", "morph": "N-GSF", "strong": "G1391", "index": 7},
            {"form": "ἀγαλλιάσει", "lemma": "ἀγαλλίασις", "morph": "N-DSF", "strong": "G20", "index": 8},
        ],
    },
    {
        "language": "greek",
        "verse": 25,
        "chapter": 1,
        "book": "JUD",
        "tokens": [
            {"form": "μόνῳ", "lemma": "μόνος", "morph": "A-DSM", "strong": "G3441", "index": 1},
            {"form": "θεῷ", "lemma": "θεός", "morph": "N-DSM", "strong": "G2316", "index": 2},
            {"form": "σωτῆρι", "lemma": "σωτήρ", "morph": "N-DSM", "strong": "G4990", "index": 3},
            {"form": "δόξα", "lemma": "δόξα", "morph": "N-NSF", "strong": "G1391", "index": 4},
            {"form": "μεγαλωσύνη", "lemma": "μεγαλωσύνη", "morph": "N-NSF", "strong": "G3172", "index": 5},
            {"form": "κράτος", "lemma": "κράτος", "morph": "N-NSN", "strong": "G2904", "index": 6},
            {"form": "καί", "lemma": "καί", "morph": "CONJ", "strong": "G2532", "index": 7},
            {"form": "ἐξουσία", "lemma": "ἐξουσία", "morph": "N-NSF", "strong": "G1849", "index": 8},
            {"form": "Ἀμήν", "lemma": "ἀμήν", "morph": "HEB", "strong": "G281", "index": 9},
        ],
    },
]

JUDE_TEXT = (
    "Annak pedig, aki megőrizhet titeket a botlástól, "
    "és feddhetetlenségben állíthat dicsősége elé nagy örömmel, "
    "az egyedül üdvözítő Istennek… dicsőség, hatalom és uralom… Ámen."
)


def test_select_keywords_selective_short_passage():
    selected = select_keyword_candidates(JUDE_TOKENS)
    assert 2 <= len(selected) <= 6
    lemmas = " ".join(e.lemma for e in selected).casefold()
    # Ne emelje ki a καί-t
    assert "καί" not in {e.lemma for e in selected}
    # Fontos lemmák közül legalább egy
    assert any(
        x in lemmas for x in ("φυλάσσω", "ἄπταιστος", "ἄμωμος", "σωτήρ", "θεός", "δόξα")
    )


def test_related_phrases_can_merge():
    selected = select_keyword_candidates(JUDE_TOKENS)
    phrases = [e for e in selected if e.is_phrase]
    # aptaistos + amomos vagy theos+soter
    assert phrases or any("+" in e.lemma for e in selected) or len(selected) >= 2
    # Ha mindkét melléknév bekerült, legyen phrase
    surfaces = " ".join(e.surface for e in selected)
    if "ἀπταίστους" in surfaces and "ἀμώμους" in surfaces:
        assert any(e.is_phrase for e in selected)


def test_build_core_prose_no_mechanical_subheads():
    core = build_exegetical_core(
        reference="Júd 24–25",
        bible_text=JUDE_TEXT,
        token_verses=JUDE_TOKENS,
        generate_fn=None,
        enrich=False,
    )
    md = core.to_display_markdown()
    assert "## Szöveg és szerkezet" in md
    assert "## Kulcskifejezések" in md
    assert "## Teológiai összegzés" in md
    assert "## Átadás a homiletikai műhelynek" in md
    low = md.casefold()
    assert "alapjelentés:" not in low
    assert "miért fontos" not in low
    assert "igehirdetési hozam:" not in low
    # Összefüggő próza — ne csak egy-két szó
    assert len(core.concise_analysis.split()) >= 20
    issues = validate_core_result(core)
    assert "mechanical_subheads" not in issues
    assert "disproportionate_length" not in issues


def test_detailed_morphology_separated_from_default_display():
    core = build_exegetical_core(
        reference="Júd 24–25",
        bible_text=JUDE_TEXT,
        token_verses=JUDE_TOKENS,
        enrich=False,
    )
    display = core.to_display_markdown()
    morph = core.detailed_morphology_markdown()
    assert morph
    assert "| Forma |" in morph
    # Az alap megjelenés ne legyen a teljes morph tábla
    assert "| Forma |" not in display
    assert len(core.detailed_morphology) >= len(core.selected_expressions)


def test_short_passage_not_disproportionately_long():
    core = build_exegetical_core(
        reference="Júd 24–25",
        bible_text=JUDE_TEXT,
        token_verses=JUDE_TOKENS,
        enrich=False,
    )
    total = (
        len(core.concise_analysis.split())
        + sum(len(e.prose_paragraph.split()) for e in core.selected_expressions)
        + len(core.theological_synthesis.split())
    )
    assert total < 900
    assert len(core.selected_expressions) <= 6


def test_claim_kinds_distinguish_fact_and_theology():
    core = build_exegetical_core(
        reference="Júd 24–25",
        bible_text=JUDE_TEXT,
        token_verses=JUDE_TOKENS,
        enrich=False,
    )
    kinds = set()
    for e in core.selected_expressions:
        kinds.update(e.claim_kinds)
    assert ClaimKind.TEXT_DATA.value in kinds
    # Homiletikai híd a bridge mezőben, ne lexikai tényként
    assert core.homiletical_bridge
    for e in core.selected_expressions:
        only_hom = set(e.claim_kinds or []) == {ClaimKind.HOMILETICAL_BRIDGE.value}
        assert not (only_hom and e.grounded)


def test_enrichment_does_not_override_token_facts():
    def fake_enrich_generate(prompt, **kwargs):
        return json.dumps(
            {
                "notes": "Külső megjegyzés a φυλάσσω-ról.",
                "items": [
                    {
                        "related": "φυλάσσω",
                        "excerpt": "megőriz",
                        "origin": "model_synthesis",
                        "reliability": "unverified",
                    }
                ],
            },
            ensure_ascii=False,
        )

    service = CautiousModelSynthesisService(fake_enrich_generate)
    core = build_exegetical_core(
        reference="Júd 24–25",
        bible_text=JUDE_TEXT,
        token_verses=JUDE_TOKENS,
        generate_fn=None,
        enrich=True,
        enrichment_service=service,
    )
    # Token lemma megmarad
    lemmas = [e.lemma for e in core.selected_expressions]
    assert any("φυλάσσω" in L or "ἄπταιστος" in L or "+" in L for L in lemmas)
    # Forrásjegyzet megvan, de nem írja felül a textus-adatot
    assert core.alignment_status == "aligned"
    assert core.raw_token_verses


def test_no_fake_external_source_without_url():
    notes, refs = _parse_enrichment_payload(
        json.dumps(
            {
                "notes": "x",
                "items": [
                    {
                        "related": "δόξα",
                        "excerpt": "dicsőség",
                        "origin": "external",
                        "source_name": "Wikipedia",
                        "reliability": "high",
                    }
                ],
            }
        )
    )
    assert refs
    assert refs[0].origin == "model_synthesis"
    assert refs[0].reliability == "unverified"
    assert not refs[0].url

    core = build_exegetical_core(
        reference="Júd 24–25",
        bible_text=JUDE_TEXT,
        token_verses=JUDE_TOKENS,
        enrich=False,
    )
    core.source_references.extend(refs)
    issues = validate_core_result(core)
    assert "fake_external_source" not in issues  # downgrade miatt


def test_null_enrichment_leaves_no_invented_citations():
    core = build_exegetical_core(
        reference="Júd 24–25",
        bible_text=JUDE_TEXT,
        token_verses=JUDE_TOKENS,
        enrich=True,
        enrichment_service=NullEnrichmentService(),
    )
    for s in core.source_references:
        if s.origin == "external":
            assert s.url, "külső forrás URL nélkül tilos"
        assert "http://fake" not in (s.url or "")
        assert "example.com" not in (s.url or "")


def test_cache_invalidation_on_text_or_version_change():
    session: dict[str, Any] = {}
    core = build_exegetical_core(
        reference="Júd 24–25",
        bible_text=JUDE_TEXT,
        token_verses=JUDE_TOKENS,
        enrich=False,
    )
    store_core(session, core)
    hit = get_cached_core(session, reference="Júd 24–25", bible_text=JUDE_TEXT)
    assert hit is not None
    assert hit.fingerprint == core.fingerprint

    # Más textus → érvénytelen
    assert (
        get_cached_core(session, reference="Júd 24–25", bible_text=JUDE_TEXT + " X")
        is None
    )
    assert invalidate_core_if_stale(
        session, reference="Júd 24–25", bible_text=JUDE_TEXT + " X"
    )

    # Újra store, majd más referencia
    store_core(session, core)
    assert get_cached_core(session, reference="Jn 3,16", bible_text=JUDE_TEXT) is None

    # Adatverzió változás
    store_core(session, core)
    session[SESSION_CORE_KEY]["source_data_version"] = "old_v0"
    assert get_cached_core(session, reference="Júd 24–25", bible_text=JUDE_TEXT) is None


def test_original_text_and_outline_share_same_core():
    session: dict[str, Any] = {}
    core1 = build_exegetical_core(
        reference="Júd 24–25",
        bible_text=JUDE_TEXT,
        token_verses=JUDE_TOKENS,
        enrich=False,
    )
    store_core(session, core1, sync_original_text=True)
    # Második hívás (vázlat) ugyanazt a cache-t kapja — display nélkül
    core2 = ensure_exegetical_core(
        session,
        reference="Júd 24–25",
        bible_text=JUDE_TEXT,
        generate_fn=None,
        enrich=False,
        sync_original_text=False,
    )
    assert core1.fingerprint == core2.fingerprint
    assert session.get(SESSION_CORE_KEY)
    assert session.get("original_text")
    brief = core_to_outline_brief(core2)
    assert brief.central_claim == core2.central_claim
    assert brief.grounded_in_original_data
    assert brief.key_expressions


def test_ai_merge_preserves_grounded_tokens():
    def fake_ai(prompt, **kwargs):
        return json.dumps(
            {
                "literary_movement": "doxológia: megtartás → dicsőítés",
                "central_claim": "Isten megőriz és dicsősége elé állít.",
                "concise_analysis": (
                    "A szakasz a megtartástól a dicsőítésig vezet. "
                    "A központi állítás Isten egyedül üdvözítő hatalma. "
                    "A nyelvtani ív a megőrzés és az elé állítás körül forog."
                ),
                "expressions": [
                    {
                        "lemma_or_surface": "φυλάσσω",
                        "prose_paragraph": (
                            "A φυλάσσω aoristos infinitivusa a megőrzés "
                            "isteni cselekvését emeli ki a szakaszban."
                        ),
                        "contextual_gloss": "megőrizni",
                        "role_in_passage": "megtartó mozgás",
                        "claim_kinds": ["TEXT_DATA", "INTERPRETATION"],
                    }
                ],
                "theological_synthesis": (
                    "A szöveg Isten megtartó kegyelmét állítja középpontba."
                ),
                "homiletical_bridge": (
                    "A hallgató botlásfélelme felől Isten ígéretéhez vezet."
                ),
                "warnings": [],
                "confidence_flags": ["high_confidence_on_tokens"],
            },
            ensure_ascii=False,
        )

    core = build_exegetical_core(
        reference="Júd 24–25",
        bible_text=JUDE_TEXT,
        token_verses=JUDE_TOKENS,
        generate_fn=fake_ai,
        enrich=False,
    )
    assert "megtartás" in core.literary_movement.casefold() or "doxológ" in core.literary_movement.casefold()
    assert core.raw_token_verses
    assert core.source_data_version == SOURCE_DATA_VERSION
    # Fingerprint stabil
    fp = compute_exegetical_fingerprint(
        reference="Júd 24–25",
        bible_text=JUDE_TEXT,
        original_language=core.original_language,
        token_signature=core.fingerprint and "",  # recomputed below via ensure
    )
    assert isinstance(fp, str) and len(fp) >= 8


def test_enrichment_cannot_inject_fake_lemma_into_selection():
    """A kiegészítés nem cserélheti le a tokenekből származó szelekciót kitalált lemmára."""
    before = select_keyword_candidates(JUDE_TOKENS)
    before_lemmas = {e.lemma for e in before}

    def evil_ai(prompt, **kwargs):
        return json.dumps(
            {
                "literary_movement": "x",
                "central_claim": "y",
                "concise_analysis": "A szakasz rövid mozgása itt. Második bekezdés is.",
                "expressions": [
                    {
                        "lemma_or_surface": "φαντασία",
                        "prose_paragraph": "Ez a lemma nincs a textusban.",
                        "claim_kinds": ["TEXT_DATA"],
                    }
                ],
                "theological_synthesis": "Teológia.",
                "homiletical_bridge": "Híd.",
            }
        )

    core = build_exegetical_core(
        reference="Júd 24–25",
        bible_text=JUDE_TEXT,
        token_verses=JUDE_TOKENS,
        generate_fn=evil_ai,
        enrich=False,
    )
    # A kiválasztott kifejezések a token-alapú listából indulnak;
    # a fantázia lemma nem válhat grounded TEXT_DATA-vá token nélkül.
    for e in core.selected_expressions:
        if "φαντασία" in (e.lemma or ""):
            assert not e.grounded or ClaimKind.TEXT_DATA.value not in (e.claim_kinds or [])
        else:
            # Meglévő jelöltek grounded maradnak
            if e.lemma in before_lemmas or e.is_phrase:
                assert e.grounded


@pytest.mark.parametrize(
    "heading",
    ["Alapjelentés:", "Miért fontos", "Mélyebb árnyalat", "Igehirdetési hozam:"],
)
def test_validate_flags_mechanical_subheads(heading: str):
    core = build_exegetical_core(
        reference="Júd 24–25",
        bible_text=JUDE_TEXT,
        token_verses=JUDE_TOKENS,
        enrich=False,
    )
    if core.selected_expressions:
        core.selected_expressions[0].prose_paragraph = f"**{heading}** valami szöveg."
    issues = validate_core_result(core)
    assert "mechanical_subheads" in issues


def test_generated_expression_must_be_token_backed():
    core = build_exegetical_core(
        reference="Júd 24–25",
        bible_text=JUDE_TEXT,
        token_verses=JUDE_TOKENS,
        enrich=False,
    )
    core.selected_expressions.append(
        SelectedExpression(
            surface="not_in_text",
            lemma="imaginary_lemma",
            grounded=True,
            claim_kinds=[ClaimKind.TEXT_DATA.value],
        )
    )
    assert "ungrounded_expression" in validate_core_result(core)


def test_generated_morphology_must_be_token_backed():
    core = build_exegetical_core(
        reference="Júd 24–25",
        bible_text=JUDE_TEXT,
        token_verses=JUDE_TOKENS,
        enrich=False,
    )
    assert core.selected_expressions
    core.selected_expressions[0].morph_relevant = "V-FAKE-999"
    assert "ungrounded_morphology" in validate_core_result(core)


def test_missing_original_language_data_does_not_invent_sources():
    core = build_exegetical_core(
        reference="Eszt 4,14",
        bible_text="Ki tudja, talán a mostani idő miatt jutottál királyságra?",
        token_verses=[],
        enrich=False,
    )
    assert core.original_language == "unknown"
    assert not core.selected_expressions
    assert "no_tokens" in core.confidence_flags
    assert any("token" in w.casefold() for w in core.warnings)
    assert not [s for s in core.source_references if s.source_type == "database"]


def test_passage_fingerprint_includes_schema_and_text():
    base = compute_passage_fingerprint(
        reference="Júd 24-25",
        bible_text=JUDE_TEXT,
        token_signature="abc",
        prompt_schema_version="schema_a",
    )
    changed_schema = compute_passage_fingerprint(
        reference="Júd 24-25",
        bible_text=JUDE_TEXT,
        token_signature="abc",
        prompt_schema_version="schema_b",
    )
    changed_text = compute_passage_fingerprint(
        reference="Júd 24-25",
        bible_text=JUDE_TEXT + " X",
        token_signature="abc",
        prompt_schema_version="schema_a",
    )
    assert base != changed_schema
    assert base != changed_text


def test_stale_core_invalidates_linked_passage_outputs():
    session: dict[str, Any] = {
        key: f"old-{key}" for key in LINKED_PASSAGE_OUTPUT_KEYS
    }
    core = build_exegetical_core(
        reference="Júd 24–25",
        bible_text=JUDE_TEXT,
        token_verses=JUDE_TOKENS,
        enrich=False,
    )
    store_core(session, core)
    assert session.get(SESSION_PASSAGE_FP_KEY) == core.passage_fingerprint

    changed = invalidate_core_if_stale(
        session,
        reference="Júd 24–25",
        bible_text=JUDE_TEXT + " Másik textus.",
    )
    assert changed
    assert SESSION_CORE_KEY not in session
    assert SESSION_PASSAGE_FP_KEY not in session
    assert all(key not in session for key in LINKED_PASSAGE_OUTPUT_KEYS)


def test_outline_bundle_prefers_core_over_legacy_markdown():
    from sermon_workshop_outline_ai import _truncate, collect_outline_context_bundle

    session: dict[str, Any] = {
        "last_igehely": "Júd 24–25",
        "passage_text": JUDE_TEXT,
        "exegesis": "RÉGI MARKDOWN " * 300,
        "theology": "Régi teológiai markdown",
        "history": "Régi kortörténet",
        "original_text": "Régi eredeti szöveg markdown",
    }
    core = build_exegetical_core(
        reference="Júd 24–25",
        bible_text=JUDE_TEXT,
        token_verses=JUDE_TOKENS,
        enrich=False,
    )
    store_core(session, core, sync_original_text=False)

    bundle = collect_outline_context_bundle(session)
    assert "exegetical_core" in bundle
    assert bundle["exegetical_core"]["passage_fingerprint"] == core.passage_fingerprint
    assert bundle["exegesis"] == _truncate(core.to_prompt_summary(), 1600)
    assert "RÉGI MARKDOWN" not in bundle["exegesis"]
    assert "theology" not in bundle
    assert "history" not in bundle
    assert "original_text" not in bundle


@pytest.mark.parametrize(
    ("reference", "text"),
    [
        (
            "Mk 4,35-41",
            "Aznap este Jézus átviszi tanítványait a túlsó partra; "
            "vihar támad, ő pedig lecsendesíti a szelet és a tengert.",
        ),
        (
            "Róm 8,31-39",
            "Ha Isten velünk, ki lehet ellenünk? Pál érvelése a vád, "
            "kárhoztatás és elszakító erők ellen sorakoztatja Isten szeretetét.",
        ),
    ],
)
def test_core_handles_narrative_and_argumentative_passages_without_tokens(reference: str, text: str):
    core = build_exegetical_core(
        reference=reference,
        bible_text=text,
        token_verses=[],
        enrich=False,
    )
    assert core.is_usable()
    assert core.literary_genre
    assert core.central_claim
    assert not core.selected_expressions


def test_jude_24_25_full_dry_run_without_model_calls():
    from sermon_outline_engine import generate_sermon_outline
    from sermon_workshop_outline_ai import collect_outline_context_bundle

    session: dict[str, Any] = {
        "last_igehely": "Júd 24–25",
        "passage_reference": "Júd 24–25",
        "passage_text": JUDE_TEXT,
        "exegesis": "RÉGI TELJES MARKDOWN\n\n## Vitatott\nAutomatikus zaj.",
        "theology": "Régi teológiai markdown zaj.",
        "history": "Régi történeti markdown zaj.",
        "original_text": "Régi eredeti szöveg markdown zaj.",
    }
    core = build_exegetical_core(
        reference="Júd 24–25",
        bible_text=JUDE_TEXT,
        token_verses=JUDE_TOKENS,
        generate_fn=None,
        enrich=False,
    )
    store_core(session, core, sync_original_text=False)

    view_model = core.to_prompt_dict()
    display = core.to_display_markdown()
    bundle = collect_outline_context_bundle(session)
    outline = generate_sermon_outline(
        session,
        mode="quick",
        generate_fn=None,
        force_overwrite=True,
    )

    token_values = {
        str(tok.get(key) or "").casefold()
        for verse in JUDE_TOKENS
        for tok in verse["tokens"]
        for key in ("form", "lemma")
        if tok.get(key)
    }
    for expr in core.selected_expressions:
        parts = []
        for candidate in [expr.surface, expr.lemma, *expr.forms]:
            raw = str(candidate or "").casefold()
            if "+" in raw:
                parts.extend(x.strip() for x in raw.split("+") if x.strip())
            elif raw:
                parts.append(raw)
        assert any(part in token_values for part in parts)

    assert view_model["passage_fingerprint"] == core.passage_fingerprint
    assert "exegetical_core" in bundle
    assert "RÉGI TELJES MARKDOWN" not in bundle.get("exegesis", "")
    assert "theology" not in bundle
    assert "history" not in bundle
    assert "original_text" not in bundle
    assert "## Vitatott" not in display
    assert "Prédikációs haszon" not in display
    assert "Igehirdetési hozam" not in display
    assert "## Átadás a homiletikai műhelynek" in display
    assert validate_core_result(core) == []

    assert outline.ok
    titles = " ".join(
        str(m.get("title") or "")
        for m in outline.outline.get("movements", [])
        if isinstance(m, dict)
    ).casefold()
    assert "ámen" not in titles and "amen" not in titles

    assert get_cached_core(session, reference="Júd 24–25", bible_text=JUDE_TEXT)
    assert invalidate_core_if_stale(
        session,
        reference="Júd 24–25",
        bible_text=JUDE_TEXT + " Textusváltás.",
    )
    assert get_cached_core(
        session,
        reference="Júd 24–25",
        bible_text=JUDE_TEXT + " Textusváltás.",
    ) is None
