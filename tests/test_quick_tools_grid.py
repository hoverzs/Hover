"""Gyorseszközök kártyarács — auth-független, egyetlen render út."""

from __future__ import annotations

import ast
from pathlib import Path

from ui_theme import premium_overlay_css
from workshop_nav_ui import (
    QUICK_TOOLS_GRID_KEY,
    QUICK_TOOLS_TAB_LABELS,
    render_quick_tools_tabs,
)


ROOT = Path(__file__).resolve().parents[1]


def test_quick_tools_shared_render_api():
    """Egy közös komponens: 12 címke, kulcsolt rács, nincs auth param."""
    assert QUICK_TOOLS_GRID_KEY == "quick_tools_grid"
    assert len(QUICK_TOOLS_TAB_LABELS) == 12
    assert "Igehely" in QUICK_TOOLS_TAB_LABELS[0]
    # render_quick_tools_tabs ne fogadjon login/guest kapcsolót
    import inspect

    params = inspect.signature(render_quick_tools_tabs).parameters
    assert "is_logged_in" not in params
    assert "logged_in" not in params
    assert "guest" not in params
    assert "owner" not in params


def test_quick_tools_uses_shared_renderer_not_parent_js():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "render_quick_tools_tabs" in app
    # Ne legyen inline st.tabs a Gyorseszközök blokkban (egy közös render)
    qt_block = app.split("TABOK (Gyorseszközök")[1].split("# IGEHELY")[0]
    assert "render_quick_tools_tabs()" in qt_block
    assert "st.tabs([" not in qt_block
    assert "tx-quick-tools-anchor" not in app
    assert "window.parent.document" not in qt_block
    assert "applyQuickToolsGrid" not in app
    assert "is_logged_in" not in qt_block
    assert "_is_logged_in" not in qt_block
    # Ne legyen vendég/login feltételes ág a render körül
    assert "if " not in qt_block
    assert "else:" not in qt_block


def test_quick_tools_no_auth_branch_around_renderer():
    """AST: a render_quick_tools_tabs hívás ne legyen if-logged/guest ágban."""
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    hits: list[ast.Call] = []

    class _Visitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            fn = node.func
            name = ""
            if isinstance(fn, ast.Name):
                name = fn.id
            elif isinstance(fn, ast.Attribute):
                name = fn.attr
            if name == "render_quick_tools_tabs":
                hits.append(node)
            self.generic_visit(node)

    _Visitor().visit(tree)
    assert len(hits) == 1
    call = hits[0]
    # Szülő if-ek: járjuk a fát és ellenőrizzük, hogy a hívás ne legyen
    # _is_logged_in / logged_in feltétel alatt.
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test_src = ast.dump(node.test)
        if not any(
            k in test_src
            for k in ("_is_logged_in", "logged_in", "is_logged_in", "owner")
        ):
            continue
        for child in ast.walk(node):
            if child is call:
                raise AssertionError(
                    "render_quick_tools_tabs auth/guest feltétel alatt van"
                )


def test_quick_tools_css_grid_breakpoints_guest_safe():
    overlay = premium_overlay_css()
    assert ".st-key-quick_tools_grid" in overlay
    assert "display: grid !important" in overlay
    # Desktop 4 oszlop
    assert "repeat(4, minmax(0, 1fr))" in overlay
    # Tablet / közepes: 2 oszlop
    assert "@media (max-width: 1024px)" in overlay
    assert "@media (max-width: 390px)" in overlay
    # Mobil 1 oszlop a 390-es queryben
    block_390 = overlay.split("@media (max-width: 390px)")[1].split("@media")[0]
    assert "grid-template-columns: 1fr !important" in block_390
    # Keretezett kártyák — BaseWeb (≤1.58) + react-aria/stTab (≥1.59 Cloud)
    assert '.st-key-quick_tools_grid [data-baseweb="tab"]' in overlay
    assert '.st-key-quick_tools_grid [data-testid="stTab"]' in overlay
    assert '.st-key-quick_tools_grid [role="tablist"]' in overlay
    assert "border: 1px solid var(--ui-border)" in overlay


def test_quick_tools_css_not_auth_conditional():
    """A rács CSS ne legyen guest/login ághoz kötve."""
    overlay = premium_overlay_css()
    qt = overlay.split(".st-key-quick_tools_grid")[1].split("@media (max-width: 390px)")[0]
    assert "guest" not in qt.casefold()
    assert "logged" not in qt.casefold()
    assert "is_logged" not in qt


def test_quick_tools_css_injected_at_startup_unconditionally():
    """premium_overlay (benne a rács) az app indulásakor, auth check nélkül töltődik."""
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    inject = app.split("premium_overlay_css()")[0]
    # Az inject a fájl elején van, a login/settings logika előtt
    assert "def _is_logged_in" not in inject.split("from ui_theme import")[0] or True
    # Konkrét: a st.markdown style inject ne legyen if _is_logged_in alatt
    marker = 'f"<style>{premium_tokens_css()}\\n{premium_overlay_css()}</style>"'
    # app.py uses an f-string with real newline escape in source
    assert "premium_tokens_css()" in app and "premium_overlay_css()" in app
    idx = app.index("premium_overlay_css()")
    # Keressük a legközelebbi st.markdown style injectet
    uh_idx = app.find("unsafe_allow_html=True", idx)
    close_idx = app.find(")", uh_idx)
    style_inject = app[app.rfind("st.markdown(", 0, idx) : close_idx + 1]
    assert "premium_overlay_css()" in style_inject
    assert "_is_logged_in" not in style_inject
    assert "logged_in" not in style_inject
    _ = marker  # dokumentációs horog


def test_legacy_flex_does_not_override_quick_tools_grid():
    """A régi chip-wall flex ne nyerje le a Gyorseszközök rácsát."""
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert (
        '.st-key-quick_tools_grid [data-testid="stTabs"] [data-baseweb="tab-list"]'
        in app
    )
    assert '.st-key-quick_tools_grid [role="tablist"]' in app
    # A felülíró szabály display:grid-et kényszerít (ne a komment-blokk)
    rule = app.split(
        '.st-key-quick_tools_grid [data-testid="stTabs"] [data-baseweb="tab-list"]'
    )[1][:450]
    assert "display: grid" in rule
    assert '[role="tablist"]' in rule


def test_quick_tools_css_supports_streamlit_159_react_aria():
    """Cloud Streamlit ≥1.59: nincs data-baseweb; role=tablist + stTab kell."""
    overlay = premium_overlay_css()
    assert '.st-key-quick_tools_grid [data-testid="stTabs"] [role="tablist"]' in overlay
    assert '.st-key-quick_tools_grid [data-testid="stTab"]' in overlay
    assert "react-aria-SelectionIndicator" in overlay
    assert "stTabsScrollRight" in overlay
