"""Explicit pilot place catalog and Antioch disambiguation helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PilotPlaceSpec:
    place_id: str
    name_hu: str
    name_en: str
    openbible_id: str
    modern_country: str
    place_type: str
    region_hu: str | None
    ancient_region: str | None
    card_summary_hu: str
    included_in_pilot: bool = True
    is_primary_demo_place: bool = False
    pleiades_id: str | None = None
    antioch_kind: str | None = None  # "syria" | "pisidia" | None
    modern_name: str | None = None
    search_names_hu: tuple[str, ...] = ()


# Locked hand-curated records: bulk import must not overwrite their dense content.
MANUAL_LOCKED_PLACE_IDS = frozenset({"corinth", "ephesus"})

# Fields that remain under human curation for locked places when already filled.
PROTECTED_CONTENT_FIELDS = frozenset(
    {
        "name_hu",
        "name_en",
        "ancient_names",
        "original_names",
        "transliterations",
        "modern_name",
        "modern_country",
        "place_type",
        "identification_status",
        "confidence_note_hu",
        "latitude",
        "longitude",
        "region_hu",
        "ancient_region",
        "geometry_type",
        "coordinate_source_id",
        "card_summary_hu",
        "card_summary_en",
        "is_primary_demo_place",
        "geography_hu",
        "history_hu",
        "political_context_hu",
        "economic_context_hu",
        "social_context_hu",
        "religious_context_hu",
        "archaeology_hu",
        "biblical_significance_hu",
        "modern_context_hu",
        "exegetical_notes",
        "translation_status",
        "translation_method",
        "translation_model",
        "translated_at",
        "review_status",
        "reviewed_by",
        "reviewed_at",
        "pleiades_id",
    }
)

PILOT_PLACE_SPECS: tuple[PilotPlaceSpec, ...] = (
    PilotPlaceSpec(
        place_id="jerusalem",
        name_hu="Jeruzsálem",
        name_en="Jerusalem",
        openbible_id="a15257a",
        pleiades_id="687928",
        modern_country="Izrael",
        place_type="város, templomi és királyi központ",
        region_hu="Júda / Jeruzsálem",
        ancient_region="Judea",
        modern_name="Jerusalem",
        card_summary_hu=(
            "Jeruzsálem a bibliai elbeszélés központi városa, a Templom és több "
            "újszövetségi esemény helyszíne."
        ),
        is_primary_demo_place=True,
        search_names_hu=("Jeruzsálem",),
    ),
    PilotPlaceSpec(
        place_id="nazareth",
        name_hu="Názáret",
        name_en="Nazareth",
        openbible_id="af5884f",
        modern_country="Izrael",
        place_type="galileai település",
        region_hu="Galilea",
        ancient_region="Galilee",
        modern_name="Nazareth",
        card_summary_hu=(
            "Názáret galileai település, a keresztyén hagyomány szerint Jézus "
            "felnevelkedésének helye."
        ),
        search_names_hu=("Názáret",),
    ),
    PilotPlaceSpec(
        place_id="capernaum",
        name_hu="Kapernaum",
        name_en="Capernaum",
        openbible_id="af2161c",
        pleiades_id="678231",
        modern_country="Izrael",
        place_type="tó menti település",
        region_hu="Galilea, Genezáreti-tó",
        ancient_region="Galilee",
        modern_name="Capernaum / Tell Hum",
        card_summary_hu=(
            "Kapernaum a Genezáreti-tó partján fekvő település, Jézus galileai "
            "szolgálatának egyik fontos helyszíne."
        ),
        search_names_hu=("Kapernaum",),
    ),
    PilotPlaceSpec(
        place_id="corinth",
        name_hu="Korinthus",
        name_en="Corinth",
        openbible_id="a6f437a",
        pleiades_id="570182",
        modern_country="Görögország",
        place_type="ókori görög–római város",
        region_hu="Korinthia, Peloponnészosz",
        ancient_region="Achaia",
        modern_name="Archaia Korinthos",
        card_summary_hu=(
            "Korinthus a Korinthoszi-földszoros melletti jelentős görög–római város, "
            "Pál szolgálatának egyik központja."
        ),
        search_names_hu=("Korinthus",),
    ),
    PilotPlaceSpec(
        place_id="ephesus",
        name_hu="Efezus",
        name_en="Ephesus",
        openbible_id="a5feb15",
        pleiades_id="599612",
        modern_country="Törökország",
        place_type="ókori görög–római város, kikötőváros",
        region_hu="İzmir tartomány, Selçuk",
        ancient_region="Iónia, Asia provincia",
        modern_name="Efes, Selçuk",
        card_summary_hu=(
            "Efezus Kis-Ázsia jelentős görög–római városa és kikötője, Pál "
            "hosszabb szolgálatának helyszíne."
        ),
        search_names_hu=("Efezus",),
    ),
    PilotPlaceSpec(
        place_id="athens",
        name_hu="Athén",
        name_en="Athens",
        openbible_id="a1fe6e7",
        pleiades_id="579885",
        modern_country="Görögország",
        place_type="ókori görög város",
        region_hu="Attika",
        ancient_region="Attica",
        modern_name="Athens",
        card_summary_hu=(
            "Athén ókori görög város; az ApCsel 17 szerint Pál itt hirdette az "
            "evangéliumot az Areopágosznál."
        ),
        search_names_hu=("Athén",),
    ),
    PilotPlaceSpec(
        place_id="philippi",
        name_hu="Filippi",
        name_en="Philippi",
        openbible_id="a49e1d0",
        modern_country="Görögország",
        place_type="római kolónia",
        region_hu="Kelet-Makedónia",
        ancient_region="Macedonia",
        modern_name="Filippoi",
        card_summary_hu=(
            "Filippi makedóniai római kolónia; az ApCsel 16 szerint Pál európai "
            "szolgálatának egyik első állomása."
        ),
        search_names_hu=("Filippi",),
    ),
    PilotPlaceSpec(
        place_id="thessalonica",
        name_hu="Thesszalonika",
        name_en="Thessalonica",
        openbible_id="afa9d8e",
        pleiades_id="491741",
        modern_country="Görögország",
        place_type="ókori város, tartományi központ",
        region_hu="Közép-Makedónia",
        ancient_region="Macedonia",
        modern_name="Thessaloniki",
        card_summary_hu=(
            "Thesszalonika makedóniai város; az ApCsel 17 szerint Pál rövid ideig "
            "itt szolgált, mielőtt Beroiába ment."
        ),
        search_names_hu=("Thesszalonika", "Thesszaloniki"),
    ),
    PilotPlaceSpec(
        place_id="antioch_syria",
        name_hu="Antiókhia",
        name_en="Antioch of Syria",
        openbible_id="ae41ab4",
        pleiades_id="658381",
        modern_country="Törökország",
        place_type="ókori nagyváros, missziói központ",
        region_hu="Hatay, Antakya",
        ancient_region="Syria",
        modern_name="Antakya",
        antioch_kind="syria",
        card_summary_hu=(
            "A szíriai Antiókhia (Orontész menti) az őskeresztyén misszió egyik "
            "fontos központja; nem azonos a pisidiai Antiókhiával."
        ),
        search_names_hu=("Antiókhia", "szíriai Antiókhia", "Antiókhia (Szíria)"),
    ),
    PilotPlaceSpec(
        place_id="rome",
        name_hu="Róma",
        name_en="Rome",
        openbible_id="afc8e7a",
        pleiades_id="423025",
        modern_country="Olaszország",
        place_type="birodalmi főváros",
        region_hu="Lazio",
        ancient_region="Italia",
        modern_name="Rome",
        card_summary_hu=(
            "Róma a Római Birodalom fővárosa; az ApCsel 28 szerint Pál itt töltött "
            "házi őrizetet és hirdette az evangéliumot."
        ),
        search_names_hu=("Róma",),
    ),
    # Known but outside the ten-place pilot display set.
    PilotPlaceSpec(
        place_id="antioch_pisidia",
        name_hu="Antiókhia",
        name_en="Antioch of Pisidia",
        openbible_id="a6c704a",
        pleiades_id="609307",
        modern_country="Törökország",
        place_type="ókori város, római kolónia",
        region_hu="Isparta tartomány",
        ancient_region="Pisidia",
        modern_name="Yalvaç közelében",
        antioch_kind="pisidia",
        included_in_pilot=False,
        card_summary_hu=(
            "A pisidiai Antiókhia külön bibliai hely a szíriai Antiókhiától; "
            "Pál missziói útjain jelenik meg."
        ),
        search_names_hu=("pisidiai Antiókhia", "Antiókhia (Pisidia)"),
    ),
)


def pilot_specs_by_id() -> dict[str, PilotPlaceSpec]:
    return {spec.place_id: spec for spec in PILOT_PLACE_SPECS}


def included_pilot_specs() -> tuple[PilotPlaceSpec, ...]:
    return tuple(spec for spec in PILOT_PLACE_SPECS if spec.included_in_pilot)


def resolve_places_by_hungarian_name(name_hu: str) -> tuple[PilotPlaceSpec, ...]:
    """Resolve Hungarian names without collapsing distinct Antiochs."""
    needle = (name_hu or "").strip().casefold()
    if not needle:
        return ()
    exact = [
        spec
        for spec in PILOT_PLACE_SPECS
        if any(alias.casefold() == needle for alias in ((spec.name_hu,) + spec.search_names_hu))
    ]
    if needle in {"antiókhia", "antiokhia", "antiochia"}:
        # Ambiguous bare name: return both candidates, never a silent single pick.
        return tuple(spec for spec in PILOT_PLACE_SPECS if spec.antioch_kind)
    return tuple(exact)
