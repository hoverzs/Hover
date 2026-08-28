from __future__ import annotations

import json
import os
from pathlib import Path

from streamlit.testing.v1 import AppTest

from bible_engine.greek_analysis_ui import (
    CROSS_CHAPTER_GREEK_MESSAGE,
    GREEK_DATA_ERROR_MESSAGE,
    INVALID_GREEK_DATABASE_MESSAGE,
    LEXICON_HU_PATH,
    LEXICAL_SCOPE_NOTE,
    MISSING_GREEK_DATA_MESSAGE,
    MISSING_GREEK_DATABASE_MESSAGE,
    NO_LEXICON_ENTRY_MESSAGE,
    OLD_TESTAMENT_MESSAGE,
    TAGNT_DATABASE_BUILD_HINT,
    TBESG_DATABASE_MISSING_MESSAGE,
    TBESG_SCOPE_NOTE,
    TBESG_SOURCE_NOTE,
    component_state_token_key,
    greek_reference_status,
    load_demo_hungarian_lexicon,
    render_greek_analysis_block,
)
from bible_engine.greek_token_repository import GreekVerseTokens
from bible_engine.greek_token_repository import TAGNT_DATABASE_ENV_VAR
from bible_engine.tagnt_parser import GreekToken
from bible_engine.tagnt_sqlite import import_tagnt_book
from components.greek_token_selector import component_tokens, normalize_component_selection_key


ROOT = Path(__file__).parents[1]


def _render_john_3_16_block() -> None:
    from bible_engine.greek_analysis_ui import load_john_3_16_tokens, render_greek_analysis_block

    render_greek_analysis_block(
        reference="Jn 3,16",
        key_prefix="test_greek",
        token_loader=load_john_3_16_tokens,
        tbesg_lexicon_loader=lambda _strong_id: None,
    )


def _render_john_3_16_compact_block() -> None:
    from bible_engine.greek_analysis_ui import load_john_3_16_tokens, render_greek_analysis_block

    render_greek_analysis_block(
        reference="Jn 3,16",
        key_prefix="test_greek_compact",
        token_loader=load_john_3_16_tokens,
        tbesg_lexicon_loader=lambda _strong_id: None,
        display_mode="compact",
    )


def _render_john_3_16_default_loader_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block

    render_greek_analysis_block(reference="Jn 3,16", key_prefix="test_greek")


def _render_multi_verse_john_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block
    from bible_engine.greek_token_repository import GreekVerseTokens
    from bible_engine.tagnt_parser import GreekToken

    def token(
        chapter: int,
        verse: int,
        word_index: int,
        greek_form: str,
        lemma: str,
        morph_code: str,
        strong_id: str,
    ) -> GreekToken:
        return GreekToken(
            book="Jhn",
            chapter=chapter,
            verse=verse,
            word_index=word_index,
            greek_form=greek_form,
            lemma=lemma,
            morph_code=morph_code,
            strong_id=strong_id,
            edition_flags="NKO",
        )

    def passage_tokens() -> list[GreekVerseTokens]:
        return [
            GreekVerseTokens(
                book="Jhn",
                chapter=3,
                verse=16,
                tokens=(
                    token(3, 16, 1, "οὕτως", "οὕτω, οὕτως", "ADV", "G3779"),
                    token(3, 16, 2, "γὰρ", "γάρ", "CONJ", "G1063"),
                ),
            ),
            GreekVerseTokens(
                book="Jhn",
                chapter=3,
                verse=17,
                tokens=(
                    token(3, 17, 1, "οὐ", "οὐ", "PRT-N", "G3756"),
                    token(3, 17, 2, "γὰρ", "γάρ", "CONJ", "G1063"),
                ),
            ),
            GreekVerseTokens(
                book="Jhn",
                chapter=3,
                verse=18,
                tokens=(token(3, 18, 1, "ὁ", "ὁ", "T-NSM", "G3588"),),
            ),
        ]

    render_greek_analysis_block(
        reference="Jn 3,16-18",
        key_prefix="test_greek",
        token_loader=passage_tokens,
        tbesg_lexicon_loader=lambda _strong_id: None,
    )


def _render_first_corinthians_13_1_3_block() -> None:
    import sys
    from pathlib import Path

    from bible_engine.greek_analysis_ui import render_greek_analysis_block

    tests_dir = Path.cwd() / "tests"
    if str(tests_dir) not in sys.path:
        sys.path.insert(0, str(tests_dir))
    from test_greek_analysis_ui import _first_corinthians_13_1_3_tokens

    render_greek_analysis_block(
        reference="1Kor 13,1-3",
        key_prefix="test_greek",
        token_loader=_first_corinthians_13_1_3_tokens,
        lexicon_loader=lambda: {},
        tbesg_lexicon_loader=lambda _strong_id: None,
    )


def _render_romans_8_1_2_block() -> None:
    import sys
    from pathlib import Path

    from bible_engine.greek_analysis_ui import render_greek_analysis_block

    tests_dir = Path.cwd() / "tests"
    if str(tests_dir) not in sys.path:
        sys.path.insert(0, str(tests_dir))
    from test_greek_analysis_ui import _romans_8_1_2_tokens

    render_greek_analysis_block(
        reference="Róm 8,1-2",
        key_prefix="test_greek",
        token_loader=_romans_8_1_2_tokens,
        lexicon_loader=lambda: {},
        tbesg_lexicon_loader=lambda _strong_id: None,
    )


def _render_cross_chapter_john_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block

    render_greek_analysis_block(reference="Jn 3,16-4,2", key_prefix="test_greek")


def _render_other_new_testament_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block
    from bible_engine.greek_token_repository import GreekVerseTokens
    from bible_engine.tagnt_parser import GreekToken

    def token(
        book: str,
        chapter: int,
        verse: int,
        word_index: int,
        greek_form: str,
        lemma: str,
        morph_code: str,
        strong_id: str,
    ) -> GreekToken:
        return GreekToken(
            book=book,
            chapter=chapter,
            verse=verse,
            word_index=word_index,
            greek_form=greek_form,
            lemma=lemma,
            morph_code=morph_code,
            strong_id=strong_id,
            edition_flags="NKO",
        )

    render_greek_analysis_block(
        reference="Róm 8,1",
        key_prefix="test_greek",
        token_loader=lambda: [
            GreekVerseTokens(
                book="Rom",
                chapter=8,
                verse=1,
                tokens=(token("Rom", 8, 1, 1, "Οὐδὲν", "οὐδείς", "A-NSN", "G3762"),),
            )
        ],
        tbesg_lexicon_loader=lambda _strong_id: None,
    )


def _render_old_testament_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block

    render_greek_analysis_block(reference="Zsolt 23,1", key_prefix="test_greek")


def _render_old_testament_compact_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block

    render_greek_analysis_block(
        reference="Zsolt 23,1",
        key_prefix="test_hebrew_compact",
        display_mode="compact",
    )


def _render_unknown_old_testament_like_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block

    render_greek_analysis_block(reference="Ismeretlen 1,1", key_prefix="test_greek")


def _render_missing_old_testament_passage_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block

    render_greek_analysis_block(reference="Mal 99,1", key_prefix="test_greek")


