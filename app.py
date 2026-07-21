import streamlit as st
import requests
import urllib3
import base64
import json
import io
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_AUTOSAVE_INTERVAL_S = 180  # 3 perc — csak bejelentkezve, megnyitott projektnél


from workspace_data import (
    PROJECT_DATA_KEYS,
    WORKSPACE_KEYS,
    WORKSPACE_LIST_KEYS,
    WORKSPACE_STR_KEYS,
    build_workspace_payload,
    project_content_fingerprint,
)

# =========================================================
# VERZIÓ
# =========================================================
APP_VERSION = "1.0"
APP_NAME = "TEXTUS"
APP_SUBTITLE = "Homiletikai műhely"
APP_TAGLINE = "A szövegtől a szószékig"
APP_SCRIPTURE = (
    "„A teljes Írás Istentől ihletett és hasznos a tanításra, a feddésre, "
    "a megjobbításra és az igazságban való nevelésre.”"
)
APP_SCRIPTURE_REF = "— 2Timóteus 3,16"
APP_DOMAIN = "textus.ro"
APP_STREAMLIT_URL = "https://textus.streamlit.app"
FEEDBACK_TO_EMAIL = "hoverzsolt@gmail.com"

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(
    page_title=f"{APP_NAME} {APP_VERSION}",
    page_icon="📖",
    layout="wide"
)


# =========================================================
# BEÉPÍTETT (KÖZÖS) GEMINI API KULCS
# =========================================================
#
# Az alapértelmezett kulcsot SOHA nem írjuk a forráskódba.
# Források (priorítás — fontos a sorrend):
#   1) `GEMINI_API_KEY` környezeti változó (Docker / CI / explicit felülírás)
#   2) `.streamlit/secrets.toml` az `app.py` könyvtárában (`Path(__file__)`):
#      mindig ehhez a projekthez kötött kulcs; nem írja felül egy másik
#      mappából indított Streamlit által betöltött `st.secrets`.
#   3) `st.secrets["GEMINI_API_KEY"]` — Streamlit Cloud + helyi, ha a cwd
#      alatti `.streamlit/secrets.toml` az egyetlen elérhető forrás.
#
# Ha egyik sincs, a felhasználó a Beállítások fülön adhat meg saját kulcsot.

def _read_gemini_key_from_project_secrets_file() -> str:
    """`.streamlit/secrets.toml` az app fájl melletti projektgyökérben (TOML)."""
    p = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"
    if not p.is_file():
        return ""
    try:
        import tomllib  # py3.11+
    except ImportError:
        return ""
    try:
        with p.open("rb") as f:
            data = tomllib.load(f)
        v = data.get("GEMINI_API_KEY")
        if v:
            return str(v).strip()
    except Exception:
        pass
    return ""


def _load_builtin_api_key() -> str:
    """Beépített kulcs: env > projekt secrets.toml > Streamlit cwd secrets."""
    env_k = (os.environ.get("GEMINI_API_KEY", "") or "").strip()
    if env_k:
        return env_k
    v2 = _read_gemini_key_from_project_secrets_file()
    if v2:
        return v2
    try:
        v = st.secrets.get("GEMINI_API_KEY", "")
        if v:
            return str(v).strip()
    except Exception:
        pass
    return ""


BUILTIN_API_KEY = _load_builtin_api_key()


# =========================================================
# RÖGZÍTETT GEMINI MODELL
# =========================================================
#
# --- Gemini REST modellek (költség-optimalizált páros) --------------------
# A `generate_text(..., tab_label=…)` a `resolve_gemini_model_for_tab()` alapján
# választ modellt. Beépített közös kulcsnál: `gemini-2.5-flash` vagy
# `gemini-2.5-flash-lite`. Saját kulcsnál opcionális kézi modellválasztás;
# alapértelmezés („auto”) = ugyanaz a fül szerinti párosítás.
#
# `LOCKED_MODEL` = fő (Flash) modell-ID — backward compat + „ismeretlen” fül.

LOCKED_MODEL = "gemini-2.5-flash"
GEMINI_MODEL_FLASH_LITE = "gemini-2.5-flash-lite"
GEMINI_MODEL_PRO = "gemini-3.1-pro-preview"
GEMINI_MODEL_FLASH_3 = "gemini-3-flash-preview"
# A sorozattervezőhöz a mélyebb (Flash) modellt használjuk — több hetes,
# strukturált, teológiailag igényes Markdownt termel. A régebbi
# `gemini-1.5-flash` v1beta-n már gyakran nem elérhető (404 / not supported).
GEMINI_MODEL_SERIES_PLANNER = LOCKED_MODEL
LOCKED_MODEL_DISPLAY = "Gemini 2.5 Flash"
GEMINI_MODEL_PRO_DISPLAY = "Gemini 3.1 Pro"
GEMINI_MODEL_FLASH_3_DISPLAY = "Gemini 3 Flash"
OWN_KEY_MODEL_AUTO = "auto"
GEMINI_MODEL_DISPLAY_BY_ID: dict[str, str] = {
    LOCKED_MODEL: LOCKED_MODEL_DISPLAY,
    GEMINI_MODEL_FLASH_LITE: "Gemini 2.5 Flash Lite",
    GEMINI_MODEL_PRO: GEMINI_MODEL_PRO_DISPLAY,
    GEMINI_MODEL_FLASH_3: GEMINI_MODEL_FLASH_3_DISPLAY,
}
# Saját kulcsnál választható modellek (kulcs = API modell-ID).
OWN_KEY_MODEL_OPTIONS: dict[str, str] = {
    OWN_KEY_MODEL_AUTO: "Alapértelmezett (fül szerint: Flash / Flash Lite)",
    LOCKED_MODEL: LOCKED_MODEL_DISPLAY,
    GEMINI_MODEL_FLASH_LITE: "Gemini 2.5 Flash Lite",
    GEMINI_MODEL_FLASH_3: GEMINI_MODEL_FLASH_3_DISPLAY,
    GEMINI_MODEL_PRO: GEMINI_MODEL_PRO_DISPLAY,
}

# Kulcs = `generate_text(..., tab_label=…)` (SECTION_LABELS magyar címek +
# speciális hívások). A finomító chat `tab_label="chat: {cím}"` — a resolver
# levágja a `chat:` prefixet, így ugyanaz a kulcs érvényes.
GEMINI_MODEL_BY_TAB_LABEL: dict[str, str] = {
    # --- gemini-2.5-flash (mély elemzés) ---
    "Exegézis": LOCKED_MODEL,
    "Teológia": LOCKED_MODEL,
    "Eredeti szöveg": LOCKED_MODEL,
    "Eredeti szöveg tanulmányozása": LOCKED_MODEL,
    "API teszt": LOCKED_MODEL,
    # --- gemini-2.5-flash-lite (összegzés, háttér, könnyebb szekciók) ---
    "Áttekintés": GEMINI_MODEL_FLASH_LITE,
    "Kortörténet": GEMINI_MODEL_FLASH_LITE,
    "Illusztrációk": GEMINI_MODEL_FLASH_LITE,
    "Aktualizálás": GEMINI_MODEL_FLASH_LITE,
    "Vázlat": GEMINI_MODEL_FLASH_LITE,
    "Énekajánló": GEMINI_MODEL_FLASH_LITE,
    "Prédikációvázlat": GEMINI_MODEL_FLASH_LITE,
    "Igehirdetési sorozat tervező": GEMINI_MODEL_SERIES_PLANNER,
}


def _is_using_own_api_key() -> bool:
    """A felhasználó saját kulcsot adott meg (nem a beépített közös kulcsot)."""
    if bool(st.session_state.get("using_builtin_key", True)):
        return False
    return bool((st.session_state.get("api_key") or "").strip())


def _own_key_model_override() -> str | None:
    """Saját kulcsnál kézzel választott modell, vagy None (= fül szerinti alap)."""
    if not _is_using_own_api_key():
        return None
    choice = (st.session_state.get("user_model_choice") or OWN_KEY_MODEL_AUTO).strip()
    if choice == OWN_KEY_MODEL_AUTO or choice not in OWN_KEY_MODEL_OPTIONS:
        return None
    return choice


def resolve_gemini_model_for_tab(tab_label: str) -> str:
    """Visszaadja a `…/models/{id}:generateContent` modell-ID-t a fül alapján.

    A teljes táblázat: `GEMINI_MODEL_BY_TAB_LABEL`. Ismeretlen címkénél
    a biztonságos alapértelmezés a `LOCKED_MODEL` (Flash).
    Saját kulcsnál, ha a felhasználó modellt választott, az minden hívásra
    érvényes; „Alapértelmezett” esetén a fül szerinti Flash / Flash Lite páros.
    """
    override = _own_key_model_override()
    if override:
        return override
    raw = (tab_label or "").strip()
    if raw.lower().startswith("chat:"):
        raw = raw.split(":", 1)[1].strip()
    return GEMINI_MODEL_BY_TAB_LABEL.get(raw, LOCKED_MODEL)

# =========================================================
# SEGÉDFÜGGVÉNYEK
# =========================================================

def find_file(possible_names):
    for name in possible_names:
        if Path(name).exists():
            return name
    return None


def file_to_base64(file_path):
    with open(file_path, "rb") as file:
        return base64.b64encode(file.read()).decode()


# =========================================================
# HÁTTÉR ÉS LOGÓ
# =========================================================

background_file = find_file([
    "background.jpg",
    "background.jpeg",
    "background.png",
    "background.webp",
    "background.jpg.jpg"
])

logo_file = find_file([
    "textus_logo.png",
    "logo.png",
    "logo.jpg",
    "logo.jpeg",
    "logo.webp",
    "emmaus_logo.png",  # visszafelé kompatibilitás — régi telepítésekhez
])

igehely_icon_file = find_file([
    r"C:\Users\Hover\PreAPP\icons\igehely.png",
    "icon/igehely.png",
    "icon/igehely.svg",
    "icon/igehely.webp",
    "icon/igehely.jpg",
    "icon/igehely.jpeg",
    "icons/igehely.png",
    "icons/igehely.svg",
    "icons/igehely.webp",
    "icons/igehely.jpg",
    "icons/igehely.jpeg",
    "ikon/igehely.png",
    "ikon/igehely.svg",
    "ikon/igehely.webp",
    "ikon/igehely.jpg",
    "ikon/igehely.jpeg",
])

exegezis_icon_file = find_file([
    r"C:\Users\Hover\PreAPP\icons\egzegezis.png",
    "icons/egzegezis.png",
    "icons/egzegezis.svg",
    "icons/egzegezis.webp",
    "icons/egzegezis.jpg",
    "icons/egzegezis.jpeg",
])

if background_file:
    bg_encoded = file_to_base64(background_file)

    if background_file.endswith(".png"):
        bg_mime = "image/png"
    elif background_file.endswith(".webp"):
        bg_mime = "image/webp"
    else:
        bg_mime = "image/jpeg"

    background_css = f"""
    background-image:
        linear-gradient(rgba(248,245,238,0.80), rgba(248,245,238,0.80)),
        url("data:{bg_mime};base64,{bg_encoded}");
    background-size: cover;
    background-position: center;
    background-attachment: fixed;
    """
else:
    background_css = "background-color: #f6f1e8;"

igehely_icon_css = ""
if igehely_icon_file:
    if igehely_icon_file.endswith(".svg"):
        with open(igehely_icon_file, "r", encoding="utf-8") as svg_file:
            svg_content = svg_file.read()
        svg_content = svg_content.replace("\n", "").replace('"', "'").replace("#", "%23")
        icon_url = f"data:image/svg+xml;utf8,{svg_content}"
    else:
        icon_encoded = file_to_base64(igehely_icon_file)
        if igehely_icon_file.endswith(".png"):
            icon_mime = "image/png"
        elif igehely_icon_file.endswith(".webp"):
            icon_mime = "image/webp"
        else:
            icon_mime = "image/jpeg"
        icon_url = f"data:{icon_mime};base64,{icon_encoded}"

    igehely_icon_css = f"""
.stTabs [data-baseweb="tab"]:nth-of-type(1) p::before,
.stTabs [data-baseweb="tab"]:nth-of-type(1) span::before {{
    content: "";
    width: 1.34rem;
    height: 1.34rem;
    border-radius: 3px;
    background-image: url("{icon_url}");
    background-size: contain;
    background-repeat: no-repeat;
    background-position: center;
    filter: drop-shadow(0 1px 0 rgba(255,255,255,0.62))
            drop-shadow(0 1px 4px rgba(84,53,27,0.24));
}}
"""

exegezis_icon_css = ""
if exegezis_icon_file:
    if exegezis_icon_file.endswith(".svg"):
        with open(exegezis_icon_file, "r", encoding="utf-8") as svg_file:
            svg_content = svg_file.read()
        svg_content = svg_content.replace("\n", "").replace('"', "'").replace("#", "%23")
        icon_url = f"data:image/svg+xml;utf8,{svg_content}"
    else:
        icon_encoded = file_to_base64(exegezis_icon_file)
        if exegezis_icon_file.endswith(".png"):
            icon_mime = "image/png"
        elif exegezis_icon_file.endswith(".webp"):
            icon_mime = "image/webp"
        else:
            icon_mime = "image/jpeg"
        icon_url = f"data:{icon_mime};base64,{icon_encoded}"

    exegezis_icon_css = f"""
.stTabs [data-baseweb="tab"]:nth-of-type(3) p::before,
.stTabs [data-baseweb="tab"]:nth-of-type(3) span::before {{
    content: "";
    width: 1.34rem;
    height: 1.34rem;
    border-radius: 3px;
    background-image: url("{icon_url}");
    background-size: contain;
    background-repeat: no-repeat;
    background-position: center;
    filter: drop-shadow(0 1px 0 rgba(255,255,255,0.62))
            drop-shadow(0 1px 4px rgba(84,53,27,0.24));
}}
"""

# Letisztult, egységes tab-ikon megjelenéshez az egyedi képes ikonokat kikapcsoljuk.
igehely_icon_css = ""
exegezis_icon_css = ""


# =========================================================
# CSS
# =========================================================

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&family=Inter:wght@400;500;600;700&family=Playfair+Display:wght@600;700&family=Lora:ital,wght@0,500;1,500;1,600&display=swap');
@import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css');

.stApp {{
    {background_css}
    color: #2f2a24;
    font-family: "Inter", "Segoe UI", sans-serif;
}}

.stApp::before {{
    content: "";
    position: fixed;
    inset: 0;
    background:
        radial-gradient(ellipse 70% 55% at 50% -8%, rgba(255, 240, 210, 0.20), transparent 55%),
        radial-gradient(circle at 18% 18%, rgba(255, 224, 182, 0.12), transparent 42%),
        radial-gradient(circle at 84% 12%, rgba(120, 152, 195, 0.12), transparent 36%),
        radial-gradient(circle at 50% 92%, rgba(98, 70, 42, 0.12), transparent 46%);
    pointer-events: none;
    z-index: 0;
    mix-blend-mode: soft-light;
}}

.stApp::after {{
    content: "";
    position: fixed;
    inset: 0;
    background:
        radial-gradient(ellipse 110% 90% at 50% 50%, transparent 40%, rgba(28, 18, 8, 0.22) 88%, rgba(18, 12, 4, 0.38) 100%),
        linear-gradient(180deg, rgba(255, 255, 255, 0.06), transparent 24%, transparent 76%, rgba(20, 12, 4, 0.12));
    pointer-events: none;
    z-index: 0;
    mix-blend-mode: multiply;
}}

.stApp > header,
.stApp > div,
.stMainBlockContainer {{
    position: relative;
    z-index: 1;
}}

.block-container {{
    max-width: 1450px;
    padding-top: 0.6rem;
    padding-bottom: 3.5rem;
    padding-left: 1.35rem;
    padding-right: 1.35rem;
}}

header[data-testid="stHeader"],
div[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"] {{
    display: none !important;
    height: 0 !important;
    visibility: hidden !important;
}}

/* Streamlit components iframe (0 magasság) ne foglaljon helyet */
iframe[title="streamlit_components.v1.html.html"],
iframe[height="0"] {{
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    border: 0 !important;
    display: block;
}}

[data-testid="stAppViewContainer"] > .main,
section.main {{
    padding-top: 0 !important;
}}

.stApp {{
    padding-top: 0 !important;
}}

.main-card {{
    background:
        linear-gradient(
            145deg,
            rgba(255, 251, 244, 0.38),
            rgba(238, 226, 206, 0.26) 52%,
            rgba(218, 200, 174, 0.22)
        ),
        radial-gradient(circle at 14% -8%, rgba(255, 255, 255, 0.42), transparent 52%),
        radial-gradient(circle at 92% 110%, rgba(122, 145, 176, 0.12), transparent 55%);
    backdrop-filter: blur(48px) saturate(165%);
    -webkit-backdrop-filter: blur(48px) saturate(165%);
    border: 1px solid rgba(255, 255, 255, 0.55);
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.78) inset,
        0 0 0 1px rgba(255, 230, 188, 0.18) inset,
        0 0 38px rgba(255, 220, 170, 0.10) inset,
        0 -1px 0 rgba(58, 38, 18, 0.10) inset,
        0 0 0 1px rgba(255, 224, 178, 0.16),
        0 0 60px rgba(255, 220, 170, 0.18),
        0 4px 10px rgba(40, 28, 14, 0.10),
        0 18px 32px rgba(40, 28, 14, 0.18),
        0 38px 70px rgba(28, 18, 6, 0.34),
        0 64px 120px rgba(18, 12, 4, 0.44);
    padding: 38px 44px 34px;
    border-radius: 32px;
    margin-bottom: 38px;
    transition: transform 0.36s cubic-bezier(0.4, 0.0, 0.2, 1),
                box-shadow 0.36s cubic-bezier(0.4, 0.0, 0.2, 1);
    position: relative;
    overflow: hidden;
    isolation: isolate;
}}

.main-card::before {{
    content: "";
    position: absolute;
    inset: -60px;
    background:
        radial-gradient(ellipse 65% 45% at 50% -8%, rgba(255, 220, 170, 0.32), transparent 60%),
        radial-gradient(ellipse 80% 60% at 50% 110%, rgba(122, 145, 176, 0.18), transparent 65%);
    filter: blur(28px);
    pointer-events: none;
    z-index: -1;
}}

.main-card:hover {{
    transform: translateY(-5px);
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.86) inset,
        0 0 0 1px rgba(255, 230, 188, 0.22) inset,
        0 0 50px rgba(255, 220, 170, 0.14) inset,
        0 -1px 0 rgba(58, 38, 18, 0.12) inset,
        0 0 0 1px rgba(255, 224, 178, 0.22),
        0 0 80px rgba(255, 220, 170, 0.24),
        0 6px 14px rgba(40, 28, 14, 0.12),
        0 24px 42px rgba(40, 28, 14, 0.24),
        0 52px 92px rgba(28, 18, 6, 0.42),
        0 80px 150px rgba(18, 12, 4, 0.50);
}}

.main-card::after {{
    content: "";
    position: absolute;
    inset: 0;
    background:
        linear-gradient(120deg, rgba(255, 255, 255, 0.52), transparent 36%),
        linear-gradient(200deg, transparent 58%, rgba(122, 145, 176, 0.08)),
        radial-gradient(ellipse 80% 28% at 50% -2%, rgba(255, 252, 246, 0.62), transparent 68%),
        radial-gradient(ellipse 80% 50% at 50% 110%, rgba(255, 224, 178, 0.08), transparent 65%);
    pointer-events: none;
    border-radius: inherit;
}}

.header-card {{
    margin-top: 0.4rem;
}}

.header-grid {{
    display: grid;
    grid-template-columns: 300px 1fr;
    gap: 1.4rem;
    align-items: center;
}}

.header-logo {{
    display: flex;
    align-items: center;
    justify-content: center;
}}

.header-logo .main-logo {{
    width: 280px !important;
    max-width: none !important;
    height: auto;
    filter: drop-shadow(0 6px 14px rgba(40, 28, 14, 0.28));
}}

.main-logo-fallback {{
    font-family: "Cormorant Garamond", Georgia, serif;
    font-size: 4.2rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: #6b4f2e;
    text-shadow: 0 6px 14px rgba(40, 28, 14, 0.28);
}}

.header-text {{
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
}}

.header-caption {{
    margin-top: 0.4rem;
    display: inline-block;
    width: max-content;
    padding: 0.22rem 0.7rem;
    border-left: 2px solid rgba(122, 145, 176, 0.6);
    background: linear-gradient(
        90deg,
        rgba(232, 238, 247, 0.55),
        rgba(232, 238, 247, 0)
    );
    border-radius: 4px;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.92rem;
    font-weight: 700;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: #3d567a;
    text-shadow:
        0 1px 0 rgba(255, 255, 255, 0.65),
        0 0 14px rgba(122, 145, 176, 0.18);
}}

@media (max-width: 720px) {{
    .header-grid {{
        grid-template-columns: 1fr;
        text-align: center;
        gap: 0.8rem;
    }}
    .header-caption {{
        margin-left: auto;
        margin-right: auto;
    }}
}}

.main-title {{
    font-family: "Playfair Display", "Cormorant Garamond", Georgia, serif;
    font-size: clamp(3rem, 5vw, 4.15rem);
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #2b2116;
    line-height: 0.96;
    margin-bottom: 6px;
    text-shadow:
        0 1px 0 rgba(255, 255, 255, 0.62),
        0 8px 18px rgba(71, 52, 30, 0.16);
}}

.version-line {{
    font-family: "Inter", "Helvetica Neue", system-ui, sans-serif;
    font-size: 0.92rem;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #5d4830;
    margin-top: 0.2rem;
    margin-bottom: 0.15rem;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.55);
}}

/* ===== Rögzített modell — read-only kijelzés a Beállításokon ===== */
.locked-model-row {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.85rem;
    margin: 0.4rem 0 0.2rem;
}}

.locked-model-label {{
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.92rem;
    font-weight: 600;
    color: #4a3e32;
    letter-spacing: 0.01em;
}}

.locked-model-value {{
    display: inline-flex;
    align-items: center;
    gap: 0.55rem;
    padding: 0.45rem 0.85rem;
    font-family: "Cormorant Garamond", Georgia, serif;
    font-size: 1.12rem;
    font-weight: 700;
    color: #2a1f12;
    background:
        linear-gradient(180deg,
            rgba(255, 252, 246, 0.62),
            rgba(238, 226, 206, 0.42));
    border: 1px solid rgba(206, 189, 166, 0.65);
    border-radius: 12px;
    box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.72),
        0 4px 10px rgba(60, 42, 22, 0.10);
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.55);
}}

.locked-model-pill {{
    font-family: "Inter", system-ui, sans-serif;
    font-size: 0.66rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #6a4a22;
    padding: 0.14rem 0.5rem;
    background: rgba(228, 211, 178, 0.55);
    border: 1px solid rgba(166, 134, 86, 0.42);
    border-radius: 999px;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.6);
    text-shadow: none;
}}

.header-tagline {{
    font-family: "Cormorant Garamond", Georgia, serif;
    font-size: 1.22rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    color: #5a4630;
    line-height: 1.35;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.65);
}}

.subtitle {{
    font-family: "Lora", "Cormorant Garamond", Georgia, serif;
    font-size: 1.22rem;
    color: #4f3f31;
    font-style: italic;
    line-height: 1.48;
    max-width: 96ch;
    margin-top: 0.35rem;
    padding-left: 0.85rem;
    border-left: 2px solid rgba(141, 113, 79, 0.42);
    text-shadow:
        0 1px 0 rgba(255, 255, 255, 0.72),
        0 2px 10px rgba(255, 252, 246, 0.55);
}}

.scripture-ref {{
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.88rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    color: #6a5844;
    margin-top: 0.35rem;
    padding-left: 0.85rem;
}}

h1, h2, h3, h4, h5, h6 {{
    font-family: "Cormorant Garamond", Georgia, serif;
    color: #2a1f12;
    letter-spacing: 0.005em;
    text-rendering: optimizeLegibility;
    -webkit-font-smoothing: antialiased;
    font-feature-settings: "liga", "kern";
}}

h1 {{
    font-weight: 700;
    line-height: 1.05;
}}

h2 {{
    font-size: 2.25rem !important;
    font-weight: 700 !important;
    line-height: 1.18 !important;
    margin-top: 0.4rem !important;
    margin-bottom: 1.4rem !important;
    padding-bottom: 0.55rem;
    position: relative;
    border-bottom: none;
}}

h2::after {{
    content: "";
    display: block;
    position: absolute;
    left: 0;
    bottom: 0;
    width: 64px;
    height: 2px;
    border-radius: 2px;
    background: linear-gradient(
        90deg,
        rgba(141, 113, 79, 0.85),
        rgba(122, 145, 176, 0.65) 65%,
        transparent
    );
}}

h3 {{
    font-size: 1.55rem !important;
    font-weight: 600 !important;
    line-height: 1.32 !important;
    margin-top: 1.6rem !important;
    margin-bottom: 0.7rem !important;
    color: #3a2c1d !important;
}}

h4 {{
    font-size: 1.22rem !important;
    font-weight: 600 !important;
    font-style: italic;
    color: #4a3826 !important;
    margin-top: 1.2rem !important;
    margin-bottom: 0.5rem !important;
}}

.stMarkdown p,
.stMarkdown li,
.result-box p,
.result-box li {{
    font-family: "Lora", Georgia, serif;
    font-size: 1.04rem;
    line-height: 1.78;
    color: #34281c;
    font-weight: 400;
    letter-spacing: 0.002em;
    margin-bottom: 0.85rem;
}}

.stMarkdown p {{
    max-width: 78ch;
}}

.stMarkdown strong,
.result-box strong {{
    font-weight: 600;
    color: #2a1f12;
}}

.stMarkdown em,
.result-box em {{
    color: #5b4a37;
}}

.stMarkdown blockquote,
.result-box blockquote {{
    border-left: 3px solid rgba(141, 113, 79, 0.55);
    padding: 0.4rem 1rem;
    margin: 1rem 0 1.2rem;
    font-style: italic;
    color: #4a3826;
    background: linear-gradient(
        90deg,
        rgba(247, 240, 226, 0.45),
        rgba(247, 240, 226, 0)
    );
    border-radius: 0 8px 8px 0;
}}

.stMarkdown ul,
.stMarkdown ol,
.result-box ul,
.result-box ol {{
    padding-left: 1.4rem;
    margin-bottom: 1rem;
}}

.stMarkdown li,
.result-box li {{
    margin-bottom: 0.45rem;
}}

p, li, label {{
    color: #34281c;
    line-height: 1.7;
}}

label, .stTextInput label, .stTextArea label, .stSelectbox label {{
    color: #3e342a !important;
    font-size: 0.96rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.005em;
}}

.stCaption,
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p,
small {{
    opacity: 1 !important;
    letter-spacing: 0.16em !important;
    text-transform: uppercase !important;
    font-family: "Inter", "Segoe UI", sans-serif !important;
    font-size: 0.92rem !important;
    font-weight: 700 !important;
    color: #3d567a !important;
    text-shadow:
        0 1px 0 rgba(255, 255, 255, 0.65),
        0 0 14px rgba(122, 145, 176, 0.18) !important;
    margin-top: 0.35rem !important;
    display: inline-block;
    padding: 0.18rem 0.55rem;
    border-left: 2px solid rgba(122, 145, 176, 0.55);
    background: linear-gradient(
        90deg,
        rgba(232, 238, 247, 0.55),
        rgba(232, 238, 247, 0)
    );
    border-radius: 4px;
}}

.result-box {{
    background:
        linear-gradient(165deg, rgba(255, 253, 249, 0.52), rgba(245, 236, 222, 0.40)),
        radial-gradient(circle at 100% 0%, rgba(122, 145, 176, 0.10), transparent 55%);
    backdrop-filter: blur(28px) saturate(135%);
    -webkit-backdrop-filter: blur(28px) saturate(135%);
    border-radius: 22px;
    padding: 30px 32px;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.92) inset,
        0 -1px 0 rgba(118, 95, 70, 0.10) inset,
        0 0 0 1px rgba(255, 224, 178, 0.10),
        0 2px 4px rgba(60, 42, 22, 0.07),
        0 12px 22px rgba(60, 42, 22, 0.16),
        0 28px 50px rgba(38, 25, 10, 0.26);
    border: 1px solid rgba(225, 203, 172, 0.82);
    margin-top: 22px;
    margin-bottom: 16px;
    transition: transform 0.24s cubic-bezier(0.4, 0.0, 0.2, 1),
                box-shadow 0.24s cubic-bezier(0.4, 0.0, 0.2, 1);
    position: relative;
}}

.result-box:hover {{
    transform: translateY(-3px);
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.96) inset,
        0 -1px 0 rgba(118, 95, 70, 0.12) inset,
        0 0 0 1px rgba(255, 224, 178, 0.14),
        0 4px 8px rgba(60, 42, 22, 0.10),
        0 18px 32px rgba(60, 42, 22, 0.22),
        0 38px 64px rgba(38, 25, 10, 0.32);
}}

.result-box::before {{
    content: "";
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 4px;
    border-radius: 20px 0 0 20px;
    background: linear-gradient(180deg, rgba(141, 113, 79, 0.55), rgba(122, 145, 176, 0.55));
}}

.basket-box {{
    background:
        linear-gradient(155deg, rgba(255, 246, 231, 0.72), rgba(247, 235, 215, 0.52));
    backdrop-filter: blur(16px) saturate(120%);
    -webkit-backdrop-filter: blur(16px) saturate(120%);
    border-left: 5px solid #b67b3e;
    padding: 18px 18px 16px;
    border-radius: 14px;
    margin-bottom: 14px;
    box-shadow: 0 8px 18px rgba(84, 61, 35, 0.10);
}}

.stButton {{
    position: relative;
    isolation: isolate;
}}

/* ===== PRIMARY CTA (világos kékes + erős kontraszt + lebegő hover) ===== */
.stButton > button[kind="primary"],
.stButton > button[kind="primaryFormSubmit"] {{
    position: relative;
    background:
        linear-gradient(
            155deg,
            #e8eef8 0%,
            #d4e0f2 22%,
            #c5d6ea 48%,
            #b8c9e2 72%,
            #a8bad8 100%
        );
    color: #1a2838 !important;
    border: 1px solid rgba(122, 145, 176, 0.55);
    border-radius: 14px;
    padding: 0.7rem 1.5rem;
    min-height: 2.85rem;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.99rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    text-shadow:
        0 1px 0 rgba(255, 255, 255, 0.85);
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.92) inset,
        0 0 0 1px rgba(255, 255, 255, 0.35) inset,
        0 -1px 0 rgba(90, 108, 132, 0.12) inset,
        0 0 0 1px rgba(122, 145, 176, 0.22),
        0 2px 6px rgba(52, 68, 92, 0.12),
        0 10px 22px rgba(52, 68, 92, 0.16),
        0 20px 40px rgba(40, 54, 78, 0.12);
    transition: transform 0.24s cubic-bezier(0.34, 1.2, 0.64, 1),
                box-shadow 0.24s cubic-bezier(0.34, 1.2, 0.64, 1),
                background 0.24s ease,
                color 0.24s ease,
                border-color 0.24s ease;
    overflow: hidden;
    z-index: 1;
}}

.stButton > button[kind="primary"]::before,
.stButton > button[kind="primaryFormSubmit"]::before {{
    content: "";
    position: absolute;
    inset: -22px;
    background: radial-gradient(
        ellipse 70% 60% at 50% 0%,
        rgba(255, 252, 246, 0.55),
        rgba(180, 200, 230, 0.18) 45%,
        transparent 70%
    );
    filter: blur(12px);
    opacity: 0.85;
    transition: opacity 0.24s ease, transform 0.24s ease;
    pointer-events: none;
    z-index: -1;
}}

.stButton > button[kind="primary"]::after,
.stButton > button[kind="primaryFormSubmit"]::after {{
    content: "";
    position: absolute;
    inset: 0;
    background:
        linear-gradient(125deg, rgba(255, 255, 255, 0.55), transparent 42%),
        linear-gradient(210deg, transparent 55%, rgba(141, 113, 79, 0.06));
    pointer-events: none;
    border-radius: inherit;
    transition: opacity 0.24s ease;
}}

.stButton > button[kind="primary"]:hover,
.stButton > button[kind="primaryFormSubmit"]:hover {{
    background:
        linear-gradient(
            155deg,
            #eef3fb 0%,
            #dde9f6 24%,
            #ccdff0 50%,
            #bcd2e8 74%,
            #aec6df 100%
        );
    color: #13202e !important;
    border-color: rgba(100, 130, 168, 0.62);
    transform: translateY(-4px);
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.95) inset,
        0 0 0 1px rgba(255, 255, 255, 0.45) inset,
        0 -1px 0 rgba(90, 108, 132, 0.10) inset,
        0 0 0 1px rgba(122, 155, 198, 0.35),
        0 4px 10px rgba(52, 72, 98, 0.14),
        0 14px 28px rgba(52, 72, 98, 0.20),
        0 28px 52px rgba(40, 58, 82, 0.18),
        0 0 32px rgba(122, 155, 198, 0.28);
}}

