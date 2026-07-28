"""RÚF 2014 igehely-lekérés a szentiras.hu nyilvános oldalairól.

Nem függ Streamlitől. A fejezet HTML-jébe ágyazott `verse-data` JSON-t
olvassa (megbízhatóbb, mint a látható DOM scraping), és a tiszta `verse`
mezőt használja — a keresztutalások a `verse_formatted.links` mezőben
vannak, nem a szövegben.

URL-forma: https://szentiras.hu/biblia/ruf/{BOOK}/{chapter}
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable

import requests

TRANSLATION_NAME = "RÚF 2014"
SOURCE_NAME = "szentiras.hu"
COPYRIGHT_NOTICE = "© Magyar Bibliatársulat, 2014"
BASE_URL = "https://szentiras.hu/biblia/ruf"
USER_AGENT = "TextusHomiletics/2.1 (+https://textus.ro; RUF passage loader)"
DEFAULT_CONNECT_TIMEOUT_S = 6.0
DEFAULT_READ_TIMEOUT_S = 20.0
DEFAULT_TIMEOUT_S = DEFAULT_READ_TIMEOUT_S
DEFAULT_TIMEOUT = (DEFAULT_CONNECT_TIMEOUT_S, DEFAULT_READ_TIMEOUT_S)
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_DELAYS_S = (0.5, 1.5)
CACHE_TTL_S = 24 * 60 * 60
STALE_CACHE_WARNING = (
    "A szentiras.hu jelenleg nem érhető el; a korábban eltárolt szöveget jelenítjük meg."
)
RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504}

_VERSE_DATA_RE = re.compile(
    r'<script\s+id="verse-data"\s+type="application/json"\s*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)

# Fejezet-cache: (book_code, chapter) -> {"fetched_at": float, "url": str, "verses": {n: text}}
_CHAPTER_CACHE: dict[tuple[str, int], dict[str, Any]] = {}

# Passage-cache: (translation, book_code, chapter, verse_start, verse_end) -> result dict
_PASSAGE_CACHE: dict[tuple[str, str, int, int | None, int | None], dict[str, Any]] = {}


@dataclass(frozen=True)
class BookInfo:
    code: str  # USFM / szentiras.hu kód (pl. JHN, 1CO, JUD)
    abbr: str  # elsődleges magyar rövidítés megjelenítéshez
    single_chapter: bool = False


@dataclass(frozen=True)
class RufHttpError(ConnectionError):
    status_code: int
    reason: str
    transient: bool = False

    def __str__(self) -> str:
        if self.transient:
            return (
                "Átmeneti külső szolgáltatási hiba a szentiras.hu válaszában: "
                f"HTTP {self.status_code} {self.reason}".strip()
            )
        return (
            "A szentiras.hu nem tudta kiszolgálni ezt az igehelyet: "
            f"HTTP {self.status_code} {self.reason}".strip()
        )


@dataclass(frozen=True)
class ChapterFetchResult:
    verses: dict[int, str]
    url: str
    warnings: list[str]
    cache_status: str


class RufPermanentFetchFailure(ValueError):
    pass


def _fold(text: str) -> str:
    """Ékezetmentes, kisbetűs, szóközmentes kulcs."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFKD", text)
    ascii_ish = "".join(ch for ch in norm if not unicodedata.combining(ch))
    return re.sub(r"[\s.]+", "", ascii_ish.casefold())