def _render_invalid_reference_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block

    render_greek_analysis_block(reference="nem igehely", key_prefix="test_greek")


def _render_token_load_failure_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block

    def fail_tokens():
        raise OSError("missing fixture")

    render_greek_analysis_block(
        reference="Jn 3,16",
        key_prefix="test_greek",
        token_loader=fail_tokens,
        tbesg_lexicon_loader=lambda _strong_id: None,
    )


def _render_reference_switch_block() -> None:
    import streamlit as st
    from bible_engine.greek_analysis_ui import render_greek_analysis_block
    from bible_engine.greek_token_repository import GreekVerseTokens
    from bible_engine.tagnt_parser import GreekToken

    reference = st.session_state.get("active_reference", "Jn 3,16")

    def token(
        book: str,
        chapter: int,
        verse: int,
        word_index: int,
        greek_form: str,
        lemma: str,
        morph_code: str,
        strong_id: str,
    ) -> GreekToken:
        return GreekToken(
            book=book,
            chapter=chapter,
            verse=verse,
            word_index=word_index,
            greek_form=greek_form,
            lemma=lemma,
            morph_code=morph_code,
            strong_id=strong_id,
            edition_flags="NKO",
        )

    def passage_tokens() -> list[GreekVerseTokens]:
        if reference.startswith("Róm"):
            return [
                GreekVerseTokens(
                    book="Rom",
                    chapter=8,
                    verse=1,
                    tokens=(
                        token("Rom", 8, 1, 1, "Οὐδὲν", "οὐδείς", "A-NSN", "G3762"),
                        token("Rom", 8, 1, 2, "ἄρα", "ἄρα", "PRT", "G0686"),
                    ),
                )
            ]
        return [
            GreekVerseTokens(
                book="Jhn",
                chapter=3,
                verse=16,
                tokens=(
                    token("Jhn", 3, 16, 1, "οὕτως", "οὕτω, οὕτως", "ADV", "G3779"),
                    token("Jhn", 3, 16, 2, "γὰρ", "γάρ", "CONJ", "G1063"),
                ),
            )
        ]

    render_greek_analysis_block(
        reference=reference,
        key_prefix="test_greek",
        token_loader=passage_tokens,
        tbesg_lexicon_loader=lambda _strong_id: None,
    )


def _render_english_tbesg_fallback_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block
    from bible_engine.greek_token_repository import GreekVerseTokens
    from bible_engine.tagnt_parser import GreekToken
    from bible_engine.tbesg_sqlite import SQLiteGreekLexiconEntry

    token = GreekToken(
        book="Rom",
        chapter=8,
        verse=1,
        word_index=1,
        greek_form="Οὐδὲν",
        lemma="οὐδείς",
        morph_code="A-NSN",
        strong_id="G3762",
        edition_flags="NKO",
    )
    entry = SQLiteGreekLexiconEntry(
        strong_id="G3762",
        dstrong_id="G3762 =",
        ustrong_id="G3762",
        lemma="οὐδείς",
        transliteration="oudeis",
        morph="G:A",
        gloss="no one, nothing",
        meaning_raw="<b>οὐδείς</b>, no one, nothing",
        meaning_plain="οὐδείς, no one, none, nothing; used as a negative substantive.",
        meaning_paragraphs=("οὐδείς, no one, none, nothing; used as a negative substantive.",),
        references=("Rom.8.1",),
        source_name="STEPBible TBESG",
        source_version="test",
    )

    render_greek_analysis_block(
        reference="Róm 8,1",
        key_prefix="test_greek",
        token_loader=lambda: [
            GreekVerseTokens(book="Rom", chapter=8, verse=1, tokens=(token,))
        ],
        lexicon_loader=lambda: {},
        tbesg_lexicon_loader=lambda _strong_id: entry,
    )


def _render_missing_tbesg_database_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block
    from bible_engine.greek_lexicon_repository import TBESGDatabaseUnavailableError
    from bible_engine.greek_token_repository import GreekVerseTokens
    from bible_engine.tagnt_parser import GreekToken

    token = GreekToken(
        book="Rom",
        chapter=8,
        verse=1,
        word_index=1,
        greek_form="Οὐδὲν",
        lemma="οὐδείς",
        morph_code="A-NSN",
        strong_id="G3762",
        edition_flags="NKO",
    )

    def missing(_strong_id: str):
        raise TBESGDatabaseUnavailableError("missing test DB")

    render_greek_analysis_block(
        reference="Róm 8,1",
        key_prefix="test_greek",
        token_loader=lambda: [
            GreekVerseTokens(book="Rom", chapter=8, verse=1, tokens=(token,))
        ],
        lexicon_loader=lambda: {},
        tbesg_lexicon_loader=missing,
    )


def _render_no_lexicon_data_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block
    from bible_engine.greek_token_repository import GreekVerseTokens
    from bible_engine.tagnt_parser import GreekToken

    token = GreekToken(
        book="Rom",
        chapter=8,
        verse=1,
        word_index=1,
        greek_form="Οὐδὲν",
        lemma="οὐδείς",
        morph_code="A-NSN",
        strong_id="G3762",
        edition_flags="NKO",
    )

    render_greek_analysis_block(
        reference="Róm 8,1",
        key_prefix="test_greek",
        token_loader=lambda: [
            GreekVerseTokens(book="Rom", chapter=8, verse=1, tokens=(token,))
        ],
        lexicon_loader=lambda: {},
        tbesg_lexicon_loader=lambda _strong_id: None,
    )


def _render_alias_hungarian_lexicon_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block
    from bible_engine.greek_token_repository import GreekVerseTokens
    from bible_engine.lexicon_hu import HungarianLexiconEntry
    from bible_engine.tagnt_parser import GreekToken

    token = GreekToken(
        book="Mat",
        chapter=1,
        verse=20,
        word_index=6,
        greek_form="ἄγγελος",
        lemma="ἄγγελος",
        morph_code="N-NSM",
        strong_id="G0032G",
        edition_flags="NKO",
    )
    entry = HungarianLexiconEntry(
        strong_id="G0032",
        lemma="ἄγγελος",
        primary_gloss="angyal",
        senses=("angyal", "küldött"),
        note=None,
        source="teszt",
        review_status="draft",
    )

    render_greek_analysis_block(
        reference="Mt 1,20",
        key_prefix="test_greek",
        token_loader=lambda: [
            GreekVerseTokens(book="Mat", chapter=1, verse=20, tokens=(token,))
        ],
        lexicon_loader=lambda: {"G0032": entry},
        tbesg_lexicon_loader=lambda _strong_id: None,
    )


