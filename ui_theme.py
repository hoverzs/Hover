"""Premium UX 2.0 design tokens és közös felületi stílusok.

Csak vizuális finomhangolás: nem módosít üzleti logikát.
"""

from __future__ import annotations


def premium_tokens_css() -> str:
    """Központi UI-tokenek (színek, térközök, radiusok, árnyékok)."""
    return """
:root {
    --tx-bg: #f5eee2;
    --tx-surface: rgba(255, 251, 244, 0.74);
    --tx-surface-strong: rgba(255, 251, 244, 0.9);
    --tx-primary: #5a7aa8;
    --tx-primary-deep: #1f334d;
    --tx-primary-soft: rgba(232, 238, 247, 0.72);
    --tx-gold: #8a6a3f;
    --tx-text: #2f2a24;
    --tx-text-muted: #5d5347;
    --tx-border: rgba(170, 145, 112, 0.28);
    --tx-success: #6f9a78;
    --tx-warning: #b2853e;
    --tx-danger: #a65d48;
    --tx-neutral: #8d8378;

    --tx-space-xs: 0.25rem;
    --tx-space-sm: 0.5rem;
    --tx-space-md: 0.75rem;
    --tx-space-lg: 1rem;
    --tx-space-xl: 1.5rem;

    --tx-radius-sm: 8px;
    --tx-radius-md: 12px;
    --tx-radius-lg: 18px;

    --tx-shadow-soft: 0 6px 16px rgba(58, 40, 22, 0.1);
    --tx-shadow-float: 0 14px 30px rgba(38, 25, 10, 0.18);
}
""".strip()


