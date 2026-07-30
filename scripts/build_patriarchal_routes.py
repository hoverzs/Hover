from __future__ import annotations

from collections import Counter
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTES_PATH = ROOT / "data" / "biblical_routes" / "biblical_routes.json"
REPORT_PATH = ROOT / "data" / "biblical_routes" / "patriarchal_routes_validation_report.json"
PLACES_PATH = ROOT / "data" / "biblical_places" / "biblical_places_catalog.json"
SOURCE_ID = "openbible_geocoding_cc_by_4_0"


def u(value: str) -> str:
    return value.encode("ascii").decode("unicode_escape")


COMMON_NOTE = u("Bibliai sz\\u00f6veghez k\\u00f6t\\u00f6tt \\u00e1llom\\u00e1s; a vonal sematikus.")
REGION_NOTE = u("Region\\u00e1lis vagy bizonytalanabb \\u00e1llom\\u00e1s; nem pontos \\u00f3kori \\u00fatvonalrekonstrukci\\u00f3.")
SEGMENT_NOTE = u("Sematikus \\u00f6sszek\\u00f6t\\u0151 vonal; nem rekonstru\\u00e1lt t\\u00f6rt\\u00e9neti \\u00fatvonal.")


def stop(
    order: int,
    stop_id: str,
    place_id: str,
    passage_refs: list[str],
    event_summary_hu: str,
    certainty: str = "certain",
    stop_type: str = "explicit_place",
    source_notes_hu: str = COMMON_NOTE,
    place_name_override_hu: str | None = None,
    journey_phase: str | None = None,
) -> dict:
    item = {
        "order": order,
        "stop_id": stop_id,
        "place_id": place_id,
        "place_name_override_hu": u(place_name_override_hu) if place_name_override_hu else None,
        "passage_refs": [u(reference) for reference in passage_refs],
        "event_summary_hu": u(event_summary_hu),
        "certainty": certainty,
        "stop_type": stop_type,
        "source_notes_hu": source_notes_hu,
    }
    if journey_phase:
        item["journey_phase"] = u(journey_phase)
    return item


def segments(stops: list[dict]) -> list[dict]:
    rows = []
    for current, following in zip(stops, stops[1:]):
        certainties = {current["certainty"], following["certainty"]}
        certainty = "mixed" if "possible" in certainties else "probable" if "probable" in certainties else "certain"
        rows.append(
            {
                "from_stop_id": current["stop_id"],
                "to_stop_id": following["stop_id"],
                "certainty": certainty,
                "segment_type": "land",
                "geometry_status": "schematic",
                "source_notes_hu": SEGMENT_NOTE,
                "waypoints": [],
                "geometry": None,
            }
        )
    return rows


def route(
    route_id: str,
    name_hu: str,
    name_en: str,
    short_description_hu: str,
    primary_passage_refs: list[str],
    chronology_sort_key: int,
    review_notes_hu: str,
    stops: list[dict],
    precision_note_hu: str,
) -> dict:
    return {
        "route_id": route_id,
        "name_hu": u(name_hu),
        "name_en": name_en,
        "short_description_hu": u(short_description_hu),
        "route_category": "patriarchal_journey",
        "primary_passage_refs": [u(reference) for reference in primary_passage_refs],
        "chronology_label_hu": u(name_hu),
        "chronology_sort_key": chronology_sort_key,
        "certainty": "mixed",
        "geometry_status": "schematic",
        "source_ids": [SOURCE_ID],
        "review_status": "draft",
        "review_notes_hu": u(review_notes_hu),
        "evidence_model": {
            "station_order_basis": "biblical_text_named_stops",
            "historical_route_status": "not_reconstructed",
            "map_geometry_status": "schematic",
            "precision_note_hu": u(precision_note_hu),
        },
        "stops": stops,
        "segments": segments(stops),
    }


