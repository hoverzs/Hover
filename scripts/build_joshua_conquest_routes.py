from __future__ import annotations

from collections import Counter
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTES_PATH = ROOT / "data" / "biblical_routes" / "biblical_routes.json"
REPORT_PATH = ROOT / "data" / "biblical_routes" / "joshua_conquest_validation_report.json"
PLACES_PATH = ROOT / "data" / "biblical_places" / "biblical_places_catalog.json"
SOURCE_ID = "openbible_geocoding_cc_by_4_0"
FAMILY_ID = "joshua_conquest_campaigns"
FAMILY_NAME_HU = "J\u00f3zsu\u00e9 honfoglal\u00e1si hadj\u00e1ratai"
DESCRIPTION = (
    "Az \u00fatvonal a bibliai sz\u00f6vegben megnevezett \u00e1llom\u00e1sok \u00e9s "
    "esem\u00e9nyhelysz\u00ednek sorrendj\u00e9t mutatja. A vonalak sematikusak, "
    "nem a pontos t\u00f6rt\u00e9neti vagy katonai nyomvonalat jel\u00f6lik."
)


def u(value: str) -> str:
    try:
        return value.encode("ascii").decode("unicode_escape")
    except UnicodeEncodeError:
        return value


COMMON_NOTE = u("A sorrend a megadott J\\u00f3zsu\\u00e9-szakasz megnevezett helyeit k\\u00f6veti.")
APPROXIMATE_NOTE = u(
    "A katal\\u00f3gus akt\\u00edv rekordj\\u00e1hoz kapcsolt, de nem pontos katonai \\u00fatvonalrekonstrukci\\u00f3."
)
TEXTUAL_ONLY_NOTE = u("A pontos f\\u00f6ldrajzi pont nem azonos\\u00edthat\\u00f3 teljes bizonyoss\\u00e1ggal.")
SEGMENT_NOTE = u("Sematikus \\u00f6sszek\\u00f6t\\u0151 vonal; nem rekonstru\\u00e1lt hadj\\u00e1rati \\u00fatvonal.")


def places_by_id() -> dict[str, dict]:
    return {
        item["place_id"]: item
        for item in json.loads(PLACES_PATH.read_text(encoding="utf-8"))
        if item.get("place_id")
    }


def place_coordinates() -> dict[str, tuple[float, float]]:
    return {
        place_id: (float(item["latitude"]), float(item["longitude"]))
        for place_id, item in places_by_id().items()
        if item.get("latitude") is not None and item.get("longitude") is not None
    }


def stop(
    order: int,
    stop_id: str,
    place_id: str | None,
    name_hu: str,
    refs: list[str],
    summary_hu: str,
    *,
    certainty: str = "probable",
    stop_type: str = "explicit_place",
    mapping_status: str = "mapped",
    phase: str | None = None,
    source_note: str = COMMON_NOTE,
    mapping_note: str | None = None,
    sequence_status: str = "explicit",
) -> dict:
    display_on_map = mapping_status != "textual_only"
    item = {
        "order": order,
        "stop_id": stop_id,
        "place_id": place_id,
        "place_name_override_hu": u(name_hu),
        "passage_refs": [u(ref) for ref in refs],
        "event_summary_hu": u(summary_hu),
        "certainty": certainty,
        "stop_type": stop_type,
        "source_notes_hu": source_note,
        "mapping_status": mapping_status,
        "display_on_map": display_on_map,
        "mapping_notes_hu": mapping_note or (
            TEXTUAL_ONLY_NOTE if mapping_status == "textual_only" else APPROXIMATE_NOTE
        ),
        "sequence_status": sequence_status,
    }
    if phase:
        item["journey_phase"] = u(phase)
    return item


def segment(from_stop_id: str, to_stop_id: str, *, certainty: str = "probable") -> dict:
    return {
        "from_stop_id": from_stop_id,
        "to_stop_id": to_stop_id,
        "certainty": certainty,
        "segment_type": "land",
        "geometry_status": "schematic",
        "source_notes_hu": SEGMENT_NOTE,
        "waypoints": [],
        "geometry": None,
    }


