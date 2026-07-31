"""Append safely catalog-backed biblical routes (schematic, draft).

Only routes with unambiguous active place_ids and text-named station order.
Skips disputed itineraries (Jonah/Tarshish, David flight, Elijah, exile, flight to Egypt).
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTES_PATH = ROOT / "data" / "biblical_routes" / "biblical_routes.json"
PLACES_PATH = ROOT / "data" / "biblical_places" / "biblical_places_catalog.json"
SOURCE_ID = "openbible_geocoding_cc_by_4_0"

NEW_ROUTE_IDS = {
    "paul_early_damascus_to_antioch",
    "philip_samaria_to_caesarea",
    "peter_jerusalem_to_caesarea",
    "jesus_galilee_named_sites",
    "jesus_passion_jerusalem",
    "seven_churches_asia",
    "ruth_moab_to_bethlehem",
}

DESCRIPTION = (
    "Az útvonal a bibliai szövegben megnevezett állomások sorrendjét mutatja. "
    "A vonalak sematikusak, nem a pontos ókori nyomvonalat jelölik."
)


def places_by_id() -> dict[str, dict]:
    return {
        item["place_id"]: item
        for item in json.loads(PLACES_PATH.read_text(encoding="utf-8"))
        if item.get("place_id")
    }


def require_places(place_ids: list[str]) -> None:
    catalog = places_by_id()
    missing = [place_id for place_id in place_ids if place_id not in catalog]
    if missing:
        raise SystemExit(f"Missing active place_ids: {missing}")


def stop(
    order: int,
    stop_id: str,
    place_id: str,
    name_hu: str | None,
    refs: list[str],
    summary_hu: str,
    *,
    certainty: str = "certain",
    stop_type: str = "explicit_place",
    mapping_status: str = "mapped",
    phase: str | None = None,
    source_note: str | None = None,
    mapping_note: str | None = None,
    segment_type_hint: str = "land",
) -> dict:
    item = {
        "order": order,
        "stop_id": stop_id,
        "place_id": place_id,
        "place_name_override_hu": name_hu,
        "passage_refs": refs,
        "event_summary_hu": summary_hu,
        "certainty": certainty,
        "stop_type": stop_type,
        "source_notes_hu": source_note
        or "Az állomás a bibliai szövegben megnevezett hely.",
        "mapping_status": mapping_status,
        "display_on_map": True,
        "mapping_notes_hu": mapping_note
        or "Aktív katalógusrekord; a térképi vonal sematikus.",
        "sequence_status": "explicit",
        "_segment_type_hint": segment_type_hint,
    }
    if phase:
        item["journey_phase"] = phase
    return item


def automatic_segments(stops: list[dict]) -> list[dict]:
    catalog = places_by_id()
    rows: list[dict] = []
    for current, following in zip(stops, stops[1:]):
        cur = catalog[current["place_id"]]
        nxt = catalog[following["place_id"]]
        if (cur.get("latitude"), cur.get("longitude")) == (
            nxt.get("latitude"),
            nxt.get("longitude"),
        ):
            continue
        certainties = {current["certainty"], following["certainty"]}
        certainty = "mixed" if "possible" in certainties else "probable"
        segment_type = following.get("_segment_type_hint") or current.get("_segment_type_hint") or "land"
        if current.get("_segment_type_hint") == "sea" or following.get("_segment_type_hint") == "sea":
            # Prefer explicit sea only when the following stop marks a sea leg start.
            segment_type = following.get("_segment_type_hint") or "land"
        rows.append(
            {
                "from_stop_id": current["stop_id"],
                "to_stop_id": following["stop_id"],
                "certainty": certainty,
                "segment_type": segment_type if segment_type in {"land", "sea"} else "land",
                "geometry_status": "schematic",
                "source_notes_hu": (
                    "Sematikus összekötő vonal két megnevezett állomás között; "
                    "nem rekonstruált ókori útvonal."
                ),
                "waypoints": [],
                "geometry": None,
            }
        )
    return rows


def strip_hints(stops: list[dict]) -> list[dict]:
    cleaned = []
    for item in stops:
        row = {key: value for key, value in item.items() if not key.startswith("_")}
        cleaned.append(row)
    return cleaned


def route(
    *,
    route_id: str,
    name_hu: str,
    name_en: str,
    category: str,
    primary_refs: list[str],
    chronology_label_hu: str,
    sort_key: float | int,
    stops: list[dict],
    review_notes_hu: str,
    family: dict | None = None,
    certainty: str = "mixed",
    precision_note_hu: str | None = None,
) -> dict:
    require_places([stop["place_id"] for stop in stops])
    payload = {
        "route_id": route_id,
        "name_hu": name_hu,
        "name_en": name_en,
        "short_description_hu": DESCRIPTION,
        "route_category": category,
        "primary_passage_refs": primary_refs,
        "chronology_label_hu": chronology_label_hu,
        "chronology_sort_key": sort_key,
        "certainty": certainty,
        "geometry_status": "schematic",
        "source_ids": [SOURCE_ID],
        "review_status": "draft",
        "review_notes_hu": review_notes_hu,
        "evidence_model": {
            "station_order_basis": "biblical_text_named_stops",
            "historical_route_status": "not_reconstructed",
            "map_geometry_status": "schematic",
            "precision_note_hu": precision_note_hu
            or (
                "Az állomássorrend a bibliai szöveg megnevezett helyeit követi; "
                "a vonalak sematikusak."
            ),
        },
        "stops": strip_hints(stops),
        "segments": automatic_segments(stops),
    }
    if family:
        payload = {**{k: family[k] for k in (
            "route_family_id",
            "family_name_hu",
            "route_sequence_order",
            "previous_route_id",
            "next_route_id",
        )}, **payload}
        # Keep family fields near top like other routes.
        ordered = {"route_id": route_id}
        for key in (
            "route_family_id",
            "family_name_hu",
            "route_sequence_order",
            "previous_route_id",
            "next_route_id",
        ):
            ordered[key] = family[key]
        for key, value in payload.items():
            if key in ordered:
                continue
            ordered[key] = value
        return ordered
    return payload


def build_new_routes() -> list[dict]:
    paul_early = route(
        route_id="paul_early_damascus_to_antioch",
        name_hu="Pál korai útja Damaszkusztól Antiókhiáig",
        name_en="Paul's early journey from Damascus to Antioch",
        category="missionary_journey",
        primary_refs=["ApCsel 9,1-30", "ApCsel 11,25-26"],
        chronology_label_hu="Pál korai évei",
        sort_key=0,
        family={
            "route_family_id": "pauline_missionary_journeys",
            "family_name_hu": "Pál missziói útjai",
            "route_sequence_order": 1,
            "previous_route_id": None,
            "next_route_id": "paul_first_missionary_journey",
        },
        review_notes_hu=(
            "Csak az ApCselben biztonságosan megnevezett állomások. "
            "Az arábiai tartózkodás (Gal 1,17) nincs térképezve, mert a katalógusban "
            "nincs elég pontos, egyértelmű helyrekord."
        ),
        stops=[
            stop(1, "damascus_conversion", "damascus", "Damaszkusz", ["ApCsel 9,1-25"], "Saul Damaszkuszban találkozik az Úrral, majd tanít.", certainty="certain", stop_type="embarkation", phase="Damaszkusz"),
            stop(2, "jerusalem_early_paul", "jerusalem", "Jeruzsálem", ["ApCsel 9,26-29"], "Saul Jeruzsálemben csatlakozik a tanítványokhoz.", certainty="probable", phase="Jeruzsálem"),
            stop(3, "caesarea_to_tarsus", "caesarea", "Cézárea", ["ApCsel 9,30"], "Saulot Cézárán át Tarzuszba küldik.", certainty="certain", stop_type="transit", phase="Tarzusz felé"),
            stop(4, "tarsus_early_paul", "tarsus", "Tarzusz", ["ApCsel 9,30", "ApCsel 11,25"], "Saul Tarzuszban tartózkodik.", certainty="certain", phase="Tarzusz"),
            stop(5, "antioch_syria_early", "antioch_syria", "szíriai Antiókhia", ["ApCsel 11,25-26"], "Barnabás elhozza Sault Antiókhiába.", certainty="probable", stop_type="destination", phase="Antiókhia"),
        ],
    )

    philip = route(
        route_id="philip_samaria_to_caesarea",
        name_hu="Fülöp útja Szamáriától Cézáráig",
        name_en="Philip's journey from Samaria to Caesarea",
        category="ministry_journey",
        primary_refs=["ApCsel 8,5-40"],
        chronology_label_hu="Fülöp szolgálata",
        sort_key=13,
        family={
            "route_family_id": "acts_early_journeys",
            "family_name_hu": "Korai apostoli utak (ApCsel)",
            "route_sequence_order": 1,
            "previous_route_id": None,
            "next_route_id": "peter_jerusalem_to_caesarea",
        },
        review_notes_hu=(
            "Az ApCsel 8 megnevezett helyei. Azótusz az aktív ashdod rekordra mutat; "
            "a Gáza felé vezető út sematikus tájékozódási pont."
        ),
        stops=[
            stop(1, "samaria_philip", "samaria_1", "Szamária", ["ApCsel 8,5-25"], "Fülöp Szamáriában hirdeti az igét.", certainty="certain", stop_type="embarkation", phase="Szamária"),
            stop(2, "gaza_road_philip", "gaza", "Gáza felé vezető út", ["ApCsel 8,26-39"], "Fülöp a Gáza felé vezető úton találkozik az etióp udvari főemberrel.", certainty="probable", stop_type="transit", mapping_status="approximate", phase="Gáza útja", mapping_note="A szöveg utat említ Gáza felé; a gaza rekord sematikus tájékozódási pont."),
            stop(3, "azotus_philip", "ashdod", "Azótusz (Asdód)", ["ApCsel 8,40"], "Fülöp Azótuszban jelenik meg, és hirdeti az evangéliumot.", certainty="certain", phase="Tengerparti városok", source_note="Azótusz a katalógus ashdod (Asdód) rekordjára mutat."),
            stop(4, "caesarea_philip", "caesarea", "Cézárea", ["ApCsel 8,40"], "Fülöp Cézáráig jut.", certainty="certain", stop_type="destination", phase="Tengerparti városok"),
        ],
    )

    peter = route(
        route_id="peter_jerusalem_to_caesarea",
        name_hu="Péter útja Jeruzsálemtől Cézáráig",
        name_en="Peter's journey from Jerusalem to Caesarea",
        category="ministry_journey",
        primary_refs=["ApCsel 8,14-25", "ApCsel 9,32-10,48"],
        chronology_label_hu="Péter korai szolgálata",
        sort_key=14,
        family={
            "route_family_id": "acts_early_journeys",
            "family_name_hu": "Korai apostoli utak (ApCsel)",
            "route_sequence_order": 2,
            "previous_route_id": "philip_samaria_to_caesarea",
            "next_route_id": None,
        },
        review_notes_hu=(
            "Az ApCsel 8–10 megnevezett állomásai. Lydda a katalógus lod rekordjára mutat."
        ),
        stops=[
            stop(1, "jerusalem_peter", "jerusalem", "Jeruzsálem", ["ApCsel 8,14"], "A jeruzsálemi apostolok Pétert is elküldik Szamáriába.", certainty="probable", stop_type="embarkation", phase="Jeruzsálem és Szamária"),
            stop(2, "samaria_peter", "samaria_1", "Szamária", ["ApCsel 8,14-25"], "Péter Szamáriában szolgál.", certainty="certain", phase="Jeruzsálem és Szamária"),
            stop(3, "lydda_peter", "lod", "Lidda (Lód)", ["ApCsel 9,32-35"], "Péter Liddában meggyógyítja Éneást.", certainty="certain", phase="Lidda és Joppé", source_note="Lidda a katalógus lod rekordjára mutat."),
            stop(4, "joppa_peter", "joppa", "Joppé", ["ApCsel 9,36-43"], "Péter Joppéban feltámasztja Tábithát.", certainty="certain", phase="Lidda és Joppé"),
            stop(5, "caesarea_peter", "caesarea", "Cézárea", ["ApCsel 10,1-48"], "Péter Cézárában Kornéliusz házában szolgál.", certainty="certain", stop_type="destination", phase="Cézárea"),
        ],
    )

    galilee = route(
        route_id="jesus_galilee_named_sites",
        name_hu="Jézus galileai helyszínei",
        name_en="Jesus' named sites in Galilee",
        category="ministry_journey",
        primary_refs=["Mt 4,12-25", "Mk 1,14-39", "Lk 4,14-37", "Mt 15,21-28", "Mt 16,13"],
        chronology_label_hu="Jézus galileai szolgálata",
        sort_key=15,
        family={
            "route_family_id": "jesus_ministry_routes",
            "family_name_hu": "Jézus szolgálatának helyszínei",
            "route_sequence_order": 1,
            "previous_route_id": None,
            "next_route_id": "jesus_passion_jerusalem",
        },
        certainty="mixed",
        review_notes_hu=(
            "Csak egyértelműen azonosítható, aktív katalógushelyek. "
            "A sorrend a evangéliumi elbeszélés tipikus helycsoportjait követi sematikusan; "
            "nem rekonstruált egyetlen körút. Gerasza/Gadara vita miatt kimaradt."
        ),
        precision_note_hu=(
            "Sematikus helylánc a megnevezett galileai és kapcsolódó helyekről; "
            "nem állít pontos napi itineráriumot."
        ),
        stops=[
            stop(1, "nazareth_start", "nazareth", "Názáret", ["Lk 4,16-30"], "Jézus Názáretben tanít a zsinagógában.", certainty="probable", stop_type="embarkation", phase="Galileai kezdet"),
            stop(2, "cana_sign", "cana", "Kána", ["Jn 2,1-11"], "A kánai menyegző.", certainty="probable", phase="Galileai kezdet"),
            stop(3, "capernaum_base", "capernaum", "Kapernaum", ["Mt 4,13", "Mk 1,21-34"], "Kapernaum a galileai szolgálat központi helye.", certainty="certain", phase="Kapernaum és környéke"),
            stop(4, "chorazin_named", "chorazin", "Korazin", ["Mt 11,21"], "Jézus Korazint is megnevezi.", certainty="probable", phase="Kapernaum és környéke"),
            stop(5, "bethsaida_named", "bethsaida_1", "Betsaida", ["Mk 8,22-26", "Mt 11,21"], "Betsaida megnevezett galileai hely.", certainty="probable", phase="Kapernaum és környéke", mapping_note="A katalógus egy aktív Betsaida-rekordot tartalmaz; az azonosítás a szakirodalomban vitatott lehet."),
            stop(6, "magdala_named", "magdala", "Magdala", ["Mt 15,39"], "Magdala / Magadán térsége.", certainty="probable", phase="Kapernaum és környéke"),
            stop(7, "nain_named", "nain", "Nain", ["Lk 7,11-17"], "Nainban feltámaszt egy ifjút.", certainty="certain", phase="Galileai városok"),
            stop(8, "sea_of_galilee_ministry", "sea_of_galilee", "Galileai-tenger", ["Mk 4,35-41", "Mt 14,22-33"], "Több elbeszélés a Galileai-tengerhez kötődik.", certainty="certain", stop_type="region", phase="Galileai-tenger"),
            stop(9, "tyre_sidon_approach", "tyre", "Tírusz", ["Mt 15,21-28", "Mk 7,24-31"], "Jézus Tírusz vidékére megy.", certainty="certain", phase="Tírusz és Szidón"),
            stop(10, "sidon_named", "sidon", "Szidón", ["Mk 7,31"], "Szidón térsége is szerepel az elbeszélésben.", certainty="certain", phase="Tírusz és Szidón"),
            stop(11, "caesarea_philippi_named", "caesarea_philippi", "Cézárea Filippi", ["Mt 16,13-20"], "Péter vallástétele Cézárea Filippi vidékén.", certainty="certain", stop_type="destination", phase="Cézárea Filippi"),
        ],
    )

    passion = route(
        route_id="jesus_passion_jerusalem",
        name_hu="Jézus útja Jeruzsálemben a passió idején",
        name_en="Jesus in Jerusalem during the Passion",
        category="ministry_journey",
        primary_refs=["Mt 21,1-27,66", "Mk 11,1-15,47", "Lk 19,28-23,56", "Jn 12,12-19,42"],
        chronology_label_hu="Passió hét",
        sort_key=16,
        family={
            "route_family_id": "jesus_ministry_routes",
            "family_name_hu": "Jézus szolgálatának helyszínei",
            "route_sequence_order": 2,
            "previous_route_id": "jesus_galilee_named_sites",
            "next_route_id": None,
        },
        review_notes_hu=(
            "A passió elbeszélések megnevezett helyei. Emmaus kimaradt, mert azonosítása "
            "vitatott. Betánia a certain bethany_1 rekordra mutat."
        ),
        stops=[
            stop(1, "bethany_passion", "bethany_1", "Betánia", ["Jn 12,1-8", "Mk 14,3"], "Jézus Betániában tartózkodik a passió előtt.", certainty="certain", stop_type="embarkation", phase="Betánia és bevonulás"),
            stop(2, "bethphage_entry", "bethphage", "Betfagé", ["Mt 21,1-11", "Mk 11,1-10"], "A bevonulás Betfagé felől indul.", certainty="probable", phase="Betánia és bevonulás"),
            stop(3, "jerusalem_entry", "jerusalem", "Jeruzsálem", ["Mt 21,10-17", "Mk 11,11"], "Jézus bevonul Jeruzsálembe.", certainty="probable", phase="Jeruzsálem"),
            stop(4, "mount_of_olives_teaching", "mount_of_olives", "Olajfák hegye", ["Mt 24,3", "Mk 13,3"], "Tanítás az Olajfák hegyén.", certainty="certain", phase="Olajfák hegye"),
            stop(5, "gethsemane_prayer", "gethsemane", "Gecsemáné", ["Mt 26,36-46", "Mk 14,32-42"], "Imádság a Gecsemánéban.", certainty="certain", phase="Gecsemáné"),
            stop(6, "golgotha_crucifixion", "golgotha", "Golgota", ["Mt 27,33-50", "Jn 19,17-30"], "A keresztre feszítés helye.", certainty="probable", stop_type="destination", phase="Golgota"),
        ],
    )

    churches = route(
        route_id="seven_churches_asia",
        name_hu="Ázsia hét gyülekezete",
        name_en="The seven churches of Asia",
        category="other",
        primary_refs=["Jel 1,11", "Jel 2,1-3,22"],
        chronology_label_hu="Jelenések – hét gyülekezet",
        sort_key=17,
        certainty="certain",
        review_notes_hu=(
            "A Jel 1,11 és 2–3 megnevezett városai sorrendben. "
            "Ez állomáslánc / gyülekezeti kör, nem egyetlen utazás rekonstrukciója."
        ),
        precision_note_hu=(
            "A sorrend a Jelenések könyvében megadott városnevek sorrendjét követi; "
            "a vonalak sematikusak."
        ),
        stops=[
            stop(1, "ephesus_church", "ephesus", "Efézus", ["Jel 2,1-7"], "Az efézusi gyülekezet üzenete.", certainty="certain"),
            stop(2, "smyrna_church", "smyrna", "Szmirna", ["Jel 2,8-11"], "A szmirnai gyülekezet üzenete.", certainty="certain"),
            stop(3, "pergamum_church", "pergamum", "Pergamon", ["Jel 2,12-17"], "A pergamoni gyülekezet üzenete.", certainty="certain"),
            stop(4, "thyatira_church", "thyatira", "Thiatira", ["Jel 2,18-29"], "A thiatirai gyülekezet üzenete.", certainty="certain"),
            stop(5, "sardis_church", "sardis", "Szárdisz", ["Jel 3,1-6"], "A szárdiszi gyülekezet üzenete.", certainty="certain"),
            stop(6, "philadelphia_church", "philadelphia", "Filadelfia", ["Jel 3,7-13"], "A filadelfiai gyülekezet üzenete.", certainty="certain"),
            stop(7, "laodicea_church", "laodicea", "Laodicea", ["Jel 3,14-22"], "A laodiceai gyülekezet üzenete.", certainty="certain", stop_type="destination"),
        ],
    )

    ruth = route(
        route_id="ruth_moab_to_bethlehem",
        name_hu="Ruth útja Moábtól Betlehemig",
        name_en="Ruth's journey from Moab to Bethlehem",
        category="other",
        primary_refs=["Ruth 1,1-22"],
        chronology_label_hu="Ruth története",
        sort_key=7.5,
        certainty="certain",
        review_notes_hu="Rövid, szövegesen egyértelmű állomáspár; Moáb régióként, Betlehem településként.",
        stops=[
            stop(1, "moab_ruth", "moab_1", "Moáb", ["Ruth 1,1-5"], "Elimélek családja Moáb mezejére megy.", certainty="certain", stop_type="region", phase="Moáb"),
            stop(2, "bethlehem_ruth", "bethlehem_1", "Betlehem", ["Ruth 1,19-22"], "Naomi és Ruth visszatérnek Betlehembe.", certainty="certain", stop_type="destination", phase="Betlehem"),
        ],
    )

    return [paul_early, philip, peter, galilee, passion, churches, ruth]


def update_pauline_family(existing: list[dict]) -> None:
    links = {
        "paul_early_damascus_to_antioch": (1, None, "paul_first_missionary_journey"),
        "paul_first_missionary_journey": (2, "paul_early_damascus_to_antioch", "paul_second_missionary_journey"),
        "paul_second_missionary_journey": (3, "paul_first_missionary_journey", "paul_third_missionary_journey"),
        "paul_third_missionary_journey": (4, "paul_second_missionary_journey", "paul_journey_to_rome"),
        "paul_journey_to_rome": (5, "paul_third_missionary_journey", None),
    }
    for route in existing:
        rid = route["route_id"]
        if rid not in links:
            continue
        sequence, previous, next_id = links[rid]
        route["route_family_id"] = "pauline_missionary_journeys"
        route["family_name_hu"] = "Pál missziói útjai"
        route["route_sequence_order"] = sequence
        route["previous_route_id"] = previous
        route["next_route_id"] = next_id


def main() -> None:
    existing = json.loads(ROUTES_PATH.read_text(encoding="utf-8"))
    existing = [route for route in existing if route.get("route_id") not in NEW_ROUTE_IDS]
    update_pauline_family(existing)
    new_routes = build_new_routes()
    ordered = existing + new_routes

    ROUTES_PATH.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(ordered)} routes to {ROUTES_PATH}")
    for route in ordered:
        if route["route_id"] in NEW_ROUTE_IDS or route["route_id"].startswith("paul_"):
            print(
                route["route_id"],
                "stops",
                len(route["stops"]),
                "segs",
                len(route["segments"]),
                "seq",
                route.get("route_sequence_order"),
            )


if __name__ == "__main__":
    main()
