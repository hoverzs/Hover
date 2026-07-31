from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biblical_routes import (
    BiblicalRouteDataError,
    load_biblical_routes,
    passage_refs_overlap,
    route_options,
    validate_route_user_text,
)


ROUTES_PATH = ROOT / "data" / "biblical_routes" / "biblical_routes.json"
VALIDATION_REPORT_PATH = ROOT / "data" / "biblical_routes" / "pauline_routes_validation_report.json"
JOSHUA_VALIDATION_REPORT_PATH = ROOT / "data" / "biblical_routes" / "joshua_conquest_validation_report.json"
EXPECTED_ROUTE_NAMES_HU = [
    "P\u00e1l els\u0151 misszi\u00f3i \u00fatja",
    "P\u00e1l m\u00e1sodik misszi\u00f3i \u00fatja",
    "P\u00e1l harmadik misszi\u00f3i \u00fatja",
    "P\u00e1l \u00fatja Jeruzs\u00e1lemb\u0151l R\u00f3m\u00e1ba",
    "\u00c1brah\u00e1m v\u00e1ndorl\u00e1sa",
    "J\u00e1k\u00f3b \u00fatjai",
    "J\u00f3zsef t\u00f6rt\u00e9net\u00e9nek f\u00f6ldrajzi \u00edve",
    "A kivonul\u00e1s Egyiptomt\u00f3l a S\u00ednai-hegyig",
    "A pusztai v\u00e1ndorl\u00e1s a S\u00ednait\u00f3l a m\u00f3\u00e1bi s\u00edks\u00e1gig",
    "A Jord\u00e1n \u00e1tkel\u00e9se \u00e9s a k\u00f6z\u00e9ps\u0151 hadj\u00e1rat",
    "J\u00f3zsu\u00e9 d\u00e9li hadj\u00e1rata",
    "J\u00f3zsu\u00e9 \u00e9szaki hadj\u00e1rata",
]
CORRUPTED_TEXT_MARKERS = ("\ufffd", "\u0102", "\u00c2", "\u010f", "ďż˝")


def _route_payload() -> list[dict]:
    return json.loads(ROUTES_PATH.read_text(encoding="utf-8"))


def _write_temp_routes(payload: list[dict]) -> Path:
    path = Path(tempfile.mkdtemp()) / "routes.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _assert_raises(expected: type[Exception], callback, *args, **kwargs) -> Exception:
    try:
        callback(*args, **kwargs)
    except expected as exc:
        return exc
    raise AssertionError(f"Expected {expected.__name__} to be raised.")


def test_valid_pilot_route_loads() -> None:
    routes = load_biblical_routes()
    assert len(routes) == 12
    route = routes[0]
    assert route.route_id == "paul_first_missionary_journey"
    assert route.name_hu == EXPECTED_ROUTE_NAMES_HU[0]
    assert route.route_category == "missionary_journey"
    assert route.primary_passage_refs == ("ApCsel 13,1-14,28",)
    assert len(route.stops) == 15
    assert len(route.segments) == 14


def test_all_pauline_routes_load_in_chronological_order() -> None:
    routes = load_biblical_routes()

    assert [route.route_id for route in routes] == [
        "paul_first_missionary_journey",
        "paul_second_missionary_journey",
        "paul_third_missionary_journey",
        "paul_journey_to_rome",
        "abraham_journey",
        "jacob_journeys",
        "joseph_geographical_arc",
        "exodus_egypt_to_sinai",
        "wilderness_sinai_to_moab",
        "joshua_jordan_crossing_central_campaign",
        "joshua_southern_campaign",
        "joshua_northern_campaign",
    ]
    assert route_options(routes) == [route.route_id for route in routes]
    assert len({route.route_id for route in routes}) == 12
    assert [route.name_hu for route in routes] == EXPECTED_ROUTE_NAMES_HU


