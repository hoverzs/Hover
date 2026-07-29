from __future__ import annotations

import importlib
import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
APP_SOURCE = ROOT / "app.py"
BIBLE_TEXT_UI_SOURCE = ROOT / "bible_text_ui.py"

from biblical_map_data import (
    BIBLICAL_MAP_PLACES,
    BIBLICAL_PLACES_CATALOG_PATH,
    BiblicalMapDataError,
    BiblicalMapSource,
    PILOT_PLACES_PATH,
    SOURCES_PATH,
    get_all_biblical_places,
    get_biblical_place,
    load_biblical_places,
    load_pilot_biblical_places,
    load_biblical_sources,
    validate_place_record,
)
from biblical_map_ui import (
    CATALOG_SEARCH_PICK_KEY,
    CATALOG_SEARCH_QUERY_KEY,
    SELECTED_PLACE_SELECTBOX_KEY,
    SELECTED_PLACE_ID_KEY,
    _render_place_card,
    _render_short_sources,
    compact_sources_html,
    compact_sources_markdown,
    dedupe_sources,
    display_place_name,
    fallback_place_description,
    map_rows,
    normalize_place_search_text,
    passage_linked_places,
    place_option_labels,
    place_selectbox_options,
    render_biblical_map_prototype,
    resolve_selected_place_id,
    search_biblical_places,
    selected_place_for_session,
)
from biblical_map_passages import (
    BIBLICAL_PASSAGE_PLACE_LINKS,
    MAP_LAST_PROCESSED_REFERENCE_KEY,
    MAP_SELECTION_SOURCE_AUTO,
    MAP_SELECTION_SOURCE_KEY,
    MAP_SELECTION_SOURCE_MANUAL,
    MAP_SELECTION_SOURCE_UNMATCHED,
    PASSAGE_LINK_SOURCE_NOTE,
    PASSAGE_LINK_TYPE_PRIMARY_EVENT_LOCATION,
    apply_passage_place_selection,
    find_place_links_for_passage,
    find_primary_place_for_passage,
    validate_passage_place_links,
)


class _FakeContext:
    def __init__(self, fake_st):
        self.fake_st = fake_st

    def __enter__(self):
        return self.fake_st

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeStreamlit:
    def __init__(self, *, fail_map: bool = False, selectbox_choice: str | None = None):
        self.session_state = {}
        self.fail_map = fail_map
        self.selectbox_choice = selectbox_choice
        self.captions = []
        self.errors = []
        self.expanders = []
        self.infos = []
        self.markdowns = []
        self.maps = []
        self.radios = []
        self.selectboxes = []
        self.text_inputs = []
        self.warnings = []

    def expander(self, label, expanded=False):
        self.expanders.append((label, expanded))
        return _FakeContext(self)

    def columns(self, spec, gap=None):
        return [_FakeContext(self), _FakeContext(self)]

    def markdown(self, body, **kwargs):
        self.markdowns.append(body)

    def caption(self, body):
        self.captions.append(body)

    def error(self, body):
        self.errors.append(body)

    def info(self, body):
        self.infos.append(body)

    def warning(self, body):
        self.warnings.append(body)

    def map(self, rows, **kwargs):
        if self.fail_map:
            raise TypeError("unsupported st.map parameter")
        self.maps.append((rows, kwargs))

    def radio(self, label, options, index=0, **kwargs):
        self.radios.append((label, options, index, kwargs))
        return options[index]

    def text_input(self, label, **kwargs):
        self.text_inputs.append((label, kwargs))
        key = kwargs.get("key")
        if key and key not in self.session_state:
            self.session_state[key] = ""
        return self.session_state.get(key, "")

    def selectbox(self, label, options, index=0, **kwargs):
        self.selectboxes.append((label, options, index, kwargs))
        key = kwargs.get("key")
        if self.selectbox_choice is not None and self.selectbox_choice in options:
            chosen = self.selectbox_choice
        else:
            chosen = self.session_state.get(key) if key else None
            if chosen not in options:
                chosen = options[index]
        if key:
            self.session_state[key] = chosen
        return chosen


def test_biblical_place_ids_are_unique() -> None:
    ids = [place.place_id for place in BIBLICAL_MAP_PLACES]
    assert len(ids) > 100
    assert len(ids) == len(set(ids))


def test_full_catalog_loads_and_pilot_remains_override_layer() -> None:
    assert PILOT_PLACES_PATH.exists()
    assert BIBLICAL_PLACES_CATALOG_PATH.exists()
    assert SOURCES_PATH.exists()
    raw_places = json.loads(PILOT_PLACES_PATH.read_text(encoding="utf-8"))
    raw_catalog = json.loads(BIBLICAL_PLACES_CATALOG_PATH.read_text(encoding="utf-8"))
    raw_sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    data_source = (ROOT / "biblical_map_data.py").read_text(encoding="utf-8")

    assert isinstance(raw_places, list)
    assert isinstance(raw_catalog, list)
    assert isinstance(raw_sources, list)
    assert len(raw_places) == 10
    assert len(load_pilot_biblical_places()) == 10
    assert len(load_biblical_places()) == len(raw_catalog) > 100
    assert len(get_all_biblical_places()) == len(raw_catalog) > 100
    assert "BIBLICAL_MAP_PLACES: tuple[BiblicalPlace, ...] = (" not in data_source
    assert data_source.count("BiblicalPlace(") == 1