def _render_long_tbesg_meaning_block() -> None:
    from bible_engine.greek_analysis_ui import render_greek_analysis_block
    from bible_engine.greek_token_repository import GreekVerseTokens
    from bible_engine.tagnt_parser import GreekToken
    from bible_engine.tbesg_sqlite import SQLiteGreekLexiconEntry

    token = GreekToken(
        book="Rom",
        chapter=8,
        verse=1,
        word_index=1,
        greek_form="Οὐδὲν",
        lemma="οὐδείς",
        morph_code="A-NSN",
        strong_id="G3762",
        edition_flags="NKO",
    )
    long_meaning = " ".join(
        [
            "A long English lexicon article about the term, preserving readable detail."
            for _ in range(25)
        ]
    )
    entry = SQLiteGreekLexiconEntry(
        strong_id="G3762",
        dstrong_id=None,
        ustrong_id="G3762",
        lemma="οὐδείς",
        transliteration="oudeis",
        morph="G:A",
        gloss="no one, nothing",
        meaning_raw=long_meaning,
        meaning_plain=long_meaning,
        meaning_paragraphs=(long_meaning,),
        references=("Rom.8.1",),
        source_name="STEPBible TBESG",
        source_version="test",
    )

    render_greek_analysis_block(
        reference="Róm 8,1",
        key_prefix="test_greek",
        token_loader=lambda: [
            GreekVerseTokens(book="Rom", chapter=8, verse=1, tokens=(token,))
        ],
        lexicon_loader=lambda: {},
        tbesg_lexicon_loader=lambda _strong_id: entry,
    )


def _render_revelation_22_20_21_block() -> None:
    import sys
    from pathlib import Path

    from bible_engine.greek_analysis_ui import render_greek_analysis_block
    from bible_engine.tbesg_sqlite import SQLiteGreekLexiconEntry

    tests_dir = Path.cwd() / "tests"
    if str(tests_dir) not in sys.path:
        sys.path.insert(0, str(tests_dir))
    from test_greek_analysis_ui import _revelation_22_20_21_tokens

    tbesg_entry = SQLiteGreekLexiconEntry(
        strong_id="G3140",
        dstrong_id="G3140 =",
        ustrong_id="G3140",
        lemma="μαρτυρέω",
        transliteration="martureō",
        morph="G:V",
        gloss="to testify",
        meaning_raw="to testify",
        meaning_plain="μαρτυρέω, to testify, bear witness.",
        meaning_paragraphs=("μαρτυρέω, to testify, bear witness.",),
        references=("Rev.22.20",),
        source_name="STEPBible TBESG",
        source_version="test",
    )

    def lexicon_loader(strong_id: str):
        if strong_id == "G3140":
            return tbesg_entry
        return None

    render_greek_analysis_block(
        reference="Jel 22,20-21",
        key_prefix="test_greek",
        token_loader=_revelation_22_20_21_tokens,
        lexicon_loader=lambda: {},
        tbesg_lexicon_loader=lexicon_loader,
    )


def _first_corinthians_13_1_3_tokens() -> list[GreekVerseTokens]:
    return [
        GreekVerseTokens(
            book="1Co",
            chapter=13,
            verse=1,
            tokens=(
                _token("1Co", 13, 1, 1, "Ἐὰν", "ἐάν", "COND", "G1437"),
                _token("1Co", 13, 1, 2, "ταῖς", "ὁ", "T-DPF", "G3588"),
                _token("1Co", 13, 1, 3, "γλώσσαις", "γλῶσσα", "N-DPF", "G1100"),
                _token("1Co", 13, 1, 4, "λαλῶ", "λαλέω", "V-PAS-1S", "G2980"),
            ),
        ),
        GreekVerseTokens(
            book="1Co",
            chapter=13,
            verse=2,
            tokens=(
                _token("1Co", 13, 2, 1, "καὶ", "καί", "CONJ", "G2532"),
                _token("1Co", 13, 2, 2, "ἐὰν", "ἐάν", "COND", "G1437"),
                _token("1Co", 13, 2, 3, "ἔχω", "ἔχω", "V-PAS-1S", "G2192"),
                _token("1Co", 13, 2, 4, "προφητείαν", "προφητεία", "N-ASF", "G4394"),
            ),
        ),
        GreekVerseTokens(
            book="1Co",
            chapter=13,
            verse=3,
            tokens=(
                _token("1Co", 13, 3, 1, "κἂν", "καί ἐάν", "COND", "G2579"),
                _token("1Co", 13, 3, 2, "ψωμίσω", "ψωμίζω", "V-AAS-1S", "G5595"),
                _token("1Co", 13, 3, 3, "πάντα", "πᾶς", "A-APN", "G3956"),
                _token("1Co", 13, 3, 4, "τὰ", "ὁ", "T-APN", "G3588"),
            ),
        ),
    ]


def _romans_8_1_2_tokens() -> list[GreekVerseTokens]:
    return [
        GreekVerseTokens(
            book="Rom",
            chapter=8,
            verse=1,
            tokens=(
                _token("Rom", 8, 1, 1, "Οὐδὲν", "οὐδείς", "A-NSN", "G3762"),
                _token("Rom", 8, 1, 2, "ἄρα", "ἄρα", "PRT", "G0686"),
                _token("Rom", 8, 1, 3, "νῦν", "νῦν", "ADV", "G3568"),
            ),
        ),
        GreekVerseTokens(
            book="Rom",
            chapter=8,
            verse=2,
            tokens=(
                _token("Rom", 8, 2, 1, "ὁ", "ὁ", "T-NSM", "G3588"),
                _token("Rom", 8, 2, 2, "γὰρ", "γάρ", "CONJ", "G1063"),
                _token("Rom", 8, 2, 3, "νόμος", "νόμος", "N-NSM", "G3551"),
            ),
        ),
    ]


def _revelation_22_20_21_tokens() -> list[GreekVerseTokens]:
    return [
        GreekVerseTokens(
            book="Rev",
            chapter=22,
            verse=20,
            tokens=tuple(
                _token("Rev", 22, 20, index, form, lemma, morph, strong)
                for index, form, lemma, morph, strong in (
                    (1, "Λέγει", "λέγω", "V-PAI-3S", "G3004G"),
                    (2, "ὁ", "ὁ", "T-NSM", "G3588"),
                    (3, "μαρτυρῶν", "μαρτυρέω", "V-PAP-NSM", "G3140"),
                    (4, "ταῦτα·", "οὗτος", "D-APN", "G3778"),
                    (5, "ναὶ", "ναί", "PRT", "G3483"),
                    (6, "ἔρχομαι", "ἔρχομαι", "V-PNI-1S", "G2064"),
                    (7, "ταχύ·", "ταχύ", "ADV", "G5035"),
                    (8, "ἀμήν.", "ἀμήν", "INJ-HEB", "G0281"),
                    (9, "ναί", "ναί", "PRT", "G3483"),
                    (10, "ἔρχου,", "ἔρχομαι", "V-PNM-2S", "G2064"),
                    (11, "κύριε", "κύριος", "N-VSM-T", "G2962G"),
                    (12, "Ἰησοῦ.¶", "Ἰησοῦς", "N-VSM-P", "G2424G"),
                )
            ),
        ),
        GreekVerseTokens(
            book="Rev",
            chapter=22,
            verse=21,
            tokens=tuple(
                _token("Rev", 22, 21, index, form, lemma, morph, strong)
                for index, form, lemma, morph, strong in (
                    (1, "Ἡ", "ὁ", "T-NSF", "G3588"),
                    (2, "χάρις", "χάρις", "N-NSF", "G5485"),
                    (3, "τοῦ", "ὁ", "T-GSM", "G3588"),
                    (4, "κυρίου", "κύριος", "N-GSM-T", "G2962G"),
                    (5, "ημῶν", "ἐγώ", "P-1GP", "G3165"),
                    (6, "Ἰησοῦ", "Ἰησοῦς", "N-GSM-P", "G2424G"),
                    (7, "Χριστοῦ", "Χριστός", "N-GSM-T", "G5547"),
                    (8, "μετὰ", "μετά", "PREP", "G3326"),
                    (9, "πάντων", "πᾶς", "A-GPM", "G3956"),
                    (10, "τῶν", "ὁ", "T-GPM", "G3588"),
                    (11, "ὑμῶν.", "σύ", "P-2GP", "G4771"),
                    (12, "ἀμήν.", "ἀμήν", "INJ-HEB", "G0281"),
                )
            ),
        ),
    ]


