"""Matthew Henry source manifest loading + fetch verification tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from textus_kb.importers.henry_source_fetch import (
    HenrySourceFetchError,
    HenryVolumeFile,
    fetch_volume,
    load_source_manifest,
)

DEFAULT_MANIFEST = Path("textus_kb/data/henry_commentary_source_manifest.json")


def test_default_manifest_loads_6_volumes_66_books() -> None:
    manifest = load_source_manifest(DEFAULT_MANIFEST)
    assert len(manifest.volumes) == 6
    assert len(manifest.books) == 66


def test_volumes_ordered_and_urls_pinned() -> None:
    manifest = load_source_manifest(DEFAULT_MANIFEST)
    numbers = [v.volume for v in manifest.volumes]
    assert numbers == [1, 2, 3, 4, 5, 6]
    for v in manifest.volumes:
        assert v.url == f"https://www.ccel.org/ccel/henry/mhc{v.volume}.xml"
        assert len(v.raw_sha256) == 64


def test_books_are_ordered_and_volume_scoped_unique() -> None:
    manifest = load_source_manifest(DEFAULT_MANIFEST)
    orders = [b.order for b in manifest.books]
    assert orders == sorted(orders)
    assert len(set(orders)) == 66
    keys = {(b.volume, b.div1_id) for b in manifest.books}
    assert len(keys) == 66


def test_ez_div1_id_means_different_books_in_different_volumes() -> None:
    """Real corpus finding: div1 id 'Ez' is Ezra in volume 2 and Ezekiel
    in volume 4 — ids are only unique within their own volume file."""
    manifest = load_source_manifest(DEFAULT_MANIFEST)
    matches = [b for b in manifest.books if b.div1_id == "Ez"]
    assert len(matches) == 2
    titles = {b.title for b in matches}
    assert titles == {"Ezra", "Ezekiel"}
    volumes = {b.volume for b in matches}
    assert volumes == {2, 4}


def test_44_books_by_henry_22_by_named_continuators() -> None:
    manifest = load_source_manifest(DEFAULT_MANIFEST)
    henry = [b for b in manifest.books if b.contributor_raw_name == "Matthew Henry"]
    others = [b for b in manifest.books if b.contributor_raw_name != "Matthew Henry"]
    assert len(henry) == 44
    assert len(others) == 22


def test_acts_is_henry_not_a_continuator() -> None:
    """Real corpus finding (Volume V's own preface footnote): Acts was
    originally part of Henry's own Matthew-Acts manuscript, just moved
    into the Volume VI file for CCEL's pagination split — it must not be
    attributed to a posthumous continuator."""
    manifest = load_source_manifest(DEFAULT_MANIFEST)
    acts = next(b for b in manifest.books if b.title == "Acts")
    assert acts.contributor_raw_name == "Matthew Henry"
    assert acts.authorship_note == ""


def test_romans_onward_have_named_continuators_and_authorship_note() -> None:
    """Real corpus finding (Volume VI's preface table of contributors):
    each book from Romans through Revelation names a specific continuing
    minister, never Matthew Henry."""
    manifest = load_source_manifest(DEFAULT_MANIFEST)
    by_title = {b.title: b for b in manifest.books}
    assert by_title["Romans"].contributor_raw_name == "Mr. John Evans"
    assert by_title["Revelation"].contributor_raw_name == "Mr. William Tong"
    assert by_title["Hebrews"].contributor_raw_name == "Mr. William Tong"
    assert by_title["First John"].contributor_raw_name == "Mr. John Reynolds"
    assert by_title["Second John"].contributor_raw_name == "Mr. John Reynolds"
    assert by_title["Third John"].contributor_raw_name == "Mr. John Reynolds"
    for title in ("Romans", "Revelation", "Hebrews"):
        assert by_title[title].authorship_note.strip()
        assert "Matthew Henry" in by_title[title].authorship_note


def test_five_known_empty_commentary_div_exceptions() -> None:
    """Real corpus finding: all 5 one-chapter books of the Bible (and no
    others) share an identical upstream CCEL markup artifact."""
    manifest = load_source_manifest(DEFAULT_MANIFEST)
    flagged = [b for b in manifest.books if b.known_empty_commentary_divs]
    assert {b.title for b in flagged} == {
        "Obadiah",
        "Philemon",
        "Second John",
        "Third John",
        "Jude",
    }
    for b in flagged:
        assert len(b.known_empty_commentary_divs) == 1
        exc = b.known_empty_commentary_divs[0]
        assert exc.classification == "duplicate_empty_marker"
        assert exc.reason.strip()


def test_fetch_volume_reuses_existing_matching_file_without_network() -> None:
    manifest = load_source_manifest(DEFAULT_MANIFEST)
    for volume in manifest.volumes:
        if not volume.local_path.is_file():
            pytest.skip("Henry raw volumes not fetched locally.")
        result = fetch_volume(volume)
        assert result.already_present is True
        assert result.raw_sha256 == volume.raw_sha256


def test_fetch_volume_rejects_checksum_mismatch(tmp_path: Path) -> None:
    bad_path = tmp_path / "wrong.xml"
    bad_path.write_text("not the real content", encoding="utf-8")
    volume = HenryVolumeFile(
        volume=1,
        title="t",
        url="https://example.test/mhc1.xml",
        local_path=bad_path,
        raw_sha256="f" * 64,
    )
    with pytest.raises(HenrySourceFetchError, match="does not match the manifest"):
        fetch_volume(volume)


def test_duplicate_volume_number_rejected(tmp_path: Path) -> None:
    manifest_path = tmp_path / "bad.json"
    manifest_path.write_text(
        """
        {
          "manifest_version": "1",
          "volumes": [
            {"volume": 1, "title": "t", "url": "https://example.test/mhc1.xml",
             "local_path": "data/raw/henry/mhc1.xml", "raw_sha256": "%s"},
            {"volume": 1, "title": "t2", "url": "https://example.test/mhc1b.xml",
             "local_path": "data/raw/henry/mhc1b.xml", "raw_sha256": "%s"}
          ],
          "books": []
        }
        """
        % ("0" * 64, "1" * 64),
        encoding="utf-8",
    )
    with pytest.raises(HenrySourceFetchError, match="Duplicate volume"):
        load_source_manifest(manifest_path)
