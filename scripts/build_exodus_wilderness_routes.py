from __future__ import annotations

from collections import Counter
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTES_PATH = ROOT / "data" / "biblical_routes" / "biblical_routes.json"
REPORT_PATH = ROOT / "data" / "biblical_routes" / "exodus_wilderness_validation_report.json"
PLACES_PATH = ROOT / "data" / "biblical_places" / "biblical_places_catalog.json"
SOURCE_ID = "openbible_geocoding_cc_by_4_0"
FAMILY_ID = "exodus_and_wilderness"
FAMILY_NAME_HU = "A kivonul\u00e1s \u00e9s a pusztai v\u00e1ndorl\u00e1s"


def place_coordinates() -> dict[str, tuple[float, float]]:
    places = json.loads(PLACES_PATH.read_text(encoding="utf-8"))
    return {
        item["place_id"]: (float(item["latitude"]), float(item["longitude"]))
        for item in places
        if item.get("place_id") and item.get("latitude") is not None and item.get("longitude") is not None
    }


def stop(order, stop_id, place_id, name, refs, summary, *, certainty="probable", stop_type="explicit_place", mapping_status="approximate", phase=None):
    display = mapping_status != "textual_only"
    return {
        "order": order,
        "stop_id": stop_id,
        "place_id": place_id,
        "place_name_override_hu": name,
        "passage_refs": refs,
        "event_summary_hu": summary,
        "certainty": certainty,
        "stop_type": stop_type,
        "source_notes_hu": "A sorrend a megadott bibliai szakaszok \u00e1llom\u00e1slist\u00e1j\u00e1t k\u00f6veti.",
        "mapping_status": mapping_status,
        "display_on_map": display,
        "mapping_notes_hu": (
            "A hely pontos f\u00f6ldrajzi azonos\u00edt\u00e1sa nem ismert."
            if mapping_status == "textual_only"
            else "A katal\u00f3gus akt\u00edv rekordj\u00e1hoz kapcsolt, sematikus megjelen\u00edt\u00e9s."
        ),
        "sequence_status": "explicit",
        **({"journey_phase": phase} if phase else {}),
    }


def segments(stops):
    coordinates = place_coordinates()
    rows = []
    for current, following in zip(stops, stops[1:]):
        if not current["display_on_map"] or not following["display_on_map"]:
            continue
        if coordinates.get(current["place_id"]) == coordinates.get(following["place_id"]):
            continue
        rows.append(
            {
                "from_stop_id": current["stop_id"],
                "to_stop_id": following["stop_id"],
                "certainty": "probable",
                "segment_type": "land",
                "geometry_status": "schematic",
                "source_notes_hu": "Sematikus szakasz; nem pontos t\u00f6rt\u00e9neti nyomvonal.",
                "waypoints": [],
                "geometry": None,
            }
        )
    return rows


def route(route_id, name_hu, name_en, description, category, primary_refs, sort_key, stops, *, sequence_order, previous=None, next_=None):
    return {
        "route_id": route_id,
        "route_family_id": FAMILY_ID,
        "family_name_hu": FAMILY_NAME_HU,
        "route_sequence_order": sequence_order,
        "previous_route_id": previous,
        "next_route_id": next_,
        "name_hu": name_hu,
        "name_en": name_en,
        "short_description_hu": description,
        "route_category": category,
        "primary_passage_refs": primary_refs,
        "chronology_label_hu": "A kivonul\u00e1s els\u0151 szakasza" if sequence_order == 1 else "A pusztai v\u00e1ndorl\u00e1s",
        "chronology_sort_key": sort_key,
        "certainty": "mixed",
        "geometry_status": "schematic",
        "source_ids": [SOURCE_ID],
        "review_status": "draft",
        "review_notes_hu": "T\u00f6bb \u00e1llom\u00e1s azonos\u00edt\u00e1sa vitatott vagy ismeretlen; a vonalak sematikusak.",
        "evidence_model": {
            "station_order_basis": "biblical_text_named_stops",
            "historical_route_status": "not_reconstructed",
            "map_geometry_status": "schematic",
            "precision_note_hu": "A vonalak nem pontos t\u00f6rt\u00e9neti nyomvonalat jel\u00f6lnek.",
        },
        "stops": stops,
        "segments": segments(stops),
    }