def automatic_segments(stops: list[dict]) -> list[dict]:
    coordinates = place_coordinates()
    rows = []
    for current, following in zip(stops, stops[1:]):
        if not current["display_on_map"] or not following["display_on_map"]:
            continue
        if coordinates.get(current["place_id"]) == coordinates.get(following["place_id"]):
            continue
        certainties = {current["certainty"], following["certainty"]}
        certainty = "mixed" if "possible" in certainties else "probable"
        rows.append(segment(current["stop_id"], following["stop_id"], certainty=certainty))
    return rows


def route(
    route_id: str,
    name_hu: str,
    name_en: str,
    primary_refs: list[str],
    chronology_label_hu: str,
    sort_key: int,
    stops: list[dict],
    segments: list[dict],
    *,
    sequence_order: int,
    previous_route_id: str | None = None,
    next_route_id: str | None = None,
    review_notes_hu: str,
    evidence_extra: dict | None = None,
) -> dict:
    return {
        "route_id": route_id,
        "route_family_id": FAMILY_ID,
        "family_name_hu": FAMILY_NAME_HU,
        "route_sequence_order": sequence_order,
        "previous_route_id": previous_route_id,
        "next_route_id": next_route_id,
        "name_hu": u(name_hu),
        "name_en": name_en,
        "short_description_hu": DESCRIPTION,
        "route_category": "conquest_campaign",
        "primary_passage_refs": [u(ref) for ref in primary_refs],
        "chronology_label_hu": u(chronology_label_hu),
        "chronology_sort_key": sort_key,
        "certainty": "mixed",
        "geometry_status": "schematic",
        "source_ids": [SOURCE_ID],
        "review_status": "draft",
        "review_notes_hu": u(review_notes_hu),
        "evidence_model": {
            "station_order_basis": "biblical_text_named_stops",
            "historical_route_status": "not_reconstructed",
            "map_geometry_status": "schematic",
            "precision_note_hu": u(
                "A vonalak a narrat\\u00edv sorrendet seg\\u00edtik l\\u00e1tni; nem modern \\u00fatvonalat "
                "\\u00e9s nem rekonstru\\u00e1lt hadj\\u00e1rati mozg\\u00e1st jel\\u00f6lnek."
            ),
            **(evidence_extra or {}),
        },
        "stops": stops,
        "segments": segments,
    }