def _token(
    book: str,
    chapter: int,
    verse: int,
    word_index: int,
    greek_form: str,
    lemma: str,
    morph_code: str,
    strong_id: str,
) -> GreekToken:
    return GreekToken(
        book=book,
        chapter=chapter,
        verse=verse,
        word_index=word_index,
        greek_form=greek_form,
        lemma=lemma,
        morph_code=morph_code,
        strong_id=strong_id,
        edition_flags="NKO",
    )


def _render_bible_text_editor_with_john_text() -> None:
    import streamlit as st
    from bible_text_ui import render_bible_text_editor

    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["passage_text"] = (
        "16 Mert úgy szerette Isten a világot, hogy egyszülött Fiát adta."
    )
    st.session_state["passage_text_source"] = "szentiras.hu"
    st.session_state["passage_text_source_url"] = "https://szentiras.hu/biblia/ruf/JHN/3"
    render_bible_text_editor()


def test_reference_status_distinguishes_supported_and_unsupported_references() -> None:
    assert greek_reference_status("Jn 3,16") == "loaded"
    assert greek_reference_status("Jn 1,1") == "loaded"
    assert greek_reference_status("Jn 14,6") == "loaded"
    assert greek_reference_status("Jn 3,16-18") == "loaded"
    assert greek_reference_status("Jn 3,16-4,2") == "cross_chapter"
    assert greek_reference_status("János 3,16") == "loaded"
    assert greek_reference_status("Róm 8,1") == "loaded"
    assert greek_reference_status("Mt 5,1-3") == "loaded"
    assert greek_reference_status("Júd 20-21") == "loaded"
    assert greek_reference_status("Zsolt 23,1") == "old_testament"
    assert greek_reference_status("") == "empty"
    assert greek_reference_status("Jn 3") == "needs_verses"
    assert greek_reference_status("Lk 10") == "needs_verses"
    assert greek_reference_status("ApCsel 2") == "needs_verses"
    assert greek_reference_status("nem igehely") == "invalid"


def test_john_3_16_renders_greek_block_and_analysis_panel() -> None:
    app = AppTest.from_function(_render_john_3_16_block).run()

    assert not app.exception
    markdown_values = [markdown.value for markdown in app.markdown]
    caption_values = [caption.value for caption in app.caption]

    assert any("Görög eredeti szöveg" in value for value in markdown_values)
    assert any("Válasszon egy görög szót" in value for value in markdown_values)
    assert app.selectbox[0].value == 1
    assert app.subheader[0].value == "οὕτως"
    assert any("<strong>Szótári alak / alakok:</strong> οὕτω, οὕτως" in value for value in markdown_values)
    assert any("<strong>Nyelvtani alak:</strong> határozószó" in value for value in markdown_values)
    assert any("Alapjelentés:** így" in value for value in markdown_values)
    assert any(LEXICAL_SCOPE_NOTE in value for value in caption_values)


def test_default_greek_display_mode_keeps_full_research_panel() -> None:
    app = AppTest.from_function(_render_john_3_16_block).run()

    assert not app.exception
    page_text = "\n".join(markdown.value for markdown in app.markdown)
    page_text += "\n".join(caption.value for caption in app.caption)
    assert "Magyar lexikai jelentések" in page_text
    assert "Ellenőrzési állapot" in page_text
    assert any("Alternatív szóválasztás" in expander.label for expander in app.expander)
    assert app.selectbox
    assert app.subheader[0].value == "οὕτως"
    assert "textus-greek-compact-card-marker" not in page_text


def test_compact_greek_display_mode_shows_only_essential_word_info() -> None:
    app = AppTest.from_function(_render_john_3_16_compact_block).run()

    assert not app.exception
    page_text = "\n".join(markdown.value for markdown in app.markdown)
    page_text += "\n".join(caption.value for caption in app.caption)
    assert "Görög eredeti szöveg" in page_text
    assert "οὕτως" in page_text
    assert "Morfológia:" in page_text
    assert "határozószó" in page_text
    assert "Alapjelentés:" in page_text
    assert "textus-greek-compact-card-marker" in page_text
    assert "Magyar lexikai jelentések" not in page_text
    assert "Ellenőrzési állapot" not in page_text
    assert "Lehetséges jelentések" not in page_text
    assert LEXICAL_SCOPE_NOTE not in page_text
    assert "Konkordancia" not in page_text
    assert '<div class="textus-greek-analysis-card-marker">' not in page_text
    assert app.selectbox
    assert not app.subheader
    assert not any("Alternatív szóválasztás" in expander.label for expander in app.expander)
    assert not any("Konkordancia" in button.label for button in app.button)


def test_selected_word_analysis_updates_through_fallback_selectbox() -> None:
    app = AppTest.from_function(_render_john_3_16_block).run()

    app.selectbox[0].set_value(3)
    app.run()

    markdown_values = [markdown.value for markdown in app.markdown]
    assert app.subheader[0].value == "ἠγάπησεν"
    assert any("<strong>Strong/STEP:</strong> G0025" in value for value in markdown_values)
    assert any("Alapjelentés:** szeret" in value for value in markdown_values)
    assert any("szeret · megbecsül" in value for value in markdown_values)

    app.selectbox[0].set_value(7)
    app.run()

    markdown_values = [markdown.value for markdown in app.markdown]
    assert app.subheader[0].value == "κόσμον,"
    assert any("<strong>Strong/STEP:</strong> G2889" in value for value in markdown_values)
    assert any("Alapjelentés:** világ" in value for value in markdown_values)


def test_hungarian_lexicon_has_priority_over_english_tbesg_fallback() -> None:
    app = AppTest.from_function(_render_john_3_16_block).run()

    app.selectbox[0].set_value(3)
    app.run()

    page_text = "\n".join(markdown.value for markdown in app.markdown)
    page_text += "\n".join(caption.value for caption in app.caption)
    assert "Magyar lexikai jelentések" in page_text
    assert "Alapjelentés:** szeret" in page_text
    assert "Angol lexikai alapadat" not in page_text
    assert TBESG_SCOPE_NOTE not in page_text