def test_route_json_and_report_are_clean_utf8() -> None:
    for path in (ROUTES_PATH, VALIDATION_REPORT_PATH, JOSHUA_VALIDATION_REPORT_PATH):
        text = path.read_text(encoding="utf-8")
        assert not any(marker in text for marker in CORRUPTED_TEXT_MARKERS)
        assert "P?l" not in text
        assert "?tja" not in text
        assert json.loads(text)


def test_route_json_utf8_roundtrip_preserves_hungarian_names() -> None:
    payload = _route_payload()
    encoded = json.dumps(payload, ensure_ascii=False)
    decoded = json.loads(encoded)

    assert [route["name_hu"] for route in decoded] == EXPECTED_ROUTE_NAMES_HU


def test_route_loader_rejects_corrupted_user_facing_text() -> None:
    payload = _route_payload()
    payload[1]["name_hu"] = "P?l m?sodik misszi?i ?tja"
    path = _write_temp_routes(payload)

    exc = _assert_raises(BiblicalRouteDataError, load_biblical_routes, routes_path=path)

    assert "Corrupted user-facing route text" in str(exc)
    assert "routes.name_hu" in str(exc)


def test_user_text_validator_rejects_mojibake_and_allows_normal_question_marks() -> None:
    validate_route_user_text("Mi t\u00f6rt\u00e9nt itt?", "routes.review_notes_hu")

    exc = _assert_raises(
        BiblicalRouteDataError,
        validate_route_user_text,
        "P\u0102\u2030l els\u0105\u2018 misszi\u0102\u0142i",
        "routes.name_hu",
    )
    assert "routes.name_hu" in str(exc)


def test_new_pauline_routes_have_expected_boundaries_and_counts() -> None:
    routes = {route.route_id: route for route in load_biblical_routes()}

    second = routes["paul_second_missionary_journey"]
    assert second.primary_passage_refs == ("ApCsel 15,36-18,22",)
    assert second.stops[0].place_id == "antioch_syria"
    assert second.stops[-1].place_id == "antioch_syria"
    assert len(second.stops) == 23
    assert len(second.segments) == 22

    third = routes["paul_third_missionary_journey"]
    assert third.primary_passage_refs == ("ApCsel 18,23-21,17",)
    assert third.stops[0].place_id == "antioch_syria"
    assert third.stops[-1].place_id == "jerusalem"
    assert len(third.stops) == 21
    assert len(third.segments) == 20

    rome = routes["paul_journey_to_rome"]
    assert rome.primary_passage_refs == ("ApCsel 21,17-28,31",)
    assert rome.stops[0].place_id == "jerusalem"
    assert rome.stops[-1].place_id == "rome"
    assert len(rome.stops) == 19
    assert len(rome.segments) == 18


def test_patriarchal_routes_have_expected_boundaries_and_counts() -> None:
    routes = {route.route_id: route for route in load_biblical_routes()}

    abraham = routes["abraham_journey"]
    assert abraham.primary_passage_refs == ("1M\u00f3z 11,27-13,18", "1M\u00f3z 20-22")
    assert abraham.route_category == "patriarchal_journey"
    assert abraham.stops[0].place_id == "ur_1"
    assert abraham.stops[-1].place_id == "beersheba_1"
    assert len(abraham.stops) == 13
    assert len(abraham.segments) == 12

    jacob = routes["jacob_journeys"]
    assert jacob.primary_passage_refs == ("1M\u00f3z 27,41-35,29",)
    assert jacob.stops[0].place_id == "beersheba_1"
    assert jacob.stops[-1].place_id == "hebron"
    assert len(jacob.stops) == 12
    assert len(jacob.segments) == 11

    joseph = routes["joseph_geographical_arc"]
    assert joseph.primary_passage_refs == ("1M\u00f3z 37-47",)
    assert joseph.stops[0].place_id == "valley_of_hebron"
    assert joseph.stops[-1].place_id == "goshen_1"
    assert len(joseph.stops) == 10
    assert len(joseph.segments) == 9
    raw = {route["route_id"]: route for route in _route_payload()}
    assert {stop["journey_phase"] for stop in raw["joseph_geographical_arc"]["stops"]} == {
        "J\u00f3zsef elhurcol\u00e1sa",
        "A testv\u00e9rek egyiptomi \u00fatjai",
        "J\u00e1k\u00f3b csal\u00e1dj\u00e1nak Egyiptomba k\u00f6lt\u00f6z\u00e9se",
    }


