"""Forrásolt kiegészítő keresési réteg az exegetikai maghoz.

A keresés tárgyát mindig a Textusban azonosított tokenek / kifejezések
határozzák meg. Nincs ellenőrizetlen, forrás nélküli webscraping.

Ha a Gemini Google Search grounding elérhető, a GroundedEnrichmentService
használja. Egyébként CautiousModelSynthesisService óvatos, nem ellenőrzött
szintézisként jelöli a kiegészítést — színlelt URL nélkül.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Protocol

from exegetical_core import ExegeticalCoreResult, SourceReference

logger = logging.getLogger("textus.exegetical_enrichment")

GenerateFn = Callable[..., str]


class ExegeticalEnrichmentService(Protocol):
    """Bővíthető interfész célzott exegetikai kiegészítéshez."""

    def enrich(
        self, core: ExegeticalCoreResult
    ) -> tuple[str, list[SourceReference]]:
        """Vissza: (jegyzet_szöveg, forrás_referenciák)."""
        ...


class NullEnrichmentService:
    def enrich(
        self, core: ExegeticalCoreResult
    ) -> tuple[str, list[SourceReference]]:
        return "", []


ENRICH_SYSTEM = """\
Célzott exegetikai kiegészítést készítesz a megadott kulcskifejezésekhez.
Csak a kapott lemmákra / formulákra és a szakasz szerkezetére irányulj.

TILOS:
- színlelt URL vagy kitalált forrásnév;
- a textusban nem szereplő lemma kitalálása;
- általános internetes szöveggyűjtés forrás nélkül.

Ha grounding / keresés elérhető, használd a releváns találatokat.
Ha nem, fogalmazz óvatosan, és jelöld: model_synthesis.

