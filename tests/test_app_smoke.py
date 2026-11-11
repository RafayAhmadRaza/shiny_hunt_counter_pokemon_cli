import re
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import functions as tracker

ROOT = Path(__file__).resolve().parents[1]

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U0000FE0F"
    "\U00002B00-\U00002BFF"
    "]"
)


def test_app_boots_and_creates_current_schema(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    app = AppTest.from_file(str(ROOT / "main.py"), default_timeout=60)
    app.run()

    assert not app.exception
    assert app.title[0].value == "Shiny Hunt Tracker"
    assert any(subheader.value == "Phase history" for subheader in app.subheader)

    hunts = pd.read_csv(tmp_path / "hunts.csv")
    phases = pd.read_csv(tmp_path / "phased.csv")
    assert list(hunts.columns) == tracker.HUNT_COLUMNS
    assert list(phases.columns) == tracker.PHASE_COLUMNS


def test_app_add_hunt_form_creates_functional_hunt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    app = AppTest.from_file(str(ROOT / "main.py"), default_timeout=60)
    app.run()

    app.selectbox(key="new_game").select("Black 2")
    app.run()
    app.selectbox(key="new_method_Black 2").set_value("breeding")
    app.run()

    app.text_input(key="new_name").set_value("Deino")
    app.checkbox(key="new_charm").check()
    app.checkbox(key="new_masuda").check()
    app.button[0].click()
    app.run()

    assert not app.exception

    hunts = pd.read_csv(tmp_path / "hunts.csv")
    assert len(hunts) == 1
    row = hunts.iloc[0]
    assert row["name"] == "Deino"
    assert row["game"] == "Black 2"
    assert row["generation"] == 5
    assert row["encounter_method"] == "breeding"
    assert bool(row["shiny_charm"]) is True
    assert bool(row["masuda_method"]) is True


def test_app_masuda_tracks_game_and_method_switches(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    app = AppTest.from_file(str(ROOT / "main.py"), default_timeout=60)
    app.run()

    # Platinum: Masuda becomes selectable only after choosing breeding.
    app.selectbox(key="new_game").select("Platinum")
    app.run()
    assert app.checkbox(key="new_masuda").disabled is True

    app.selectbox(key="new_method_Platinum").set_value("breeding")
    app.run()
    assert app.checkbox(key="new_masuda").disabled is False

    # Switching back to wild must disable it again without locking it forever.
    app.selectbox(key="new_method_Platinum").set_value("wild")
    app.run()
    assert app.checkbox(key="new_masuda").disabled is True

    app.selectbox(key="new_method_Platinum").set_value("breeding")
    app.run()
    assert app.checkbox(key="new_masuda").disabled is False

    # Black supports breeding and Masuda but has no Shiny Charm.
    app.selectbox(key="new_game").select("Black")
    app.run()
    app.selectbox(key="new_method_Black").set_value("breeding")
    app.run()
    assert app.checkbox(key="new_masuda").disabled is False
    assert app.checkbox(key="new_charm").disabled is True

    # B2W2 supports both, including the combined eight-roll case.
    app.selectbox(key="new_game").select("Black 2")
    app.run()
    app.selectbox(key="new_method_Black 2").set_value("breeding")
    app.run()
    assert app.checkbox(key="new_masuda").disabled is False
    assert app.checkbox(key="new_charm").disabled is False

    # Sword/Shield and Scarlet/Violet support both.
    for game in ("Sword", "Scarlet"):
        app.selectbox(key="new_game").select(game)
        app.run()
        app.selectbox(key=f"new_method_{game}").set_value("breeding")
        app.run()
        assert app.checkbox(key="new_masuda").disabled is False
        assert app.checkbox(key="new_charm").disabled is False

    # Modern games without breeding must not offer Masuda at all.
    for game in ("Legends: Arceus", "Legends: Z-A"):
        app.selectbox(key="new_game").select(game)
        app.run()
        method_box = app.selectbox(key=f"new_method_{game}")
        assert "breeding" not in method_box.options
        assert app.checkbox(key="new_masuda").disabled is True
        assert app.checkbox(key="new_charm").disabled is False


def test_app_gen3_games_cannot_enable_masuda(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    app = AppTest.from_file(str(ROOT / "main.py"), default_timeout=60)
    app.run()

    for game in ("Ruby", "Sapphire", "Emerald", "FireRed", "LeafGreen"):
        app.selectbox(key="new_game").select(game)
        app.run()
        method_box = app.selectbox(key=f"new_method_{game}")
        assert "Breeding (eggs)" in method_box.options, game
        method_box.set_value("breeding")
        app.run()
        assert app.checkbox(key="new_masuda").disabled is True, game

    # A Gen III hunt created while breeding is selected keeps the base roll.
    app.text_input(key="new_name").set_value("Pikachu")
    app.button[0].click()
    app.run()

    assert not app.exception
    hunts = pd.read_csv(tmp_path / "hunts.csv")
    row = hunts.iloc[0]
    assert row["game"] == "LeafGreen"
    assert row["encounter_method"] == "breeding"
    assert bool(row["masuda_method"]) is False

    pokemon = tracker.Pokemon.from_row(row)
    result = tracker.hunt_odds(pokemon)
    assert result.total_rolls == 1
    assert result.masuda_applied is False
    assert result.one_in == pytest.approx(8192)


def test_app_carries_method_and_masuda_across_supported_games(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)

    app = AppTest.from_file(str(ROOT / "main.py"), default_timeout=60)
    app.run()

    app.selectbox(key="new_game").select("Platinum")
    app.run()
    app.selectbox(key="new_method_Platinum").set_value("breeding")
    app.run()

    # Black 2 also supports breeding and Masuda, so the method carries over
    # instead of silently resetting to wild encounters.
    app.selectbox(key="new_game").select("Black 2")
    app.run()
    assert app.selectbox(key="new_method_Black 2").value == "breeding"
    assert app.checkbox(key="new_masuda").disabled is False


def test_app_creates_platinum_masuda_hunt_with_five_rolls(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    app = AppTest.from_file(str(ROOT / "main.py"), default_timeout=60)
    app.run()
    app.selectbox(key="new_game").select("Platinum")
    app.run()
    app.selectbox(key="new_method_Platinum").set_value("breeding")
    app.run()
    app.text_input(key="new_name").set_value("Riolu")
    app.checkbox(key="new_masuda").check()
    app.button[0].click()
    app.run()

    assert not app.exception
    hunts = pd.read_csv(tmp_path / "hunts.csv")
    row = hunts.iloc[0]
    assert row["game"] == "Platinum"
    assert row["encounter_method"] == "breeding"
    assert bool(row["masuda_method"]) is True
    assert bool(row["shiny_charm"]) is False

    pokemon = tracker.Pokemon.from_row(row)
    result = tracker.hunt_odds(pokemon)
    assert result.total_rolls == 5
    assert result.one_in == pytest.approx(1638.83, rel=1e-4)


def test_ui_source_contains_no_emoji_characters():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert EMOJI_PATTERN.search(source) is None