def test_all_route_stops_and_segments_are_valid() -> None:
    for route in load_biblical_routes():
        stop_ids = [stop.stop_id for stop in route.stops]
        orders = [stop.order for stop in route.stops]
        assert len(stop_ids) == len(set(stop_ids))
        assert orders == list(range(1, len(route.stops) + 1))
        assert all(stop.place_id for stop in route.stops if stop.display_on_map)
        assert all(stop.place_id is None for stop in route.stops if stop.mapping_status == "textual_only")
        assert all(stop.event_summary_hu.strip() for stop in route.stops)
        assert all(segment.geometry_status == "schematic" for segment in route.segments)
        assert all(segment.segment_type in {"land", "sea"} for segment in route.segments)
        assert all(segment.from_stop_id in stop_ids for segment in route.segments)
        assert all(segment.to_stop_id in stop_ids for segment in route.segments)


def test_new_route_segment_type_counts() -> None:
    routes = {route.route_id: route for route in load_biblical_routes()}

    assert [segment.segment_type for segment in routes["paul_second_missionary_journey"].segments].count("sea") == 4
    assert [segment.segment_type for segment in routes["paul_second_missionary_journey"].segments].count("land") == 18
    assert [segment.segment_type for segment in routes["paul_third_missionary_journey"].segments].count("sea") == 11
    assert [segment.segment_type for segment in routes["paul_third_missionary_journey"].segments].count("land") == 9
    assert [segment.segment_type for segment in routes["paul_journey_to_rome"].segments].count("sea") == 13
    assert [segment.segment_type for segment in routes["paul_journey_to_rome"].segments].count("land") == 5


def test_pilot_stop_place_ids_exist_and_repeat_places_are_allowed() -> None:
    route = load_biblical_routes()[0]
    place_ids = [stop.place_id for stop in route.stops]
    assert place_ids == [
        "antioch_syria",
        "seleucia",
        "salamis",
        "paphos",
        "perga",
        "antioch_2",
        "iconium",
        "lystra",
        "derbe",
        "lystra",
        "iconium",
        "antioch_2",
        "perga",
        "attalia",
        "antioch_syria",
    ]
    assert place_ids.count("lystra") == 2
    assert place_ids.count("iconium") == 2
    assert place_ids.count("antioch_2") == 2
    assert place_ids.count("perga") == 2
    assert place_ids.count("antioch_syria") == 2


def test_pilot_stop_ids_and_orders_are_unique_and_consecutive() -> None:
    route = load_biblical_routes()[0]
    stop_ids = [stop.stop_id for stop in route.stops]
    orders = [stop.order for stop in route.stops]
    assert len(stop_ids) == len(set(stop_ids))
    assert orders == list(range(1, len(route.stops) + 1))


def test_segments_reference_existing_stops_and_have_expected_types() -> None:
    route = load_biblical_routes()[0]
    stop_ids = {stop.stop_id for stop in route.stops}
    assert all(segment.from_stop_id in stop_ids for segment in route.segments)
    assert all(segment.to_stop_id in stop_ids for segment in route.segments)
    segment_types = [segment.segment_type for segment in route.segments]
    assert segment_types.count("sea") == 3
    assert segment_types.count("land") == 11
    assert all(segment.geometry_status == "schematic" for segment in route.segments)


def test_invalid_place_id_is_rejected() -> None:
    payload = _route_payload()
    payload[0]["stops"][0]["place_id"] = "not_a_place"
    path = _write_temp_routes(payload)
    exc = _assert_raises(BiblicalRouteDataError, load_biblical_routes, routes_path=path)
    assert "unknown place_id" in str(exc)


