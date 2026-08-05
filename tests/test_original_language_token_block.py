from __future__ import annotations

from app import build_original_language_token_block


def test_greek_passage_returns_real_tokens_not_free_generation() -> None:
    block = build_original_language_token_block("Jn 3:16")

    assert block.startswith("EREDETI NYELVI TOKENEK (helyi adatbázisból, kizárólagos forrás):\n")
    assert "Nincs" not in block.splitlines()[0]
    lines = block.splitlines()[1:]
    assert len(lines) == 26  # Jn 3:16 TAGNT token count

    first = lines[0]
    assert first.startswith("[1] ")
    assert "lemma:" in first
    assert "morf:" in first
    assert "Strong:" in first
    # word_index 3 is ἠγάπησεν / ἀγαπάω, Strong G0025 (already "G"-prefixed
    # in the source data — must appear verbatim, not double-prefixed as "GG0025").
    assert "G0025" in block
    assert "GG0025" not in block


def test_hebrew_passage_returns_real_tokens_not_free_generation() -> None:
    block = build_original_language_token_block("1Móz 1:1")

    assert block.startswith("EREDETI NYELVI TOKENEK (helyi adatbázisból, kizárólagos forrás):\n")
    lines = block.splitlines()[1:]
    assert len(lines) == 7  # Gen 1:1 TAHOT token count

    first = lines[0]
    assert first.startswith("[1] ")
    assert "lemma:" in first
    assert "morf:" in first
    assert "Strong:" in first
    assert "H7225" in block  # רֵאשִׁית -> Strong H7225, must appear verbatim from DB


def test_cross_chapter_reference_yields_explicit_no_data_message_not_generated_content() -> None:
    block = build_original_language_token_block("Jn 3,16-4,2")

    assert block.startswith("EREDETI NYELVI TOKENEK (helyi adatbázisból, kizárólagos forrás):\n")
    body = block.split("\n", 1)[1]
    # Explicit "no data" signal, not a fabricated token list.
    assert "Nincs lekérhető token-adat" in body
    assert "[1]" not in body
    assert "lemma:" not in body
