import os
from pathlib import Path

import pandas as pd
import pytest

import functions as tracker
from shiny_mechanics import BREEDING, SUPPORTED_GAMES, get_mechanics
from functions import (
    ConcurrentUpdateError,
    DuplicateHuntError,
    Phased,
    Pokemon,
    TrackerError,
    TransactionError,
    ValidationError,
    add_encounter,
    calulate_probability,
    create_csv,
    create_phase_csv,
    custom_add_encounter,
    custom_remove_encounter,
    delete_hunt,
    from_csv_to_Pokemon,
    group_phases_by_hunt,
    hunt_odds,
    load_hunts,
    load_phases,
    migrate_csvs,
    new_hunt,
    next_phase_number,
    phase_summary,
    phases_for_hunt,
    record_phase,
    remove_encounter,
    remove_hunt_from_csv,
    save_hunt_to_csv,
    update_hunt_in_csv,
    validate_phase_input,
)


@pytest.fixture
def paths(tmp_path):
    return tmp_path / "hunts.csv", tmp_path / "phased.csv"


def make_hunt(paths, name="Axew", game="Black 2", **kwargs):
    hunts_path, phases_path = paths
    pokemon = new_hunt(name=name, game=game, csv_path=str(hunts_path), **kwargs)
    create_phase_csv(str(phases_path), str(hunts_path))
    return pokemon


def set_count(paths, pokemon, count):
    hunts_path, _ = paths
    pokemon.encounter_count = count
    return update_hunt_in_csv(pokemon, load_hunts(str(hunts_path)), str(hunts_path))


# ---------------------------------------------------------------------------
# Schema, round-trip and validation
# ---------------------------------------------------------------------------


def test_new_hunt_derives_generation_and_schema(paths):
    hunts_path, phases_path = paths
    pokemon = make_hunt(paths, "Bulbasaur", "FireRed")

    assert pokemon.generation == 3
    assert pokemon.odds == 8192
    assert pokemon.encounter_method == "wild"
    assert pokemon.masuda_method is False

    dataframe = load_hunts(str(hunts_path))
    assert list(dataframe.columns) == tracker.HUNT_COLUMNS
    assert dataframe.iloc[0]["hunt_id"] == pokemon.hunt_id
    assert dataframe.iloc[0]["generation"] == 3

    phases = create_phase_csv(str(phases_path), str(hunts_path))
    assert list(phases.columns) == tracker.PHASE_COLUMNS
    assert phases.empty


def test_new_hunt_sanitises_impossible_bonuses(paths):
    fishing = make_hunt(
        paths,
        "Magikarp",
        "FireRed",
        encounter_method="static",
        shiny_charm=True,
        masuda_method=True,
    )
    assert fishing.shiny_charm is False
    assert fishing.masuda_method is False

    bdsp_wild = make_hunt(
        paths,
        "Bidoof",
        "Brilliant Diamond",
        encounter_method="wild",
        shiny_charm=True,
    )
    assert bdsp_wild.shiny_charm is False

    bdsp_egg = make_hunt(
        paths,
        "Piplup",
        "Shining Pearl",
        encounter_method="breeding",
        shiny_charm=True,
        masuda_method=True,
    )
    assert bdsp_egg.shiny_charm is True
    assert bdsp_egg.masuda_method is True


def test_new_hunt_rejects_method_the_game_does_not_support(paths):
    hunts_path, _ = paths
    with pytest.raises(ValidationError):
        new_hunt(
            "Pikachu",
            "Legends: Z-A",
            encounter_method="breeding",
            csv_path=str(hunts_path),
        )
    with pytest.raises(ValidationError):
        new_hunt(
            "Garchomp",
            "Legends: Arceus",
            encounter_method="static",
            csv_path=str(hunts_path),
        )
    assert load_hunts(str(hunts_path)).empty