def test_english_tbesg_fallback_renders_when_hungarian_entry_is_missing() -> None:
    app = AppTest.from_function(_render_english_tbesg_fallback_block).run()

    assert not app.exception
    page_text = "\n".join(markdown.value for markdown in app.markdown)
    page_text += "\n".join(caption.value for caption in app.caption)
    assert "Angol lexikai alapadat" in page_text
    assert "**Alapjelentés:** no one, nothing" in page_text
    assert "**Szótári alak:** οὐδείς" in page_text
    assert "**Szófaji jelölés:** G:A" in page_text
    assert "Részletes leírás" in page_text
    assert TBESG_SCOPE_NOTE in page_text
    assert TBESG_SOURCE_NOTE in page_text
    assert "Magyar lexikai jelentések" not in page_text


def test_missing_english_tbesg_database_is_controlled() -> None:
    app = AppTest.from_function(_render_missing_tbesg_database_block).run()

    assert not app.exception
    page_text = "\n".join(markdown.value for markdown in app.markdown)
    page_text += "\n".join(caption.value for caption in app.caption)
    assert TBESG_DATABASE_MISSING_MESSAGE in page_text
    assert "Traceback" not in page_text
    assert app.subheader[0].value == "Οὐδὲν"


def test_no_lexicon_data_message_when_no_hungarian_or_tbesg_entry_exists() -> None:
    app = AppTest.from_function(_render_no_lexicon_data_block).run()

    assert not app.exception
    page_text = "\n".join(markdown.value for markdown in app.markdown)
    assert NO_LEXICON_ENTRY_MESSAGE in page_text


def test_alias_hungarian_lexicon_record_marks_source_and_preserves_token_strong() -> None:
    app = AppTest.from_function(_render_alias_hungarian_lexicon_block).run()

    assert not app.exception
    page_text = "\n".join(markdown.value for markdown in app.markdown)
    page_text += "\n".join(caption.value for caption in app.caption)
    assert app.subheader[0].value == "ἄγγελος"
    assert "<strong>Strong/STEP:</strong> G0032G" in page_text
    assert "Magyar lexikai rekord alias alapján: G0032G → G0032" in page_text
    assert "Alapjelentés:** angyal" in page_text
    assert "Angol lexikai alapadat" not in page_text


def test_long_tbesg_meaning_is_collapsed_behind_expander() -> None:
    app = AppTest.from_function(_render_long_tbesg_meaning_block).run()

    assert not app.exception
    page_text = "\n".join(markdown.value for markdown in app.markdown)
    assert "Részletes leírás" in page_text
    assert len(app.expander) >= 2
    assert any(expander.label == "Részletes angol szócikk" for expander in app.expander)


def test_revelation_22_tokens_all_have_unique_clickable_selection_keys() -> None:
    verse_groups = _revelation_22_20_21_tokens()
    all_tokens = [token for group in verse_groups for token in group.tokens]
    payloads = [
        payload
        for group in verse_groups
        for payload in component_tokens(
            list(group.tokens),
            selected_token_key=f"{group.book}:{group.chapter}:{group.verse}:1",
        )
    ]

    assert len(all_tokens) == 24
    assert len(payloads) == 24
    selection_keys = [payload["selection_key"] for payload in payloads]
    assert len(selection_keys) == len(set(selection_keys))
    assert all(key.startswith("Rev:22:") for key in selection_keys)
    assert [payload["greek_form"] for payload in payloads[:8]] == [
        "Λέγει",
        "ὁ",
        "μαρτυρῶν",
        "ταῦτα·",
        "ναὶ",
        "ἔρχομαι",
        "ταχύ·",
        "ἀμήν.",
    ]


def test_first_corinthians_13_payload_keeps_three_verses_distinct() -> None:
    verse_groups = _first_corinthians_13_1_3_tokens()
    all_tokens = [token for group in verse_groups for token in group.tokens]
    payloads = component_tokens(all_tokens, selected_token_key="1Co:13:2:4")

    assert len(payloads) == 12
    assert {payload["verse"] for payload in payloads} == {1, 2, 3}
    assert {"1Co:13:1:4", "1Co:13:2:4", "1Co:13:3:4"}.issubset(
        {payload["selection_key"] for payload in payloads}
    )
    assert [
        payload["selection_key"]
        for payload in payloads
        if payload["word_index"] == 4
    ] == ["1Co:13:1:4", "1Co:13:2:4", "1Co:13:3:4"]
    assert [payload["selected"] for payload in payloads].count(True) == 1
    assert next(
        payload for payload in payloads if payload["selected"] is True
    )["greek_form"] == "προφητείαν"


def test_first_corinthians_13_selection_survives_rerun_by_token_key() -> None:
    app = AppTest.from_function(_render_first_corinthians_13_1_3_block).run()

    assert not app.exception
    assert app.selectbox[0].value == "1Co:13:1:1"

    for selection_key, greek_form in (
        ("1Co:13:1:4", "λαλῶ"),
        ("1Co:13:2:4", "προφητείαν"),
        ("1Co:13:3:4", "τὰ"),
        ("1Co:13:1:1", "Ἐὰν"),
        ("1Co:13:2:1", "καὶ"),
    ):
        app.selectbox[0].set_value(selection_key)
        app.run()
        assert not app.exception
        assert app.session_state["test_greek_selected_token_key"] == selection_key
        assert app.subheader[0].value == greek_form


def test_john_3_17_component_selection_is_not_plain_word_index() -> None:
    verse_groups = sample_passage_tokens()[:2]
    all_tokens = [token for group in verse_groups for token in group.tokens]

    assert normalize_component_selection_key("Jhn:3:17:2", all_tokens) == "Jhn:3:17:2"
    assert component_state_token_key(
        {"selected_token_key": "Jhn:3:17:2", "selected_word_index": 2},
        all_tokens,
    ) == "Jhn:3:17:2"


def test_romans_8_1_2_second_verse_tokens_do_not_collide_by_word_index() -> None:
    verse_groups = _romans_8_1_2_tokens()
    all_tokens = [token for group in verse_groups for token in group.tokens]
    payloads = component_tokens(all_tokens, selected_token_key="Rom:8:2:2")

    assert [payload["selection_key"] for payload in payloads if payload["word_index"] == 2] == [
        "Rom:8:1:2",
        "Rom:8:2:2",
    ]
    assert [payload["selected"] for payload in payloads].count(True) == 1
    assert next(payload for payload in payloads if payload["selected"])["verse"] == 2

    app = AppTest.from_function(_render_romans_8_1_2_block).run()
    app.selectbox[0].set_value("Rom:8:2:3")
    app.run()

    assert not app.exception
    assert app.session_state["test_greek_selected_token_key"] == "Rom:8:2:3"
    assert app.subheader[0].value == "νόμος"


