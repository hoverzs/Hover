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

/* Gyorseszközök tabok: chip-fal helyett rendezett eszközrács-hatás */
.stTabs [data-baseweb="tab-list"] {
    display: grid !important;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 0.45rem !important;
}

.stTabs [data-baseweb="tab"] {
    min-height: 3rem !important;
    border-radius: var(--tx-radius-md) !important;
    border: 1px solid var(--tx-border) !important;
    background: var(--tx-surface) !important;
    justify-content: flex-start !important;
    text-align: left !important;
    padding: 0.55rem 0.75rem !important;
    box-shadow: none !important;
    font-weight: 550 !important;
}

.stTabs [aria-selected="true"][data-baseweb="tab"] {
    background: linear-gradient(
        120deg,
        var(--tx-primary-soft),
        rgba(255, 249, 240, 0.8)
    ) !important;
    border-color: rgba(90, 122, 168, 0.42) !important;
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
    .stTabs [data-baseweb="tab-list"] {
        grid-template-columns: 1fr 1fr !important;
    }
}

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
""".strip()