def test_masuda_is_enabled_for_every_breeding_capable_game():
    for game in SUPPORTED_GAMES:
        mechanics = get_mechanics(game)
        pokemon = Pokemon(
            name="Test",
            game=game,
            encounter_method=BREEDING,
            masuda_method=True,
        )
        assert pokemon.masuda_method is mechanics.masuda_supported, game
        if mechanics.masuda_supported:
            assert pokemon.odds_result.masuda_applied is True, game
        else:
            assert pokemon.odds_result.masuda_applied is False, game


def test_masuda_and_charm_combined_odds_per_game():
    expected_rolls = {
        "Black 2": 8,
        "White 2": 8,
        "X": 8,
        "Y": 8,
        "Omega Ruby": 8,
        "Alpha Sapphire": 8,
        "Sun": 8,
        "Moon": 8,
        "Ultra Sun": 8,
        "Ultra Moon": 8,
        "Sword": 8,
        "Shield": 8,
        "Brilliant Diamond": 8,
        "Shining Pearl": 8,
        "Scarlet": 8,
        "Violet": 8,
    }
    for game, rolls in expected_rolls.items():
        pokemon = Pokemon(
            name="Test",
            game=game,
            encounter_method=BREEDING,
            shiny_charm=True,
            masuda_method=True,
        )
        result = pokemon.odds_result
        assert result.total_rolls == rolls, game
        assert result.masuda_applied is True, game
        assert result.shiny_charm_applied is True, game
        if game in ("Black 2", "White 2"):
            assert result.one_in == pytest.approx(1024.44, rel=1e-4), game
        else:
            assert result.one_in == pytest.approx(512.44, rel=1e-4), game


def test_new_hunt_rejects_blank_name_and_unsupported_game(paths):
    hunts_path, _ = paths
    with pytest.raises(ValidationError):
        new_hunt("   ", "Black", csv_path=str(hunts_path))
    with pytest.raises(ValidationError):
        new_hunt("Pikachu", "Pokémon Pinball", csv_path=str(hunts_path))
    assert load_hunts(str(hunts_path)).empty


def test_pokemon_sanitises_on_construction():
    pokemon = Pokemon(
        name="  Axew  ",
        encounter_count=-5,
        game="black2",
        shiny_charm=True,
        encounter_method="breeding",
        masuda_method=True,
    )
    assert pokemon.name == "Axew"
    assert pokemon.game == "Black 2"
    assert pokemon.generation == 5
    assert pokemon.encounter_count == 0
    assert pokemon.shiny_charm is True
    assert pokemon.masuda_method is True


def test_encounter_helpers():
    pokemon = Pokemon(name="Axew", encounter_count=0, game="Black")
    assert add_encounter(pokemon).encounter_count == 1
    assert remove_encounter(pokemon).encounter_count == 0
    assert remove_encounter(add_encounter(pokemon)).encounter_count == 0
    assert custom_add_encounter(pokemon, 10).encounter_count == 10
    assert custom_remove_encounter(pokemon, 10).encounter_count == 0
    with pytest.raises(ValidationError):
        custom_add_encounter(pokemon, 0)
    with pytest.raises(ValidationError):
        custom_remove_encounter(pokemon, -1)


def test_save_and_load_round_trip(paths):
    pokemon = make_hunt(
        paths,
        "Axew",
        "Black 2",
        encounter_method="breeding",
        shiny_charm=True,
        masuda_method=True,
    )
    loaded = from_csv_to_Pokemon(load_hunts(str(paths[0])))
    assert len(loaded) == 1
    assert loaded[0] == pokemon


def test_duplicate_hunt_id_is_rejected(paths):
    pokemon = make_hunt(paths)
    dataframe = load_hunts(str(paths[0]))
    with pytest.raises(DuplicateHuntError):
        save_hunt_to_csv(pokemon, dataframe, str(paths[0]))


def test_update_and_remove(paths):
    pokemon = make_hunt(paths)
    updated = set_count(paths, pokemon, 25)
    assert int(updated.iloc[0]["encounter_count"]) == 25

    removed = remove_hunt_from_csv(
        pokemon, load_hunts(str(paths[0])), str(paths[0])
    )
    assert removed.empty

    with pytest.raises(ValidationError):
        update_hunt_in_csv(pokemon, load_hunts(str(paths[0])), str(paths[0]))