def test_sources_json_loads_and_demo_source_is_present() -> None:
    sources = load_biblical_sources()
    by_id = {source.source_id: source for source in sources}

    assert "manual_demo_v1" in by_id
    assert by_id["manual_demo_v1"].source_type == "manual_demo"
    assert by_id["manual_demo_v1"].reliability_tier == "prototype_only"
    assert by_id["openbible_geocoding_cc_by_4_0"].license == "CC-BY-4.0"
    assert by_id["pleiades_corinth_570182"].reliability_tier == "scholarly_curated"
    assert (
        by_id["ascsa_ancient_corinth_history"].source_type
        == "scholarly_archaeological_reference"
    )
    assert by_id["hellenic_ministry_ancient_corinth"].provider == "Hellenic Ministry of Culture"
    assert by_id["pleiades_ephesus_599612"].reliability_tier == "scholarly_curated"
    assert by_id["unesco_ephesus_1018"].provider == "UNESCO World Heritage Centre"
    assert (
        by_id["turkiye_ephesus_archaeological_site"].source_type
        == "official_archaeological_site"
    )


def test_biblical_places_have_valid_names_and_coordinates() -> None:
    names = {place.name_hu for place in BIBLICAL_MAP_PLACES}
    assert {
        "Jeruzsálem",
        "Názáret",
        "Kapernaum",
        "Korinthus",
        "Efezus",
        "Athén",
        "Filippi",
        "Thesszalonika",
        "Antiókhia",
        "Róma",
    }.issubset(names)
    for place in BIBLICAL_MAP_PLACES:
        assert place.name_hu.strip()
        assert place.place_id.strip()
        assert validate_place_record(place)
        assert -90 <= place.latitude <= 90
        assert -180 <= place.longitude <= 180
        assert place.geometry_type == "point"
        assert place.coordinate_source_id
        assert place.source_ids


def test_biblical_map_has_exactly_one_primary_place() -> None:
    primary_places = [place for place in BIBLICAL_MAP_PLACES if place.is_primary]
    assert len(primary_places) == 1
    assert primary_places[0].place_id == "jerusalem"


def test_hungarian_accents_load_from_json() -> None:
    jerusalem = get_biblical_place("jerusalem")
    nazareth = get_biblical_place("nazareth")

    assert jerusalem is not None
    assert nazareth is not None
    assert jerusalem.name_hu == "Jeruzsálem"
    assert nazareth.name_hu == "Názáret"


def test_corinth_pilot_record_contains_source_marked_details() -> None:
    corinth = get_biblical_place("corinth")

    assert corinth is not None
    assert corinth.identification_status == "certain"
    assert corinth.modern_country == "Görögország"
    assert "Κόρινθος" in corinth.original_names
    assert corinth.coordinate_source_id == "pleiades_corinth_570182"
    assert corinth.pleiades_id == "570182"
    assert corinth.translation_status == "not_required"
    assert corinth.translation_method == "human_authored_source_synthesis"
    assert corinth.review_status == "needs_review"
    assert set(corinth.source_ids) >= {
        "pleiades_corinth_570182",
        "ascsa_ancient_corinth_history",
        "hellenic_ministry_ancient_corinth",
    }
    assert len(corinth.exegetical_notes) == 1
    assert corinth.exegetical_notes[0].passage_reference == "ApCsel 18,1–18"


def test_non_corinth_records_are_import_reviewed_shells() -> None:
    by_id = {place.place_id: place for place in BIBLICAL_MAP_PLACES}

    assert "openbible_geocoding_cc_by_4_0" in by_id["jerusalem"].source_ids
    assert by_id["nazareth"].coordinate_source_id == "openbible_geocoding_cc_by_4_0"
    assert by_id["capernaum"].review_status == "needs_review"
    assert by_id["athens"].place_id == "athens"
    assert by_id["antioch_syria"].name_hu == "Antiókhia"


def test_ephesus_pilot_record_contains_source_marked_details() -> None:
    ephesus = get_biblical_place("ephesus")

    assert ephesus is not None
    assert ephesus.identification_status == "certain"
    assert ephesus.modern_country == "Törökország"
    assert "Ἔφεσος" in ephesus.original_names
    assert ephesus.coordinate_source_id == "pleiades_ephesus_599612"
    assert ephesus.pleiades_id == "599612"
    assert ephesus.translation_status == "not_required"
    assert ephesus.translation_method == "human_authored_source_synthesis"
    assert ephesus.review_status == "needs_review"
    assert set(ephesus.source_ids) >= {
        "pleiades_ephesus_599612",
        "unesco_ephesus_1018",
        "turkiye_ephesus_archaeological_site",
    }
    assert len(ephesus.exegetical_notes) == 1
    assert ephesus.exegetical_notes[0].passage_reference == "ApCsel 19,1–41"


def test_missing_optional_background_fields_do_not_break_loading() -> None:
    raw_places = json.loads(PILOT_PLACES_PATH.read_text(encoding="utf-8"))
    raw_places[0].pop("history_hu", None)
    raw_places[0]["unexpected_optional_field"] = "ignored"
    with tempfile.TemporaryDirectory() as tmp_dir:
        places_path = Path(tmp_dir) / "places.json"
        places_path.write_text(json.dumps(raw_places, ensure_ascii=False), encoding="utf-8")
        places = load_biblical_places(places_path=places_path)

    by_id = {place.place_id: place for place in places}
    assert by_id["jerusalem"].history_hu is None
    assert by_id["jerusalem"].name_hu == "Jeruzsálem"