.stButton > button[kind="primary"]:hover::before,
.stButton > button[kind="primaryFormSubmit"]:hover::before {{
    opacity: 1;
    transform: scale(1.04);
    background: radial-gradient(
        ellipse 75% 65% at 50% 0%,
        rgba(255, 255, 255, 0.65),
        rgba(160, 188, 220, 0.22) 48%,
        transparent 72%
    );
}}

.stButton > button[kind="primary"]:active,
.stButton > button[kind="primaryFormSubmit"]:active {{
    transform: translateY(-1px);
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.75) inset,
        0 0 0 1px rgba(255, 255, 255, 0.28) inset,
        0 2px 5px rgba(52, 68, 92, 0.14),
        0 8px 18px rgba(52, 68, 92, 0.16);
}}

.stButton > button[kind="primary"]:focus-visible,
.stButton > button[kind="primaryFormSubmit"]:focus-visible {{
    outline: 2px solid rgba(122, 155, 198, 0.85);
    outline-offset: 3px;
}}

.stButton > button[kind="primary"] > div > p,
.stButton > button[kind="primaryFormSubmit"] > div > p {{
    font-size: 0.99rem !important;
    letter-spacing: 0.04em !important;
    color: #1a2838 !important;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.85) !important;
}}

.stButton > button[kind="primary"]:hover > div > p,
.stButton > button[kind="primaryFormSubmit"]:hover > div > p {{
    color: #13202e !important;
}}

/* ===== SECONDARY (refined glass / quiet action) ===== */
.stButton > button:not([kind="primary"]):not([kind="primaryFormSubmit"]) {{
    position: relative;
    background:
        linear-gradient(
            145deg,
            rgba(255, 252, 247, 0.78),
            rgba(238, 228, 211, 0.58)
        );
    backdrop-filter: blur(14px) saturate(125%);
    -webkit-backdrop-filter: blur(14px) saturate(125%);
    color: #3a2c1d;
    border: 1px solid rgba(186, 158, 122, 0.55);
    border-radius: 12px;
    padding: 0.55rem 1.15rem;
    min-height: 2.55rem;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.94rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    text-transform: none;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.55);
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.78) inset,
        0 -1px 0 rgba(86, 64, 38, 0.10) inset,
        0 4px 8px rgba(58, 40, 22, 0.08),
        0 10px 18px rgba(38, 26, 12, 0.14);
    transition: transform 0.18s cubic-bezier(0.4, 0.0, 0.2, 1),
                box-shadow 0.18s cubic-bezier(0.4, 0.0, 0.2, 1),
                color 0.18s ease,
                border-color 0.18s ease,
                background 0.18s ease;
    overflow: hidden;
}}

.stButton > button:not([kind="primary"]):not([kind="primaryFormSubmit"]):hover {{
    background:
        linear-gradient(
            145deg,
            rgba(255, 253, 248, 0.92),
            rgba(240, 232, 218, 0.74)
        );
    color: #2c4a72;
    border-color: rgba(132, 156, 189, 0.62);
    transform: translateY(-1px);
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.82) inset,
        0 0 0 1px rgba(132, 156, 189, 0.22),
        0 6px 12px rgba(58, 76, 101, 0.16),
        0 14px 26px rgba(34, 50, 75, 0.18);
}}

.stButton > button:not([kind="primary"]):not([kind="primaryFormSubmit"]):active {{
    transform: translateY(0);
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.6) inset,
        0 -1px 0 rgba(86, 64, 38, 0.12) inset,
        0 4px 10px rgba(58, 40, 22, 0.14);
}}

.stButton > button:not([kind="primary"]):not([kind="primaryFormSubmit"]):focus-visible {{
    outline: 2px solid rgba(122, 145, 176, 0.6);
    outline-offset: 2px;
}}

/* ===== DESTRUCTIVE (refined burgundy / aged-red glass) ===== */
.btn-danger-marker {{
    display: none !important;
    height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
}}

.element-container:has(.btn-danger-marker) + .element-container .stButton > button {{
    background:
        linear-gradient(
            145deg,
            rgba(246, 226, 220, 0.78),
            rgba(229, 196, 184, 0.62)
        ) !important;
    color: #6e1f1f !important;
    border: 1px solid rgba(168, 76, 64, 0.45) !important;
    text-shadow: 0 1px 0 rgba(255, 250, 247, 0.55) !important;
    box-shadow:
        0 1px 0 rgba(255, 248, 245, 0.78) inset,
        0 -1px 0 rgba(120, 36, 28, 0.10) inset,
        0 4px 8px rgba(110, 36, 28, 0.10),
        0 12px 22px rgba(80, 22, 16, 0.18) !important;
    transition: transform 0.18s cubic-bezier(0.4, 0.0, 0.2, 1),
                box-shadow 0.18s cubic-bezier(0.4, 0.0, 0.2, 1),
                color 0.18s ease,
                border-color 0.18s ease,
                background 0.18s ease !important;
}}

.element-container:has(.btn-danger-marker) + .element-container .stButton > button:hover {{
    background:
        linear-gradient(
            145deg,
            rgba(248, 230, 224, 0.92),
            rgba(232, 198, 188, 0.78)
        ) !important;
    color: #5a1414 !important;
    border-color: rgba(168, 76, 64, 0.78) !important;
    transform: translateY(-1px) !important;
    box-shadow:
        0 1px 0 rgba(255, 248, 245, 0.85) inset,
        0 0 0 1px rgba(168, 76, 64, 0.30),
        0 8px 14px rgba(110, 36, 28, 0.18),
        0 18px 30px rgba(80, 22, 16, 0.26),
        0 0 26px rgba(186, 92, 80, 0.18) !important;
}}

.element-container:has(.btn-danger-marker) + .element-container .stButton > button:active {{
    transform: translateY(0) !important;
    box-shadow:
        0 1px 0 rgba(255, 248, 245, 0.55) inset,
        0 -1px 0 rgba(120, 36, 28, 0.16) inset,
        0 4px 10px rgba(110, 36, 28, 0.20) !important;
}}

.element-container:has(.btn-danger-marker) + .element-container .stButton > button:focus-visible {{
    outline: 2px solid rgba(168, 76, 64, 0.65) !important;
    outline-offset: 2px;
}}

.stTabs [data-baseweb="tab"] {{
    background:
        linear-gradient(
            145deg,
            rgba(255, 252, 246, 0.40),
            rgba(238, 228, 211, 0.26) 60%,
            rgba(220, 205, 180, 0.22)
        ),
        radial-gradient(circle at 0% 0%, rgba(255, 255, 255, 0.42), transparent 58%);
    backdrop-filter: blur(24px) saturate(140%);
    -webkit-backdrop-filter: blur(24px) saturate(140%);
    border-radius: 14px;
    margin-right: 8px;
    border: 1px solid rgba(206, 189, 166, 0.55);
    padding: 0.78rem 1.18rem;
    min-height: 2.85rem;
    font-weight: 700;
    font-size: 0.97rem;
    letter-spacing: 0.012em;
    color: #4a3e32;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.72) inset,
        0 -1px 0 rgba(76, 56, 32, 0.06) inset,
        0 6px 12px rgba(48, 36, 22, 0.10),
        0 14px 28px rgba(34, 24, 12, 0.18);
    transition: transform 0.22s cubic-bezier(0.4, 0.0, 0.2, 1),
                box-shadow 0.22s cubic-bezier(0.4, 0.0, 0.2, 1),
                background 0.22s ease,
                color 0.22s ease;
    position: relative;
    isolation: isolate;
}}

.stTabs [data-baseweb="tab"]::before {{
    content: "";
    position: absolute;
    inset: -16px -10px -10px;
    background: radial-gradient(ellipse 60% 50% at 50% 50%, rgba(122, 145, 176, 0.0), transparent 65%);
    filter: blur(14px);
    pointer-events: none;
    z-index: -1;
    transition: background 0.24s ease;
}}

.stTabs [data-baseweb="tab"] p,
.stTabs [data-baseweb="tab"] span {{
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 700 !important;
    font-size: 0.97rem !important;
    letter-spacing: 0.01em;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.44);
}}

.stTabs [data-baseweb="tab"] p::before,
.stTabs [data-baseweb="tab"] span::before {{
    font-family: "Font Awesome 6 Free";
    font-weight: 900;
    font-size: 0.96rem;
    opacity: 0.92;
    color: #6f7f95;
    text-shadow:
        0 1px 0 rgba(255, 255, 255, 0.62),
        0 0 8px rgba(111, 127, 149, 0.22);
    transition: transform 0.18s ease, color 0.18s ease;
}}

.stTabs [data-baseweb="tab"]:hover {{
    background:
        linear-gradient(145deg, rgba(255, 253, 248, 0.62), rgba(240, 232, 218, 0.44));
    color: #3a4f69;
    transform: translateY(-2px);
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.82) inset,
        0 0 0 1px rgba(132, 156, 189, 0.38),
        0 10px 18px rgba(58, 76, 101, 0.18),
        0 22px 34px rgba(34, 50, 75, 0.20);
    text-shadow: none;
}}

.stTabs [data-baseweb="tab"]:hover::before {{
    background: radial-gradient(ellipse 70% 55% at 50% 50%, rgba(122, 145, 176, 0.18), transparent 65%);
}}

.stTabs [aria-selected="true"] {{
    background:
        linear-gradient(
            160deg,
            rgba(252, 252, 249, 0.72),
            rgba(232, 240, 250, 0.58)
        ) !important;
    color: #1f2c3d !important;
    border-color: rgba(124, 151, 186, 0.92) !important;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.95) inset,
        0 0 0 1px rgba(255, 230, 188, 0.20) inset,
        0 0 28px rgba(122, 145, 176, 0.18) inset,
        0 0 0 1px rgba(124, 151, 186, 0.28),
        0 10px 18px rgba(48, 65, 90, 0.20),
        0 24px 40px rgba(28, 42, 64, 0.30) !important;
    transform: translateY(-3px);
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.65);
}}

.stTabs [aria-selected="true"]::before {{
    background: radial-gradient(ellipse 80% 60% at 50% 60%, rgba(122, 145, 176, 0.28), transparent 65%);
}}

.stTabs [aria-selected="true"]::after {{
    content: "";
    position: absolute;
    left: 16%;
    right: 16%;
    bottom: -7px;
    height: 3px;
    border-radius: 999px;
    background: linear-gradient(
        90deg,
        transparent,
        rgba(141, 113, 79, 0.85) 30%,
        rgba(122, 145, 176, 0.85) 70%,
        transparent
    );
    box-shadow: 0 0 12px rgba(141, 113, 79, 0.45);
    pointer-events: none;
}}

.stTabs [data-baseweb="tab"]:hover p::before,
.stTabs [data-baseweb="tab"]:hover span::before {{
    color: #4f6786;
    transform: translateY(-1px) scale(1.06);
}}

.stTabs [aria-selected="true"] p::before,
.stTabs [aria-selected="true"] span::before {{
    color: #3f5979;
    text-shadow:
        0 1px 0 rgba(255, 255, 255, 0.72),
        0 0 10px rgba(123, 151, 187, 0.35);
}}

.stTabs [data-baseweb="tab"]:nth-of-type(1) p::before,
.stTabs [data-baseweb="tab"]:nth-of-type(1) span::before {{ content: "\\f518"; }}
.stTabs [data-baseweb="tab"]:nth-of-type(2) p::before,
.stTabs [data-baseweb="tab"]:nth-of-type(2) span::before {{ content: "\\f02d"; }}
.stTabs [data-baseweb="tab"]:nth-of-type(3) p::before,
.stTabs [data-baseweb="tab"]:nth-of-type(3) span::before {{ content: "\\f002"; }}
.stTabs [data-baseweb="tab"]:nth-of-type(4) p::before,
.stTabs [data-baseweb="tab"]:nth-of-type(4) span::before {{ content: "\\f19c"; }}
.stTabs [data-baseweb="tab"]:nth-of-type(5) p::before,
.stTabs [data-baseweb="tab"]:nth-of-type(5) span::before {{ content: "\\f669"; }}
.stTabs [data-baseweb="tab"]:nth-of-type(6) p::before,
.stTabs [data-baseweb="tab"]:nth-of-type(6) span::before {{ content: "\\f03e"; }}
.stTabs [data-baseweb="tab"]:nth-of-type(7) p::before,
.stTabs [data-baseweb="tab"]:nth-of-type(7) span::before {{ content: "\\f57d"; }}
.stTabs [data-baseweb="tab"]:nth-of-type(8) p::before,
.stTabs [data-baseweb="tab"]:nth-of-type(8) span::before {{ content: "\\f303"; }}
.stTabs [data-baseweb="tab"]:nth-of-type(9) p::before,
.stTabs [data-baseweb="tab"]:nth-of-type(9) span::before {{ content: "\\f07a"; }}
.stTabs [data-baseweb="tab"]:nth-of-type(10) p::before,
.stTabs [data-baseweb="tab"]:nth-of-type(10) span::before {{ content: "\\f001"; }}
.stTabs [data-baseweb="tab"]:nth-of-type(11) p::before,
.stTabs [data-baseweb="tab"]:nth-of-type(11) span::before {{ content: "\\f013"; }}

{igehely_icon_css}
{exegezis_icon_css}

.stTabs [data-baseweb="tab-list"] {{
    display: flex !important;
    flex-wrap: wrap !important;
    row-gap: 0.55rem !important;
    column-gap: 0.42rem !important;
    overflow-x: visible !important;
    overflow-y: visible !important;
    padding-bottom: 0.65rem;
    margin-bottom: 0.6rem;
    border-bottom: 1px solid rgba(170, 149, 123, 0.20);
    white-space: normal !important;
}}

.stTabs [data-baseweb="tab-border"] {{
    display: none !important;
}}

.stTabs > div:first-child {{
    overflow: visible !important;
}}

.stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {{
    display: none;
}}

.stTabs [data-baseweb="tab-highlight"] {{
    height: 3px !important;
    border-radius: 999px;
    background: linear-gradient(90deg, #8f714f, #7a91b1, #8f714f) !important;
    box-shadow: 0 0 8px rgba(123, 151, 187, 0.42);
}}

.stTabs [aria-selected="true"] {{
    border-top: 2px solid rgba(122, 145, 176, 0.78) !important;
}}

.stTabs [data-baseweb="tab-panel"] {{
    background:
        linear-gradient(165deg, rgba(255, 253, 248, 0.48), rgba(244, 237, 226, 0.36)),
        radial-gradient(circle at 0% 0%, rgba(255, 255, 255, 0.38), transparent 52%);
    backdrop-filter: blur(26px) saturate(135%);
    -webkit-backdrop-filter: blur(26px) saturate(135%);
    border: 1px solid rgba(216, 199, 177, 0.78);
    border-radius: 18px;
    padding: 1.5rem 1.5rem 1.65rem;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.84) inset,
        0 -1px 0 rgba(118, 95, 70, 0.08) inset,
        0 0 0 1px rgba(255, 224, 178, 0.08),
        0 8px 18px rgba(54, 42, 25, 0.12),
        0 28px 56px rgba(34, 22, 8, 0.24);
    margin-bottom: 0.7rem;
    position: relative;
}}

/* Finom „olvasási köpeny” a üveges panelek szövegén — nem zavarja a háttér átlátszóságát */
.stTabs [data-baseweb="tab-panel"] p,
.stTabs [data-baseweb="tab-panel"] li,
.stTabs [data-baseweb="tab-panel"] label,
.stTabs [data-baseweb="tab-panel"] .stMarkdown p,
.stTabs [data-baseweb="tab-panel"] .stMarkdown li {{
    text-shadow: 0 1px 1px rgba(255, 255, 255, 0.78);
}}

.stTabs [data-baseweb="tab-panel"] h1,
.stTabs [data-baseweb="tab-panel"] h2,
.stTabs [data-baseweb="tab-panel"] h3 {{
    text-shadow:
        0 1px 0 rgba(255, 255, 255, 0.72),
        0 2px 12px rgba(255, 252, 246, 0.55);
}}

.result-box p,
.result-box li,
.result-box .stMarkdown p,
.result-box .stMarkdown li {{
    text-shadow: 0 1px 1px rgba(255, 255, 255, 0.78);
}}

section[data-testid="stSidebar"] {{
    background: linear-gradient(
        170deg,
        rgba(92, 60, 34, 0.52),
        rgba(66, 44, 28, 0.44)
    );
    backdrop-filter: blur(22px) saturate(120%);
    -webkit-backdrop-filter: blur(22px) saturate(120%);
    border-right: 1px solid rgba(255, 230, 196, 0.26);
    box-shadow: 8px 0 28px rgba(39, 24, 12, 0.25);
}}

section[data-testid="stSidebar"] * {{
    color: #fff8ec;
}}

section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stCaption {{
    color: #fff0da !important;
}}

section[data-testid="stSidebar"] .stAlert {{
    background: rgba(255, 245, 225, 0.16) !important;
    border: 1px solid rgba(255, 220, 174, 0.24) !important;
    border-radius: 12px !important;
}}

.stTextInput input,
.stTextArea textarea,
.stSelectbox div[data-baseweb="select"] {{
    background-color: rgba(255, 252, 246, 0.78) !important;
    color: #2f251b !important;
    border-radius: 13px !important;
    border: 1px solid rgba(181, 161, 136, 0.54) !important;
    box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.58),
        0 5px 12px rgba(74, 51, 28, 0.08);
    transition: all 0.16s cubic-bezier(0.4, 0.0, 0.2, 1);
}}

.stTextInput input:focus,
.stTextArea textarea:focus,
.stSelectbox div[data-baseweb="select"]:focus-within {{
    border-color: rgba(112, 144, 184, 0.78) !important;
    box-shadow:
        0 0 0 3px rgba(122, 155, 198, 0.24),
        0 8px 18px rgba(70, 84, 103, 0.14) !important;
}}

.stTextInput > div,
.stTextArea > div,
.stSelectbox > div {{
    margin-bottom: 0.2rem;
}}

.stTextInput input::placeholder,
.stTextArea textarea::placeholder {{
    color: rgba(90, 86, 82, 0.62) !important;
    line-height: 1.55 !important;
    opacity: 1; /* Firefox: a default 0.54 opacity-t felülírjuk a saját rgba-val */
}}

[data-testid="stChatMessage"] {{
    background: rgba(255, 252, 246, 0.58);
    backdrop-filter: blur(12px) saturate(120%);
    -webkit-backdrop-filter: blur(12px) saturate(120%);
    border: 1px solid rgba(218, 188, 152, 0.62);
    border-radius: 15px;
    box-shadow: 0 8px 18px rgba(72, 51, 31, 0.10);
}}

[data-testid="stChatMessage"]:hover {{
    box-shadow: 0 10px 22px rgba(72, 51, 31, 0.14);
}}

[data-testid="stChatInput"] > div {{
    background: rgba(255, 252, 246, 0.72);
    backdrop-filter: blur(10px) saturate(120%);
    -webkit-backdrop-filter: blur(10px) saturate(120%);
    border: 1px solid rgba(186, 147, 104, 0.35);
    border-radius: 14px;
}}

div[data-testid="stForm"] {{
    background: rgba(255, 249, 240, 0.34);
    backdrop-filter: blur(14px) saturate(125%);
    -webkit-backdrop-filter: blur(14px) saturate(125%);
    border: 1px solid rgba(220, 193, 157, 0.44);
    border-radius: 15px;
    padding: 0.85rem;
}}

.stAlert {{
    border-radius: 13px !important;
    border: 1px solid rgba(208, 171, 128, 0.38) !important;
    box-shadow: 0 7px 15px rgba(75, 53, 30, 0.09) !important;
}}

.stDivider {{
    margin-top: 2rem !important;
    margin-bottom: 1.7rem !important;
    opacity: 0.6;
}}

[data-testid="stHorizontalBlock"] {{
    gap: 1.2rem;
}}

/* ===== ARS POETICA / WORKSHOP MANIFESTO ===== */
.ars-section {{
    margin: 0 0 36px;
    padding: 30px 36px 30px;
    background:
        linear-gradient(165deg, rgba(252, 244, 228, 0.40), rgba(238, 224, 198, 0.28)),
        radial-gradient(circle at 14% -8%, rgba(255, 255, 255, 0.42), transparent 50%);
    backdrop-filter: blur(32px) saturate(145%);
    -webkit-backdrop-filter: blur(32px) saturate(145%);
    border: 1px solid rgba(208, 184, 142, 0.55);
    border-radius: 22px;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.65) inset,
        0 -1px 0 rgba(118, 86, 50, 0.10) inset,
        0 0 0 1px rgba(255, 224, 178, 0.14),
        0 8px 18px rgba(58, 40, 22, 0.14),
        0 22px 44px rgba(38, 25, 10, 0.22);
    position: relative;
    overflow: hidden;
}}

.ars-section::after {{
    content: "";
    position: absolute;
    inset: 0;
    background:
        linear-gradient(120deg, rgba(255, 255, 255, 0.44), transparent 40%),
        radial-gradient(ellipse 80% 30% at 50% -2%, rgba(255, 252, 246, 0.50), transparent 65%);
    pointer-events: none;
    border-radius: inherit;
}}

.ars-poetica {{
    position: relative;
    z-index: 1;
    font-family: "Lora", "Cormorant Garamond", Georgia, serif;
    font-style: italic;
    font-size: 1.18rem;
    line-height: 1.6;
    color: #4a3826;
    text-align: center;
    max-width: 78ch;
    margin: 0.1rem auto 1.4rem;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.55);
}}

.ars-divider {{
    position: relative;
    z-index: 1;
    width: 84px;
    height: 1.5px;
    margin: 0.4rem auto 1.5rem;
    background: linear-gradient(
        90deg,
        transparent,
        rgba(141, 113, 79, 0.78) 30%,
        rgba(122, 145, 176, 0.55) 70%,
        transparent
    );
    border-radius: 2px;
}}

.ars-stations {{
    position: relative;
    z-index: 1;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1.6rem;
    margin-top: 0.4rem;
}}

@media (max-width: 760px) {{
    .ars-stations {{
        grid-template-columns: 1fr;
        gap: 1.1rem;
    }}
}}

.ars-station {{
    padding: 0.2rem 0.4rem 0.2rem 0.85rem;
    border-left: 2px solid rgba(141, 113, 79, 0.45);
    text-align: left;
}}

.ars-numeral {{
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.22em;
    color: #8a6a3f;
    margin-bottom: 0.35rem;
    text-transform: uppercase;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.6);
}}

.ars-station-title {{
    font-family: "Cormorant Garamond", Georgia, serif;
    font-size: 1.32rem;
    font-weight: 700;
    color: #2a1f12;
    margin-bottom: 0.4rem;
    line-height: 1.22;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.65);
}}

.ars-station-text {{
    font-family: "Lora", Georgia, serif;
    font-size: 0.96rem;
    line-height: 1.62;
    color: #3e3023;
    margin: 0;
    text-shadow: 0 1px 1px rgba(255, 255, 255, 0.72);
}}

.ars-station-text a {{
    color: #6a4a22;
    font-weight: 600;
    text-decoration: none;
    border-bottom: 1px dotted rgba(106, 74, 34, 0.45);
    transition: color 160ms ease, border-color 160ms ease;
}}

.ars-station-text a:hover {{
    color: #8a5a1f;
    border-bottom-color: rgba(138, 90, 31, 0.85);
}}

.ars-footer {{
    margin-top: 2.6rem !important;
    margin-bottom: 1.2rem !important;
    opacity: 0.96;
}}


.feedback-wrap {{
    margin: 0 0 36px;
    padding: 28px 34px 30px;
    background:
        linear-gradient(165deg, rgba(252, 244, 228, 0.42), rgba(238, 224, 198, 0.30)),
        radial-gradient(circle at 86% -10%, rgba(122, 145, 176, 0.14), transparent 52%);
    backdrop-filter: blur(32px) saturate(145%);
    -webkit-backdrop-filter: blur(32px) saturate(145%);
    border: 1px solid rgba(208, 184, 142, 0.55);
    border-radius: 22px;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.65) inset,
        0 -1px 0 rgba(118, 86, 50, 0.10) inset,
        0 8px 18px rgba(58, 40, 22, 0.14),
        0 22px 44px rgba(38, 25, 10, 0.20);
}}

.feedback-header {{
    text-align: center;
    margin-bottom: 1.1rem;
}}

.feedback-header .ars-station-title {{
    margin-bottom: 0.45rem;
}}

.feedback-header .ars-station-text {{
    max-width: 68ch;
    margin: 0 auto;
}}

.feedback-wrap [data-testid="stForm"],
[data-testid="stForm"] {{
    border: none;
    padding: 0;
    background: transparent;
}}

[data-testid="stForm"] label {{
    font-family: "Inter", "Segoe UI", sans-serif !important;
    font-size: 0.88rem !important;
    font-weight: 600 !important;
    color: #4a3826 !important;
}}

[data-testid="stForm"] textarea,
[data-testid="stForm"] input {{
    background: rgba(255, 251, 244, 0.72) !important;
    border: 1px solid rgba(180, 150, 110, 0.45) !important;
    border-radius: 12px !important;
    font-family: "Lora", Georgia, serif !important;
    color: #3a2c1d !important;
}}

[data-testid="stForm"] button[kind="primaryFormSubmit"] {{
    background: linear-gradient(135deg, #5a7a9e, #3d567a) !important;
    border: 1px solid rgba(61, 86, 122, 0.35) !important;
    border-radius: 12px !important;
    font-family: "Inter", "Segoe UI", sans-serif !important;
    font-weight: 700 !important;
    letter-spacing: 0.04em;
    box-shadow: 0 8px 18px rgba(61, 86, 122, 0.22);
}}

/* ===== EREDETI SZÖVEG / WORD CARDS ===== */
.original-text-result {{
    padding: 32px 36px;
}}

.original-text-result h2 {{
    font-family: "Cormorant Garamond", Georgia, serif;
    font-size: 1.55rem !important;
    font-weight: 700 !important;
    color: #3a2c1d !important;
    margin-top: 1.6rem !important;
    margin-bottom: 0.9rem !important;
    padding-bottom: 0.4rem;
    position: relative;
    border-bottom: none;
}}

.original-text-result h2::after {{
    background: linear-gradient(
        90deg,
        rgba(141, 113, 79, 0.85),
        rgba(122, 145, 176, 0.55) 65%,
        transparent
    );
}}

.original-text-result h3 {{
    font-family: "Cormorant Garamond", "Times New Roman", serif !important;
    font-size: 2.05rem !important;
    font-weight: 700 !important;
    line-height: 1.2 !important;
    color: #2a1f12 !important;
    margin: 1.6rem 0 0.6rem !important;
    padding: 0.6rem 0 0.7rem 1rem;
    border-left: 3px solid rgba(141, 113, 79, 0.5);
    background: linear-gradient(
        90deg,
        rgba(255, 240, 210, 0.32),
        rgba(255, 240, 210, 0)
    );
    border-radius: 0 8px 8px 0;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.55);
}}

.original-text-result h3 em {{
    font-family: "Lora", Georgia, serif;
    font-style: italic;
    font-size: 1.05rem;
    font-weight: 500;
    color: #6b5638;
    margin-left: 0.55rem;
    letter-spacing: 0.04em;
    text-transform: lowercase;
    text-shadow: none;
}}

.original-text-result p {{
    font-family: "Lora", Georgia, serif;
    font-size: 1.02rem;
    line-height: 1.78;
    color: #34281c;
    margin-bottom: 0.85rem;
    max-width: 78ch;
}}

.original-text-result p strong {{
    display: inline-block;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.78rem;
    font-weight: 700;
    color: #3d567a;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    margin-right: 0.45rem;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.55);
}}

.original-text-result blockquote {{
    margin: 0.6rem 0 1.4rem;
    padding: 0.85rem 1.1rem;
    background: linear-gradient(
        90deg,
        rgba(246, 226, 220, 0.55),
        rgba(246, 226, 220, 0)
    );
    border-left: 3px solid rgba(168, 76, 64, 0.55);
    border-radius: 0 10px 10px 0;
    font-family: "Lora", Georgia, serif;
    font-size: 0.96rem;
    line-height: 1.65;
    color: #5a2a22;
    font-style: italic;
}}

.original-text-result blockquote strong {{
    color: #6e1f1f;
    font-style: normal;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.78rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    margin-right: 0.45rem;
}}

.original-text-result hr {{
    border: none;
    height: 1px;
    margin: 1.8rem 0 1.2rem;
    background: linear-gradient(
        90deg,
        transparent,
        rgba(141, 113, 79, 0.45) 30%,
        rgba(122, 145, 176, 0.30) 70%,
        transparent
    );
}}

/* ===== AUTHOR SIGNATURE (Útmutatás — Ars Poetica aláírás) ===== */
.author-signature {{
    margin: 1.4rem 0 0.4rem auto;
    padding: 0.85rem 1.15rem 0.95rem;
    max-width: 360px;
    text-align: right;
    border-right: 3px solid rgba(141, 113, 79, 0.55);
    background: rgba(255, 252, 246, 0.42);
    border-radius: 12px 4px 4px 12px;
    box-shadow: 0 4px 12px rgba(74, 51, 28, 0.06);
    backdrop-filter: blur(6px);
    -webkit-backdrop-filter: blur(6px);
    font-family: 'Cormorant Garamond', 'Times New Roman', serif;
    line-height: 1.45;
}}

.author-signature .author-name {{
    font-size: 1.18rem;
    font-weight: 600;
    color: #4a3520;
    letter-spacing: 0.01em;
}}

.author-signature .author-role {{
    font-size: 0.97rem;
    font-style: italic;
    color: #6b5238;
    margin-top: 0.1rem;
}}

.author-signature .author-place {{
    font-size: 0.92rem;
    color: #7a6244;
    margin-top: 0.15rem;
}}

.author-signature .author-mail {{
    font-size: 0.92rem;
    margin-top: 0.45rem;
    letter-spacing: 0.01em;
}}

.author-signature .author-mail a {{
    color: #5a7ba0 !important;
    text-decoration: none;
    border-bottom: 1px dotted rgba(90, 123, 160, 0.45);
    transition: border-bottom-color 0.18s ease, color 0.18s ease;
}}

.author-signature .author-mail a:hover {{
    color: #3f5d7e !important;
    border-bottom-color: rgba(63, 93, 126, 0.85);
}}

@media (max-width: 768px) {{
    .author-signature {{
        max-width: 100%;
        margin: 1.2rem 0 0.4rem;
        padding: 0.75rem 1rem 0.85rem;
        border-right: none;
        border-left: 3px solid rgba(141, 113, 79, 0.55);
        border-radius: 4px 12px 12px 4px;
        text-align: left;
    }}
}}

/* ===== API GUIDE BOX (Beállítások — kulcs igénylés) ===== */
.api-guide-box {{
    padding: 26px 32px;
    margin-top: 0.4rem;
}}

.api-guide-box ol {{
    margin: 0.6rem 0 0.4rem;
    padding-left: 1.4rem;
    counter-reset: api-step;
    list-style: none;
}}

.api-guide-box ol li {{
    position: relative;
    padding: 0.55rem 0 0.55rem 0.6rem;
    margin-bottom: 0.25rem;
    line-height: 1.6;
    counter-increment: api-step;
}}

.api-guide-box ol li::before {{
    content: counter(api-step);
    position: absolute;
    left: -1.55rem;
    top: 0.55rem;
    width: 1.55rem;
    height: 1.55rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-family: "Inter", system-ui, sans-serif;
    font-size: 0.78rem;
    font-weight: 700;
    color: #5d4830;
    background:
        linear-gradient(180deg,
            rgba(252, 246, 232, 0.92),
            rgba(228, 211, 178, 0.78));
    border: 1px solid rgba(166, 134, 86, 0.42);
    border-radius: 50%;
    box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.72),
        0 2px 5px rgba(71, 52, 30, 0.14);
}}

.api-guide-box a {{
    color: #6a4a22;
    font-weight: 600;
    text-decoration: none;
    border-bottom: 1px dotted rgba(106, 74, 34, 0.45);
    transition: color 160ms ease, border-color 160ms ease;
}}

.api-guide-box a:hover {{
    color: #8a5a1f;
    border-bottom-color: rgba(138, 90, 31, 0.85);
}}

/* ===== ÉNEKAJÁNLÓ / HYMN CARDS ===== */
.songs-result {{
    padding: 30px 34px;
}}

.songs-result h2 {{
    font-family: "Cormorant Garamond", Georgia, serif !important;
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    color: #3a2c1d !important;
    margin: 1.7rem 0 0.85rem !important;
    padding-bottom: 0.4rem;
    letter-spacing: 0.01em;
    border-bottom: none;
    position: relative;
}}

