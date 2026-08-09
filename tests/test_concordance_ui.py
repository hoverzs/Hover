from __future__ import annotations

from concordance_ui import _strip_html_tags


def test_strip_html_tags_removes_cross_reference_anchor() -> None:
    """A Szentírás.eu API (és a belőle importált helyi RÚF-tár) néhány
    vers szövegébe nyers kereszthivatkozás-HTML-t ágyaz be (pl. Lk 17,3
    elején egy szakaszcím-hivatkozás). Élő tesztelés során ez a Kérdés/
    fogalom mód találatában renderelet-len, nyers HTML-ként jelent meg."""
    raw = "A megbocsátás (<a href='Mt 18,25.21-22'>Mt 18,25.21-22</a>) Vigyázzatok magatokra!"
    assert _strip_html_tags(raw) == "A megbocsátás (Mt 18,25.21-22) Vigyázzatok magatokra!"


def test_strip_html_tags_leaves_plain_text_untouched() -> None:
    plain = "Mert úgy szerette Isten a világot, hogy egyszülött Fiát adta."
    assert _strip_html_tags(plain) == plain


def test_strip_html_tags_handles_empty_and_none() -> None:
    assert _strip_html_tags("") == ""
    assert _strip_html_tags(None) == ""