def test_missing_required_field_raises_validation_error() -> None:
    raw_places = json.loads(PILOT_PLACES_PATH.read_text(encoding="utf-8"))
    raw_places[0].pop("place_id", None)
    with tempfile.TemporaryDirectory() as tmp_dir:
        places_path = Path(tmp_dir) / "places.json"
        places_path.write_text(json.dumps(raw_places, ensure_ascii=False), encoding="utf-8")
        try:
            load_biblical_places(places_path=places_path)
        except BiblicalMapDataError as exc:
            assert "place_id" in str(exc)
        else:
            raise AssertionError("Missing required field did not raise BiblicalMapDataError.")


def test_unknown_selected_place_id_falls_back_to_none() -> None:
    session_state = {SELECTED_PLACE_ID_KEY: "unknown-place"}
    assert resolve_selected_place_id(session_state) is None


def test_existing_selected_place_id_is_preserved() -> None:
    session_state = {SELECTED_PLACE_ID_KEY: "ephesus"}
    assert resolve_selected_place_id(session_state) == "ephesus"


def test_selected_place_for_session_returns_primary_without_selection() -> None:
    assert selected_place_for_session({}).place_id == "jerusalem"


def test_map_rows_mark_primary_or_selected_as_larger() -> None:
    rows = map_rows("ephesus")
    by_id = {row["place_id"]: row for row in rows}
    assert by_id["jerusalem"]["size"] > by_id["nazareth"]["size"]
    assert by_id["ephesus"]["size"] > by_id["nazareth"]["size"]


def test_demo_passage_links_have_valid_shape_and_places() -> None:
    valid_ids = {place.place_id for place in BIBLICAL_MAP_PLACES}

    assert len(BIBLICAL_PASSAGE_PLACE_LINKS) >= 10
    for link in BIBLICAL_PASSAGE_PLACE_LINKS:
        assert link.normalized_reference.strip()
        assert link.place_id in valid_ids
        assert link.link_type == PASSAGE_LINK_TYPE_PRIMARY_EVENT_LOCATION
        assert link.reason_hu.strip()
        assert link.source_note.strip()
    assert validate_passage_place_links() == BIBLICAL_PASSAGE_PLACE_LINKS


def test_every_place_source_reference_resolves() -> None:
    source_ids = {source.source_id for source in load_biblical_sources()}

    for place in BIBLICAL_MAP_PLACES:
        assert place.coordinate_source_id in source_ids
        assert set(place.source_ids).issubset(source_ids)
        for note in place.exegetical_notes:
            assert set(note.source_ids).issubset(source_ids)


def test_demo_passages_resolve_to_expected_places() -> None:
    assert find_primary_place_for_passage("ApCsel 18,1–18") == "corinth"
    assert find_primary_place_for_passage("ApCsel 18,1–5") == "corinth"
    assert find_primary_place_for_passage("Ef 1,1–14") == "ephesus"
    assert find_primary_place_for_passage("ApCsel 19,1–41") == "ephesus"
    assert find_primary_place_for_passage("ApCsel 19,1–10") == "ephesus"
    assert find_primary_place_for_passage("ApCsel 19,21–41") == "ephesus"
    assert find_primary_place_for_passage("ApCsel 19") is None
    assert find_primary_place_for_passage("Mt 2,23") == "nazareth"
    assert find_primary_place_for_passage("Mk 1,21–28") == "capernaum"
    assert find_primary_place_for_passage("ApCsel 2,1–13") == "jerusalem"
    assert find_primary_place_for_passage("ApCsel 17,16–34") == "athens"
    assert find_primary_place_for_passage("ApCsel 16,11–40") == "philippi"
    assert find_primary_place_for_passage("ApCsel 17,1–9") == "thessalonica"
    assert find_primary_place_for_passage("ApCsel 11,19–30") == "antioch_syria"
    assert find_primary_place_for_passage("ApCsel 28,11–31") == "rome"


def test_unknown_empty_and_invalid_passages_do_not_resolve() -> None:
    assert find_primary_place_for_passage(None) is None
    assert find_primary_place_for_passage("") is None
    assert find_primary_place_for_passage("not a reference") is None
    assert find_primary_place_for_passage("Jn 3,16") is None
    assert find_primary_place_for_passage("ApCsel 18") is None


def test_all_resolved_place_ids_exist_in_prototype_places() -> None:
    valid_ids = {place.place_id for place in BIBLICAL_MAP_PLACES}

    for link in BIBLICAL_PASSAGE_PLACE_LINKS:
        assert find_primary_place_for_passage(link.normalized_reference) in valid_ids


def test_auto_selection_updates_for_new_supported_reference() -> None:
    state = {}

    apply_passage_place_selection(
        state,
        "ApCsel 18,1-18",
        selected_place_key=SELECTED_PLACE_ID_KEY,
    )

    assert state[SELECTED_PLACE_ID_KEY] == "corinth"
    assert state[MAP_SELECTION_SOURCE_KEY] == MAP_SELECTION_SOURCE_AUTO
    assert state[MAP_LAST_PROCESSED_REFERENCE_KEY] == "ApCsel 18,1–18"