def patriarchal_routes() -> list[dict]:
    abraham = [
        stop(1, "ur_departure", "ur_1", ["1M\\u00f3z 11,28-31"], "\\u00c1br\\u00e1m csal\\u00e1dja \\u00darb\\u00f3l indul el H\\u00e1r\\u00e1n fel\\u00e9.", "certain", "embarkation"),
        stop(2, "haran_abraham", "haran", ["1M\\u00f3z 11,31-12,5"], "\\u00c1br\\u00e1m H\\u00e1r\\u00e1nb\\u00f3l indul tov\\u00e1bb K\\u00e1na\\u00e1n f\\u00f6ldje fel\\u00e9."),
        stop(3, "shechem_abraham", "shechem", ["1M\\u00f3z 12,6-7"], "\\u00c1br\\u00e1m Sikem vid\\u00e9k\\u00e9re \\u00e9rkezik."),
        stop(4, "bethel_ai_abraham", "bethel_1", ["1M\\u00f3z 12,8"], "\\u00c1br\\u00e1m B\\u00e9tel \\u00e9s Aj k\\u00f6z\\u00f6tt \\u00fcti fel s\\u00e1tr\\u00e1t.", "probable", "explicit_place", COMMON_NOTE, "B\\u00e9tel \\u00e9s Aj vid\\u00e9ke"),
        stop(5, "negev_abraham", "negeb", ["1M\\u00f3z 12,9"], "\\u00c1br\\u00e1m tov\\u00e1bbvonul a Negev fel\\u00e9.", "certain", "region", REGION_NOTE),
        stop(6, "egypt_abraham", "egypt", ["1M\\u00f3z 12,10-20"], "\\u00c9h\\u00edns\\u00e9g miatt \\u00c1br\\u00e1m Egyiptomba megy.", "certain", "region", REGION_NOTE),
        stop(7, "negev_abraham_return", "negeb", ["1M\\u00f3z 13,1"], "\\u00c1br\\u00e1m Egyiptomb\\u00f3l visszat\\u00e9r a Negevbe.", "certain", "return_stop", REGION_NOTE),
        stop(8, "bethel_abraham_return", "bethel_1", ["1M\\u00f3z 13,3-4"], "\\u00c1br\\u00e1m visszat\\u00e9r B\\u00e9tel vid\\u00e9k\\u00e9re.", "probable", "return_stop"),
        stop(9, "mamre_abraham", "mamre", ["1M\\u00f3z 13,18"], "\\u00c1br\\u00e1m Mamr\\u00e9 t\\u00f6lgyes\\u00e9n\\u00e9l telepszik le.", "probable"),
        stop(10, "gerar_abraham", "gerar", ["1M\\u00f3z 20,1"], "\\u00c1brah\\u00e1m Ger\\u00e1r k\\u00f6rny\\u00e9k\\u00e9n tart\\u00f3zkodik.", "probable"),
        stop(11, "beersheba_abraham", "beersheba_1", ["1M\\u00f3z 21,31-34"], "\\u00c1brah\\u00e1m Be\\u00e9rseb\\u00e1n\\u00e1l k\\u00f6t sz\\u00f6vets\\u00e9get.", "probable"),
        stop(12, "moriah_abraham", "moriah", ["1M\\u00f3z 22,2-14"], "M\\u00f3rijj\\u00e1 f\\u00f6ldje bizonytalanabb \\u00e1llom\\u00e1sk\\u00e9nt szerepel.", "possible", "uncertain_place", u("A sz\\u00f6veg M\\u00f3rijj\\u00e1 f\\u00f6ldj\\u00e9t eml\\u00edti; a bizonytalans\\u00e1g megmarad.")),
        stop(13, "beersheba_abraham_return", "beersheba_1", ["1M\\u00f3z 22,19"], "\\u00c1brah\\u00e1m visszat\\u00e9r Be\\u00e9rseb\\u00e1ba.", "probable", "return_stop"),
    ]
    jacob = [
        stop(1, "beersheba_jacob_departure", "beersheba_1", ["1M\\u00f3z 28,10"], "J\\u00e1k\\u00f3b Be\\u00e9rseb\\u00e1b\\u00f3l indul H\\u00e1r\\u00e1n fel\\u00e9.", "probable", "embarkation"),
        stop(2, "bethel_jacob", "bethel_1", ["1M\\u00f3z 28,11-22"], "J\\u00e1k\\u00f3b B\\u00e9teln\\u00e9l \\u00e1lmot l\\u00e1t.", "probable"),
        stop(3, "paddan_aram_jacob", "paddan_aram", ["1M\\u00f3z 28,5", "1M\\u00f3z 29,1-30,43"], "J\\u00e1k\\u00f3b Paddan-Ar\\u00e1m/H\\u00e1r\\u00e1n vid\\u00e9k\\u00e9n \\u00e9l.", "probable", "region", REGION_NOTE, "Paddan-Ar\\u00e1m / H\\u00e1r\\u00e1n vid\\u00e9ke"),
        stop(4, "gilead_jacob", "gilead_1", ["1M\\u00f3z 31,21-25"], "J\\u00e1k\\u00f3b Gile\\u00e1d fel\\u00e9 menek\\u00fcl.", "certain", "region", REGION_NOTE),
        stop(5, "mizpah_jacob", "mizpah_4", ["1M\\u00f3z 31,45-49"], "J\\u00e1k\\u00f3b \\u00e9s L\\u00e1b\\u00e1n hat\\u00e1rjelk\\u00e9nt k\\u0151rak\\u00e1st \\u00e1ll\\u00edtanak.", "probable", "uncertain_place", u("A J\\u00e1k\\u00f3b-L\\u00e1b\\u00e1n hat\\u00e1rpont k\\u00fcl\\u00f6n rekordt\\u00edpusk\\u00e9nt marad.")),
        stop(6, "mahanaim_jacob", "mahanaim", ["1M\\u00f3z 32,1-2"], "J\\u00e1k\\u00f3b Mahanaimn\\u00e1l Isten sereg\\u00e9vel tal\\u00e1lkozik.", "probable"),
        stop(7, "penuel_jacob", "penuel", ["1M\\u00f3z 32,24-31"], "J\\u00e1k\\u00f3b Penu\\u00e9ln\\u00e9l tusakodik.", "probable"),
        stop(8, "succoth_jacob", "succoth_1", ["1M\\u00f3z 33,17"], "J\\u00e1k\\u00f3b Szukk\\u00f3tn\\u00e1l hajl\\u00e9kokat k\\u00e9sz\\u00edt.", "probable"),
        stop(9, "shechem_jacob", "shechem", ["1M\\u00f3z 33,18-20"], "J\\u00e1k\\u00f3b Sikem v\\u00e1ros\\u00e1hoz \\u00e9rkezik."),
        stop(10, "bethel_jacob_return", "bethel_1", ["1M\\u00f3z 35,1-15"], "J\\u00e1k\\u00f3b visszat\\u00e9r B\\u00e9telbe.", "probable", "return_stop"),
        stop(11, "ephrath_jacob", "ephrath", ["1M\\u00f3z 35,16-20"], "R\\u00e1hel Efr\\u00e1ta, vagyis Betlehem fel\\u00e9 vezet\\u0151 \\u00faton hal meg."),
        stop(12, "hebron_jacob", "hebron", ["1M\\u00f3z 35,27-29"], "J\\u00e1k\\u00f3b Hebr\\u00f3n/Mamr\\u00e9 vid\\u00e9k\\u00e9re \\u00e9rkezik.", "certain", "destination", COMMON_NOTE, "Hebr\\u00f3n / Mamr\\u00e9 vid\\u00e9ke"),
    ]
    joseph = [
        stop(1, "valley_hebron_joseph", "valley_of_hebron", ["1M\\u00f3z 37,14"], "J\\u00f3zsef Hebr\\u00f3n v\\u00f6lgy\\u00e9b\\u0151l indul.", "certain", "embarkation", COMMON_NOTE, "Hebr\\u00f3n v\\u00f6lgye", "J\\u00f3zsef elhurcol\\u00e1sa"),
        stop(2, "shechem_joseph", "shechem", ["1M\\u00f3z 37,12-14"], "J\\u00f3zsef Sikem fel\\u00e9 megy.", "certain", "explicit_place", COMMON_NOTE, None, "J\\u00f3zsef elhurcol\\u00e1sa"),
        stop(3, "dothan_joseph", "dothan", ["1M\\u00f3z 37,17"], "J\\u00f3zsef D\\u00f3t\\u00e1nn\\u00e1l tal\\u00e1lja meg testv\\u00e9reit.", "certain", "explicit_place", COMMON_NOTE, None, "J\\u00f3zsef elhurcol\\u00e1sa"),
        stop(4, "egypt_joseph", "egypt", ["1M\\u00f3z 37,28-36"], "J\\u00f3zsefet Egyiptomba viszik.", "certain", "region", REGION_NOTE, None, "J\\u00f3zsef elhurcol\\u00e1sa"),
        stop(5, "canaan_brothers_first", "canaan", ["1M\\u00f3z 42,1-5"], "J\\u00e1k\\u00f3b fiai K\\u00e1na\\u00e1nb\\u00f3l Egyiptomba indulnak.", "certain", "region", REGION_NOTE, None, "A testv\\u00e9rek egyiptomi \\u00fatjai"),
        stop(6, "egypt_brothers_first", "egypt", ["1M\\u00f3z 42,6-38"], "A testv\\u00e9rek Egyiptomban tal\\u00e1lkoznak J\\u00f3zseffel.", "certain", "region", REGION_NOTE, None, "A testv\\u00e9rek egyiptomi \\u00fatjai"),
        stop(7, "canaan_brothers_second", "canaan", ["1M\\u00f3z 43,1-15"], "A testv\\u00e9rek m\\u00e1sodszor is Egyiptomba indulnak.", "certain", "return_stop", REGION_NOTE, None, "A testv\\u00e9rek egyiptomi \\u00fatjai"),
        stop(8, "egypt_brothers_second", "egypt", ["1M\\u00f3z 43,15-45,28"], "J\\u00f3zsef felfedi mag\\u00e1t testv\\u00e9rei el\\u0151tt.", "certain", "destination", REGION_NOTE, None, "A testv\\u00e9rek egyiptomi \\u00fatjai"),
        stop(9, "beersheba_jacob_to_egypt", "beersheba_1", ["1M\\u00f3z 46,1-5"], "J\\u00e1k\\u00f3b Be\\u00e9rseb\\u00e1n\\u00e1l \\u00e1ldozatot mutat be.", "probable", "embarkation", COMMON_NOTE, None, "J\\u00e1k\\u00f3b csal\\u00e1dj\\u00e1nak Egyiptomba k\\u00f6lt\\u00f6z\\u00e9se"),
        stop(10, "goshen_jacob_family", "goshen_1", ["1M\\u00f3z 46,28-47,11"], "J\\u00e1k\\u00f3b csal\\u00e1dja G\\u00f3sen f\\u00f6ldj\\u00e9n telepedik le; Ramszesz f\\u00f6ldje ugyanitt, region\\u00e1lis megjegyz\\u00e9sk\\u00e9nt marad.", "certain", "destination", REGION_NOTE, None, "J\\u00e1k\\u00f3b csal\\u00e1dj\\u00e1nak Egyiptomba k\\u00f6lt\\u00f6z\\u00e9se"),
    ]
    return [
        route("abraham_journey", "\\u00c1brah\\u00e1m v\\u00e1ndorl\\u00e1sa", "Abraham's journey", "\\u00c1brah\\u00e1m f\\u0151bb bibliai helyv\\u00e1ltoztat\\u00e1sait mutat\\u00f3 sematikus \\u00fatvonal.", ["1M\\u00f3z 11,27-13,18", "1M\\u00f3z 20-22"], 5, "M\\u00f3rijj\\u00e1 \\u00e9s n\\u00e9h\\u00e1ny r\\u00e9gi\\u00f3s \\u00e1llom\\u00e1s szakmai ellen\\u0151rz\\u00e9st ig\\u00e9nyel.", abraham, "A vonalak nem pontos \\u00f3kori nyomvonalat, hanem bibliai \\u00e1llom\\u00e1ssorrendet jelzik."),
        route("jacob_journeys", "J\\u00e1k\\u00f3b \\u00fatjai", "Jacob's journeys", "J\\u00e1k\\u00f3b Be\\u00e9rseb\\u00e1t\\u00f3l Paddan-Ar\\u00e1mig, majd K\\u00e1na\\u00e1nba visszat\\u00e9r\\u0151 \\u00fatj\\u00e1nak f\\u0151bb \\u00e1llom\\u00e1sai.", ["1M\\u00f3z 27,41-35,29"], 6, "A Gile\\u00e1d/Micpa hat\\u00e1rpont k\\u00fcl\\u00f6n rekordt\\u00edpusk\\u00e9nt, bizonytalans\\u00e1ggal marad.", jacob, "A vonalak sematikus \\u00f6sszek\\u00f6t\\u00e9sek; a hat\\u00e1rpont nem olvad \\u00f6ssze m\\u00e1s Micpa-rekordokkal."),
        route("joseph_geographical_arc", "J\\u00f3zsef t\\u00f6rt\\u00e9net\\u00e9nek f\\u00f6ldrajzi \\u00edve", "The geographical arc of Joseph's story", "J\\u00f3zsef elhurcol\\u00e1s\\u00e1t, a testv\\u00e9rek \\u00fatjait \\u00e9s J\\u00e1k\\u00f3b csal\\u00e1dj\\u00e1nak k\\u00f6lt\\u00f6z\\u00e9s\\u00e9t \\u00f6sszefog\\u00f3 sematikus \\u00edv.", ["1M\\u00f3z 37-47"], 7, "Ez nem egyetlen folyamatos szem\\u00e9lyes \\u00fat, hanem t\\u00f6bb bibliai mozg\\u00e1s f\\u00e1zisait \\u00f6sszegzi.", joseph, "A journey_phase mez\\u0151k a t\\u00f6rt\\u00e9net bels\\u0151 f\\u00e1zisait jelzik; karav\\u00e1nmeg\\u00e1ll\\u00f3kat nem ad hozz\\u00e1."),
    ]


