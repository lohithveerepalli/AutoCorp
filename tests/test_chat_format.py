"""Chat bubble formatting preserves newlines (shipped format_chat_html)."""

from pathlib import Path

from autocorp.ui.streamlit_app import format_chat_html


def test_format_chat_html_escapes_and_preserves_newlines() -> None:
    raw = "Line 1\nLine 2\n<script>x</script>"
    out = format_chat_html(raw)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "<br>" in out
    assert "Line 1" in out and "Line 2" in out
    # Newlines become <br>\n so CSS pre-wrap and HTML both work
    assert out.count("<br>") >= 2


def test_css_has_pre_wrap_on_chat_bubbles() -> None:
    css = (
        Path(__file__).resolve().parents[1]
        / "autocorp"
        / "ui"
        / "assets"
        / "streamlit_theme.css"
    ).read_text(encoding="utf-8")
    assert "white-space: pre-wrap" in css
    assert ".ac-chat-body" in css
    assert ".ac-chat-user" in css and ".ac-chat-agent" in css


def test_streamlit_uses_format_chat_html() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "autocorp"
        / "ui"
        / "streamlit_app.py"
    ).read_text(encoding="utf-8")
    assert "format_chat_html" in src
    assert "format_chat_html(m.content)" in src
    # Must not only raw-escape without formatter in bubble body
    assert "ac-chat-body" in src