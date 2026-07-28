from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class HungarianMorphology:
    raw_code: str
    part_of_speech: str | None
    tense: str | None
    voice: str | None
    mood: str | None
    verb_form: str | None
    person: str | None
    number: str | None
    case: str | None
    gender: str | None
    degree: str | None
    extra: tuple[str, ...]
    pronoun_type: str | None = None
    name_type: str | None = None
    original_language: str | None = None
    components: tuple["HungarianMorphology", ...] = ()
    unresolved: tuple[str, ...] = ()

    @property
    def is_fully_resolved(self) -> bool:
        return not self.unresolved and all(component.is_fully_resolved for component in self.components)


_FUNCTIONS = {
    "A": "melléknév",
    "ADV": "határozószó",
    "ARAM": "arámi átírt szó",
    "C": "kölcsönös névmás",
    "COND": "feltételes kötőszó",
    "CONJ": "kötőszó",
    "D": "mutató névmás",
    "F": "visszaható névmás",
    "HEB": "héber átírt szó",
    "I": "kérdő névmás",
    "INJ": "indulatszó",
    "K": "korrelatív névmás",
    "N": "főnév",
    "P": "személyes névmás",
    "PREP": "elöljárószó",
    "PRT": "partikula",
    "Q": "korrelatív vagy kérdő névmás",
    "R": "vonatkozó névmás",
    "S": "birtokos névmás",
    "T": "határozott névelő",
    "V": "ige",
    "X": "határozatlan névmás",
}

_FUNCTION_FIELD_HU = {
    "Adjective": "melléknév",
    "Adverb": "határozószó",
    "Aramaic transliterated word": "arámi átírt szó",
    "Article": "határozott névelő",
    "Conditional particle or conjunction": "feltételes kötőszó",
    "Conjunction": "kötőszó",
    "Correlative or Interrogative pronoun": "korrelatív vagy kérdő névmás",
    "Correlative pronoun": "korrelatív névmás",
    "Demonstrative pronoun": "mutató névmás",
    "Hebrew transliterated word": "héber átírt szó",
    "Indefinite pronoun": "határozatlan névmás",
    "Interjection": "indulatszó",
    "Interrogative Particle": "kérdő partikula",
    "Interrogative pronoun": "kérdő névmás",
    "Noun": "főnév",
    "Particle": "partikula",
    "Personal pronoun": "személyes névmás",
    "Preposition": "elöljárószó",
    "Reciprocal pronoun": "kölcsönös névmás",
    "Reflexive pronoun": "visszaható névmás",
    "Relative pronoun": "vonatkozó névmás",
    "Possessive pronoun": "birtokos névmás",
    "Verb": "ige",
}

_CASES = {
    "N": "alanyeset",
    "G": "birtokos eset",
    "D": "részes eset",
    "A": "tárgyeset",
    "V": "megszólító eset",
    "Nominative": "alanyeset",
    "Genitive": "birtokos eset",
    "Dative": "részes eset",
    "Accusative": "tárgyeset",
    "Vocative": "megszólító eset",
}

_NUMBERS = {
    "S": "egyes",
    "P": "többes",
    "Singular": "egyes",
    "Plural": "többes",
}

_GENDERS = {
    "M": "hímnem",
    "F": "nőnem",
    "N": "semlegesnem",
    "Masculine": "hímnem",
    "Feminine": "nőnem",
    "Neuter": "semlegesnem",
}

_PERSONS = {
    "1": "első",
    "2": "második",
    "3": "harmadik",
    "1st": "első",
    "2nd": "második",
    "3rd": "harmadik",
    "1st Person": "első",
    "2nd Person": "második",
    "3rd Person": "harmadik",
}

_TENSES = {
    "P": "jelen idő",
    "2P": "jelen idő",
    "I": "imperfektum",
    "F": "jövő idő",
    "2F": "második jövő idő",
    "A": "aorisztoszi",
    "2A": "második aorisztoszi",
    "R": "perfectum",
    "2R": "második perfectum",
    "L": "plusquamperfectum",
    "2L": "második plusquamperfectum",
    "Present": "jelen idő",
    "Imperfect": "imperfektum",
    "Future": "jövő idő",
    "2nd Future": "második jövő idő",
    "Aorist": "aorisztoszi",
    "2nd Aorist": "második aorisztoszi",
    "Perfect": "perfectum",
    "2nd Perfect": "második perfectum",
    "Pluperfect": "plusquamperfectum",
    "2nd Pluperfect": "második plusquamperfectum",
}

