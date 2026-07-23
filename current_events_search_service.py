"""Aktuális kapcsolódások — webes keresés absztrakció.

Preferált út: a meglévő Gemini `enable_google_search` grounding
(app.generate_text). Nincs hardcode-olt API-kulcs.
Ha a generate_fn None, vagy a keresés nem elérhető, világos üzenetet ad.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

GenerateFn = Callable[..., str]

NO_SEARCH_MESSAGE = (
    "A friss hírek kereséséhez még nincs beállítva webes keresési szolgáltatás."
)


@dataclass
class CurrentEventsSearchResult:
    ok: bool
    raw_text: str = ""
    used_web_search: bool = False
    error_message: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "raw_text": self.raw_text,
            "used_web_search": self.used_web_search,
            "error_message": self.error_message,
            "warnings": list(self.warnings),
        }


def search_current_events(
    *,
    query_prompt: str,
    generate_fn: GenerateFn | None,
    tab_label: str = "Aktualizálás",
    system_bundle: str = "",
    temperature: float = 0.2,
) -> CurrentEventsSearchResult:
    """Célzott webes keresés Gemini Google Search groundinggal.

    Nem scrape-el híroldalakat. Ha nincs generate_fn, nem állítja, hogy
    friss hírt vizsgált.
    """
    if generate_fn is None:
        return CurrentEventsSearchResult(
            ok=False,
            used_web_search=False,
            error_message=NO_SEARCH_MESSAGE,
        )
    try:
        raw = generate_fn(
            query_prompt,
            enable_google_search=True,
            tab_label=tab_label,
            use_cache=False,
            system_bundle=system_bundle or None,
            temperature=temperature,
            include_brevity_directive=False,
        )
    except TypeError:
        # Régebbi generate_fn signature — próbáljuk kevesebb kwarggal
        try:
            raw = generate_fn(
                query_prompt,
                enable_google_search=True,
                tab_label=tab_label,
                use_cache=False,
            )
        except Exception as exc:  # noqa: BLE001
            return CurrentEventsSearchResult(
                ok=False,
                used_web_search=False,
                error_message=NO_SEARCH_MESSAGE,
                warnings=[str(exc)],
            )
    except Exception as exc:  # noqa: BLE001
        return CurrentEventsSearchResult(
            ok=False,
            used_web_search=False,
            error_message=NO_SEARCH_MESSAGE,
            warnings=[str(exc)],
        )

    text = str(raw or "").strip()
    if not text:
        return CurrentEventsSearchResult(
            ok=False,
            used_web_search=True,
            error_message="A webes keresés nem adott használható választ.",
        )
    lower = text.casefold()
    if "nincs beállítva" in lower or "api kulcs" in lower or "api-kulcs" in lower:
        return CurrentEventsSearchResult(
            ok=False,
            used_web_search=False,
            error_message=NO_SEARCH_MESSAGE,
            raw_text=text,
        )
    return CurrentEventsSearchResult(
        ok=True,
        raw_text=text,
        used_web_search=True,
    )


__all__ = [
    "NO_SEARCH_MESSAGE",
    "CurrentEventsSearchResult",
    "search_current_events",
]
