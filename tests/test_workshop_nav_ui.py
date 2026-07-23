"""Workshop navigáció / completed-section helper tesztek."""

from __future__ import annotations

from workshop_nav_ui import (
    completed_step_indices,
    render_info_panel,
    render_primary_view_switcher,
    render_project_toolbar,
    render_project_toolbar_anchor,
    render_section_stepper,
    render_workshop_stepper,
    sermon_completed_sections,
    sermon_section_statuses,
    textus_completed_sections,
)


def test_textus_completed_sections_empty():
    assert textus_completed_sections({}) == set()


def test_textus_completed_sections_marks_filled():
    state = {
        "last_igehely": "Jn 3,16",
        "original_text": "λόγος",
        "exegesis": "rövid exegézis",
        "history": "háttér",
        "theology": "teológia",
        "text_workshop": {
            "text_main_idea": "Isten szeretete",
            "text_main_idea_status": "approved",
            "approved_insights": [{"content": "egy felismerés"}],
        },
    }
    done = textus_completed_sections(state)
    assert "Igehely, alkalom és szövegkörnyezet" in done
    assert "Eredeti szöveg és kulcsszavak" in done
    assert "Exegézis, műfaj és szerkezet" in done
    assert "Kortörténeti háttér" in done
    assert "Teológiai hangsúlyok" in done
    assert "A textus fő gondolata" in done
    assert "Mit viszünk tovább?" in done


def test_sermon_completed_sections_approved_and_content():
    state = {
        "sermon_workshop": {
            "sermon_main_idea": "Fő gondolat",
            "sermon_main_idea_status": "approved",
            "human_condition": "helyzet",
            "lection": {"reference": "Zsolt 23"},
            "lection_status": "draft",
            "diagnostics": {"result": {"overview": "ok"}},
        }
    }
    done = sermon_completed_sections(state)
    assert "Az igehirdetés fő gondolata" in done
    assert "Emberi helyzet és kegyelmi válasz" in done
    assert "Lekciójavaslat" in done
    assert "Homiletikai diagnosztika" in done
    assert "Imádsági előkészítés" not in done

    statuses = sermon_section_statuses(state)
    assert statuses["Az igehirdetés fő gondolata"] == "approved"
    assert statuses["Emberi helyzet és kegyelmi válasz"] == "own_emphasis"
    assert statuses["Lekciójavaslat"] == "own_emphasis"
    assert statuses["Homiletikai diagnosztika"] == "own_emphasis"
    assert statuses["Imádsági előkészítés"] == "ai_ready"
    assert statuses["Hallgatói kérdés és feszültség"] == "ai_ready"


def test_sermon_section_statuses_ai_suggested_and_labels():
    """AI-javaslat vs. saját hangsúly; üres szakasz = AI által kidolgozható."""
    from workshop_nav_ui import _STEP_STATE_LABEL

    state = {
        "sermon_workshop": {
            "sermon_main_idea_suggestions": [{"text": "Javasolt fő gondolat"}],
            "listener_tension_suggestions": {"question": "Mi feszül?"},
            "closing": {"arrival": "Megérkezés a kegyelemhez"},
            "closing_status": "draft",
        }
    }
    statuses = sermon_section_statuses(state)
    assert statuses["Az igehirdetés fő gondolata"] == "ai_suggested"
    assert statuses["Hallgatói kérdés és feszültség"] == "ai_suggested"
    assert statuses["Lezárás és megérkezés"] == "own_emphasis"
    assert statuses["Emberi helyzet és kegyelmi válasz"] == "ai_ready"

    assert _STEP_STATE_LABEL["ai_ready"] == "AI által kidolgozható"
    assert _STEP_STATE_LABEL["ai_suggested"] == "AI-javaslat elkészült"
    assert _STEP_STATE_LABEL["own_emphasis"] == "Saját hangsúly hozzáadva"
    assert _STEP_STATE_LABEL["approved"] == "Jóváhagyva"
    assert _STEP_STATE_LABEL["pending"] == "AI által kidolgozható"


def test_sermon_completed_sections_ignores_empty_defaults():
    """Üres alapértelmezett prayer/outline/diag ne legyen „elkészült”."""
    from sermon_workshop_data import (
        get_default_sermon_workshop,
        normalize_sermon_outline_diagnostics,
    )

    done = sermon_completed_sections(
        {"sermon_workshop": get_default_sermon_workshop()}
    )
    assert "Imádsági előkészítés" not in done
    assert "Igehirdetési vázlat" not in done
    assert "Homiletikai diagnosztika" not in done

    statuses = sermon_section_statuses(
        {"sermon_workshop": get_default_sermon_workshop()}
    )
    assert statuses["Imádsági előkészítés"] == "ai_ready"
    assert statuses["Igehirdetési vázlat"] == "ai_ready"
    assert statuses["Homiletikai diagnosztika"] == "ai_ready"

    # Normalizált üres diagnosztika ok=True alapértelmezéssel se számítson.
    sw = get_default_sermon_workshop()
    sw["sermon_outline_diagnostics"] = normalize_sermon_outline_diagnostics({})
    assert sw["sermon_outline_diagnostics"].get("ok") is True
    assert "Homiletikai diagnosztika" not in sermon_completed_sections(
        {"sermon_workshop": sw}
    )


