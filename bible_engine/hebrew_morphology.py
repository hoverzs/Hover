from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class HebrewMorphology:
    code: str
    original_code: str = ""
    language: str = ""
    part_of_speech: str = ""
    component_type: str = ""
    components: tuple[dict[str, object], ...] = ()
    noun_type: str = ""
    adjective_type: str = ""
    pronoun_type: str = ""
    proper_name_type: str = ""
    particle_type: str = ""
    preposition_type: str = ""
    conjunction_type: str = ""
    verb_stem: str = ""
    verb_conjugation: str = ""
    person: str = ""
    gender: str = ""
    number: str = ""
    state: str = ""
    suffix_type: str = ""
    suffix_person: str = ""
    suffix_gender: str = ""
    suffix_number: str = ""
    english_expansion: str = ""
    unresolved_parts: tuple[str, ...] = ()
    status: str = "unresolved"

    @property
    def fully_decoded(self) -> bool:
        return self.status == "fully_decoded"


LANGUAGE = {"H": "Hebrew", "A": "Aramaic"}
FUNCTION = {
    "N": "Noun",
    "A": "Adjective",
    "P": "Pronoun",
    "R": "Preposition",
    "C": "Conjunction",
    "c": "Conjunction",
    "T": "Particle",
    "D": "Adverb",
    "V": "Verb",
    "S": "Suffix",
    "o": "Object marker",
    "d": "Article",
    "n": "Negative",
    "m": "Interrogative",
    "r": "Relative",
}
PARTICLE_FORMS = {
    "a": "Article",
    "d": "Article",
    "o": "Object marker",
    "n": "Negative",
    "m": "Interrogative",
    "r": "Relative",
    "c": "Conjunction",
    "i": "Interrogative",
    "j": "Interjection",
}
STEMS = {
    "q": "Qal",
    "N": "Niphal",
    "p": "Piel",
    "P": "Pual",
    "h": "Hiphil",
    "H": "Hophal",
    "t": "Hithpael",
    "v": "Hishtaphel",
    "a": "Aphel",
    "A": "Haphel",
    "e": "Peal",
    "E": "Peil",
    "Q": "Peil",
    "i": "Ithpeel",
    "r": "Hithpaal",
    "s": "Shaphel",
    "c": "Tiphil",
    "u": "Hitpael",
    "M": "Hitpaal",
    "D": "Nithpael",
}
VERB_FORMS = {
    "p": "Perfect",
    "i": "Imperfect",
    "w": "Consecutive Imperfect",
    "v": "Consecutive Perfect",
    "m": "Imperative",
    "c": "Infinitive Construct",
    "a": "Infinitive Absolute",
    "r": "Participle",
    "s": "Passive Participle",
    "q": "Consecutive Perfect",
    "j": "Jussive",
    "n": "Imperfect",
    "u": "Conjunction Imperfect",
}
PERSON = {"1": "First", "2": "Second", "3": "Third"}
GENDER = {"m": "Masculine", "f": "Feminine", "b": "Either gender", "c": "Common"}
NUMBER = {"s": "Singular", "p": "Plural", "d": "Dual"}
STATE = {"a": "Absolute", "c": "Construct", "d": "Definite", "e": "Emphatic"}


def load_tehmc_expansions(source_path: str | Path) -> dict[str, str]:
    expansions: dict[str, str] = {}
    for raw_line in Path(source_path).read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or "\t" not in line:
            continue
        code, expansion = line.split("\t", 1)
        code = code.strip()
        if re.match(r"^(?:[AH][A-Za-z0-9]+|S[po]?[123]?[cfmb]?[spd]?)$", code):
            expansions[code] = expansion.strip()
    return expansions


def decode_hebrew_morphology(code: str, expansions: dict[str, str] | None = None) -> HebrewMorphology:
    clean = (code or "").strip()
    if not clean:
        return HebrewMorphology(code=clean, unresolved_parts=("empty",), status="malformed")
    parts = _split_morphology_components(clean)
    decoded = [
        _decode_single(
            part,
            expansions or {},
            original_code=raw_part,
            component_type=_component_type(part, index, len(parts)),
        )
        for index, (raw_part, part) in enumerate(parts)
    ]
    if len(decoded) == 1:
        return decoded[0]
    unresolved = tuple(item for morph in decoded for item in morph.unresolved_parts)
    primary = _primary_component(decoded)
    return HebrewMorphology(
        code=clean,
        original_code=clean,
        language=", ".join(dict.fromkeys(m.language for m in decoded if m.language)),
        part_of_speech=" + ".join(m.part_of_speech for m in decoded if m.part_of_speech),
        component_type="composite",
        components=tuple(_component_payload(morph) for morph in decoded),
        proper_name_type=primary.proper_name_type,
        particle_type=primary.particle_type,
        verb_stem=primary.verb_stem,
        verb_conjugation=primary.verb_conjugation,
        person=primary.person,
        gender=primary.gender,
        number=primary.number,
        state=primary.state,
        suffix_type=primary.suffix_type,
        suffix_person=primary.suffix_person,
        suffix_gender=primary.suffix_gender,
        suffix_number=primary.suffix_number,
        english_expansion=" / ".join(m.english_expansion for m in decoded if m.english_expansion),
        unresolved_parts=unresolved,
        status=_combined_status(decoded, unresolved),
    )


