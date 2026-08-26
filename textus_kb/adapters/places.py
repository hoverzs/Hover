"""Read-only biblical places adapter."""

from __future__ import annotations

from dataclasses import dataclass

from textus_kb.canonical_reference import CanonicalReference
from textus_kb.manifest import ManifestSource


@dataclass(frozen=True)
class PassagePlaceLink:
    place_id: str
    normalized_reference: str
    reason_hu: str
    source_note: str


@dataclass(frozen=True)
class PlaceCatalogEntry:
    place_id: str
    name_hu: str
    name_en: str | None
    latitude: float
    longitude: float
    identification_status: str
    card_summary_hu: str | None


@dataclass(frozen=True)
class PlaceEnrichmentExcerpt:
    place_id: str
    section_key: str
    text_hu: str
    confidence: str
    source_ids: tuple[str, ...]
    review_status: str


class PlacesAdapter:
    CATALOG_SOURCE_ID = "biblical_places_catalog"
    LINKS_SOURCE_ID = "biblical_places_passage_links"
    ENRICHMENT_SOURCE_ID = "place_enrichments_overlay"

    def __init__(
        self,
        catalog_source: ManifestSource | None,
        links_source: ManifestSource | None,
        enrichment_source: ManifestSource | None,
    ) -> None:
        self._catalog_source = catalog_source
        self._links_source = links_source
        self._enrichment_source = enrichment_source

    @property
    def catalog_available(self) -> bool:
        return (
            self._catalog_source is not None
            and self._catalog_source.enabled
            and self._catalog_source.resolved_path.is_file()
        )

    @property
    def links_available(self) -> bool:
        return (
            self._links_source is not None
            and self._links_source.enabled
            and self._links_source.resolved_path.is_file()
        )

    @property
    def enrichment_available(self) -> bool:
        return (
            self._enrichment_source is not None
            and self._enrichment_source.enabled
            and self._enrichment_source.resolved_path.is_file()
        )

    def find_passage_links(self, reference: CanonicalReference) -> list[PassagePlaceLink]:
        if not self.links_available:
            return []

        from biblical_map_passages import find_place_links_for_passage

        display_ref = _reference_display_for_overlap(reference)
        raw_links = find_place_links_for_passage(display_ref)
        return [
            PassagePlaceLink(
                place_id=link.place_id,
                normalized_reference=link.normalized_reference,
                reason_hu=link.reason_hu,
                source_note=link.source_note,
            )
            for link in raw_links
        ]

    def get_catalog_entry(self, place_id: str) -> PlaceCatalogEntry | None:
        if not self.catalog_available:
            return None

        from biblical_map_data import places_by_id

        place = places_by_id().get(place_id)
        if place is None:
            return None
        return PlaceCatalogEntry(
            place_id=place.place_id,
            name_hu=place.name_hu,
            name_en=place.name_en,
            latitude=place.latitude,
            longitude=place.longitude,
            identification_status=place.identification_status,
            card_summary_hu=place.card_summary_hu,
        )

    def get_enrichment_excerpts(
        self,
        place_id: str,
        *,
        max_sections: int = 2,
    ) -> list[PlaceEnrichmentExcerpt]:
        if not self.enrichment_available:
            return []

        from biblical_place_enrichment import get_place_enrichment

        enrichment = get_place_enrichment(place_id)
        if enrichment is None:
            return []

        excerpts: list[PlaceEnrichmentExcerpt] = []
        for section_key in (
            "biblical_significance",
            "key_events",
            "ancient_geography",
            "historical_context",
        ):
            section = enrichment.sections.get(section_key)
            if section is None:
                continue
            if hasattr(section, "text_hu"):
                text = getattr(section, "text_hu", "") or ""
                confidence = getattr(section, "confidence", "medium")
                review_status = getattr(section, "review_status", "needs_review")
                source_ids = tuple(getattr(section, "source_ids", ()) or ())
            elif hasattr(section, "items"):
                items = getattr(section, "items", ()) or ()
                if not items:
                    continue
                summaries = []
                refs: set[str] = set()
                source_ids_set: set[str] = set()
                for item in items[:3]:
                    summaries.append(getattr(item, "summary_hu", ""))
                    for ref in getattr(item, "passage_refs", ()) or ():
                        refs.add(str(ref))
                    source_ids_set.update(getattr(item, "source_ids", ()) or ())
                text = " ".join(s for s in summaries if s)
                if refs:
                    text = f"{text} ({', '.join(sorted(refs)[:5])})"
                confidence = getattr(section, "confidence", "medium")
                review_status = getattr(section, "review_status", "needs_review")
                source_ids = tuple(sorted(source_ids_set))
            else:
                continue

            if not text.strip():
                continue
            if review_status != "source_backed":
                continue
            excerpts.append(
                PlaceEnrichmentExcerpt(
                    place_id=place_id,
                    section_key=section_key,
                    text_hu=text.strip(),
                    confidence=str(confidence),
                    source_ids=source_ids,
                    review_status=str(review_status),
                )
            )
            if len(excerpts) >= max_sections:
                break
        return excerpts


def _reference_display_for_overlap(reference: CanonicalReference) -> str:
    book_code = reference.ruf_book_code
    if reference.is_single_verse:
        return f"{book_code} {reference.start_chapter},{reference.start_verse}"
    if reference.start_chapter == reference.end_chapter:
        return (
            f"{book_code} {reference.start_chapter},"
            f"{reference.start_verse}-{reference.end_verse}"
        )
    return (
        f"{book_code} {reference.start_chapter},{reference.start_verse}-"
        f"{reference.end_chapter},{reference.end_verse}"
    )