def test_no_temporary_files_are_left_behind(paths):
    pokemon = make_hunt(paths)
    set_count(paths, pokemon, 10)
    set_count(paths, pokemon, 10)
    temporary = list(Path(paths[0]).parent.glob(".shiny_tracker_*"))
    assert temporary == []


def test_probability_uses_registry(paths):
    pokemon = make_hunt(paths, "Axew", "Black", encounter_method="wild")
    assert calulate_probability(pokemon) == 0.0
    pokemon.encounter_count = 8192
    assert calulate_probability(pokemon) == pytest.approx(63.21, abs=0.01)

    breeder = make_hunt(
        paths,
        "Deino",
        "Black 2",
        encounter_method="breeding",
        shiny_charm=True,
        masuda_method=True,
    )
    assert hunt_odds(breeder).total_rolls == 8
    assert hunt_odds(breeder).one_in == pytest.approx(1024.44, rel=1e-4)


# ---------------------------------------------------------------------------
# Phasing
# ---------------------------------------------------------------------------


def test_record_phase_resets_counter_and_preserves_hunt(paths):
    hunts_path, phases_path = paths
    pokemon = make_hunt(
        paths,
        "Axew",
        "Black 2",
        encounter_method="breeding",
        shiny_charm=True,
        masuda_method=True,
    )
    pokemon.is_done = True
    set_count(paths, pokemon, 123)

    new_hunts, new_phases, record = record_phase(
        pokemon.hunt_id,
        "Boldore",
        123,
        hunts_path=str(hunts_path),
        phases_path=str(phases_path),
        expected_encounter_count=123,
        expected_next_phase=1,
    )

    assert record.phase == 1
    assert record.target_pokemon == "Axew"
    assert len(new_hunts) == 1  # no new hunt was created
    row = new_hunts.iloc[0]
    assert row["hunt_id"] == pokemon.hunt_id
    assert row["name"] == "Axew"
    assert int(row["encounter_count"]) == 0
    assert bool(row["is_done"]) is True
    assert bool(row["shiny_charm"]) is True
    assert bool(row["masuda_method"]) is True
    assert row["encounter_method"] == "breeding"

    assert len(new_phases) == 1
    phase_row = new_phases.iloc[0]
    assert phase_row["hunt_id"] == pokemon.hunt_id
    assert phase_row["target_pokemon"] == "Axew"
    assert phase_row["phased_pokemon"] == "Boldore"
    assert int(phase_row["encounter_count"]) == 123


def test_phase_numbering_is_independent_per_hunt(paths):
    hunts_path, phases_path = paths
    a = make_hunt(paths, "Axew", "Black")
    b = make_hunt(paths, "Boldore", "Black")
    set_count(paths, a, 10)
    set_count(paths, b, 20)

    record_phase(a.hunt_id, "Pidove", 10, hunts_path=str(hunts_path), phases_path=str(phases_path))
    record_phase(b.hunt_id, "Roggenrola", 20, hunts_path=str(hunts_path), phases_path=str(phases_path))
    record_phase(a.hunt_id, "Timburr", 5, hunts_path=str(hunts_path), phases_path=str(phases_path))

    phases = load_phases(str(phases_path))
    assert next_phase_number(phases, a.hunt_id) == 3
    assert next_phase_number(phases, b.hunt_id) == 2
    assert sorted(phases.loc[phases.hunt_id == a.hunt_id, "phase"]) == [1, 2]
    assert list(phases.loc[phases.hunt_id == b.hunt_id, "phase"]) == [1]