.songs-result h2::after {{
    content: "";
    display: block;
    width: 78px;
    height: 2px;
    margin-top: 0.45rem;
    background: linear-gradient(
        90deg,
        rgba(141, 113, 79, 0.85),
        rgba(122, 145, 176, 0.55) 65%,
        transparent
    );
    border-radius: 999px;
}}

.songs-result h3 {{
    font-family: "Cormorant Garamond", "Times New Roman", serif !important;
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    line-height: 1.25 !important;
    color: #2a1f12 !important;
    margin: 1.7rem 0 0.7rem !important;
    padding: 0.65rem 0.9rem 0.7rem 1rem;
    border-left: 3px solid rgba(141, 113, 79, 0.55);
    background: linear-gradient(
        90deg,
        rgba(255, 240, 210, 0.34),
        rgba(255, 240, 210, 0.06) 55%,
        rgba(255, 240, 210, 0)
    );
    border-radius: 0 10px 10px 0;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.55);
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.55) inset,
        0 6px 14px rgba(74, 51, 28, 0.06);
    position: relative;
}}

.songs-result h3::before {{
    content: "\\f001";
    font-family: "Font Awesome 6 Free", "Font Awesome 5 Free", "FontAwesome";
    font-weight: 900;
    color: rgba(122, 145, 176, 0.78);
    font-size: 0.78rem;
    margin-right: 0.55rem;
    vertical-align: 0.18em;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.6);
}}

.songs-result h3 em {{
    font-family: "Inter", "Segoe UI", sans-serif !important;
    font-style: normal !important;
    font-size: 0.74rem !important;
    font-weight: 700 !important;
    color: #3d567a !important;
    margin-left: 0.6rem;
    padding: 0.18rem 0.55rem;
    border: 1px solid rgba(122, 145, 176, 0.34);
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.55);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    text-shadow: none;
    vertical-align: 0.18em;
}}

.songs-result p {{
    font-family: "Lora", Georgia, serif;
    font-size: 1.0rem;
    line-height: 1.72;
    color: #34281c;
    margin: 0.35rem 0 0.6rem;
    max-width: 78ch;
}}

.songs-result p strong {{
    display: inline-block;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.74rem;
    font-weight: 700;
    color: #3d567a;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    margin-right: 0.45rem;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.55);
}}

.songs-result hr {{
    border: none;
    height: 1px;
    margin: 1.6rem 0 1.1rem;
    background: linear-gradient(
        90deg,
        transparent,
        rgba(141, 113, 79, 0.40) 30%,
        rgba(122, 145, 176, 0.28) 70%,
        transparent
    );
}}

.songs-result blockquote {{
    margin: 0.7rem 0 1.3rem;
    padding: 0.85rem 1.1rem;
    background: linear-gradient(
        90deg,
        rgba(238, 226, 205, 0.58),
        rgba(238, 226, 205, 0)
    );
    border-left: 3px solid rgba(141, 113, 79, 0.55);
    border-radius: 0 10px 10px 0;
    font-family: "Lora", Georgia, serif;
    font-size: 0.96rem;
    line-height: 1.65;
    color: #4a3826;
    font-style: italic;
}}

/* =========================================================
   ELEMZÉS FOLYAMATJELZŐ — animált progress card
   ========================================================= */

.analysis-progress {{
    margin: 0.4rem 0 1.1rem;
    padding: 18px 22px 20px;
    background:
        linear-gradient(165deg, rgba(255, 253, 248, 0.55), rgba(244, 237, 226, 0.40)),
        radial-gradient(circle at 0% 0%, rgba(255, 255, 255, 0.45), transparent 55%);
    backdrop-filter: blur(28px) saturate(135%);
    -webkit-backdrop-filter: blur(28px) saturate(135%);
    border: 1px solid rgba(216, 199, 177, 0.55);
    border-radius: 16px;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.85) inset,
        0 -1px 0 rgba(118, 95, 70, 0.06) inset,
        0 0 0 1px rgba(255, 224, 178, 0.10),
        0 6px 14px rgba(54, 42, 25, 0.10),
        0 18px 36px rgba(34, 22, 8, 0.18);
    position: relative;
    overflow: hidden;
}}

.analysis-progress.completed {{
    background:
        linear-gradient(165deg, rgba(244, 248, 254, 0.55), rgba(232, 240, 250, 0.40)),
        radial-gradient(circle at 0% 0%, rgba(255, 255, 255, 0.45), transparent 55%);
    border-color: rgba(122, 145, 176, 0.45);
}}

.analysis-progress .progress-eyebrow {{
    display: inline-block;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.66rem;
    font-weight: 700;
    letter-spacing: 0.20em;
    text-transform: uppercase;
    color: #6f7f95;
    margin-bottom: 0.45rem;
    padding-left: 0.55rem;
    border-left: 2px solid rgba(122, 145, 176, 0.55);
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.7);
}}

.analysis-progress .progress-step {{
    font-family: "Cormorant Garamond", Georgia, serif;
    font-size: 1.32rem;
    font-weight: 700;
    color: #2a1f12;
    line-height: 1.22;
    margin: 0 0 0.7rem;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.65);
}}

.analysis-progress.completed .progress-step {{
    color: #1f2c3d;
}}

.analysis-progress .progress-bar {{
    height: 10px;
    background:
        linear-gradient(180deg, rgba(48, 36, 22, 0.12), rgba(48, 36, 22, 0.06));
    border-radius: 999px;
    overflow: hidden;
    position: relative;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.55),
        inset 0 1px 2px rgba(34, 22, 8, 0.18);
}}

.analysis-progress .progress-fill {{
    height: 100%;
    width: 0%;
    border-radius: 999px;
    background: linear-gradient(
        90deg,
        #8f714f 0%,
        #a98865 35%,
        #7a91b1 70%,
        #6f88a8 100%
    );
    box-shadow:
        0 0 0 1px rgba(255, 255, 255, 0.22) inset,
        0 0 14px rgba(122, 145, 176, 0.42),
        0 0 22px rgba(141, 113, 79, 0.30);
    transition: width 0.6s cubic-bezier(0.4, 0.0, 0.2, 1);
    position: relative;
    overflow: hidden;
}}

.analysis-progress .progress-fill::after {{
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(
        90deg,
        transparent,
        rgba(255, 255, 255, 0.55) 50%,
        transparent
    );
    animation: progress-shimmer 1.5s linear infinite;
}}

.analysis-progress.completed .progress-fill {{
    background: linear-gradient(
        90deg,
        #6f88a8 0%,
        #8aa8c8 50%,
        #6f88a8 100%
    );
    box-shadow:
        0 0 0 1px rgba(255, 255, 255, 0.30) inset,
        0 0 18px rgba(122, 145, 176, 0.55);
}}

.analysis-progress.completed .progress-fill::after {{
    animation: none;
    background: linear-gradient(
        90deg,
        transparent,
        rgba(255, 255, 255, 0.30),
        transparent
    );
}}

@keyframes progress-shimmer {{
    from {{ transform: translateX(-100%); }}
    to   {{ transform: translateX(100%); }}
}}

.analysis-progress .progress-meta {{
    margin: 0.55rem 0 0.4rem;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    color: #6b5638;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.55);
}}

.analysis-progress.completed .progress-meta {{
    color: #3d567a;
}}

.analysis-progress .progress-steps {{
    list-style: none;
    padding: 0;
    margin: 0.6rem 0 0;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 0.35rem 0.7rem;
}}

.analysis-progress .progress-steps li {{
    display: flex;
    align-items: center;
    gap: 0.55rem;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.86rem;
    color: #4a3a28;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.55);
}}

.analysis-progress .progress-steps li.pending {{
    color: rgba(74, 58, 40, 0.50);
    font-style: italic;
}}

.analysis-progress .progress-steps li.done {{
    color: #2a1f12;
    font-weight: 600;
}}

.analysis-progress .progress-steps li.current {{
    color: #1f2c3d;
    font-weight: 700;
}}

.analysis-progress .progress-dot {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    font-size: 0.62rem;
    font-weight: 900;
    flex-shrink: 0;
    text-shadow: none;
}}

.analysis-progress .progress-dot.done {{
    background: linear-gradient(140deg, #b5cae0, #8aa8c8);
    color: #1c2a3c;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.65) inset,
        0 0 0 1px rgba(122, 145, 176, 0.42),
        0 0 8px rgba(122, 145, 176, 0.32);
}}

.analysis-progress .progress-dot.current {{
    background: linear-gradient(140deg, #f3d8a8, #d8b27a);
    color: #4a3618;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.65) inset,
        0 0 0 1px rgba(180, 140, 80, 0.45),
        0 0 12px rgba(220, 180, 110, 0.55);
    animation: progress-pulse 1.2s ease-in-out infinite;
}}

.analysis-progress .progress-dot.pending {{
    background: rgba(255, 255, 255, 0.40);
    color: rgba(74, 58, 40, 0.30);
    border: 1px dashed rgba(141, 113, 79, 0.40);
}}

@keyframes progress-pulse {{
    0%, 100% {{
        transform: scale(1);
        box-shadow:
            0 1px 0 rgba(255, 255, 255, 0.65) inset,
            0 0 0 1px rgba(180, 140, 80, 0.45),
            0 0 8px rgba(220, 180, 110, 0.40);
    }}
    50% {{
        transform: scale(1.12);
        box-shadow:
            0 1px 0 rgba(255, 255, 255, 0.65) inset,
            0 0 0 1px rgba(180, 140, 80, 0.55),
            0 0 18px rgba(220, 180, 110, 0.78);
    }}
}}

/* =========================================================
   RESZPONZÍV — TABLET ÉS MOBIL
   =========================================================
   Egy helyen összegyűjtve, hogy bármikor karbantartható legyen.
   3 breakpoint:
     - tablet: max-width 1024px
     - mobil:  max-width 640px
     - kis mobil: max-width 380px
*/

/* Globális biztonsági szabály: hosszú szavak / linkek soha ne tördeljék
   szét a layoutot mobilon */
.main-card,
.result-box,
.basket-box,
.ars-section,
[data-testid="stMarkdownContainer"],
[data-testid="stChatMessage"] {{
    overflow-wrap: break-word;
    word-wrap: break-word;
    word-break: normal;
    hyphens: auto;
}}

/* Képek a tartalomban sose lógjanak túl — fejléc logó kivétel */
[data-testid="stMarkdownContainer"] img:not(.main-logo) {{
    max-width: 100%;
    height: auto;
}}

/* ---------- TABLET (≤1024px) ---------- */
@media (max-width: 1024px) {{
    .block-container {{
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }}

    .header-grid {{
        grid-template-columns: 220px 1fr;
        gap: 1.1rem;
    }}

    .header-logo .main-logo {{
        width: 190px !important;
    }}

    .main-card {{
        padding: 28px 30px !important;
    }}

    .result-box,
    .basket-box {{
        padding: 24px 26px !important;
    }}

    .stTabs [data-baseweb="tab"] {{
        padding: 0.62rem 0.95rem !important;
        font-size: 0.92rem !important;
        margin-right: 6px !important;
        min-height: 2.55rem !important;
    }}

    .ars-section {{
        padding: 1.6rem 1.4rem !important;
    }}
}}

/* ---------- MOBIL (≤640px) ---------- */
@media (max-width: 640px) {{
    .block-container {{
        padding-top: 0.4rem !important;
        padding-bottom: 2rem !important;
        padding-left: 0.7rem !important;
        padding-right: 0.7rem !important;
    }}

    /* Header: a logó kerüljön középre, a szöveg alá */
    .main-card.header-card {{
        padding: 22px 18px !important;
    }}

    .header-grid {{
        grid-template-columns: 1fr !important;
        text-align: center;
        gap: 0.8rem !important;
    }}

    .header-logo {{
        justify-content: center;
    }}

    .header-logo .main-logo {{
        width: 140px !important;
    }}

    .main-title {{
        font-size: clamp(2.1rem, 8vw, 2.8rem) !important;
        line-height: 1 !important;
    }}

    .version-line {{
        font-size: 0.78rem !important;
        letter-spacing: 0.12em !important;
    }}

    .subtitle {{
        font-size: 1.02rem !important;
        line-height: 1.4 !important;
        max-width: 100% !important;
        text-align: center;
    }}

    .header-caption {{
        margin-left: auto;
        margin-right: auto;
        font-size: 0.78rem !important;
        letter-spacing: 0.12em !important;
        padding: 0.18rem 0.55rem !important;
    }}

    /* Kártyák — kompaktabb belső tér */
    .main-card {{
        padding: 20px 18px !important;
        border-radius: 18px !important;
    }}

    .result-box,
    .basket-box {{
        padding: 18px 18px !important;
        border-radius: 16px !important;
        margin-top: 16px !important;
    }}

    /* Tabok — alacsonyabb sor, kisebb padding, kisebb font, de még olvasható */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 4px !important;
        row-gap: 6px !important;
    }}

    .stTabs [data-baseweb="tab"] {{
        padding: 0.5rem 0.7rem !important;
        font-size: 0.84rem !important;
        margin-right: 4px !important;
        min-height: 2.3rem !important;
        border-radius: 11px !important;
        letter-spacing: 0 !important;
    }}

    /* Címsorok mobilon kisebbek */
    h1 {{ font-size: 1.6rem !important; }}
    h2 {{ font-size: 1.35rem !important; line-height: 1.3 !important; }}
    h3 {{ font-size: 1.18rem !important; line-height: 1.3 !important; }}
    h4 {{ font-size: 1.05rem !important; }}

    /* Szövegmezők — KÖTELEZŐ min. 16px font, hogy az iOS Safari NE
       zoomoljon rá automatikusan a fókuszáláskor */
    .stTextInput input,
    .stTextArea textarea,
    .stSelectbox div[data-baseweb="select"] {{
        font-size: 16px !important;
    }}

    /* Gombok — érintési target legalább 44px (Apple HIG) */
    .stButton > button {{
        min-height: 44px !important;
        padding: 0.7rem 1.1rem !important;
        font-size: 0.95rem !important;
    }}

    /* Chat input mobilon */
    [data-testid="stChatInput"] textarea {{
        font-size: 16px !important;
        min-height: 44px !important;
    }}

    /* Lábléc / ars-section mobilon */
    .ars-section {{
        padding: 1.4rem 1.1rem !important;
        margin-top: 1.6rem !important;
    }}

    .ars-poetica {{
        font-size: 1rem !important;
        line-height: 1.5 !important;
    }}

    .ars-stations {{
        grid-template-columns: 1fr !important;
        gap: 1rem !important;
    }}

    .ars-station {{
        padding: 0.4rem 0.6rem !important;
        border-left: 2px solid rgba(141, 113, 79, 0.45);
    }}

    .ars-numeral {{
        font-size: 0.72rem !important;
        letter-spacing: 0.16em !important;
    }}

    .ars-station-title {{
        font-size: 1.18rem !important;
    }}

    .ars-station-text {{
        font-size: 0.92rem !important;
    }}

    /* API guide box — a számozott badge ne lógjon ki */
    .api-guide-box {{
        padding: 18px 18px 18px 18px !important;
    }}

    .api-guide-box ol {{
        padding-left: 1.7rem !important;
    }}

    .api-guide-box ol li::before {{
        left: -1.7rem !important;
        width: 1.4rem !important;
        height: 1.4rem !important;
        font-size: 0.72rem !important;
    }}

    /* Eredeti szöveg / Énekajánló kártyák kompakt */
    .original-text-result,
    .songs-result {{
        padding: 20px 18px !important;
    }}

    /* Chat üzenetek mobilon */
    [data-testid="stChatMessage"] {{
        padding: 12px 14px !important;
    }}

    /* Streamlit alert / info / warning paddingek */
    [data-testid="stAlert"] {{
        padding: 0.7rem 0.9rem !important;
    }}
}}

/* ---------- KIS MOBIL (≤380px) — extra szűkítés ---------- */
@media (max-width: 380px) {{
    .block-container {{
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }}

    .header-logo .main-logo {{
        width: 120px !important;
    }}

    .main-title {{
        font-size: 1.95rem !important;
    }}

    .version-line {{
        margin: 0.25rem auto 0 !important;
    }}

    .subtitle {{
        font-size: 0.94rem !important;
    }}

    .stTabs [data-baseweb="tab"] {{
        padding: 0.45rem 0.55rem !important;
        font-size: 0.78rem !important;
    }}

    /* Sidebar-szerű full-width megjelenítés a kicsi képernyőn */
    .stTextInput input,
    .stTextArea textarea {{
        font-size: 16px !important;
        padding: 0.6rem 0.7rem !important;
    }}
}}

</style>
""", unsafe_allow_html=True)


# =========================================================
# KÖZÖS ALAP PROMPT
# =========================================================

BASE_SYSTEM_PROMPT = """
Te a TEXTUS homiletikai műhely szakértő teológiai modulja vagy.
Feladatod a református lelkipásztor tudományos igényű exegetikai és homiletikai
munkájának támogatása.

Gondolkodásodat a biblikus alapvetés, a református hitvallásos érzékenység
(Heidelbergi Káté, II. Helvét Hitvallás) és az evangéliumi fókusz határozza meg.

Stílus és attitűd:
- Kerüld a közhelyeket, a moralizálást és a felszínes „chatbot-stílust".
- Tekintsd a textust Isten élő igéjének, ne pusztán szövegnek.
- Ne kész prédikációt írj, hanem tárd fel a szöveg mélységeit, feszültségeit
  és krisztológiai összefüggéseit.
- Ne helyettesítsd a lelkipásztor saját teológiai és lelki felelősségét —
  inkább segíts kérdéseket, irányokat, összefüggéseket és szerkezeti
  lehetőségeket feltárni.
- Ne írj túlzóan kegyes vagy pátoszos hangon.

Tartalmi elvárások:
- biblikusan megalapozott,
- exegetikailag pontos,
- teológiailag árnyalt,
- homiletikailag használható,
- történetileg érzékeny,
- világosan strukturált,
- tömör és gyakorlatias, de nem hiányos — ne hagyj ki fontos információt,
  ugyanakkor kerüld a túlmagyarázást, a tankönyvszerű körítést és a felesleges ismétlést.

Pontosság és integritás:
- NE találj ki nem létező idézeteket, hamis forrásokat, bizonytalan
  történelmi adatokat vagy mesterségesen hangzó prédikációs kliséket.
- Ha egy értelmezés vitatott vagy bizonytalan, ezt explicit módon jelezd
  („Vitatott:", „Bizonytalan:" stb.).

Formázási követelmények — KÖTELEZŐ:
- A választ STRUKTURÁLT MARKDOWN formában add.
- Használj megfelelő szintű címsorokat (`##`, `###`).
- A teológiai szakkifejezéseket, kulcs-fogalmakat és kulcsszavakat
  emeld ki **félkövéren**.
- Ahol indokolt, használj felsorolásokat, idézet-blokkokat (`>`)
  és vízszintes elválasztókat (`---`).
- A válasz olvasható, áttekinthető és prédikációs munkában azonnal
  használható legyen.

══════════════════════════════════════════════════════════════════
SZIGORÚAN TILOS NYITÓ ÉS ZÁRÓ FORDULATOK — KÖTELEZŐ BETARTANI
══════════════════════════════════════════════════════════════════

A válaszod AZONNAL a szakmai tartalommal kezdődjön — az ELSŐ KARAKTER egy
Markdown címsor (`#`/`##`/`###`) vagy közvetlenül az első tartalmas
exegetikai/teológiai mondat legyen.

SOHA, SEMMILYEN KÖRÜLMÉNYEK KÖZÖTT NE használj:

❌ Üdvözlést, megszólítást:
   - „Üdvözlöm, Lelkipásztor Testvérem!"
   - „Kedves Lelkipásztor!"
   - „Tisztelt Felhasználó!"
   - „Hello", „Szia", „Szervusz", „Jó napot"
   - „Drága Testvérem", „Kedves Olvasó"

❌ Öndefiniáló / önbemutatkozó bevezetést:
   - „A TEXTUS homiletikai műhely szakértő teológiai moduljaként…"
   - „Mint a TEXTUS modulja, örömmel segítek…"
   - „A teológiai segédletként…"
   - „AI-ként", „Modellként", „Asszisztensként"

❌ Értékelő / udvariaskodó nyitó köröket:
   - „Örömmel segítek…", „Szívesen elemzem…"
   - „Nagyszerű kérdés!", „Kiváló választás!"
   - „Természetesen…", „Persze…", „Hogyne…"
   - „Folytatva a bibliai humor gazdag tárházának feltárását…"

❌ Bevezető meta-mondatokat:
   - „Itt van az elemzés…", „Íme az elemzés…"
   - „Az alábbiakban bemutatom…"
   - „A következőkben kifejtem…"
   - „Ebben a válaszban…"

❌ Záró udvariaskodó mondatokat:
   - „Reményeim szerint hasznos volt…"
   - „Bízom benne, hogy segítettem…"
   - „Bármikor szólj, ha…"
   - „Ha bármi kérdésed van, fordulj hozzám bizalommal…"
   - „Áldás kíséri a szolgálatodat" típusú lezáró áldások.

✅ HELYETTE: A válasz ELSŐ karaktere maga a szakmai tartalom (címsor vagy
   exegetikai mondat), az UTOLSÓ karaktere pedig az utolsó releváns
   szakmai gondolat — semmiféle „kabát" se elöl, se hátul.

Beszélj úgy, mint egy profi teológus kolléga, aki egyenesen a tárgyra tér.
Tárgyilagos, lényegre törő, sallangmentes — egy hangsúlyos és művelt
tudományos műhely hangja, nem egy chatbot udvariassága.

Válaszolj magyarul, természetes, lelkipásztori munkában használható,
művelt és igényes nyelven.
"""


ORIGINAL_TEXT_BASE_PROMPT = """
Légy alapos, teológiai és nyelvészeti érzékenységgel dolgozó exegéta.
Segíts a megadott bibliai szakasz eredeti nyelvű tanulmányozásában úgy,
hogy az közvetlenül támogassa az ige mélyebb megértését és az üzenet
megfogalmazását.

Ne készíts teljes kommentárt. Ne elemezz minden szót. Válassz ki néhány
valóban fontos eredeti kifejezést, motívumot vagy jelentésréteget, amelyek
érdemben segítik a textus megértését.

Elsősorban azokra a héber vagy görög kifejezésekre figyelj, amelyek:
- több jelentésréteget hordoznak,
- a magyar fordításban könnyen elsimulnak,
- teológiailag vagy homiletikailag fontosak,
- belső feszültséget, kontrasztot vagy hangsúlyt adnak a szakasznak.

Minden kiemelt kifejezésnél világosan mutasd meg:
- mi az eredeti szó vagy kifejezés (ha biztosan azonosítható),
- mit jelent alapvetően,
- milyen árnyalatokat vagy többletjelentést hordozhat,
- miért fontos ez a textus üzenete szempontjából,
- hogyan segítheti az igehirdetés fő gondolatának megfogalmazását.

Ha valóban releváns, említs néhány bibliai párhuzamot is, ahol ugyanaz a szó,
motívum vagy gondolat megjelenik. Csak akkor hozz párhuzamot, ha az tényleg
segít a mostani szakasz megértésében. Ha egy szó máshol eltérő árnyalattal
szerepel, ezt röviden magyarázd el.

A válasz legyen:
- világos és jól tagolt,
- lényegre törő,
- nem túl hosszú,
- de szakmailag elég mély egy alapos prédikációs készüléshez.

Javasolt forma:

### [eredeti szó / kifejezés] — [rövid magyar jelzés]
**Alapjelentés:** ...
**Miért fontos itt:** ...
**Mélyebb árnyalat:** ...
**Bibliai párhuzam (ha releváns):** ...
**Igehirdetési hozam:** ...

Ha bizonytalan vagy egy eredeti alakban, etimológiában vagy párhuzamban,
jelöld világosan: „Bizonytalan:” vagy „Vitatott:”. Ne találj ki nem létező
eredeti nyelvi adatot, bibliai párhuzamot vagy idézetet.
"""


SONGS_BASE_PROMPT = """
Te egy református liturgiai és énekirodalmi műhelyvezető vagy,
aki kifejezetten lelkipásztori prédikációra készülést támogat.

Szakmai vízió:
Válogass énekeket a **magyarországi és erdélyi református énekeskönyvek
kincstárából liturgiai ívben** (kezdőének → igehirdetés előtti ének →
főének → záróének). Minden ajánláshoz fűzz **teológiailag megalapozott
indoklást**, amely megmutatja, miért éppen ez az ének felel meg a textusnak,
az alkalomnak és a prédikáció hangsúlyának.

A célod: a megadott bibliai szakasz, alkalom és prédikációs hangsúly
alapján liturgiailag és teológiailag illeszkedő református énekeket ajánlani
az istentisztelet ívének megfelelően.

Nagyon fontos forrásszemlélet:
- Elsősorban a magyarországi és erdélyi (illetve határon túli magyar)
  református énekeskönyvek énekeiből válogass.
- Vedd figyelembe a Magyarországi Református Egyház Énekeskönyvét (1948),
  az új Református Énekeskönyvet (2021), valamint az Erdélyi Református
  Énekeskönyvet és a Kárpát-medencei magyar református hagyományt.
- Csak valódi, valóban használt református énekeket javasolj.
- Soha NE találj ki nem létező énekszámot, kezdősort vagy szerzőt.
- Ha bizonytalan vagy egy énekszámban, kezdősorban vagy abban,
  hogy egy adott ének valóban szerepel-e az énekeskönyvben,
  ezt világosan jelezd („Bizonytalan énekszám", „Ellenőrizendő" stb.),
  és inkább adj alternatívát is.

Liturgiai szemlélet:
- Az ajánlások az istentisztelet ívét kövessék
  (kezdő → prédikáció előtti → fő → záró ének).
- Az énekek illeszkedjenek a református istentiszteleti rend szelleméhez,
  a textushoz, az ünnepkörhöz, a teológiai hangsúlyhoz és az alkalomhoz.
- A főének álljon a legszorosabb kapcsolatban a textussal és a prédikáció
  központi gondolatával.
- Az ajánlás legyen pasztorális, mértéktartó, igényes — ne színpadi,
  ne hatásvadász.

Minden ajánlás tartalmazza:
- énekszám (ha biztos vagy benne, jelezd a forrást is, pl.
  „RÉ 2021: 234." vagy „RÉ 1948: 134."),
- az ének címe vagy kezdősora,
- 1–2 mondatos lelkipásztori indoklás,
- külön mondat arról, hogy konkrétan hogyan kapcsolódik
  az igeszakaszhoz vagy a prédikáció hangsúlyához.

Soha ne adj egyszerű listát; minden énekajánlás legyen
strukturált, indokolt, prédikációhoz használható.

A válasz végén — opcionálisan — adhatsz egy nagyon rövid
„Liturgiai megjegyzés" szakaszt, ahol jelzed, ha valami különös
liturgiai szempontot fontosnak tartasz (pl. úrvacsorai szakasz,
ünnepkör, gyászalkalom egyedi hangsúlya).

Soha ne pótold ki bizonytalan adatokat találgatott számokkal vagy címekkel.
Inkább jelezd a bizonytalanságot, és adj reális alternatívát.

Válaszolj magyarul, természetes, lelkipásztori-liturgiai nyelven.
"""


# =========================================================
# SZEKCIÓ PROMPTOK (újragenerálható szekciókhoz is)
# =========================================================

SECTION_PROMPTS = {
    "overview": """{alap}

# IGEHELY — A SZÖVEG BELSŐ DINAMIKÁJA

Szakmai vízió:
Térképezd fel a szöveg belső dinamikáját — hol találhatók benne a teológiai
hangsúlyeltolódások, hol feszülnek belső ellentétek, és mi az az alapvető
„mozgás", amely a kezdetétől a végéig vezeti az olvasót. Mutasd be a szakasz
**irodalmi és teológiai architektúráját**, rávilágítva azokra a pontokra,
ahol az Ige **provokál, vigasztal vagy kérdőre von**.

A válasz strukturáltan, az alábbi szakaszokra bontva:

## Fő üzenet
1–2 mondatos magvas tételmondat — a szöveg „idegszála".

## Közvetlen bibliai kontextus
Mi előzi meg, mi követi, hol helyezkedik el a kanonikus íven belül.

## Irodalmi és teológiai architektúra
- A szakasz szerkezete (kompozíció, ismétlés, retorikai fordulatok).
- Belső mozgás: honnan-hová vezet a szöveg.
- Belső feszültségek és hangsúlyeltolódások.

## Teológiai hangsúly
A textus központi teológiai magja — Isten-kép, emberkép, kegyelem, hit, ítélet stb.

## Prédikációs irányok
3–5 lehetséges kibontási út, mindegyikhez egy mondatos indoklás.

## Figyelmeztetések
Mire kell vigyázni az értelmezésnél (szövegrész félreérthető pontjai, gyakori torzítások).

Ne írj teljes prédikációt — szakmai feltáró elemzést készíts.
""",
    "exegesis": """{alap}

# Exegézis — Szövegelemzés

Szakmai vízió:
Készíts alapos exegetikai elemzést. Határozd meg a szakasz **pontos
szerkezetét** és **irodalmi műfaját**. Elemezd a kontextuális összefüggéseket:
mi előzi meg, mi követi, és hogyan illeszkedik ez a rész **a kánon egészébe**.
Világíts rá a **biztos pontokra** és a **vitatott értelmezési kérdésekre** is.

Strukturáld a választ így:

## Műfaj és szerkezet
A szakasz műfaji besorolása + belső szerkezete (versek/szakaszok, kompozíciós elemek).

## Kontextus
- Közvetlen szövegkörnyezet (mi előtte, mi utána).
- Tágabb kontextus a könyv egészében.
- Helye a kánoni íven belül (Ó- vagy Újszövetség, hagyományegység).

## Kulcsszavak és kulcskifejezések
3–6 valóban hangsúlyos kifejezés rövid exegetikai magyarázattal.

## Nyelvtani és szerkezeti megfigyelések
Releváns igealakok, mondatszerkezet, retorikai eszközök.

## Párhuzamos bibliai helyek
Csak biztos, ellenőrizhető párhuzamok rövid magyarázattal.

## Értelmezési kérdések
- **Biztos:** amit a tudomány konszenzusosan állít.
- **Valószínű:** ahol több értelmezés is megengedett, de van súlypont.
- **Vitatott:** ahol komoly értelmezésbeli feszültségek vannak.

## Prédikációs haszon
Az exegézis fő gyümölcse — mit ad ez a homiletikai munkához.

Ne prédikációt írj, hanem szakmai háttérelemzést.
""",
    "history": """{alap}

# KORTÖRTÉNET — A TEXTUS ÉLETVILÁGA

Szakmai vízió:
Helyezd el a textust a keletkezésének **valóságos történeti és kulturális
terébe**. Keress konkrét **régészeti, társadalmi vagy vallástörténeti adatokat**.
Hogyan értették ezt az üzenetet az **első hallgatók** a saját **politikai,
gazdasági vagy vallási szorongásaik** közepette?

Strukturáld a választ így:

## Történelmi háttér
A szöveg keletkezésének időszaka, az adott periódus jellemzői.

## Politikai és vallási környezet
Uralkodók, hatalmi viszonyok, vallási intézmények, kortárs irányzatok.

## Társadalmi és gazdasági viszonyok
Társadalmi rétegek, hétköznapok, gazdasági realitások — ami nélkül a szöveget nem értjük.

## Földrajzi és régészeti háttér
Helyszín, topográfia, releváns régészeti felfedezések — csak biztos adatok.

## Korabeli szokások
A textus hátterében álló kulturális gyakorlatok (étkezés, házasság, jog, vallási rítusok stb.).

## Az első hallgatók szorongásai
**Hogyan hangzott ez akkor?** — a konkrét történelmi terhek között.

## Homiletikai haszon
- Mit érdemes ebből a prédikációban használni.
- Mit **nem** érdemes túlhangsúlyozni (a kontextus nem helyettesíti az igét).

Külön és világosan jelezd, mi **biztos**, mi **valószínű**, és mi **vitatott**.
""",
    "theology": """{alap}

# TEOLÓGIA — REFORMÁTUS ÉRZÉKENYSÉGGEL

Szakmai vízió:
Bontsd ki a textusban rejlő teológiai igazságokat a **református gondolkodásmód**
mentén. Vizsgáld az **Istenképet**, az **antropológiát** és a **szoteriológiát**.
Keresd meg a szöveg **krisztológiai fókuszát**, és helyezd el az üzenetet
a **református hitvallások** (Heidelbergi Káté, II. Helvét Hitvallás)
összefüggésrendszerében.

Strukturáld a választ így:

## Istenkép
A textus által kirajzolódó Isten-arculat (szent, irgalmas, igazságos, szövetségkötő stb.).

## Antropológia
Mit mond a szöveg az emberről — bűn, méltóság, hivatás, közösség.

## Szoteriológia
Hogyan szól ez Isten üdvözítő munkájáról.

## Krisztológiai fókusz
**A szöveg hogyan mutat Krisztusra**, akár közvetlenül, akár tipológiailag, akár ígéretként.