# (BookInfo, alias lista) — az aliasokból épül a keresőtábla.
_BOOK_DEFS: list[tuple[BookInfo, tuple[str, ...]]] = [
    # Ószövetség
    (BookInfo("GEN", "1Móz"), ("1Moz", "1Móz", "IMoz", "IMÓZ", "Mozes1", "Genesis", "Ter", "Teremtes")),
    (BookInfo("EXO", "2Móz"), ("2Moz", "2Móz", "IIMoz", "Exodus", "Kiv", "Kivonulas")),
    (BookInfo("LEV", "3Móz"), ("3Moz", "3Móz", "IIIMoz", "Leviticus", "Lev")),
    (BookInfo("NUM", "4Móz"), ("4Moz", "4Móz", "IVMoz", "Numeri", "Szam", "Szám")),
    (BookInfo("DEU", "5Móz"), ("5Moz", "5Móz", "VMoz", "Deuteronomium", "Torv", "Törv")),
    (BookInfo("JOS", "Józs"), ("Jozs", "Józs", "Jozsue", "Joshua")),
    (BookInfo("JDG", "Bir"), ("Bir", "Bír", "Birak", "Bírák", "Judges")),
    (BookInfo("RUT", "Ruth"), ("Ruth", "Rut")),
    (BookInfo("1SA", "1Sám"), ("1Sam", "1Sám", "ISam", "ISÁM", "1Samuel")),
    (BookInfo("2SA", "2Sám"), ("2Sam", "2Sám", "IISam", "IISÁM", "2Samuel")),
    (BookInfo("1KI", "1Kir"), ("1Kir", "IKir", "1Kiralyok", "1Királyok")),
    (BookInfo("2KI", "2Kir"), ("2Kir", "IIKir", "2Kiralyok", "2Királyok")),
    (BookInfo("1CH", "1Krón"), ("1Kron", "1Krón", "IKron", "1Cronica", "1Krónika")),
    (BookInfo("2CH", "2Krón"), ("2Kron", "2Krón", "IIKron", "2Cronica", "2Krónika")),
    (BookInfo("EZR", "Ezd"), ("Ezd", "Ezra", "Ezsdras")),
    (BookInfo("NEH", "Neh"), ("Neh", "Nehemias", "Nehémiás")),
    (BookInfo("EST", "Eszt"), ("Eszt", "Eszter", "Esther")),
    (BookInfo("JOB", "Jób"), ("Job", "Jób")),
    (BookInfo("PSA", "Zsolt"), ("Zsolt", "Zsoltar", "Zsoltárok", "Psalm", "Psalms", "Zsol")),
    (BookInfo("PRO", "Péld"), ("Peld", "Péld", "Proverbia", "Peldabeszedek", "Példabeszédek")),
    (BookInfo("ECC", "Préd"), ("Pred", "Préd", "Predikator", "Prédikátor", "Ecclesiastes")),
    (BookInfo("SNG", "Énekek"), ("Enekek", "Énekek", "En", "Én", "Cantio", "Salomon")),
    (BookInfo("ISA", "Ézs"), ("Ezs", "Ézs", "Iz", "Ézsaiás", "Ezsaias", "Isaiah")),
    (BookInfo("JER", "Jer"), ("Jer", "Jeremias", "Jeremiás")),
    (BookInfo("LAM", "Jsir"), ("Jsir", "Siralmak", "JerSiralmai", "Lamentations")),
    (BookInfo("EZK", "Ez"), ("Ez", "Ezekiel", "Ezékiel")),
    (BookInfo("DAN", "Dán"), ("Dan", "Dán", "Daniel", "Dániel")),
    (BookInfo("HOS", "Hós"), ("Hos", "Hós", "Hoseas", "Hóseás")),
    (BookInfo("JOL", "Jóel"), ("Joel", "Jóel")),
    (BookInfo("AMO", "Ám"), ("Am", "Ám", "Amos", "Ámós")),
    (BookInfo("OBA", "Abd", True), ("Abd", "Abdias", "Abdiás", "Obad", "Obadias")),
    (BookInfo("JON", "Jón"), ("Jon", "Jón", "Jonas", "Jónás")),
    (BookInfo("MIC", "Mik"), ("Mik", "Mikeas", "Mikeás")),
    (BookInfo("NAM", "Náh"), ("Nah", "Náh", "Nahum", "Náhum")),
    (BookInfo("HAB", "Hab"), ("Hab", "Habakkuk")),
    (BookInfo("ZEP", "Zof"), ("Zof", "Zofonias", "Sofonias", "Zofóniás")),
    (BookInfo("HAG", "Agge"), ("Agge", "Haggeus", "Haggai")),
    (BookInfo("ZEC", "Zak"), ("Zak", "Zakarias", "Zakariás")),
    (BookInfo("MAL", "Mal"), ("Mal", "Malakias", "Malakiás")),
    # Újszövetség
    (BookInfo("MAT", "Mt"), ("Mt", "Mat", "Mate", "Máté", "Matthew")),
    (BookInfo("MRK", "Mk"), ("Mk", "Mar", "Mark", "Márk")),
    (BookInfo("LUK", "Lk"), ("Lk", "Luc", "Luk", "Luka", "Lukács")),
    (BookInfo("JHN", "Jn"), ("Jn", "Jan", "Janos", "János", "John", "Jhn")),
    (BookInfo("ACT", "ApCsel"), ("ApCsel", "Apcsel", "Act", "Csel", "Apostolok")),
    # Gemini gyakran ad teljes magyar nevet (Róma, nem Róm / Rómaiak).
    (
        BookInfo("ROM", "Róm"),
        ("Rom", "Róm", "Roma", "Róma", "Romanus", "Romaiak", "Rómaiak"),
    ),
    (
        BookInfo("1CO", "1Kor"),
        ("1Kor", "IKor", "1Cor", "1Korinthus", "1Korinthusiak"),
    ),
    (
        BookInfo("2CO", "2Kor"),
        ("2Kor", "IIKor", "2Cor", "2Korinthus", "2Korinthusiak"),
    ),
    (BookInfo("GAL", "Gal"), ("Gal", "Galata", "Galatak", "Galaták")),
    (BookInfo("EPH", "Ef"), ("Ef", "Eph", "Efezus", "Efezusiak", "Efézusiak")),
    (BookInfo("PHP", "Fil"), ("Fil", "Phil", "Filippi", "Philippiek", "Filippiek")),
    (BookInfo("COL", "Kol"), ("Kol", "Col", "Kolosse", "Kolossé", "Kolosséiak")),
    (
        BookInfo("1TH", "1Thess"),
        ("1Thess", "1Tess", "IThess", "1Thesszalonika", "1Thesszalonikaiak"),
    ),
    (
        BookInfo("2TH", "2Thess"),
        ("2Thess", "2Tess", "IIThess", "2Thesszalonika", "2Thesszalonikaiak"),
    ),
    (
        BookInfo("1TI", "1Tim"),
        ("1Tim", "ITim", "1Timothy", "1Timoteus", "1Timóteus"),
    ),
    (
        BookInfo("2TI", "2Tim"),
        ("2Tim", "IITim", "2Timothy", "2Timoteus", "2Timóteus"),
    ),
    (BookInfo("TIT", "Tit"), ("Tit", "Titusz", "Titus")),
    (BookInfo("PHM", "Filem", True), ("Filem", "Phm", "Filemon", "Philemon")),
    (BookInfo("HEB", "Zsid"), ("Zsid", "Heb", "Zsidok", "Zsidók", "Hebrews")),
    (BookInfo("JAS", "Jak"), ("Jak", "James", "Jakob", "Jakab")),
    (
        BookInfo("1PE", "1Pt"),
        ("1Pt", "1Pet", "IPt", "1Peter", "1Péter"),
    ),
    (BookInfo("2PE", "2Pt"), ("2Pt", "2Pet", "IIPt", "2Peter", "2Péter")),
    (BookInfo("1JN", "1Jn"), ("1Jn", "1Jan", "IJn", "1Janos", "1János")),
    (BookInfo("2JN", "2Jn", True), ("2Jn", "2Jan", "IIJn", "2Janos", "2János")),
    (BookInfo("3JN", "3Jn", True), ("3Jn", "3Jan", "IIIJn", "3Janos", "3János")),
    (BookInfo("JUD", "Júd", True), ("Jud", "Júd", "Judas", "Júdás", "Jude")),
    (
        BookInfo("REV", "Jel"),
        ("Jel", "Rev", "Apokalipszis", "Revelation", "Jelenesek", "Jelenések"),
    ),
]


