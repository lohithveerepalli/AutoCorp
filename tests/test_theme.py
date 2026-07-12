"""Theme preference persistence — drives shipped theme module."""

from pathlib import Path

from autocorp.ui.theme import (
    DEFAULT_THEME,
    get_theme_preference,
    set_theme_preference,
    theme_css_variables,
    toggle_theme_preference,
)


def test_default_theme_is_dark(tmp_path: Path) -> None:
    path = tmp_path / "ui_theme.json"
    assert get_theme_preference(path) == DEFAULT_THEME == "dark"


def test_set_and_get_theme_persists(tmp_path: Path) -> None:
    path = tmp_path / "ui_theme.json"
    assert set_theme_preference("light", path) == "light"
    assert path.exists()
    assert get_theme_preference(path) == "light"
    assert set_theme_preference("dark", path) == "dark"
    assert get_theme_preference(path) == "dark"


def test_toggle_theme(tmp_path: Path) -> None:
    path = tmp_path / "ui_theme.json"
    set_theme_preference("dark", path)
    assert toggle_theme_preference(path) == "light"
    assert toggle_theme_preference(path) == "dark"


def test_css_variables_for_both_themes() -> None:
    dark = theme_css_variables("dark")
    light = theme_css_variables("light")
    assert dark["--ac-bg"] != light["--ac-bg"]
    assert "--ac-accent" in dark and "--ac-accent" in light
