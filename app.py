import streamlit as st
import streamlit.components.v1 as st_components
import requests
import urllib3
import base64
import json
import io
import os
from datetime import datetime
from pathlib import Path

# =========================================================
# VERZIÓ
# =========================================================
APP_VERSION = "1.0"

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(
    page_title=f"Emmaus {APP_VERSION}",
    page_icon="✝️",
    layout="wide"
)


# =========================================================
# BEÉPÍTETT (KÖZÖS) GEMINI API KULCS
# =========================================================
#
# Az alapértelmezett kulcsot SOHA nem írjuk a forráskódba.
# Két forrásból olvashatjuk (priorítás-sorrendben):
#   1) `.streamlit/secrets.toml` → `GEMINI_API_KEY` (`.gitignore` blokkolja)
#   2) `GEMINI_API_KEY` környezeti változó (Cloud / Docker / Render stb.)
#
# Ha sem az egyik, sem a másik nincs jelen, akkor a felhasználónak saját
# kulcsot kell megadnia a Beállítások fülön — az app működik továbbra is.

def _load_builtin_api_key() -> str:
    try:
        v = st.secrets.get("GEMINI_API_KEY", "")
        if v:
            return str(v).strip()
    except Exception:
        pass
    return (os.environ.get("GEMINI_API_KEY", "") or "").strip()


BUILTIN_API_KEY = _load_builtin_api_key()


# =========================================================
# RÖGZÍTETT GEMINI MODELL
# =========================================================
#
# Az alkalmazás SZÁNDÉKOSAN csak a `gemini-2.5-flash` modellt
# használja — ez az egyetlen engedélyezett modell.
#
# A backend a `generate_text()` függvényben kemény-érvényesíti
# ezt: a session_state esetleges manipulációja sem tud másik
# modellt rákényszeríteni az API hívásra.
#
# Ha valaha váltani akarsz (pl. egy új generációra), elég ezt az
# EGY konstanst átírni — a kód minden része ebből olvas.

LOCKED_MODEL = "gemini-2.5-flash"
LOCKED_MODEL_DISPLAY = "Gemini 2.5 Flash"

# ─────────────────────────────────────────────────────────────────────
# MODELL FALLBACK LÁNC
#   Ha az elsődleges modell 404 NotFound-ot ad (pl. átmeneti Google
#   API-hiba, regionális deprecation, kulcs-engedélyezetlenség), az
#   `_advance_active_model()` automatikusan átvált a következőre,
#   ÉS a választás KITART a teljes munkamenet alatt — nem hívunk újra
#   meg újra olyan modellt, ami már egyszer 404-et adott.
# ─────────────────────────────────────────────────────────────────────
MODEL_FALLBACK_CHAIN = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]
MODEL_DISPLAY = {
    "gemini-2.5-flash": "Gemini 2.5 Flash",
    "gemini-2.0-flash": "Gemini 2.0 Flash",
    "gemini-1.5-flash": "Gemini 1.5 Flash",
}

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
    "logo.png",
    "logo.jpg",
    "logo.jpeg",
    "logo.webp",
    "emmaus_logo.png"
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

/* Tawk.to widget injector iframe-je 0 magasságú, ne foglaljon margin/padding-helyet */
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
    grid-template-columns: 150px 1fr;
    gap: 1.6rem;
    align-items: center;
}}

.header-logo {{
    display: flex;
    align-items: center;
    justify-content: center;
}}

.header-logo .main-logo {{
    width: 120px;
    height: auto;
    filter: drop-shadow(0 6px 14px rgba(40, 28, 14, 0.28));
}}

.main-logo-fallback {{
    font-family: "Cormorant Garamond", Georgia, serif;
    font-size: 4.6rem;
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
    letter-spacing: 0.012em;
    color: #2b2116;
    line-height: 0.96;
    margin-bottom: 6px;
    text-shadow:
        0 1px 0 rgba(255, 255, 255, 0.62),
        0 8px 18px rgba(71, 52, 30, 0.16);
}}

