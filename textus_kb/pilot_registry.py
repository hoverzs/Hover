"""Minimal multi-passage pilot registry for Knowledge Base retrieval.

Phase 4C: John.4.1-42 and Luke.10.25-37 only. No full-Bible generalization.
"""

from __future__ import annotations

from dataclasses import dataclass

from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.paths import PROJECT_ROOT

from textus_kb.books import BOOKS

# USFM-style book numbers (1–66) aligned with textus_kb.books order.
USFM_BOOK_NUMBERS: dict[str, int] = {
    book.osis_id: index for index, book in enumerate(BOOKS, start=1)
}
BOOK_ID_BY_USFM: dict[int, str] = {
    index: book.osis_id for index, book in enumerate(BOOKS, start=1)
}


@dataclass(frozen=True)
class PilotPassage:
    """Configuration for one end-to-end supported pilot passage."""

    id: str
    canonical: str
    usfm_book_num: int
    org_index_lo: int
    org_index_hi: int
    lexical_seed: tuple[str, ...]
    dictionary_index_refs: frozenset[str]
    dictionary_place_ids: frozenset[str]
    study_notes_path: str
    dictionary_path: str
    acai_json_path: str
    aquifer_study_notes_content_file: str

    @property
    def study_notes_resolved(self):
        return PROJECT_ROOT / self.study_notes_path

    @property
    def dictionary_resolved(self):
        return PROJECT_ROOT / self.dictionary_path

    @property
    def acai_json_resolved(self):
        return PROJECT_ROOT / self.acai_json_path

    def reference(self) -> CanonicalReference:
        return CanonicalReference.parse(self.canonical)


JOHN_4_PILOT = PilotPassage(
    id="john_4_1_42",
    canonical="John.4.1-42",
    usfm_book_num=43,
    org_index_lo=43004001,
    org_index_hi=43004042,
    lexical_seed=(
        "G5204",  # water
        "G5207",  # son
        "G3962",  # father
        "G4352",  # worship
        "G4151",  # spirit
        "G225",  # truth
        "G5117",  # place
        "G1097",  # know
    ),
    dictionary_index_refs=frozenset(
        {
            "samaria",
            "samaritans",
            "mount gerizim",
            "sychar",
            "jacob",
            "jacobs well",
            "galilee",
            "judea judeans",
            "temple",
            "worship",
            "well",
            "water",
        }
    ),
    dictionary_place_ids=frozenset(
        {
            "sychar",
            "samaria_1",
            "samaria_2",
            "galilee_1",
            "judea_1",
            "mount_gerizim",
            "jerusalem",
        }
    ),
    study_notes_path="data/kb/aquifer/john_4_1_42_study_notes.json",
    dictionary_path="data/kb/aquifer/john_4_1_42_bible_dictionary.json",
    acai_json_path="data/kb/acai/john_4_1_42_entities.json",
    aquifer_study_notes_content_file="43.content.json",
)

LUKE_10_PILOT = PilotPassage(
    id="luke_10_25_37",
    canonical="Luke.10.25-37",
    usfm_book_num=42,
    org_index_lo=42010025,
    org_index_hi=42010037,
    lexical_seed=(
        "G4139",  # neighbor
        "G2409",  # priest
        "G3019",  # Levite
        "G4541",  # Samaritan
        "G1653",  # have mercy
        "G3598",  # way / road
        "G2419",  # Jerusalem
        "G2410",  # Jericho
        "G25",  # love
        "G3551",  # law
    ),
    dictionary_index_refs=frozenset(
        {
            "samaritans",
            "samaria",
            "jerusalem",
            "jericho",
            "priests and levites",
            "levites",
            "neighbor",
            "love",
            "parable",
            "travel",
        }
    ),
    dictionary_place_ids=frozenset(
        {
            "jerusalem",
            "jericho",
            "samaria_2",
        }
    ),
    study_notes_path="data/kb/aquifer/luke_10_25_37_study_notes.json",
    dictionary_path="data/kb/aquifer/luke_10_25_37_bible_dictionary.json",
    acai_json_path="data/kb/acai/luke_10_25_37_entities.json",
    aquifer_study_notes_content_file="42.content.json",
)

PILOTS: tuple[PilotPassage, ...] = (JOHN_4_PILOT, LUKE_10_PILOT)
PILOTS_BY_ID: dict[str, PilotPassage] = {pilot.id: pilot for pilot in PILOTS}