def test_textual_only_stop_loads_without_place_id() -> None:
    payload = _route_payload()
    route = payload[0]
    route["stops"].insert(
        1,
        {
            "order": 2,
            "stop_id": "unknown_textual_stop",
            "place_id": None,
            "place_name_override_hu": "Ismeretlen állomás",
            "passage_refs": ["2Móz 15,22"],
            "event_summary_hu": "A szöveg név szerint említi, de nem térképezhető biztonságosan.",
            "certainty": "possible",
            "stop_type": "uncertain_place",
            "source_notes_hu": "Szövegileg igazolt állomás.",
            "mapping_status": "textual_only",
            "display_on_map": False,
            "mapping_notes_hu": "Nincs biztonságosan feloldható aktív helyrekord.",
            "sequence_status": "explicit",
        },
    )
    for index, stop in enumerate(route["stops"], start=1):
        stop["order"] = index
    route["segments"] = []
    path = _write_temp_routes(payload)

    loaded = load_biblical_routes(routes_path=path)[0]
    textual_stop = loaded.stops[1]

    assert textual_stop.place_id is None
    assert textual_stop.mapping_status == "textual_only"
    assert textual_stop.display_on_map is False
    assert textual_stop.mapping_notes_hu


def test_textual_only_stop_validation_rejects_bad_mapping_contract() -> None:
    payload = _route_payload()
    payload[0]["stops"][0]["mapping_status"] = "textual_only"
    payload[0]["stops"][0]["display_on_map"] = True
    payload[0]["stops"][0]["place_id"] = None
    path = _write_temp_routes(payload)

    exc = _assert_raises(BiblicalRouteDataError, load_biblical_routes, routes_path=path)

    assert "textual_only stop" in str(exc)


def test_mapped_stop_without_place_id_is_rejected() -> None:
    payload = _route_payload()
    payload[0]["stops"][0]["place_id"] = None
    path = _write_temp_routes(payload)

    exc = _assert_raises(BiblicalRouteDataError, load_biblical_routes, routes_path=path)

    assert "mapped stop must define place_id" in str(exc)


def test_invalid_segment_stop_reference_is_rejected() -> None:
    payload = _route_payload()
    payload[0]["segments"][0]["to_stop_id"] = "missing_stop"
    path = _write_temp_routes(payload)
    exc = _assert_raises(BiblicalRouteDataError, load_biblical_routes, routes_path=path)
    assert "unknown to_stop_id" in str(exc)


def test_unknown_certainty_is_rejected() -> None:
    payload = _route_payload()
    payload[0]["stops"][0]["certainty"] = "absolutely"
    path = _write_temp_routes(payload)
    exc = _assert_raises(BiblicalRouteDataError, load_biblical_routes, routes_path=path)
    assert "Unknown stops.certainty" in str(exc)


def test_unknown_geometry_status_is_rejected() -> None:
    payload = _route_payload()
    payload[0]["segments"][0]["geometry_status"] = "teleported"
    path = _write_temp_routes(payload)
    exc = _assert_raises(BiblicalRouteDataError, load_biblical_routes, routes_path=path)
    assert "Unknown segments.geometry_status" in str(exc)


def test_legacy_place_id_resolves_only_in_compatibility_mode() -> None:
    payload = _route_payload()
    payload[0]["stops"][0]["place_id"] = "bethsaida_2"
    path = _write_temp_routes(payload)
    exc = _assert_raises(BiblicalRouteDataError, load_biblical_routes, routes_path=path)
    assert "legacy place_id" in str(exc)

    route = load_biblical_routes(routes_path=path, allow_legacy_place_ids=True)[0]
    assert route.stops[0].place_id == "bethsaida_1"


def test_invalid_passage_reference_is_rejected() -> None:
    payload = _route_payload()
    payload[0]["stops"][0]["passage_refs"] = ["Ez nem igehely"]
    path = _write_temp_routes(payload)
    exc = _assert_raises(BiblicalRouteDataError, load_biblical_routes, routes_path=path)
    assert "Invalid passage reference" in str(exc)