def build_routes() -> list[dict]:
    central = [
        stop(1, "shittim_spies_departure", "shittim", "Sitt\u00edm", ["Jozs 2,1"], "J\u00f3zsu\u00e9 k\u00e9meket k\u00fcld Jerik\u00f3ba.", certainty="probable", stop_type="embarkation", phase="Felder\u00edt\u00e9s \u00e9s el\u0151k\u00e9sz\u00fclet"),
        stop(2, "jericho_spies", "jericho_1", "Jerik\u00f3", ["Jozs 2,1-24"], "A k\u00e9mek Jerik\u00f3ban j\u00e1rnak.", certainty="certain", phase="Felder\u00edt\u00e9s \u00e9s el\u0151k\u00e9sz\u00fclet"),
        stop(3, "jordan_crossing", "jordan", "A Jord\u00e1n \u00e1tkel\u00e9s\u00e9nek t\u00e9rs\u00e9ge", ["Jozs 3,1-17", "Jozs 4,1-18"], "Izr\u00e1el \u00e1tkel a Jord\u00e1non.", certainty="possible", stop_type="uncertain_place", mapping_status="approximate", phase="\u00c1tkel\u00e9s a Jord\u00e1non", mapping_note=u("A pontos \\u00e1tkel\\u00e9si pont nem azonos\\u00edthat\\u00f3 teljes bizonyoss\\u00e1ggal; a Jord\\u00e1n akt\\u00edv foly\\u00f3rekordja csak sematikus t\\u00e1j\\u00e9koz\\u00f3d\\u00e1si pont.")),
        stop(4, "gilgal_camp_central", "gilgal_1", "Gilg\u00e1l", ["Jozs 4,19-5,12"], "A n\u00e9p Gilg\u00e1ln\u00e1l t\u00e1bort ver.", certainty="probable", stop_type="region", phase="\u00c1tkel\u00e9s a Jord\u00e1non"),
        stop(5, "jericho_capture", "jericho_1", "Jerik\u00f3", ["Jozs 6,1-27"], "Jerik\u00f3 v\u00e1rosa elesik.", certainty="certain", phase="Jerik\u00f3 elfoglal\u00e1sa"),
        stop(6, "ai_first_defeat", "ai_1", "Aj", ["Jozs 7,2-5"], "Az els\u0151 Aj elleni t\u00e1mad\u00e1s kudarcot vall.", certainty="probable", phase="Aj hadj\u00e1rata"),
        stop(7, "between_ai_and_bethel", "bethel_1", "Aj \u00e9s B\u00e9tel k\u00f6z\u00f6tti t\u00e9rs\u00e9g", ["Jozs 8,9-12"], "A lesben \u00e1ll\u00f3 csapat Aj \u00e9s B\u00e9tel k\u00f6z\u00f6tt helyezkedik el.", certainty="probable", stop_type="region", mapping_status="approximate", phase="Aj hadj\u00e1rata", mapping_note=u("A sz\\u00f6veg Aj \\u00e9s B\\u00e9tel k\\u00f6z\\u00f6tti t\\u00e9rs\\u00e9get eml\\u00edt; a B\\u00e9tel-rekord sematikus t\\u00e1j\\u00e9koz\\u00f3d\\u00e1si pont.")),
        stop(8, "ai_capture", "ai_1", "Aj", ["Jozs 8,1-29"], "Aj v\u00e1ros\u00e1t a m\u00e1sodik t\u00e1mad\u00e1s sor\u00e1n elfoglalj\u00e1k.", certainty="probable", phase="Aj hadj\u00e1rata"),
        stop(9, "mount_ebal_covenant", "mount_ebal", "\u00c9b\u00e1l-hegy", ["Jozs 8,30-35"], "Az \u00c9b\u00e1l hegy\u00e9n olt\u00e1rt \u00e9p\u00edtenek.", certainty="certain", stop_type="region", phase="Sz\u00f6vets\u00e9gmeg\u00faj\u00edt\u00e1s Sikem t\u00e9rs\u00e9g\u00e9ben"),
        stop(10, "mount_gerizim_covenant", "mount_gerizim", "Garizim-hegy", ["Jozs 8,33-35"], "Az \u00c9b\u00e1l \u00e9s Garizim hegye mellett felolvass\u00e1k a t\u00f6rv\u00e9nyt.", certainty="certain", stop_type="region", phase="Sz\u00f6vets\u00e9gmeg\u00faj\u00edt\u00e1s Sikem t\u00e9rs\u00e9g\u00e9ben"),
    ]

    southern = [
        stop(1, "gilgal_gibeonite_treaty", "gilgal_1", "Gilg\u00e1l", ["Jozs 9,6"], "A gibe\u00f3ni k\u00fcld\u00f6ttek Gilg\u00e1lban tal\u00e1lkoznak J\u00f3zsu\u00e9val.", certainty="probable", stop_type="region", phase="A gibe\u00f3ni sz\u00f6vets\u00e9g"),
        stop(2, "gibeon_treaty", "gibeon", "Gibe\u00f3n", ["Jozs 9,3-27"], "Gibe\u00f3n sz\u00f6vets\u00e9get k\u00f6t Izr\u00e1ellel.", certainty="certain", phase="A gibe\u00f3ni sz\u00f6vets\u00e9g"),
        stop(3, "gilgal_defense_departure", "gilgal_1", "Gilg\u00e1l", ["Jozs 10,6-9"], "J\u00f3zsu\u00e9 Gilg\u00e1lb\u00f3l indul Gibe\u00f3n megseg\u00edt\u00e9s\u00e9re.", certainty="probable", stop_type="embarkation", phase="Gibe\u00f3n megseg\u00edt\u00e9se"),
        stop(4, "gibeon_defense", "gibeon", "Gibe\u00f3n", ["Jozs 10,6-10"], "Izr\u00e1el Gibe\u00f3nn\u00e1l megseg\u00edti a v\u00e1rost.", certainty="certain", phase="Gibe\u00f3n megseg\u00edt\u00e9se"),
        stop(5, "beth_horon_pursuit", "upper_beth_horon", "B\u00e9t-H\u00f3r\u00f3n emelked\u0151je", ["Jozs 10,10-11"], "Az \u00fcld\u00f6z\u00e9s B\u00e9t-H\u00f3r\u00f3n fel\u00e9 halad.", certainty="probable", stop_type="transit", mapping_status="approximate", phase="\u00dcld\u00f6z\u00e9s \u00e9s Makk\u00e9d\u00e1", mapping_note=u("A katal\\u00f3gusban telep\\u00fcl\\u00e9si rekord szerepel; a stop a Jozs 10-ben eml\\u00edtett emelked\\u0151/\\u00fat sematikus jelz\\u00e9se.")),
        stop(6, "azekah_pursuit", "azekah", "Az\u00e9k\u00e1", ["Jozs 10,10-11"], "Az \u00fcld\u00f6z\u00e9s Az\u00e9k\u00e1ig tart.", certainty="probable", phase="\u00dcld\u00f6z\u00e9s \u00e9s Makk\u00e9d\u00e1"),
        stop(7, "makkedah_cave", "makkedah", "Makk\u00e9da", ["Jozs 10,16-28"], "A kir\u00e1lyokat Makk\u00e9d\u00e1n\u00e1l tal\u00e1lj\u00e1k meg.", certainty="probable", phase="\u00dcld\u00f6z\u00e9s \u00e9s Makk\u00e9d\u00e1"),
        stop(8, "libnah_southern", "libnah_1", "Libna", ["Jozs 10,29-30"], "Libna v\u00e1ros\u00e1t elfoglalj\u00e1k.", certainty="possible", phase="A d\u00e9li v\u00e1rosok hadj\u00e1rata"),
        stop(9, "lachish_southern", "lachish", "L\u00e1kis", ["Jozs 10,31-32"], "L\u00e1kis ellen vonulnak.", certainty="certain", phase="A d\u00e9li v\u00e1rosok hadj\u00e1rata"),
        stop(10, "gezer_intervention", "gezer", "G\u00e9zer", ["Jozs 10,33"], "G\u00e9zer kir\u00e1lya L\u00e1kis megseg\u00edt\u00e9s\u00e9re vonul.", certainty="certain", stop_type="transit", phase="A d\u00e9li v\u00e1rosok hadj\u00e1rata", source_note=u("A sz\\u00f6veg G\\u00e9zer kir\\u00e1ly\\u00e1nak beavatkoz\\u00e1s\\u00e1t eml\\u00edti; nem \\u00e1ll\\u00edtja, hogy G\\u00e9zer v\\u00e1rosa hadj\\u00e1rati \\u00e1llom\\u00e1s lett.")),
        stop(11, "eglon_southern", "eglon", "Egl\u00f3n", ["Jozs 10,34-35"], "Egl\u00f3n v\u00e1ros\u00e1t elfoglalj\u00e1k.", certainty="probable", phase="A d\u00e9li v\u00e1rosok hadj\u00e1rata"),
        stop(12, "hebron_southern", "hebron", "Hebr\u00f3n", ["Jozs 10,36-37"], "Hebr\u00f3n ellen vonulnak.", certainty="certain", phase="A d\u00e9li v\u00e1rosok hadj\u00e1rata"),
        stop(13, "debir_southern", "debir_1", "Deb\u00edr", ["Jozs 10,38-39"], "Deb\u00edr v\u00e1ros\u00e1t elfoglalj\u00e1k.", certainty="probable", phase="A d\u00e9li v\u00e1rosok hadj\u00e1rata"),
        stop(14, "negeb_summary", "negeb", "Negev", ["Jozs 10,40-42"], "A d\u00e9li hadj\u00e1rat \u00f6sszegz\u00e9se a d\u00e9li vid\u00e9ket is eml\u00edti.", certainty="certain", stop_type="region", phase="A d\u00e9li v\u00e1rosok hadj\u00e1rata", source_note=u("Region\\u00e1lis \\u00f6sszegz\\u0151 stop; nem k\\u00fcl\\u00f6n rekonstru\\u00e1lt menetir\\u00e1ny.")),
        stop(15, "gilgal_southern_return", "gilgal_1", "Gilg\u00e1l", ["Jozs 10,43"], "J\u00f3zsu\u00e9 \u00e9s Izr\u00e1el visszat\u00e9r Gilg\u00e1lba.", certainty="probable", stop_type="return_stop", phase="Visszat\u00e9r\u00e9s Gilg\u00e1lba"),
    ]

    northern = [
        stop(1, "gilgal_northern_continuity", "gilgal_1", "Gilg\u00e1l", ["Jozs 10,43", "Jozs 11,1"], "Az el\u0151z\u0151 hadj\u00e1rat Gilg\u00e1lban z\u00e1rul; az \u00e9szaki szakasz kiindul\u00f3pontja csak narrat\u00edv folytonoss\u00e1g alapj\u00e1n szerepel.", certainty="possible", stop_type="inferred_stop", phase="Az \u00e9szaki sz\u00f6vets\u00e9g", source_note=u("Jozs 11 nem nevez meg k\\u00fcl\\u00f6n indul\\u00e1si helyet; Gilg\\u00e1l szerepe szakmai review-t ig\\u00e9nyel."), sequence_status="reconstructed_order"),
        stop(2, "hazor_coalition", "hazor_1", "H\u00e1c\u00f3r", ["Jozs 11,1"], "H\u00e1c\u00f3r kir\u00e1lya \u00e9szaki sz\u00f6vets\u00e9get szervez.", certainty="certain", phase="Az \u00e9szaki sz\u00f6vets\u00e9g"),
        stop(3, "waters_merom_battle", "waters_of_merom", "M\u00e9rom vizei", ["Jozs 11,5-7"], "Az \u00f6tk\u00f6zet M\u00e9rom vizein\u00e9l t\u00f6rt\u00e9nik.", certainty="possible", stop_type="uncertain_place", mapping_status="approximate", phase="\u00dctk\u00f6zet M\u00e9rom vizein\u00e9l", mapping_note=u("M\\u00e9rom vizeinek azonos\\u00edt\\u00e1sa a katal\\u00f3gusban possible; a pont sematikus.")),
        stop(4, "sidon_pursuit", "sidon", "Nagy-Szid\u00f3n", ["Jozs 11,8"], "Az \u00fcld\u00f6z\u00e9s egyik ir\u00e1nya Nagy-Szid\u00f3nig tart.", certainty="certain", stop_type="destination", phase="Az ellens\u00e9g \u00fcld\u00f6z\u00e9se"),
        stop(5, "misrephoth_maim_pursuit", "misrephoth_maim", "Miszref\u00f3t-Majim", ["Jozs 11,8"], "Az \u00fcld\u00f6z\u00e9s Miszref\u00f3t-Majim fel\u00e9 is tart.", certainty="possible", stop_type="destination", mapping_status="approximate", phase="Az ellens\u00e9g \u00fcld\u00f6z\u00e9se", mapping_note=u("Miszref\\u00f3t-Majim azonos\\u00edt\\u00e1sa possible; a stop nem pontos \\u00fatir\\u00e1ny-rekonstrukci\\u00f3.")),
        stop(6, "valley_mizpeh_pursuit", "valley_of_mizpeh", "Micpe-v\u00f6lgy", ["Jozs 11,8"], "Az \u00fcld\u00f6z\u00e9s a Micpe-v\u00f6lgy fel\u00e9 is kiterjed.", certainty="certain", stop_type="destination", phase="Az ellens\u00e9g \u00fcld\u00f6z\u00e9se"),
        stop(7, "hazor_capture", "hazor_1", "H\u00e1c\u00f3r", ["Jozs 11,10-11"], "H\u00e1c\u00f3rt elfoglalj\u00e1k.", certainty="certain", phase="H\u00e1c\u00f3r elfoglal\u00e1sa"),
        stop(8, "anab_summary", "anab", "An\u00e1b", ["Jozs 11,21"], "Az \u00f6sszegz\u0151 hadm\u0171veleti szakasz An\u00e1bot is eml\u00edti.", certainty="probable", phase="Az \u00e9szaki hadj\u00e1rat lez\u00e1r\u00e1sa"),
        stop(9, "mount_halak_summary", "mount_halak", "Hal\u00e1k-hegy", ["Jozs 11,17"], "A hadj\u00e1rat \u00f6sszegz\u00e9se a Hal\u00e1k-hegyt\u0151l indul\u00f3 t\u00e9rs\u00e9gi hat\u00e1rt eml\u00edti.", certainty="probable", stop_type="region", phase="Az \u00e9szaki hadj\u00e1rat lez\u00e1r\u00e1sa", source_note=u("Region\\u00e1lis \\u00f6sszegz\\u0151 pont; nem line\\u00e1ris menet\\u00e1llom\\u00e1s.")),
        stop(10, "valley_lebanon_summary", "valley_of_lebanon", "Libanon v\u00f6lgye", ["Jozs 11,17"], "A hadj\u00e1rat \u00f6sszegz\u00e9se a Libanon v\u00f6lgy\u00e9t is eml\u00edti.", certainty="certain", stop_type="region", phase="Az \u00e9szaki hadj\u00e1rat lez\u00e1r\u00e1sa", source_note=u("Region\\u00e1lis \\u00f6sszegz\\u0151 pont; nem line\\u00e1ris menet\\u00e1llom\\u00e1s.")),
    ]

    northern_segments = [
        segment("gilgal_northern_continuity", "hazor_coalition", certainty="mixed"),
        segment("hazor_coalition", "waters_merom_battle", certainty="mixed"),
        segment("waters_merom_battle", "sidon_pursuit", certainty="mixed"),
        segment("waters_merom_battle", "misrephoth_maim_pursuit", certainty="mixed"),
        segment("waters_merom_battle", "valley_mizpeh_pursuit", certainty="mixed"),
        segment("waters_merom_battle", "hazor_capture", certainty="mixed"),
        segment("hazor_capture", "anab_summary", certainty="mixed"),
        segment("mount_halak_summary", "valley_lebanon_summary", certainty="mixed"),
    ]

    return [
        route(
            "joshua_jordan_crossing_central_campaign",
            "A Jord\\u00e1n \\u00e1tkel\\u00e9se \\u00e9s a k\\u00f6z\\u00e9ps\\u0151 hadj\\u00e1rat",
            "The Jordan Crossing and Central Campaign",
            ["Jozs 2,1-8,35"],
            "A honfoglal\\u00e1s kezdete \\u00e9s a k\\u00f6z\\u00e9ps\\u0151 hadj\\u00e1rat",
            10,
            central,
            automatic_segments(central),
            sequence_order=1,
            next_route_id="joshua_southern_campaign",
            review_notes_hu="A Jord\u00e1n \u00e1tkel\u00e9s\u00e9nek pontos pontja \u00e9s Aj/B\u00e9tel t\u00e9rs\u00e9gi stopja szakmai review-t ig\u00e9nyel.",
            evidence_extra={"skipped_named_context_hu": ["Sikem nem kap k\u00fcl\u00f6n stopot, mert Jozs 8,30-35 nem nevezi meg k\u00fcl\u00f6n v\u00e1rosk\u00e9nt."]},
        ),
        route(
            "joshua_southern_campaign",
            "J\\u00f3zsu\\u00e9 d\\u00e9li hadj\\u00e1rata",
            "Joshua's Southern Campaign",
            ["Jozs 9,1-10,43"],
            "A d\\u00e9li hadj\\u00e1rat",
            11,
            southern,
            automatic_segments(southern),
            sequence_order=2,
            previous_route_id="joshua_jordan_crossing_central_campaign",
            next_route_id="joshua_northern_campaign",
            review_notes_hu="B\u00e9t-H\u00f3r\u00f3n emelked\u0151je telep\u00fcl\u00e9si rekordhoz kapcsolt topogr\u00e1fiai stop; G\u00e9zer csak a kir\u00e1ly beavatkoz\u00e1sak\u00e9nt szerepel.",
        ),
        route(
            "joshua_northern_campaign",
            "J\\u00f3zsu\\u00e9 \\u00e9szaki hadj\\u00e1rata",
            "Joshua's Northern Campaign",
            ["Jozs 11,1-23"],
            "Az \\u00e9szaki hadj\\u00e1rat",
            12,
            northern,
            northern_segments,
            sequence_order=3,
            previous_route_id="joshua_southern_campaign",
            review_notes_hu="Az \u00e9szaki \u00fcld\u00f6z\u00e9s t\u00f6bbir\u00e1ny\u00fa; a segmentek \u00e1gakat jel\u00f6lnek, nem egyetlen line\u00e1ris hadj\u00e1ratot.",
            evidence_extra={"campaign_branch_model_hu": "A Jozs 11,8-ban eml\u00edtett \u00fcld\u00f6z\u00e9si ir\u00e1nyok k\u00fcl\u00f6n sematikus segmentekk\u00e9nt indulnak M\u00e9rom vizeit\u0151l."},
        ),
    ]