def audit_morphology_codes(codes: list[str], expansions: dict[str, str]) -> dict[str, object]:
    counts = Counter(codes)
    decoded = {code: decode_hebrew_morphology(code, expansions) for code in counts}
    fully = [code for code, morph in decoded.items() if morph.status == "fully_decoded"]
    partial = [code for code, morph in decoded.items() if morph.status == "partially_decoded"]
    unresolved = [code for code, morph in decoded.items() if morph.status == "unresolved"]
    malformed = [code for code, morph in decoded.items() if morph.status == "malformed"]
    total_tokens = sum(counts.values())
    return {
        "unique_morphology_codes": len(counts),
        "fully_decoded_codes": len(fully),
        "partially_decoded_codes": len(partial),
        "unresolved_codes": len(unresolved),
        "malformed_codes": len(malformed),
        "decoded_token_count": sum(counts[code] for code in fully),
        "partially_decoded_token_count": sum(counts[code] for code in partial),
        "unresolved_token_count": sum(counts[code] for code in unresolved),
        "malformed_token_count": sum(counts[code] for code in malformed),
        "token_coverage_percent": (
            100.0 * sum(counts[code] for code in fully) / total_tokens if total_tokens else 0.0
        ),
        "unique_code_coverage_percent": 100.0 * len(fully) / len(counts) if counts else 0.0,
        "unresolved_pattern_groups": _group_unresolved_patterns(counts, decoded),
        "most_common_unresolved": [
            {"code": code, "token_count": counts[code], "decoded": asdict(decoded[code])}
            for code in sorted(unresolved, key=lambda item: (-counts[item], item))[:100]
        ],
    }


def _decode_single(
    code: str,
    expansions: dict[str, str],
    *,
    original_code: str | None = None,
    component_type: str = "",
) -> HebrewMorphology:
    expansion = expansions.get(code, "")
    unresolved: list[str] = []
    if code.startswith("S"):
        values: dict[str, str | tuple[str, ...]] = {
            "code": code,
            "original_code": original_code or code,
            "component_type": component_type or "suffix",
            "part_of_speech": "Suffix",
            "english_expansion": expansion,
            "suffix_type": {
                "p": "Pronominal",
                "o": "Object",
                "d": "Directional",
                "n": "Emphatic",
            }.get(code[1:2], ""),
        }
        _decode_person_gender_number(code[2:], values, unresolved, prefix="suffix_")
        values["unresolved_parts"] = tuple(unresolved)
        values["status"] = _status(code, expansion, unresolved, values)
        return HebrewMorphology(**values)  # type: ignore[arg-type]
    language = LANGUAGE.get(code[:1], "")
    if not language:
        unresolved.append(code[:1] or "missing-language")
    function_code = code[1:2]
    pos = FUNCTION.get(function_code, "")
    if not pos:
        unresolved.append(function_code or "missing-function")
    values: dict[str, str | tuple[str, ...]] = {
        "code": code,
        "original_code": original_code or code,
        "language": language,
        "part_of_speech": pos,
        "component_type": component_type,
        "english_expansion": expansion,
    }
    tail = code[2:]
    if function_code == "V":
        if tail[:1] in STEMS:
            values["verb_stem"] = STEMS[tail[:1]]
        else:
            unresolved.append(tail[:1] or "missing-verb-stem")
        if tail[1:2] in VERB_FORMS:
            values["verb_conjugation"] = VERB_FORMS[tail[1:2]]
        else:
            unresolved.append(tail[1:2] or "missing-verb-form")
        _decode_verb_ending(tail[2:], values, unresolved)
    elif function_code in {"N", "A", "P"}:
        if tail[:1]:
            if function_code == "N":
                values["noun_type"] = {
                    "c": "Common",
                    "p": "Proper",
                    "g": "Gentilic",
                    "t": "Title",
                }.get(tail[:1], "")
            elif function_code == "A":
                values["adjective_type"] = {
                    "a": "Adjective",
                    "c": "Numerical",
                    "o": "Numerical position",
                }.get(tail[:1], "")
            else:
                values["pronoun_type"] = {"p": "Personal", "d": "Demonstrative", "i": "Interrogative"}.get(tail[:1], "")
            if function_code == "N" and values.get("noun_type") == "Proper":
                values["proper_name_type"] = {"l": "Location", "t": "Title"}.get(tail[1:2], "")
            if not values.get("noun_type") and not values.get("adjective_type") and not values.get("pronoun_type"):
                unresolved.append(tail[:1])
        tail = tail[1:]
        if function_code == "N" and values.get("proper_name_type"):
            tail = tail[1:]
        if function_code == "P" and tail[:1] in PERSON:
            _decode_person_gender_number(tail, values, unresolved)
        else:
            _decode_gender_number_state(tail, values, unresolved)
    elif function_code == "S":
        values["suffix_type"] = {
            "p": "Pronominal",
            "o": "Object",
            "d": "Directional",
            "n": "Emphatic",
        }.get(tail[:1], "")
        _decode_person_gender_number(tail[1:], values, unresolved, prefix="suffix_")
    elif function_code == "T":
        if tail[:1] in PARTICLE_FORMS:
            values["part_of_speech"] = PARTICLE_FORMS[tail[:1]]
            values["particle_type"] = PARTICLE_FORMS[tail[:1]]
            tail = tail[1:]
        if tail:
            unresolved.append(tail)
    elif function_code == "R":
        values["preposition_type"] = tail or ""
    elif function_code in {"C", "c"}:
        values["conjunction_type"] = tail or ""
    elif tail and expansion:
        pass
    elif tail:
        unresolved.append(tail)
    values["unresolved_parts"] = tuple(unresolved)
    values["status"] = _status(code, expansion, unresolved, values)
    return HebrewMorphology(**values)  # type: ignore[arg-type]