def test_cross_chapter_primary_reference_is_accepted() -> None:
    route = load_biblical_routes()[0]
    assert route.primary_passage_refs == ("ApCsel 13,1-14,28",)


def test_shared_passage_overlap_handles_chapter_and_book_code_aliases() -> None:
    assert passage_refs_overlap("ApCsel 13", "ACT 13,4")
    assert passage_refs_overlap("ACT 14", "ApCsel 14,21-23")
    assert passage_refs_overlap("ApCsel 13,1-14,28", "ACT 14,8")
    assert not passage_refs_overlap("ApCsel 13", "ACT 14,8")


def test_pauline_route_passage_windows_overlap_expected_chapters() -> None:
    routes = {route.route_id: route for route in load_biblical_routes()}

    assert any(
        passage_refs_overlap("ApCsel 16", reference)
        for stop in routes["paul_second_missionary_journey"].stops
        for reference in stop.passage_refs
    )
    assert any(
        passage_refs_overlap("ApCsel 19", reference)
        for stop in routes["paul_third_missionary_journey"].stops
        for reference in stop.passage_refs
    )
    assert any(
        passage_refs_overlap("ApCsel 27", reference)
        for stop in routes["paul_journey_to_rome"].stops
        for reference in stop.passage_refs
    )
    assert any(
        passage_refs_overlap("ApCsel 28", reference)
        for stop in routes["paul_journey_to_rome"].stops
        for reference in stop.passage_refs
    )
    assert any(
        passage_refs_overlap("ApCsel 18,1-18", reference)
        for stop in routes["paul_second_missionary_journey"].stops
        for reference in stop.passage_refs
    )
    assert not any(
        passage_refs_overlap("ApCsel 18,1-18", reference)
        for stop in routes["paul_third_missionary_journey"].stops
        for reference in stop.passage_refs
    )
    assert any(
        passage_refs_overlap("ApCsel 21,1-16", reference)
        for stop in routes["paul_third_missionary_journey"].stops
        for reference in stop.passage_refs
    )
    assert not any(
        passage_refs_overlap("ApCsel 21,1-16", reference)
        for stop in routes["paul_journey_to_rome"].stops
        for reference in stop.passage_refs
    )


def test_pauline_routes_validation_report_matches_loader() -> None:
    report = json.loads(VALIDATION_REPORT_PATH.read_text(encoding="utf-8"))
    report_by_id = {route["route_id"]: route for route in report["routes"]}

    for route in load_biblical_routes():
        if route.route_id not in report_by_id:
            continue
        item = report_by_id[route.route_id]
        assert item["stop_count"] == len(route.stops)
        assert item["segment_count"] == len(route.segments)
        assert item["unresolved_place_ids"] == []
        assert item["passage_errors"] == []
        assert len(item["place_resolution"]) == len(route.stops)


def test_loader_runs_without_streamlit_dependency() -> None:
    sys.modules.pop("streamlit", None)
    routes = load_biblical_routes()
    assert routes
    assert "streamlit" not in sys.modules


def test_patriarchal_routes_validation_report_matches_loader() -> None:
    report_path = ROOT / "data" / "biblical_routes" / "patriarchal_routes_validation_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report_by_id = {route["route_id"]: route for route in report["routes"]}
    routes = {route.route_id: route for route in load_biblical_routes()}

    assert set(report_by_id) == {"abraham_journey", "jacob_journeys", "joseph_geographical_arc"}
    for route_id, item in report_by_id.items():
        route = routes[route_id]
        assert item["stop_count"] == len(route.stops)
        assert item["segment_count"] == len(route.segments)
        assert item["unresolved_or_skipped_places"] == []
        assert item["mojibake_utf8_check"] == "passed"
        assert item["duplicate_geometry_check"] == "one_render_geometry_per_segment_expected"


