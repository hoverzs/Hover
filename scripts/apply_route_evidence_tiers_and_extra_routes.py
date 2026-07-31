"""Assign route_evidence_tier values and append additional safe catalog routes."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTES_PATH = ROOT / "data" / "biblical_routes" / "biblical_routes.json"
PLACES_PATH = ROOT / "data" / "biblical_places" / "biblical_places_catalog.json"
SOURCE_ID = "openbible_geocoding_cc_by_4_0"

DESCRIPTION = (
    "Az útvonal a bibliai szövegben megnevezett állomások sorrendjét mutatja. "
    "A vonalak sematikusak, nem a pontos ókori nyomvonalat jelölik."
)

# Conservative tiers: strong = clear named sequence; moderate = text-led with
# regions/interpretation; weak = schematic grouping or many uncertain stops.
EVIDENCE_TIERS: dict[str, str] = {
    "paul_first_missionary_journey": "strong",
    "paul_second_missionary_journey": "moderate",
    "paul_third_missionary_journey": "moderate",
    "paul_journey_to_rome": "moderate",
    "paul_early_damascus_to_antioch": "moderate",
    "abraham_journey": "moderate",
    "jacob_journeys": "moderate",
    "joseph_geographical_arc": "moderate",
    "exodus_egypt_to_sinai": "weak",
    "wilderness_sinai_to_moab": "weak",
    "joshua_jordan_crossing_central_campaign": "moderate",
    "joshua_southern_campaign": "moderate",
    "joshua_northern_campaign": "moderate",
    "philip_samaria_to_caesarea": "moderate",
    "peter_jerusalem_to_caesarea": "moderate",
    "jesus_galilee_named_sites": "weak",
    "jesus_passion_jerusalem": "strong",
    "seven_churches_asia": "strong",
    "ruth_moab_to_bethlehem": "strong",
    "jesus_infancy_egypt": "moderate",
    "jesus_samaria_sychar": "strong",
    "ezra_return_babylon_to_jerusalem": "moderate",
    "nehemiah_susa_to_jerusalem": "strong",
}

EXTRA_ROUTE_IDS = {
    "jesus_infancy_egypt",
    "jesus_samaria_sychar",
    "ezra_return_babylon_to_jerusalem",
    "nehemiah_susa_to_jerusalem",
}


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
        "source_notes_hu": source_note or "Az állomás a bibliai szövegben megnevezett hely.",
        "mapping_status": mapping_status,
        "display_on_map": True,
        "mapping_notes_hu": mapping_note or "Aktív katalógusrekord; a térképi vonal sematikus.",
        "sequence_status": "explicit",
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
        rows.append(
            {
                "from_stop_id": current["stop_id"],
                "to_stop_id": following["stop_id"],
                "certainty": certainty,
                "segment_type": "land",
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
    evidence_tier: str,
    family: dict | None = None,
    certainty: str = "mixed",
    precision_note_hu: str | None = None,
) -> dict:
    require_places([item["place_id"] for item in stops])
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
        "route_evidence_tier": evidence_tier,
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
        "stops": stops,
        "segments": automatic_segments(stops),
    }
    if not family:
        return payload
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
        if key not in ordered:
            ordered[key] = value
    return ordered


def build_extra_routes() -> list[dict]:
    infancy = route(
        route_id="jesus_infancy_egypt",
        name_hu="Jézus gyermekkora: Betlehemtől Egyiptomon át Názáretig",
        name_en="Jesus' infancy: Bethlehem via Egypt to Nazareth",
        category="ministry_journey",
        primary_refs=["Mt 2,1-23"],
        chronology_label_hu="Jézus gyermekkora",
        sort_key=14.5,
        evidence_tier="moderate",
        family={
            "route_family_id": "jesus_ministry_routes",
            "family_name_hu": "Jézus szolgálatának helyszínei",
            "route_sequence_order": 1,
            "previous_route_id": None,
            "next_route_id": "jesus_galilee_named_sites",
        },
        review_notes_hu=(
            "Mt 2 megnevezett állomásai. Egyiptom régióként szerepel, nem konkrét város; "
            "ezért a tier közepes."
        ),
        stops=[
            stop(1, "bethlehem_infancy", "bethlehem_1", "Betlehem", ["Mt 2,1-12"], "Jézus Betlehemben születik.", certainty="certain", stop_type="embarkation", phase="Betlehem"),
            stop(2, "egypt_refuge", "egypt", "Egyiptom", ["Mt 2,13-15"], "A család Egyiptomba menekül.", certainty="certain", stop_type="region", mapping_status="approximate", phase="Egyiptom", mapping_note="A szöveg Egyiptomot mint országot/régiót nevezi meg; nem egyetlen városrekonstrukció."),
            stop(3, "nazareth_settlement", "nazareth", "Názáret", ["Mt 2,19-23"], "A család Názáretben telepszik le.", certainty="probable", stop_type="destination", phase="Názáret"),
        ],
    )

    sychar = route(
        route_id="jesus_samaria_sychar",
        name_hu="Jézus útja Szikáron át",
        name_en="Jesus' journey through Sychar",
        category="ministry_journey",
        primary_refs=["Jn 4,1-45"],
        chronology_label_hu="Szikár",
        sort_key=15.5,
        evidence_tier="strong",
        certainty="probable",
        review_notes_hu="Jn 4 rövid, szövegesen egyértelmű útvonala Júdeából Szikáron át Galileába.",
        stops=[
            stop(1, "judea_departure_sychar", "judea_1", "Júdea", ["Jn 4,1-3"], "Jézus elhagyja Júdeát.", certainty="certain", stop_type="region", phase="Júdeából"),
            stop(2, "sychar_well", "sychar", "Szikár", ["Jn 4,4-42"], "Találkozás a szamáriai asszonnyal Szikárnál.", certainty="probable", phase="Szikár"),
            stop(3, "galilee_arrival_sychar", "galilee_1", "Galilea", ["Jn 4,43-45"], "Jézus Galileába megy.", certainty="certain", stop_type="destination", phase="Galilea"),
        ],
    )

    ezra = route(
        route_id="ezra_return_babylon_to_jerusalem",
        name_hu="Ezra hazatérése Babilontól Jeruzsálemig",
        name_en="Ezra's return from Babylon to Jerusalem",
        category="return_from_exile",
        primary_refs=["Ezd 7,1-8,36"],
        chronology_label_hu="Ezra hazatérése",
        sort_key=12.5,
        evidence_tier="moderate",
        family={
            "route_family_id": "return_from_exile_routes",
            "family_name_hu": "Hazatérés a fogságból",
            "route_sequence_order": 1,
            "previous_route_id": None,
            "next_route_id": "nehemiah_susa_to_jerusalem",
        },
        review_notes_hu=(
            "Ezd 7–8 megnevezett állomásai. A babiloni kiindulópont a katalógus babylon_1 "
            "rekordjára mutat. Az Ahava a jelenlegi katalógusban azonos koordinátán van "
            "Babilonnal, ezért a térképi összekötés csak Jeruzsálem felé rajzolódik."
        ),
        stops=[
            stop(1, "babylon_ezra", "babylon_1", "Babilon", ["Ezd 7,6-9"], "Ezra Babilonból indul.", certainty="certain", stop_type="embarkation", phase="Babilon"),
            stop(
                2,
                "ahava_ezra",
                "ahava",
                "Ahava",
                ["Ezd 8,15-31"],
                "Az Ahava folyónál tábort vernek és böjtölnek.",
                certainty="probable",
                stop_type="region",
                mapping_status="approximate",
                phase="Ahava",
                mapping_note=(
                    "A katalógusban az Ahava jelenleg azonos koordinátával szerepel, mint Babilon; "
                    "a stop szövegbeli állomás, nem külön térképi elmozdulás."
                ),
            ),
            stop(3, "jerusalem_ezra", "jerusalem", "Jeruzsálem", ["Ezd 8,31-36"], "Megérkeznek Jeruzsálembe.", certainty="probable", stop_type="destination", phase="Jeruzsálem"),
        ],
    )

    nehemiah = route(
        route_id="nehemiah_susa_to_jerusalem",
        name_hu="Nehemiás útja Súsántól Jeruzsálemig",
        name_en="Nehemiah's journey from Susa to Jerusalem",
        category="return_from_exile",
        primary_refs=["Neh 1,1-2,11"],
        chronology_label_hu="Nehemiás útja",
        sort_key=12.6,
        evidence_tier="strong",
        certainty="certain",
        family={
            "route_family_id": "return_from_exile_routes",
            "family_name_hu": "Hazatérés a fogságból",
            "route_sequence_order": 2,
            "previous_route_id": "ezra_return_babylon_to_jerusalem",
            "next_route_id": None,
        },
        review_notes_hu="Neh 1–2 rövid, szövegesen egyértelmű útvonala Súsántól Jeruzsálemig.",
        stops=[
            stop(1, "susa_nehemiah", "susa", "Súsán", ["Neh 1,1-2,8"], "Nehemiás Súsánban szolgál, majd engedélyt kap az útra.", certainty="certain", stop_type="embarkation", phase="Súsán"),
            stop(2, "jerusalem_nehemiah", "jerusalem", "Jeruzsálem", ["Neh 2,9-11"], "Nehemiás megérkezik Jeruzsálembe.", certainty="probable", stop_type="destination", phase="Jeruzsálem"),
        ],
    )

    return [infancy, sychar, ezra, nehemiah]


def update_jesus_family(routes: list[dict]) -> None:
    links = {
        "jesus_infancy_egypt": (1, None, "jesus_galilee_named_sites"),
        "jesus_galilee_named_sites": (2, "jesus_infancy_egypt", "jesus_passion_jerusalem"),
        "jesus_passion_jerusalem": (3, "jesus_galilee_named_sites", None),
    }
    for route in routes:
        rid = route["route_id"]
        if rid not in links:
            continue
        sequence, previous, next_id = links[rid]
        route["route_family_id"] = "jesus_ministry_routes"
        route["family_name_hu"] = "Jézus szolgálatának helyszínei"
        route["route_sequence_order"] = sequence
        route["previous_route_id"] = previous
        route["next_route_id"] = next_id


def main() -> None:
    existing = json.loads(ROUTES_PATH.read_text(encoding="utf-8"))
    existing = [route for route in existing if route.get("route_id") not in EXTRA_ROUTE_IDS]
    for route in existing:
        tier = EVIDENCE_TIERS.get(route["route_id"])
        if not tier:
            raise SystemExit(f"Missing evidence tier for {route['route_id']}")
        route["route_evidence_tier"] = tier

    extras = build_extra_routes()
    update_jesus_family(existing + extras)
    ordered = existing + extras
    for route in ordered:
        expected = EVIDENCE_TIERS[route["route_id"]]
        route["route_evidence_tier"] = expected

    ROUTES_PATH.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(ordered)} routes")
    for route in ordered:
        print(route["route_evidence_tier"], route["route_id"])


if __name__ == "__main__":
    main()