def _split_morphology_components(code: str) -> list[tuple[str, str]]:
    raw_parts = [part for part in code.split("/") if part]
    parts: list[tuple[str, str]] = []
    current_language = ""
    for part in raw_parts:
        if current_language and part[:1] == "A" and part[1:2] in {"a", "c", "o"} and part[2:3] in GENDER:
            normalized = current_language + part
        elif part[:1] in LANGUAGE or part.startswith("S"):
            normalized = part
        elif current_language:
            normalized = current_language + part
        else:
            normalized = part
        if normalized[:1] == "A" and normalized[1:2] in {"a", "c", "o"} and normalized[2:3] in GENDER:
            normalized = "A" + normalized
        elif normalized[:1] == "A" and normalized[1:2] not in FUNCTION:
            normalized = "A" + normalized
        if normalized[:1] in LANGUAGE:
            current_language = normalized[:1]
        parts.append((part, normalized))
    return parts


def _component_type(code: str, index: int, total: int) -> str:
    function_code = code[1:2] if code[:1] in LANGUAGE else code[:1]
    if function_code in {"C", "c", "R", "T", "D", "d", "o", "n", "m", "r"} and index < total - 1:
        return "prefix"
    if function_code == "S" or code.startswith("S"):
        return "suffix"
    return "core"


def _primary_component(decoded: list[HebrewMorphology]) -> HebrewMorphology:
    for morph in decoded:
        if morph.part_of_speech == "Verb":
            return morph
    for morph in decoded:
        if morph.component_type == "core":
            return morph
    return decoded[0]


def _component_payload(morph: HebrewMorphology) -> dict[str, object]:
    return {
        "code": morph.code,
        "original_code": morph.original_code or morph.code,
        "language": morph.language,
        "component_type": morph.component_type,
        "part_of_speech": morph.part_of_speech,
        "noun_type": morph.noun_type,
        "adjective_type": morph.adjective_type,
        "pronoun_type": morph.pronoun_type,
        "proper_name_type": morph.proper_name_type,
        "particle_type": morph.particle_type,
        "preposition_type": morph.preposition_type,
        "conjunction_type": morph.conjunction_type,
        "verb_stem": morph.verb_stem,
        "verb_conjugation": morph.verb_conjugation,
        "person": morph.person,
        "gender": morph.gender,
        "number": morph.number,
        "state": morph.state,
        "suffix_type": morph.suffix_type,
        "suffix_person": morph.suffix_person,
        "suffix_gender": morph.suffix_gender,
        "suffix_number": morph.suffix_number,
        "english_expansion": morph.english_expansion,
        "unresolved_parts": morph.unresolved_parts,
        "status": morph.status,
    }