def test_manual_selection_is_preserved_for_same_reference() -> None:
    state = {}
    apply_passage_place_selection(
        state,
        "ApCsel 18,1-18",
        selected_place_key=SELECTED_PLACE_ID_KEY,
    )
    state[SELECTED_PLACE_ID_KEY] = "ephesus"
    state[MAP_SELECTION_SOURCE_KEY] = MAP_SELECTION_SOURCE_MANUAL

    apply_passage_place_selection(
        state,
        "ApCsel 18,1-18",
        selected_place_key=SELECTED_PLACE_ID_KEY,
    )

    assert state[SELECTED_PLACE_ID_KEY] == "ephesus"
    assert state[MAP_SELECTION_SOURCE_KEY] == MAP_SELECTION_SOURCE_MANUAL


def test_new_supported_reference_can_override_manual_selection() -> None:
    state = {
        SELECTED_PLACE_ID_KEY: "ephesus",
        MAP_SELECTION_SOURCE_KEY: MAP_SELECTION_SOURCE_MANUAL,
        MAP_LAST_PROCESSED_REFERENCE_KEY: "ApCsel 18,1–18",
    }

    apply_passage_place_selection(
        state,
        "Mk 1,21-28",
        selected_place_key=SELECTED_PLACE_ID_KEY,
    )

    assert state[SELECTED_PLACE_ID_KEY] == "capernaum"
    assert state[MAP_SELECTION_SOURCE_KEY] == MAP_SELECTION_SOURCE_AUTO


def test_new_unsupported_reference_does_not_pick_arbitrary_place() -> None:
    state = {
        SELECTED_PLACE_ID_KEY: "ephesus",
        MAP_SELECTION_SOURCE_KEY: MAP_SELECTION_SOURCE_MANUAL,
        MAP_LAST_PROCESSED_REFERENCE_KEY: "ApCsel 18,1–18",
    }

    apply_passage_place_selection(
        state,
        "Jn 3,16",
        selected_place_key=SELECTED_PLACE_ID_KEY,
    )

    assert state[SELECTED_PLACE_ID_KEY] == "ephesus"
    assert state[MAP_SELECTION_SOURCE_KEY] == MAP_SELECTION_SOURCE_UNMATCHED


def test_ui_module_imports_without_secret_or_network_access() -> None:
    module = importlib.import_module("biblical_map_ui")
    assert callable(module.render_biblical_map_prototype)


def test_app_imports_biblical_map_renderer() -> None:
    source = APP_SOURCE.read_text(encoding="utf-8")

    assert "from biblical_map_ui import render_biblical_map_prototype" in source


def test_map_call_is_in_igehely_panel_after_overview_button() -> None:
    source = APP_SOURCE.read_text(encoding="utf-8")
    helper_start = source.index("def render_current_biblical_map_prototype() -> None:")
    helper_end = source.index("def render_igehely_panel(", helper_start)
    helper_source = source[helper_start:helper_end]

    panel_start = source.index("def render_igehely_panel() -> None:")
    panel_end = source.index("def render_original_text_panel() -> None:", panel_start)
    panel_source = source[panel_start:panel_end]

    workshop_start = source.index("def render_textus_workshop_shell() -> None:")
    workshop_end = source.index(
        'if st.session_state.get("ui_mode") not in ("quick", "workshop", "sermon_workshop"):',
        workshop_start,
    )
    workshop_source = source[workshop_start:workshop_end]

    button_index = panel_source.index('"Bibliai háttér összegzése"')
    map_index = panel_source.index("render_current_biblical_map_prototype()")
    overview_result_index = panel_source.index(
        'if st.session_state.get("overview"):',
        button_index,
    )

    assert button_index < map_index < overview_result_index
    assert "render_current_biblical_map_prototype()" not in workshop_source
    assert 'st.caption("Bibliai térkép renderpont elérve.")' not in source
    assert "SMART-MAP BIZTOS RENDERPONT ELÉRVE" not in source
    assert source.count("render_current_biblical_map_prototype()") == 2
    assert 'st.caption("Bibliai térkép modul")' not in source
    assert "render_biblical_map_prototype(passage_reference=passage_reference)" in helper_source
    assert "or None" in helper_source
    assert '(st.session_state.get("last_igehely") or "").strip()' in helper_source
    assert '(st.session_state.get("igehely_input") or "").strip()' in helper_source


def test_bible_text_editor_has_no_map_callback_or_renderer() -> None:
    bible_text_source = BIBLE_TEXT_UI_SOURCE.read_text(encoding="utf-8")

    assert "Callable" not in bible_text_source
    assert "after_bible_text" not in bible_text_source
    assert "render_biblical_map_prototype" not in bible_text_source


def test_exactly_one_active_ui_map_render_call() -> None:
    source = APP_SOURCE.read_text(encoding="utf-8")
    map_ui_source = (ROOT / "biblical_map_ui.py").read_text(encoding="utf-8")
    render_fn_start = map_ui_source.index("def render_biblical_map_prototype(")
    expander_index = map_ui_source.index(
        'with st.expander("Bibliai térkép – prototípus", expanded=False):',
        render_fn_start,
    )
    before_expander = map_ui_source[render_fn_start:expander_index]

    assert source.count("render_biblical_map_prototype(") == 1
    assert "SMART-MAP RENDERFÜGGVÉNY ELINDULT" not in map_ui_source
    assert "Első izolált prototípus" not in map_ui_source
    assert "Még nincs automatikus kapcsolat" not in map_ui_source
    assert "st.radio(" not in map_ui_source
    assert "SELECTED_PLACE_RADIO_KEY" not in map_ui_source
    assert "st.selectbox(" in map_ui_source
    assert map_ui_source.count("Bibliai térkép – prototípus") == 1
    assert "return" not in before_expander
    assert "passage_reference" not in before_expander.split("st_module", 1)[-1]
    assert "if not places" not in before_expander
    assert "try:" not in before_expander