## Szövetségteológiai összefüggések
A szövetség(ek) ívében hol áll ez a textus.

## Református hitvallásos kapcsolódás
Konkrét utalás a Heidelbergi Káté és a II. Helvét Hitvallás vonatkozó pontjaira
(csak ha ténylegesen megalapozott — ne találj ki kérdés-számot).

## Kerülendő torzítások
Milyen teológiai félreértésekre, eltolódásokra hajlamosít a szöveg.

A cél a **teológiai tisztánlátás** — nem közhelyek, hanem mély, prédikálható megértés.
""",
    "illustrations": """{alap}

# ILLUSZTRÁCIÓK — FELTÖRIK A TEXTUS KÉRGÉT

Szakmai vízió:
Generálj olyan **szellemi képeket és analógiákat**, amelyek **feltörik
a textus kemény kérgeit**. Keress a **kortárs kultúrából, a tudományból
vagy a művészetből** olyan metaforákat, amelyek a textus **belső logikáját**
teszik átélhetővé. Olyan képeket adj, amelyek **intellektuálisan izgalmasak
és lelkileg megrendítőek**.

Strukturáld a választ így:

## Hétköznapi képek
2–3 mai, megélt élethelyzet, amely a textus központi mozgását leképezi.

## Kortárs kulturális analógiák
Kortárs irodalmi, filmes, zenei vagy közéleti analógiák — csak valós, nem találgatott.
Ha egy idézet vagy hivatkozás bizonytalan, jelöld: *(bizonytalan eredet)*.

## Tudomány és művészet
Olyan **természettudományos, művészettörténeti vagy filozófiai kép**, amely
intellektuálisan is provokál és új szemszöget nyit a szövegre.

## Történeti vagy bibliai párhuzam
Egy másik bibliai vagy egyháztörténeti történet, amely a textus üzenetét élővé teszi.

## Egy bevezető kép
**Egy konkrét, készre formált bevezető kép** — amelyet a lelkipásztor a prédikáció
első mondataiban használhat.

Soha NE használj hamis idézeteket, ellenőrizetlen legendákat vagy kitalált
egyházatya-mondásokat. Ha bizonytalan vagy az eredetben, jelezd.
""",
    "actualization": """{alap}

# AKTUALIZÁLÁS — A TEXTUS ÉS A MAI VILÁG (GOOGLE SEARCH AKTÍV)

Szakmai vízió:
**HASZNÁLD A GOOGLE SEARCH ESZKÖZT.** Keress rá az **elmúlt 24–48 óra**
legfontosabb **magyarországi és nemzetközi híreire** mértékadó portálokon
(pl. Telex, HVG, Index, MTI, BBC, Reuters, Associated Press).

Strukturáld a választ pontosan így:

## Aktuális horizont
3–4 friss, valós **headline vagy trend**, amely a mai közhangulatot meghatározza.
Minden tételhez: **rövid leíró cím + 1–2 mondatos kontextus**.
Ahol lehet, jelöld a forrást és (ha ismert) az időpontot.

## Teológiai híd
Építs **szellemi kapcsolatot** a textus és a fenti hírek mögött meghúzódó
**emberi tapasztalatok** között. Nem felszínes „aktualizálás", hanem mélyebb
megfeleltetés: a textus milyen **emberi alapkérdést** érint, ami a hírekben
is felszínre kerül (félelem, remény, igazságszolgáltatás, identitás, halál,
megbocsátás, közösség, hatalom stb.).

## Lelki relevancia
Hogyan szólít meg ez az Ige egy **ma reggeli híreket olvasó embert**?
Milyen **konkrét lelki válasz**, irány, vigasz vagy hívás származik a textusból
ebbe az aktuális élethelyzetbe?

## Prédikációs alkalmazás
1–2 konkrét, prédikációba beépíthető irány — hogyan szólalhat meg ez
a kapcsolat a vasárnapi igehirdetésben **tisztelettel és nem politikai éllel**.

Szigorú szabályok:
- **Kerüld a pártpolitikát** és a politikai állásfoglalást.
- A híreket **mint az emberi állapot tüneteit** vizsgáld, nem mint politikai eseményeket.
- Ne erőltesd rá a textusra a mai kérdéseket — engedd, hogy a szöveg szólaljon meg.
- Ha egy hír forrása vagy időpontja bizonytalan, jelezd.
""",
}

SECTION_LABELS = {
    "overview": "Áttekintés",
    "exegesis": "Exegézis",
    "history": "Kortörténet",
    "theology": "Teológia",
    "illustrations": "Illusztrációk",
    "actualization": "Aktualizálás",
}


def _sync_inputs_to_last():
    """Az élő input mezők értékét a `last_*` session kulcsokba menti.

    Így minden tab generálás-gombja ugyanazt a forrást használja, és a
    workspace-mentésnél is a legfrissebb állapot kerül exportra.
    """
    igehely = (st.session_state.get("igehely_input") or "").strip()
    alkalom = st.session_state.get("alkalom_input") or ""
    stilus = st.session_state.get("stilus_input") or ""
    sajat = st.session_state.get("sajat_input") or ""

    if igehely:
        st.session_state["last_igehely"] = igehely
        # verse_history frissítés (utolsó 10, duplikátum nélkül)
        _vh = [v for v in st.session_state.get("verse_history", []) if v != igehely]
        _vh.insert(0, igehely)
        st.session_state["verse_history"] = _vh[:10]

    if alkalom:
        st.session_state["last_alkalom"] = alkalom
    if stilus:
        st.session_state["last_stilus"] = stilus
    st.session_state["last_sajat"] = sajat


def build_alap_from_state():
    """A `last_…` session-mezőkből építi vissza az elemzés kontextusát."""
    return f"""Igehely: {st.session_state.get('last_igehely', '')}
Alkalom: {st.session_state.get('last_alkalom', '')}
Homiletikai stílus: {st.session_state.get('last_stilus', '')}
Saját megjegyzés: {st.session_state.get('last_sajat') or 'Nincs külön megjegyzés.'}
"""


# =========================================================
# EREDETI SZÖVEG ÉS ÉNEKAJÁNLÓ — PROMPT ÉPÍTŐK
# =========================================================
# Külön függvénybe szervezve, hogy a "Teljes elemzés indítása" gomb
# is automatikusan tudja generálni ezeket az igehely megadásakor.

def build_original_text_prompt(igehely: str) -> str:
    """Az „Eredeti szöveg" fül teljes promptja. Csak az igehely kell
    bemenetként — ugyanaz a sablon, mint a tab saját gombja mögött."""
    return f"""
{ORIGINAL_TEXT_BASE_PROMPT}

==================================================
EREDETI NYELVI MŰHELY — FELADAT
==================================================

Igeszakasz: {igehely}

Készíts eredeti nyelvű elemzést ehhez a textushoz a fenti mesterprompt
szerkezete szerint.

Ha a szakasz eredeti nyelvi kulcsszavai biztonsággal azonosíthatók, építsd be
őket a kapcsolati hálóba. Ha az eredeti alakban bizonytalan vagy, ne találgass:
inkább jelezd a bizonytalanságot, és dolgozz a textus biztos motívumaival,
ismétlődéseivel, belső feszültségeivel és homiletikai lehetőségeivel.
"""


def _looks_incomplete_response(text: str) -> bool:
    """Óvatos heurisztika: csak láthatóan félbeszakadt választ jelölünk rövidítettnek."""
    cleaned = _strip_chatty_intro(text or "").strip()
    if not cleaned:
        return False

    # Markdown kerítések / idézőjelek gyakori félbeszakadás-jelei.
    if cleaned.count("```") % 2 == 1:
        return True
    if cleaned.endswith(("-", "–", "—", ",", ";", ":", "(", "[", "{", "/")):
        return True

    last_nonempty = ""
    for line in reversed(cleaned.splitlines()):
        if line.strip():
            last_nonempty = line.strip()
            break
    if not last_nonempty:
        return False

    if re.match(r"^[-*+]\s*$", last_nonempty) or re.match(r"^\d+\.\s*$", last_nonempty):
        return True

    # Ha a legutolsó sor természetes záró írásjel nélkül áll meg, az gyanús.
    return not re.search(r'[.!?…)"”\]\}]$', last_nonempty)


def build_songs_prompt(
    igehely: str,
    alkalom: str,
    enekeskonyv: str = "Vegyesen — magyar református hagyomány",
    hangsuly: str = "",
) -> str:
    """Az „Énekajánló" fül teljes promptja. Az igehely + alkalom +
    énekeskönyv + (opcionális) hangsúly bemenetekre épül."""
    hangsuly_block = (
        f"Prédikációs / teológiai hangsúly:\n{hangsuly.strip()}\n"
        if hangsuly and hangsuly.strip()
        else "Prédikációs / teológiai hangsúly: nincs külön megadva — az igeszakasz fő üzenete vezessen.\n"
    )
    return f"""
{SONGS_BASE_PROMPT}

==================================================
ÉNEKAJÁNLÓ — FELADAT
==================================================

Igeszakasz: {igehely}
Alkalom: {alkalom}
Elsődleges énekeskönyv: {enekeskonyv}
{hangsuly_block}

Ajánlj négy éneket az alábbi liturgiai ív szerint,
pontosan ebben a sorrendben és pontosan ebben a markdown szerkezetben
(NE térj el a szerkezettől, hogy a felület helyesen tudja megjeleníteni):

### 1. Kezdőének — *Énekszám / forrás*
**Cím / kezdősor:** az ének címe vagy első sora.
**Indoklás:** 1–2 mondat arról, miért illik az alkalomhoz és az ünnepkörhöz.
**Kapcsolat az igével:** 1 mondat arról, hogyan készíti elő az igeszakasz hallgatását.

### 2. Prédikáció előtti ének — *Énekszám / forrás*
**Cím / kezdősor:** az ének címe vagy első sora.
**Indoklás:** 1–2 mondat a textushoz vezető lelki hangoltságról.
**Kapcsolat az igével:** 1 mondat a textus kulcsmotívumához fűződő kapcsolatról.

### 3. Főének — *Énekszám / forrás*
**Cím / kezdősor:** az ének címe vagy első sora.
**Indoklás:** 1–2 mondat arról, miért ez áll legszorosabb kapcsolatban a textussal és a prédikáció hangsúlyával.
**Kapcsolat az igével:** 1–2 mondat a központi gondolat és az ének közötti kifejtett kapcsolatról.

### 4. Záróének — *Énekszám / forrás*
**Cím / kezdősor:** az ének címe vagy első sora.
**Indoklás:** 1–2 mondat a gyülekezet kibocsátásáról, válaszáról.
**Kapcsolat az igével:** 1 mondat arról, hogyan summázza vagy küldi tovább a textus üzenetét.

---

## Liturgiai megjegyzés
2–4 mondat. Csak akkor írd ki, ha valami különös liturgiai szempont
(ünnepkör, úrvacsora, gyász, ifjúsági istentisztelet stb.) miatt
fontos megjegyzést tenni. Ha nem, hagyd ki ezt a részt.

Az „Énekszám / forrás" mezőben mindig jelezd a forrást:
pl. „RÉ 2021: 234.", „RÉ 1948: 134.", „Erdélyi RÉ: …".
Ha bizonytalan vagy az énekszámban vagy abban, hogy az ének valóban szerepel
az énekeskönyvben, írd oda zárójelben: „(bizonytalan szám — ellenőrizendő)",
és adj alternatív, biztosan létező énekjavaslatot is.