_VOICES = {
    "A": "aktív igenem",
    "M": "mediális igenem",
    "P": "passzív igenem",
    "E": "mediális vagy passzív igenem",
    "D": "mediális deponens",
    "O": "passzív deponens",
    "N": "mediális vagy passzív deponens",
    "Active": "aktív igenem",
    "Middle": "mediális igenem",
    "Passive": "passzív igenem",
    "Middle or Passive": "mediális vagy passzív igenem",
    "Middle Deponent": "mediális deponens",
    "Passive Deponent": "passzív deponens",
    "Middle or Passive Deponent": "mediális vagy passzív deponens",
}

_MOODS = {
    "I": "kijelentő mód",
    "M": "felszólító mód",
    "S": "kötőmód",
    "O": "óhajtó mód",
    "N": "főnévi igenév",
    "P": "igei melléknévi igenév",
    "Indicative": "kijelentő mód",
    "Imperative": "felszólító mód",
    "Subjunctive": "kötőmód",
    "Optative": "óhajtó mód",
}

_EXTRAS = {
    "Abbreviated": "rövidült alak",
    "Attic Greek form": "attikai görög alak",
    "Comparative": "középfok",
    "Contracted form": "összevont alak",
    "Indeclinable": "ragozhatatlan alak",
    "Indeclinable Letter": "ragozhatatlan betűnév",
    "Interrogative": "kérdő jelölés",
    "Negative": "tagadó jelölés",
    "Numeral": "számnévi jelölés",
    "Superlative": "felsőfok",
    "Transcribed from Hebrew": "héberből átírt alak",
}

_NAME_TYPES = {
    "Individual": "tulajdonnév",
    "Location": "helynév",
    "Location Gentilic": "helynévi népnév",
    "Gentilic": "népnév",
    "Person Gentilic": "személynévi népnév",
    "Title": "cím vagy titulus",
}

_INDECLINABLE_VALUES = {"NUI", "PRI"}


def parse_morphology_hu(code: str) -> HungarianMorphology:
    raw_code = (code or "").strip()
    if not raw_code:
        return _morphology(raw_code, {})
    components = tuple(_parse_component(part.strip()) for part in raw_code.split(" + ") if part.strip())
    if len(components) > 1:
        return _morphology(
            raw_code,
            {
                "components": components,
                "unresolved": tuple(
                    item for component in components for item in component.unresolved
                ),
            },
        )
    return components[0] if components else _morphology(raw_code, {})


def format_morphology_hu(morphology: HungarianMorphology) -> str:
    if morphology.components:
        return " + ".join(
            text for text in (format_morphology_hu(component) for component in morphology.components) if text
        )

    parts: list[str] = []
    pos = _display_part_of_speech(morphology)
    if pos:
        parts.append(pos)

    if morphology.verb_form == "participle":
        if morphology.tense:
            parts.append(_adjectival_tense(morphology.tense))
        if morphology.voice:
            parts.append(morphology.voice)
        _append_nominal(parts, morphology)
    elif morphology.verb_form == "infinitive":
        if morphology.tense:
            parts.append(morphology.tense)
        if morphology.voice:
            parts.append(morphology.voice)
    else:
        if morphology.tense:
            parts.append(morphology.tense)
        if morphology.mood:
            parts.append(morphology.mood)
        if morphology.voice:
            parts.append(morphology.voice)
        if morphology.person and morphology.number:
            parts.append(f"{morphology.number} szám {morphology.person} személy")
        else:
            if morphology.number and not (morphology.case or morphology.gender):
                parts.append(f"{morphology.number} szám")
            if morphology.person:
                parts.append(f"{morphology.person} személy")
        _append_nominal(parts, morphology)

    if morphology.degree:
        parts.append(morphology.degree)
    parts.extend(morphology.extra)
    parts.extend(f"nem feloldott morfológiai jelölés: {item}" for item in morphology.unresolved)
    return ", ".join(_dedupe(parts))