def test_render_accepts_missing_passage_reference_without_early_return() -> None:
    fake_st = _FakeStreamlit()

    render_biblical_map_prototype(passage_reference=None, st_module=fake_st)

    assert fake_st.errors == []
    assert ("Bibliai térkép – prototípus", False) in fake_st.expanders
    assert "A térképes prototípus renderelése aktív." not in fake_st.captions
    assert "Aktuális igerész még nincs megadva." in fake_st.captions
    assert fake_st.maps
    assert fake_st.text_inputs
    assert fake_st.text_inputs[0][0] == "Másik bibliai hely keresése"
    assert not any(label == "Aktuális igerész helyszínei" for label, *_ in fake_st.selectboxes)
    assert fake_st.radios == []
    assert any(
        "A térkép az aktuális igerészhez kapcsolódó bibliai helyszíneket jeleníti meg."
        in body
        for body in fake_st.markdowns
    )
    assert any(
        "Válassz helyszínt a keresőből" in caption for caption in fake_st.captions
    )


def test_render_auto_selects_linked_place_and_shows_status() -> None:
    fake_st = _FakeStreamlit()

    render_biblical_map_prototype(passage_reference="ApCsel 18,1-5", st_module=fake_st)

    assert fake_st.session_state[SELECTED_PLACE_ID_KEY] == "corinth"
    assert fake_st.session_state[MAP_SELECTION_SOURCE_KEY] == MAP_SELECTION_SOURCE_AUTO
    assert fake_st.infos == [
        "A helyszín a megadott igerész alapján automatikusan lett kiválasztva: Korinthus."
    ]
    passage_boxes = [
        (label, options)
        for label, options, *_ in fake_st.selectboxes
        if label == "Aktuális igerész helyszínei"
    ]
    assert passage_boxes
    assert passage_boxes[0][1][0] == "corinth"
    assert fake_st.text_inputs[0][0] == "Másik bibliai hely keresése"
    assert fake_st.radios == []
    assert any("Korinthus" in body for body in fake_st.markdowns)


def test_passage_place_selector_only_lists_linked_places() -> None:
    acts_18_places = [place.place_id for place in passage_linked_places("ApCsel 18,1-18")]
    acts_16_places = [place.place_id for place in passage_linked_places("ApCsel 16,11-40")]

    assert acts_18_places[0] == "corinth"
    assert len(acts_18_places) > 1
    assert acts_16_places[0] == "philippi"
    assert len(acts_16_places) > 1
    assert passage_linked_places("Jn 3,16") == ()

    fake_st = _FakeStreamlit()
    render_biblical_map_prototype(passage_reference="ApCsel 16,11-40", st_module=fake_st)
    passage_boxes = [
        (label, options)
        for label, options, *_ in fake_st.selectboxes
        if label == "Aktuális igerész helyszínei"
    ]
    assert passage_boxes
    assert passage_boxes[0][1][0] == "philippi"
    assert len(passage_boxes[0][1]) == len(acts_16_places)
    assert set(place.place_id for place in BIBLICAL_MAP_PLACES) - {"philippi"}
    assert all(
        len(options) < len(BIBLICAL_MAP_PLACES)
        for _, options, *_ in fake_st.selectboxes
        if _ != "Keresési találatok"
    )


def test_specific_verse_does_not_inherit_whole_passage_place_list() -> None:
    whole_passage = [place.place_id for place in passage_linked_places("ApCsel 18,1-18")]
    single_verse = [place.place_id for place in passage_linked_places("ApCsel 18,5")]

    assert whole_passage[0] == "corinth"
    assert single_verse[0] == "corinth"
    assert len(single_verse) < len(whole_passage)
    assert set(single_verse) != set(whole_passage)


def test_same_named_distinct_places_are_not_merged() -> None:
    bethel_hits = search_biblical_places("bethel", limit=10)
    bethel_ids = {place.place_id for place in bethel_hits}

    assert {"bethel_1", "bethel_2", "bethel_3"}.issubset(bethel_ids)


