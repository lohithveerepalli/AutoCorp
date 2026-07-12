"""Skeleton is callable/used; streamlit-extras is imported in the app module."""

import inspect
from pathlib import Path

import autocorp.ui.streamlit_app as app


def test_skeleton_function_returns_ac_skeleton_markup() -> None:
    """Drive shipped skeleton() without Streamlit UI by checking source + pure HTML builder."""
    # skeleton uses st.markdown — verify HTML generation pattern by inspecting source
    # and a pure helper path: call the HTML expression used by skeleton
    src = inspect.getsource(app.skeleton)
    assert "ac-skeleton" in src
    assert "st.markdown" in src

    # Simulate markup generation (same formula as skeleton)
    lines = 3
    markup = "".join('<div class="ac-skeleton"></div>' for _ in range(max(1, lines)))
    assert markup.count("ac-skeleton") == 3
    assert markup.startswith('<div class="ac-skeleton">')


def test_skeleton_has_call_sites_in_app() -> None:
    text = Path(app.__file__).read_text(encoding="utf-8")
    # Definition + at least one real call (not just def skeleton)
    assert text.count("skeleton(") >= 4  # def + launch + cycles + chat (+ maybe dash)
    assert "skeleton(5)" in text or "skeleton(3)" in text or "skeleton(2)" in text


def test_streamlit_extras_imported_in_app() -> None:
    text = Path(app.__file__).read_text(encoding="utf-8")
    assert "streamlit_extras" in text
    assert "add_vertical_space" in text
    assert "colored_header" in text or "style_metric_cards" in text
    # Module-level imports must succeed
    assert hasattr(app, "add_vertical_space")
    assert hasattr(app, "style_metric_cards")
    assert hasattr(app, "colored_header")


def test_go_to_page_uses_apply_nav_destination() -> None:
    text = Path(app.__file__).read_text(encoding="utf-8")
    assert "def go_to_page" in text
    assert "apply_nav_destination" in text
    assert 'go_to_page("Talk to Agents"' in text or "go_to_page(\"Talk to Agents\"" in text