def _build_book_lookup() -> dict[str, BookInfo]:
    lookup: dict[str, BookInfo] = {}
    for info, aliases in _BOOK_DEFS:
        for name in (info.code, info.abbr, *aliases):
            key = _fold(name)
            if key:
                lookup[key] = info
        # Szám + könyv szóköz nélkül is (1kor, 1moz)
        folded_abbr = _fold(info.abbr)
        if folded_abbr:
            lookup[folded_abbr] = info
    return lookup


_BOOK_LOOKUP = _build_book_lookup()


@dataclass(frozen=True)
class ParsedReference:
    book: BookInfo
    chapter: int
    verse_start: int | None
    verse_end: int | None
    requested_reference: str

    @property
    def normalized_reference(self) -> str:
        abbr = self.book.abbr
        if self.book.single_chapter:
            if self.verse_start is None:
                return abbr
            if self.verse_end is None or self.verse_end == self.verse_start:
                return f"{abbr} {self.verse_start}"
            return f"{abbr} {self.verse_start}–{self.verse_end}"
        if self.verse_start is None:
            return f"{abbr} {self.chapter}"
        if self.verse_end is None or self.verse_end == self.verse_start:
            return f"{abbr} {self.chapter},{self.verse_start}"
        return f"{abbr} {self.chapter},{self.verse_start}–{self.verse_end}"