def test_render_corinth_details_sources_and_quality_sections() -> None:
    fake_st = _FakeStreamlit()

    render_biblical_map_prototype(passage_reference="ApCsel 18,1-18", st_module=fake_st)

    assert ("Részletes háttér", False) in fake_st.expanders
    assert ("Exegetikai megjegyzések", False) in fake_st.expanders
    assert ("Források és adatminőség", False) not in fake_st.expanders
    joined_markdown = "\n".join(fake_st.markdowns)
    joined_captions = "\n".join(fake_st.captions)
    rendered_text = joined_markdown + "\n" + joined_captions

    assert "Korinthus a Korinthoszi-földszoros mellett" in joined_markdown
    assert "Korinthus jelentősége Pál szolgálatában" in joined_markdown
    assert "Adatminőség: biztos helyazonosítás · szakmai ellenőrzésre vár" in rendered_text
    assert "textus-biblical-map-sources" in joined_markdown
    assert "textus-biblical-map-quality" in joined_markdown
    assert 'href="https://pleiades.stoa.org/places/570182"' in joined_markdown
    source_blocks = [
        body
        for body in fake_st.markdowns
        if body.strip().startswith('<div class="textus-biblical-map-sources">')
    ]
    assert source_blocks
    assert all(block.count(">Pleiades</a>") == 1 for block in source_blocks)
    assert (
        'href="https://www.ascsa.edu.gr/excavations/ancient-corinth/'
        'about-the-excavations-1/history-timeline"'
    ) in joined_markdown
    assert ">American School of Classical Studies at Athens</a>" in joined_markdown
    assert 'href="https://odysseus.culture.gr/h/3/eh351.jsp?obj_id=2388"' in joined_markdown
    assert ">Hellenic Ministry of Culture</a>" in joined_markdown
    assert " · " in joined_markdown
    assert "**Források**\n" not in joined_markdown
    assert "- [Pleiades]" not in joined_markdown
    assert "Pleiades ID: 570182" not in rendered_text
    assert "Licenc:" not in rendered_text
    assert "Minősítés:" not in rendered_text
    assert "Attribution:" not in rendered_text
    assert "Fordítás" not in rendered_text
    assert "human_authored_source_synthesis" not in rendered_text
    assert "scholarly_curated" not in rendered_text
    assert "source_type" not in rendered_text
    assert "None" not in rendered_text
    assert "null" not in rendered_text


def test_render_ephesus_details_use_existing_short_source_ui() -> None:
    fake_st = _FakeStreamlit()

    render_biblical_map_prototype(passage_reference="ApCsel 19,1-41", st_module=fake_st)

    assert fake_st.session_state[SELECTED_PLACE_ID_KEY] == "ephesus"
    assert ("Részletes háttér", False) in fake_st.expanders
    assert ("Exegetikai megjegyzések", False) in fake_st.expanders
    assert ("Források és adatminőség", False) not in fake_st.expanders
    joined_markdown = "\n".join(fake_st.markdowns)
    joined_captions = "\n".join(fake_st.captions)
    rendered_text = joined_markdown + "\n" + joined_captions

    assert "Efezus Kis-Ázsia egyik legjelentősebb" in joined_markdown
    assert "Az evangélium hatása Efezus vallási és gazdasági rendszerére" in joined_markdown
    assert "Adatminőség: biztos helyazonosítás · szakmai ellenőrzésre vár" in rendered_text
    assert "textus-biblical-map-sources" in joined_markdown
    assert 'href="https://pleiades.stoa.org/places/599612"' in joined_markdown
    assert ">Pleiades</a>" in joined_markdown
    assert 'href="https://whc.unesco.org/en/list/1018/"' in joined_markdown
    assert ">UNESCO World Heritage Centre</a>" in joined_markdown
    assert (
        "href=\"https://muze.gov.tr/Language/Index/EN?url=%2Fmuze-detay"
        "%3Fsectionid%3Defs01%26distid%3Defs\""
    ) in joined_markdown
    assert ">Republic of Türkiye Ministry of Culture and Tourism</a>" in joined_markdown
    assert " · " in joined_markdown
    assert "- [Pleiades]" not in joined_markdown
    assert "Pleiades ID: 599612" not in rendered_text
    assert "Licenc:" not in rendered_text
    assert "Minősítés:" not in rendered_text
    assert "Attribution:" not in rendered_text
    assert "human_authored_source_synthesis" not in rendered_text
    assert "scholarly_curated" not in rendered_text


def test_real_source_place_cards_do_not_show_demo_source_note() -> None:
    for reference, place_name in [
        ("ApCsel 17,16-34", "Athén"),
        ("ApCsel 16,11-40", "Filippi"),
        ("ApCsel 28,11-31", "Róma"),
        ("ApCsel 18,1-18", "Korinthus"),
        ("ApCsel 19,1-41", "Efezus"),
    ]:
        fake_st = _FakeStreamlit()

        render_biblical_map_prototype(passage_reference=reference, st_module=fake_st)

        joined_markdown = "\n".join(fake_st.markdowns)
        assert place_name in joined_markdown
        assert "Forrás:</strong> demonstrációs adat" not in joined_markdown


def test_manual_demo_source_note_can_render_for_manual_only_records() -> None:
    fake_st = _FakeStreamlit()
    manual_place = replace(
        BIBLICAL_MAP_PLACES[0],
        source_ids=("manual_demo_v1",),
        coordinate_source_id="manual_demo_v1",
    )

    _render_place_card(fake_st, manual_place, "")

    assert any("Forrás:</strong> demonstrációs adat" in body for body in fake_st.markdowns)


def test_place_selectbox_options_prioritize_auto_place_and_sort_the_rest() -> None:
    base = BIBLICAL_MAP_PLACES[0]
    dummy_places = tuple(
        replace(
            base,
            place_id=f"dummy_{index:03d}",
            name_hu=name,
            is_primary_demo_place=False,
        )
        for index, name in enumerate(["Zéta", "Alfa", "Mű", "Béta"] * 75)
    )
    auto_place = replace(
        base,
        place_id="auto_place",
        name_hu="Kiemelt hely",
        is_primary_demo_place=False,
    )
    places = dummy_places + (auto_place,) + dummy_places[:10]

    options = place_selectbox_options(places, "auto_place")
    labels = place_option_labels(places)

    assert options[0] == "auto_place"
    assert options.count("auto_place") == 1
    assert len(options) == len(set(options))
    assert options[1:] == sorted(options[1:], key=lambda place_id: (labels[place_id].casefold(), place_id))
    assert labels["auto_place"] == "Kiemelt hely"
    assert "auto_place" not in labels["auto_place"]