def usfm_book_num(book_id: str) -> int | None:
    return USFM_BOOK_NUMBERS.get(book_id)


def book_id_from_usfm(book_num: int) -> str | None:
    return BOOK_ID_BY_USFM.get(book_num)


def org_ref_bounds(reference: CanonicalReference) -> tuple[str, str]:
    book_num = usfm_book_num(reference.book_id)
    if book_num is None:
        raise ValueError(f"No USFM book number for {reference.book_id!r}")
    org_lo = f"{book_num:02d}{reference.start_chapter:03d}{reference.start_verse:03d}"
    org_hi = f"{book_num:02d}{reference.end_chapter:03d}{reference.end_verse:03d}"
    return org_lo, org_hi


def org_ref_to_canonical(org_ref: str) -> str | None:
    if len(org_ref) != 8 or not org_ref.isdigit():
        return None
    book_id = book_id_from_usfm(int(org_ref[:2]))
    if book_id is None:
        return None
    chapter = int(org_ref[2:5])
    verse = int(org_ref[5:8])
    return f"{book_id}.{chapter}.{verse}"


def references_overlap(a: CanonicalReference, b: CanonicalReference) -> bool:
    if a.book_id != b.book_id:
        return False
    if a.end_chapter < b.start_chapter or a.start_chapter > b.end_chapter:
        return False
    if a.start_chapter == a.end_chapter == b.start_chapter == b.end_chapter:
        return not (a.end_verse < b.start_verse or a.start_verse > b.end_verse)
    return True


def find_pilot(reference: str | CanonicalReference) -> PilotPassage | None:
    try:
        ref = (
            reference
            if isinstance(reference, CanonicalReference)
            else CanonicalReference.parse(reference)
        )
    except CanonicalReferenceError:
        return None
    for pilot in PILOTS:
        if references_overlap(ref, pilot.reference()):
            return pilot
    return None


def get_pilot(pilot_id: str) -> PilotPassage:
    try:
        return PILOTS_BY_ID[pilot_id]
    except KeyError as exc:
        raise KeyError(f"Unknown pilot id: {pilot_id!r}") from exc


def resolve_pilot_bundles(reference: str | CanonicalReference) -> dict[str, object] | None:
    """Return bundle paths and ACAI source hints for a registered pilot passage.

    Keys: pilot_id, canonical, study_notes_path, dictionary_path, acai_json_path,
    acai_store (manifest-driven SQLite when configured), study_notes_resolved,
    dictionary_resolved, acai_json_resolved.
    """
    pilot = find_pilot(reference)
    if pilot is None:
        return None
    return {
        "pilot_id": pilot.id,
        "canonical": pilot.canonical,
        "study_notes_path": pilot.study_notes_path,
        "dictionary_path": pilot.dictionary_path,
        "acai_json_path": pilot.acai_json_path,
        "acai_store": "manifest:acai",
        "study_notes_resolved": pilot.study_notes_resolved,
        "dictionary_resolved": pilot.dictionary_resolved,
        "acai_json_resolved": pilot.acai_json_resolved,
    }


def validate_pilot_registry() -> list[str]:
    """Return registry configuration issues (empty when valid)."""
    issues: list[str] = []
    if not PILOTS:
        issues.append("Pilot registry is empty.")
    seen_ids: set[str] = set()
    seen_canonicals: set[str] = set()
    for pilot in PILOTS:
        if not pilot.id:
            issues.append("Pilot entry missing id.")
            continue
        if pilot.id in seen_ids:
            issues.append(f"Duplicate pilot id: {pilot.id!r}")
        seen_ids.add(pilot.id)
        if pilot.canonical in seen_canonicals:
            issues.append(f"Duplicate pilot canonical: {pilot.canonical!r}")
        seen_canonicals.add(pilot.canonical)
        try:
            parsed = pilot.reference().canonical_string()
        except CanonicalReferenceError as exc:
            issues.append(f"Pilot {pilot.id!r} has invalid canonical: {exc}")
            continue
        if parsed != pilot.canonical:
            issues.append(
                f"Pilot {pilot.id!r} canonical {pilot.canonical!r} "
                f"does not match parsed form {parsed!r}."
            )
    return issues


def index_reference_overlaps_pilot(index_start: int, index_end: int, pilot: PilotPassage) -> bool:
    if index_start > pilot.org_index_hi or index_end < pilot.org_index_lo:
        return False
    return int(str(index_start).zfill(8)[:2]) == pilot.usfm_book_num