def test_revelation_22_second_verse_payload_has_independent_clickable_tokens() -> None:
    verse_groups = _revelation_22_20_21_tokens()
    verse_20, verse_21 = verse_groups

    verse_20_payload = component_tokens(list(verse_20.tokens), selected_token_key=None)
    verse_21_payload = component_tokens(list(verse_21.tokens), selected_token_key=None)

    assert len(verse_20_payload) == 12
    assert len(verse_21_payload) == 12
    assert all(payload["book"] == "Rev" for payload in verse_21_payload)
    assert all(payload["chapter"] == 22 for payload in verse_21_payload)
    assert all(payload["verse"] == 21 for payload in verse_21_payload)
    assert all(payload["selection_key"].startswith("Rev:22:20:") for payload in verse_20_payload)
    assert all(payload["selection_key"].startswith("Rev:22:21:") for payload in verse_21_payload)
    assert {payload["word_index"] for payload in verse_20_payload} == {
        payload["word_index"] for payload in verse_21_payload
    }
    assert {
        payload["selection_key"] for payload in verse_20_payload
    }.isdisjoint({payload["selection_key"] for payload in verse_21_payload})
    assert [payload["greek_form"] for payload in verse_21_payload] == [
        "Ἡ",
        "χάρις",
        "τοῦ",
        "κυρίου",
        "ημῶν",
        "Ἰησοῦ",
        "Χριστοῦ",
        "μετὰ",
        "πάντων",
        "τῶν",
        "ὑμῶν.",
        "ἀμήν.",
    ]


def test_revelation_22_tokens_can_be_selected_with_and_without_lexicon_data() -> None:
    app = AppTest.from_function(_render_revelation_22_20_21_block).run()

    assert not app.exception
    assert app.selectbox[0].value == "Rev:22:20:1"
    assert app.subheader[0].value == "Λέγει"

    selectable = {
        "Rev:22:20:1": "Λέγει",
        "Rev:22:20:2": "ὁ",
        "Rev:22:20:3": "μαρτυρῶν",
        "Rev:22:20:4": "ταῦτα·",
        "Rev:22:20:5": "ναὶ",
        "Rev:22:20:6": "ἔρχομαι",
        "Rev:22:20:7": "ταχύ·",
        "Rev:22:20:8": "ἀμήν.",
        "Rev:22:21:2": "χάρις",
        "Rev:22:21:4": "κυρίου",
        "Rev:22:21:6": "Ἰησοῦ",
        "Rev:22:21:7": "Χριστοῦ",
        "Rev:22:21:9": "πάντων",
        "Rev:22:21:11": "ὑμῶν.",
        "Rev:22:21:12": "ἀμήν.",
    }
    for selection_key, greek_form in selectable.items():
        app.selectbox[0].set_value(selection_key)
        app.run()
        assert not app.exception
        assert app.session_state["test_greek_selected_token_key"] == selection_key
        assert app.subheader[0].value == greek_form

    app.selectbox[0].set_value("Rev:22:20:3")
    app.run()
    english_text = "\n".join(markdown.value for markdown in app.markdown)
    assert "Angol lexikai alapadat" in english_text
    assert "**Alapjelentés:** to testify" in english_text

    app.selectbox[0].set_value("Rev:22:20:4")
    app.run()
    no_lexicon_text = "\n".join(markdown.value for markdown in app.markdown)
    assert NO_LEXICON_ENTRY_MESSAGE in no_lexicon_text
    assert app.subheader[0].value == "ταῦτα·"


def test_greek_analysis_ui_text_has_no_mojibake_markers() -> None:
    source = (ROOT / "bible_engine" / "greek_analysis_ui.py").read_text(encoding="utf-8")

    assert "Ã" not in source
    assert "Å" not in source
    assert "Â" not in source


def test_other_new_testament_reference_renders_greek_analysis() -> None:
    app = AppTest.from_function(_render_other_new_testament_block).run()

    assert not app.exception
    assert app.subheader[0].value == "Οὐδὲν"
    assert app.session_state["test_greek_selected_token_key"] == "Rom:8:1:1"
    assert app.selectbox[0].value == 1


def test_multi_verse_john_reference_renders_verse_rows_and_shared_panel() -> None:
    app = AppTest.from_function(_render_multi_verse_john_block).run()

    assert not app.exception
    assert app.subheader[0].value == "οὕτως"
    assert app.session_state["test_greek_selected_token_key"] == "Jhn:3:16:1"
    assert app.session_state["test_greek_selected_word_index"] == 1
    assert app.selectbox[0].value == "Jhn:3:16:1"

    app.selectbox[0].set_value("Jhn:3:17:1")
    app.run()

    assert app.subheader[0].value == "οὐ"
    assert app.session_state["test_greek_selected_token_key"] == "Jhn:3:17:1"
    assert app.session_state["test_greek_selected_word_index"] == 1


def test_cross_chapter_john_reference_shows_controlled_message() -> None:
    app = AppTest.from_function(_render_cross_chapter_john_block).run()

    assert not app.exception
    assert any(CROSS_CHAPTER_GREEK_MESSAGE in caption.value for caption in app.caption)
    assert len(app.selectbox) == 0


def test_default_renderer_does_not_use_fixture_fallback_for_missing_database(
    monkeypatch,
    tmp_path: Path,
) -> None:
    missing_database = tmp_path / "missing.sqlite3"
    monkeypatch.setenv(TAGNT_DATABASE_ENV_VAR, str(missing_database))

    app = AppTest.from_function(_render_john_3_16_default_loader_block).run()

    assert not app.exception
    caption_values = [caption.value for caption in app.caption]
    assert any(MISSING_GREEK_DATABASE_MESSAGE in value for value in caption_values)
    assert any(TAGNT_DATABASE_BUILD_HINT in value for value in caption_values)
    page_text = "\n".join(caption_values)
    assert "A teljes görög Újszövetség helyi adatbázisa még nincs előkészítve." in page_text
    assert (
        "Előkészítés: python scripts/build_tagnt_nt_db.py "
        "--mat-jhn-source ... --act-rev-source ... "
        "--output data/generated/tagnt_nt.sqlite3"
    ) in page_text
    assert "Ã" not in page_text
    assert "Å" not in page_text
    assert "Â" not in page_text
    assert len(app.selectbox) == 0


def test_default_renderer_shows_invalid_database_message(
    monkeypatch,
    tmp_path: Path,
) -> None:
    invalid_database = tmp_path / "invalid.sqlite3"
    invalid_database.write_text("not sqlite", encoding="utf-8")
    monkeypatch.setenv(TAGNT_DATABASE_ENV_VAR, str(invalid_database))

    app = AppTest.from_function(_render_john_3_16_default_loader_block).run()

    assert not app.exception
    caption_values = [caption.value for caption in app.caption]
    assert any(INVALID_GREEK_DATABASE_MESSAGE in value for value in caption_values)
    assert not any(MISSING_GREEK_DATABASE_MESSAGE in value for value in caption_values)
    assert len(app.selectbox) == 0


def test_old_testament_reference_renders_hebrew_panel() -> None:
    app = AppTest.from_function(_render_old_testament_block).run()

    assert not app.exception
    page_text = "\n".join(markdown.value for markdown in app.markdown)
    page_text += "\n".join(caption.value for caption in app.caption)
    assert "H\u00e9ber-ar\u00e1mi eredeti sz\u00f6veg" in page_text
    assert "V\u00e1lasszon egy h\u00e9ber vagy ar\u00e1mi sz\u00f3t" in page_text
    assert OLD_TESTAMENT_MESSAGE not in page_text
    assert app.selectbox