def test_short_source_list_omits_heading_when_empty_and_handles_missing_url() -> None:
    fake_st = _FakeStreamlit()

    _render_short_sources(fake_st, [])
    _render_short_sources(
        fake_st,
        [
            BiblicalMapSource(
                source_id="source-without-url",
                provider="Teszt forrás",
                title="Teszt",
                original_language=None,
                source_url=None,
                license="test",
                attribution=None,
                retrieved_at=None,
                source_type="test",
                reliability_tier="test",
                notes_hu=None,
            )
        ],
    )

    assert fake_st.markdowns == [
        '<div class="textus-biblical-map-sources">'
        "<strong>Források:</strong> Teszt forrás"
        "</div>"
    ]
    assert compact_sources_markdown([]) == ""
    assert (
        compact_sources_markdown(
            [
                BiblicalMapSource(
                    source_id="linked",
                    provider="Pleiades",
                    title="Place",
                    original_language=None,
                    source_url="https://example.com/a",
                    license="test",
                    attribution=None,
                    retrieved_at=None,
                    source_type="test",
                    reliability_tier="test",
                    notes_hu=None,
                ),
                BiblicalMapSource(
                    source_id="linked-dup",
                    provider="Pleiades",
                    title="Place duplicate provider",
                    original_language=None,
                    source_url="https://example.com/b",
                    license="test",
                    attribution=None,
                    retrieved_at=None,
                    source_type="test",
                    reliability_tier="test",
                    notes_hu=None,
                ),
                BiblicalMapSource(
                    source_id="plain",
                    provider="Plain Provider",
                    title="Plain",
                    original_language=None,
                    source_url=None,
                    license="test",
                    attribution=None,
                    retrieved_at=None,
                    source_type="test",
                    reliability_tier="test",
                    notes_hu=None,
                ),
            ]
        )
        == "**Források:** [Pleiades](https://example.com/a) · Plain Provider"
    )
    html = compact_sources_html(
        [
            BiblicalMapSource(
                source_id="pleiades_corinth_570182",
                provider="Pleiades",
                title="A",
                original_language=None,
                source_url="https://pleiades.stoa.org/places/570182",
                license="test",
                attribution=None,
                retrieved_at=None,
                source_type="test",
                reliability_tier="test",
                notes_hu=None,
            ),
            BiblicalMapSource(
                source_id="pleiades_place_570182",
                provider="Pleiades",
                title="B",
                original_language=None,
                source_url="https://pleiades.stoa.org/places/570182",
                license="test",
                attribution=None,
                retrieved_at=None,
                source_type="test",
                reliability_tier="test",
                notes_hu=None,
            ),
        ]
    )
    assert html.count(">Pleiades</a>") == 1
    assert len(dedupe_sources(
        [
            BiblicalMapSource(
                source_id="a",
                provider="Pleiades",
                title="A",
                original_language=None,
                source_url=None,
                license="t",
                attribution=None,
                retrieved_at=None,
                source_type="t",
                reliability_tier="t",
                notes_hu=None,
            ),
            BiblicalMapSource(
                source_id="a",
                provider="Pleiades",
                title="A",
                original_language=None,
                source_url=None,
                license="t",
                attribution=None,
                retrieved_at=None,
                source_type="t",
                reliability_tier="t",
                notes_hu=None,
            ),
        ]
    )) == 1
    assert "None" not in "\n".join(fake_st.markdowns)
    assert "null" not in "\n".join(fake_st.markdowns)


def test_catalog_search_is_accent_insensitive_and_capped() -> None:
    assert normalize_place_search_text("Korinthús") == "korinthus"
    hits = search_biblical_places("korinthus")
    assert hits and hits[0].place_id == "corinth"
    hits_en = search_biblical_places("athens")
    assert hits_en and hits_en[0].place_id == "athens"
    hits_catalog = search_biblical_places("abana")
    assert hits_catalog and hits_catalog[0].place_id == "abana"
    many = search_biblical_places("a", limit=20)
    assert len(many) <= 20


def test_missing_hungarian_name_and_summary_use_safe_ui_fallbacks() -> None:
    abana = get_biblical_place("abana")

    assert abana is not None
    assert abana.name_en == "Abana"
    assert display_place_name(abana) == "Abana"
    assert "abana" not in display_place_name(abana)
    assert fallback_place_description(abana) == (
        "Bibliai helyszín; mai azonosítása: Barada River."
    )


def test_catalog_search_pick_updates_selected_place_without_query_alone() -> None:
    fake_st = _FakeStreamlit()
    fake_st.session_state[CATALOG_SEARCH_QUERY_KEY] = "efe"

    render_biblical_map_prototype(passage_reference="ApCsel 18,1-18", st_module=fake_st)
    assert fake_st.session_state[SELECTED_PLACE_ID_KEY] == "corinth"
    assert fake_st.session_state[MAP_SELECTION_SOURCE_KEY] == MAP_SELECTION_SOURCE_AUTO

    fake_st.selectbox_choice = "ephesus"
    render_biblical_map_prototype(passage_reference="ApCsel 18,1-18", st_module=fake_st)

    assert fake_st.session_state[SELECTED_PLACE_ID_KEY] == "ephesus"
    assert fake_st.session_state[MAP_SELECTION_SOURCE_KEY] == MAP_SELECTION_SOURCE_MANUAL
    assert any("Efezus" in body for body in fake_st.markdowns)