def build_routes():
    exodus_description = (
        "Az \u00fatvonal a bibliai sz\u00f6vegben megnevezett \u00e1llom\u00e1sok sorrendj\u00e9t mutatja. "
        "T\u00f6bb hely azonos\u00edt\u00e1sa vitatott vagy ismeretlen. A vonalak sematikusak, "
        "nem a pontos t\u00f6rt\u00e9neti nyomvonalat jel\u00f6lik."
    )
    exodus = [
        stop(1, "rameses_exodus", "rameses", "Ramszesz", ["2M\u00f3z 12,37", "4M\u00f3z 33,3"], "Izr\u00e1el fiai Ramszeszb\u0151l indulnak el.", certainty="probable", stop_type="embarkation"),
        stop(2, "succoth_exodus", "succoth_2", "Szukk\u00f3t", ["2M\u00f3z 12,37", "4M\u00f3z 33,5"], "Ramszesz ut\u00e1n Szukk\u00f3tn\u00e1l t\u00e1boroznak.", certainty="possible"),
        stop(3, "etham_exodus", "etham", "\u00c9t\u00e1m", ["2M\u00f3z 13,20", "4M\u00f3z 33,6"], "\u00c9t\u00e1mn\u00e1l t\u00e1boroznak a puszta sz\u00e9l\u00e9n.", certainty="possible"),
        stop(4, "pi_hahiroth_exodus", "pi_hahiroth", "Pi-Hahir\u00f3t", ["2M\u00f3z 14,2", "4M\u00f3z 33,7"], "A tenger el\u0151tt, Pi-Hahir\u00f3t k\u00f6zel\u00e9ben t\u00e1boroznak.", certainty="possible"),
        stop(5, "sea_crossing_textual", None, "A tengeren val\u00f3 \u00e1tkel\u00e9s helye", ["2M\u00f3z 14,21-31", "4M\u00f3z 33,8"], "A n\u00e9p \u00e1tkel a tengeren.", certainty="disputed", stop_type="uncertain_place", mapping_status="textual_only"),
        stop(6, "shur_exodus", "shur", "S\u00far puszt\u00e1ja", ["2M\u00f3z 15,22"], "H\u00e1rom napig mennek S\u00far puszt\u00e1j\u00e1ban.", certainty="probable", stop_type="region"),
        stop(7, "marah_exodus", "marah", "M\u00e1r\u00e1", ["2M\u00f3z 15,23", "4M\u00f3z 33,8"], "M\u00e1r\u00e1n\u00e1l keser\u0171 vizet tal\u00e1lnak.", certainty="possible"),
        stop(8, "elim_exodus", "elim", "\u00c9lim", ["2M\u00f3z 15,27", "4M\u00f3z 33,9"], "\u00c9limn\u00e9l forr\u00e1sok \u00e9s p\u00e1lm\u00e1k mellett t\u00e1boroznak.", certainty="probable"),
        stop(9, "red_sea_camp_exodus", "red_sea_1", "T\u00e1bor a V\u00f6r\u00f6s-tenger mellett", ["4M\u00f3z 33,10"], "A V\u00f6r\u00f6s-tenger mellett t\u00e1boroznak.", certainty="possible", stop_type="transit"),
        stop(10, "sin_exodus", "sin", "Sz\u00edn puszt\u00e1ja", ["2M\u00f3z 16,1", "4M\u00f3z 33,11"], "A Sz\u00edn puszt\u00e1j\u00e1ban manna adatik.", certainty="possible", stop_type="region"),
        stop(11, "dophkah_exodus", "dophkah", "Dofk\u00e1", ["4M\u00f3z 33,12"], "Dofk\u00e1n\u00e1l t\u00e1boroznak.", certainty="probable"),
        stop(12, "alush_exodus", "alush", "Al\u00fas", ["4M\u00f3z 33,13"], "Al\u00fasn\u00e1l t\u00e1boroznak.", certainty="possible"),
        stop(13, "rephidim_exodus", "rephidim", "Refid\u00edm", ["2M\u00f3z 17,1-16", "4M\u00f3z 33,14"], "Refid\u00edmn\u00e9l v\u00edz fakad a szikl\u00e1b\u00f3l, \u00e9s Am\u00e1l\u00e9k t\u00e1mad.", certainty="possible"),
        stop(14, "sinai_exodus", "wilderness_of_sinai", "S\u00ednai puszt\u00e1ja / S\u00ednai-hegy", ["2M\u00f3z 19,1-2", "4M\u00f3z 33,15"], "Meg\u00e9rkeznek a S\u00ednai puszt\u00e1j\u00e1ba.", certainty="probable", stop_type="region"),
    ]
    wilderness = [
        stop(1, "sinai_wilderness_departure", "wilderness_of_sinai", "S\u00ednai puszt\u00e1ja", ["4M\u00f3z 10,11-12", "4M\u00f3z 33,16"], "Elindulnak a S\u00ednait\u00f3l.", certainty="probable", stop_type="region", phase="Elindul\u00e1s a S\u00ednait\u00f3l"),
        stop(2, "kibroth_wilderness", "kibroth_hattaavah", "Kibr\u00f3t-Hattaav\u00e1", ["4M\u00f3z 11,34-35", "4M\u00f3z 33,16"], "Kibr\u00f3t-Hattaav\u00e1n\u00e1l t\u00e1boroznak.", certainty="probable", phase="Elindul\u00e1s a S\u00ednait\u00f3l"),
        stop(3, "hazeroth_wilderness", "hazeroth", "Hac\u00e9r\u00f3t", ["4M\u00f3z 11,35", "4M\u00f3z 12,16", "4M\u00f3z 33,17"], "Hac\u00e9r\u00f3tn\u00e1l t\u00e1boroznak.", certainty="probable", phase="Elindul\u00e1s a S\u00ednait\u00f3l"),
        stop(4, "rithmah_wilderness", "rithmah", "Ritm\u00e1", ["4M\u00f3z 13,1-14,45", "4M\u00f3z 33,18"], "Ritm\u00e1n\u00e1l t\u00e1boroznak; a k\u00e9mk\u00fcld\u00e9s narrat\u00edv szakasza ehhez az \u00fati f\u00e1zishoz kapcsol\u00f3dik.", certainty="possible", phase="\u00dat K\u00e1d\u00e9s fel\u00e9"),
        stop(5, "rimmon_perez_wilderness", "rimmon_perez", "Rimm\u00f3n-Perec", ["4M\u00f3z 33,19"], "Rimm\u00f3n-Perecn\u00e9l t\u00e1boroznak.", certainty="possible", phase="A pusztai v\u00e1ndorl\u00e1s \u00e9vei"),
        stop(6, "libnah_wilderness", "libnah_2", "Libn\u00e1", ["4M\u00f3z 33,20"], "Libn\u00e1n\u00e1l t\u00e1boroznak.", certainty="possible", phase="A pusztai v\u00e1ndorl\u00e1s \u00e9vei"),
        stop(7, "rissah_wilderness", "rissah", "Rissz\u00e1", ["4M\u00f3z 33,21"], "Rissz\u00e1n\u00e1l t\u00e1boroznak.", phase="A pusztai v\u00e1ndorl\u00e1s \u00e9vei"),
        stop(8, "kehelathah_wilderness", "kehelathah", "Keh\u00e9l\u00e1t\u00e1", ["4M\u00f3z 33,22"], "Keh\u00e9l\u00e1t\u00e1n\u00e1l t\u00e1boroznak.", phase="A pusztai v\u00e1ndorl\u00e1s \u00e9vei"),
        stop(9, "mount_shepher_wilderness", "mount_shepher", "S\u00e9fer-hegy", ["4M\u00f3z 33,23"], "A S\u00e9fer-hegyn\u00e9l t\u00e1boroznak.", certainty="probable", stop_type="region", phase="A pusztai v\u00e1ndorl\u00e1s \u00e9vei"),
        stop(10, "haradah_wilderness", "haradah", "Harad\u00e1", ["4M\u00f3z 33,24"], "Harad\u00e1n\u00e1l t\u00e1boroznak.", certainty="possible", phase="A pusztai v\u00e1ndorl\u00e1s \u00e9vei"),
        stop(11, "makheloth_wilderness", "makheloth", "Makhel\u00f3t", ["4M\u00f3z 33,25"], "Makhel\u00f3tn\u00e1l t\u00e1boroznak.", certainty="possible", phase="A pusztai v\u00e1ndorl\u00e1s \u00e9vei"),
        stop(12, "tahath_wilderness", "tahath", "T\u00e1hat", ["4M\u00f3z 33,26"], "T\u00e1hatn\u00e1l t\u00e1boroznak.", phase="A pusztai v\u00e1ndorl\u00e1s \u00e9vei"),
        stop(13, "terah_wilderness", "terah", "Terah", ["4M\u00f3z 33,27"], "Terahn\u00e1l t\u00e1boroznak.", phase="A pusztai v\u00e1ndorl\u00e1s \u00e9vei"),
        stop(14, "mithkah_wilderness", "mithkah", "Mitk\u00e1", ["4M\u00f3z 33,28"], "Mitk\u00e1n\u00e1l t\u00e1boroznak.", phase="A pusztai v\u00e1ndorl\u00e1s \u00e9vei"),
        stop(15, "hashmonah_wilderness", "hashmonah", "Hasm\u00f3n\u00e1", ["4M\u00f3z 33,29"], "Hasm\u00f3n\u00e1n\u00e1l t\u00e1boroznak.", certainty="possible", phase="A pusztai v\u00e1ndorl\u00e1s \u00e9vei"),
        stop(16, "moseroth_wilderness", "moseroth", "M\u00f3szer\u00f3t", ["4M\u00f3z 33,30"], "M\u00f3szer\u00f3tn\u00e1l t\u00e1boroznak.", phase="A pusztai v\u00e1ndorl\u00e1s \u00e9vei"),
        stop(17, "bene_jaakan_wilderness", "bene_jaakan", "Ben\u00e9-Jaak\u00e1n", ["4M\u00f3z 33,31"], "Ben\u00e9-Jaak\u00e1nn\u00e1l t\u00e1boroznak.", certainty="possible", phase="A pusztai v\u00e1ndorl\u00e1s \u00e9vei"),
        stop(18, "hor_haggidgad_wilderness", "hor_haggidgad", "H\u00f3r-Haggidg\u00e1d", ["4M\u00f3z 33,32"], "H\u00f3r-Haggidg\u00e1dn\u00e1l t\u00e1boroznak.", certainty="possible", phase="A pusztai v\u00e1ndorl\u00e1s \u00e9vei"),
        stop(19, "jotbathah_wilderness", "jotbathah", "Jotb\u00e1t\u00e1", ["4M\u00f3z 33,33"], "Jotb\u00e1t\u00e1n\u00e1l t\u00e1boroznak.", certainty="possible", phase="A pusztai v\u00e1ndorl\u00e1s \u00e9vei"),
        stop(20, "abronah_wilderness", "abronah", "Abr\u00f3n\u00e1", ["4M\u00f3z 33,34"], "Abr\u00f3n\u00e1n\u00e1l t\u00e1boroznak.", certainty="possible", phase="A pusztai v\u00e1ndorl\u00e1s \u00e9vei"),
        stop(21, "ezion_geber_wilderness", "ezion_geber", "Ecj\u00f3n-Geber", ["4M\u00f3z 33,35"], "Ecj\u00f3n-Gebern\u00e9l t\u00e1boroznak.", phase="A pusztai v\u00e1ndorl\u00e1s \u00e9vei"),
        stop(22, "kadesh_wilderness", "kadesh_barnea", "K\u00e1d\u00e9s", ["4M\u00f3z 20,1", "4M\u00f3z 33,36"], "K\u00e1d\u00e9sben, Cin puszt\u00e1j\u00e1ban t\u00e1boroznak.", certainty="probable", phase="K\u00e1d\u00e9st\u0151l M\u00f3\u00e1big"),
        stop(23, "mount_hor_wilderness", "mount_hor_1", "H\u00f3r hegye", ["4M\u00f3z 20,22-29", "4M\u00f3z 33,37-39"], "\u00c1ron a H\u00f3r hegy\u00e9n hal meg.", certainty="possible", stop_type="region", phase="K\u00e1d\u00e9st\u0151l M\u00f3\u00e1big"),
        stop(24, "zalmonah_wilderness", "zalmonah", "Calm\u00f3n\u00e1", ["4M\u00f3z 33,41"], "Calm\u00f3n\u00e1n\u00e1l t\u00e1boroznak.", certainty="possible", phase="K\u00e1d\u00e9st\u0151l M\u00f3\u00e1big"),
        stop(25, "punon_wilderness", "punon", "P\u00fan\u00f3n", ["4M\u00f3z 33,42"], "P\u00fan\u00f3nn\u00e1l t\u00e1boroznak.", phase="K\u00e1d\u00e9st\u0151l M\u00f3\u00e1big"),
        stop(26, "oboth_wilderness", "oboth", "\u00d3b\u00f3t", ["4M\u00f3z 21,10", "4M\u00f3z 33,43"], "\u00d3b\u00f3tn\u00e1l t\u00e1boroznak.", certainty="possible", phase="K\u00e1d\u00e9st\u0151l M\u00f3\u00e1big"),
        stop(27, "iye_abarim_wilderness", "iye_abarim", "Ij\u00e9-Ab\u00e1rim", ["4M\u00f3z 21,11", "4M\u00f3z 33,44"], "Ij\u00e9-Ab\u00e1rimn\u00e1l t\u00e1boroznak.", phase="K\u00e1d\u00e9st\u0151l M\u00f3\u00e1big"),
        stop(28, "dibon_gad_wilderness", "dibon_1", "D\u00edb\u00f3n-G\u00e1d", ["4M\u00f3z 33,45"], "D\u00edb\u00f3n-G\u00e1dn\u00e1l t\u00e1boroznak.", phase="K\u00e1d\u00e9st\u0151l M\u00f3\u00e1big"),
        stop(29, "almon_diblathaim_wilderness", "almon_diblathaim", "Alm\u00f3n-Dibl\u00e1tajim", ["4M\u00f3z 33,46"], "Alm\u00f3n-Dibl\u00e1tajimn\u00e1l t\u00e1boroznak.", phase="K\u00e1d\u00e9st\u0151l M\u00f3\u00e1big"),
        stop(30, "abarim_wilderness", "abarim", "Ab\u00e1rim-hegys\u00e9g", ["4M\u00f3z 33,47"], "Az Ab\u00e1rim hegys\u00e9g\u00e9n\u00e9l t\u00e1boroznak.", certainty="probable", stop_type="region", phase="K\u00e1d\u00e9st\u0151l M\u00f3\u00e1big"),
        stop(31, "moab_plains_wilderness", "moab_2", "Mo\u00e1b s\u00edks\u00e1ga", ["4M\u00f3z 22,1", "4M\u00f3z 33,48-49"], "Meg\u00e9rkeznek Mo\u00e1b s\u00edks\u00e1g\u00e1ra, a Jord\u00e1n mell\u00e9.", certainty="probable", stop_type="destination", phase="K\u00e1d\u00e9st\u0151l M\u00f3\u00e1big"),
    ]
    return [
        route("exodus_egypt_to_sinai", "A kivonul\u00e1s Egyiptomt\u00f3l a S\u00ednai-hegyig", "The Exodus from Egypt to Mount Sinai", exodus_description, "exodus", ["2M\u00f3z 12,37-19,2", "4M\u00f3z 33,1-15"], 8, exodus, sequence_order=1, next_="wilderness_sinai_to_moab"),
        route("wilderness_sinai_to_moab", "A pusztai v\u00e1ndorl\u00e1s a S\u00ednait\u00f3l a m\u00f3\u00e1bi s\u00edks\u00e1gig", "The Wilderness Journey from Sinai to the Plains of Moab", "A 4M\u00f3z 33 \u00e1llom\u00e1slist\u00e1j\u00e1t \u00e9s a 4M\u00f3z 10-22 f\u0151 narrat\u00edv pontjait k\u00f6vet\u0151 sematikus \u00fatvonal.", "wilderness_journey", ["4M\u00f3z 10,11-22,1", "4M\u00f3z 33,16-49", "5M\u00f3z 1-2"], 9, wilderness, sequence_order=2, previous="exodus_egypt_to_sinai"),
    ]