def _parse_component(component: str) -> HungarianMorphology:
    code = component.split("=", 1)[1] if "=" in component else component
    code = code.strip()
    parts = tuple(part for part in code.split("-") if part)
    prefix = parts[0] if parts else code
    fields: dict[str, object] = {"part_of_speech": _FUNCTIONS.get(prefix)}
    unresolved: list[str] = []

    if prefix == "V":
        _decode_verb(parts, fields, unresolved)
    elif prefix in {"A", "N", "T", "D", "I", "K", "Q", "R", "X", "C"}:
        _decode_nominal(parts, fields, unresolved)
    elif prefix in {"P", "F", "S"}:
        _decode_pronoun(parts, fields, unresolved)
    elif prefix in {"ADV", "CONJ", "COND", "PREP", "PRT", "INJ", "ARAM"}:
        _decode_simple(parts, fields, unresolved)
    else:
        unresolved.extend(parts or (code,))

    if prefix in {"D", "I", "K", "Q", "R", "X", "C", "P", "F", "S"}:
        fields.setdefault("pronoun_type", fields.get("part_of_speech"))

    fields["unresolved"] = tuple(unresolved)
    return _morphology(component, fields)


def _decode_verb(parts: tuple[str, ...], fields: dict[str, object], unresolved: list[str]) -> None:
    if len(parts) < 2:
        unresolved.extend(parts[1:] or parts)
        return
    stem = parts[1]
    tense_code = stem[:2] if stem.startswith("2") else stem[:1]
    rest = stem[2:] if stem.startswith("2") else stem[1:]
    if len(rest) != 2:
        unresolved.append(stem)
        return
    voice_code, mood_code = rest[0], rest[1]
    fields["tense"] = _TENSES.get(tense_code)
    fields["voice"] = _VOICES.get(voice_code)
    if mood_code == "N":
        fields["verb_form"] = "infinitive"
    elif mood_code == "P":
        fields["verb_form"] = "participle"
    else:
        fields["mood"] = _MOODS.get(mood_code)
    _add_unresolved_if_missing(unresolved, stem, (fields.get("tense"), fields.get("voice"), fields.get("mood") or fields.get("verb_form")))

    if len(parts) >= 3:
        ending = parts[2]
        if fields.get("verb_form") == "participle":
            _decode_case_number_gender(ending, fields, unresolved)
        else:
            _decode_person_number(ending, fields, unresolved)
    if len(parts) > 3:
        for extra in parts[3:]:
            _decode_extra(extra, fields, unresolved)


def _decode_nominal(parts: tuple[str, ...], fields: dict[str, object], unresolved: list[str]) -> None:
    if len(parts) < 2:
        return
    head = parts[1]
    if head in _INDECLINABLE_VALUES:
        fields["extra"] = ("ragozhatatlan számnév" if head == "NUI" else "ragozhatatlan névmási alak",)
    else:
        _decode_case_number_gender(head, fields, unresolved)
    for extra in parts[2:]:
        _decode_extra(extra, fields, unresolved)


def _decode_pronoun(parts: tuple[str, ...], fields: dict[str, object], unresolved: list[str]) -> None:
    if len(parts) < 2:
        return
    head = parts[1]
    if re.fullmatch(r"[123][SP]?[NGDAV][SP][MFN]?", head):
        fields["person"] = _PERSONS.get(head[0])
        rest = head[2:] if len(head) >= 2 and head[1] in _NUMBERS else head[1:]
        _decode_case_number_gender(rest, fields, unresolved)
        return
    if re.fullmatch(r"[123][NGDAV][SP]", head):
        fields["person"] = _PERSONS.get(head[0])
        _decode_case_number(rest[1:] if (rest := head) else "", fields, unresolved)
        return
    _decode_case_number_gender(head, fields, unresolved)


def _decode_simple(parts: tuple[str, ...], fields: dict[str, object], unresolved: list[str]) -> None:
    for extra in parts[1:]:
        _decode_extra(extra, fields, unresolved)


def _decode_case_number_gender(value: str, fields: dict[str, object], unresolved: list[str]) -> None:
    if len(value) != 3:
        _decode_case_number(value, fields, unresolved)
        return
    fields["case"] = _CASES.get(value[0])
    fields["number"] = _NUMBERS.get(value[1])
    fields["gender"] = _GENDERS.get(value[2])
    _add_unresolved_if_missing(unresolved, value, (fields.get("case"), fields.get("number"), fields.get("gender")))


