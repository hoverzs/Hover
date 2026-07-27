from __future__ import annotations

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


_DOCUMENTED_JHN_3_16_CODES: dict[str, dict[str, str | tuple[str, ...]]] = {
    "A-ASF": {
        "part_of_speech": "melléknév",
        "case": "tárgyeset",
        "number": "egyes",
        "gender": "nőnem",
    },
    "A-ASM": {
        "part_of_speech": "melléknév",
        "case": "tárgyeset",
        "number": "egyes",
        "gender": "hímnem",
    },
    "A-NSM": {
        "part_of_speech": "melléknév",
        "case": "alanyeset",
        "number": "egyes",
        "gender": "hímnem",
    },
    "ADV": {"part_of_speech": "határozószó"},
    "CONJ": {"part_of_speech": "kötőszó"},
    "N-ASF": {
        "part_of_speech": "főnév",
        "case": "tárgyeset",
        "number": "egyes",
        "gender": "nőnem",
    },
    "N-ASM": {
        "part_of_speech": "főnév",
        "case": "tárgyeset",
        "number": "egyes",
        "gender": "hímnem",
    },
    "N-NSM-T": {
        "part_of_speech": "főnév",
        "case": "alanyeset",
        "number": "egyes",
        "gender": "hímnem",
        "extra": ("cím",),
    },
    "P-ASM": {
        "part_of_speech": "személyes névmás",
        "case": "tárgyeset",
        "number": "egyes",
        "gender": "hímnem",
    },
    "P-GSM": {
        "part_of_speech": "személyes névmás",
        "case": "birtokos eset",
        "number": "egyes",
        "gender": "hímnem",
    },
    "PREP": {"part_of_speech": "elöljárószó"},
    "PRT-N": {"part_of_speech": "tagadószó", "extra": ("tagadó",)},
    "T-ASM": {
        "part_of_speech": "határozott névelő",
        "case": "tárgyeset",
        "number": "egyes",
        "gender": "hímnem",
    },
    "T-NSM": {
        "part_of_speech": "határozott névelő",
        "case": "alanyeset",
        "number": "egyes",
        "gender": "hímnem",
    },
    "V-2AMS-3S": {
        "part_of_speech": "ige",
        "tense": "második aorisztosz",
        "voice": "mediális",
        "mood": "kötőmód",
        "person": "harmadik",
        "number": "egyes",
    },
    "V-AAI-3S": {
        "part_of_speech": "ige",
        "tense": "aorisztosz",
        "voice": "aktív",
        "mood": "kijelentő",
        "person": "harmadik",
        "number": "egyes",
    },
    "V-PAP-NSM": {
        "part_of_speech": "ige",
        "tense": "jelen idő",
        "voice": "aktív igenem",
        "verb_form": "participium",
        "case": "alanyeset",
        "number": "egyes",
        "gender": "hímnem",
    },
    "V-AAN": {
        "part_of_speech": "ige",
        "tense": "aorisztosz",
        "voice": "aktív",
        "verb_form": "infinitivus",
    },
    "V-PAS-3S": {
        "part_of_speech": "ige",
        "tense": "jelen",
        "voice": "aktív",
        "mood": "kötőmód",
        "person": "harmadik",
        "number": "egyes",
    },
}

_PART_OF_SPEECH_PREFIXES = {
    "A": "melléknév",
    "ADV": "határozószó",
    "CONJ": "kötőszó",
    "N": "főnév",
    "P": "személyes névmás",
    "PREP": "elöljárószó",
    "PRT": "partikula",
    "T": "határozott névelő",
    "V": "ige",
}


def parse_morphology_hu(code: str) -> HungarianMorphology:
    raw_code = code.strip()
    fields = _DOCUMENTED_JHN_3_16_CODES.get(raw_code)
    if fields is not None:
        return _morphology(raw_code, fields)

    if not raw_code:
        return _morphology(raw_code, {})

    parts = tuple(part for part in raw_code.split("-") if part)
    part_of_speech = _PART_OF_SPEECH_PREFIXES.get(parts[0]) if parts else None
    unknown_parts = parts[1:] if part_of_speech else parts
    return _morphology(
        raw_code,
        {
            "part_of_speech": part_of_speech,
            "extra": unknown_parts,
        },
    )


def format_morphology_hu(morphology: HungarianMorphology) -> str:
    parts: list[str] = []
    if morphology.part_of_speech:
        parts.append(morphology.part_of_speech)
    if morphology.tense:
        parts.append(morphology.tense)
    if morphology.voice:
        parts.append(morphology.voice)
    if morphology.mood:
        parts.append(morphology.mood)
    if morphology.verb_form:
        parts.append(morphology.verb_form)
    if morphology.person:
        parts.append(f"{morphology.person} személy")
    if morphology.number:
        parts.append(f"{morphology.number} szám")
    if morphology.case:
        parts.append(morphology.case)
    if morphology.gender:
        parts.append(morphology.gender)
    if morphology.degree:
        parts.append(morphology.degree)
    if morphology.extra:
        parts.append(f"egyéb: {', '.join(morphology.extra)}")
    return ", ".join(parts)


def _morphology(
    raw_code: str, fields: dict[str, str | tuple[str, ...] | None]
) -> HungarianMorphology:
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
    )


def _string_field(
    fields: dict[str, str | tuple[str, ...] | None], name: str
) -> str | None:
    value = fields.get(name)
    return value if isinstance(value, str) else None