def test_render_preserves_manual_catalog_choice_for_same_reference() -> None:
    fake_st = _FakeStreamlit()
    fake_st.session_state[CATALOG_SEARCH_QUERY_KEY] = "efe"
    fake_st.selectbox_choice = "ephesus"

    render_biblical_map_prototype(passage_reference="ApCsel 18,1-18", st_module=fake_st)
    fake_st.selectbox_choice = None
    render_biblical_map_prototype(passage_reference="ApCsel 18,1-18", st_module=fake_st)

    assert fake_st.session_state[SELECTED_PLACE_ID_KEY] == "ephesus"
    assert fake_st.session_state[MAP_SELECTION_SOURCE_KEY] == MAP_SELECTION_SOURCE_MANUAL
    assert "A jelenlegi helyszínt kézzel választottad ki." in fake_st.captions


def test_new_supported_reference_can_override_manual_selectbox_choice() -> None:
    fake_st = _FakeStreamlit()
    fake_st.session_state[CATALOG_SEARCH_QUERY_KEY] = "efe"
    fake_st.selectbox_choice = "ephesus"

    render_biblical_map_prototype(passage_reference="ApCsel 18,1-18", st_module=fake_st)
    fake_st.selectbox_choice = None
    fake_st.session_state[CATALOG_SEARCH_QUERY_KEY] = ""
    if CATALOG_SEARCH_PICK_KEY in fake_st.session_state:
        del fake_st.session_state[CATALOG_SEARCH_PICK_KEY]
    render_biblical_map_prototype(passage_reference="ApCsel 16,11-40", st_module=fake_st)

    assert fake_st.session_state[SELECTED_PLACE_ID_KEY] == "philippi"
    assert fake_st.session_state[MAP_SELECTION_SOURCE_KEY] == MAP_SELECTION_SOURCE_AUTO
    assert fake_st.infos[-1] == (
        "A helyszín a megadott igerész alapján automatikusan lett kiválasztva: Filippi."
    )


def test_unknown_passage_preserves_existing_choice_without_arbitrary_pick() -> None:
    fake_st = _FakeStreamlit()
    fake_st.session_state[CATALOG_SEARCH_QUERY_KEY] = "efe"
    fake_st.selectbox_choice = "ephesus"

    render_biblical_map_prototype(passage_reference="ApCsel 18,1-18", st_module=fake_st)
    fake_st.selectbox_choice = None
    fake_st.session_state[CATALOG_SEARCH_QUERY_KEY] = ""
    if CATALOG_SEARCH_PICK_KEY in fake_st.session_state:
        del fake_st.session_state[CATALOG_SEARCH_PICK_KEY]
    selectbox_count = len(fake_st.selectboxes)
    render_biblical_map_prototype(passage_reference="Jn 3,16", st_module=fake_st)
    new_selectboxes = fake_st.selectboxes[selectbox_count:]

    assert fake_st.session_state[SELECTED_PLACE_ID_KEY] == "ephesus"
    assert fake_st.session_state[MAP_SELECTION_SOURCE_KEY] == MAP_SELECTION_SOURCE_UNMATCHED
    assert any(
        "Ehhez az igerészhez a prototípus még nem tartalmaz automatikus helykapcsolatot."
        in caption
        for caption in fake_st.captions
    )
    assert not any(label == "Aktuális igerész helyszínei" for label, *_ in new_selectboxes)


def test_selectbox_uses_place_ids_internally_and_hungarian_labels_in_ui() -> None:
    fake_st = _FakeStreamlit()

    render_biblical_map_prototype(passage_reference="ApCsel 17,16-34", st_module=fake_st)

    passage_boxes = [
        (label, options, index, kwargs)
        for label, options, index, kwargs in fake_st.selectboxes
        if label == "Aktuális igerész helyszínei"
    ]
    assert passage_boxes
    label, options, index, kwargs = passage_boxes[-1]
    assert options[0] == "athens"
    assert kwargs["format_func"]("athens") == "Athén"
    assert "athens" not in kwargs["format_func"]("athens")
    assert fake_st.text_inputs[0][0] == "Másik bibliai hely keresése"
    assert fake_st.radios == []


def test_map_failure_keeps_selector_and_place_card_visible() -> None:
    fake_st = _FakeStreamlit(fail_map=True)
    fake_st.session_state[CATALOG_SEARCH_QUERY_KEY] = "efe"
    fake_st.selectbox_choice = "ephesus"

    render_biblical_map_prototype(passage_reference="ApCsel 19", st_module=fake_st)

    assert fake_st.errors == []
    assert "Aktuális igerész: ApCsel 19" in fake_st.captions
    assert fake_st.warnings == [
        "A térképi nézet nem érhető el, de a helyválasztó és az adatlap használható."
    ]
    assert fake_st.text_inputs
    assert fake_st.radios == []
    assert fake_st.session_state[SELECTED_PLACE_ID_KEY] == "ephesus"
    assert any("Efezus" in body for body in fake_st.markdowns)