Soha ne találj ki nem létező éneket vagy énekszámot.
"""


SECTIONS_WITH_GOOGLE_SEARCH = {"actualization"}


def generate_section(key: str) -> bool:
    """Egy adott szekciót lefuttat (első generálás VAGY újrageneráláshoz).

    Olvassa az élő input mezőket (igehely_input stb.), szinkronizálja
    `last_*`-okba, majd indít EGYETLEN Gemini hívást. Visszatérési érték:
      - True   → eredmény bekerült a `st.session_state[key]`-be
      - False  → blokkoló validáció (pl. nincs igehely vagy API kulcs)
    """
    _sync_inputs_to_last()

    if not _resolve_api_key().strip():
        st.warning("Először add meg az API kulcsot a Beállítások fülön.")
        return False
    if not st.session_state.get("last_igehely"):
        st.warning("Add meg az igeszakaszt az „Igehely” fülön, mielőtt itt generálsz.")
        return False

    label = SECTION_LABELS.get(key, key)
    use_search = key in SECTIONS_WITH_GOOGLE_SEARCH
    with st.spinner(f"{label} készítése…"):
        prompt = SECTION_PROMPTS[key].format(alap=build_alap_from_state())
        st.session_state[key] = generate_text(
            prompt,
            enable_google_search=use_search,
            tab_label=label,
        )
    return True


regenerate_section = generate_section


# =========================================================
# SECTION TAB RENDERER — DRY, TABONKÉNTI GENERÁLÁS
# =========================================================

def render_section_tab(
    key: str,
    header: str,
    basket_label: str,
    chat_title: str = None,
    empty_msg: str = None,
    extra_box_class: str = "",
    action_label: str = None,
    regen_label: str = None,
):
    """Egységes szekció-tab renderelő.

    - Saját **Generálás** gomb (futás közben tiltott, spinner aktív).
    - Csak gombnyomásra fut Gemini hívás, page-load alatt SOHA.
    - Az eredmény külön `st.session_state[key]`-ben él, rerun nem dobja.
    - Megjeleníti a finomítás-chatet és a vázlatkosár-jegyzetet.

    Paraméterek:
      - `action_label`: a gomb felirata első generáláskor. Ha nincs megadva,
        az alapértelmezett `"{header} generálása"` lesz.
      - `regen_label`: a gomb felirata újrageneráláskor. Ha nincs megadva,
        a `regen_label = "Frissítés — " + action_label` automatikus.
    """
    st.header(header)

    has_result = bool(st.session_state.get(key))
    running_flag = f"_{key}_running"
    is_running = bool(st.session_state.get(running_flag))

    _primary = action_label or f"{header} generálása"
    _regen = regen_label or (f"Frissítés — {action_label}" if action_label else f"{header} újragenerálása")
    btn_label = _regen if has_result else _primary
    btn_type = "secondary" if has_result else "primary"

    if st.button(
        btn_label,
        type=btn_type,
        key=f"{key}_generate_btn",
        disabled=is_running,
    ):
        st.session_state[running_flag] = True
        try:
            generate_section(key)
        finally:
            st.session_state[running_flag] = False
        st.rerun()

    if has_result:
        box_classes = f"result-box {extra_box_class}".strip()
        st.markdown(f'<div class="{box_classes}">', unsafe_allow_html=True)
        st.markdown(st.session_state[key])
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info(empty_msg or "Még nincs tartalom — kattints a generálás gombra.")

    refinement_chat(chat_title or header, key, f"{key}_chat")

    note_key = f"{key}_note"
    add_btn_key = f"{key}_add"
    _maybe_clear_note(note_key)
    note = st.text_area("Mit szeretnél ebből megtartani a vázlathoz?", key=note_key)

    if st.button("Hozzáadás a vázlatkosárhoz", key=add_btn_key):
        if note.strip():
            st.session_state["basket"].append((basket_label, note.strip()))
            _request_clear_note(note_key)
            st.success("Hozzáadva.")
            st.rerun()


# =========================================================
# SAFE NOTE-CLEAR PATTERN
# =========================================================
#
# Streamlit nem engedi, hogy egy widget value-ját (pl. text_area) annak
# példányosítása UTÁN módosítsuk a session_state-en keresztül. Ezért
# bevezetünk egy `<key>_clear_pending` flag pattern-t: a kosárhoz adáskor
# csak állítjuk a flag-et és rerunolunk; a következő render-ben, MÉG A
# WIDGET LÉTREHOZÁSA ELŐTT, a flag alapján töröljük az értéket.

def _maybe_clear_note(note_key: str) -> None:
    """A widget példányosítása ELŐTT törli a megadott note mezőt,
    ha van rá pending törlési kérelem."""
    flag_key = f"{note_key}_clear_pending"
    if st.session_state.get(flag_key):
        st.session_state[note_key] = ""
        st.session_state[flag_key] = False


def _request_clear_note(note_key: str) -> None:
    """A kosárhoz-adás után: NE töröljük közvetlenül a value-t, csak
    állítsuk a flag-et — a következő rerun majd biztonságosan törli."""
    st.session_state[f"{note_key}_clear_pending"] = True


# =========================================================
# WORKSPACE MENTÉS / BETÖLTÉS
# =========================================================

def serialize_workspace():
    payload = build_workspace_payload(version=APP_VERSION, state=st.session_state)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def deserialize_workspace(raw_bytes):
    try:
        text = raw_bytes.decode("utf-8") if isinstance(raw_bytes, bytes) else raw_bytes
        obj = json.loads(text)
    except Exception as e:
        return False, f"A fájl nem olvasható JSON: {e}"
    if not isinstance(obj, dict) or obj.get("_app") not in ("Textus", "Emmaus"):
        return False, "Ez nem TEXTUS munkamenet-fájl."
    for k in WORKSPACE_KEYS:
        if k in obj:
            st.session_state[k] = obj[k]
    return True, obj.get("_saved_at", "ismeretlen időpont")


def _is_logged_in() -> bool:
    """Biztonságos login-check: `[auth]` nélkül az `is_logged_in` attribútum nem létezik.

    Szándékosan NEM használjuk a `st.user.is_logged_in` attribútum-elérést
    a hívó oldalon — csak ezt a wrappert, hogy Cloud secrets nélkül se omoljon az app.
    """
    try:
        user = st.user
    except Exception:
        return False
    # Dict-szerű elérés: hiányzó kulcsnál KeyError/AttributeError → vendég
    try:
        if hasattr(user, "get"):
            val = user.get("is_logged_in", False)
            return bool(val)
    except Exception:
        pass
    try:
        return bool(user["is_logged_in"])
    except Exception:
        return False


def _auth_secrets_configured() -> bool:
    """Van-e használható `[auth]` blokk a Streamlit secrets-ben."""
    try:
        auth = st.secrets.get("auth", None)
        if not auth:
            return False
        # TOML tábla / dict-szerű
        client_id = ""
        try:
            client_id = str(auth.get("client_id", "") or "")
        except Exception:
            client_id = str(getattr(auth, "client_id", "") or "")
        return bool(client_id.strip())
    except Exception:
        return False


def _owner_sub() -> str | None:
    """Bejelentkezett felhasználó azonosítója: kizárólag `st.user["sub"]`."""
    if not _is_logged_in():
        return None
    try:
        sub = (st.user["sub"] or "").strip()
    except Exception:
        return None
    return sub or None


def _queue_project_widget_sync_from_state() -> None:
    """Widget-kulcsok frissítését a következő futás elejére ütemezi.

    A Beállítások fülön a megnyitás után a tabok widgetjei már létezhetnek
    ugyanabban a futásban — közvetlen írás Streamlit hibát okozna.
    """
    st.session_state["_pending_project_widget_sync"] = {
        "igehely_input": st.session_state.get("last_igehely", "") or "",
        "alkalom_input": st.session_state.get("last_alkalom", "") or "",
        "stilus_input": st.session_state.get("last_stilus", "") or "",
        "sajat_input": st.session_state.get("last_sajat", "") or "",
        "_outline_draft_editor": st.session_state.get("outline_draft", "") or "",
        "_outline_answers_editor": (
            st.session_state.get("outline_workshop_answers", "") or ""
        ),
        "_outline_reworked_editor": (
            st.session_state.get("outline_reworked_draft", "") or ""
        ),
    }
    st.session_state.pop("_pending_outline_draft_editor", None)


def _apply_pending_project_widget_sync() -> None:
    """Pending widget-értékek alkalmazása — a tabok/widgetek létrehozása előtt."""
    pending = st.session_state.pop("_pending_project_widget_sync", None)
    if not isinstance(pending, dict):
        return
    for key, value in pending.items():
        st.session_state[key] = value


def _apply_project_data_to_session(project_data: dict) -> None:
    """Felhő `project_data` visszaírása; widget-szinkron pending + rerun után."""
    if not isinstance(project_data, dict):
        return
    for key in PROJECT_DATA_KEYS:
        if key in project_data:
            st.session_state[key] = project_data[key]
    _queue_project_widget_sync_from_state()


def _workspace_has_substantive_content() -> bool:
    for key in (
        "overview",
        "exegesis",
        "history",
        "theology",
        "illustrations",
        "actualization",
        "outline",
        "outline_draft",
        "original_text",
        "songs",
        "series_planner_output",
        "last_igehely",
    ):
        if (st.session_state.get(key) or "").strip():
            return True
    if st.session_state.get("basket"):
        return True
    return False


def _set_flash(message: str, kind: str = "success") -> None:
    st.session_state["_flash_message"] = {"type": kind, "text": message}


def _render_flash_message() -> None:
    flash = st.session_state.pop("_flash_message", None)
    if not isinstance(flash, dict):
        return
    text = (flash.get("text") or "").strip()
    if not text:
        return
    kind = flash.get("type") or "success"
    if kind == "error":
        st.error(text)
    elif kind == "warning":
        st.warning(text)
    elif kind == "info":
        st.info(text)
    else:
        st.success(text)


def _mark_project_clean() -> None:
    st.session_state["project_saved_fingerprint"] = project_content_fingerprint(
        st.session_state
    )
    st.session_state["_project_last_save_ts"] = time.time()


def _is_project_dirty() -> bool:
    """Van-e nem mentett tartalmi változás a legutóbbi felhő-mentéshez képest."""
    _sync_inputs_to_last()
    title_now = (st.session_state.get("project_title_input") or "").strip()
    title_saved = (st.session_state.get("current_project_title") or "").strip()
    if title_now and title_now != title_saved:
        return True
    saved = (st.session_state.get("project_saved_fingerprint") or "").strip()
    current = project_content_fingerprint(st.session_state)
    if not saved:
        return _workspace_has_substantive_content()
    return current != saved


def _resolve_project_title() -> str:
    title = (st.session_state.get("project_title_input") or "").strip()
    if not title:
        title = (st.session_state.get("current_project_title") or "").strip()
    if not title:
        title = (st.session_state.get("last_igehely") or "").strip()
    return title or "Névtelen projekt"


def _cloud_save_project(*, as_new: bool = False, autosave: bool = False) -> None:
    """Mentés a fejlécsávból. Vendégnél no-op. Autosave csak meglévő projektre."""
    owner = _owner_sub()
    if not owner:
        if not autosave:
            _set_flash("A felhőmentéshez jelentkezz be.", "warning")
            st.rerun()
        return

    from project_storage import (
        build_project_data_from_state,
        create_project,
        update_project,
    )

    try:
        _sync_inputs_to_last()
        pdata = build_project_data_from_state(st.session_state, version=APP_VERSION)
        passage = (st.session_state.get("last_igehely") or "").strip()
        title = _resolve_project_title()
        cur_id = (st.session_state.get("current_project_id") or "").strip()

        if autosave:
            if not cur_id:
                return
            updated = update_project(cur_id, owner, title, passage, pdata)
            if not updated:
                return
            st.session_state["current_project_title"] = title
            st.session_state["_pending_project_title_input"] = title
            _mark_project_clean()
            _set_flash(f"Automatikus mentés: {title}", "info")
            st.rerun()
            return

        if as_new or not cur_id:
            row = create_project(owner, title, passage, pdata)
            st.session_state["current_project_id"] = str(row.get("id") or "")
            st.session_state["current_project_title"] = title
            st.session_state["_pending_project_title_input"] = title
            _mark_project_clean()
            _set_flash(f"Új projekt mentve: {title}")
        else:
            updated = update_project(cur_id, owner, title, passage, pdata)
            if not updated:
                _set_flash(
                    "A projekt nem található, vagy nem a te fiókodhoz tartozik.",
                    "error",
                )
            else:
                st.session_state["current_project_title"] = title
                st.session_state["_pending_project_title_input"] = title
                _mark_project_clean()
                _set_flash(f"Mentve: {title}")
        st.session_state["project_delete_confirm_id"] = None
        st.session_state["project_open_confirm_id"] = None
        st.rerun()
    except Exception as exc:
        if autosave:
            return
        _set_flash(f"Mentési hiba: {exc}", "error")
        st.rerun()


def _project_confirm_blocking() -> bool:
    return bool(
        st.session_state.get("project_open_confirm_id")
        or st.session_state.get("project_logout_confirm")
        or st.session_state.get("project_new_work_confirm")
        or st.session_state.get("project_delete_confirm_id")
    )


def _maybe_autosave_project() -> None:
    """3 percenként ment, ha be van jelentkezve, van megnyitott projekt, és dirty."""
    if not _owner_sub():
        return
    cur_id = (st.session_state.get("current_project_id") or "").strip()
    if not cur_id:
        return
    if _project_confirm_blocking():
        return
    if not _is_project_dirty():
        return
    last = float(st.session_state.get("_project_last_save_ts") or 0.0)
    if (time.time() - last) < PROJECT_AUTOSAVE_INTERVAL_S:
        return
    _cloud_save_project(as_new=False, autosave=True)


@st.fragment(run_every=timedelta(seconds=PROJECT_AUTOSAVE_INTERVAL_S))
def _project_autosave_fragment() -> None:
    """Háttérben futó autosave-ütemező (Streamlit fragment)."""
    _maybe_autosave_project()


def _cloud_open_project(project_id: str) -> None:
    owner = _owner_sub()
    if not owner:
        _set_flash("A betöltéshez jelentkezz be.", "warning")
        st.rerun()
        return

    from project_storage import get_project

    try:
        row = get_project(str(project_id), owner)
        if not row:
            _set_flash("A projekt nem található, vagy nem a tied.", "error")
            st.session_state["project_open_confirm_id"] = None
            st.rerun()
            return
        _apply_project_data_to_session(row.get("project_data") or {})
        title = (row.get("title") or "").strip() or "Névtelen projekt"
        st.session_state["current_project_id"] = str(row.get("id") or "")
        st.session_state["current_project_title"] = title
        st.session_state["_pending_project_title_input"] = title
        st.session_state["project_open_confirm_id"] = None
        st.session_state["project_delete_confirm_id"] = None
        st.session_state["show_projects_panel"] = False
        _mark_project_clean()
        _set_flash(f"Betöltve: {title}")
        st.rerun()
    except Exception as exc:
        _set_flash(f"Betöltési hiba: {exc}", "error")
        st.rerun()


def _request_open_project(project_id: str) -> None:
    """Megnyitás dirty / nem üres munkamenet esetén megerősítéssel."""
    pid = (project_id or "").strip()
    if not pid:
        return
    cur_id = (st.session_state.get("current_project_id") or "").strip()
    needs_confirm = pid != cur_id and (
        _is_project_dirty() or _workspace_has_substantive_content()
    )
    if needs_confirm:
        st.session_state["project_open_confirm_id"] = pid
        st.session_state["project_delete_confirm_id"] = None
        st.session_state["project_logout_confirm"] = False
        st.session_state["project_new_work_confirm"] = False
        st.rerun()
        return
    _cloud_open_project(pid)


def _clear_workspace_content() -> None:
    """Generált tartalom ürítése (API-kulcs érintetlen)."""
    for k in WORKSPACE_STR_KEYS:
        st.session_state[k] = ""
    for k in WORKSPACE_LIST_KEYS:
        st.session_state[k] = []
    for k in ("series_cadence",):
        st.session_state[k] = "vasárnapi"
    st.session_state["series_weeks"] = 4
    st.session_state["_clear_outline_workshop_editors"] = True
    st.session_state["current_project_id"] = ""
    st.session_state["current_project_title"] = ""
    st.session_state["_pending_project_title_input"] = ""
    st.session_state["project_saved_fingerprint"] = ""
    _queue_project_widget_sync_from_state()


def _start_new_work() -> None:
    _clear_workspace_content()
    st.session_state["project_new_work_confirm"] = False
    st.session_state["show_projects_panel"] = False
    _set_flash("Új üres munka indítva.", "info")
    st.rerun()


def _render_project_nav_confirms(owner: str | None) -> None:
    """Dirty váltás / megnyitás / kijelentkezés / új munka megerősítői."""
    open_pending = st.session_state.get("project_open_confirm_id")
    if open_pending:
        st.warning(
            "Nem mentett vagy meglévő munkamenet van a böngészőben. "
            "A megnyitás felülírja a jelenlegi tartalmat (a többi felhőprojekt érintetlen)."
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "Megnyitás a jelenlegi felülírásával",
                key="project_open_confirm_yes",
                use_container_width=True,
            ):
                _cloud_open_project(str(open_pending))
        with c2:
            if st.button("Mégsem", key="project_open_confirm_no", use_container_width=True):
                st.session_state["project_open_confirm_id"] = None
                st.rerun()

    if st.session_state.get("project_new_work_confirm"):
        st.warning("Nem mentett változások elveszhetnek. Indítod az új üres munkát?")
        n1, n2 = st.columns(2)
        with n1:
            if st.button(
                "Igen, új üres munka",
                key="project_new_work_yes",
                use_container_width=True,
            ):
                _start_new_work()
        with n2:
            if st.button("Mégsem", key="project_new_work_no", use_container_width=True):
                st.session_state["project_new_work_confirm"] = False
                st.rerun()

    if st.session_state.get("project_logout_confirm"):
        st.warning(
            "Nem mentett változások elveszhetnek a kijelentkezéssel. "
            "Előbb mentsd a fejlécsávból, vagy erősítsd meg a kilépést."
        )
        l1, l2 = st.columns(2)
        with l1:
            if st.button(
                "Kijelentkezés mentés nélkül",
                key="project_logout_yes",
                use_container_width=True,
            ):
                st.session_state["project_logout_confirm"] = False
                st.logout()
        with l2:
            if st.button("Mégsem", key="project_logout_no", use_container_width=True):
                st.session_state["project_logout_confirm"] = False
                st.rerun()


def _render_projects_quick_list(owner: str) -> None:
    """Kompakt projektlista a fejlécsáv „Projektek…” paneljében."""
    from project_storage import delete_project, get_user_projects

    del_pending = st.session_state.get("project_delete_confirm_id")
    if del_pending:
        del_label = "ezt a projektet"
        try:
            for p in get_user_projects(owner):
                if str(p.get("id")) == str(del_pending):
                    del_label = (p.get("title") or "").strip() or del_label
                    break
        except Exception:
            pass
        st.warning(f"Biztosan törlöd: **{del_label}**? Ez nem vonható vissza.")
        d1, d2 = st.columns(2)
        with d1:
            if st.button(
                "Végleges törlés",
                key="bar_project_delete_yes",
                use_container_width=True,
            ):
                try:
                    ok = delete_project(str(del_pending), owner)
                    if ok:
                        if str(st.session_state.get("current_project_id") or "") == str(
                            del_pending
                        ):
                            st.session_state["current_project_id"] = ""
                            st.session_state["current_project_title"] = ""
                            st.session_state["project_saved_fingerprint"] = ""
                        st.session_state["project_delete_confirm_id"] = None
                        _set_flash("Projekt törölve.")
                        st.rerun()
                    else:
                        _set_flash("A törlés nem sikerült.", "error")
                        st.rerun()
                except Exception as exc:
                    _set_flash(f"Törlési hiba: {exc}", "error")
                    st.rerun()
        with d2:
            if st.button("Mégsem", key="bar_project_delete_no", use_container_width=True):
                st.session_state["project_delete_confirm_id"] = None
                st.rerun()

    try:
        projects = get_user_projects(owner)
    except Exception as exc:
        st.error(f"A projektlista nem tölthető be: {exc}")
        return

    if not projects:
        st.caption("Még nincs mentett projekt. Használd a Mentés gombot az első mentéshez.")
        return

    cur_id = (st.session_state.get("current_project_id") or "").strip()
    for proj in projects:
        pid = str(proj.get("id") or "")
        ptitle = (proj.get("title") or "").strip() or "Névtelen projekt"
        ppassage = (proj.get("passage") or "").strip() or "—"
        pupdated = (proj.get("updated_at") or "")[:19].replace("T", " ")
        is_current = bool(pid and pid == cur_id)
        st.markdown(
            f"**{ptitle}**"
            + (" · *megnyitva*" if is_current else "")
            + f"  \n{ppassage}"
            + (f" · {pupdated}" if pupdated else "")
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "Megnyitás",
                key=f"bar_project_open_{pid}",
                use_container_width=True,
                disabled=not pid,
            ):
                _request_open_project(pid)
        with c2:
            if st.button(
                "Törlés",
                key=f"bar_project_delete_{pid}",
                use_container_width=True,
                disabled=not pid,
            ):
                st.session_state["project_delete_confirm_id"] = pid
                st.session_state["project_open_confirm_id"] = None
                st.rerun()


def _apply_pending_project_title_input() -> None:
    """Pending cím alkalmazása a `project_title_input` widget létrehozása előtt."""
    if st.session_state.get("_pending_project_title_input") is not None:
        st.session_state["project_title_input"] = st.session_state[
            "_pending_project_title_input"
        ]
        st.session_state["_pending_project_title_input"] = None
    elif "project_title_input" not in st.session_state:
        st.session_state["project_title_input"] = (
            (st.session_state.get("current_project_title") or "").strip()
            or (st.session_state.get("last_igehely") or "").strip()
            or ""
        )


def _render_project_status_bar() -> None:
    """Állandó projekt-sáv a fejléc után — mentés, dirty, projektek."""
    owner = _owner_sub()
    st.markdown("##### Projekt")
    if not owner:
        if not _auth_secrets_configured():
            st.caption(
                "Vendég mód · a felhő-bejelentkezéshez a Streamlit Secrets-ben "
                "be kell állítani az `[auth]` blokkot (és a Google OAuth redirect URI-t)."
            )
        else:
            st.caption(
                "Vendég mód · a felhőmentéshez jelentkezz be Google-fiókkal. "
                "A TEXTUS minden funkciója így is használható."
            )
            if st.button("Bejelentkezés Google-fiókkal", key="bar_google_login"):
                st.login()
        return

    cur_id = (st.session_state.get("current_project_id") or "").strip()
    cur_title = (st.session_state.get("current_project_title") or "").strip()
    passage = (st.session_state.get("last_igehely") or "").strip()
    dirty = _is_project_dirty()

    if cur_id:
        status = "Nem mentett változások" if dirty else "Mentve"
        label = cur_title or "Névtelen projekt"
        if passage and passage not in label:
            st.caption(
                f"**{label}** · {passage} · {status} · autosave ~3 perc"
            )
        else:
            st.caption(f"**{label}** · {status} · autosave ~3 perc")
    else:
        status = "Nem mentett változások" if dirty else "Nincs megnyitott projekt"
        st.caption(
            f"{status} · az autosave csak megnyitott / elmentett projektnél fut"
        )

    _apply_pending_project_title_input()
    st.text_input(
        "Projekt címe",
        placeholder="Pl. Jn 3,16 — húsvéti igehirdetés",
        key="project_title_input",
        help="A következő mentéskor (kézi vagy automatikus) ez a cím kerül a felhőbe.",
    )

    b1, b2, b3, b4 = st.columns([1.2, 1.2, 1.2, 1.2])
    with b1:
        save_label = "Mentés" if cur_id else "Mentés újként"
        if st.button(save_label, key="bar_project_save", use_container_width=True):
            _cloud_save_project(as_new=not bool(cur_id))
    with b2:
        if cur_id and st.button(
            "Mentés újként",
            key="bar_project_save_as_new",
            use_container_width=True,
        ):
            _cloud_save_project(as_new=True)
    with b3:
        toggle = "Projektek elrejtése" if st.session_state.get("show_projects_panel") else "Projektek…"
        if st.button(toggle, key="bar_projects_toggle", use_container_width=True):
            st.session_state["show_projects_panel"] = not bool(
                st.session_state.get("show_projects_panel")
            )
            st.rerun()
    with b4:
        if st.button("Új munka", key="bar_new_work", use_container_width=True):
            if _is_project_dirty() or _workspace_has_substantive_content():
                st.session_state["project_new_work_confirm"] = True
                st.session_state["project_logout_confirm"] = False
                st.session_state["project_open_confirm_id"] = None
                st.rerun()
            else:
                _start_new_work()

    _render_project_nav_confirms(owner)

    if st.session_state.get("show_projects_panel"):
        with st.expander("Mentett projektek", expanded=True):
            _render_projects_quick_list(owner)

    # Autosave: fragment 3 percenként + azonnali ellenőrzés interakciókor
    if cur_id:
        _maybe_autosave_project()
        _project_autosave_fragment()


# =========================================================
# VÁZLAT WORD EXPORT (.docx)
# =========================================================
# Ugyanaz a tartalom-struktúra, mint a Markdown exportnál; a vázlat törzsét
# és a kosár/ének szövegeket soronkénti, egyszerű Markdown-heurisztikával
# alakítjuk Word-be (UTF-8, Calibri — magyar ékezetek).

def _docx_strip_md_links(text: str) -> str:
    return re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text or "")


def _docx_add_inline_runs(paragraph, line: str) -> None:
    """`**félkövér**` és sima szöveg — páros `**` felosztással."""
    t = _docx_strip_md_links(line)
    parts = t.split("**")
    for i, seg in enumerate(parts):
        if not seg:
            continue
        run = paragraph.add_run(seg)
        if i % 2 == 1:
            run.bold = True


def _docx_append_markdown_body(doc, text: str) -> None:
    """Markdown-szerű blokk Word-be: címsorok, listák, idézet, üres sorok."""
    if not (text or "").strip():
        p = doc.add_paragraph(style="Intense Quote")
        p.add_run("_Még nem készült vázlat._")
        return
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            doc.add_paragraph()
            continue
        if stripped in ("---", "***", "___"):
            doc.add_paragraph()
            continue
        hm = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if hm:
            level = min(len(hm.group(1)), 4)
            doc.add_heading(hm.group(2).strip(), level=level)
            continue
        if stripped.startswith(">"):
            content = stripped.lstrip(">").strip()
            p = doc.add_paragraph(style="Quote")
            _docx_add_inline_runs(p, content)
            continue
        if re.match(r"^[-*+]\s+", stripped):
            content = re.sub(r"^[-*+]\s+", "", stripped)
            p = doc.add_paragraph(style="List Bullet")
            _docx_add_inline_runs(p, content)
            continue
        if re.match(r"^\d+\.\s+", stripped):
            content = re.sub(r"^\d+\.\s+", "", stripped)
            p = doc.add_paragraph(style="List Number")
            _docx_add_inline_runs(p, content)
            continue
        p = doc.add_paragraph()
        _docx_add_inline_runs(p, stripped)


def build_outline_docx() -> bytes:
    """Összeállítja a vázlatkosár + ének Word dokumentumát (bináris .docx)."""
    from docx import Document
    from docx.enum.text import WD_COLOR_INDEX
    from docx.shared import Pt

    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)

    doc.add_heading(f"Prédikációvázlat — {APP_NAME}", level=1)

    igehely = st.session_state.get("last_igehely", "—")
    alkalom = st.session_state.get("last_alkalom", "—")
    stilus = st.session_state.get("last_stilus", "—")
    outline = st.session_state.get("outline", "").strip()
    basket = st.session_state.get("basket", [])
    songs = st.session_state.get("songs", "").strip()
    now = datetime.now().strftime("%Y. %m. %d. %H:%M")

    p_meta = doc.add_paragraph()
    r_l = p_meta.add_run("Igehely: ")
    r_l.bold = True
    r_v = p_meta.add_run(igehely)
    r_v.bold = True
    try:
        r_v.font.highlight_color = WD_COLOR_INDEX.YELLOW
    except Exception:
        r_v.italic = True

    p_al = doc.add_paragraph()
    p_al.add_run("Alkalom: ").bold = True
    _docx_add_inline_runs(p_al, alkalom)

    p_st = doc.add_paragraph()
    p_st.add_run("Homiletikai stílus: ").bold = True
    _docx_add_inline_runs(p_st, stilus)

    doc.add_paragraph(f"Készült: {now}")
    doc.add_paragraph()

    doc.add_heading("Vázlat", level=2)
    _docx_append_markdown_body(doc, outline)

    if basket:
        doc.add_heading("Vázlatkosár — gondolatok a vázlathoz", level=2)
        for source, item in basket:
            doc.add_heading(source, level=3)
            _docx_append_markdown_body(doc, item)

    if songs:
        doc.add_heading("Liturgiai énekajánlás", level=2)
        _docx_append_markdown_body(doc, songs)

    doc.add_paragraph()
    p_f = doc.add_paragraph()
    r_f = p_f.add_run(f"{APP_NAME} v{APP_VERSION} — {APP_SUBTITLE} · {APP_TAGLINE}")
    r_f.italic = True

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# =========================================================
# SESSION STATE
# =========================================================

defaults = {
    "api_key": BUILTIN_API_KEY,
    "using_builtin_key": bool(BUILTIN_API_KEY),
    "user_model_choice": OWN_KEY_MODEL_AUTO,
    "model_name": LOCKED_MODEL,
    "temperature": 0.3,

    "last_igehely": "",
    "last_alkalom": "",
    "last_stilus": "",
    "last_sajat": "",
    "verse_history": [],

    "overview": "",
    "exegesis": "",
    "history": "",
    "theology": "",
    "illustrations": "",
    "actualization": "",
    "outline": "",
    "outline_draft": "",
    "outline_workshop_questions": "",
    "outline_workshop_answers": "",
    "outline_reworked_draft": "",
    "outline_title_suggestions": "",
    "original_text": "",
    "songs": "",

    "series_planner_output": "",
    "series_idea": "",
    "series_weeks": 4,
    "series_cadence": "vasárnapi",

    "basket": [],

    "exegesis_chat": [],
    "history_chat": [],
    "theology_chat": [],
    "illustrations_chat": [],
    "actualization_chat": [],
    "outline_chat": [],
    "original_text_chat": [],
    "songs_chat": [],

    # Cache + cooldown + debug log infra
    "enable_cache": True,
    "_call_cache": {},
    "_debug_log": [],
    "_last_api_call_ts": 0.0,

    # Felhő projekt (Saját munkáim) — csak bejelentkezve használt
    "current_project_id": "",
    "current_project_title": "",
    "project_delete_confirm_id": None,
    "project_open_confirm_id": None,
    "project_logout_confirm": False,
    "project_new_work_confirm": False,
    "show_projects_panel": False,
    "project_saved_fingerprint": "",
    "_project_last_save_ts": 0.0,
    "_flash_message": None,
    "_pending_project_title_input": None,
    "_pending_project_widget_sync": None,

    # Textus 2.0 M0 — nézetváltó (nem kerül project_data mentésbe)
    "ui_mode": "quick",
    "tw_active_section": "Igehely, alkalom és szövegkörnyezet",
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# Beépített módban a session kulcs másolatát szinkronban tartjuk a
# Streamlit Secrets / env aktuális értékével (Cloud Secrets frissítés,
# lokális secrets.toml szerkesztés újraindítás nélkül is konzisztens).
if st.session_state.get("using_builtin_key", False):
    _sk_sync = _load_builtin_api_key().strip()
    if _sk_sync:
        st.session_state["api_key"] = _sk_sync

# Régi munkamenet / rossz cwd: üres session-kulcs, de a projekt secrets már elérhető
_live_builtin = _load_builtin_api_key().strip()
if _live_builtin and not (st.session_state.get("api_key") or "").strip():
    st.session_state["api_key"] = _live_builtin
    st.session_state["using_builtin_key"] = True


def _resolve_api_key() -> str:
    """Minden Gemini REST-kéréshez használandó API-kulcs (egyetlen belépési pont).

    Felülírási sorrend (a feladat szerinti fallback):
      1. Ha a felhasználó **saját kulcsot** adott meg (`using_builtin_key` hamis
         és van nem üres `st.session_state["api_key"]`) → **azt** használjuk.
      2. Egyébként → `_load_builtin_api_key()` (env → projekt `secrets.toml` →
         `st.secrets`), minden híváskor frissen, hogy ne maradjon elavult érték.

    A `x-goog-api-key` fejléc **mindig** ennek a függvénynek a visszatérési értékét
    kapja — nincs párhuzamos, eltérő kulcsforrás a kódban.
    """
    sess = (st.session_state.get("api_key") or "").strip()
    using_builtin = bool(st.session_state.get("using_builtin_key", True))
    secret_default = _load_builtin_api_key().strip()

    if not using_builtin and sess:
        return sess
    return secret_default or sess


def _api_key_source_label() -> str:
    """Debug / napló: honnan jön az épp aktív kulcs."""
    if not bool(st.session_state.get("using_builtin_key", True)) and (
        st.session_state.get("api_key") or ""
    ).strip():
        return "user-override"
    if (os.environ.get("GEMINI_API_KEY", "") or "").strip():
        return "env-GEMINI_API_KEY"
    if _read_gemini_key_from_project_secrets_file():
        return "project-.streamlit/secrets.toml"
    try:
        if st.secrets.get("GEMINI_API_KEY", ""):
            return "st.secrets-cwd"
    except Exception:
        pass
    return "none"


# =========================================================
# GEMINI API HÍVÁS
# =========================================================

def _google_search_tool_for_model(model_name: str = LOCKED_MODEL):
    """Google Search grounding (`google_search`) — a hívott modellhez illesztve."""
    return {"google_search": {}}


def _extract_retry_after_seconds(response, attempt: int, default_base_s: int) -> int:
    """A 429-válaszból kinyeri a Google által javasolt várakozási időt.

    Sorrend:
      1. `Retry-After` HTTP header (egész másodperc)
      2. body → `error.details[*]` `RetryInfo.retryDelay` (pl. "30s")
      3. fallback: `default_base_s * 2^attempt`
    """
    raw = response.headers.get("Retry-After") or response.headers.get("retry-after")
    if raw:
        try:
            v = int(float(raw))
            if 0 < v < 600:
                return v
        except (ValueError, TypeError):
            pass

    try:
        body = response.json()
        details = body.get("error", {}).get("details", []) or []
        for d in details:
            tname = d.get("@type", "") or ""
            if "RetryInfo" in tname:
                rd = d.get("retryDelay", "")
                if isinstance(rd, str) and rd.endswith("s"):
                    try:
                        v = int(float(rd[:-1]))
                        if 0 < v < 600:
                            return v
                    except (ValueError, TypeError):
                        pass
    except Exception:
        pass

    return default_base_s * (2 ** attempt)


def _extract_error_message(response) -> str:
    """A Google API hibaválaszából tisztán kinyeri az `error.message` szöveget."""
    try:
        body = response.json()
        msg = body.get("error", {}).get("message", "")
        if msg:
            return str(msg)[:500]
    except Exception:
        pass
    snippet = (response.text or "").strip()
    return snippet[:500] if snippet else "(nincs hibaüzenet a válaszban)"


def _log_http_error(model: str, sc: int, response) -> str:
    """Részletes konzol-log a nem-200 válaszról + visszaadja a hibaüzenetet."""
    err_msg = _extract_error_message(response)
    body_snippet = (response.text or "")[:800]
    try:
        print(
            f"[GEMINI ERROR] model={model} status={sc} message={err_msg}\n"
            f"  body[:800]={body_snippet}",
            flush=True,
        )
    except Exception:
        pass
    return err_msg


def _format_grounding_sources(result: dict) -> str:
    """A Google Search grounding válaszból kiszedi a forrás-URL-eket
    és egy elegáns Markdown forrás-listát ad vissza."""
    try:
        candidate = result["candidates"][0]
        meta = candidate.get("groundingMetadata") or {}
        chunks = meta.get("groundingChunks") or []
        sources = []
        seen = set()
        for ch in chunks:
            web = ch.get("web") or {}
            uri = web.get("uri")
            title = web.get("title") or uri
            if uri and uri not in seen:
                seen.add(uri)
                sources.append((title, uri))
        queries = meta.get("webSearchQueries") or []

        if not sources and not queries:
            return ""

        out = ["", "---", "", "### 🌐 Google Search források"]
        if queries:
            qlist = ", ".join(f"`{q}`" for q in queries[:6])
            out.append(f"_Lekérdezések:_ {qlist}")
            out.append("")
        for title, uri in sources[:10]:
            out.append(f"- [{title}]({uri})")
        return "\n".join(out)
    except Exception:
        return ""


# =========================================================
# UDVARIASSÁGI BEVEZETŐK / ZÁRÁSOK ELTÁVOLÍTÁSA
# =========================================================
#
# Második védelmi vonal a prompt-szintű tiltás mellett: ha a Gemini
# mégis becsempész egy "Üdvözlöm…" / "A TEXTUS moduljaként…" típusú
# bevezetőt vagy záró "Bízom benne, hogy…" sort, kódból kivágjuk.

import re as _re_chatty

_CHATTY_INTRO_PATTERNS = [
    # Üdvözlések
    r"^(üdvözlöm|üdv|hello|szia|szervusz|tisztelt|kedves|drága|jó (napot|reggelt|estét))\b",
    # Öndefiniáló bevezetők
    r"^(a textus|az textus|mint (a |)textus|textus(ként| modulként| moduljaként)|"
    r"(a |)textus homiletikai|"
    r"az emmaus|mint (az |)emmaus|emmaus(ként| modulként| moduljaként)|"
    r"(az |)emmaus digitális|teológiai modul(ja)?ként|"
    r"ai(-)?(\s*ként|nak|ként)|asszisztens(ként)?|"
    r"modell(ként)?|chatbot(ként)?|nyelvi modell)\b",
    # Udvariaskodó nyitások
    r"^(örömmel|szívesen|nagyszerű|kiváló|remek|természetesen|persze|hogyne)\b",
    # Bevezető meta-mondatok
    r"^(itt (van|vannak|következik|áll)|íme|alább(iakban)?|az alábbi(akban)?|"
    r"a következőkben|ebben a válaszban|az elemzésem|az alábbi elemzés|"
    r"folytatva|folytatom)\b",
]

_CHATTY_OUTRO_PATTERNS = [
    r"^(reményeim szerint|remélem,? hogy|bízom benne,? hogy|bízom abban,? hogy)\b",
    r"^(bármikor szólj|bármi(ben|kor) (segítek|kérdésed)|ha bármi (kérdésed|kérdés))\b",
    r"^(áldás|az úr áldása|isten áldása) (kíséri|kísérje|legyen)\b",
    r"^(jó (munkát|szolgálatot|prédikálást)|sok sikert|kitartást)\b",
    r"^(összegezve|végezetül|összefoglalva)[:,]?\s*(reményeim|remélem|bízom|"
    r"hasznos volt|hasznos lehet)",
]

_CHATTY_INTRO_RE = _re_chatty.compile(
    "|".join(_CHATTY_INTRO_PATTERNS), _re_chatty.IGNORECASE
)
_CHATTY_OUTRO_RE = _re_chatty.compile(
    "|".join(_CHATTY_OUTRO_PATTERNS), _re_chatty.IGNORECASE
)


_MD_BLOCK_PREFIXES = ("#", "-", "*", "|", "```", ">", "1.", "2.", "3.")


def _strip_chatty_intro(text: str) -> str:
    """A válasz elejéről és végéről eltávolítja a tipikus Gemini-féle
    udvariassági / öndefiniáló bevezető és záró fordulatokat.

    Stratégia:
    - ELÖL: az ELSŐ bekezdés MONDATAIT szűrjük egyenként (max. 4 mondatig);
      addig vetjük el a mondatokat, amíg a chatty regex matchel. Az első
      olyan mondatnál, amelyik NEM matchel, megállunk és minden további
      tartalmat megtartunk.
    - HÁTUL: bekezdés-szinten dobjuk az utolsó udvariaskodó záró mondatot.
    - Markdown blokkokat (címsor, lista, kód, idézet, számozott lista)
      sosem nyúlunk hozzá.
    """
    if not text or not isinstance(text, str):
        return text

    text = text.lstrip("\ufeff").lstrip()

    # 404-fallback `> ℹ️` jelzést megőrizzük a tetején.
    leading_notice = ""
    if text.startswith(">"):
        end_of_quote = text.find("\n\n")
        if end_of_quote != -1:
            leading_notice = text[: end_of_quote + 2]
            text = text[end_of_quote + 2 :]

    # ───── ELEJE: mondat-szintű cleanup az első bekezdésen belül ─────
    if text and not text.lstrip().startswith(_MD_BLOCK_PREFIXES):
        first_para_end = text.find("\n\n")
        if first_para_end == -1:
            first_para = text
            rest = ""
        else:
            first_para = text[:first_para_end]
            rest = text[first_para_end:]

        sentences = _re_chatty.split(r"(?<=[\.!\?])\s+", first_para.strip())

        kept_idx = 0
        max_skip = min(4, len(sentences))
        for i in range(max_skip):
            s = sentences[i].strip()
            if not s:
                kept_idx = i + 1
                continue
            if _CHATTY_INTRO_RE.search(s):
                kept_idx = i + 1
                continue
            break

        kept = sentences[kept_idx:]
        first_para_clean = " ".join(kept).strip()
        text = (first_para_clean + rest) if first_para_clean else rest.lstrip()

    # ───── VÉGE: utolsó bekezdés szűrése ─────
    parts = _re_chatty.split(r"\n{2,}", text)
    if len(parts) > 1:
        last = parts[-1].strip()
        if (
            last
            and not last.startswith(_MD_BLOCK_PREFIXES)
            and len(last) < 500
            and _CHATTY_OUTRO_RE.search(last)
        ):
            parts = parts[:-1]
        text = "\n\n".join(p for p in parts if p).rstrip()

    return (leading_notice + text).strip()


import time as _time
import hashlib as _hashlib
from datetime import datetime as _dt

# ─── Retry, cooldown, debug, cache konfiguráció ──────────────────────
GEMINI_MAX_RETRIES = 3            # max. ennyi újrapróbálkozás 429 / 5xx esetén
GEMINI_RETRY_BASE_S = 10          # 5xx exponenciális backoff: 10s, 20s, 40s
GEMINI_RATE_LIMIT_BASE_S = 15     # 429-re külön, hosszabb backoff: 15s, 30s, 60s
GEMINI_TIMEOUT_S = 120
GEMINI_COOLDOWN_S = 8             # globális cooldown két logikai hívás közt
GEMINI_DEBUG_LOG_MAX = 80         # session debug-log max bejegyzések

# Nincs alkalmazásszintű kimeneti tokenplafon: nem küldünk
# `generationConfig.maxOutputTokens` mezőt. A válaszhosszt promptszinten
# szabályozzuk: tömör, strukturált, de a fontos információkat nem kihagyó
# válaszokat kérünk.

KEY_EXPRESSIONS_SYSTEM_PROMPT = """\
Te egy bibliai eredeti nyelvi és exegetikai műhelyvezető vagy.
Az Eredeti szöveg tanulmányozása funkcióban fontos héber/görög kifejezéseket,
jelentésárnyalatokat, bibliai párhuzamokat és prédikációs hozamokat emelsz ki
magyarul.

A cél nem teljes teológiai rendszer, hanem tiszta, fókuszált segítség a textus
tudatosabb olvasásához és prédikációra való előkészítéséhez.
Kerüld a chatty megszólítást, önbemutatkozást és udvariaskodó zárást; azonnal
a szakmai tartalommal kezdj.
"""

# ─────────────────────────────────────────────────────────────────────
# VÁLASZADÁSI STÍLUS — GLOBÁLIS IRÁNYELVEK
# ─────────────────────────────────────────────────────────────────────
# A `_build_payload` nem állít kimeneti tokenlimitet. Ez a direktíva csak
# stílusirány: legyen áttekinthető, arányos és prédikáció-előkészítésben
# használható, de ne terjengős.

_RESPONSE_LENGTH_DIRECTIVE = """\
==================================================
VÁLASZADÁSI STÍLUS — GLOBÁLIS IRÁNYELVEK
==================================================

Minden válasz legyen:

- világos,
- jól strukturált,
- könnyen áttekinthető,
- teológiailag igényes,
- gyakorlati szempontból használható.

A cél nem akadémiai szóhalmozás vagy teljes kommentár készítése,
hanem egy prédikációra készülő lelkipásztor segítése.

FONTOS:

- Emeld ki a lényeget.
- Ne elemezz feleslegesen minden részletet.
- Ne ismételd önmagad különböző megfogalmazásokban.
- Kerüld a túl hosszú körmondatokat és a szócséplést.
- A válasz ne legyen sem túl rövid, sem indokolatlanul hosszú.
- Inkább kevés, de lényeges és jól megfogalmazott megfigyelést adj.
- A felsorolások legyenek áttekinthetőek és funkcionálisak.
- A hangsúly a használhatóságon, nem a terjedelem maximalizálásán legyen.

A stílus legyen:
- természetes,
- emberközeli,
- tiszteletteljes,
- de ne túl informális.

A válaszok segítsék:
- az igehirdetés előkészítését,
- az exegetikai tájékozódást,
- a teológiai reflexiót,
- és a gyakorlati alkalmazhatóságot.

NE írj megszólítást, udvariaskodó nyitást vagy zárást; azonnal kezdd a szakmai tartalommal.
"""


def _is_using_builtin_key() -> bool:
    """A felhasználó a beépített közös kulcsot használja-e (csak label)."""
    return bool(st.session_state.get("using_builtin_key", False))


def _active_brevity_directive() -> str:
    """Egységes, kulcsforrástól független válaszstílus-irányelv."""
    return _RESPONSE_LENGTH_DIRECTIVE


SERIES_PLANNER_SYSTEM_PROMPT = """\
Te egy tapasztalt lelkipásztor és homiletikai tanácsadó vagy. A feladatod, hogy a megadott téma és a felhasználó által megadott sorozat-jelleg (vasárnapi heti / hétköznapi napi / vegyes) alapján egy összefüggő, teológiailag megalapozott és gyülekezetépítő Igehirdetési sorozat tervezetet készíts.

A válaszod szerkezete (Markdown formátumban):

Sorozat címe: Adj egy beszédes, hívogató címet a sorozatnak.

Lelki célkitűzés: 2-3 mondatban foglald össze, mi a sorozat fő üzenete és hová kívánja elvezetni a hallgatókat.

Alkalmankénti bontás: Minden egyes alkalomra (a megadott számnak megfelelően) készíts egy külön részt. A fejléc a sorozat jellegéhez igazodjon:
- vasárnapi (heti) sorozatnál: „1. hét — …”, „2. hét — …” …
- hétköznapi sorozatnál (pl. bűnbánati hét, esti istentiszteleti hét): a hét napjai szerint („Hétfő — …”, „Kedd — …” stb.) vagy „1. nap — …”, „2. nap — …”.
- sátoros ünnepi (Karácsony / Húsvét / Pünkösd) sorozatnál: pontosan **3** alkalom, „Ünnep első napja — …”, „Ünnep második napja — …”, „Ünnep harmadik napja — …” fejlécekkel (vagy konkrétan: „Karácsony 1. napja — …”, „Húsvét 1. napja — …”, „Pünkösd 1. napja — …”).
- vegyes / egyéb ütemnél: „1. alkalom — …”, „2. alkalom — …”.
A fejléc legyen önálló sor elején (Markdown bold vagy `##`/`###` cím is lehet), hogy a felület külön egységekbe tagolja.

Minden alkalom tartalma:

Fő alapige: (Pontos hivatkozás és a legfontosabb vers idézése)

Kapcsolódó igeszakasz: (Egy kiegészítő igehely a mélyebb megértéshez)

Az igehirdetés fő üzenete: (3-4 pontba szedett teológiai és gyakorlati kulcsgondolat)

Gyakorlati tanulság: (Egy konkrét kérdés vagy gyakorlat, amit a hívek magukkal vihetnek)