def _empty_result(
    *,
    requested_reference: str,
    error: str,
    warnings: list[str] | None = None,
    source_url: str = "",
    normalized_reference: str = "",
    cache_status: str = "miss",
) -> dict[str, Any]:
    return {
        "success": False,
        "requested_reference": requested_reference or "",
        "normalized_reference": normalized_reference,
        "translation": TRANSLATION_NAME,
        "text": "",
        "verses": [],
        "source_name": SOURCE_NAME,
        "source_url": source_url,
        "copyright_notice": COPYRIGHT_NOTICE,
        "warnings": list(warnings or []),
        "error": error,
        "cache_status": cache_status,
    }


def _ok_result(
    *,
    requested_reference: str,
    normalized_reference: str,
    text: str,
    verses: list[dict[str, Any]] | None = None,
    source_url: str,
    warnings: list[str] | None = None,
    cache_status: str = "live",
) -> dict[str, Any]:
    return {
        "success": True,
        "requested_reference": requested_reference,
        "normalized_reference": normalized_reference,
        "translation": TRANSLATION_NAME,
        "text": text,
        "verses": list(verses or []),
        "source_name": SOURCE_NAME,
        "source_url": source_url,
        "copyright_notice": COPYRIGHT_NOTICE,
        "warnings": list(warnings or []),
        "error": "",
        "cache_status": cache_status,
    }


def clear_ruf_cache() -> None:
    _CHAPTER_CACHE.clear()
    _PASSAGE_CACHE.clear()