Kizárólag JSON:
{
  "notes": "rövid kiegészítő jegyzet a kiválasztott kifejezésekhez",
  "items": [
    {
      "related": "lemma vagy formula",
      "excerpt": "rövid kivonat / állítás",
      "source_name": "forrás neve vagy üres",
      "source_url": "url vagy üres",
      "origin": "external|model_synthesis|database",
      "reliability": "high|medium|low|unverified"
    }
  ]
}
"""


def _parse_enrichment_payload(raw: str) -> tuple[str, list[SourceReference]]:
    from sermon_workshop_m4_ai import extract_json_object
    from ai_response_validation import sanitize_ai_json

    obj = extract_json_object(raw or "") or {}
    if not isinstance(obj, dict):
        return "", []
    try:
        obj = sanitize_ai_json(obj) or obj
    except Exception:
        pass
    notes = str(obj.get("notes") or "").strip()
    refs: list[SourceReference] = []
    for item in obj.get("items") or []:
        if not isinstance(item, dict):
            continue
        origin = str(item.get("origin") or "").strip() or "model_synthesis"
        url = str(item.get("url") or item.get("source_url") or "").strip()
        name = str(item.get("source_name") or item.get("name") or "").strip()
        reliability = str(item.get("reliability") or "unverified").strip()
        # Színlelt forrás tiltása: external + nincs URL → model_synthesis / low
        if origin == "external" and not url:
            origin = "model_synthesis"
            reliability = "unverified"
            if not name:
                name = "Modell-szintézis (nem forrásolt)"
        refs.append(
            SourceReference(
                source_type="enrichment",
                name=name or ("Google grounding" if url else "Modell-szintézis"),
                url=url,
                related_lemma_or_span=str(item.get("related") or "").strip(),
                excerpt=str(item.get("excerpt") or "").strip()[:500],
                reliability=reliability,
                origin=origin,
            )
        )
    return notes, refs


class GroundedEnrichmentService:
    """Gemini Google Search grounding — ha a generate_fn támogatja."""

    def __init__(self, generate_fn: GenerateFn) -> None:
        self.generate_fn = generate_fn

    def enrich(
        self, core: ExegeticalCoreResult
    ) -> tuple[str, list[SourceReference]]:
        exprs = [
            {
                "lemma": e.lemma,
                "surface": e.surface,
                "is_phrase": e.is_phrase,
                "gloss": e.contextual_gloss,
            }
            for e in core.selected_expressions[:6]
        ]
        if not exprs:
            return "", []
        prompt = (
            f"Igehely: {core.passage_reference}\n"
            f"Mozgás: {core.literary_movement}\n"
            f"Kulcskifejezések:\n{json.dumps(exprs, ensure_ascii=False)}\n\n"
            "Készíts célzott kiegészítést: lemma jelentés a kontextusban, "
            "nyelvtani szerkezet jelentősége, szoros párhuzamok, szükséges háttér. "
            "Ne térj el a megadott kifejezésektől."
        )
        try:
            raw = self.generate_fn(
                prompt,
                enable_google_search=True,
                tab_label="Eredeti szöveg tanulmányozása",
                use_cache=False,
                system_bundle=ENRICH_SYSTEM,
                include_brevity_directive=False,
                max_output_tokens=1200,
            )
        except TypeError:
            # Legacy signature — grounding nélkül
            try:
                raw = self.generate_fn(prompt)
            except Exception as exc:
                logger.info("grounded_enrich_failed err=%s", type(exc).__name__)
                return "", []
        except Exception as exc:
            logger.info("grounded_enrich_failed err=%s", type(exc).__name__)
            return "", []

        notes, refs = _parse_enrichment_payload(raw or "")
        # A grounding források a generate_text végén markdownként is megjelenhetnek;
        # itt strukturált refs-et építünk. Ha van URL a raw szövegben, próbáljuk.
        if "http" in (raw or "") and not any(r.url for r in refs):
            import re

            for m in re.finditer(r"\[([^\]]+)\]\((https?://[^)]+)\)", raw or ""):
                refs.append(
                    SourceReference(
                        source_type="enrichment",
                        name=m.group(1)[:120],
                        url=m.group(2),
                        reliability="medium",
                        origin="external",
                    )
                )
        if notes or refs:
            if not any(r.origin == "external" and r.url for r in refs):
                # Grounding futott, de nincs ellenőrizhető URL → ne színleljünk forrást
                if not any(r.origin == "model_synthesis" for r in refs):
                    refs.append(
                        SourceReference(
                            source_type="enrichment",
                            name="Modell-szintézis / grounding (URL nélkül)",
                            reliability="unverified",
                            origin="model_synthesis",
                        )
                    )
        return notes, refs


class CautiousModelSynthesisService:
    """Keresés nélkül — óvatos modell-szintézis, nem színlelt forrás."""

    def __init__(self, generate_fn: GenerateFn) -> None:
        self.generate_fn = generate_fn

    def enrich(
        self, core: ExegeticalCoreResult
    ) -> tuple[str, list[SourceReference]]:
        exprs = [
            {"lemma": e.lemma, "surface": e.surface, "is_phrase": e.is_phrase}
            for e in core.selected_expressions[:6]
        ]
        if not exprs:
            return "", []
        prompt = (
            f"Igehely: {core.passage_reference}\n"
            f"Kulcskifejezések: {json.dumps(exprs, ensure_ascii=False)}\n\n"
            "Adj rövid, óvatos kiegészítést. origin legyen mindig model_synthesis. "
            "Ne adj URL-t. Ne állíts biztos lexikai tényt bizonytalan etimológiából."
        )
        try:
            try:
                raw = self.generate_fn(
                    prompt,
                    enable_google_search=False,
                    tab_label="Eredeti szöveg tanulmányozása",
                    use_cache=False,
                    system_bundle=ENRICH_SYSTEM,
                    include_brevity_directive=False,
                    max_output_tokens=900,
                )
            except TypeError:
                raw = self.generate_fn(prompt)
        except Exception as exc:
            logger.info("synthesis_enrich_failed err=%s", type(exc).__name__)
            return "", []
        notes, refs = _parse_enrichment_payload(raw or "")
        # Kényszerítjük: nincs színlelt external
        cleaned: list[SourceReference] = []
        for r in refs:
            if r.origin == "external" and not r.url:
                r.origin = "model_synthesis"
                r.reliability = "unverified"
            cleaned.append(r)
        if notes and not cleaned:
            cleaned.append(
                SourceReference(
                    source_type="enrichment",
                    name="Modell-szintézis (nem forrásolt)",
                    reliability="unverified",
                    origin="model_synthesis",
                )
            )
        return notes, cleaned


def get_default_enrichment_service(
    *,
    generate_fn: GenerateFn | None = None,
    prefer_grounding: bool = True,
) -> ExegeticalEnrichmentService:
    if generate_fn is None:
        return NullEnrichmentService()
    if prefer_grounding:
        return GroundedEnrichmentService(generate_fn)
    return CautiousModelSynthesisService(generate_fn)


__all__ = [
    "CautiousModelSynthesisService",
    "ExegeticalEnrichmentService",
    "GroundedEnrichmentService",
    "NullEnrichmentService",
    "get_default_enrichment_service",
]