Teológiai iránytű: Kövesd a protestáns hagyományokat, legyél bibliacentrikus, de a magyarázatok legyenek relevánsak a 21. századi ember életvezetési nehézségeire is. Ne adj több vagy kevesebb alkalmat, mint amennyit a felhasználó kért."""


_SERIES_WEEKDAY_OR_FESTIVAL = (
    r"H[eé]tf[oő]|Kedd|Szerda|Cs[uü]t[oö]rt[oö]k|P[eé]ntek|Szombat|Vas[aá]rnap|"
    r"Vir[aá]gvas[aá]rnap|Nagyh[eé]tf[oő]|Nagykedd|Nagyszerda|"
    r"Nagycs[uü]t[oö]rt[oö]k|Nagyp[eé]ntek|Nagyszombat|"
    r"Kar[aá]csony|H[uú]sv[eé]t|P[uü]nk[oö]sd"
)

_SERIES_FESTIVAL_DAY = (
    r"(?:Kar[aá]csony|H[uú]sv[eé]t|P[uü]nk[oö]sd|Ünnep)\s+"
    r"(?:els[oő]|m[aá]sodik|harmadik|\d+\.)\s*napja"
)

_SERIES_SECTION_SPLIT_RE = re.compile(
    r"(?m)^(?=\s*"
    r"(?:#{1,6}\s+)?"
    r"(?:\*\*)?"
    r"(?:"
    r"\d+\.\s*(?:hét|alkalom|nap|este)\b"
    r"|" + _SERIES_FESTIVAL_DAY +
    r"|" + _SERIES_WEEKDAY_OR_FESTIVAL + r"\b"
    r")"
    r")",
    re.IGNORECASE,
)


def _parse_series_week_sections(markdown: str) -> tuple[str, list[tuple[str, str]]]:
    """Sorozat-fej + alkalmankénti blokkok szétválasztása.

    Több mintázatot ismer: `N. hét`, `N. alkalom`, `N. nap`, `N. este`,
    valamint hétköznap- és ünnepneveket (Hétfő, Nagypéntek, …) — opcionális
    `**` vagy `##`/`###` előtaggal.
    """
    text = (markdown or "").strip()
    if not text:
        return "", []

    parts = _SERIES_SECTION_SPLIT_RE.split(text)
    if len(parts) <= 1:
        return text, []

    head = parts[0].strip()
    sections: list[tuple[str, str]] = []
    for chunk in parts[1:]:
        chunk = chunk.strip()
        if not chunk:
            continue
        first_line, sep, rest = chunk.partition("\n")
        title_raw = first_line.strip() or "Alkalom"
        title = re.sub(r"^#{1,6}\s+", "", title_raw)
        title = title.strip("*").strip()
        title = (title or "Alkalom")[:160]
        body = rest.strip() if sep else chunk
        if not body:
            body = chunk
        sections.append((title, body))
    return head, sections


def _now_str() -> str:
    return _dt.now().strftime("%H:%M:%S")


def _hash_prompt(prompt: str, extra: str = "") -> str:
    h = _hashlib.sha256()
    h.update(prompt.encode("utf-8"))
    if extra:
        h.update(b"|")
        h.update(extra.encode("utf-8"))
    return h.hexdigest()[:16]


def _mask_api_key(key) -> str:
    """API kulcsot biztonságosan maszkol a logokhoz.

    Csak az első 6 karaktert mutatja, a többit `*`-ra cseréli.
    Pl.: `AIzaSyB123...456` → `AIzaSy**********`. A teljes kulcsot
    SOHA nem írja ki — semmilyen log, terminál vagy debug felület felé.
    """
    if not key:
        return "(nincs)"
    key = str(key).strip()
    if not key:
        return "(nincs)"
    if len(key) <= 6:
        return "*" * len(key)
    return key[:6] + ("*" * (len(key) - 6))


def _get_session_id() -> str:
    """Streamlit session azonosítót ad vissza (max 12 karakter), biztonságosan.

    Elsősorban a Streamlit belső script-run-context session_id-jét
    használja; ha az nem elérhető (pl. headless teszt), egyszer generált
    UUID-fallback kerül a session_state-be.
    """
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx  # noqa: WPS433
        ctx = get_script_run_ctx()
        if ctx and getattr(ctx, "session_id", None):
            return str(ctx.session_id)[:12]
    except Exception:
        pass
    sid = st.session_state.get("_session_uuid")
    if not sid:
        import uuid as _uuid
        sid = _uuid.uuid4().hex[:12]
        st.session_state["_session_uuid"] = sid
    return sid


def _debug_log_append(entry: dict):
    """Egyetlen debug-bejegyzést hozzáfűz a session loghoz + konzolra is print.

    Automatikusan kitölti a kontextus-mezőket, ha még nincsenek:
    `session_id`, `key_source` (built-in / saját), `key_masked`.
    """
    if "session_id" not in entry:
        try:
            entry["session_id"] = _get_session_id()
        except Exception:
            entry["session_id"] = "unknown"

    if "key_source" not in entry or "key_masked" not in entry:
        resolved = _resolve_api_key().strip()
        entry.setdefault("key_source", _api_key_source_label())
        entry.setdefault("key_masked", _mask_api_key(resolved))

    log = st.session_state.setdefault("_debug_log", [])
    log.append(entry)
    if len(log) > GEMINI_DEBUG_LOG_MAX:
        del log[: len(log) - GEMINI_DEBUG_LOG_MAX]

    try:
        print(
            "[GEMINI {ts}] sid={sid} key_src={ksrc} key={kmsk} auth_ok={auth} "
            "tab={tab} attempt={att} status={st} model={mdl} "
            "prompt_chars={pc} resp_chars={rc} latency_ms={lat}".format(
                ts=entry.get("ts", ""),
                sid=entry.get("session_id", ""),
                ksrc=entry.get("key_source", ""),
                kmsk=entry.get("key_masked", ""),
                auth=entry.get("auth_ok", "—"),
                tab=entry.get("tab", ""),
                att=entry.get("attempt", ""),
                st=entry.get("status", ""),
                mdl=entry.get("model", ""),
                pc=entry.get("prompt_chars", ""),
                rc=entry.get("response_chars", ""),
                lat=entry.get("latency_ms", ""),
            ),
            flush=True,
        )
    except Exception:
        pass


def _cooldown_remaining() -> float:
    """Hátralévő mp a globális cooldown végéig (0.0 ha elindítható)."""
    last = float(st.session_state.get("_last_api_call_ts", 0.0))
    if last <= 0:
        return 0.0
    elapsed = _time.time() - last
    if elapsed >= GEMINI_COOLDOWN_S:
        return 0.0
    return GEMINI_COOLDOWN_S - elapsed


def _build_payload(
    prompt: str,
    enable_google_search: bool,
    model: str,
    *,
    system_bundle: str | None = None,
    include_brevity_directive: bool = True,
) -> dict:
    """Összeállítja a Gemini REST kérés JSON body-ját (`model` = Flash vagy Flash Lite).

    Alapértelmezés: `BASE_SYSTEM_PROMPT` + `_RESPONSE_LENGTH_DIRECTIVE` + FELADAT.
    Ha `system_bundle` meg van adva, az váltja ki a `BASE_SYSTEM_PROMPT` részt
    (pl. sorozattervező saját rendszerpromptja). `include_brevity_directive=False`
    esetén a rövid válasz direktíva nem kerül a promptba.

    Nem állítunk `generationConfig.maxOutputTokens` mezőt; a válaszhosszt
    promptszinten szabályozzuk.
    Google Search grounding: `google_search` tool, ha `enable_google_search`.
    """
    task_block = (
        "==================================================\n"
        "FELADAT\n"
        "==================================================\n\n"
        f"{prompt}\n"
    )
    if system_bundle is not None:
        body_parts = [system_bundle.strip()]
        if include_brevity_directive:
            body_parts.append(_active_brevity_directive())
        body_parts.append(task_block)
        final_prompt = "\n\n".join(body_parts)
    else:
        body_parts = [BASE_SYSTEM_PROMPT.strip()]
        if include_brevity_directive:
            body_parts.append(_active_brevity_directive())
        body_parts.append(task_block)
        final_prompt = "\n\n".join(body_parts)

    payload = {
        "contents": [{"parts": [{"text": final_prompt}]}],
        "generationConfig": {
            "temperature": st.session_state.get("temperature", 0.3),
        },
    }
    if enable_google_search:
        payload["tools"] = [_google_search_tool_for_model(model)]
    return payload


def generate_text(
    prompt,
    enable_google_search: bool = False,
    *,
    tab_label: str = "unknown",
    use_cache: bool = True,
    system_bundle: str | None = None,
    include_brevity_directive: bool = True,
    truncation_message: str | None = None,
    truncation_notice_mode: str = "always",
    incomplete_response_message: str | None = None,
):
    """EGYETLEN logikai Gemini-hívás — gomb-szintű egyediség garantált.

    Egyetlen gombnyomás MAX 1 logikai `generate_text` hívást indíthat;
    a retry-loop (429/5xx esetén) ugyanahhoz a gombnyomáshoz tartozik
    (a debug log `attempt` mezője láthatóvá teszi az ismétlést).

    Védelmi rétegek (sorrendben):
      1. API-kulcs check
      2. Opcionális cache-hit (enable_cache + azonos prompt) → 0 hívás
      3. Globális cooldown (`GEMINI_COOLDOWN_S`) → blokkoló üzenet
      4. HTTP hívás retry-jal (429/5xx → 10/20/40s backoff, max 3x)

    Minden HTTP-küldés ELŐTT és UTÁN debug-log bejegyzés készül
    (session_state["_debug_log"] + konzol-print).

    A cél-modell a `tab_label` alapján automatikusan választódik
    (`resolve_gemini_model_for_tab`). Közös kulcsnál Flash / Flash Lite;
    saját kulcsnál opcionális kézi modellválasztás (alapértelmezés = fül szerint).

    `system_bundle` / `include_brevity_directive`:
    speciális fülekhez (pl. sorozattervező) — lásd `_build_payload`.
    """
    api_key = _resolve_api_key().strip()
    if not api_key:
        return "⚠️ **Hiányzó API kulcs.** Add meg a Beállítások fülön a Gemini API kulcsot, mielőtt elindítanád az elemzést."

    model = resolve_gemini_model_for_tab(tab_label)
    st.session_state["model_name"] = model

    cache_enabled = (
        use_cache
        and bool(st.session_state.get("enable_cache", True))
        and not enable_google_search  # Google-keresés esetén mindig friss adat kell
    )
    _sys_key = "def"
    if system_bundle is not None:
        _sys_key = _hash_prompt(system_bundle)[:12]
    _brv = "1" if include_brevity_directive else "0"
    _trunc_key = _hash_prompt(
        f"{truncation_message or 'default'}|{truncation_notice_mode}|"
        f"{incomplete_response_message or 'allow_partial'}"
    )[:12]
    prompt_hash = _hash_prompt(
        prompt,
        extra=(
            f"{model}|{st.session_state.get('temperature', 0.3)}|"
            f"{_sys_key}|{_brv}|{_trunc_key}"
        ),
    )

    # ─── 1. CACHE HIT ────────────────────────────────────────────────
    cache = st.session_state.setdefault("_call_cache", {})
    if cache_enabled and prompt_hash in cache:
        cached_text, _cached_ts = cache[prompt_hash]
        _debug_log_append({
            "ts": _now_str(),
            "tab": tab_label,
            "attempt": 0,
            "status": "CACHE_HIT",
            "model": model,
            "prompt_chars": len(prompt),
            "response_chars": len(cached_text),
            "latency_ms": 0,
        })
        return cached_text

    # ─── 2. GLOBÁLIS COOLDOWN ────────────────────────────────────────
    remaining = _cooldown_remaining()
    if remaining > 0:
        _debug_log_append({
            "ts": _now_str(),
            "tab": tab_label,
            "attempt": 0,
            "status": "COOLDOWN_BLOCK",
            "model": model,
            "prompt_chars": len(prompt),
            "response_chars": 0,
            "latency_ms": 0,
        })
        return (
            "⏳ **Kérlek várj néhány másodpercet az újabb generálás előtt.** "
            f"(Még kb. {int(remaining) + 1} másodperc.)"
        )

    # ─── 3. HTTP HÍVÁS (retry: 429 / 5xx — ugyanazon a modellen) ───────
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    prompt_chars = len(prompt)
    last_error_msg = "⚠️ **Ismeretlen hiba történt a kérés közben.**"

    for attempt in range(GEMINI_MAX_RETRIES):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        data = _build_payload(
            prompt,
            enable_google_search,
            model,
            system_bundle=system_bundle,
            include_brevity_directive=include_brevity_directive,
        )

        # log: BEFORE (kulcsforrás + auth még függőben)
        _debug_log_append({
            "ts": _now_str(),
            "tab": tab_label,
            "attempt": attempt + 1,
            "status": "REQUEST",
            "model": model,
            "prompt_chars": prompt_chars,
            "response_chars": 0,
            "latency_ms": 0,
            "auth_ok": "pending",
        })
        start_ts = _time.time()

        try:
            response = requests.post(
                url, headers=headers, json=data,
                verify=False, timeout=GEMINI_TIMEOUT_S, stream=False,
            )
        except requests.exceptions.Timeout:
            latency_ms = int((_time.time() - start_ts) * 1000)
            try:
                print(f"[GEMINI ERROR] model={model} TIMEOUT after {latency_ms}ms", flush=True)
            except Exception:
                pass
            _debug_log_append({
                "ts": _now_str(), "tab": tab_label, "attempt": attempt + 1,
                "status": "TIMEOUT", "model": model,
                "prompt_chars": prompt_chars, "response_chars": 0, "latency_ms": latency_ms,
                "error_message": "Network timeout",
            })
            st.session_state["_last_api_call_ts"] = _time.time()
            last_error_msg = (
                "⚠️ **Időtúllépés.** A Gemini szerver nem válaszolt időben. "
                "Próbáld újra pár másodperc múlva, vagy rövidítsd a kérést / bontsd kisebb részekre."
            )
            if attempt < GEMINI_MAX_RETRIES - 1:
                _time.sleep(GEMINI_RETRY_BASE_S * (2 ** attempt))
                continue
            return last_error_msg
        except requests.exceptions.ConnectionError as ce:
            try:
                print(f"[GEMINI ERROR] model={model} CONN_ERROR: {ce}", flush=True)
            except Exception:
                pass
            _debug_log_append({
                "ts": _now_str(), "tab": tab_label, "attempt": attempt + 1,
                "status": "CONN_ERROR", "model": model,
                "prompt_chars": prompt_chars, "response_chars": 0,
                "latency_ms": int((_time.time() - start_ts) * 1000),
                "error_message": str(ce)[:300],
            })
            st.session_state["_last_api_call_ts"] = _time.time()
            return (
                "⚠️ **Nincs internetkapcsolat.** Nem sikerült elérni a Gemini API-t. "
                "Ellenőrizd a hálózati kapcsolatot."
            )
        except Exception as e:
            try:
                print(f"[GEMINI ERROR] model={model} EXCEPTION: {e}", flush=True)
            except Exception:
                pass
            _debug_log_append({
                "ts": _now_str(), "tab": tab_label, "attempt": attempt + 1,
                "status": "EXCEPTION", "model": model,
                "prompt_chars": prompt_chars, "response_chars": 0,
                "latency_ms": int((_time.time() - start_ts) * 1000),
                "error_message": str(e)[:300],
            })
            st.session_state["_last_api_call_ts"] = _time.time()
            return f"⚠️ **Ismeretlen hiba történt a kérés közben.**\n\n```\n{e}\n```"

        latency_ms = int((_time.time() - start_ts) * 1000)
        sc = response.status_code
        # cooldown timestamp frissítés MINDEN befejezett HTTP után
        st.session_state["_last_api_call_ts"] = _time.time()

        # ─── Sikeres válasz ─────────────────────────────────────────
        if sc == 200:
            try:
                result = response.json()
                candidate = result["candidates"][0]
                parts = candidate.get("content", {}).get("parts", [])
                text = "".join(
                    str(part.get("text", ""))
                    for part in parts
                    if isinstance(part, dict) and part.get("text")
                )
                text = _strip_chatty_intro(text)

                # ── MODELL-OLDALI LEVÁGÁS DETEKTÁLÁSA ─────────────────
                # Nem állítunk app-szintű kimeneti plafont, de a modellnek
                # lehet saját természetes kimeneti korlátja.
                finish_reason = candidate.get("finishReason", "STOP")
                truncated = finish_reason == "MAX_TOKENS"
                status_label = "200_OK" if not truncated else "200_TRUNCATED"

                if not text.strip():
                    _debug_log_append({
                        "ts": _now_str(), "tab": tab_label, "attempt": attempt + 1,
                        "status": "EMPTY_TEXT", "model": model,
                        "prompt_chars": prompt_chars, "response_chars": 0,
                        "latency_ms": latency_ms,
                        "error_message": "No text parts in Gemini response",
                        "auth_ok": True,
                    })
                    return (
                        "⚠️ **A Gemini válasza üres volt.** "
                        "Próbáld újra, vagy fogalmazd át kissé a kérést."
                    )

                if incomplete_response_message and (
                    truncated or _looks_incomplete_response(text)
                ):
                    _debug_log_append({
                        "ts": _now_str(), "tab": tab_label, "attempt": attempt + 1,
                        "status": "INCOMPLETE_REJECTED", "model": model,
                        "prompt_chars": prompt_chars, "response_chars": len(text),
                        "latency_ms": latency_ms,
                        "error_message": f"finishReason={finish_reason}",
                        "auth_ok": True,
                    })
                    return incomplete_response_message

                if enable_google_search:
                    sources_md = _format_grounding_sources(result)
                    if sources_md:
                        text = text + "\n" + sources_md

                show_truncation_note = truncated and (
                    truncation_notice_mode != "never"
                    and (
                        truncation_notice_mode != "if_incomplete"
                        or _looks_incomplete_response(text)
                    )
                )
                if show_truncation_note:
                    note = truncation_message or (
                        "> ⚠️ **A válasz a modell kimeneti korlátjánál megszakadt.** "
                        "Kérlek, próbáld újra vagy bontsd kisebb részekre a kérést; "
                        "részletekért használd a **finomítás chatet**."
                    )
                    text = text + "\n\n---\n\n" + note

                _debug_log_append({
                    "ts": _now_str(), "tab": tab_label, "attempt": attempt + 1,
                    "status": status_label, "model": model,
                    "prompt_chars": prompt_chars, "response_chars": len(text),
                    "latency_ms": latency_ms,
                    "error_message": ("finishReason=MAX_TOKENS" if truncated else ""),
                    "auth_ok": True,
                })
                if cache_enabled and not truncated:
                    cache[prompt_hash] = (text, _time.time())
                return text
            except (KeyError, IndexError, ValueError):
                err_msg = _log_http_error(model, sc, response)
                _debug_log_append({
                    "ts": _now_str(), "tab": tab_label, "attempt": attempt + 1,
                    "status": "EMPTY_OR_BLOCKED", "model": model,
                    "prompt_chars": prompt_chars, "response_chars": 0,
                    "latency_ms": latency_ms,
                    "error_message": err_msg[:300],
                })
                try:
                    result = response.json()
                    feedback = result.get("promptFeedback", {})
                    block_reason = feedback.get("blockReason")
                    if block_reason:
                        return (
                            f"⚠️ **A modell biztonsági okból elutasította a kérést.** "
                            f"(`{block_reason}`)\n\nFogalmazd át a kérést, vagy módosíts a tartalmon."
                        )
                except Exception:
                    pass
                return (
                    "⚠️ **A válasz üres vagy értelmezhetetlen volt.** "
                    "Próbáld újra, vagy módosíts kissé a kérdésen."
                )

        # ─── 404 NotFound — nincs modellváltás, csak egyértelmű üzenet ───
        if sc == 404:
            err_msg = _log_http_error(model, sc, response)
            _debug_log_append({
                "ts": _now_str(), "tab": tab_label, "attempt": attempt + 1,
                "status": "404_NOT_FOUND", "model": model,
                "prompt_chars": prompt_chars, "response_chars": 0,
                "latency_ms": latency_ms,
                "error_message": err_msg[:300],
            })
            return (
                "⚠️ **A modellnév vagy API elérés hibás.**\n\n"
                f"**Részletek (Google):**\n```\n{err_msg}\n```"
            )

        # ─── 429 rate-limit → exponenciális backoff (Retry-After-aware) ─
        if sc == 429:
            err_msg = _log_http_error(model, sc, response)
            wait_s = _extract_retry_after_seconds(response, attempt, GEMINI_RATE_LIMIT_BASE_S)
            _debug_log_append({
                "ts": _now_str(), "tab": tab_label, "attempt": attempt + 1,
                "status": "429_RATE_LIMIT", "model": model,
                "prompt_chars": prompt_chars, "response_chars": 0,
                "latency_ms": latency_ms,
                "error_message": f"{err_msg} (wait={wait_s}s)"[:300],
            })
            if attempt < GEMINI_MAX_RETRIES - 1:
                _time.sleep(wait_s)
                continue

            # Free-tier konkrét detektálás: a Google a hibában maga jelzi,
            # hogy `generate_content_free_tier_requests` metrikát lépett túl
            # → a kulcs Google-oldalon még mindig free tier kvótán fut,
            # nem a billing-es paid tier-en (akkor is, ha a felhasználó a
            # Cloud Console-ban beállította a billinget).
            _free_tier = "free_tier" in (err_msg or "").lower()
            if _free_tier:
                _src = _api_key_source_label()
                _key_mask = _mask_api_key(_resolve_api_key())
                return (
                    "⚠️ **Túl sok kérés vagy quota limit. Próbáld újra később.**\n\n"
                    "**A Google a hibában `free_tier_requests` metrikát említ — "
                    "vagyis ez a kulcs Google-oldalon még mindig a `Free` szinten van, "
                    "NEM a fizetős (paid) szinten, hiába van billing a Cloud-projekthez kötve.**\n\n"
                    f"Aktív kulcs forrása: `{_src}` · maszk: `{_key_mask}`\n\n"
                    "**Mit tegyél (egyszer, 2–5 perc):**\n"
                    "1. Nyisd meg az AI Studio kulcsfelületét: "
                    "<https://aistudio.google.com/apikey> — a kulcs sorában szerepelnie kell, "
                    "hogy **Paid** (nem `Free of charge`). Ha még `Free`, kattints a kulcsra, "
                    "és kösd egy olyan **Cloud-projekthez**, amelynél aktív a billing.\n"
                    "2. Cloud Console → válaszd a projektet → **Billing → Link a billing account** "
                    "(ha még nincs összekötve), és győződj meg, hogy a számla **aktív**, nem `Closed`.\n"
                    "3. Cloud Console → **APIs & Services → Library → Generative Language API → Enable** "
                    "ugyanabban a projektben.\n"
                    "4. Várj 2–5 percet (Google-oldalon a tier-váltás nem azonnali), majd próbáld újra.\n"
                    "5. Ha 5 perc után is `free_tier_requests` jön: a legbiztosabb megoldás **új API "
                    "kulcsot generálni a Cloud Console-ban** (APIs & Services → Credentials → "
                    "Create credentials → API key), majd a `.streamlit/secrets.toml` `GEMINI_API_KEY` "
                    "értékét lecserélni rá. Az új kulcs **a billing-es projekttől örökli a paid tier kvótát**.\n\n"
                    f"**Részletek (Google):**\n```\n{err_msg}\n```"
                )
            return (
                "⚠️ **Túl sok kérés vagy quota limit. Próbáld újra később.**\n\n"
                f"**Részletek (Google):**\n```\n{err_msg}\n```"
            )

        # ─── 5xx szerver hiba → backoff retry ────────────────────────
        if sc >= 500:
            err_msg = _log_http_error(model, sc, response)
            _debug_log_append({
                "ts": _now_str(), "tab": tab_label, "attempt": attempt + 1,
                "status": f"{sc}_SERVER", "model": model,
                "prompt_chars": prompt_chars, "response_chars": 0,
                "latency_ms": latency_ms,
                "error_message": err_msg[:300],
            })
            if attempt < GEMINI_MAX_RETRIES - 1:
                _time.sleep(GEMINI_RETRY_BASE_S * (2 ** attempt))
                continue
            return (
                f"⚠️ **A Gemini szerver átmenetileg nem elérhető** (státusz: {sc}). "
                "Próbáld újra pár másodperc múlva.\n\n"
                f"**Google API üzenet:**\n```\n{err_msg}\n```"
            )

        # ─── Egyéb hibakódok (401/403/400/…) → azonnali ──────────────
        err_msg = _log_http_error(model, sc, response)
        _dbg_other = {
            "ts": _now_str(), "tab": tab_label, "attempt": attempt + 1,
            "status": f"{sc}_OTHER", "model": model,
            "prompt_chars": prompt_chars, "response_chars": 0,
            "latency_ms": latency_ms,
            "error_message": err_msg[:300],
        }
        if sc in (401, 403):
            _dbg_other["auth_ok"] = False
        _debug_log_append(_dbg_other)
        snippet = (response.text or "")[:400]

        if sc in (401, 403):
            return (
                "⚠️ **Érvénytelen vagy lejárt API kulcs (státusz: "
                f"{sc}).** Generálj újat a Google AI Studio-ban, és cseréld a Beállítások fülön.\n\n"
                f"**Google API üzenet:**\n```\n{err_msg}\n```"
            )
        if sc == 400:
            return (
                "⚠️ **A kérés hibás vagy elutasított.** A modell nem tudta feldolgozni "
                "a beküldött tartalmat (státusz: 400).\n\n"
                f"Részletek (rövidítve):\n```\n{snippet}\n```"
            )
        return f"⚠️ **Ismeretlen API válasz** (státusz: {sc}).\n\n```\n{snippet}\n```"

    return last_error_msg


# =========================================================
# CHAT FINOMÍTÓ
# =========================================================

def refinement_chat(title, result_key, chat_key):
    st.divider()
    st.subheader(f"💬 Finomítás: {title}")

    if not st.session_state.get(result_key):
        st.info("Előbb generálj tartalmat ehhez a részhez.")
        return

    for msg in st.session_state[chat_key]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_msg = st.chat_input(f"Kérdezz vagy kérj módosítást ehhez: {title}", key=f"chat_{chat_key}")

    if user_msg:
        st.session_state[chat_key].append({"role": "user", "content": user_msg})

        with st.chat_message("user"):
            st.markdown(user_msg)

        prompt = f"""
A TEXTUS homiletikai műhely egyik részét finomítjuk.

Szekció:
{title}

Jelenlegi tartalom:
{st.session_state[result_key]}

Felhasználói kérés:
{user_msg}

Feladat:
Válaszolj magyarul, teológiailag óvatosan, lelkipásztori szempontból használható módon.
Ne írj teljesen új prédikációt, csak ehhez a részhez kapcsolódj.
"""

        # Chat-finomítás: ne legyen cache (interaktív, mindig friss válasz)
        answer = generate_text(
            prompt,
            tab_label=f"chat: {title}",
            use_cache=False,
        )

        st.session_state[chat_key].append({"role": "assistant", "content": answer})

        with st.chat_message("assistant"):
            st.markdown(answer)


# =========================================================
# VISSZAJELZÉS (beépített űrlap)
# =========================================================

def _read_project_secret(key: str) -> str:
    """`.streamlit/secrets.toml` titok olvasása kulcs alapján."""
    p = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"
    if not p.is_file():
        return ""
    try:
        import tomllib
    except ImportError:
        return ""
    try:
        with p.open("rb") as f:
            data = tomllib.load(f)
        v = data.get(key)
        if v:
            return str(v).strip()
    except Exception:
        pass
    return ""


def _feedback_secret(key: str, default: str = "") -> str:
    env_val = (os.environ.get(key, "") or "").strip()
    if env_val:
        return env_val
    file_val = _read_project_secret(key)
    if file_val:
        return file_val
    try:
        sec_val = st.secrets.get(key, "")
        if sec_val:
            return str(sec_val).strip()
    except Exception:
        pass
    return default


def _send_feedback_smtp(name: str, email: str, category: str, message: str) -> tuple:
    import smtplib
    from email.mime.text import MIMEText

    smtp_user = _feedback_secret("FEEDBACK_SMTP_USER")
    smtp_pass = _feedback_secret("FEEDBACK_SMTP_PASSWORD")
    if not smtp_user or not smtp_pass:
        return False, ""

    smtp_host = _feedback_secret("FEEDBACK_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(_feedback_secret("FEEDBACK_SMTP_PORT", "587") or "587")
    to_email = _feedback_secret("FEEDBACK_TO_EMAIL", FEEDBACK_TO_EMAIL)

    body = (
        f"TEXTUS visszajelzés\n\n"
        f"Téma: {category}\n"
        f"Név: {name or '—'}\n"
        f"E-mail: {email or '—'}\n\n"
        f"Üzenet:\n{message}\n"
    )
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"TEXTUS visszajelzés: {category}"
    msg["From"] = smtp_user
    msg["To"] = to_email
    if email:
        msg["Reply-To"] = email

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [to_email], msg.as_string())
        return True, "Köszönjük! Visszajelzésed megérkezett — hamarosan elolvassuk."
    except Exception as exc:
        return False, f"E-mail küldési hiba: {exc}"


def _send_feedback_formsubmit(name: str, email: str, category: str, message: str) -> tuple:
    """Alapértelmezett kézbesítés: FormSubmit.co → FEEDBACK_TO_EMAIL postaláda."""
    to_email = _feedback_secret("FEEDBACK_TO_EMAIL", FEEDBACK_TO_EMAIL)
    headers = {
        "Accept": "application/json",
        "Referer": f"{APP_STREAMLIT_URL}/",
        "Origin": APP_STREAMLIT_URL,
        "User-Agent": f"{APP_NAME}-Feedback/{APP_VERSION}",
    }
    payload = {
        "name": name or "Névtelen látogató",
        "email": email or "",
        "message": (
            f"Téma: {category}\n"
            f"Név: {name or '—'}\n"
            f"Visszajelző e-mail: {email or '—'}\n\n"
            f"Üzenet:\n{message}"
        ),
        "_subject": f"TEXTUS visszajelzés: {category}",
        "_template": "table",
        "_captcha": "false",
    }
    try:
        resp = requests.post(
            f"https://formsubmit.co/ajax/{to_email}",
            data=payload,
            headers=headers,
            timeout=20,
        )
        try:
            data = resp.json()
        except ValueError:
            data = {}
        success = str(data.get("success", "")).lower() == "true"
        if success:
            return True, "Köszönjük! Visszajelzésed e-mailben megérkezett hozzánk."
        api_msg = (data.get("message") or "").strip()
        if "activation" in api_msg.lower() or "activate" in api_msg.lower():
            return False, (
                "Az e-mail küldés még aktiválásra vár. "
                f"Ellenőrizd a(z) {to_email} postaládát — a FormSubmit küldött egy "
                "„Activate Form” linket; egyszer rá kell kattintani, utána működni fog."
            )
        if api_msg:
            return False, f"Nem sikerült elküldeni: {api_msg}"
        return False, "Nem sikerült elküldeni a visszajelzést. Próbáld újra később."
    except Exception as exc:
        return False, f"Küldési hiba: {exc}"


def _send_feedback(name: str, email: str, category: str, message: str) -> tuple:
    web3_key = _feedback_secret("FEEDBACK_WEB3FORMS_ACCESS_KEY")
    if web3_key:
        try:
            resp = requests.post(
                "https://api.web3forms.com/submit",
                json={
                    "access_key": web3_key,
                    "subject": f"TEXTUS visszajelzés: {category}",
                    "from_name": APP_NAME,
                    "name": name or "Névtelen látogató",
                    "email": email or FEEDBACK_TO_EMAIL,
                    "message": f"Téma: {category}\n\n{message}",
                },
                timeout=20,
            )
            data = resp.json()
            if resp.ok and data.get("success"):
                return True, "Köszönjük! Visszajelzésed megérkezett — hamarosan elolvassuk."
            return False, data.get("message", "Nem sikerült elküldeni a visszajelzést.")
        except Exception as exc:
            return False, f"Küldési hiba: {exc}"

    webhook = _feedback_secret("FEEDBACK_WEBHOOK_URL")
    if webhook:
        try:
            resp = requests.post(
                webhook,
                json={
                    "name": name or "Névtelen látogató",
                    "email": email or "",
                    "category": category,
                    "message": message,
                    "_subject": f"TEXTUS visszajelzés: {category}",
                },
                headers={"Accept": "application/json"},
                timeout=20,
            )
            if resp.ok:
                return True, "Köszönjük! Visszajelzésed megérkezett — hamarosan elolvassuk."
            return False, "Nem sikerült elküldeni a visszajelzést."
        except Exception as exc:
            return False, f"Küldési hiba: {exc}"

    ok, msg = _send_feedback_smtp(name, email, category, message)
    if ok:
        return ok, msg

    ok, msg = _send_feedback_formsubmit(name, email, category, message)
    if ok:
        return ok, msg
    if msg and "aktiválás" in msg.lower():
        return False, msg

    return False, (
        f"Nem sikerült elküldeni e-mailben. Próbáld újra, vagy írj közvetlenül: {FEEDBACK_TO_EMAIL}"
        + (f"\n\n(Részlet: {msg})" if msg else "")
    )


def render_feedback_section() -> None:
    st.markdown(
        """