def test_phase_helpers_group_and_summarise(paths):
    hunts_path, phases_path = paths
    a = make_hunt(paths, "Axew", "Black")
    b = make_hunt(paths, "Boldore", "Black")
    set_count(paths, a, 10)
    set_count(paths, b, 20)
    record_phase(a.hunt_id, "Pidove", 10, hunts_path=str(hunts_path), phases_path=str(phases_path))
    record_phase(a.hunt_id, "Timburr", 7, hunts_path=str(hunts_path), phases_path=str(phases_path))
    record_phase(b.hunt_id, "Roggenrola", 20, hunts_path=str(hunts_path), phases_path=str(phases_path))

    phases = load_phases(str(phases_path))
    grouped = group_phases_by_hunt(phases)
    assert set(grouped) == {a.hunt_id, b.hunt_id}
    assert list(grouped[a.hunt_id]["phase"]) == [1, 2]
    assert list(phases_for_hunt(phases, a.hunt_id)["phased_pokemon"]) == [
        "Pidove",
        "Timburr",
    ]

    summary = phase_summary(phases)
    axew = summary.loc[summary.hunt_id == a.hunt_id].iloc[0]
    assert int(axew["phase_count"]) == 2
    assert int(axew["total_encounters"]) == 17
    assert int(axew["last_phase"]) == 2


def test_blank_phase_pokemon_is_rejected_without_writing(paths):
    hunts_path, phases_path = paths
    pokemon = make_hunt(paths)
    set_count(paths, pokemon, 10)
    hunts_before = Path(hunts_path).read_text()
    phases_before = Path(phases_path).read_text() if Path(phases_path).exists() else None

    with pytest.raises(ValidationError):
        validate_phase_input("   ", 10)
    with pytest.raises(ValidationError):
        record_phase(
            pokemon.hunt_id,
            "   ",
            10,
            hunts_path=str(hunts_path),
            phases_path=str(phases_path),
        )

    assert Path(hunts_path).read_text() == hunts_before
    if phases_before is None:
        assert not Path(phases_path).exists() or Path(phases_path).read_text() == ""
    else:
        assert Path(phases_path).read_text() == phases_before


def test_negative_phase_count_is_rejected(paths):
    pokemon = make_hunt(paths)
    with pytest.raises(ValidationError):
        record_phase(
            pokemon.hunt_id,
            "Pidove",
            -1,
            hunts_path=str(paths[0]),
            phases_path=str(paths[1]),
        )


def test_expected_count_mismatch_does_not_write(paths):
    hunts_path, phases_path = paths
    pokemon = make_hunt(paths)
    set_count(paths, pokemon, 10)
    before = Path(hunts_path).read_text()

    with pytest.raises(ConcurrentUpdateError):
        record_phase(
            pokemon.hunt_id,
            "Pidove",
            10,
            hunts_path=str(hunts_path),
            phases_path=str(phases_path),
            expected_encounter_count=9,
        )

    assert Path(hunts_path).read_text() == before
    assert load_phases(str(phases_path)).empty


def test_expected_next_phase_mismatch_does_not_write(paths):
    hunts_path, phases_path = paths
    pokemon = make_hunt(paths)
    set_count(paths, pokemon, 10)
    record_phase(
        pokemon.hunt_id,
        "Pidove",
        10,
        hunts_path=str(hunts_path),
        phases_path=str(phases_path),
    )
    before = Path(hunts_path).read_text()
    phases_before = Path(phases_path).read_text()

    with pytest.raises(ConcurrentUpdateError):
        record_phase(
            pokemon.hunt_id,
            "Timburr",
            5,
            hunts_path=str(hunts_path),
            phases_path=str(phases_path),
            expected_next_phase=1,
        )

    assert Path(hunts_path).read_text() == before
    assert Path(phases_path).read_text() == phases_before


def test_record_phase_rolls_back_phase_file_when_hunt_write_fails(paths, monkeypatch):
    hunts_path, phases_path = paths
    pokemon = make_hunt(paths)
    set_count(paths, pokemon, 10)
    hunts_before = Path(hunts_path).read_text()
    phases_before = Path(phases_path).read_text()

    original = tracker._atomic_write_csv

    def flaky(dataframe, csv_path):
        if str(csv_path).endswith("hunts.csv"):
            raise OSError("simulated disk failure")
        return original(dataframe, csv_path)

    monkeypatch.setattr(tracker, "_atomic_write_csv", flaky)

    with pytest.raises(TransactionError):
        record_phase(
            pokemon.hunt_id,
            "Pidove",
            10,
            hunts_path=str(hunts_path),
            phases_path=str(phases_path),
            backup=False,
        )

    assert Path(hunts_path).read_text() == hunts_before
    assert Path(phases_path).read_text() == phases_before