def test_compact_hebrew_display_mode_hides_research_details() -> None:
    app = AppTest.from_function(_render_old_testament_compact_block).run()

    assert not app.exception
    page_text = "\n".join(markdown.value for markdown in app.markdown)
    page_text += "\n".join(caption.value for caption in app.caption)
    assert "Héber-arámi eredeti szöveg" in page_text
    assert "Válasszon egy héber vagy arámi szót" in page_text
    assert "textus-hebrew-compact-card-marker" in page_text
    assert "Technikai morfológiai részletek" not in page_text
    assert "Lexikai adatok" not in page_text
    assert "Ellenőrzési állapot" not in page_text
    assert "Forrás és licenc" not in page_text
    assert "Konkordancia" not in page_text
    assert not any("Alternatív szóválasztás" in expander.label for expander in app.expander)
    assert not any("Technikai morfológiai részletek" in expander.label for expander in app.expander)
    assert not any("Konkordancia" in button.label for button in app.button)
    assert app.selectbox


def test_unknown_old_testament_like_reference_shows_friendly_error() -> None:
    app = AppTest.from_function(_render_unknown_old_testament_like_block).run()

    assert not app.exception
    warning_values = [warning.value for warning in app.warning]
    assert any(
        "Az \u00f3sz\u00f6vets\u00e9gi k\u00f6nyv r\u00f6vid\u00edt\u00e9se nem azonos\u00edthat\u00f3: Ismeretlen"
        in value
        for value in warning_values
    )


def test_missing_old_testament_passage_shows_friendly_error() -> None:
    app = AppTest.from_function(_render_missing_old_testament_passage_block).run()

    assert not app.exception
    warning_values = [warning.value for warning in app.warning]
    assert any(
        "A k\u00e9rt \u00f3sz\u00f6vets\u00e9gi szakasz nem tal\u00e1lhat\u00f3 a helyi TAHOT adatb\u00e1zisban."
        in value
        for value in warning_values
    )
    assert any("Fejleszt\u0151i r\u00e9szletek" in expander.label for expander in app.expander)


def test_invalid_reference_renders_no_greek_block() -> None:
    app = AppTest.from_function(_render_invalid_reference_block).run()

    assert not app.exception
    page_text = "\n".join(markdown.value for markdown in app.markdown)
    page_text += "\n".join(caption.value for caption in app.caption)
    assert "Görög eredeti szöveg" not in page_text
    assert MISSING_GREEK_DATA_MESSAGE not in page_text
    assert OLD_TESTAMENT_MESSAGE not in page_text


def test_key_prefix_separates_session_state_keys() -> None:
    app = AppTest.from_function(_render_john_3_16_block).run()

    assert app.session_state["test_greek_selected_word_index"] == 1
    assert app.session_state["test_greek_fallback_selector"] == 1
    assert "greek_demo_selected_word_index" not in app.session_state
    assert "bible_text_ui_selected_word_index" not in app.session_state


# ---------------------------------------------------------------------------
# RESET 2D-A (2026-08-19): görög = zöld / héber = kék token-kiemelés.
# LOCAL MANUAL QA FIX, Phase A (2026-08-21): a nyers forrásszöveg (az
# ALAP `.hebrew-token`/`.greek-token` szabály) mostantól semleges színű
# (`color: inherit`) — a szín csak az elemzésben kiemelt, KIJELÖLT szóra
# kerül (`[aria-pressed="true"]`), ami a lenti morfológiai kártyát
# vezérli. A token-kattinthatóság, az RTL működés és a font változatlan.
#
# Statikus fájlteszt ÉS aktív renderelési teszt is: az utóbbi a VALÓDI
# render-útvonalat futtatja (`render_greek_analysis_block` -> a nyelv
# szerinti dispatch -> a komponens saját `_component()` segédfüggvénye),
# és a ténylegesen a Streamlit v2 komponensnek átadott `css=` payloadot
# kémleli ki egy `st.components.v2.component` spy-jal — nem egy a
# teszttől független, duplikált CSS-stringet vizsgál.
# ---------------------------------------------------------------------------


def test_greek_raw_token_base_rule_is_neutral_not_hardcoded_green() -> None:
    css_path = ROOT / "components" / "greek_token_selector" / "frontend" / "style.css"
    css = css_path.read_text(encoding="utf-8")
    token_rule_start = css.index(".greek-token {")
    token_rule_end = css.index("}", token_rule_start)
    token_rule = css[token_rule_start:token_rule_end]

    assert "color: inherit" in token_rule
    assert "color: #166534" not in token_rule


def test_greek_selected_token_rule_keeps_accessible_green() -> None:
    css_path = ROOT / "components" / "greek_token_selector" / "frontend" / "style.css"
    css = css_path.read_text(encoding="utf-8")
    selected_start = css.index('.greek-token[aria-pressed="true"] {')
    selected_end = css.index("}", selected_start)
    selected_rule = css[selected_start:selected_end]

    assert "color: #166534" in selected_rule


def test_hebrew_raw_token_base_rule_is_neutral_not_hardcoded_blue() -> None:
    css_path = ROOT / "components" / "hebrew_token_selector" / "frontend" / "style.css"
    css = css_path.read_text(encoding="utf-8")
    token_rule_start = css.index(".hebrew-token {")
    token_rule_end = css.index("}", token_rule_start)
    token_rule = css[token_rule_start:token_rule_end]

    assert "color: inherit" in token_rule
    assert "color: #1e40af" not in token_rule


def test_hebrew_selected_token_rule_keeps_accessible_blue() -> None:
    css_path = ROOT / "components" / "hebrew_token_selector" / "frontend" / "style.css"
    css = css_path.read_text(encoding="utf-8")
    selected_start = css.index('.hebrew-token[aria-pressed="true"] {')
    selected_end = css.index("}", selected_start)
    selected_rule = css[selected_start:selected_end]

    assert "color: #1e40af" in selected_rule


def test_greek_token_selector_delivers_green_css_through_real_render_path(
    monkeypatch,
) -> None:
    """Aktív renderelési bizonyíték: a Jn 3,16 blokk valódi renderelése
    (`_render_john_3_16_block`, ugyanaz a segédfüggvény, amit a többi
    görög teszt is használ) ténylegesen eljut a komponens saját
    `_component()`-jéig, ami a lemezről beolvasott, valódi `style.css`
    tartalmat adja át — ezt kémleljük ki, nem egy külön stringet."""
    import streamlit as st

    captured: dict[str, str] = {}
    real_component_factory = st.components.v2.component

    def spy_component_factory(name, *, html, css, js):
        if name == "greek_token_selector":
            captured["css"] = css
        return real_component_factory(name, html=html, css=css, js=js)

    monkeypatch.setattr(st.components.v2, "component", spy_component_factory)

    app = AppTest.from_function(_render_john_3_16_block).run()

    assert not app.exception
    assert "css" in captured, "a komponens sosem lett meghívva a valódi render során"
    assert ".greek-token {" in captured["css"]
    assert "color: #166534" in captured["css"]