<div id="visszajelzes" class="feedback-wrap">
    <div class="feedback-header">
        <div class="ars-numeral">Visszajelzés</div>
        <div class="ars-station-title">Mondd el a tapasztalataidat</div>
        <div class="ars-station-text">
            Ötlet, hiba, dicséret — minden visszajelzés segít jobbá tenni a műhelyt.
            A kitöltött üzenet e-mailben érkezik meg: <strong>hoverzsolt@gmail.com</strong>.
        </div>
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("textus_feedback_form", clear_on_submit=True):
        col_name, col_email = st.columns(2)
        with col_name:
            fb_name = st.text_input("Név (opcionális)", placeholder="Hogyan szólíthatunk?")
        with col_email:
            fb_email = st.text_input("E-mail (opcionális)", placeholder="Ha választ szeretnél")
        fb_category = st.selectbox(
            "Téma",
            [
                "Tapasztalat / vélemény",
                "Ötlet javaslat",
                "Hiba / technikai",
                "Egyéb",
            ],
        )
        fb_message = st.text_area(
            "Üzeneted",
            placeholder="Írd le röviden, mi tetszett, mi nem, mit javítsunk…",
            height=140,
        )
        submitted = st.form_submit_button(
            "Visszajelzés küldése",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        msg_text = (fb_message or "").strip()
        if not msg_text:
            st.warning("Kérjük, írd meg az üzeneted.")
        elif len(msg_text) < 10:
            st.warning("Kérjük, írj legalább néhány mondatot — így jobban megérthetjük a véleményed.")
        else:
            last_sent = st.session_state.get("_feedback_last_sent")
            if last_sent and (datetime.now().timestamp() - last_sent) < 30:
                st.warning("Kérjük, várj pár másodpercet a következő üzenet küldése előtt.")
            else:
                ok, result_msg = _send_feedback(
                    (fb_name or "").strip(),
                    (fb_email or "").strip(),
                    fb_category,
                    msg_text,
                )
                if ok:
                    st.session_state["_feedback_last_sent"] = datetime.now().timestamp()
                    st.success(result_msg)
                else:
                    st.error(result_msg)


# =========================================================
# FEJLÉC
# =========================================================

if logo_file:
    logo_b64 = file_to_base64(logo_file)
    if logo_file.endswith(".png"):
        logo_mime = "image/png"
    elif logo_file.endswith(".webp"):
        logo_mime = "image/webp"
    elif logo_file.endswith(".svg"):
        logo_mime = "image/svg+xml"
    else:
        logo_mime = "image/jpeg"
    logo_html = f'<img src="data:{logo_mime};base64,{logo_b64}" class="main-logo" alt="{APP_NAME}" />'
else:
    logo_html = f'<div class="main-logo-fallback">{APP_NAME[0]}</div>'

st.markdown(
    f"""
<div class="main-card header-card">
    <div class="header-grid">
        <div class="header-logo">{logo_html}</div>
        <div class="header-text">
            <div class="main-title">{APP_NAME}</div>
            <div class="version-line">V{APP_VERSION}</div>
            <div class="header-caption">{APP_SUBTITLE}</div>
            <div class="header-tagline">{APP_TAGLINE}</div>
            <div class="subtitle">{APP_SCRIPTURE}</div>
            <div class="scripture-ref">{APP_SCRIPTURE_REF}</div>
        </div>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

if not background_file:
    st.warning("A háttérkép nem található. Neve legyen background.jpg, background.jpeg, background.png vagy background.webp, és ugyanabban a mappában legyen, mint az app.py.")

if not logo_file:
    st.info("Logó nem található. Neve legyen textus_logo.png, logo.png, logo.jpg vagy logo.webp, és ugyanabban a mappában legyen, mint az app.py.")

# Flash (mentés/megnyitás utáni üzenet — túléli az st.rerun()-t)
_render_flash_message()

# Állandó projekt-sáv (mentés / dirty / projektek) — a tabok előtt
_render_project_status_bar()


# =========================================================
# NÉZETVÁLTÓ (Gyorseszközök / Textusműhely) — M0 Lépés 3
# =========================================================

_TW_SECTION_OPTIONS = [
    "Igehely, alkalom és szövegkörnyezet",
    "Eredeti szöveg és kulcsszavak",
    "Exegézis, műfaj és szerkezet",
    "Kortörténeti háttér",
    "Teológiai hangsúlyok",
    "A textus nagy gondolata",
    "Mit viszünk tovább?",
]

_UI_MODE_LABELS = {
    "quick": "Gyorseszközök",
    "workshop": "Textusműhely",
}


def render_igehely_panel() -> None:
    """Igehely, alkalom, stílus, saját szempont + Áttekintés (bibliai háttér)."""
    st.header("Igeszakasz megadása")

    st.text_input(
        "Melyik igeszakaszt elemezzük?",
        placeholder="Pl. Jn 3,16–21",
        key="igehely_input",
    )

    col1, col2 = st.columns(2)

    with col1:
        st.selectbox(
            "Felhasználási cél",
            [
                "vasárnapi gyülekezeti igehirdetés",
                "ifjúsági alkalom",
                "bibliaóra",
                "temetés",
                "esküvő",
                "konferencia",
                "pasztorális beszélgetés",
            ],
            key="alkalom_input",
        )

    with col2:
        st.selectbox(
            "Homiletikai stílus",
            [
                "klasszikus református",
                "narratív",
                "tanító jellegű",
                "pasztorális",
                "ifjúsági",
                "storytelling",
                "induktív",
            ],
            key="stilus_input",
        )

    st.text_area(
        "Saját szempont vagy kérdés",
        placeholder="Pl. szeretném hangsúlyozni a kegyelem, hit vagy reménység témáját...",
        key="sajat_input",
    )

    if st.session_state.get("verse_history"):
        with st.expander("Korábbi igehelyek (utolsó 5)", expanded=False):
            for v_idx, v in enumerate(st.session_state["verse_history"][:5]):
                if st.button(f"📜 {v}", key=f"verse_hist_{v_idx}", use_container_width=True):
                    st.session_state["igehely_input"] = v
                    st.rerun()

    st.info(
        "**Tabonkénti generálás:** Itt csak az **Áttekintést** kéred le. "
        "A többi szekciót (Eredeti szöveg tanulmányozása, Exegézis, Kortörténet, Teológia, "
        "Illusztrációk, Aktualizálás, Vázlat, Énekajánló) az adott fülön, "
        "külön gombbal indíthatod — így pontosan azt generálod, amire szükséged van. "
        f"\n\n*Két API-hívás között legalább {GEMINI_COOLDOWN_S} másodperc vár; "
        "a válaszok tömör, strukturált, de a fontos információkat nem kihagyó prompttal készülnek.*"
    )

    overview_disabled = bool(st.session_state.get("_overview_running"))
    if st.button(
        "Bibliai háttér összegzése",
        type="primary",
        key="overview_generate_btn",
        disabled=overview_disabled,
    ):
        st.session_state["_overview_running"] = True
        try:
            if generate_section("overview"):
                st.success("Bibliai háttér elkészült.")
        finally:
            st.session_state["_overview_running"] = False

    if st.session_state.get("overview"):
        st.markdown('<div class="result-box">', unsafe_allow_html=True)
        st.markdown(st.session_state["overview"])
        st.markdown('</div>', unsafe_allow_html=True)

        col_regen_o, _ = st.columns([1, 4])
        with col_regen_o:
            if st.button("Bibliai háttér újragenerálása", key="overview_regen"):
                if generate_section("overview"):
                    st.rerun()


def render_original_text_panel() -> None:
    """Eredeti héber/görög szöveg tanulmányozása, jegyzet és vázlatkosár."""
    st.header("Eredeti szöveg tanulmányozása")
    st.caption("Héber / görög kulcskifejezések, jelentésárnyalatok és prédikációs hozam")

    # Az igeszakaszt az "Igehely" fülről örököljük — ugyanaz a forrás,
    # mint a többi szekciónál (Exegézis, Kortörténet stb.). Itt csak
    # olvasható kijelzést mutatunk; a változtatás az "Igehely" fülön
    # történik, és a `_sync_inputs_to_last()` szinkronizálja minden
    # generálás-gombnyomáskor.
    _igehely_orig = (
        (st.session_state.get("igehely_input") or "").strip()
        or (st.session_state.get("last_igehely") or "").strip()
    )
    if _igehely_orig:
        st.markdown(
            f"**Igeszakasz** *(az „Igehely” fülről):* `{_igehely_orig}`"
        )
    else:
        st.info(
            "Add meg az igeszakaszt az **Igehely** fülön — innen "
            "automatikusan átvesszük."
        )

    _orig_running = bool(st.session_state.get("_original_running"))
    if st.button(
        "Eredeti szöveg tanulmányozása",
        type="primary",
        key="original_run",
        disabled=_orig_running,
    ):
        _sync_inputs_to_last()
        _igehely_now = (st.session_state.get("last_igehely") or "").strip()
        if not _resolve_api_key().strip():
            st.warning("Először add meg az API kulcsot a Beállítások fülön.")
        elif not _igehely_now:
            st.warning("Add meg az igeszakaszt az „Igehely” fülön, mielőtt itt generálsz.")
        else:
            st.session_state["_original_running"] = True
            try:
                with st.spinner("Eredeti nyelvi elemzés készül..."):
                    st.session_state["original_text"] = generate_text(
                        build_original_text_prompt(_igehely_now),
                        tab_label="Eredeti szöveg tanulmányozása",
                        use_cache=False,
                        system_bundle=KEY_EXPRESSIONS_SYSTEM_PROMPT,
                        include_brevity_directive=False,
                        truncation_notice_mode="never",
                        incomplete_response_message=(
                            "⚠️ **Az eredeti nyelvi elemzés nem érkezett meg teljesen.** "
                            "Nem jelenítek meg félbeszakadt szöveget. Kérlek, próbáld újra."
                        ),
                    )
            finally:
                st.session_state["_original_running"] = False
            st.rerun()

    if st.session_state.get("original_text"):
        if st.session_state["original_text"].startswith(("⚠️", "⏳")):
            st.warning(st.session_state["original_text"])
        else:
            st.markdown(
                '<div class="result-box original-text-result">',
                unsafe_allow_html=True
            )
            st.markdown(st.session_state["original_text"])
            st.markdown('</div>', unsafe_allow_html=True)

    else:
        st.info("Még nincs eredeti nyelvi elemzés.")

    refinement_chat("Eredeti szöveg tanulmányozása", "original_text", "original_text_chat")

    _maybe_clear_note("original_note")
    note = st.text_area(
        "Mit szeretnél ebből megtartani a vázlathoz?",
        key="original_note"
    )

    if st.button("Hozzáadás a vázlatkosárhoz", key="original_add"):
        if note.strip():
            st.session_state["basket"].append(("Eredeti szöveg tanulmányozása", note.strip()))
            _request_clear_note("original_note")
            st.success("Hozzáadva.")
            st.rerun()


def render_textus_workshop_shell() -> None:
    """Textusműhely-keret: Igehely + Eredeti szöveg panelek; többi helyőrző."""
    st.header("Textusműhely")
    st.caption("A bibliai szöveg megértésétől a továbbvihető felismerésekig.")

    if st.session_state.get("tw_active_section") not in _TW_SECTION_OPTIONS:
        st.session_state["tw_active_section"] = _TW_SECTION_OPTIONS[0]

    st.radio(
        "Aktív szakasz",
        options=_TW_SECTION_OPTIONS,
        key="tw_active_section",
    )

    active = st.session_state.get("tw_active_section") or _TW_SECTION_OPTIONS[0]
    st.subheader(active)

    if active == "Igehely, alkalom és szövegkörnyezet":
        render_igehely_panel()
    elif active == "Eredeti szöveg és kulcsszavak":
        render_original_text_panel()
    else:
        st.info(
            "Ez a műhelyszakasz a következő fejlesztési lépésben kapcsolódik "
            "a meglévő Textus-funkcióhoz."
        )


if st.session_state.get("ui_mode") not in ("quick", "workshop"):
    st.session_state["ui_mode"] = "quick"

st.radio(
    "Nézet",
    options=["quick", "workshop"],
    format_func=lambda m: _UI_MODE_LABELS.get(m, m),
    horizontal=True,
    key="ui_mode",
)

# Textusműhely: csak a műhelykeret; a régi 13 fül ne jöjjön létre
if st.session_state.get("ui_mode") == "workshop":
    render_textus_workshop_shell()
    st.stop()


# =========================================================
# TABOK (Gyorseszközök mód)
# =========================================================

# Felhőprojekt megnyitás után: widget-szinkron a tabok létrehozása előtt
_apply_pending_project_widget_sync()

tabs = st.tabs([
    "Igehely",
    "Eredeti szöveg tanulmányozása",
    "Exegézis",
    "Kortörténet",
    "Teológia",
    "Illusztrációk",
    "Aktualizálás",
    "Vázlat",
    "Vázlatkosár",
    "Énekajánló",
    "📅 Igehirdetési sorozat tervező",
    "📖 Útmutatás",
    "⚙️ Beállítások",
])


# =========================================================
# IGEHELY (Gyorseszközök — ugyanaz a panel, mint a Textusműhelyben)
# =========================================================

with tabs[0]:
    render_igehely_panel()


# =========================================================
# TARTALOM TABOK — egységes Generálás-gombos minta
# =========================================================

with tabs[2]:
    render_section_tab(
        key="exegesis",
        header="Exegézis",
        basket_label="Exegézis",
        empty_msg="Még nincs exegézis. Kattints az „Exegetikai háttér feltárása” gombra.",
        action_label="Exegetikai háttér feltárása",
    )

with tabs[3]:
    render_section_tab(
        key="history",
        header="Kortörténet",
        basket_label="Kortörténet",
        empty_msg="Még nincs kortörténeti háttér. Kattints a „Kortörténeti háttér feltárása” gombra.",
        action_label="Kortörténeti háttér feltárása",
    )

with tabs[4]:
    render_section_tab(
        key="theology",
        header="Teológia",
        basket_label="Teológia",
        empty_msg="Még nincs teológiai elemzés. Kattints a „Teológiai összefüggések feltárása” gombra.",
        action_label="Teológiai összefüggések feltárása",
    )

with tabs[5]:
    render_section_tab(
        key="illustrations",
        header="Illusztrációk",
        basket_label="Illusztráció",
        empty_msg="Még nincsenek illusztrációs ötletek. Kattints az „Illusztrációs ötletek gyűjtése” gombra.",
        action_label="Illusztrációs ötletek gyűjtése",
    )

with tabs[6]:
    render_section_tab(
        key="actualization",
        header="Aktualizálás",
        basket_label="Aktualizálás",
        empty_msg="Még nincs aktualizálás. Kattints a „Mai kapcsolódások keresése” gombra (Google-keresés használatával friss kontextust kap).",
        action_label="Mai kapcsolódások keresése",
    )


# =========================================================
# VÁZLAT
# =========================================================

with tabs[7]:
    st.header("Prédikációvázlat")

    if st.session_state.pop("_clear_outline_workshop_editors", False):
        st.session_state["_outline_draft_editor"] = ""
        st.session_state["_outline_answers_editor"] = ""
        st.session_state["_outline_reworked_editor"] = ""
        st.session_state.pop("_pending_outline_draft_editor", None)

    homiletikai_modell = st.selectbox(
        "Homiletikai modell",
        [
            "klasszikus hárompontos református",
            "narratív prédikáció",
            "induktív modell",
            "probléma–megoldás modell",
            "egy főgondolatra épülő modell",
            "10 pontos tanító vázlat"
        ]
    )

    # Régebbi munkamenetnél a korábban generált vázlatot induló vázlatként
    # tesszük szerkeszthetővé, de csak akkor, ha még nincs külön műhely-vázlat.
    if st.session_state.get("outline") and not st.session_state.get("outline_draft"):
        st.session_state["outline_draft"] = st.session_state["outline"]

    if "_pending_outline_draft_editor" in st.session_state:
        st.session_state["_outline_draft_editor"] = st.session_state.pop("_pending_outline_draft_editor")
    elif "_outline_draft_editor" not in st.session_state:
        st.session_state["_outline_draft_editor"] = st.session_state.get("outline_draft", "")

    if "_outline_reworked_editor" not in st.session_state:
        st.session_state["_outline_reworked_editor"] = st.session_state.get("outline_reworked_draft", "")

    if "_outline_answers_editor" not in st.session_state:
        st.session_state["_outline_answers_editor"] = st.session_state.get("outline_workshop_answers", "")

    _outline_running = bool(st.session_state.get("_outline_running"))
    if st.button(
        "Szerkeszthető vázlat készítése",
        type="primary",
        disabled=_outline_running,
        key="outline_run",
    ):
        basket_text = "\n".join([f"- {source}: {text}" for source, text in st.session_state["basket"]])

        prompt = f"""
# VÁZLAT — KOHERENS PRÉDIKÁCIÓS STRUKTÚRA

Szakmai vízió:
Készíts **szerkeszthető homiletikai vázlatot**, nem végleges prédikációt.
Rendezd össze az eddigi fülekből és a vázlatkosárból származó gondolatokat
egy **koherens prédikációs struktúrává**. Ne írj kimondásra kész prédikációs
mondatokat; ne úgy fogalmazz, mintha már maga az igehirdetés szólalna meg.

A cél: jól felépített, áttekinthető, tovább szerkeszthető vázlat,
amely segíti a lelkipásztort a saját igehirdetése megformálásában.

Homiletikai modell:
{homiletikai_modell}

Az eddigi elemzések, amelyekből építkezz:

## Áttekintés
{st.session_state["overview"]}

## Exegézis
{st.session_state["exegesis"]}

## Kortörténet
{st.session_state["history"]}

## Teológia
{st.session_state["theology"]}

## Illusztrációk
{st.session_state["illustrations"]}

## Aktualizálás
{st.session_state["actualization"]}

## A vázlatba feltétlenül beépítendő, megőrzött gondolatok
{basket_text if basket_text else "Nincs külön elem."}

A vázlat legyen lelkipásztori használatra alkalmas, de NE legyen teljes prédikáció.
Ne adj kész bevezető-, átvezető- vagy zárómondatokat. Inkább irányokat,
logikai kapcsolódásokat, hangsúlyokat és szerkezeti pontokat adj.
Hagyj benne olyan elemeket is, amelyeket a lelkipásztor tovább tud gondolni.

A vázlatot pontosan az alábbi szerkezetben add (Markdown formátum):

## Tételmondat (scopus)
A prédikáció gerince egyetlen világos, teológiailag tartós állításban.

## Az ív — diagnózis → evangéliumi fordulat → Isten válasza
Mutasd meg, milyen **mozgás** rendezheti a vázlatot: honnan indul, hol van
az **evangéliumi fordulat**, és hová érkezik meg a textus alapján.

## Szerkezet
A választott modell szerint **2–4 pontos vázlat**, mindegyik ponthoz:
- pont címe (rövid, hangsúlyos),
- rövid magyarázat arról, mit rendez ez a pont,
- konkrét textuális vagy teológiai horgony.

## Átvezetési logika
Ne kész mondatokat írj, hanem jelezd, hogyan kapcsolódnak egymáshoz a pontok.

## Bevezetési irány
Adj egy lehetséges nyitási irányt: kép, kérdés, élethelyzet vagy feszültség,
de ne fogalmazd meg kész prédikációs szövegként.

## Lezárási irány
Jelezd, milyen lelki vagy teológiai irányba fusson ki a vázlat; ne írj kész záróbeszédet.

## Alkalmazási pontok
2–3 konkrét, gyülekezeti életbe illesztett **alkalmazási irány**.
"""

        st.session_state["_outline_running"] = True
        try:
            with st.spinner("Szerkeszthető vázlat készül..."):
                draft = generate_text(
                    prompt,
                    tab_label="Vázlat",
                )
                st.session_state["outline_draft"] = draft
                st.session_state["_outline_draft_editor"] = draft
                st.session_state["outline_workshop_questions"] = ""
                st.session_state["outline_workshop_answers"] = ""
                st.session_state["_outline_answers_editor"] = ""
                st.session_state["outline_reworked_draft"] = ""
                st.session_state["_outline_reworked_editor"] = ""
                st.session_state["outline"] = ""
                st.session_state["outline_title_suggestions"] = ""
        finally:
            st.session_state["_outline_running"] = False
        st.rerun()

    st.subheader("1. Szerkeszthető fő vázlat")
    st.caption(
        "Ez a fő műhelymező. A későbbi „Végleges vázlat készítése” mindig "
        "ennek az aktuális tartalmából dolgozik."
    )
    outline_draft_current = st.text_area(
        "Fő vázlat",
        key="_outline_draft_editor",
        height=420,
        placeholder=(
            "Írj vagy generálj egy első homiletikai vázlatot. "
            "Ide kerülhet a tételmondat, az ív, a fő pontok, átvezetések, "
            "képek, alkalmazási irányok."
        ),
    )
    st.session_state["outline_draft"] = outline_draft_current

    has_draft = bool(outline_draft_current.strip())

    st.divider()
    st.subheader("2. Iteratív homiletikai műhely")
    st.caption(
        "A kérdések nem kerülnek bele automatikusan a vázlatba. Előbb válaszolsz "
        "rájuk, majd külön kérheted az átdolgozást."
    )

    question_running = bool(st.session_state.get("_outline_questions_running"))
    if st.button(
        "Segíts továbbgondolni",
        key="outline_questions_btn",
        disabled=question_running or not has_draft,
    ):
        question_prompt = f"""
Egy prédikációs vázlatot műhelyezünk. Ne írd át a vázlatot.
Csak tegyél fel **pontosan 4** egyszerű, gondolkodtató kérdést.

A kérdések célja brainstorming: segítsék a lelkipásztort abban, hogy
észrevegye, mit szeretne még jobban kiemelni, elmélyíteni vagy személyesebbé
tenni a vázlatban és később az igehirdetésben.

Jelenlegi fő vázlat:
{outline_draft_current}

Kérdésirányok:
- Mit emelne ki a lelkipásztor leginkább ebből az igéből?
- Melyik pontot lenne érdemes még elmélyíteni vagy konkrétabbá tenni?
- Milyen kérdés, kép, tapasztalat vagy gyülekezeti helyzet kapcsolódhat ehhez?
- Mi hiányzik még ahhoz, hogy a vázlat élőbb, személyesebb és prédikálhatóbb legyen?

Válaszformátum:
Csak **4 számozott kérdés** legyen, magyarul.
Ne adj tanácsot, ne írj új vázlatot, ne fűzz hosszú magyarázatot.
A kérdések legyenek közérthetőek, természetesek, nem túlbonyolított teológiai kérdések.
"""
        st.session_state["_outline_questions_running"] = True
        try:
            with st.spinner("Tisztázó kérdések készülnek..."):
                st.session_state["outline_workshop_questions"] = generate_text(
                    question_prompt,
                    tab_label="Vázlat",
                    use_cache=False,
                )
        finally:
            st.session_state["_outline_questions_running"] = False
        st.rerun()

    if not has_draft:
        st.info("Előbb írj vagy generálj egy fő vázlatot.")

    if st.session_state.get("outline_workshop_questions"):
        st.markdown("#### Tisztázó kérdések")
        st.markdown('<div class="result-box">', unsafe_allow_html=True)
        st.markdown(st.session_state["outline_workshop_questions"])
        st.markdown('</div>', unsafe_allow_html=True)

    answers_current = st.text_area(
        "Válaszaid, új hangsúlyok, pontosítások, személyes megfigyelések",
        key="_outline_answers_editor",
        height=220,
        placeholder=(
            "Válaszolj a kérdésekre, vagy írd le, milyen hangsúlyt, személyes "
            "megfigyelést, gyülekezeti helyzetet, textuális pontosítást szeretnél "
            "beépíteni az átdolgozásba."
        ),
    )
    st.session_state["outline_workshop_answers"] = answers_current

    rework_running = bool(st.session_state.get("_outline_rework_running"))
    if st.button(
        "Vázlat átdolgozása a válaszok alapján",
        key="outline_rework_btn",
        disabled=rework_running or not has_draft or not answers_current.strip(),
    ):
        rework_prompt = f"""
Egy prédikációs vázlatot kell **valóban átszerkesztened** a lelkipásztor
válaszai és új hangsúlyai alapján.

Fontos:
- NE másold be a válaszokat a vázlat végére.
- NE csak függeléket írj.
- Szerkeszd át a teljes vázlatot úgy, hogy a válaszokból származó hangsúlyok
  szervesen beépüljenek.
- Tartsd meg a felhasználó saját gondolatait, hangját és eredeti jó meglátásait.
- Pontosítsd a fő üzenetet (scopus).
- Rendezd a szerkezetet.
- Javítsd az átvezetéseket.
- Szűrd ki a túl általános, moralizáló vagy textustól elszakadó részeket.
- Ne készíts teljes prédikációt; maradjon műhelyben tovább szerkeszthető vázlat.
- Ne adj kimondásra kész prédikációs mondatokat; a szöveg maradjon vázlat,
  nem elmondandó igehirdetés.

Aktuális fő vázlat:
{outline_draft_current}

AI által korábban feltett tisztázó kérdések:
{st.session_state.get("outline_workshop_questions", "").strip() or "Nincs külön kérdéslista."}

Felhasználói válaszok, hangsúlyok, pontosítások:
{answers_current}

Kimenet:
Adj egy **átdolgozott, egységes prédikációs vázlatot** Markdown formátumban.
Ne írj meta-kommentárt arról, mit változtattál; csak az átdolgozott vázlatot add.
"""
        st.session_state["_outline_rework_running"] = True
        try:
            with st.spinner("A vázlat átdolgozása folyamatban..."):
                reworked = generate_text(
                    rework_prompt,
                    tab_label="Vázlat",
                    use_cache=False,
                )
                st.session_state["outline_reworked_draft"] = reworked
                st.session_state["_outline_reworked_editor"] = reworked
        finally:
            st.session_state["_outline_rework_running"] = False
        st.rerun()

    if st.session_state.get("outline_reworked_draft"):
        st.markdown("#### Átdolgozott vázlat")
        reworked_current = st.text_area(
            "Átdolgozott vázlat (szerkeszthető)",
            key="_outline_reworked_editor",
            height=420,
        )
        st.session_state["outline_reworked_draft"] = reworked_current

        if st.button(
            "Átdolgozott vázlat használata",
            key="outline_accept_reworked_btn",
            disabled=not reworked_current.strip(),
        ):
            st.session_state["outline_draft"] = reworked_current
            st.session_state["_pending_outline_draft_editor"] = reworked_current
            st.success("Az átdolgozott vázlat lett a fő vázlat.")
            st.rerun()

    st.divider()
    st.subheader("3. Végleges vázlat")
    final_running = bool(st.session_state.get("_outline_final_running"))
    if st.button(
        "Végleges vázlat készítése",
        type="primary",
        key="outline_final_btn",
        disabled=final_running or not has_draft,
    ):
        basket_text_final = "\n".join(
            f"- {source}: {text}"
            for source, text in st.session_state["basket"]
        ) or "Nincs külön elem."

        final_prompt = f"""
Készíts végleges, lelkipásztori használatra alkalmas **prédikációvázlatot**.
Ez ne legyen kimondásra kész prédikációszöveg: ne adj elmondandó mondatokat,
ne írj kész bevezetést, átvezetést vagy záróbeszédet.

A feladatod: strukturáld össze az összes eddig generált fül gondolatait,
a vázlatkosár megtartott elemeit, valamint a Vázlat fülön született
finomításokat egy szépen felépített, de nem túl bőbeszédű vázlattá.

Nagyon fontos:
- Ne írj kész prédikációt.
- Ne adj címjavaslatokat; ez külön gombbal készül.
- Ne másold be a kérdéseket vagy válaszokat függelékként.
- A finomításokból származó hangsúlyokat szervesen építsd be a vázlatba.
- Tartsd meg a felhasználó saját gondolatait és jó meglátásait.
- Szűrd ki a túl általános, moralizáló vagy textustól elszakadó részeket.

Homiletikai modell:
{homiletikai_modell}

Az eddigi fülek anyaga:

## Áttekintés
{st.session_state["overview"]}

## Eredeti szöveg tanulmányozása
{st.session_state["original_text"]}

## Exegézis
{st.session_state["exegesis"]}

## Kortörténet
{st.session_state["history"]}

## Teológia
{st.session_state["theology"]}

## Illusztrációk
{st.session_state["illustrations"]}

## Aktualizálás
{st.session_state["actualization"]}

## Énekajánló
{st.session_state["songs"]}

## Vázlatkosár megtartott gondolatai
{basket_text_final}

Aktuális fő vázlat:
{outline_draft_current}

Vázlat műhely-kérdések:
{st.session_state.get("outline_workshop_questions", "").strip() or "Nincs külön kérdéslista."}

Felhasználói válaszok és finomítások:
{st.session_state.get("outline_workshop_answers", "").strip() or "Nincs külön válasz."}

Átdolgozott vázlat, ha készült:
{st.session_state.get("outline_reworked_draft", "").strip() or "Nincs külön átdolgozott változat."}

A végleges vázlatot pontosan az alábbi szerkezetben add (Markdown formátum):

## Tételmondat (scopus)
Egyetlen, lényegre törő, teológiailag tartós állítás — a vázlat gerince.

## Az ív — diagnózis → evangéliumi fordulat → Isten válasza
Mutasd meg, milyen logikai és teológiai mozgás rendezze a prédikációt:
honnan indul, hol van az evangéliumi fordulat, és hová érkezik.

## Szerkezet
A választott modell szerint **2–4 pontos vázlat**, mindegyik ponthoz:
- pont címe (rövid, hangsúlyos),
- rövid magyarázat arról, mit rendez ez a pont,
- konkrét textuális vagy teológiai horgony.

## Átvezetési logika
Ne kész átvezető mondatokat írj, hanem jelezd, hogyan kapcsolódnak a pontok.

## Bevezetési irány
Lehetséges nyitási irány: kép, kérdés, élethelyzet vagy feszültség.
Ne fogalmazd meg kész prédikációs szövegként.

## Lezárási irány
Jelezd, milyen lelki vagy teológiai irányba fusson ki a vázlat.
Ne írj kész záróbeszédet.

## Alkalmazási pontok
2–3 konkrét, gyülekezeti életbe illesztett **alkalmazási irány**.
"""
        st.session_state["_outline_final_running"] = True
        try:
            with st.spinner("Végleges vázlat készül az aktuális fő vázlatból..."):
                st.session_state["outline"] = generate_text(
                    final_prompt,
                    tab_label="Vázlat",
                    use_cache=False,
                )
                st.session_state["outline_title_suggestions"] = ""
        finally:
            st.session_state["_outline_final_running"] = False
        st.rerun()

    if st.session_state["outline"]:
        st.markdown("#### Végleges vázlat")
        st.markdown('<div class="result-box">', unsafe_allow_html=True)
        st.markdown(st.session_state["outline"])
        st.markdown('</div>', unsafe_allow_html=True)

        title_running = bool(st.session_state.get("_outline_titles_running"))
        if st.button(
            "Címjavaslatok",
            key="outline_title_suggestions_btn",
            disabled=title_running,
        ):
            title_prompt = f"""
Az alábbi prédikációvázlathoz adj **3–5 címjavaslatot**.

Fontos:
- Ne írj új vázlatot.
- Ne bővítsd az igehirdetést.
- Csak címeket adj, mindegyikhez legfeljebb egy rövid indoklással.
- A címek legyenek beszédesek, igehirdetéshez használhatók, de ne hatásvadászok.
- Legyen köztük visszafogottabb, biblikusabb és képszerűbb lehetőség is.

Igeszakasz:
{st.session_state.get("last_igehely", "")}

Végleges vázlat:
{st.session_state["outline"]}

Válaszformátum:
## Címjavaslatok
1. **Cím** — rövid indoklás.
2. **Cím** — rövid indoklás.
"""
            st.session_state["_outline_titles_running"] = True
            try:
                with st.spinner("Címjavaslatok készülnek..."):
                    st.session_state["outline_title_suggestions"] = generate_text(
                        title_prompt,
                        tab_label="Vázlat",
                        use_cache=False,
                    )
            finally:
                st.session_state["_outline_titles_running"] = False
            st.rerun()

        if st.session_state.get("outline_title_suggestions"):
            if st.session_state["outline_title_suggestions"].startswith(("⚠️", "⏳")):
                st.warning(st.session_state["outline_title_suggestions"])
            else:
                st.markdown('<div class="result-box">', unsafe_allow_html=True)
                st.markdown(st.session_state["outline_title_suggestions"])
                st.markdown('</div>', unsafe_allow_html=True)

        st.divider()
        st.subheader("Letöltés és megosztás")
        st.caption(
            "A vázlat, a vázlatkosár tartalma és (ha van) az énekajánlás "
            "**Word (.docx)** formátumban tölthető le — címsor-stílusokkal, "
            "kiemelt igehellyel, tagolt listákkal, UTF-8 ékezetekkel; "
            "Word/LibreOffice-ban azonnal megnyitható, nyomtatható vagy telefonra küldhető."
        )

        _verse_clean = (st.session_state.get("last_igehely") or "vazlat").replace(" ", "_").replace("/", "-").replace(",", "").replace(":", "-")
        _ts = datetime.now().strftime("%Y%m%d-%H%M")
        _filename_docx = f"textus-vazlat-{_verse_clean}-{_ts}.docx"

        try:
            _docx_bytes = build_outline_docx()
            st.download_button(
                label="Vázlat letöltése (Word)",
                data=_docx_bytes,
                file_name=_filename_docx,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=False,
                key="outline_download_docx",
                type="primary",
            )
        except ImportError:
            import sys as _sys
            _py = _sys.executable or "python"
            st.error(
                "**Word export nem érhető el** — a `python-docx` csomag nincs telepítve "
                "abba a Python környezetbe, amit ez a Streamlit alkalmazás használ.\n\n"
                "**Gyors megoldás (másold be PowerShell / cmd ablakba):**\n\n"
                f"```powershell\n\"{_py}\" -m pip install python-docx\n```\n\n"
                "Majd **állítsd le a Streamlit-et** (Ctrl+C a terminálban) és indítsd újra:\n\n"
                "```powershell\nstreamlit run app.py\n```\n\n"
                f"_(Aktív Python: `{_py}`)_"
            )
    else:
        st.info("Még nincs végleges vázlat. A véglegesítés mindig a fenti fő vázlat aktuális tartalmából készül.")


# =========================================================
# VÁZLATKOSÁR
# =========================================================

with tabs[8]:
    st.header("Vázlatkosár")
    st.caption(f"{len(st.session_state['basket'])} elem · szerkeszthető, törölhető, sorrendezhető")

    if not st.session_state["basket"]:
        st.info("Még nincs elmentett elem. A tartalom-fülek alján a „Hozzáadás a vázlatkosárhoz” gombbal tudsz hozzáadni.")

    for idx, (source, item) in enumerate(st.session_state["basket"]):
        st.markdown(
            f'<div class="basket-box"><b>{source}</b></div>',
            unsafe_allow_html=True
        )

        edited = st.text_area(
            "Tartalom",
            value=item,
            key=f"basket_edit_{idx}",
            height=140,
            label_visibility="collapsed"
        )

        c1, c2, c3, c4 = st.columns([1, 1, 1, 4])
        with c1:
            if st.button("Mentés", key=f"basket_save_{idx}"):
                st.session_state["basket"][idx] = (source, edited.strip())
                st.success("Frissítve.")
                st.rerun()
        with c2:
            if idx > 0 and st.button("↑", key=f"basket_up_{idx}", help="Feljebb"):
                st.session_state["basket"][idx - 1], st.session_state["basket"][idx] = (
                    st.session_state["basket"][idx],
                    st.session_state["basket"][idx - 1],
                )
                st.rerun()
        with c3:
            if idx < len(st.session_state["basket"]) - 1 and st.button("↓", key=f"basket_down_{idx}", help="Lejjebb"):
                st.session_state["basket"][idx + 1], st.session_state["basket"][idx] = (
                    st.session_state["basket"][idx],
                    st.session_state["basket"][idx + 1],
                )
                st.rerun()
        with c4:
            st.markdown('<div class="btn-danger-marker"></div>', unsafe_allow_html=True)
            if st.button(f"Törlés", key=f"delete_{idx}"):
                st.session_state["basket"].pop(idx)
                st.rerun()

        st.markdown("<hr style='opacity:0.3; margin:1.2rem 0;' />", unsafe_allow_html=True)

    if st.session_state["basket"]:
        st.markdown('<div class="btn-danger-marker"></div>', unsafe_allow_html=True)
        if st.button("Kosár ürítése"):
            st.session_state["basket"] = []
            st.rerun()


# =========================================================
# EREDETI SZÖVEG (Gyorseszközök — ugyanaz a panel, mint a Textusműhelyben)
# =========================================================

with tabs[1]:
    render_original_text_panel()


# =========================================================
# ÉNEKAJÁNLÓ
# =========================================================

with tabs[9]:
    st.header("Énekajánló")
    st.caption("Református liturgiai énekajánlás az igeszakaszhoz és az alkalomhoz")

    igehely_song = st.text_input(
        "Igeszakasz",
        placeholder="Pl. Lk 15,11–32 vagy Zsolt 23",
        key="songs_verse"
    )

    alkalom_song = st.selectbox(
        "Alkalom",
        [
            "Vasárnapi istentisztelet",
            "Úrvacsorás istentisztelet",
            "Adventi istentisztelet",
            "Karácsonyi istentisztelet",
            "Nagyhét",
            "Nagypénteki istentisztelet",
            "Húsvéti istentisztelet",
            "Pünkösdi istentisztelet",
            "Reformáció ünnepe",
            "Új kenyér / Új bor",
            "Aratás / Hálaadás",
            "Konfirmáció",
            "Keresztelő",
            "Esküvő",
            "Temetés",
            "Bűnbánati istentisztelet",
            "Hétközi alkalom / Bibliaóra",
            "Ifjúsági istentisztelet",
            "Egyéb"
        ],
        key="songs_occasion"
    )

    hangsuly_song = st.text_area(
        "Prédikációs / teológiai hangsúly (opcionális)",
        placeholder="Pl. „a hazatérő gyermek és az atyai irgalom” — vagy hagyd üresen.",
        key="songs_focus",
        height=110
    )

    enekeskonyv_song = st.selectbox(
        "Elsődleges énekeskönyv",
        [
            "Vegyesen — magyar református hagyomány",
            "Református Énekeskönyv (1948)",
            "Református Énekeskönyv (2021)",
            "Erdélyi Református Énekeskönyv"
        ],
        key="songs_book"
    )

    _songs_running = bool(st.session_state.get("_songs_running"))
    if st.button(
        "Énekek ajánlása",
        type="primary",
        key="songs_run",
        disabled=_songs_running,
    ):
        if not _resolve_api_key().strip():
            st.warning("Először add meg az API kulcsot a Beállítások fülön.")
        elif not igehely_song.strip():
            st.warning("Add meg az igeszakaszt.")
        else:
            st.session_state["_songs_running"] = True
            try:
                with st.spinner("Református énekek keresése a liturgiai ívhez..."):
                    st.session_state["songs"] = generate_text(
                        build_songs_prompt(
                            igehely=igehely_song,
                            alkalom=alkalom_song,
                            enekeskonyv=enekeskonyv_song,
                            hangsuly=hangsuly_song,
                        ),
                        tab_label="Énekajánló",
                    )
            finally:
                st.session_state["_songs_running"] = False
            st.rerun()

    if st.session_state.get("songs"):
        st.markdown(
            '<div class="result-box songs-result">',
            unsafe_allow_html=True
        )
        st.markdown(st.session_state["songs"])
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("Még nincs énekajánlás. Add meg az igeszakaszt és az alkalmat, majd kérj ajánlást.")

    refinement_chat("Énekajánló", "songs", "songs_chat")

    _maybe_clear_note("songs_note")
    note = st.text_area(
        "Mit szeretnél ebből megtartani a vázlathoz?",
        key="songs_note"
    )

    if st.button("Hozzáadás a vázlatkosárhoz", key="songs_add"):
        if note.strip():
            st.session_state["basket"].append(("Énekajánló", note.strip()))
            _request_clear_note("songs_note")
            st.success("Hozzáadva.")
            st.rerun()


# =========================================================
# BEÁLLÍTÁSOK
# =========================================================

with tabs[12]:
    st.header("⚙️ Beállítások")

    # ─── 0) Opcionális Google-bejelentkezés (nem kapu — vendégként is teljes app) ──
    st.subheader("Fiók")
    if _is_logged_in():
        try:
            _auth_name = (st.user.get("name") or "").strip()
            _auth_email = (st.user.get("email") or "").strip()
        except Exception:
            _auth_name, _auth_email = "", ""
        _auth_label = _auth_name or _auth_email or "Bejelentkezett felhasználó"
        st.caption(f"Bejelentkezve: {_auth_label}")
        if st.button("Kijelentkezés", key="settings_google_logout"):
            if _is_project_dirty():
                st.session_state["project_logout_confirm"] = True
                st.session_state["project_new_work_confirm"] = False
                st.session_state["project_open_confirm_id"] = None
                st.rerun()
            else:
                st.logout()
        if st.session_state.get("project_logout_confirm"):
            st.caption(
                "A kijelentkezés megerősítése a lap tetején, a Projekt sávnál jelenik meg."
            )
    elif not _auth_secrets_configured():
        st.info(
            "A Google-bejelentkezéshez add meg az `[auth]` beállításokat a Streamlit Cloud "
            "**Secrets** felületén (`client_id`, `client_secret`, `cookie_secret`, "
            "`redirect_uri` = `https://textus.streamlit.app/oauth2callback`). "
            "Vendégként az app továbbra is használható."
        )
    else:
        st.caption(
            "A bejelentkezés opcionális. Vendégként is teljes mértékben használhatod a TEXTUS-t; "
            "a Google-fiók csak a személyes azonosítást szolgálja."
        )
        if st.button("Bejelentkezés Google-fiókkal", key="settings_google_login"):
            st.login()

    # ─── 0b) Saját munkáim — részletes lista; napi mentés a fejlécsávon ──
    st.subheader("Saját munkáim")
    _owner = _owner_sub()
    if not _owner:
        st.info(
            "A felhőbe mentéshez jelentkezz be Google-fiókkal. "
            "Vendégként a TEXTUS minden funkciója továbbra is használható; "
            "adatbázisba semmi nem kerül."
        )
    else:
        from project_storage import get_user_projects

        st.caption(
            "A mentés, a **projektcím** és a projektváltás a lap tetején lévő **Projekt** sávon érhető el. "
            "Megnyitott projektnél kb. 3 percenként automatikus mentés is fut, ha van nem mentett változás."
        )

        _cur_id = (st.session_state.get("current_project_id") or "").strip()
        _cur_title = (st.session_state.get("current_project_title") or "").strip()
        if _cur_id:
            st.caption(f"Megnyitott felhőprojekt: **{_cur_title or 'Névtelen projekt'}**")
        else:
            st.caption("Nincs megnyitott felhőprojekt.")

        st.markdown("##### Mentett projektek")
        st.caption(
            "Megnyitás és törlés: ugyanez a lista a lap tetején a **Projektek…** gombbal is elérhető."
        )
        try:
            _projects = get_user_projects(_owner)
        except Exception as _exc:
            _projects = []
            st.error(f"A projektlista nem tölthető be: {_exc}")

        if not _projects:
            st.caption("Még nincs mentett projekt. Használd a lap tetején a Mentés gombot.")
        else:
            for _proj in _projects:
                _pid = str(_proj.get("id") or "")
                _ptitle = (_proj.get("title") or "").strip() or "Névtelen projekt"
                _ppassage = (_proj.get("passage") or "").strip() or "—"
                _pupdated = (_proj.get("updated_at") or "")[:19].replace("T", " ")
                _is_current = _pid and _pid == _cur_id
                st.markdown(
                    f"**{_ptitle}**"
                    + (" · *megnyitva*" if _is_current else "")
                    + f"  \n{_ppassage}"
                    + (f" · {_pupdated}" if _pupdated else "")
                )
                _lc1, _lc2 = st.columns(2)
                with _lc1:
                    if st.button(
                        "Megnyitás",
                        key=f"settings_project_open_{_pid}",
                        use_container_width=True,
                        disabled=not _pid,
                    ):
                        _request_open_project(_pid)
                with _lc2:
                    if st.button(
                        "Törlés",
                        key=f"settings_project_delete_{_pid}",
                        use_container_width=True,
                        disabled=not _pid,
                    ):
                        st.session_state["project_delete_confirm_id"] = _pid
                        st.session_state["project_open_confirm_id"] = None
                        st.session_state["show_projects_panel"] = True
                        st.rerun()

    st.warning("Ha az API kulcs valaha megjelenik hibaüzenetben vagy képernyőképen, generálj újat a Google AI Studio-ban.")

    # ─── 1) Beépített közös kulcs státusza ────────────────────────────
    if BUILTIN_API_KEY:
        if st.session_state.get("using_builtin_key", False):
            st.success(
                "✓ **Beépített közös kulcs aktív.** A TEXTUS azonnal használható, "
                "nem kell saját kulcsot megadnod. Ha szeretnél, lent megadhatsz "
                "saját kulcsot — az felülírja a közöset."
            )
        else:
            st.info(
                "🔑 **Saját API kulcsot használsz.** Ha szeretnéd, visszaválthatsz "
                "a beépített közös kulcsra."
            )
            if st.button("Vissza a beépített közös kulcsra", key="restore_builtin_key"):
                st.session_state["api_key"] = _load_builtin_api_key().strip()
                st.session_state["using_builtin_key"] = True
                st.session_state["user_model_choice"] = OWN_KEY_MODEL_AUTO
                st.success("Visszaállítva a közös kulcsra.")
                st.rerun()
    else:
        st.info(
            "Még nincs beépített közös kulcs ezen a példányon. "
            "Add meg a saját Gemini API kulcsodat lent a használathoz."
        )

    # ─── 2) Saját kulcs megadása (felülírja a beépítettet) ────────────
    using_builtin = st.session_state.get("using_builtin_key", False)
    api_input = st.text_input(
        "Saját Gemini API kulcs (opcionális, felülírja a beépítettet)" if BUILTIN_API_KEY else "Gemini API kulcs",
        type="password",
        value="" if using_builtin else st.session_state["api_key"],
        placeholder="Hagyd üresen a közös kulcs használatához…" if BUILTIN_API_KEY else "Illeszd be a Google AI Studio-ban generált kulcsot",
        key="api_key_input",
    )

    if api_input and api_input.strip() and api_input.strip() != st.session_state.get("api_key", ""):
        new_key = api_input.strip()
        st.session_state["api_key"] = new_key
        st.session_state["using_builtin_key"] = (new_key == _load_builtin_api_key().strip())
        if st.session_state["using_builtin_key"]:
            st.session_state["user_model_choice"] = OWN_KEY_MODEL_AUTO
            st.success("Visszaállítva a közös kulcsra.")
        else:
            st.success("Saját API kulcs mentve.")

    # ─── Modell — közös kulcs: rögzített; saját kulcs: választható ───
    using_own_key = _is_using_own_api_key()

    if using_own_key:
        if st.session_state.get("user_model_choice") not in OWN_KEY_MODEL_OPTIONS:
            st.session_state["user_model_choice"] = OWN_KEY_MODEL_AUTO
        st.selectbox(
            "Modell (saját kulccsal)",
            options=list(OWN_KEY_MODEL_OPTIONS.keys()),
            format_func=lambda model_id: OWN_KEY_MODEL_OPTIONS[model_id],
            help=(
                "Alapértelmezett: a fül szerint választ (Flash a mély szekciókhoz, "
                "Flash Lite az összegzőkhöz). Ha konkrét modellt választasz, "
                "az minden API-hívásra érvényes. A költség a saját Google AI Studio "
                "számládon jelenik meg."
            ),
            key="user_model_choice",
        )
        choice = st.session_state.get("user_model_choice", OWN_KEY_MODEL_AUTO)
        if choice == OWN_KEY_MODEL_AUTO:
            model_summary = (
                f"**Alapértelmezett** — **{LOCKED_MODEL_DISPLAY}** "
                f"vagy **Gemini 2.5 Flash Lite** (fül szerint)"
            )
            pill = "saját kulcs · alap"
        else:
            display = OWN_KEY_MODEL_OPTIONS.get(choice, choice)
            model_summary = f"**{display}** (`{choice}`) — minden hívásra"
            pill = "saját kulcs · egyedi"
    else:
        st.session_state["user_model_choice"] = OWN_KEY_MODEL_AUTO
        model_summary = (
            f"**{LOCKED_MODEL_DISPLAY}** (`{LOCKED_MODEL}`) "
            f"vagy **Gemini 2.5 Flash Lite** (`{GEMINI_MODEL_FLASH_LITE}`)"
        )
        pill = "közös kulcs · rögzített"

    st.markdown(
        f"""
<div class="locked-model-row">
    <span class="locked-model-label">Gemini modell</span>
    <span class="locked-model-value">{model_summary}
        <span class="locked-model-pill">{pill}</span>
    </span>
</div>
""",
        unsafe_allow_html=True,
    )
    if using_own_key:
        st.caption(
            "Saját API kulccsal választhatsz modellt. Az *Alapértelmezett* ugyanazt csinálja, "
            "mint a közös kulcsnál. A Gemini Pro előfizetés (app) és az API számlázás külön."
        )
    else:
        st.caption(
            f"A közös kulcsnál a backend a fül szerint választ — **{LOCKED_MODEL_DISPLAY}** "
            f"(`{LOCKED_MODEL}`) vagy **Gemini 2.5 Flash Lite** (`{GEMINI_MODEL_FLASH_LITE}`); "
            "nincs kézi modellválasztás. A *Kreativitás* beállítás minden hívásra érvényes."
        )

    st.session_state["temperature"] = st.slider(
        "Kreativitás",
        0.0,
        1.0,
        float(st.session_state.get("temperature", 0.3)),
        0.1
    )

    st.info(
        "**Válaszhossz:** nincs alkalmazásszintű kimeneti tokenlimit beállítva. "
        "A promptok tömör, strukturált, de a fontos információkat nem kihagyó válaszokat kérnek. "
        "A *Kreativitás* csúszka továbbra is érvényes.",
        icon="📝",
    )

    with st.expander("Aktív közös alap prompt"):
        st.text_area(
            "Ez kerül minden AI-hívás elé",
            BASE_SYSTEM_PROMPT,
            height=360,
            disabled=True
        )

    # ─── Cache & cooldown ────────────────────────────────────────────
    st.divider()
    st.subheader("Cache és cooldown")
    st.caption(
        f"Globális cooldown két API-hívás közt: **{GEMINI_COOLDOWN_S} mp**. "
        "Ha túl gyorsan kattintasz, az alkalmazás megvár, és figyelmeztet."
    )

    cache_col1, cache_col2 = st.columns([2, 1])
    with cache_col1:
        st.checkbox(
            "Cache azonos kérésekre (igehely + tab + beállítások)",
            value=bool(st.session_state.get("enable_cache", True)),
            key="enable_cache",
            help=(
                "Ha be van kapcsolva, ugyanaz a kérés (azonos prompt és "
                "kreativitás-beállítás) nem indít új API-hívást — a korábbi "
                "választ adja vissza azonnal. Csak az aktuális munkamenetre érvényes."
            ),
        )
    with cache_col2:
        cache_size = len(st.session_state.get("_call_cache", {}))
        st.metric("Cache-elt válaszok", cache_size)

    if st.button("Cache törlése", key="clear_cache_btn", use_container_width=True):
        st.session_state["_call_cache"] = {}
        st.success("Cache kiürítve.")
        st.rerun()

    # ─── Debug log ───────────────────────────────────────────────────
    debug_log = st.session_state.get("_debug_log", [])
    with st.expander(
        f"Gemini debug log — utolsó {len(debug_log)} bejegyzés",
        expanded=False,
    ):
        st.caption(
            "Minden Gemini-hívás előtt és után egy bejegyzés készül. "
            "Egyetlen gombnyomás max. **1 logikai hívást** indít; ha "
            "`attempt > 1` látható, az automatikus 429-retry történt."
        )
        _mid = st.session_state.get("model_name", LOCKED_MODEL)
        _mdisp = GEMINI_MODEL_DISPLAY_BY_ID.get(_mid, _mid)
        st.caption(
            f"Session: `{_get_session_id()}` · "
            f"Kulcs: `{_mask_api_key(_resolve_api_key())}` "
            f"({_api_key_source_label()}) · "
            f"Utolsó hívás modellje: **{_mdisp}** (`{_mid}`)"
        )
        if not debug_log:
            st.info("Még nincs API-hívás ebben a munkamenetben.")
        else:
            rows = []
            for e in reversed(debug_log[-30:]):
                rows.append({
                    "Idő": e.get("ts", ""),
                    "Session": e.get("session_id", ""),
                    "Kulcs": e.get("key_masked", ""),
                    "Forrás": e.get("key_source", ""),
                    "Tab": e.get("tab", ""),
                    "Próba": e.get("attempt", ""),
                    "Státusz": e.get("status", ""),
                    "Modell": e.get("model", ""),
                    "Prompt (kar.)": e.get("prompt_chars", ""),
                    "Válasz (kar.)": e.get("response_chars", ""),
                    "Latency (ms)": e.get("latency_ms", ""),
                    "Auth": e.get("auth_ok", ""),
                    "Hibaüzenet": e.get("error_message", ""),
                })
            st.dataframe(rows, hide_index=True, use_container_width=True)

        if st.button("Debug log ürítése", key="clear_debug_log_btn"):
            st.session_state["_debug_log"] = []
            st.rerun()

    if st.button("API kapcsolat tesztelése"):
        test = generate_text(
            "Válaszolj röviden magyarul: működik a kapcsolat?",
            tab_label="API teszt",
            use_cache=False,
        )
        if test.startswith("⚠️") or test.startswith("Hiba") or test.startswith("Nincs"):
            st.error(test)
        else:
            st.success("Kapcsolat sikeres.")
            st.write(test)

    st.divider()
    st.subheader("Munkamenet mentése és betöltése")
    st.caption(
        "A teljes műhely-állapot (igehely, elemzések, finomító beszélgetések, "
        "vázlatkosár, vázlat, énekek) egyetlen fájlba menthető és visszatölthető. "
        "Hasznos, ha napokon át dolgozol egy prédikáción, vagy másik gépen folytatnád."
    )

    _ws_payload = serialize_workspace()
    _ws_verse = (st.session_state.get("last_igehely") or "munka").replace(" ", "_").replace("/", "-").replace(",", "").replace(":", "-")
    _ws_filename = f"textus-munka-{_ws_verse}-{datetime.now().strftime('%Y%m%d-%H%M')}.json"

    col_save, col_load = st.columns(2)
    with col_save:
        st.download_button(
            label="Munkamenet mentése (.json)",
            data=_ws_payload,
            file_name=_ws_filename,
            mime="application/json",
            use_container_width=True,
        )

    with col_load:
        uploaded_ws = st.file_uploader(
            "Korábbi munkamenet betöltése",
            type=["json"],
            key="ws_uploader",
            label_visibility="collapsed",
        )
        if uploaded_ws is not None:
            ok, info = deserialize_workspace(uploaded_ws.read())
            if ok:
                st.success(f"Munkamenet betöltve. (Mentés időpontja: {info})")
                st.rerun()
            else:
                st.error(info)

    st.divider()
    st.subheader("Munkamenet törlése")
    st.caption("Csak a generált tartalmat, a kosarat és a beszélgetéseket törli — az API kulcsot és a modellbeállításokat megőrzi.")
    st.markdown('<div class="btn-danger-marker"></div>', unsafe_allow_html=True)
    if st.button("Munkamenet törlése"):
        _clear_workspace_content()
        _set_flash("A munkamenet törölve.", "info")
        st.rerun()

    st.divider()
    st.subheader("Hogyan igényelhetsz saját Gemini API kulcsot?")
    st.caption("Lépésről lépésre — a folyamat teljesen ingyenes, és csak egy Google-fiók (Gmail cím) szükséges hozzá.")

    st.markdown(
        """
<div class="result-box api-guide-box">

A saját kulcs használata biztosítja, hogy a **TEXTUS** hosszú távon is
stabilan és korlátlanul rendelkezésedre álljon.

1. **Lépj be a Google AI Studio oldalára.**
   Kattints ide: <a href="https://aistudio.google.com/" target="_blank" rel="noopener">aistudio.google.com</a> — jelentkezz be a megszokott Google-fiókoddal.

2. **Fogadd el a feltételeket.**
   Az első belépéskor el kell fogadnod a felhasználási feltételeket.

3. **Kulcs létrehozása.**
   A bal oldali menüben válaszd a **„Get API key"** gombot.

4. **Új projekt indítása.**
   Kattints a **„Create API key in new project"** feliratú gombra.

5. **Másold ki a kulcsot.**
   A rendszer legenerál egy hosszú karaktersort — ez az API kulcsod.
   Kattints a **Copy** gombra.

6. **Illeszd be a TEXTUS-ba.**
   Gyere vissza ide a **Beállításokhoz**, és illeszd be a kulcsot
   a fenti **„Gemini API kulcs"** mezőbe.

</div>
""",
        unsafe_allow_html=True,
    )

    st.divider()
    st.caption(f"{APP_NAME} v{APP_VERSION} · {APP_SUBTITLE} · {APP_TAGLINE}")


# =========================================================
# ÚTMUTATÁS — ARS POETICA + PROMPT GYORSSEGÉD
# =========================================================

with tabs[11]:
    st.header("📖 Útmutatás")

    st.subheader("Ars Poetica: Miért készítettem ezt az eszközt?")
    st.markdown(
        "A TEXTUS nem egy „prédikációgyár”. Tudatos döntésem volt, "
        "hogy ne egy automatizált, kész szövegeket gyártó rendszert hozzak "
        "létre. Azért dolgoztam ezen az applikáción, hogy a technológia "
        "segítségével olyan mélységekhez is közelebb vigyelek, amelyekhez a "
        "hétköznapi rohanásban sokszor nem jutsz el: az **eredeti szöveg "
        "árnyalataihoz**, a **kortörténeti háttérhez** és az **exegetikai "
        "szempontokhoz**.\n\n"
        "Az AI itt egy **digitális szolgatárs**, aki segít az előkészítésben, "
        "de az **üzenet megszületése** és a **személyes tanúságtétel** továbbra "
        "is a te imádságos küzdelmed és a Szentlélek közös titka marad."
    )

    st.markdown(
        "<div class=\"author-signature\">"
        "<div class=\"author-name\">Hover Zsolt</div>"
        "<div class=\"author-role\">református lelkipásztor</div>"
        "<div class=\"author-place\">Kalotaszeg · Magyargyerőmonostor</div>"
        "<div class=\"author-mail\">"
        "<a href=\"mailto:hoverzsolt@gmail.com\">hoverzsolt@gmail.com</a>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    st.divider()

    st.subheader("Hogyan „beszélgess” az AI-val? — Prompt-gyorssegéd")
    st.markdown(
        "Az eredmény minősége nagyban azon múlik, **hogyan kérdezel**. Ezt "
        "hívják *promptolásnak*. Íme a javaslatom a „jó kérdezéshez”:"
    )

    st.markdown("##### 1. Adj meg szerepet és célközönséget")
    st.markdown(
        "Ne csak annyit írj, hogy *„írj vázlatot”*. Próbáld így:"
    )
    st.info(
        "„Légy egy alapos bibliakutató, és segíts vázlatot készíteni a Lukács "
        "15-ről. A célközönségem fiatal felnőttek, akik távol állnak a "
        "templomtól.”",
        icon="🎯",
    )

    st.markdown("##### 2. Kérj konkrét szempontokat")
    st.markdown(
        "Az AI nagyszerűen tud kontextust adni — használd bátran:"
    )
    st.info(
        "„Gyűjts össze 3 olyan kulturális vagy történelmi érdekességet az "
        "ókori Izraelből, ami segít jobban megérteni ezt a textust!”",
        icon="🔎",
    )

    st.markdown("##### 3. Az „arany szabály” — vitázz és finomíts")
    st.markdown(
        "Ha a válasz túl száraz vagy gépies, **ne add fel**. Az AI-val lehet "
        "és érdemes vitatkozni — írj neki vissza:"
    )
    st.info(
        "„Ez túl elméleti lett. Tudnál mondani egy hétköznapi, mai példát, "
        "amivel ezt szemléltethetném?”\n\n"
        "„Ez a pont nem elég hangsúlyos a textus alapján. Kérlek, keress hozzá "
        "egy idevágó ószövetségi párhuzamot!”",
        icon="💬",
    )

    st.markdown("##### 4. Ellenőrizd és válogasd meg")
    st.markdown(
        "Az AI néha **magabiztosan tévedhet**. A hivatkozásokat és neveket "
        "**mindig ellenőrizd!** Tekints a válaszokra úgy, mint **nyersanyagra**, "
        "amit neked kell megmunkálnod a saját stílusodban."
    )
    st.info(
        "Tipp: amelyik elemzés tetszik, mentsd el a **Vázlatkosárba** "
        "(„Hozzáadás a vázlatkosárhoz” gomb); a végén ezekből építed össze a "
        "saját vázlatodat.",
        icon="🧺",
    )

    st.divider()
    st.caption(f"{APP_NAME} v{APP_VERSION} · {APP_SUBTITLE} · {APP_TAGLINE}")


# =========================================================
# IGEHIRDETÉSI SOROZAT TERVEZŐ
# =========================================================

with tabs[10]:
    st.header("📅 Igehirdetési sorozat tervező")

    st.info(
        "Ez a fül **külön** működik az igehely-alapú elemzéstől.",
        icon="📅",
    )

    st.subheader("Tervezzünk meg egy új sorozatot!")

    st.text_area(
        "Mi a sorozat központi témája vagy alapötlete?",
        key="series_idea",
        height=260,
        placeholder=(
            "Pl.: „Amikor elfogy az erő” — sorozat Illés történetei alapján;\n"
            "„Jézus nehéz kérdései”;\n"
            "„Remény a fogságban” — Dániel könyve;\n"
            "„Sebek és helyreállás” — bibliai történetek a gyógyulásról;\n"
            "vagy egy aktuális gyülekezeti kihívás bibliai feldolgozása stb.\n"
            "\n"
            "Tipp: Érdemes megadni a sorozat hangulatát, célját vagy a "
            "gyülekezet aktuális kérdéseit is. A részletesebb leírás "
            "általában mélyebb és relevánsabb eredményt ad."
        ),
    )

    SERIES_CADENCE_OPTIONS = {
        "vasárnapi": "Vasárnapi sorozat (heti, vasárnaponkénti alkalom)",
        "hetkoznapi": "Hétköznapi sorozat (egymást követő napok — pl. bűnbánati hét, esti istentiszteleti hét)",
        "satoros": "Sátoros ünnepek (három napos ünnep — Karácsony / Húsvét / Pünkösd)",
        "vegyes": "Egyéb / vegyes ütem (havi, alkalmi, lelkigyakorlat stb.)",
    }
    series_cadence_key = st.selectbox(
        "Milyen jellegű a sorozat?",
        options=list(SERIES_CADENCE_OPTIONS.keys()),
        format_func=lambda k: SERIES_CADENCE_OPTIONS[k],
        key="series_cadence",
    )

    if series_cadence_key == "satoros":
        st.caption(
            "📅 **Sátoros ünnepi sorozat — kötött, 3 napos struktúra:** "
            "*1. nap (központi üzenet) → 2. nap (mélyítés, megélés) → "
            "3. nap (továbblépés / küldetés / hálaadás).* "
            "Az „alkalmak száma” itt nem állítható — a hagyomány szerint 3."
        )
    else:
        st.slider(
            "Hány alkalmas legyen a sorozat?",
            min_value=2,
            max_value=14,
            key="series_weeks",
            help=(
                "Vasárnapi sorozatnál ez a hetek száma; hétköznapi sorozatnál "
                "az egymást követő alkalmak (napok / esték) száma; vegyes "
                "ütemnél az alkalmak száma."
            ),
        )

    series_busy = bool(st.session_state.get("_series_planner_running"))
    if st.button(
        "📅 Sorozat vázlatának elkészítése",
        type="primary",
        key="series_generate_btn",
        disabled=series_busy,
    ):
        idea_raw = (st.session_state.get("series_idea") or "").strip()
        if series_cadence_key == "satoros":
            weeks_n = 3
        else:
            weeks_n = int(st.session_state.get("series_weeks", 4))
        cadence_label = SERIES_CADENCE_OPTIONS.get(series_cadence_key, "")
        cadence_instructions = {
            "vasárnapi": (
                "A sorozat **vasárnapi (heti) ütemű** — minden alkalom egy-egy "
                "vasárnapi istentisztelet. A fejléceket „1. hét — …”, „2. hét — …” "
                "stílusban add (sorszámozva)."
            ),
            "hetkoznapi": (
                "A sorozat **hétköznapi**, egymást követő napokon zajlik (pl. "
                "bűnbánati hét, esti istentiszteleti hét). A fejléceket vagy a "
                "hét napjai szerint („Hétfő — …”, „Kedd — …” stb.), vagy "
                "„1. nap — …”, „2. nap — …” formában add. Ha a téma a Nagyhetet "
                "vagy más egyházi hetet érinti, használhatsz konkrét napneveket "
                "is („Nagyhétfő — …”, „Nagypéntek — …”)."
            ),
            "satoros": (
                "A sorozat **sátoros ünnepi** — a magyar protestáns hagyomány "
                "szerinti **három napos ünnep** (Karácsony / Húsvét / Pünkösd) "
                "struktúrájában gondolkodj. Pontosan **3** alkalmat dolgozz ki, "
                "az ünnep teológiai ívére fűzve:\n"
                "• **1. nap** — a központi üzenet és az ünnep teológiai csúcsa "
                "(születés / feltámadás / Lélek kiáradása).\n"
                "• **2. nap** — az ünnep mélyítése és személyes megélése "
                "(megtestesülés mélysége / találkozás a Feltámadottal / a Lélek "
                "ajándékai és gyümölcsei).\n"
                "• **3. nap** — továbblépés, küldetés vagy hálaadás (igeválasz, "
                "tanúságtétel, gyülekezeti küldetés).\n"
                "A fejléceket „Ünnep első napja — …”, „Ünnep második napja — …”, "
                "„Ünnep harmadik napja — …” stílusban add; ha a téma egyértelműen "
                "Karácsony / Húsvét / Pünkösd, akkor használhatsz konkrét nevet is: "
                "„Karácsony 1. napja — …”, „Húsvét 2. napja — …”, „Pünkösd 3. napja "
                "— …”. A három napot egymásra építsd — koherens teológiai mozgás "
                "kell, hogy átvezesse a hallgatókat."
            ),
            "vegyes": (
                "A sorozat **vegyes / egyéb ütemű** — válaszd meg a természetes "
                "egységet (alkalom / este / összejövetel). A fejléceket "
                "„1. alkalom — …”, „2. alkalom — …” stílusban add."
            ),
        }.get(series_cadence_key, "")
        if not idea_raw:
            st.warning("Írd be a sorozat központi témáját vagy alapötletét.")
        else:
            series_user_prompt = (
                "Központi téma / alapötlet:\n"
                f"{idea_raw}\n\n"
                f"Sorozat jellege: **{cadence_label}**\n"
                f"{cadence_instructions}\n\n"
                f"Alkalmak száma: **{weeks_n}**.\n\n"
                "Készíts **magyar** nyelven, a rendszerutasításban megadott Markdown-szerkezetnek "
                f"megfelelően egy teljes sorozattervet. Az **Alkalmankénti bontás** alatt pontosan "
                f"**{weeks_n}** alkalmat dolgozz ki — a sorozat jellegéhez illő fejlécekkel "
                "(lásd fent). Ne hagyj ki alkalmat, és ne adj többet a kért számnál. "
                "Minden alkalom legyen önálló, jól elkülönülő blokk."
            )
            st.session_state["_series_planner_running"] = True
            try:
                with st.spinner("A sorozat vázlatának összeállítása folyamatban..."):
                    series_out = generate_text(
                        series_user_prompt,
                        tab_label="Igehirdetési sorozat tervező",
                        use_cache=False,
                        system_bundle=SERIES_PLANNER_SYSTEM_PROMPT,
                        include_brevity_directive=False,
                    )
                st.session_state["series_planner_output"] = series_out
            finally:
                st.session_state["_series_planner_running"] = False
            st.rerun()

    series_md = (st.session_state.get("series_planner_output") or "").strip()
    if series_md:
        if series_md.startswith("⚠️") or series_md.startswith("⏳"):
            st.warning(series_md)
        else:
            head_block, section_blocks = _parse_series_week_sections(series_md)
            with st.container():
                st.markdown("#### Sorozat — összefoglaló")
                st.markdown(head_block or series_md)
            if section_blocks:
                st.markdown("#### Alkalmankénti bontás")
                for exp_title, exp_body in section_blocks:
                    with st.expander(exp_title, expanded=False):
                        st.markdown(exp_body)
            else:
                st.caption(
                    "Az egyes alkalmak külön expanderekbe rendezése nem sikerült automatikusan — "
                    "a teljes válasz fent látható."
                )


# =========================================================
# LÁBLÉC — ARS POETICA / MŰHELYREND
# =========================================================

footer_html = """
<div class="ars-section ars-footer">
    <div class="ars-poetica">
        <strong>{app_name} v{app_version}</strong><br>
        A TEXTUS jelenleg ingyenesen használható, a legújabb
        <em>{locked_model_display}</em> nyelvi modell támogatásával.<br>
        <a href="https://{app_domain}" target="_blank" rel="noopener">{app_domain}</a>
        ·
        <a href="{app_streamlit_url}" target="_blank" rel="noopener">textus.streamlit.app</a>
    </div>
    <div class="ars-divider"></div>
    <div class="ars-stations">
        <div class="ars-station">
            <div class="ars-numeral">I &middot; Saját API kulcs</div>
            <div class="ars-station-title">Beállítások fülön</div>
            <div class="ars-station-text">
                Ha rendelkezel saját Google API kulccsal, a
                <strong>Beállítások</strong> fülön bármikor megadhatod.
            </div>
        </div>
        <div class="ars-station">
            <div class="ars-numeral">II &middot; Nincs még kulcsod?</div>
            <div class="ars-station-title">Ingyen igényelhető</div>
            <div class="ars-station-text">
                A Google fiókoddal pár kattintással igényelhetsz egyet — a pontos
                leírást és segítséget szintén a <strong>Beállítások</strong> fül
                alatt találod.
            </div>
        </div>
        <div class="ars-station">
            <div class="ars-numeral">III &middot; Visszajelzés</div>
            <div class="ars-station-title">Írj közvetlenül az oldalon</div>
            <div class="ars-station-text">
                Görgess az oldal legaljára, és küldd el véleményed az űrlapon —
                ötlet, hiba, tapasztalat egy helyen.<br>
                <a href="#visszajelzes">Ugrás a visszajelzéshez ↓</a>
            </div>
        </div>
    </div>
</div>
""".format(
    app_name=APP_NAME,
    app_version=APP_VERSION,
    locked_model_display=LOCKED_MODEL_DISPLAY,
    app_domain=APP_DOMAIN,
    app_streamlit_url=APP_STREAMLIT_URL,
)

st.markdown(footer_html, unsafe_allow_html=True)

render_feedback_section()