def parse_bible_reference(reference: str) -> ParsedReference:
    """Igehely → ParsedReference. ValueError érthető üzenettel."""
    raw = (reference or "").strip()
    if not raw:
        raise ValueError("Add meg az igehelyet (pl. Júd 17–20 vagy Jn 3,16–18).")

    # Kötőjelek egységesítése
    cleaned = (
        raw.replace("–", "-")
        .replace("—", "-")
        .replace("−", "-")
        .replace("‐", "-")
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Könyv + maradék
    m = re.match(
        r"^((?:[1-5]|I{1,3}|IV|V)\s*)?([A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű.]+)\s*(.*)$",
        cleaned,
    )
    if not m:
        raise ValueError(f"Nem értelmezhető igehely: {raw!r}")

    num_prefix = (m.group(1) or "").strip()
    name = (m.group(2) or "").strip().rstrip(".")
    rest = (m.group(3) or "").strip()

    book_token = f"{num_prefix}{name}".strip()
    # "1 Kor" jellegű: a regex a számot külön fogja, name=Kor
    if num_prefix and name:
        book_token = f"{num_prefix}{name}"

    info = _BOOK_LOOKUP.get(_fold(book_token))
    if info is None and num_prefix:
        # próbáljuk "1Kor" / "1 Kor" aliasokat
        info = _BOOK_LOOKUP.get(_fold(num_prefix + name))
    if info is None:
        raise ValueError(
            f"Ismeretlen könyv: {book_token!r}. "
            "Használj gyakori magyar rövidítést (pl. Jn, 1Kor, Júd, Zsolt)."
        )

    if not rest:
        if info.single_chapter:
            return ParsedReference(info, 1, None, None, raw)
        raise ValueError(
            f"Add meg a fejezetet is (pl. {info.abbr} 3 vagy {info.abbr} 3,16)."
        )

    # Fejezet / vers részek
    rest_norm = rest.replace(":", ",")
    # Csak számok, vessző, kötőjel, szóköz
    if not re.fullmatch(r"[\d,\-\s]+", rest_norm):
        raise ValueError(f"Hibás fejezet/vers rész: {rest!r}")

    rest_norm = re.sub(r"\s+", "", rest_norm)

    if "," in rest_norm:
        chapter_s, verse_part = rest_norm.split(",", 1)
        if not chapter_s.isdigit():
            raise ValueError(f"Hibás fejezet: {chapter_s!r}")
        chapter = int(chapter_s)
        if chapter < 1:
            raise ValueError("A fejezet száma legalább 1 legyen.")
        v_start, v_end = _parse_verse_span(verse_part)
        if info.single_chapter and chapter != 1:
            raise ValueError(
                f"A(z) {info.abbr} egyfejezetes könyv — a fejezet mindig 1 "
                f"(pl. {info.abbr} {v_start}"
                f"{'' if v_end is None or v_end == v_start else '–' + str(v_end)})."
            )
        return ParsedReference(info, 1 if info.single_chapter else chapter, v_start, v_end, raw)

    # Nincs vessző: "23" vagy "17-20"
    if "-" in rest_norm:
        left, right = rest_norm.split("-", 1)
        if not left.isdigit() or not right.isdigit():
            raise ValueError(f"Hibás tartomány: {rest!r}")
        a, b = int(left), int(right)
        if info.single_chapter:
            if a < 1 or b < 1:
                raise ValueError("A versszám legalább 1 legyen.")
            if a > b:
                raise ValueError(
                    f"Fordított verstartomány: {a}–{b}. "
                    "A kezdő vers ne legyen nagyobb a zárónál."
                )
            return ParsedReference(info, 1, a, b, raw)
        raise ValueError(
            f"Fejezettartomány nem támogatott. "
            f"Adj meg egy fejezetet (pl. {info.abbr} {a}) vagy "
            f"verseket vesszővel (pl. {info.abbr} {a},{b})."
        )

    if not rest_norm.isdigit():
        raise ValueError(f"Hibás fejezet/vers: {rest!r}")
    n = int(rest_norm)
    if n < 1:
        raise ValueError("A szám legalább 1 legyen.")
    if info.single_chapter:
        return ParsedReference(info, 1, n, n, raw)
    return ParsedReference(info, n, None, None, raw)


def _parse_verse_span(part: str) -> tuple[int, int | None]:
    part = (part or "").strip()
    if not part:
        raise ValueError("Hiányzik a versszám a vessző után.")
    if "-" in part:
        a_s, b_s = part.split("-", 1)
        if not a_s.isdigit() or not b_s.isdigit():
            raise ValueError(f"Hibás verstartomány: {part!r}")
        a, b = int(a_s), int(b_s)
        if a < 1 or b < 1:
            raise ValueError("A versszám legalább 1 legyen.")
        if a > b:
            raise ValueError(
                f"Fordított verstartomány: {a}–{b}. "
                "A kezdő vers ne legyen nagyobb a zárónál."
            )
        return a, b
    if not part.isdigit():
        raise ValueError(f"Hibás versszám: {part!r}")
    v = int(part)
    if v < 1:
        raise ValueError("A versszám legalább 1 legyen.")
    return v, v


def build_chapter_url(book_code: str, chapter: int) -> str:
    return f"{BASE_URL}/{book_code}/{int(chapter)}"


def extract_verse_data_json(html: str) -> dict[str, Any]:
    """HTML → verse-data objektum. Hiány / sérült struktúra → ValueError."""
    if not html or not html.strip():
        raise ValueError("Üres HTML válasz a szentiras.hu-tól.")
    m = _VERSE_DATA_RE.search(html)
    if not m:
        # Ismert „nincs ilyen oldal” / ismeretlen könyv: nincs verse-data
        raise ValueError(
            "A szentiras.hu oldalon nem található a várt verse-data adat. "
            "Lehet, hogy az igehely hibás, vagy az oldal HTML-struktúrája megváltozott."
        )
    raw = m.group(1).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "A szentiras.hu verse-data JSON-ja nem olvasható "
            f"(struktúraváltozás?). Részlet: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise ValueError("A verse-data nem objektum — váratlan HTML-struktúra.")
    verses = data.get("verses")
    if not isinstance(verses, list) or not verses:
        raise ValueError("A verse-data nem tartalmaz verseket.")
    return data


def verses_dict_from_verse_data(data: dict[str, Any]) -> dict[int, str]:
    """verse-data → {vers_szám: tiszta szöveg}. Keresztutalások nélkül."""
    out: dict[int, str] = {}
    verses = data.get("verses")
    if not isinstance(verses, list):
        raise ValueError("Hiányzó verses lista a verse-data-ban.")
    for item in verses:
        if not isinstance(item, dict):
            continue
        num_raw = item.get("verse_number")
        try:
            num = int(str(num_raw).strip())
        except (TypeError, ValueError):
            continue
        text = item.get("verse")
        if not isinstance(text, str) or not text.strip():
            # ne essünk vissza verse_formatted-re (linkek keveredhetnek)
            raise ValueError(
                f"A {num}. versnek hiányzik a tiszta `verse` mezője "
                "(parser / struktúraváltozás)."
            )
        cleaned = _clean_verse_text(text)
        if not cleaned:
            raise ValueError(f"A {num}. vers üres a forrásban.")
        out[num] = cleaned
    if not out:
        raise ValueError("Egyetlen érvényes vers sem olvasható ki a verse-data-ból.")
    return out


def _clean_verse_text(text: str) -> str:
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def format_passage_text(verses: dict[int, str], start: int, end: int) -> str:
    lines: list[str] = []
    for n in range(start, end + 1):
        if n not in verses:
            raise KeyError(n)
        lines.append(f"{n}. {verses[n]}")
    return "\n".join(lines)


def format_structured_verses(verses: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in verses:
        number = str(item.get("number") or "").strip()
        text = _clean_verse_text(str(item.get("text") or ""))
        if number and text:
            lines.append(f"{number}. {text}")
    return "\n".join(lines)


def select_verse_range(
    verses: dict[int, str],
    verse_start: int | None,
    verse_end: int | None,
) -> tuple[str, list[str], list[dict[str, Any]]]:
    """Szűrés a kért tartományra. Részleges találat → ValueError."""
    if not verses:
        raise ValueError("Üres verslista.")
    available = sorted(verses)
    if verse_start is None:
        start, end = available[0], available[-1]
    else:
        start = verse_start
        end = verse_end if verse_end is not None else verse_start

    missing = [n for n in range(start, end + 1) if n not in verses]
    if missing:
        if len(missing) == (end - start + 1):
            raise ValueError(
                f"A kért versek ({start}–{end}) nem találhatók ebben a fejezetben "
                f"(elérhető: {available[0]}–{available[-1]})."
            )
        raise ValueError(
            "Részleges találat: a kért tartományból hiányzik: "
            + ", ".join(str(n) for n in missing)
            + ". A betöltés nem sikerült teljesen."
        )
    selected = [{"number": n, "text": verses[n]} for n in range(start, end + 1)]
    text = format_structured_verses(selected)
    return text, [], selected


def _normalize_timeout(timeout: Any) -> tuple[float, float]:
    if isinstance(timeout, tuple) and len(timeout) == 2:
        return (float(timeout[0]), float(timeout[1]))
    if isinstance(timeout, list) and len(timeout) == 2:
        return (float(timeout[0]), float(timeout[1]))
    if timeout is None:
        return DEFAULT_TIMEOUT
    value = float(timeout)
    return (min(value, DEFAULT_CONNECT_TIMEOUT_S), value)


def _cache_is_fresh(entry: dict[str, Any], *, ttl_s: float) -> bool:
    if ttl_s <= 0:
        return False
    try:
        fetched_at = float(entry.get("fetched_at") or 0.0)
    except (TypeError, ValueError):
        return False
    return (time.time() - fetched_at) <= ttl_s


def _is_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, RufHttpError):
        return exc.transient
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    return False


def _format_fetch_error(exc: BaseException, *, attempts: int) -> str:
    prefix = "Külső szolgáltatási kapcsolat hibája: "
    if isinstance(exc, RufHttpError):
        return prefix + str(exc)
    if isinstance(exc, TimeoutError):
        return (
            prefix
            + "a szentiras.hu nem válaszolt időben "
            + f"({attempts} próbálkozás után)."
        )
    if isinstance(exc, ConnectionError):
        return prefix + f"nem sikerült kapcsolódni a szentiras.hu-hoz ({exc})."
    return prefix + str(exc)


def _default_http_get(url: str, *, timeout: Any = DEFAULT_TIMEOUT) -> str:
    connect_timeout, read_timeout = _normalize_timeout(timeout)
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            timeout=(connect_timeout, read_timeout),
        )
    except requests.Timeout as exc:
        raise TimeoutError("A szentiras.hu nem válaszolt időben.") from exc
    except requests.ConnectionError as exc:
        raise ConnectionError("Nincs elérhető kapcsolat a szentiras.hu-hoz.") from exc
    status = int(response.status_code)
    if status in RETRYABLE_HTTP_STATUS:
        raise RufHttpError(status, response.reason or "", transient=True)
    if 400 <= status < 500:
        raise RufHttpError(status, response.reason or "", transient=False)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise ConnectionError(f"HTTP-hiba a szentiras.hu-tól: {status}") from exc
    response.encoding = response.encoding or "utf-8"
    return response.text