def test_deleting_hunt_removes_its_phases(paths):
    hunts_path, phases_path = paths
    a = make_hunt(paths, "Axew", "Black")
    b = make_hunt(paths, "Boldore", "Black")
    set_count(paths, a, 10)
    set_count(paths, b, 10)
    record_phase(a.hunt_id, "Pidove", 10, hunts_path=str(hunts_path), phases_path=str(phases_path))
    record_phase(b.hunt_id, "Roggenrola", 10, hunts_path=str(hunts_path), phases_path=str(phases_path))

    remaining = delete_hunt(
        a, csv_path=str(hunts_path), phases_path=str(phases_path)
    )
    assert list(remaining["name"]) == ["Boldore"]
    phases = load_phases(str(phases_path))
    assert list(phases["hunt_id"]) == [b.hunt_id]


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

LEGACY_HUNTS = """name,encounter_count,generation,game,is_done,odds,shiny_charm,hunt_id
Bulbasaur,40,1,FireRed,False,8192,False,id-bulba
Boldore,431,5,Black,False,8192,True,id-boldore
Charmander,10,5,Black 2,False,8192,True,id-charmander
Piplup,5,4,Platinum,True,8192,False,id-piplup
"""

LEGACY_PHASES = """name,phase,encounter_count,pokemon_phased_on,phase_count
Bulbasaur,1,40,Pidgey,1
Bulbasaur,2,12,Rattata,2
Charmander,1,3,Zubat,1
"""


def test_migration_preserves_data_and_adds_new_columns(paths, tmp_path):
    hunts_path, phases_path = paths
    Path(hunts_path).write_text(LEGACY_HUNTS)
    Path(phases_path).write_text(LEGACY_PHASES)

    report = migrate_csvs(str(hunts_path), str(phases_path))

    assert report.hunts_changed is True
    assert report.phases_changed is True
    assert report.unsupported_hunts == ()
    assert report.hunts_rows == 4
    assert report.phase_rows == 3
    assert report.backup_dir is not None
    assert (Path(report.backup_dir) / "hunts.csv").exists()
    assert (Path(report.backup_dir) / "phased.csv").exists()

    hunts = load_hunts(str(hunts_path))
    assert list(hunts.columns)[: len(tracker.HUNT_COLUMNS)] == tracker.HUNT_COLUMNS
    assert set(hunts["hunt_id"]) == {
        "id-bulba",
        "id-boldore",
        "id-charmander",
        "id-piplup",
    }
    assert list(hunts["encounter_count"]) == [40, 431, 10, 5]
    assert list(hunts["is_done"]) == [False, False, False, True]

    bulba = hunts.loc[hunts.hunt_id == "id-bulba"].iloc[0]
    assert bulba["game"] == "FireRed"
    assert int(bulba["generation"]) == 3  # corrected from the bad legacy value
    assert bulba["encounter_method"] == "wild"
    assert bool(bulba["masuda_method"]) is False

    boldore = hunts.loc[hunts.hunt_id == "id-boldore"].iloc[0]
    assert bool(boldore["shiny_charm"]) is False  # Black has no charm

    charmander = hunts.loc[hunts.hunt_id == "id-charmander"].iloc[0]
    assert bool(charmander["shiny_charm"]) is True  # valid for B2W2
    assert int(charmander["generation"]) == 5

    phases = load_phases(str(phases_path))
    assert list(phases.columns) == tracker.PHASE_COLUMNS
    assert list(phases["target_pokemon"]) == ["Bulbasaur", "Bulbasaur", "Charmander"]
    assert list(phases["phased_pokemon"]) == ["Pidgey", "Rattata", "Zubat"]
    assert list(phases["hunt_id"]) == ["id-bulba", "id-bulba", "id-charmander"]
    assert list(phases["phase"]) == [1, 2, 1]