def test_exodus_and_wilderness_routes_have_expected_counts_and_family_links() -> None:
    routes = {route.route_id: route for route in load_biblical_routes()}
    exodus = routes["exodus_egypt_to_sinai"]
    wilderness = routes["wilderness_sinai_to_moab"]

    assert exodus.route_family_id == "exodus_and_wilderness"
    assert exodus.family_name_hu == "A kivonulás és a pusztai vándorlás"
    assert exodus.route_sequence_order == 1
    assert exodus.previous_route_id is None
    assert exodus.next_route_id == "wilderness_sinai_to_moab"
    assert len(exodus.stops) == 14
    assert len(exodus.segments) == 11
    assert sum(1 for stop in exodus.stops if stop.mapping_status == "textual_only") == 1
    assert next(stop for stop in exodus.stops if stop.mapping_status == "textual_only").stop_id == "sea_crossing_textual"

    assert wilderness.route_family_id == "exodus_and_wilderness"
    assert wilderness.route_sequence_order == 2
    assert wilderness.previous_route_id == "exodus_egypt_to_sinai"
    assert wilderness.next_route_id is None
    assert len(wilderness.stops) == 31
    assert len(wilderness.segments) == 27
    assert {stop.journey_phase for stop in wilderness.stops} == {
        "Elindulás a Sínaitól",
        "Út Kádés felé",
        "A pusztai vándorlás évei",
        "Kádéstől Móábig",
    }


def test_exodus_wilderness_validation_report_matches_loader() -> None:
    report_path = ROOT / "data" / "biblical_routes" / "exodus_wilderness_validation_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    by_id = {route["route_id"]: route for route in report["routes"]}
    routes = {route.route_id: route for route in load_biblical_routes()}

    assert set(by_id) == {"exodus_egypt_to_sinai", "wilderness_sinai_to_moab"}
    for route_id, item in by_id.items():
        route = routes[route_id]
        assert item["total_textual_stops"] == len(route.stops)
        assert item["map_segment_count"] == len(route.segments)
        assert item["mojibake_utf8_check"] == "passed"
        assert item["duplicate_geometry_check"] == "one_render_geometry_per_segment_expected"
        assert item["legacy_place_ids"] == []
        assert item["zero_length_segments"] == []


def test_joshua_conquest_routes_have_expected_counts_and_family_links() -> None:
    routes = {route.route_id: route for route in load_biblical_routes()}
    central = routes["joshua_jordan_crossing_central_campaign"]
    southern = routes["joshua_southern_campaign"]
    northern = routes["joshua_northern_campaign"]

    assert central.route_category == "conquest_campaign"
    assert central.route_family_id == "joshua_conquest_campaigns"
    assert central.family_name_hu == "J\u00f3zsu\u00e9 honfoglal\u00e1si hadj\u00e1ratai"
    assert central.route_sequence_order == 1
    assert central.previous_route_id is None
    assert central.next_route_id == "joshua_southern_campaign"
    assert len(central.stops) == 10
    assert len(central.segments) == 9
    assert [stop.place_id for stop in central.stops] == [
        "shittim",
        "jericho_1",
        "jordan",
        "gilgal_1",
        "jericho_1",
        "ai_1",
        "bethel_1",
        "ai_1",
        "mount_ebal",
        "mount_gerizim",
    ]
    assert sum(1 for stop in central.stops if stop.mapping_status == "approximate") == 2

    assert southern.route_family_id == "joshua_conquest_campaigns"
    assert southern.route_sequence_order == 2
    assert southern.previous_route_id == "joshua_jordan_crossing_central_campaign"
    assert southern.next_route_id == "joshua_northern_campaign"
    assert len(southern.stops) == 15
    assert len(southern.segments) == 14
    assert southern.stops[9].place_id == "gezer"
    assert "kir\u00e1ly\u00e1nak beavatkoz\u00e1s\u00e1t" in (southern.stops[9].source_notes_hu or "")

    assert northern.route_family_id == "joshua_conquest_campaigns"
    assert northern.route_sequence_order == 3
    assert northern.previous_route_id == "joshua_southern_campaign"
    assert northern.next_route_id is None
    assert len(northern.stops) == 10
    assert len(northern.segments) == 8
    assert northern.stops[0].stop_id == "gilgal_northern_continuity"
    assert northern.stops[0].certainty == "possible"
    assert sum(1 for stop in northern.stops if stop.mapping_status == "approximate") == 2