def _call_http_get(
    getter: Callable[..., str],
    url: str,
    *,
    timeout: Any,
) -> str:
    try:
        return getter(url, timeout=timeout)
    except TypeError:
        return getter(url)  # type: ignore[call-arg, misc]


def fetch_chapter_verses(
    book_code: str,
    chapter: int,
    *,
    timeout: Any = DEFAULT_TIMEOUT,
    http_get: Callable[..., str] | None = None,
    use_cache: bool = True,
    cache_ttl_s: float = CACHE_TTL_S,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_delays_s: tuple[float, ...] = DEFAULT_RETRY_DELAYS_S,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[dict[int, str], str]:
    """Egy fejezet versei + forrás URL. Cache-eli a fejezetet."""
    result = _fetch_chapter_verses_with_meta(
        book_code,
        chapter,
        timeout=timeout,
        http_get=http_get,
        use_cache=use_cache,
        cache_ttl_s=cache_ttl_s,
        max_attempts=max_attempts,
        retry_delays_s=retry_delays_s,
        sleep=sleep,
    )
    return result.verses, result.url


def _fetch_chapter_verses_with_meta(
    book_code: str,
    chapter: int,
    *,
    timeout: Any = DEFAULT_TIMEOUT,
    http_get: Callable[..., str] | None = None,
    use_cache: bool = True,
    cache_ttl_s: float = CACHE_TTL_S,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_delays_s: tuple[float, ...] = DEFAULT_RETRY_DELAYS_S,
    sleep: Callable[[float], None] = time.sleep,
) -> ChapterFetchResult:
    key = (book_code.upper(), int(chapter))
    url = build_chapter_url(key[0], key[1])
    if use_cache and key in _CHAPTER_CACHE and _cache_is_fresh(
        _CHAPTER_CACHE[key], ttl_s=cache_ttl_s
    ):
        cached = _CHAPTER_CACHE[key]
        return ChapterFetchResult(
            verses=dict(cached["verses"]),
            url=str(cached["url"]),
            warnings=[],
            cache_status="fresh",
        )

    getter = http_get or _default_http_get
    attempts = max(1, int(max_attempts))
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            html = _call_http_get(getter, url, timeout=_normalize_timeout(timeout))
            break
        except Exception as exc:
            last_exc = exc
            if not _is_transient_error(exc) or attempt >= attempts:
                is_transient = _is_transient_error(exc)
                if is_transient and use_cache and key in _CHAPTER_CACHE:
                    cached = _CHAPTER_CACHE[key]
                    return ChapterFetchResult(
                        verses=dict(cached["verses"]),
                        url=str(cached["url"]),
                        warnings=[STALE_CACHE_WARNING],
                        cache_status="stale_fallback",
                    )
                message = _format_fetch_error(exc, attempts=attempt)
                if not is_transient:
                    raise RufPermanentFetchFailure(message) from exc
                if isinstance(exc, TimeoutError):
                    raise TimeoutError(message) from exc
                raise ConnectionError(message) from exc
            delay = (
                retry_delays_s[min(attempt - 1, len(retry_delays_s) - 1)]
                if retry_delays_s
                else 0.0
            )
            if delay > 0:
                sleep(delay)
    else:
        assert last_exc is not None
        raise last_exc

    data = extract_verse_data_json(html)
    # Fejezet-egyezés ellenőrzése, ha van
    ch_raw = data.get("chapter")
    if ch_raw is not None:
        try:
            if int(str(ch_raw)) != key[1]:
                raise ValueError(
                    f"A forrás más fejezetet adott vissza ({ch_raw}), "
                    f"mint a kért ({key[1]})."
                )
        except (TypeError, ValueError):
            pass

    verses = verses_dict_from_verse_data(data)
    _CHAPTER_CACHE[key] = {
        "fetched_at": time.time(),
        "url": url,
        "verses": dict(verses),
    }
    return ChapterFetchResult(verses=verses, url=url, warnings=[], cache_status="live")


def fetch_ruf_passage(
    reference: str,
    *,
    timeout: Any = DEFAULT_TIMEOUT,
    http_get: Callable[..., str] | None = None,
    use_cache: bool = True,
    cache_ttl_s: float = CACHE_TTL_S,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_delays_s: tuple[float, ...] = DEFAULT_RETRY_DELAYS_S,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Központi belépési pont: igehely → RÚF szöveg eredménydict."""
    requested = (reference or "").strip()
    try:
        parsed = parse_bible_reference(requested)
    except ValueError as exc:
        return _empty_result(requested_reference=requested, error=str(exc))

    passage_key = (
        TRANSLATION_NAME,
        parsed.book.code.upper(),
        int(parsed.chapter),
        parsed.verse_start,
        parsed.verse_end,
    )
    if use_cache and passage_key in _PASSAGE_CACHE and _cache_is_fresh(
        _PASSAGE_CACHE[passage_key], ttl_s=cache_ttl_s
    ):
        cached_result = dict(_PASSAGE_CACHE[passage_key]["result"])
        cached_result["cache_status"] = "fresh"
        return cached_result

    try:
        chapter_result = _fetch_chapter_verses_with_meta(
            parsed.book.code,
            parsed.chapter,
            timeout=timeout,
            http_get=http_get,
            use_cache=use_cache,
            cache_ttl_s=cache_ttl_s,
            max_attempts=max_attempts,
            retry_delays_s=retry_delays_s,
            sleep=sleep,
        )
    except TimeoutError as exc:
        stale = _PASSAGE_CACHE.get(passage_key) if use_cache else None
        if stale:
            stale_result = dict(stale["result"])
            stale_result["warnings"] = [*stale_result.get("warnings", []), STALE_CACHE_WARNING]
            stale_result["cache_status"] = "stale_fallback"
            return stale_result
        return _empty_result(
            requested_reference=requested,
            normalized_reference=parsed.normalized_reference,
            error=str(exc),
        )
    except ConnectionError as exc:
        stale = _PASSAGE_CACHE.get(passage_key) if use_cache else None
        if stale:
            stale_result = dict(stale["result"])
            stale_result["warnings"] = [*stale_result.get("warnings", []), STALE_CACHE_WARNING]
            stale_result["cache_status"] = "stale_fallback"
            return stale_result
        return _empty_result(
            requested_reference=requested,
            normalized_reference=parsed.normalized_reference,
            error=str(exc),
        )
    except ValueError as exc:
        return _empty_result(
            requested_reference=requested,
            normalized_reference=parsed.normalized_reference,
            source_url=build_chapter_url(parsed.book.code, parsed.chapter),
            error=str(exc),
        )
    except OSError as exc:
        return _empty_result(
            requested_reference=requested,
            normalized_reference=parsed.normalized_reference,
            error=f"Hálózati hiba: {exc}",
        )

    try:
        text, warnings, selected_verses = select_verse_range(
            chapter_result.verses, parsed.verse_start, parsed.verse_end
        )
    except ValueError as exc:
        return _empty_result(
            requested_reference=requested,
            normalized_reference=parsed.normalized_reference,
            source_url=chapter_result.url,
            error=str(exc),
        )

    if not text.strip():
        return _empty_result(
            requested_reference=requested,
            normalized_reference=parsed.normalized_reference,
            source_url=chapter_result.url,
            error="Üres találat: a kért szakasz szövege üres.",
        )

    result = _ok_result(
        requested_reference=requested,
        normalized_reference=parsed.normalized_reference,
        text=text,
        verses=selected_verses,
        source_url=chapter_result.url,
        warnings=[*chapter_result.warnings, *warnings],
        cache_status=chapter_result.cache_status,
    )
    if use_cache and chapter_result.cache_status != "stale_fallback":
        _PASSAGE_CACHE[passage_key] = {
            "fetched_at": time.time(),
            "result": dict(result),
        }
    return result


__all__ = [
    "TRANSLATION_NAME",
    "SOURCE_NAME",
    "COPYRIGHT_NOTICE",
    "BASE_URL",
    "USER_AGENT",
    "DEFAULT_CONNECT_TIMEOUT_S",
    "DEFAULT_READ_TIMEOUT_S",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_RETRY_DELAYS_S",
    "CACHE_TTL_S",
    "STALE_CACHE_WARNING",
    "RufHttpError",
    "ParsedReference",
    "BookInfo",
    "parse_bible_reference",
    "build_chapter_url",
    "extract_verse_data_json",
    "verses_dict_from_verse_data",
    "select_verse_range",
    "format_passage_text",
    "format_structured_verses",
    "fetch_chapter_verses",
    "fetch_ruf_passage",
    "clear_ruf_cache",
]