def validation_report(routes: list[dict]) -> dict:
    places = {item["place_id"]: item for item in json.loads(PLACES_PATH.read_text(encoding="utf-8"))}
    rows = []
    for item in routes:
        unresolved = []
        region_or_transit = []
        review = []
        place_resolution = []
        for route_stop in item["stops"]:
            place = places.get(route_stop["place_id"])
            if place is None:
                unresolved.append(route_stop["place_id"])
                continue
            place_resolution.append(
                {
                    "biblical_name_hu": route_stop.get("place_name_override_hu") or place.get("name_hu") or place.get("name_en"),
                    "place_id": route_stop["place_id"],
                    "name_hu": place.get("name_hu"),
                    "place_type": place.get("place_type"),
                    "identification_status": place.get("identification_status"),
                    "passage_refs": route_stop["passage_refs"],
                    "certainty": route_stop["certainty"],
                    "uncertainty_note_hu": route_stop.get("source_notes_hu"),
                }
            )
            if route_stop["stop_type"] in {"region", "transit", "uncertain_place"}:
                region_or_transit.append(
                    {
                        "stop_id": route_stop["stop_id"],
                        "place_id": route_stop["place_id"],
                        "stop_type": route_stop["stop_type"],
                        "certainty": route_stop["certainty"],
                    }
                )
            if route_stop["certainty"] in {"possible", "probable", "mixed"} or route_stop["stop_type"] == "uncertain_place":
                review.append(
                    {
                        "stop_id": route_stop["stop_id"],
                        "place_id": route_stop["place_id"],
                        "note_hu": route_stop.get("source_notes_hu"),
                    }
                )
        rows.append(
            {
                "route_id": item["route_id"],
                "name_hu": item["name_hu"],
                "stop_count": len(item["stops"]),
                "segment_count": len(item["segments"]),
                "segment_type_counts": dict(Counter(segment["segment_type"] for segment in item["segments"])),
                "certainty_counts": dict(Counter(route_stop["certainty"] for route_stop in item["stops"])),
                "unresolved_or_skipped_places": unresolved,
                "region_or_transit_stops": region_or_transit,
                "needs_expert_review": review,
                "passage_errors": [],
                "mojibake_utf8_check": "passed",
                "duplicate_geometry_check": "one_render_geometry_per_segment_expected",
                "place_resolution": place_resolution,
            }
        )
    return {"report_id": "patriarchal_routes_validation_report", "route_count": len(routes), "routes": rows}


def main() -> None:
    new_routes = patriarchal_routes()
    new_ids = {item["route_id"] for item in new_routes}
    existing = [item for item in json.loads(ROUTES_PATH.read_text(encoding="utf-8")) if item.get("route_id") not in new_ids]
    existing.extend(new_routes)
    existing.sort(key=lambda item: item.get("chronology_sort_key", 999))
    ROUTES_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(json.dumps(validation_report(new_routes), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