def _status(
    code: str,
    expansion: str,
    unresolved: list[str],
    values: dict[str, str | tuple[str, ...]],
) -> str:
    if not code or any(item.startswith("missing-") for item in unresolved):
        return "malformed"
    if unresolved:
        return "partially_decoded" if expansion or _has_decoded_morphology(values) else "unresolved"
    return "fully_decoded" if expansion or code[:1] in LANGUAGE or code.startswith("S") else "unresolved"


def _has_decoded_morphology(values: dict[str, str | tuple[str, ...]]) -> bool:
    for field in (
        "part_of_speech",
        "noun_type",
        "adjective_type",
        "pronoun_type",
        "proper_name_type",
        "particle_type",
        "preposition_type",
        "conjunction_type",
        "verb_stem",
        "verb_conjugation",
        "person",
        "gender",
        "number",
        "state",
        "suffix_type",
        "suffix_person",
        "suffix_gender",
        "suffix_number",
    ):
        if values.get(field):
            return True
    return False


def _combined_status(decoded: list[HebrewMorphology], unresolved: tuple[str, ...]) -> str:
    if any(item.status == "malformed" for item in decoded):
        return "malformed"
    if unresolved:
        return (
            "partially_decoded"
            if any(item.status in {"fully_decoded", "partially_decoded"} for item in decoded)
            else "unresolved"
        )
    if all(item.status == "fully_decoded" for item in decoded):
        return "fully_decoded"
    return "partially_decoded"


def _group_unresolved_patterns(
    counts: Counter[str],
    decoded: dict[str, HebrewMorphology],
) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for code, morph in decoded.items():
        if morph.status not in {"unresolved", "malformed"}:
            continue
        pattern = _pattern_for_code(code)
        group = grouped.setdefault(
            pattern,
            {
                "pattern": pattern,
                "unique_code_count": 0,
                "affected_tokens": 0,
                "examples": [],
                "needed_parser_fix": _parser_fix_for_pattern(pattern),
                "documentation_reference": "TEHMC full morphology code table",
            },
        )
        group["unique_code_count"] = int(group["unique_code_count"]) + 1
        group["affected_tokens"] = int(group["affected_tokens"]) + counts[code]
        examples = group["examples"]
        if isinstance(examples, list) and len(examples) < 10:
            examples.append({"code": code, "token_count": counts[code], "unresolved_parts": morph.unresolved_parts})
    return sorted(grouped.values(), key=lambda item: (-int(item["affected_tokens"]), str(item["pattern"])))


def _pattern_for_code(code: str) -> str:
    return re.sub(r"\d", "0", re.sub(r"[a-z]", "x", re.sub(r"[A-Z]", "X", code)))


def _parser_fix_for_pattern(pattern: str) -> str:
    if "/" in pattern:
        return "Decode slash-separated component analyses with inherited language code."
    if pattern.startswith("S"):
        return "Decode standalone suffix morphology."
    return "Check TEHMC expansion and structural code consumption."


def _decode_person_gender_number(
    tail: str,
    values: dict[str, str | tuple[str, ...]],
    unresolved: list[str],
    *,
    prefix: str = "",
) -> None:
    if not tail:
        return
    if tail[:1] in PERSON:
        values[f"{prefix}person"] = PERSON[tail[:1]]
        tail = tail[1:]
    if tail[:1] in GENDER:
        values[f"{prefix}gender"] = GENDER[tail[:1]]
        tail = tail[1:]
    if tail[:1] in NUMBER:
        values[f"{prefix}number"] = NUMBER[tail[:1]]
        tail = tail[1:]
    if tail:
        unresolved.append(tail)


def _decode_verb_ending(
    tail: str,
    values: dict[str, str | tuple[str, ...]],
    unresolved: list[str],
) -> None:
    if values.get("verb_conjugation") in {"Infinitive Construct", "Infinitive Absolute"} and len(tail) <= 1:
        if not tail:
            return
        if tail in STATE:
            values["state"] = STATE[tail]
        else:
            unresolved.append(tail)
        return
    if values.get("verb_conjugation") in {
        "Participle",
        "Passive Participle",
    }:
        _decode_gender_number_state(tail, values, unresolved)
        return
    _decode_person_gender_number(tail, values, unresolved)


def _decode_gender_number_state(
    tail: str,
    values: dict[str, str | tuple[str, ...]],
    unresolved: list[str],
) -> None:
    if tail[:1] in GENDER:
        values["gender"] = GENDER[tail[:1]]
        tail = tail[1:]
    if tail[:1] in NUMBER:
        values["number"] = NUMBER[tail[:1]]
        tail = tail[1:]
    if tail[:1] in STATE:
        values["state"] = STATE[tail[:1]]
        tail = tail[1:]
    if tail:
        unresolved.append(tail)