def premium_overlay_css() -> str:
    """Globális, alkalmazásszintű finomhangolás a meglévő stílus fölött."""
    return """
/* ===== Premium UX 2.0 overlay ===== */
.tx-page-intro {
    margin: 0.25rem 0 0.95rem;
    padding: 0.75rem 0 0.4rem;
}

.tx-intro-eyebrow {
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    color: var(--tx-gold);
    margin-bottom: 0.25rem;
    text-transform: uppercase;
}

.tx-intro-title {
    font-family: "Playfair Display", "Cormorant Garamond", Georgia, serif;
    font-size: clamp(1.5rem, 2.8vw, 2rem);
    line-height: 1.2;
    margin: 0;
    color: #2a2117;
}

.tx-intro-body {
    margin-top: 0.35rem;
    font-family: "Lora", Georgia, serif;
    font-size: 1rem;
    line-height: 1.55;
    color: var(--tx-text-muted);
    max-width: 74ch;
}

.tx-status-badge {
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    padding: 0.17rem 0.58rem;
    margin: 0.15rem 0;
    font-size: 0.78rem;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-weight: 600;
    letter-spacing: 0.01em;
    border: 1px solid transparent;
}

.tx-status-neutral { background: rgba(140, 132, 120, 0.14); color: #5d5347; border-color: rgba(140,132,120,0.24); }
.tx-status-info { background: rgba(90, 122, 168, 0.14); color: var(--tx-primary-deep); border-color: rgba(90,122,168,0.28); }
.tx-status-success { background: rgba(111, 154, 120, 0.14); color: #3d5a45; border-color: rgba(111,154,120,0.28); }
.tx-status-warning { background: rgba(178, 133, 62, 0.15); color: #6d4b1f; border-color: rgba(178,133,62,0.28); }
.tx-status-danger { background: rgba(166, 93, 72, 0.14); color: #6e2e1f; border-color: rgba(166,93,72,0.3); }

.tx-panel {
    border-radius: var(--tx-radius-md);
    border: 1px solid var(--tx-border);
    background: var(--tx-surface);
    box-shadow: var(--tx-shadow-soft);
    padding: 0.62rem 0.82rem;
    margin: 0.25rem 0 0.7rem;
}
.tx-panel-title {
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.9rem;
    font-weight: 650;
    margin-bottom: 0.2rem;
}
.tx-panel-body {
    font-family: "Lora", Georgia, serif;
    font-size: 0.96rem;
    line-height: 1.5;
}
.tx-panel-info { border-left: 3px solid var(--tx-primary); }
.tx-panel-success { border-left: 3px solid var(--tx-success); }
.tx-panel-warning { border-left: 3px solid var(--tx-warning); }
.tx-panel-danger { border-left: 3px solid var(--tx-danger); }
.tx-panel-neutral { border-left: 3px solid var(--tx-neutral); }

.block-container {
    max-width: 1280px !important;
}

.main-card {
    border-radius: 24px !important;
    padding: 1.6rem 1.9rem 1.35rem !important;
    box-shadow: var(--tx-shadow-soft) !important;
    border: 1px solid var(--tx-border) !important;
}

.main-card:hover {
    transform: translateY(-2px) !important;
    box-shadow: var(--tx-shadow-float) !important;
}

.header-grid {
    grid-template-columns: 220px 1fr !important;
    gap: 1rem !important;
}

.header-logo .main-logo {
    width: 220px !important;
}

.main-title {
    font-size: clamp(2.35rem, 4.2vw, 3.3rem) !important;
    letter-spacing: 0.09em !important;
}

.version-line {
    letter-spacing: 0.08em !important;
    font-size: 0.84rem !important;
}

.header-caption {
    letter-spacing: 0.03em !important;
    text-transform: none !important;
    font-weight: 600 !important;
}

.subtitle {
    margin-top: 0.35rem !important;
    line-height: 1.48 !important;
    max-width: 72ch !important;
}

.scripture-ref {
    margin-top: 0.25rem !important;
}

/* Gyorseszközök tabok: chip-fal helyett rendezett eszközkártya-rács (max 4 oszlop) */
.stTabs [data-baseweb="tab-list"] {
    display: grid !important;
    grid-template-columns: repeat(4, minmax(0, 1fr)) !important;
    gap: 0.5rem !important;
    border-bottom: none !important;
}

.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] {
    display: none !important;
}

.stTabs [data-baseweb="tab"] {
    min-height: 72px !important;
    height: auto !important;
    border-radius: var(--tx-radius-md) !important;
    border: 1px solid var(--tx-border) !important;
    background:
        linear-gradient(165deg, rgba(255, 252, 247, 0.82), rgba(238, 230, 216, 0.5)) !important;
    justify-content: flex-start !important;
    text-align: left !important;
    align-items: center !important;
    padding: 0.7rem 0.9rem !important;
    box-shadow: none !important;
    font-weight: 550 !important;
    white-space: normal !important;
    line-height: 1.25 !important;
    transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}

.stTabs [data-baseweb="tab"]:hover {
    transform: translateY(-1px) !important;
    box-shadow: var(--tx-shadow-soft) !important;
}

/* Teljes cím: két sorra törhet, nincs levágás / ellipszis */
.stTabs [data-baseweb="tab"] [data-testid="stMarkdownContainer"] p,
.stTabs [data-baseweb="tab"] p {
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
    font-size: 0.9rem !important;
    line-height: 1.22 !important;
    margin: 0 !important;
}

.stTabs [aria-selected="true"][data-baseweb="tab"] {
    background: linear-gradient(
        120deg,
        var(--tx-primary-soft),
        rgba(255, 249, 240, 0.8)
    ) !important;
    border-color: rgba(90, 122, 168, 0.45) !important;
    color: var(--tx-primary-deep) !important;
    box-shadow: 0 1px 0 rgba(255, 255, 255, 0.7) inset, var(--tx-shadow-soft) !important;
}

.stTabs [data-baseweb="tab"]:hover {
    border-color: rgba(90, 122, 168, 0.36) !important;
}

[data-testid="stTextInput"] > label,
[data-testid="stTextArea"] > label,
[data-testid="stSelectbox"] > label {
    margin-bottom: 0.25rem !important;
}

.stTextInput input,
.stTextArea textarea,
.stSelectbox [data-baseweb="select"] > div {
    border-radius: var(--tx-radius-md) !important;
}

.stExpander {
    border: 1px solid var(--tx-border) !important;
    border-radius: var(--tx-radius-md) !important;
    background: var(--tx-surface) !important;
}

/* ===== Egységes gombhierarchia (alap magasság; scoped nav felülírja) ===== */
.stButton > button {
    min-height: 2.75rem !important;
    border-radius: var(--tx-radius-md) !important;
    font-weight: 600 !important;
    transition: transform 0.14s ease, box-shadow 0.14s ease, background 0.14s ease, border-color 0.14s ease;
}
.stButton > button:focus-visible {
    outline: 2px solid rgba(90, 122, 168, 0.55) !important;
    outline-offset: 2px !important;
}

/* ===== Tartalmi felületek és üzenetek ===== */
/* Szakaszcím (H2/H3) egységes, visszafogott méret */
.stMarkdown h2, [data-testid="stHeading"] h2 {
    font-size: 1.55rem !important;
    line-height: 1.25 !important;
    letter-spacing: 0 !important;
}
.stMarkdown h3, [data-testid="stHeading"] h3 {
    font-size: 1.2rem !important;
    line-height: 1.3 !important;
}

/* Információs panelek: finom, bal kék sáv, nem csupa félkövér, nem harsány */
[data-testid="stAlert"] {
    border-radius: var(--tx-radius-md) !important;
    border: 1px solid var(--tx-border) !important;
    border-left: 3px solid var(--tx-primary) !important;
    box-shadow: none !important;
    padding: 0.65rem 0.9rem !important;
}
[data-testid="stAlertContentSuccess"] { }
[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) { border-left-color: var(--tx-success) !important; }
[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) { border-left-color: var(--tx-warning) !important; }
[data-testid="stAlert"]:has([data-testid="stAlertContentError"]) { border-left-color: var(--tx-danger) !important; }
[data-testid="stAlert"] p {
    font-weight: 500 !important;
    text-transform: none !important;
    letter-spacing: 0 !important;
    font-size: 0.95rem !important;
    line-height: 1.5 !important;
}

@media (max-width: 1024px) {
    .block-container {
        max-width: 100% !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
    .header-grid {
        grid-template-columns: 1fr !important;
        text-align: center !important;
    }
    .header-logo .main-logo {
        width: 180px !important;
    }
}

@media (max-width: 768px) {
    .main-card {
        padding: 1rem 1rem 0.95rem !important;
        border-radius: 18px !important;
    }
    .main-title {
        font-size: 2.1rem !important;
    }
}

/* Gyorseszközök: közepes képernyőn 2 oszlop */
@media (max-width: 1024px) {
    .stTabs [data-baseweb="tab-list"] {
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
    }
}

/* Gyorseszközök: mobilon 1 oszlop */
@media (max-width: 560px) {
    .stTabs [data-baseweb="tab-list"] {
        grid-template-columns: 1fr !important;
    }
}

/* Shell polish: projekttoolbar gap + címmező */
.element-container:has(.ws-project-toolbar-anchor) + .element-container [data-testid="stHorizontalBlock"] {
    gap: 0.45rem !important;
    column-gap: 0.45rem !important;
    justify-content: flex-start !important;
}

.element-container:has(.ws-project-toolbar-anchor) + .element-container [data-testid="column"] .stButton > button {
    width: auto !important;
    min-width: 7.5rem !important;
}

/* Segmented nav: Streamlit piros indikátor kiütése (theme primary mellett is) */
[data-testid="stSegmentedControl"] button {
    outline: none !important;
}
[data-testid="stSegmentedControl"] button[aria-checked="true"] {
    color: #1f334d !important;
}

/* ===== Kompakt munkafolyamat-navigáció ===== */
.tx-workflow-anchor { display: none !important; height: 0 !important; margin: 0 !important; }

.element-container:has(.tx-workflow-anchor) + .element-container [data-testid="stHorizontalBlock"] {
    align-items: center !important;
    background:
        linear-gradient(165deg, rgba(255, 252, 247, 0.8), rgba(238, 230, 216, 0.5)) !important;
    border: 1px solid rgba(186, 158, 122, 0.4) !important;
    border-radius: 14px !important;
    padding: 0.6rem 0.85rem !important;
    box-shadow: 0 1px 0 rgba(255, 255, 255, 0.6) inset, 0 6px 14px rgba(58, 40, 22, 0.06) !important;
    margin-top: 0.35rem !important;
}

.tx-wf-bar { display: flex; flex-direction: column; gap: 0.05rem; }
.tx-wf-eyebrow {
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--tx-gold);
}
.tx-wf-title {
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 1.05rem;
    font-weight: 650;
    color: #1f334d;
    line-height: 1.2;
}
.tx-wf-count {
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.82rem;
    color: var(--tx-text-muted);
}

/* Workflow gombok: kompakt, egységes magasság */
.element-container:has(.tx-workflow-anchor) + .element-container .stButton > button {
    min-height: 2.6rem !important;
    border-radius: 10px !important;
}

/* Vékony, visszafogott haladássáv */
.tx-wf-progress {
    height: 4px;
    width: 100%;
    background: rgba(160, 140, 115, 0.22);
    border-radius: 999px;
    margin: 0.5rem 0 0.25rem;
    overflow: hidden;
}
.tx-wf-progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #5a7aa8, #7c96b8);
    border-radius: 999px;
    transition: width 0.3s ease;
}
.tx-wf-progress-note {
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.78rem;
    color: var(--tx-text-muted);
    margin-bottom: 0.6rem;
}

/* Lépéslista a popoverben: egyetlen oszlop, teljes sor kattintható */
[data-testid="stPopover"] .stButton > button,
div[data-baseweb="popover"] .stButton > button {
    justify-content: flex-start !important;
    text-align: left !important;
    min-height: 2.5rem !important;
    border-radius: 9px !important;
    white-space: normal !important;
    font-weight: 500 !important;
}

@media (max-width: 768px) {
    .element-container:has(.tx-workflow-anchor) + .element-container [data-testid="stHorizontalBlock"] {
        flex-direction: column !important;
        align-items: stretch !important;
        gap: 0.5rem !important;
    }
    .element-container:has(.tx-workflow-anchor) + .element-container [data-testid="column"] {
        width: 100% !important;
        flex: 1 1 100% !important;
    }
}
""".strip()