def test_hebrew_token_selector_delivers_blue_css_through_real_render_path(
    monkeypatch,
) -> None:
    """Aktív renderelési bizonyíték a héber útvonalra — a `Zsolt 23,1`
    blokk (`_render_old_testament_block`) a valódi ÓSZ-dispatch-en és a
    héber komponens saját `_component()`-jén keresztül fut."""
    import streamlit as st

    captured: dict[str, str] = {}
    real_component_factory = st.components.v2.component

    def spy_component_factory(name, *, html, css, js):
        if name == "hebrew_token_selector":
            captured["css"] = css
        return real_component_factory(name, html=html, css=css, js=js)

    monkeypatch.setattr(st.components.v2, "component", spy_component_factory)

    app = AppTest.from_function(_render_old_testament_block).run()

    assert not app.exception
    assert "css" in captured, "a komponens sosem lett meghívva a valódi render során"
    assert ".hebrew-token {" in captured["css"]
    assert "color: #1e40af" in captured["css"]


def test_runtime_hungarian_lexicon_uses_full_json_by_default() -> None:
    assert LEXICON_HU_PATH == ROOT / "bible_engine" / "data" / "lexicon_hu.json"


def test_missing_runtime_hungarian_lexicon_returns_none_without_sample_fallback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import bible_engine.greek_analysis_ui as greek_analysis_ui

    missing = tmp_path / "missing_lexicon_hu.json"
    monkeypatch.setattr(greek_analysis_ui, "LEXICON_HU_PATH", missing)
    load_demo_hungarian_lexicon.clear()

    assert load_demo_hungarian_lexicon() is None

    load_demo_hungarian_lexicon.clear()


def test_runtime_hungarian_lexicon_cache_refreshes_after_file_update(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import bible_engine.greek_analysis_ui as greek_analysis_ui

    lexicon_path = tmp_path / "lexicon_hu.json"
    _write_runtime_lexicon(lexicon_path, primary_gloss="első")
    monkeypatch.setattr(greek_analysis_ui, "LEXICON_HU_PATH", lexicon_path)
    load_demo_hungarian_lexicon.clear()

    first = load_demo_hungarian_lexicon()
    assert first["G2316"].primary_gloss == "első"

    _write_runtime_lexicon(lexicon_path, primary_gloss="második")
    current_ns = lexicon_path.stat().st_mtime_ns
    os.utime(lexicon_path, ns=(current_ns + 1_000_000_000, current_ns + 1_000_000_000))

    second = load_demo_hungarian_lexicon()
    assert second["G2316"].primary_gloss == "második"

    load_demo_hungarian_lexicon.clear()


def test_book_switch_resets_selected_token_key() -> None:
    app = AppTest.from_function(_render_reference_switch_block)
    app.session_state["active_reference"] = "Jn 3,16"
    app.run()

    assert not app.exception
    app.selectbox[0].set_value(2)
    app.run()
    assert app.session_state["test_greek_selected_token_key"] == "Jhn:3:16:2"

    app.session_state["active_reference"] = "Róm 8,1"
    app.run()

    assert not app.exception
    assert app.session_state["test_greek_selected_token_key"] == "Rom:8:1:1"
    assert app.subheader[0].value == "Οὐδὲν"


def test_token_loading_failure_is_contained() -> None:
    app = AppTest.from_function(_render_token_load_failure_block).run()

    assert not app.exception
    assert any(GREEK_DATA_ERROR_MESSAGE in caption.value for caption in app.caption)


def test_bible_text_editor_renders_greek_block_after_hungarian_text(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(TAGNT_DATABASE_ENV_VAR, str(_build_john_3_16_database(tmp_path)))

    app = AppTest.from_function(_render_bible_text_editor_with_john_text).run()

    assert not app.exception
    markdown_values = [markdown.value for markdown in app.markdown]
    bible_reader_index = next(
        index for index, value in enumerate(markdown_values) if "bible-reader" in value
    )
    greek_heading_index = next(
        index
        for index, value in enumerate(markdown_values)
        if "Görög eredeti szöveg" in value
    )

    assert bible_reader_index < greek_heading_index
    assert app.subheader[0].value == "οὕτως"
    assert app.session_state["bible_text_ui_selected_word_index"] == 1
    assert "greek_demo_selected_word_index" not in app.session_state


def test_demo_and_bible_text_ui_use_shared_renderer() -> None:
    demo_source = (ROOT / "greek_text_demo.py").read_text(encoding="utf-8")
    bible_text_source = (ROOT / "bible_text_ui.py").read_text(encoding="utf-8")
    hebrew_demo_source = (ROOT / "hebrew_text_demo.py").read_text(encoding="utf-8")
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "render_greek_analysis_block" in demo_source
    assert "render_greek_analysis_block" in bible_text_source
    assert "render_hebrew_original_language_panel" in hebrew_demo_source
    assert "render_greek_analysis_block" in app_source
    assert "from bible_engine.greek_analysis_ui import" in demo_source
    assert "from bible_engine.greek_analysis_ui import render_greek_analysis_block" in bible_text_source


def _build_john_3_16_database(tmp_path: Path) -> Path:
    database = tmp_path / "tagnt_john.sqlite3"
    import_tagnt_book(
        ROOT / "tests" / "fixtures" / "tagnt_jhn_3_16_sample.tsv",
        database,
        "Jhn",
        "fixture",
        "test",
    )
    return database


def _write_runtime_lexicon(path: Path, *, primary_gloss: str) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "strong_id": "G2316",
                    "lemma": "θεός",
                    "primary_gloss": primary_gloss,
                    "senses": [primary_gloss],
                    "note": None,
                    "source": "teszt",
                    "review_status": "draft",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def sample_passage_tokens() -> list[GreekVerseTokens]:
    return [
        GreekVerseTokens(
            book="Jhn",
            chapter=3,
            verse=16,
            tokens=(
                greek_token("Jhn", 3, 16, 1, "οὕτως", "οὕτω, οὕτως", "ADV", "G3779"),
                greek_token("Jhn", 3, 16, 2, "γὰρ", "γάρ", "CONJ", "G1063"),
            ),
        ),
        GreekVerseTokens(
            book="Jhn",
            chapter=3,
            verse=17,
            tokens=(
                greek_token("Jhn", 3, 17, 1, "οὐ", "οὐ", "PRT-N", "G3756"),
                greek_token("Jhn", 3, 17, 2, "γὰρ", "γάρ", "CONJ", "G1063"),
            ),
        ),
        GreekVerseTokens(
            book="Jhn",
            chapter=3,
            verse=18,
            tokens=(greek_token("Jhn", 3, 18, 1, "ὁ", "ὁ", "T-NSM", "G3588"),),
        ),
    ]


def greek_token(
    book: str,
    chapter: int,
    verse: int,
    word_index: int,
    greek_form: str,
    lemma: str,
    morph_code: str,
    strong_id: str,
) -> GreekToken:
    return GreekToken(
        book=book,
        chapter=chapter,
        verse=verse,
        word_index=word_index,
        greek_form=greek_form,
        lemma=lemma,
        morph_code=morph_code,
        strong_id=strong_id,
        edition_flags="NKO",
    )
