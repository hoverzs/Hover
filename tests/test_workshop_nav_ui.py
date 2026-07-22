"""Workshop navigáció / completed-section helper tesztek."""

from __future__ import annotations

from workshop_nav_ui import sermon_completed_sections, textus_completed_sections


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