def test_completed_step_indices_order():
    opts = ["A", "B", "C", "D"]
    assert completed_step_indices(opts, {"B", "D"}) == [1, 3]
    assert completed_step_indices(opts, None) == []
    assert completed_step_indices(opts, {"Z"}) == []


def test_stepper_aliases_and_helpers_importable():
    assert render_section_stepper is render_workshop_stepper
    assert callable(render_primary_view_switcher)
    assert callable(render_project_toolbar_anchor)
    assert callable(render_project_toolbar)


def test_project_toolbar_actions(monkeypatch):
    """ProjectToolbar: aktív projektnél Mentés; ideiglenesnél Mentés újként."""
    import streamlit as st
    from contextlib import nullcontext

    clicks = {"bar_project_save": True}
    monkeypatch.setattr(st, "session_state", {"project_title_input": "Teszt"})
    monkeypatch.setattr(st, "markdown", lambda *a, **k: None)

    def _columns(*args, **kwargs):
        spec = args[0] if args else kwargs.get("spec", 2)
        n = spec if isinstance(spec, int) else len(spec)
        return [nullcontext() for _ in range(n)]

    monkeypatch.setattr(st, "columns", _columns)
    monkeypatch.setattr(st, "container", lambda **k: nullcontext())
    monkeypatch.setattr(
        st,
        "button",
        lambda label, key=None, **k: bool(clicks.get(key)),
    )
    monkeypatch.setattr(st, "popover", lambda *a, **k: nullcontext())
    monkeypatch.setattr(st, "text_input", lambda *a, **k: "")
    monkeypatch.setattr(st, "form", lambda *a, **k: nullcontext())
    monkeypatch.setattr(st, "form_submit_button", lambda *a, **k: False)

    assert (
        render_project_toolbar(
            has_active_project=True,
            project_label="Teszt",
            status_label="Mentve",
            status_kind="saved",
            editing_title=False,
            projects_renderer=lambda: None,
        )
        == "save"
    )

    clicks.clear()
    clicks["bar_new_work"] = True
    assert (
        render_project_toolbar(
            has_active_project=True,
            project_label="Teszt",
            status_label="Mentve",
            status_kind="saved",
            editing_title=False,
            projects_renderer=lambda: None,
        )
        == "new_work"
    )

    clicks.clear()
    clicks["bar_project_save_as_new"] = True
    assert (
        render_project_toolbar(
            has_active_project=False,
            project_label="Névtelen",
            status_label="Ideiglenes",
            status_kind="temp",
            editing_title=False,
            projects_renderer=lambda: None,
        )
        == "save_as_new"
    )
    assert callable(render_info_panel)


def test_global_appbar_and_workspace_switcher_importable():
    from workshop_nav_ui import (
        render_app_toolbar,
        render_global_appbar,
        render_project_toolbar,
        render_workspace_switcher,
    )

    assert callable(render_app_toolbar)
    assert callable(render_global_appbar)
    assert callable(render_workspace_switcher)
    assert callable(render_project_toolbar)
    assert render_workspace_switcher is not None


def test_shell_components_use_keyed_containers():
    from pathlib import Path

    src = Path(__file__).resolve().parents[1].joinpath("workshop_nav_ui.py").read_text(
        encoding="utf-8"
    )
    assert 'key="textus_app_toolbar"' in src
    assert 'key="project_picker_content"' in src
    assert 'key="workspace_switcher"' in src
    assert 'key="workshop_step_bar"' in src
    assert "Azonnali segítség" not in src
    assert "horizontal=True" in src
    assert "Szerkesztés" not in src or 'key="bar_title_edit"' in src
    assert "Projekt nevének szerkesztése" in src
    # Ne legyen egyszerre két elsődleges mentés a toolbarban (ideiglenes ág)
    assert 'key="bar_project_save_as_new"' in src
    assert "Mentés másolatként" in src
    assert 'help="Mentett projektek megnyitása"' in src
    # JS-es widget-mozgatás a shell komponensekből kikerült
    assert "tx-appbar-anchor" not in src
    assert "tx-project-toolbar-anchor" not in src or "no-op" in src.lower() or "Kompatibilitási" in src


def test_page_intro_supports_workspace_scope():
    from pathlib import Path

    src = Path(__file__).resolve().parents[1].joinpath("ui_components.py").read_text(
        encoding="utf-8"
    )
    assert "workspace_scope" in src
    assert 'key="workspace_intro"' in src