def test_migration_is_idempotent(paths):
    hunts_path, phases_path = paths
    Path(hunts_path).write_text(LEGACY_HUNTS)
    Path(phases_path).write_text(LEGACY_PHASES)

    first = migrate_csvs(str(hunts_path), str(phases_path))
    backup_count = len(list(Path(first.backup_dir).parent.iterdir()))

    second = migrate_csvs(str(hunts_path), str(phases_path))

    assert second.hunts_changed is False
    assert second.phases_changed is False
    assert second.backup_dir is None
    assert second.notes == ()
    assert len(list(Path(first.backup_dir).parent.iterdir())) == backup_count


def test_migration_handles_legacy_empty_phase_file(paths):
    hunts_path, phases_path = paths
    Path(hunts_path).write_text(LEGACY_HUNTS)
    Path(phases_path).write_text(
        "name,phase,encounter_count,pokemon_phased_on,phase_count\n"
    )

    migrate_csvs(str(hunts_path), str(phases_path))

    phases = load_phases(str(phases_path))
    assert list(phases.columns)[: len(tracker.PHASE_COLUMNS)] == tracker.PHASE_COLUMNS
    assert phases.empty


def test_migration_repairs_missing_phase_hunt_ids(paths):
    hunts_path, phases_path = paths
    Path(hunts_path).write_text(LEGACY_HUNTS)
    Path(phases_path).write_text(
        "phase,target_pokemon,encounter_count,phased_pokemon,hunt_id\n"
        "1,Bulbasaur,40,Pidgey,\n"
    )

    migrate_csvs(str(hunts_path), str(phases_path))
    phases = load_phases(str(phases_path))
    assert phases.iloc[0]["hunt_id"] == "id-bulba"


def test_migration_drops_completely_blank_phase_rows(paths):
    hunts_path, phases_path = paths
    Path(hunts_path).write_text(LEGACY_HUNTS)
    Path(phases_path).write_text(
        "name,phase,encounter_count,pokemon_phased_on,phase_count\n"
        ",0,0,,0\n"
        "Bulbasaur,1,40,Pidgey,1\n"
    )

    migrate_csvs(str(hunts_path), str(phases_path))
    phases = load_phases(str(phases_path))
    assert len(phases) == 1
    assert phases.iloc[0]["phased_pokemon"] == "Pidgey"


def test_migration_uses_legacy_phase_count_when_phase_is_missing(paths):
    hunts_path, phases_path = paths
    Path(hunts_path).write_text(LEGACY_HUNTS)
    Path(phases_path).write_text(
        "name,encounter_count,pokemon_phased_on,phase_count\n"
        "Bulbasaur,40,Pidgey,3\n"
    )

    migrate_csvs(str(hunts_path), str(phases_path))
    phases = load_phases(str(phases_path))
    assert "phase_count" not in phases.columns
    assert int(phases.iloc[0]["phase"]) == 3
    assert phases.iloc[0]["phased_pokemon"] == "Pidgey"


def test_create_csv_creates_empty_schema(tmp_path):
    path = tmp_path / "new.csv"
    dataframe = create_csv(str(path))
    assert dataframe.empty
    assert list(dataframe.columns) == tracker.HUNT_COLUMNS
    assert path.exists()


def test_unsupported_hunt_data_is_preserved(tmp_path):
    hunts_path = tmp_path / "hunts.csv"
    phases_path = tmp_path / "phased.csv"
    hunts_path.write_text(
        "name,encounter_count,generation,game,is_done,odds,shiny_charm,hunt_id\n"
        "Pikachu,12,1,Pokémon Pinball,False,8192,False,pinball-id\n"
    )

    report = migrate_csvs(str(hunts_path), str(phases_path))
    assert report.unsupported_hunts == ("Pokémon Pinball",)

    hunts = load_hunts(str(hunts_path))
    assert hunts.iloc[0]["name"] == "Pikachu"
    assert int(hunts.iloc[0]["encounter_count"]) == 12
    assert hunts.iloc[0]["game"] == "Pokémon Pinball"
    assert hunt_odds(Pokemon.from_row(hunts.iloc[0])).supported is False