def _decode_case_number(value: str, fields: dict[str, object], unresolved: list[str]) -> None:
    if len(value) != 2:
        unresolved.append(value)
        return
    fields["case"] = _CASES.get(value[0])
    fields["number"] = _NUMBERS.get(value[1])
    _add_unresolved_if_missing(unresolved, value, (fields.get("case"), fields.get("number")))


def _decode_person_number(value: str, fields: dict[str, object], unresolved: list[str]) -> None:
    if len(value) != 2:
        unresolved.append(value)
        return
    fields["person"] = _PERSONS.get(value[0])
    fields["number"] = _NUMBERS.get(value[1])
    _add_unresolved_if_missing(unresolved, value, (fields.get("person"), fields.get("number")))


def _decode_extra(value: str, fields: dict[str, object], unresolved: list[str]) -> None:
    if value in {"C", "S"}:
        fields["degree"] = "középfok" if value == "C" else "felsőfok"
        return
    if value in {"P", "L", "LG", "G", "PG", "T"}:
        fields["name_type"] = _NAME_TYPES.get(
            {"P": "Individual", "L": "Location", "G": "Gentilic"}.get(value, value)
        )
        return
    if value in {"N", "I", "NUI", "ABB", "ATT", "ARAM", "HEB"}:
        mapped = {
            "N": "tagadó jelölés",
            "I": "kérdő jelölés",
            "NUI": "ragozhatatlan számnév",
            "ABB": "rövidült alak",
            "ATT": "attikai görög alak",
            "ARAM": "arámi eredetű alak",
            "HEB": "héberből átírt alak",
        }[value]
        extras = list(fields.get("extra") or ())
        extras.append(mapped)
        fields["extra"] = tuple(extras)
        return
    if value == "LI":
        extras = list(fields.get("extra") or ())
        extras.append("ragozhatatlan betűnév")
        fields["extra"] = tuple(extras)
        return
    unresolved.append(value)


def _display_part_of_speech(morphology: HungarianMorphology) -> str | None:
    if morphology.verb_form == "participle":
        return "igei melléknévi igenév"
    if morphology.verb_form == "infinitive":
        return "főnévi igenév"
    if morphology.name_type == "tulajdonnév":
        return "tulajdonnév"
    return morphology.part_of_speech


def _append_nominal(parts: list[str], morphology: HungarianMorphology) -> None:
    if morphology.gender:
        parts.append(morphology.gender)
    if morphology.number and not morphology.person:
        parts.append(f"{morphology.number} szám")
    if morphology.case:
        parts.append(morphology.case)
    if morphology.name_type and morphology.name_type != "tulajdonnév":
        parts.append(morphology.name_type)


def _adjectival_tense(tense: str) -> str:
    if tense.endswith(" idő"):
        return tense.replace(" idő", " idejű")
    if tense.endswith("i"):
        return tense
    return tense


def _add_unresolved_if_missing(unresolved: list[str], source: str, values: tuple[object, ...]) -> None:
    if not all(values):
        unresolved.append(source)


def _dedupe(parts: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        if part and part not in seen:
            seen.add(part)
            out.append(part)
    return out


def _morphology(raw_code: str, fields: dict[str, object]) -> HungarianMorphology:
    return HungarianMorphology(
        raw_code=raw_code,
        part_of_speech=_string_field(fields, "part_of_speech"),
        tense=_string_field(fields, "tense"),
        voice=_string_field(fields, "voice"),
        mood=_string_field(fields, "mood"),
        verb_form=_string_field(fields, "verb_form"),
        person=_string_field(fields, "person"),
        number=_string_field(fields, "number"),
        case=_string_field(fields, "case"),
        gender=_string_field(fields, "gender"),
        degree=_string_field(fields, "degree"),
        extra=tuple(fields.get("extra") or ()),
        pronoun_type=_string_field(fields, "pronoun_type"),
        name_type=_string_field(fields, "name_type"),
        original_language=_string_field(fields, "original_language"),
        components=tuple(fields.get("components") or ()),
        unresolved=tuple(fields.get("unresolved") or ()),
    )


def _string_field(fields: dict[str, object], name: str) -> str | None:
    value = fields.get(name)
    return value if isinstance(value, str) else None