.version-badge {{
    display: inline-block;
    margin-left: 0.65rem;
    padding: 0.18rem 0.62rem;
    font-family: "Inter", "Helvetica Neue", system-ui, sans-serif;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #5d4830;
    background:
        linear-gradient(180deg,
            rgba(252, 246, 232, 0.92),
            rgba(228, 211, 178, 0.78));
    border: 1px solid rgba(166, 134, 86, 0.42);
    border-radius: 999px;
    box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.72),
        0 2px 6px rgba(71, 52, 30, 0.14);
    vertical-align: middle;
    transform: translateY(-0.32em);
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

.subtitle {{
    font-family: "Lora", "Cormorant Garamond", Georgia, serif;
    font-size: 1.38rem;
    color: #4f3f31;
    font-style: italic;
    line-height: 1.42;
    max-width: 96ch;
    text-shadow:
        0 1px 0 rgba(255, 255, 255, 0.72),
        0 2px 10px rgba(255, 252, 246, 0.55);
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

/* Képek a tartalomban sose lógjanak túl */
[data-testid="stMarkdownContainer"] img {{
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
        grid-template-columns: 110px 1fr;
        gap: 1.1rem;
    }}

    .header-logo .main-logo {{
        width: 96px;
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
        width: 84px !important;
    }}

    .main-title {{
        font-size: clamp(2.1rem, 8vw, 2.8rem) !important;
        line-height: 1 !important;
    }}

    .version-badge {{
        font-size: 0.66rem !important;
        padding: 0.14rem 0.5rem !important;
        margin-left: 0.45rem !important;
        transform: translateY(-0.2em) !important;
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
        width: 72px !important;
    }}

    .main-title {{
        font-size: 1.95rem !important;
    }}

    .version-badge {{
        display: block !important;
        margin: 0.4rem auto 0 !important;
        width: max-content;
        transform: none !important;
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
Te az Emmaus digitális homiletikai műhely szakértő teológiai modulja vagy.
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
- világosan strukturált.

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
   - „Az Emmaus digitális homiletikai műhely szakértő teológiai moduljaként…"
   - „Mint az Emmaus modulja, örömmel segítek…"
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
Te egy bibliai eredeti nyelvi (görög és héber) műhelyvezető vagy,
aki kifejezetten lelkipásztori prédikációra való készülést támogat.

Szakmai vízió — ALAPOS FILOLÓGIAI ELEMZÉS:
Végezz alapos filológiai elemzést. NE csupán szótári jelentéseket közölj,
hanem vizsgáld meg az **eredeti görög vagy héber kifejezések szemantikai
hálóját**. Add meg a szavak **pontos alakját**, **fonetikus átírását**
és (ahol biztos és releváns) **etimológiáját**. Elemezd a szavak közötti
**teológiai feszültséget és szimbiózist** a konkrét bibliai környezetben.

A célod NEM tudományos nyelvészeti tanulmány,
hanem prémium szintű digitális exegetikai-homiletikai műhelyélmény:
mély, strukturált, pontos, prédikálható és gazdag segítség.

Alap szemlélet — JELENTÉSHÁLÓ, NE EGYETLEN SZÓ:
Egy bibliai szakaszban szinte sosem egyetlen kulcsszó hordozza a textust.
A textus jelentését több, egymással kapcsolatban álló szó és kifejezés
építi fel. A te dolgod, hogy ezt a jelentéshálót láttasd, ne csak
kiemelj egy „központi szót" és arra szűkíts.

Ezért minden elemzésnél:
- AZONOSÍTSD a szakasz több fontos kulcsszavát és kulcskifejezését
  (4–8 darabot, kivéve ha a szakasz jellege miatt indokoltan kevesebb),
- mutasd meg, hogyan kapcsolódnak egymáshoz a szavak,
- emeld ki az ismétlődő szavakat, motívumokat és szóláncokat,
- jelezd a textus belső feszültségeit, ellentétpárjait, fokozásait,
- és tárd fel, hogyan épül fel ezekből a szakasz mélyebb üzenete.

NE elégedj meg azzal, hogy egyetlen héber vagy görög szót elemzel.
NE szűkíts egyetlen „kulcsfogalomra".
HA mégis kevesebb mint 4 szó marad indokoltan (pl. nagyon rövid, egyetlen
mondatos textus), ezt rövid mondatban indokold meg.

Minden válaszod legyen:
- biblikusan megalapozott,
- exegetikailag pontos,
- teológiailag árnyalt,
- homiletikailag használható,
- visszafogott hangvételű,
- jól strukturált, gazdag és könnyen olvasható.

A kulcsszavak elemzése legyen mély és prédikáció-orientált:
- ne adj rövid, lexikonszerű definíciókat,
- ne sorolj fel száraz nyelvtani kategóriákat,
- ne építs spekulatív etimológiákat,
- ne írj álakadémikus nyelvészeti értekezést,
- helyette: minden kulcsszó esetében emeld ki
  a textuális, teológiai és pasztorális mélységet,
  valamint a szó helyét a textus jelentéshálójában.

Külön emeld ki, ha egy szó:
- ismétlődik a szakaszban (és hányszor),
- fontos bibliai motívumhoz kapcsolódik,
- nagyobb teológiai súllyal bír, mint amit a magyar fordítás kifejez,
- több jelentésréteget hordoz,
- több irányba nyitja az értelmezést,
- a szakaszban hangsúlyos szerepet kap,
- vagy gyakran félreértik a gyülekezetben.

Stílus:
- prémium digitális tanulmányi élmény,
- gazdag, részletes, mégis fegyelmezett,
- prédikációra elővehető — ne tankönyvszerű.

Ha valami a tudományban vitatott, használd a „Vitatott:" jelölést.
Ha bizonytalan vagy egy adatban, mondd ki nyíltan, hogy bizonytalan.
Soha ne találj ki nem létező idézetet, etimológiát, párhuzamos helyet
vagy bibliai kapcsolatot.

Válaszolj magyarul, prédikációs munkában jól használható, élő nyelven.
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

# EXEGÉZIS — PROFESSZIONÁLIS SZÖVEGELEMZÉS

Szakmai vízió:
Készíts professzionális exegetikai elemzést. Határozd meg a szakasz **pontos
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

Vizsgáld meg ennek a szakasznak az eredeti görög vagy héber szövegét.

NAGYON FONTOS — TÖBB KULCSSZÓ, NE EGY:
A szakasz jelentése sosem áll egyetlen szón. Azonosítsd a textus
TÖBB fontos kulcsszavát és kulcskifejezését, és láttasd a köztük lévő
jelentéshálót. Egyetlen szót elemezni nem elég.

KÖTELEZŐ:
- emelj ki LEGALÁBB 4, lehetőleg 6–8 valóban fontos kulcsszót
  vagy kulcskifejezést a szakaszból,
- csak valódi, valóban hangsúlyos szavakat hozz, ne tölts fel
  mesterségesen jelentéktelen szavakkal,
- ha indokoltan kevesebb mint 4 szó van (pl. nagyon rövid textus),
  ezt egy mondatban indokold meg az elemzés elején.

Ne adj felszínes szótári definíciókat.
Minden szó kapjon prédikáció-orientált, mély, strukturált elemzést,
és minden szó kapja meg a helyét a textus jelentéshálójában.

==================================================
1. JELENTÉSHÁLÓ — ÁTTEKINTÉS (kötelező, az elemzés ELEJÉN)
==================================================

Először — a részletes szóelemzések ELŐTT — adj egy rövid áttekintést
a szakasz jelentéshálójáról, pontosan ezzel a címmel és szerkezettel:

## Jelentésháló

3–6 mondatban mutasd meg:
- mely kulcsszavak hordozzák együtt a textus üzenetét,
- milyen ismétlődések, motívumok, szóláncok, ellentétpárok, fokozások
  szervezik a szakaszt,
- milyen belső feszültség(ek) feszítik a szöveget,
- és hogyan kapcsolódnak ezek a kulcsszavak egymáshoz.

Ezután — szintén az elemzés legelején — adj egy rövid, vesszővel elválasztott
listát a kulcsszavakról MAGYAR átírással, hogy a lelkipásztor első
ránézésre lássa a szóhalmazt:

**Kulcsszavak:** szó1, szó2, szó3, szó4, szó5, szó6 …

==================================================
2. KULCSSZÓ-ELEMZÉSEK (4–8 darab, a fenti hálóhoz illesztve)
==================================================

Minden egyes kulcsszót pontosan a következő markdown szerkezetben tárgyalj
(NE térj el a struktúrától, hogy a felület helyesen jeleníthesse meg):

### EREDETI_SZÓ · *fonetikus_átírás*

**Alapjelentés:** rövid, pontos alapjelentés.
Egy mondatban add meg azt, amit egy lelkipásztornak elsőként tudnia kell.

**Jelentésárnyalatok:** 2–4 mondat a finomabb jelentésárnyalatokról,
lehetséges alternatív jelentésekről, és arról, hogy a szó hány irányba
nyitja az értelmezést.
Ha a magyar fordítás nem adja vissza ezt a mélységet, ezt itt jelezd.

**Szövegkörnyezeti szerep:** 2–4 mondat arról, hogy
ez a szó miért fontos pontosan ebben a szakaszban,
milyen hangsúlyt ad a textusnak,
és hogyan működik irodalmilag (kompozíció, ismétlés, retorikai szerep).
Ha a szó ismétlődik a szakaszban, jelezd hányszor és milyen szerepben.

**Kapcsolódás a hálóhoz:** 1–3 mondat arról, hogy ez a szó
hogyan kapcsolódik a szakasz többi kulcsszavához
(milyen szóláncot, ellentétpárt, fokozást, motívumot épít velük együtt).

**Bibliai kapcsolatok:** 2–4 mondat arról, hogy
hol fordul elő még ez a szó vagy ehhez kapcsolódó fontos fogalom,
és milyen átfogóbb bibliai összefüggések épülnek köré.
Csak biztos, ellenőrizhető bibliai kapcsolatokat hozz.

**Teológiai jelentőség:** 2–4 mondat arról, hogy
milyen teológiai hangsúlyt hordoz a szó:
istenkép, emberkép, bűn, kegyelem, hit, szövetség, krisztológia stb.
Konkrét, prédikálható teológiai tartalmat adj — nem általánosságot.

**Homiletikai insight:** 2–4 mondat arról, hogy
ez a szó hogyan segíti a prédikációt:
milyen lelkipásztori alkalmazás születhet belőle,
és milyen prédikációs hangsúlyt alapozhat meg.
Itt legyél kifejezetten gyakorlatias és prédikálható.

> **Figyelmeztetés:** ezt csak akkor írd ki, ha a szóhoz
> gyakori félreértés vagy bizonytalan értelmezés kapcsolódik,
> vagy ha az AI valamiben bizonytalan az adott szóval kapcsolatban.
> Ha nincs ilyen, akkor ezt a sort teljesen hagyd ki.

---

A "EREDETI_SZÓ" helyére a tényleges görög vagy héber alakot írd
(eredeti betűkkel, NE átírással), a "fonetikus_átírás" helyére pedig
egy magyar kiejtést segítő egyszerű, természetes átírást.

Két kulcsszó-blokk között mindig legyen `---` elválasztó, hogy a
kártyák tisztán elkülönüljenek.

==================================================
3. ÖSSZEFOGLALÓ — A JELENTÉSHÁLÓ HOMILETIKAI HOZAMA
==================================================

Az elemzés végén — kötelezően — adj egy
4–6 mondatos összefoglalót, amely a kulcsszavak EGYÜTTESÉRE építve
mutatja meg, milyen prédikációs hangsúlyok bontakozhatnak ki a textusból.
Ne ismételd a szavak egyenkénti elemzését, hanem a háló egészéből
építkezz, és vezesd át a lelkipásztori-homiletikai irányba.
Ezt írd a következő cím alá:

## Összefoglaló

Nagyon fontos:
- ne találj ki nem létező szavakat, etimológiát, párhuzamos helyeket,
- ne hozz akadémikus szakkifejezéseket fölöslegesen,
- ne adj üres lexikon-szerű meghatározásokat,
- ne szűkíts egyetlen szóra, mindig a textus jelentéshálóját mutasd,
- a hangsúly végig az exegetikai mélység és a prédikációs haszon legyen.
"""


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

    if not st.session_state.get("api_key"):
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
):
    """Egységes szekció-tab renderelő.

    - Saját **Generálás** gomb (futás közben tiltott, spinner aktív).
    - Csak gombnyomásra fut Gemini hívás, page-load alatt SOHA.
    - Az eredmény külön `st.session_state[key]`-ben él, rerun nem dobja.
    - Megjeleníti a finomítás-chatet és a vázlatkosár-jegyzetet.
    """
    st.header(header)

    has_result = bool(st.session_state.get(key))
    running_flag = f"_{key}_running"
    is_running = bool(st.session_state.get(running_flag))

    btn_label = f"{header} újragenerálása" if has_result else f"{header} generálása"
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

WORKSPACE_STR_KEYS = [
    "last_igehely", "last_alkalom", "last_stilus", "last_sajat",
    "overview", "exegesis", "history", "theology",
    "illustrations", "actualization", "outline",
    "original_text", "songs",
]

WORKSPACE_LIST_KEYS = [
    "basket",
    "verse_history",
    "exegesis_chat", "history_chat", "theology_chat",
    "illustrations_chat", "actualization_chat",
    "outline_chat", "original_text_chat", "songs_chat",
]

WORKSPACE_KEYS = WORKSPACE_STR_KEYS + WORKSPACE_LIST_KEYS


def serialize_workspace():
    payload = {
        "_app": "Emmaus",
        "_version": APP_VERSION,
        "_saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    for k in WORKSPACE_STR_KEYS:
        payload[k] = st.session_state.get(k, "")
    for k in WORKSPACE_LIST_KEYS:
        payload[k] = st.session_state.get(k, [])
    return json.dumps(payload, ensure_ascii=False, indent=2)


def deserialize_workspace(raw_bytes):
    try:
        text = raw_bytes.decode("utf-8") if isinstance(raw_bytes, bytes) else raw_bytes
        obj = json.loads(text)
    except Exception as e:
        return False, f"A fájl nem olvasható JSON: {e}"
    if not isinstance(obj, dict) or obj.get("_app") != "Emmaus":
        return False, "Ez nem Emmaus munkamenet-fájl."
    for k in WORKSPACE_KEYS:
        if k in obj:
            st.session_state[k] = obj[k]
    return True, obj.get("_saved_at", "ismeretlen időpont")


# =========================================================
# VÁZLAT MARKDOWN EXPORT
# =========================================================

def build_outline_markdown():
    igehely = st.session_state.get("last_igehely", "—")
    alkalom = st.session_state.get("last_alkalom", "—")
    stilus = st.session_state.get("last_stilus", "—")
    outline = st.session_state.get("outline", "").strip()
    basket = st.session_state.get("basket", [])
    songs = st.session_state.get("songs", "").strip()
    now = datetime.now().strftime("%Y. %m. %d. %H:%M")

    lines = [
        "# Prédikációvázlat — Emmaus",
        "",
        f"**Igehely:** {igehely}  ",
        f"**Alkalom:** {alkalom}  ",
        f"**Homiletikai stílus:** {stilus}  ",
        f"**Készült:** {now}",
        "",
        "---",
        "",
        "## Vázlat",
        "",
        outline if outline else "_Még nem készült vázlat._",
        "",
    ]
    if basket:
        lines += ["---", "", "## Vázlatkosár — gondolatok a vázlathoz", ""]
        for source, item in basket:
            lines.append(f"### {source}")
            lines.append("")
            lines.append(item)
            lines.append("")
    if songs:
        lines += ["---", "", "## Liturgiai énekajánlás", "", songs, ""]
    lines += ["---", "", f"_Emmaus v{APP_VERSION} — digitális homiletikai műhely_"]
    return "\n".join(lines)


# =========================================================
# SESSION STATE
# =========================================================

defaults = {
    "api_key": BUILTIN_API_KEY,
    "using_builtin_key": bool(BUILTIN_API_KEY),
    "model_name": LOCKED_MODEL,
    "active_model": LOCKED_MODEL,
    "temperature": 0.3,
    "max_tokens": 700,

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
    "original_text": "",
    "songs": "",

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
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# =========================================================
# GEMINI API HÍVÁS
# =========================================================

def _google_search_tool_for_model(model_name: str = LOCKED_MODEL):
    """Google Search grounding tool — modell-családtól függő név.

    A 2.x család a `google_search` tool-t használja, az 1.5 család még
    a régi `google_search_retrieval` formátumot. A fallback chain
    automatikusan a megfelelőt választja.
    """
    if model_name and model_name.startswith("gemini-1.5"):
        return {"google_search_retrieval": {}}
    return {"google_search": {}}


# ─────────────────────────────────────────────────────────────────────
# AKTÍV MODELL — fallback chain kezelés (404 NotFound védelem)
# ─────────────────────────────────────────────────────────────────────

def _get_active_model() -> str:
    """A munkamenet aktuálisan használandó Gemini modellje.

    Default = `LOCKED_MODEL`; ha korábban 404 miatt fallback-eltünk,
    az `active_model` session_state-ben tárolt értéket használjuk.
    """
    m = st.session_state.get("active_model")
    if m and m in MODEL_FALLBACK_CHAIN:
        return m
    st.session_state["active_model"] = LOCKED_MODEL
    return LOCKED_MODEL


def _advance_active_model(current: str) -> str | None:
    """A fallback chain következő modelljére vált. None, ha kifutottunk."""
    try:
        idx = MODEL_FALLBACK_CHAIN.index(current)
    except ValueError:
        idx = -1
    nxt = MODEL_FALLBACK_CHAIN[idx + 1] if idx + 1 < len(MODEL_FALLBACK_CHAIN) else None
    if nxt:
        st.session_state["active_model"] = nxt
    return nxt


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
# mégis becsempész egy "Üdvözlöm…" / "Az Emmaus moduljaként…" típusú
# bevezetőt vagy záró "Bízom benne, hogy…" sort, kódból kivágjuk.

import re as _re_chatty

_CHATTY_INTRO_PATTERNS = [
    # Üdvözlések
    r"^(üdvözlöm|üdv|hello|szia|szervusz|tisztelt|kedves|drága|jó (napot|reggelt|estét))\b",
    # Öndefiniáló bevezetők
    r"^(az emmaus|mint (az |)emmaus|emmaus(ként| modulként| moduljaként)|"
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
GEMINI_DEFAULT_MAX_TOKENS = 700
GEMINI_DEBUG_LOG_MAX = 80         # session debug-log max bejegyzések

# Globális, kötelező tömörítési előírás (minden FELADAT-hoz csatolva).
_BREVITY_DIRECTIVE = """\
==================================================
TÖMÖRÍTÉSI ELŐÍRÁS — KÖTELEZŐ
==================================================

- A teljes válasz legfeljebb 600 szó (kb. 700 token).
- Ne írj fölösleges felvezetést vagy lezárást, csak érdemi tartalmat.
- Markdown listákkal és rövid címekkel tagolj.
- Ha a téma részletesebb kifejtést érdemelne, NE írd ki teljes
  hosszában; helyette zárd egyetlen sorral:
  *(A részletesebb kifejtésért indítsd a finomítás chatet,
  vagy kérd külön bővítésre.)*
"""


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
        api_key = (st.session_state.get("api_key") or "").strip()
        using_builtin = bool(st.session_state.get("using_builtin_key", False))
        entry.setdefault(
            "key_source",
            ("built-in" if using_builtin else ("saját" if api_key else "—")),
        )
        entry.setdefault("key_masked", _mask_api_key(api_key))

    log = st.session_state.setdefault("_debug_log", [])
    log.append(entry)
    if len(log) > GEMINI_DEBUG_LOG_MAX:
        del log[: len(log) - GEMINI_DEBUG_LOG_MAX]

    try:
        print(
            "[GEMINI {ts}] sid={sid} key_src={ksrc} key={kmsk} "
            "tab={tab} attempt={att} status={st} model={mdl} "
            "prompt_chars={pc} resp_chars={rc} latency_ms={lat}".format(
                ts=entry.get("ts", ""),
                sid=entry.get("session_id", ""),
                ksrc=entry.get("key_source", ""),
                kmsk=entry.get("key_masked", ""),
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


def _build_payload(prompt: str, enable_google_search: bool, model: str) -> dict:
    """Összeállítja a Gemini REST kérés JSON body-ját.

    A `_BREVITY_DIRECTIVE` minden hívásnál érvényesül (token-takarékosság),
    a `maxOutputTokens` a Beállítások fülön szabott korlátot követi.
    A Google Search grounding tool a modell-családhoz illeszkedik.
    """
    final_prompt = (
        f"{BASE_SYSTEM_PROMPT}\n\n"
        f"{_BREVITY_DIRECTIVE}\n"
        "==================================================\n"
        "FELADAT\n"
        "==================================================\n\n"
        f"{prompt}\n"
    )
    payload = {
        "contents": [{"parts": [{"text": final_prompt}]}],
        "generationConfig": {
            "temperature": st.session_state.get("temperature", 0.3),
            "maxOutputTokens": int(st.session_state.get("max_tokens", GEMINI_DEFAULT_MAX_TOKENS)),
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
    """
    api_key = st.session_state.get("api_key", "").strip()
    if not api_key:
        return "⚠️ **Hiányzó API kulcs.** Add meg a Beállítások fülön a Gemini API kulcsot, mielőtt elindítanád az elemzést."

    # ─── MODELL VÁLASZTÁS (fallback chain support) ──────────────────
    active_model = _get_active_model()
    st.session_state["model_name"] = active_model  # UI sync

    cache_enabled = (
        use_cache
        and bool(st.session_state.get("enable_cache", True))
        and not enable_google_search  # Google-keresés esetén mindig friss adat kell
    )
    prompt_hash = _hash_prompt(
        prompt,
        extra=f"{active_model}|{st.session_state.get('max_tokens', GEMINI_DEFAULT_MAX_TOKENS)}",
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
            "model": active_model,
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
            "model": active_model,
            "prompt_chars": len(prompt),
            "response_chars": 0,
            "latency_ms": 0,
        })
        return (
            "⏳ **Kérlek várj néhány másodpercet az újabb generálás előtt.** "
            f"(Még kb. {int(remaining) + 1} másodperc.)"
        )

    # ─── 3. HTTP HÍVÁS (retry + 404-fallback chain) ──────────────────
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    prompt_chars = len(prompt)
    last_error_msg = "⚠️ **Ismeretlen hiba történt a kérés közben.**"
    fallback_notice = ""

    for attempt in range(GEMINI_MAX_RETRIES):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{active_model}:generateContent"
        data = _build_payload(prompt, enable_google_search, active_model)

        # log: BEFORE
        _debug_log_append({
            "ts": _now_str(),
            "tab": tab_label,
            "attempt": attempt + 1,
            "status": "REQUEST",
            "model": active_model,
            "prompt_chars": prompt_chars,
            "response_chars": 0,
            "latency_ms": 0,
        })
        start_ts = _time.time()

        try:
            response = requests.post(
                url, headers=headers, json=data,
                verify=False, timeout=GEMINI_TIMEOUT_S,
            )
        except requests.exceptions.Timeout:
            latency_ms = int((_time.time() - start_ts) * 1000)
            try:
                print(f"[GEMINI ERROR] model={active_model} TIMEOUT after {latency_ms}ms", flush=True)
            except Exception:
                pass
            _debug_log_append({
                "ts": _now_str(), "tab": tab_label, "attempt": attempt + 1,
                "status": "TIMEOUT", "model": active_model,
                "prompt_chars": prompt_chars, "response_chars": 0, "latency_ms": latency_ms,
                "error_message": "Network timeout",
            })
            st.session_state["_last_api_call_ts"] = _time.time()
            last_error_msg = (
                "⚠️ **Időtúllépés.** A Gemini szerver nem válaszolt időben. "
                "Próbáld újra pár másodperc múlva, vagy csökkentsd a válaszhosszt a Beállítások fülön."
            )
            if attempt < GEMINI_MAX_RETRIES - 1:
                _time.sleep(GEMINI_RETRY_BASE_S * (2 ** attempt))
                continue
            return last_error_msg
        except requests.exceptions.ConnectionError as ce:
            try:
                print(f"[GEMINI ERROR] model={active_model} CONN_ERROR: {ce}", flush=True)
            except Exception:
                pass
            _debug_log_append({
                "ts": _now_str(), "tab": tab_label, "attempt": attempt + 1,
                "status": "CONN_ERROR", "model": active_model,
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
                print(f"[GEMINI ERROR] model={active_model} EXCEPTION: {e}", flush=True)
            except Exception:
                pass
            _debug_log_append({
                "ts": _now_str(), "tab": tab_label, "attempt": attempt + 1,
                "status": "EXCEPTION", "model": active_model,
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
                text = result["candidates"][0]["content"]["parts"][0]["text"]
                text = _strip_chatty_intro(text)
                if enable_google_search:
                    sources_md = _format_grounding_sources(result)
                    if sources_md:
                        text = text + "\n" + sources_md

                _debug_log_append({
                    "ts": _now_str(), "tab": tab_label, "attempt": attempt + 1,
                    "status": "200_OK", "model": active_model,
                    "prompt_chars": prompt_chars, "response_chars": len(text),
                    "latency_ms": latency_ms,
                })
                if cache_enabled:
                    cache[prompt_hash] = (text, _time.time())
                return fallback_notice + text
            except (KeyError, IndexError, ValueError):
                err_msg = _log_http_error(active_model, sc, response)
                _debug_log_append({
                    "ts": _now_str(), "tab": tab_label, "attempt": attempt + 1,
                    "status": "EMPTY_OR_BLOCKED", "model": active_model,
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

        # ─── 404 NotFound → fallback chain (modellváltás) ────────────
        if sc == 404:
            err_msg = _log_http_error(active_model, sc, response)
            nxt = _advance_active_model(active_model)
            _debug_log_append({
                "ts": _now_str(), "tab": tab_label, "attempt": attempt + 1,
                "status": "404_NOT_FOUND", "model": active_model,
                "prompt_chars": prompt_chars, "response_chars": 0,
                "latency_ms": latency_ms,
                "error_message": (err_msg + (f" → fallback: {nxt}" if nxt else " → no fallback left"))[:300],
            })
            if nxt:
                fallback_notice = (
                    f"> ℹ️ A `{active_model}` modell jelenleg nem érhető el — "
                    f"automatikusan átváltottam erre: **{MODEL_DISPLAY.get(nxt, nxt)}**.\n\n"
                )
                active_model = nxt
                st.session_state["model_name"] = active_model
                # fallback nem számít attempt-nek; ne csökkentsünk retry-t,
                # de legalább 1 mp pihenő, hogy ne forrjon a kapcsolat
                _time.sleep(1)
                continue
            return (
                f"⚠️ **A Gemini modellek (404 NotFound) jelenleg nem érhetők el.**\n\n"
                f"Próbáltam: {', '.join(MODEL_FALLBACK_CHAIN)}.\n\n"
                f"**Google API üzenet:**\n```\n{err_msg}\n```\n\n"
                "Ez többnyire átmeneti Google-szerver vagy kulcs-engedélyezési hiba; "
                "próbáld újra pár perc múlva, vagy ellenőrizd a kulcsot."
            )

        # ─── 429 rate-limit → exponenciális backoff (Retry-After-aware) ─
        if sc == 429:
            err_msg = _log_http_error(active_model, sc, response)
            wait_s = _extract_retry_after_seconds(response, attempt, GEMINI_RATE_LIMIT_BASE_S)
            _debug_log_append({
                "ts": _now_str(), "tab": tab_label, "attempt": attempt + 1,
                "status": "429_RATE_LIMIT", "model": active_model,
                "prompt_chars": prompt_chars, "response_chars": 0,
                "latency_ms": latency_ms,
                "error_message": f"{err_msg} (wait={wait_s}s)"[:300],
            })
            if attempt < GEMINI_MAX_RETRIES - 1:
                _time.sleep(wait_s)
                continue
            return (
                "⚠️ **Túl sok kérés rövid idő alatt (429).** "
                f"A Google API ajánlott várakozása: ~{wait_s} mp. "
                "Több próbálkozás után sem sikerült — várj 1–2 percet, majd próbáld újra. "
                "Ha gyakori, érdemes saját API kulcsot megadni a Beállítások fülön.\n\n"
                f"**Google API üzenet:**\n```\n{err_msg}\n```"
            )

        # ─── 5xx szerver hiba → backoff retry ────────────────────────
        if sc >= 500:
            err_msg = _log_http_error(active_model, sc, response)
            _debug_log_append({
                "ts": _now_str(), "tab": tab_label, "attempt": attempt + 1,
                "status": f"{sc}_SERVER", "model": active_model,
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
        err_msg = _log_http_error(active_model, sc, response)
        _debug_log_append({
            "ts": _now_str(), "tab": tab_label, "attempt": attempt + 1,
            "status": f"{sc}_OTHER", "model": active_model,
            "prompt_chars": prompt_chars, "response_chars": 0,
            "latency_ms": latency_ms,
            "error_message": err_msg[:300],
        })
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
Egy digitális homiletikai műhely egyik részét finomítjuk.

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
# TAWK.TO CHAT WIDGET
# =========================================================
# A widget a böngésző fő ablakának jobb alsó sarkában jelenik meg.
# A Streamlit-`components.v1.html()` egy iframe-et hoz létre — a
# tawk.to script-et a `window.parent.document`-be injektáljuk, hogy
# a chat-buborék a top-level dokumentumban legyen, ne csak az
# iframe-en belül (ami a height=0 miatt láthatatlan lenne).
#
# A `tawkto-script-inject` id-vel ellenőrizzük, hogy ne kerüljön
# többszöri beillesztésre Streamlit-rerunkor.

def _inject_tawkto_widget():
    """Tawk.to chat-widget beágyazása (0 magasságú, helyfoglalás nélkül).

    A widget a teljes alkalmazásban (minden tabon, minden reruna alatt)
    elérhető marad, a fő böngészőablak DOM-jához csatolva.
    """
    st_components.html(
        """
<script type="text/javascript">
(function() {
    // Tawk.to widget elhelyezés — feljebb tolva, hogy a Streamlit
    // Cloud "Manage app" sávja ne takarja el a chat-buborékot.
    // A `yOffset` az alulról mért távolság pixelben.
    var TAWK_CUSTOM_STYLE = {
        visibility: {
            desktop: {
                position: 'br',  // bottom-right
                xOffset: 20,
                yOffset: 80      // ~Manage app sáv + biztonsági ráhagyás
            },
            mobile: {
                position: 'br',
                xOffset: 10,
                yOffset: 70
            }
        }
    };

    function bootstrapTawk(win, doc) {
        if (doc.getElementById('tawkto-script-inject')) return;
        win.Tawk_API = win.Tawk_API || {};
        win.Tawk_API.customStyle = TAWK_CUSTOM_STYLE;
        win.Tawk_LoadStart = new Date();
        var s1 = doc.createElement("script");
        s1.id = 'tawkto-script-inject';
        s1.async = true;
        s1.src = 'https://embed.tawk.to/6a01a241eb073e1c334f0d94/1job63k35';
        s1.charset = 'UTF-8';
        s1.setAttribute('crossorigin', '*');
        var s0 = doc.getElementsByTagName("script")[0];
        if (s0 && s0.parentNode) {
            s0.parentNode.insertBefore(s1, s0);
        } else {
            doc.body.appendChild(s1);
        }
    }

    // Próbáljuk a TOP-LEVEL window-ba injektálni (hogy a chat-buborék
    // az alkalmazás jobb alsó sarkában jelenjen meg, ne csak az
    // 0-magasságú iframe-en belül).
    try {
        bootstrapTawk(window.parent, window.parent.document);
        return;
    } catch (e) {
        // Cross-origin sandbox: az iframe-en belül indítjuk (fallback)
    }
    bootstrapTawk(window, document);
})();
</script>
        """,
        height=0,
    )


_inject_tawkto_widget()


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
    logo_html = f'<img src="data:{logo_mime};base64,{logo_b64}" class="main-logo" alt="Emmaus" />'
else:
    logo_html = '<div class="main-logo-fallback">✝</div>'

st.markdown(
    f"""
<div class="main-card header-card">
    <div class="header-grid">
        <div class="header-logo">{logo_html}</div>
        <div class="header-text">
            <div class="main-title">Emmaus<span class="version-badge">v{APP_VERSION}</span></div>
            <div class="subtitle">„Nem hevült-e a szívünk, amikor beszélt hozzánk az úton, és feltárta előttünk az Írásokat?” — Lk 24,32</div>
            <div class="header-caption">Digitális homiletikai műhely</div>
        </div>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

if not background_file:
    st.warning("A háttérkép nem található. Neve legyen background.jpg, background.jpeg, background.png vagy background.webp, és ugyanabban a mappában legyen, mint az app.py.")

if not logo_file:
    st.info("Logó nem található. Neve legyen logo.png, logo.jpg vagy logo.webp, és ugyanabban a mappában legyen, mint az app.py.")


# =========================================================
# TABOK
# =========================================================

tabs = st.tabs([
    "Igehely",
    "Eredeti szöveg",
    "Exegézis",
    "Kortörténet",
    "Teológia",
    "Illusztrációk",
    "Aktualizálás",
    "Vázlat",
    "Vázlatkosár",
    "Énekajánló",
    "Beállítások"
])


# =========================================================
# IGEHELY
# =========================================================

with tabs[0]:
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
        "A többi szekciót (Eredeti szöveg, Exegézis, Kortörténet, Teológia, "
        "Illusztrációk, Aktualizálás, Vázlat, Énekajánló) az adott fülön, "
        "külön gombbal indíthatod — így pontosan azt generálod, amire szükséged van. "
        "\n\n*Két API-hívás között legalább "
        f"{GEMINI_COOLDOWN_S} másodperc vár; a tömör válasz max. ~{GEMINI_DEFAULT_MAX_TOKENS} "
        "token. Ha bővebb kifejtés kell, használd a finomítás chatet.*"
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


# =========================================================
# TARTALOM TABOK — egységes Generálás-gombos minta
# =========================================================

with tabs[2]:
    render_section_tab(
        key="exegesis",
        header="Exegézis",
        basket_label="Exegézis",
        empty_msg="Még nincs exegézis. Kattints a generálás gombra.",
    )

with tabs[3]:
    render_section_tab(
        key="history",
        header="Kortörténet",
        basket_label="Kortörténet",
        empty_msg="Még nincs kortörténeti háttér. Kattints a generálás gombra.",
    )

with tabs[4]:
    render_section_tab(
        key="theology",
        header="Teológia",
        basket_label="Teológia",
        empty_msg="Még nincs teológiai elemzés. Kattints a generálás gombra.",
    )

with tabs[5]:
    render_section_tab(
        key="illustrations",
        header="Illusztrációk",
        basket_label="Illusztráció",
        empty_msg="Még nincsenek illusztrációs ötletek. Kattints a generálás gombra.",
    )

with tabs[6]:
    render_section_tab(
        key="actualization",
        header="Aktualizálás",
        basket_label="Aktualizálás",
        empty_msg="Még nincs aktualizálás. Kattints a generálás gombra (Google-keresés használatával friss kontextust kap).",
    )


# =========================================================
# VÁZLAT
# =========================================================

with tabs[7]:
    st.header("Prédikációvázlat")

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

    _outline_running = bool(st.session_state.get("_outline_running"))
    if st.button(
        "Vázlat generálása",
        type="primary",
        disabled=_outline_running,
        key="outline_run",
    ):
        basket_text = "\n".join([f"- {source}: {text}" for source, text in st.session_state["basket"]])

        prompt = f"""
# VÁZLAT — KOHERENS PRÉDIKÁCIÓS STRUKTÚRA

Szakmai vízió:
Dolgozz ki egy **koherens prédikációs struktúrát**. Fogalmazz meg egy
**világos tételmondatot (scopus)**. Alakíts ki egy **természetes ívű
gondolatmenetet** teológiai hangsúlyokkal. Jelöld meg a prédikáció
**„evangéliumi fordulatát"** — az utat a **diagnózistól az Isten
gyógyító válaszáig**.

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

A vázlatot pontosan az alábbi szerkezetben add (Markdown formátum):

## Címajánlatok
3–5 erős, kifejező címet — mindegyikhez 1 mondatos rövid indoklás.

## Tételmondat (scopus)
**Egyetlen, lényegre törő, teológiailag tartós mondat** — ez a prédikáció gerince.

## Az ív — diagnózis → evangéliumi fordulat → Isten válasza
Egy bekezdésben mutasd meg, milyen **mozgás** vezeti a hallgatót az igehirdetésen át,
hol van az **„evangéliumi fordulat"**, ahol a textus a diagnózistól az Isten gyógyító
válaszához vezet.

## Szerkezet
A választott modell szerint **2–4 pontos vázlat**, mindegyik ponthoz:
- pont címe (rövid, hangsúlyos),
- 2–3 mondatos magyarázat,
- konkrét textuális vagy teológiai horgony.

## Átvezetések
Az egyes pontok közti **természetes átvezetések** (1–1 mondat).

## Bevezetés
Egy konkrét, **prédikációs nyitó megoldás** — kép, kérdés, élethelyzet.

## Lezárás
Egy konkrét, **prédikációs zárás** — összefoglalás, hívás, ígéret.

## Alkalmazási pontok
2–3 konkrét, gyülekezeti életbe illesztett **alkalmazási irány**.
"""

        st.session_state["_outline_running"] = True
        try:
            with st.spinner("Vázlat készül..."):
                st.session_state["outline"] = generate_text(
                    prompt, tab_label="Vázlat",
                )
        finally:
            st.session_state["_outline_running"] = False
        st.rerun()

    if st.session_state["outline"]:
        st.markdown('<div class="result-box">', unsafe_allow_html=True)
        st.markdown(st.session_state["outline"])
        st.markdown('</div>', unsafe_allow_html=True)

        st.divider()
        st.subheader("Letöltés és megosztás")
        st.caption("A vázlat, a vázlatkosár tartalma és (ha van) az énekajánlás letölthető Markdown fájlként. Bármelyik szerkesztőben megnyitható, vasárnapra kinyomtatható, vagy átküldhető telefonra.")

        _md_payload = build_outline_markdown()
        _verse_clean = (st.session_state.get("last_igehely") or "vazlat").replace(" ", "_").replace("/", "-").replace(",", "").replace(":", "-")
        _filename = f"emmaus-vazlat-{_verse_clean}-{datetime.now().strftime('%Y%m%d-%H%M')}.md"

        st.download_button(
            label="Vázlat letöltése (Markdown)",
            data=_md_payload,
            file_name=_filename,
            mime="text/markdown",
            use_container_width=False,
        )
    else:
        st.info("Még nincs vázlat.")

    refinement_chat("Prédikációvázlat", "outline", "outline_chat")


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
# EREDETI SZÖVEG
# =========================================================

with tabs[1]:
    st.header("Eredeti szöveg")
    st.caption("Görög / héber kulcsszavak a prédikációra készüléshez")

    igehely_orig = st.text_input(
        "Igeszakasz az eredeti nyelvi vizsgálathoz",
        placeholder="Pl. Jn 3,16 vagy 1Móz 1,1–3",
        key="original_verse"
    )

    _orig_running = bool(st.session_state.get("_original_running"))
    if st.button(
        "Eredeti szöveg elemzése",
        type="primary",
        key="original_run",
        disabled=_orig_running,
    ):
        if not st.session_state.get("api_key"):
            st.warning("Először add meg az API kulcsot a Beállítások fülön.")
        elif not igehely_orig:
            st.warning("Add meg az igeszakaszt.")
        else:
            st.session_state["_original_running"] = True
            try:
                with st.spinner("Eredeti nyelvi elemzés készül..."):
                    st.session_state["original_text"] = generate_text(
                        build_original_text_prompt(igehely_orig),
                        tab_label="Eredeti szöveg",
                    )
            finally:
                st.session_state["_original_running"] = False
            st.rerun()

    if st.session_state.get("original_text"):
        st.markdown(
            '<div class="result-box original-text-result">',
            unsafe_allow_html=True
        )
        st.markdown(st.session_state["original_text"])
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("Még nincs eredeti nyelvi elemzés.")

    refinement_chat("Eredeti szöveg", "original_text", "original_text_chat")

    _maybe_clear_note("original_note")
    note = st.text_area(
        "Mit szeretnél ebből megtartani a vázlathoz?",
        key="original_note"
    )

    if st.button("Hozzáadás a vázlatkosárhoz", key="original_add"):
        if note.strip():
            st.session_state["basket"].append(("Eredeti szöveg", note.strip()))
            _request_clear_note("original_note")
            st.success("Hozzáadva.")
            st.rerun()


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
        if not st.session_state.get("api_key"):
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

with tabs[10]:
    st.header("Beállítások")

    st.warning("Ha az API kulcs valaha megjelenik hibaüzenetben vagy képernyőképen, generálj újat a Google AI Studio-ban.")

    # ─── 1) Beépített közös kulcs státusza ────────────────────────────
    if BUILTIN_API_KEY:
        if st.session_state.get("using_builtin_key", False):
            st.success(
                "✓ **Beépített közös kulcs aktív.** Az Emmaus azonnal használható, "
                "nem kell saját kulcsot megadnod. Ha szeretnél, lent megadhatsz "
                "saját kulcsot — az felülírja a közöset."
            )
        else:
            st.info(
                "🔑 **Saját API kulcsot használsz.** Ha szeretnéd, visszaválthatsz "
                "a beépített közös kulcsra."
            )
            if st.button("Vissza a beépített közös kulcsra", key="restore_builtin_key"):
                st.session_state["api_key"] = BUILTIN_API_KEY
                st.session_state["using_builtin_key"] = True
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
        st.session_state["using_builtin_key"] = (new_key == BUILTIN_API_KEY)
        if st.session_state["using_builtin_key"]:
            st.success("Visszaállítva a közös kulcsra.")
        else:
            st.success("Saját API kulcs mentve erre a munkamenetre.")

    # ─── Modell — RÖGZÍTETT ─────────────────────────────────────────
    # Az alkalmazás csak a `gemini-2.5-flash` modellt használja.
    # A backend (`generate_text`) ezt kemény-érvényesíti, ezért itt
    # csak egy diszkrét read-only kijelzés szerepel — nincs választás.
    st.session_state["model_name"] = LOCKED_MODEL

    st.markdown(
        f"""
<div class="locked-model-row">
    <span class="locked-model-label">Gemini modell</span>
    <span class="locked-model-value">{LOCKED_MODEL_DISPLAY}
        <span class="locked-model-pill">rögzített</span>
    </span>
</div>
""",
        unsafe_allow_html=True,
    )
    _active_model_now = _get_active_model()
    if _active_model_now != LOCKED_MODEL:
        st.warning(
            f"⚠️ Az elsődleges modell ({LOCKED_MODEL_DISPLAY}) jelenleg **404 NotFound**-ot ad — "
            f"a fallback chain átváltott erre: **{MODEL_DISPLAY.get(_active_model_now, _active_model_now)}**. "
            "A munkamenet hátralévő részében ezt használja az alkalmazás. "
            "A `Cache törlése` után a következő próbálkozáskor visszaáll az elsődleges modellre.",
            icon="↩️",
        )
    st.caption(
        f"Az elsődleges modell `{LOCKED_MODEL}` — gyors, stabil, és a "
        "Google Search grounding (Aktualizálás modul) is elérhető hozzá. "
        f"404 esetén automatikus fallback: `{' → '.join(MODEL_FALLBACK_CHAIN)}`."
    )

    st.session_state["temperature"] = st.slider(
        "Kreativitás",
        0.0,
        1.0,
        float(st.session_state.get("temperature", 0.3)),
        0.1
    )

    st.session_state["max_tokens"] = st.slider(
        "Válaszhossz (max output token)",
        300,
        1500,
        int(st.session_state.get("max_tokens", 700)),
        50,
        help=(
            "Token-limit egyetlen Gemini válaszra. Alacsonyabb érték = "
            "gyorsabb válasz és kevesebb költség. Ajánlott: 600–900. "
            "Ha többre van szükséged, finomítsd a tartalmat a finomítás-chatben."
        ),
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
                "max-token beállítás) nem indít új API-hívást — a korábbi "
                "választ adja vissza azonnal. Csak az aktuális munkamenetre érvényes."
            ),
        )
    with cache_col2:
        cache_size = len(st.session_state.get("_call_cache", {}))
        st.metric("Cache-elt válaszok", cache_size)

    cc1, cc2 = st.columns(2)
    with cc1:
        if st.button("Cache törlése", key="clear_cache_btn", use_container_width=True):
            st.session_state["_call_cache"] = {}
            st.success("Cache kiürítve.")
            st.rerun()
    with cc2:
        if st.button(
            "Modell visszaállítása",
            key="reset_active_model_btn",
            use_container_width=True,
            help="Visszaállítja az aktív modellt az elsődlegesre (gemini-2.5-flash). Hasznos, ha 404 miatt fallback történt.",
        ):
            st.session_state["active_model"] = LOCKED_MODEL
            st.success(f"Aktív modell visszaállítva: {LOCKED_MODEL_DISPLAY}.")
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
        _active_now = _get_active_model()
        _active_display = MODEL_DISPLAY.get(_active_now, _active_now)
        _fallback_remaining = MODEL_FALLBACK_CHAIN[MODEL_FALLBACK_CHAIN.index(_active_now) + 1:] if _active_now in MODEL_FALLBACK_CHAIN else []
        st.caption(
            f"Session: `{_get_session_id()}` · "
            f"Kulcs: `{_mask_api_key(st.session_state.get('api_key', ''))}` "
            f"({'built-in' if st.session_state.get('using_builtin_key') else 'saját' if st.session_state.get('api_key') else '—'}) · "
            f"Aktív modell: **{_active_display}**"
            + (f" · Fallback még elérhető: {', '.join(_fallback_remaining)}" if _fallback_remaining else " · (utolsó modell a láncban)")
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
    _ws_filename = f"emmaus-munka-{_ws_verse}-{datetime.now().strftime('%Y%m%d-%H%M')}.json"

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
        for k in WORKSPACE_STR_KEYS:
            st.session_state[k] = ""
        for k in WORKSPACE_LIST_KEYS:
            st.session_state[k] = []
        st.success("A munkamenet törölve.")
        st.rerun()

    st.divider()
    st.subheader("Hogyan igényelhetsz saját Gemini API kulcsot?")
    st.caption("Lépésről lépésre — a folyamat teljesen ingyenes, és csak egy Google-fiók (Gmail cím) szükséges hozzá.")

    st.markdown(
        """
<div class="result-box api-guide-box">

A saját kulcs használata biztosítja, hogy az **Emmaus** hosszú távon is
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

6. **Illeszd be az Emmausba.**
   Gyere vissza ide a **Beállításokhoz**, és illeszd be a kulcsot
   a fenti **„Gemini API kulcs"** mezőbe.

</div>
""",
        unsafe_allow_html=True,
    )

    st.divider()
    st.caption(f"Emmaus v{APP_VERSION} · digitális homiletikai műhely")


# =========================================================
# LÁBLÉC — ARS POETICA / MŰHELYREND
# =========================================================

st.markdown(
    f"""
<div class="ars-section ars-footer">
    <div class="ars-poetica">
        <strong>Emmaus Műhely v{APP_VERSION}</strong><br>
        Az Emmaus jelenleg ingyenesen használható, a legújabb
        <em>{LOCKED_MODEL_DISPLAY}</em> nyelvi modell támogatásával.
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
            <div class="ars-station-title">Keress bizalommal</div>
            <div class="ars-station-text">
                Használd bátran a munkádhoz! Észrevétel, ötlet vagy tapasztalat:<br>
                📧 <a href="mailto:hoverzsolt@gmail.com">hoverzsolt@gmail.com</a><br>
                🔵 <a href="https://www.facebook.com/" target="_blank" rel="noopener">Facebook: Zsolt Hover</a>
            </div>
        </div>
    </div>
</div>
""",
    unsafe_allow_html=True,
)