def test_joshua_northern_route_uses_branch_segments_without_forced_linear_pursuit() -> None:
    route = {route.route_id: route for route in load_biblical_routes()}["joshua_northern_campaign"]
    pairs = {(segment.from_stop_id, segment.to_stop_id) for segment in route.segments}

    assert ("waters_merom_battle", "sidon_pursuit") in pairs
    assert ("waters_merom_battle", "misrephoth_maim_pursuit") in pairs
    assert ("waters_merom_battle", "valley_mizpeh_pursuit") in pairs
    assert ("sidon_pursuit", "misrephoth_maim_pursuit") not in pairs
    assert ("misrephoth_maim_pursuit", "valley_mizpeh_pursuit") not in pairs


def test_pauline_routes_have_family_navigation_links() -> None:
    routes = {route.route_id: route for route in load_biblical_routes()}
    first = routes["paul_first_missionary_journey"]
    second = routes["paul_second_missionary_journey"]
    third = routes["paul_third_missionary_journey"]
    rome = routes["paul_journey_to_rome"]

    assert first.route_family_id == "pauline_missionary_journeys"
    assert first.family_name_hu == "Pál missziói útjai"
    assert first.route_sequence_order == 1
    assert first.previous_route_id is None
    assert first.next_route_id == "paul_second_missionary_journey"

    assert second.route_family_id == "pauline_missionary_journeys"
    assert second.route_sequence_order == 2
    assert second.previous_route_id == "paul_first_missionary_journey"
    assert second.next_route_id == "paul_third_missionary_journey"

    assert third.route_sequence_order == 3
    assert third.previous_route_id == "paul_second_missionary_journey"
    assert third.next_route_id == "paul_journey_to_rome"

    assert rome.route_sequence_order == 4
    assert rome.previous_route_id == "paul_third_missionary_journey"
    assert rome.next_route_id is None
    assert rome.review_status == "draft"


def test_patriarchal_routes_have_family_navigation_links() -> None:
    routes = {route.route_id: route for route in load_biblical_routes()}
    abraham = routes["abraham_journey"]
    jacob = routes["jacob_journeys"]
    joseph = routes["joseph_geographical_arc"]

    assert abraham.route_family_id == "patriarchal_journeys"
    assert abraham.family_name_hu == "Pátriárkák földrajzi ívei"
    assert abraham.route_sequence_order == 1
    assert abraham.previous_route_id is None
    assert abraham.next_route_id == "jacob_journeys"

    assert jacob.route_sequence_order == 2
    assert jacob.previous_route_id == "abraham_journey"
    assert jacob.next_route_id == "joseph_geographical_arc"

    assert joseph.route_sequence_order == 3
    assert joseph.previous_route_id == "jacob_journeys"
    assert joseph.next_route_id is None


def test_joshua_conquest_validation_report_matches_loader() -> None:
    report = json.loads(JOSHUA_VALIDATION_REPORT_PATH.read_text(encoding="utf-8"))
    by_id = {route["route_id"]: route for route in report["routes"]}
    routes = {route.route_id: route for route in load_biblical_routes()}

    assert set(by_id) == {
        "joshua_jordan_crossing_central_campaign",
        "joshua_southern_campaign",
        "joshua_northern_campaign",
    }
    assert any("Gilg\u00e1l" in note for note in report["special_notes_hu"])
    for route_id, item in by_id.items():
        route = routes[route_id]
        assert item["stop_count"] == len(route.stops)
        assert item["segment_count"] == len(route.segments)
        assert item["mojibake_utf8_check"] == "passed"
        assert item["duplicate_geometry_check"] == "one_render_geometry_per_segment_expected"
        assert item["legacy_place_ids"] == []
        assert item["zero_length_segments"] == []
        assert len(item["place_resolution"]) == len(route.stops)
