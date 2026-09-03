"""JFB source manifest loading + fetch verification tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from textus_kb.importers.jfb_source_fetch import (
    JfbSourceFetchError,
    fetch_source,
    load_source_manifest,
)

DEFAULT_MANIFEST = Path("textus_kb/data/jfb_commentary_source_manifest.json")


def test_default_manifest_loads_66_books() -> None:
    manifest = load_source_manifest(DEFAULT_MANIFEST)
    assert manifest.source.id == "jfb"
    assert manifest.source.url == "https://www.ccel.org/ccel/jamieson/jfb.xml"
    assert len(manifest.books) == 66


def test_manifest_books_are_ordered_and_unique() -> None:
    manifest = load_source_manifest(DEFAULT_MANIFEST)
    orders = [b.order for b in manifest.books]
    assert orders == sorted(orders)
    assert len(set(orders)) == 66
    assert len({b.div2_id for b in manifest.books}) == 66


def test_manifest_covers_both_testaments() -> None:
    manifest = load_source_manifest(DEFAULT_MANIFEST)
    ot = [b for b in manifest.books if b.testament == "OT"]
    nt = [b for b in manifest.books if b.testament == "NT"]
    assert len(ot) == 39
    assert len(nt) == 27


def test_manifest_every_book_has_contributor_attribution() -> None:
    manifest = load_source_manifest(DEFAULT_MANIFEST)
    for book in manifest.books:
        assert book.contributor_raw_name.strip()


def test_manifest_contributor_attribution_matches_known_history() -> None:
    """Sanity check against well-documented history: Jamieson wrote
    Genesis-Esther, Fausset wrote Job-Malachi plus most epistles and
    Revelation, Brown wrote the Gospels/Acts/Romans. This is asserted
    against the manifest's own data (sourced from the real in-text
    attribution), not re-derived — a regression guard."""
    manifest = load_source_manifest(DEFAULT_MANIFEST)
    by_title = {b.title: b.contributor_raw_name for b in manifest.books}
    assert by_title["Genesis"] == "Robert Jamieson"
    assert by_title["Esther"] == "Robert Jamieson"
    assert by_title["Job"] == "A. R. Faussett"
    assert by_title["Malachi"] == "A. R. Faussett"
    assert by_title["Matthew"] == "David Brown"
    assert by_title["Romans"] == "David Brown"
    assert by_title["First Corinthians"] == "A. R. Faussett"
    assert by_title["Revelation"] == "A. R. Faussett"


def test_duplicate_div2_id_rejected(tmp_path: Path) -> None:
    manifest_path = tmp_path / "bad.json"
    manifest_path.write_text(
        """
        {
          "manifest_version": "1",
          "description": "",
          "source": {"id": "jfb", "title": "t", "url": "https://example.test/jfb.xml",
                      "local_path": "data/raw/jfb/jfb.xml", "raw_sha256": "%s"},
          "books": [
            {"order": 1, "div2_id": "x.i", "title": "Genesis", "testament": "OT", "contributor_raw_name": "Robert Jamieson"},
            {"order": 2, "div2_id": "x.i", "title": "Exodus", "testament": "OT", "contributor_raw_name": "Robert Jamieson"}
          ]
        }
        """
        % ("0" * 64),
        encoding="utf-8",
    )
    with pytest.raises(JfbSourceFetchError, match="Duplicate div2_id"):
        load_source_manifest(manifest_path)


def test_duplicate_order_rejected(tmp_path: Path) -> None:
    manifest_path = tmp_path / "bad.json"
    manifest_path.write_text(
        """
        {
          "manifest_version": "1",
          "description": "",
          "source": {"id": "jfb", "title": "t", "url": "https://example.test/jfb.xml",
                      "local_path": "data/raw/jfb/jfb.xml", "raw_sha256": "%s"},
          "books": [
            {"order": 1, "div2_id": "x.i", "title": "Genesis", "testament": "OT", "contributor_raw_name": "Robert Jamieson"},
            {"order": 1, "div2_id": "x.ii", "title": "Exodus", "testament": "OT", "contributor_raw_name": "Robert Jamieson"}
          ]
        }
        """
        % ("0" * 64),
        encoding="utf-8",
    )
    with pytest.raises(JfbSourceFetchError, match="Duplicate order"):
        load_source_manifest(manifest_path)


def test_fetch_source_reuses_existing_matching_file_without_network() -> None:
    manifest = load_source_manifest(DEFAULT_MANIFEST)
    if not manifest.source.local_path.is_file():
        pytest.skip("JFB raw source not fetched locally.")
    result = fetch_source(manifest.source)
    assert result.already_present is True
    assert result.raw_sha256 == manifest.source.raw_sha256


def test_fetch_source_rejects_checksum_mismatch(tmp_path: Path) -> None:
    from textus_kb.importers.jfb_source_fetch import JfbSourceFile

    bad_path = tmp_path / "wrong.xml"
    bad_path.write_text("not the real content", encoding="utf-8")
    source = JfbSourceFile(
        id="jfb",
        title="t",
        url="https://example.test/jfb.xml",
        local_path=bad_path,
        raw_sha256="f" * 64,
    )
    with pytest.raises(JfbSourceFetchError, match="does not match the manifest"):
        fetch_source(source)