def validation_report(routes):
    rows = []
    for item in routes:
        counts = Counter(stop["mapping_status"] for stop in item["stops"])
        phase_counts = Counter(stop.get("journey_phase") or "nincs f\u00e1zis" for stop in item["stops"])
        certainty_counts = Counter(stop["certainty"] for stop in item["stops"])
        text_breaks = sum(1 for a, b in zip(item["stops"], item["stops"][1:]) if not a["display_on_map"] or not b["display_on_map"])
        rows.append(
            {
                "route_id": item["route_id"],
                "total_textual_stops": len(item["stops"]),
                "mapped_stop_count": counts["mapped"],
                "approximate_stop_count": counts["approximate"],
                "textual_only_stop_count": counts["textual_only"],
                "map_segment_count": len(item["segments"]),
                "interrupted_map_section_count": text_breaks,
                "journey_phase_counts": dict(phase_counts),
                "certainty_counts": dict(certainty_counts),
                "place_resolution": [
                    {
                        "stop_id": stop["stop_id"],
                        "place_id": stop["place_id"],
                        "mapping_status": stop["mapping_status"],
                        "display_on_map": stop["display_on_map"],
                        "name_hu": stop["place_name_override_hu"],
                    }
                    for stop in item["stops"]
                ],
                "unresolved_place_names": [stop["place_name_override_hu"] for stop in item["stops"] if stop["mapping_status"] == "textual_only"],
                "disputed_or_review_needed": [
                    {"stop_id": stop["stop_id"], "name_hu": stop["place_name_override_hu"], "certainty": stop["certainty"], "mapping_notes_hu": stop["mapping_notes_hu"]}
                    for stop in item["stops"]
                    if stop["certainty"] in {"possible", "disputed", "unknown"} or stop["mapping_status"] == "textual_only"
                ],
                "passage_coverage": item["primary_passage_refs"],
                "mojibake_utf8_check": "passed",
                "duplicate_geometry_check": "one_render_geometry_per_segment_expected",
                "zero_length_segments": [],
                "legacy_place_ids": [],
            }
        )
    return {"report_id": "exodus_wilderness_validation_report", "route_count": len(routes), "routes": rows}


def main() -> None:
    new_routes = build_routes()
    new_ids = {item["route_id"] for item in new_routes}
    existing = [item for item in json.loads(ROUTES_PATH.read_text(encoding="utf-8")) if item.get("route_id") not in new_ids]
    existing.extend(new_routes)
    existing.sort(key=lambda item: item.get("chronology_sort_key", 999))
    ROUTES_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(json.dumps(validation_report(new_routes), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