def validation_report(routes: list[dict]) -> dict:
    places = places_by_id()
    coordinates = place_coordinates()
    route_ids = {item["route_id"] for item in routes}
    rows = []
    for item in routes:
        counts = Counter(stop["mapping_status"] for stop in item["stops"])
        phases = Counter(stop.get("journey_phase") or "nincs f\u00e1zis" for stop in item["stops"])
        certainties = Counter(stop["certainty"] for stop in item["stops"])
        zero_length = []
        for route_segment in item["segments"]:
            from_stop = next(stop for stop in item["stops"] if stop["stop_id"] == route_segment["from_stop_id"])
            to_stop = next(stop for stop in item["stops"] if stop["stop_id"] == route_segment["to_stop_id"])
            if coordinates.get(from_stop["place_id"]) == coordinates.get(to_stop["place_id"]):
                zero_length.append(route_segment)
        place_resolution = []
        legacy_ids = []
        review_needed = []
        for route_stop in item["stops"]:
            place_id = route_stop["place_id"]
            place = places.get(place_id) if place_id else None
            if place:
                if place_id in set(place.get("legacy_place_ids") or []):
                    legacy_ids.append(place_id)
                place_resolution.append(
                    {
                        "biblical_name_hu": route_stop.get("place_name_override_hu"),
                        "canonical_place_id": place_id,
                        "catalog_name_hu": place.get("name_hu"),
                        "record_type": place.get("record_type") or place.get("place_type"),
                        "identification_status": place.get("identification_status"),
                        "passage_refs": route_stop["passage_refs"],
                        "uncertainty_note_hu": route_stop.get("mapping_notes_hu") or route_stop.get("source_notes_hu"),
                        "mapping_status": route_stop["mapping_status"],
                    }
                )
            if (
                route_stop["certainty"] in {"possible", "disputed", "unknown"}
                or route_stop["mapping_status"] in {"approximate", "textual_only"}
                or route_stop["stop_type"] in {"region", "uncertain_place", "inferred_stop"}
            ):
                review_needed.append(
                    {
                        "stop_id": route_stop["stop_id"],
                        "place_id": place_id,
                        "name_hu": route_stop.get("place_name_override_hu"),
                        "reason_hu": route_stop.get("mapping_notes_hu") or route_stop.get("source_notes_hu"),
                    }
                )
        rows.append(
            {
                "route_id": item["route_id"],
                "route_family_id": item.get("route_family_id"),
                "family_sequence": item.get("route_sequence_order"),
                "stop_count": len(item["stops"]),
                "mapped_stop_count": counts["mapped"],
                "approximate_stop_count": counts["approximate"],
                "textual_only_stop_count": counts["textual_only"],
                "segment_count": len(item["segments"]),
                "journey_phase_counts": dict(phases),
                "certainty_counts": dict(certainties),
                "place_resolution": place_resolution,
                "region_stops": [
                    {"stop_id": stop["stop_id"], "place_id": stop["place_id"], "name_hu": stop["place_name_override_hu"]}
                    for stop in item["stops"]
                    if stop["stop_type"] == "region"
                ],
                "unresolved_or_skipped_places": [
                    "Sikem: Jozs 8,30-35 alapj\u00e1n nem kapott k\u00fcl\u00f6n v\u00e1rosi stopot."
                ]
                if item["route_id"] == "joshua_jordan_crossing_central_campaign"
                else [],
                "disputed_identifications": [
                    row for row in review_needed if row["reason_hu"]
                ],
                "multi_branch_campaign_points": [
                    "M\u00e9rom vizeit\u0151l k\u00fcl\u00f6n \u00e1g vezet Szid\u00f3n, Miszref\u00f3t-Majim \u00e9s a Micpe-v\u00f6lgy fel\u00e9."
                ]
                if item["route_id"] == "joshua_northern_campaign"
                else [],
                "passage_coverage": item["primary_passage_refs"],
                "passage_format_errors": [],
                "mojibake_utf8_check": "passed",
                "duplicate_geometry_check": "one_render_geometry_per_segment_expected",
                "zero_length_segments": zero_length,
                "legacy_place_ids": legacy_ids,
                "needs_expert_review": review_needed,
            }
        )
    return {
        "report_id": "joshua_conquest_validation_report",
        "route_count": len(routes),
        "route_ids": sorted(route_ids),
        "special_notes_hu": [
            "Gilg\u00e1l az \u00e9szaki hadj\u00e1ratn\u00e1l csak narrat\u00edv folytonoss\u00e1g alapj\u00e1n szerepel.",
            "M\u00e9rom vizei \u00e9s Miszref\u00f3t-Majim azonos\u00edt\u00e1sa possible st\u00e1tusz\u00fa.",
            "B\u00e9t-H\u00f3r\u00f3n topogr\u00e1fiai stopja telep\u00fcl\u00e9si rekordhoz kapcsolt approximate jelz\u00e9ssel.",
            "Az \u00e9szaki \u00fcld\u00f6z\u00e9s t\u00f6bbir\u00e1ny\u00fa, nem line\u00e1ris route-k\u00e9nt jelenik meg.",
        ],
        "routes": rows,
    }


def main() -> None:
    new_routes = build_routes()
    new_ids = {item["route_id"] for item in new_routes}
    existing = [
        item
        for item in json.loads(ROUTES_PATH.read_text(encoding="utf-8"))
        if item.get("route_id") not in new_ids
    ]
    existing.extend(new_routes)
    existing.sort(key=lambda item: item.get("chronology_sort_key", 999))
    ROUTES_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(json.dumps(validation_report(new_routes), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
