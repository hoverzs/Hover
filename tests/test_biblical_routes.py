from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biblical_routes import BiblicalRouteDataError, load_biblical_routes


ROUTES_PATH = ROOT / "data" / "biblical_routes" / "biblical_routes.json"


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
    assert len(routes) == 1
    route = routes[0]
    assert route.route_id == "paul_first_missionary_journey"
    assert route.name_hu == "Pál első missziói útja"
    assert route.route_category == "missionary_journey"
    assert route.primary_passage_refs == ("ApCsel 13,1-14,28",)
    assert len(route.stops) == 15
    assert len(route.segments) == 14


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


def test_loader_runs_without_streamlit_dependency() -> None:
    sys.modules.pop("streamlit", None)
    routes = load_biblical_routes()
    assert routes
    assert "streamlit" not in sys.modules
