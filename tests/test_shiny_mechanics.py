import math

import pytest

from shiny_mechanics import (
    BREEDING,
    STATIC,
    SUPPORTED_GAMES,
    WILD,
    calculate_shiny_odds,
    canonicalize_game,
    counter_label,
    cumulative_percent,
    format_one_in,
    game_generation,
    game_supports_breeding,
    get_mechanics,
    is_supported_game,
    masuda_available,
    masuda_unavailable_reason,
    shiny_charm_available,
    shiny_charm_unavailable_reason,
)


def compounded(base_odds: int, rolls: int) -> float:
    return 1.0 - (1.0 - 1.0 / base_odds) ** rolls


@pytest.mark.parametrize(
    "game,generation,base_odds",
    [
        ("FireRed", 3, 8192),
        ("Emerald", 3, 8192),
        ("Platinum", 4, 8192),
        ("Black", 5, 8192),
        ("Black 2", 5, 8192),
        ("X", 6, 4096),
        ("Ultra Moon", 7, 4096),
        ("Sword", 8, 4096),
        ("Brilliant Diamond", 8, 4096),
        ("Legends: Arceus", 8, 4096),
        ("Scarlet", 9, 4096),
        ("Violet", 9, 4096),
        ("Legends: Z-A", 9, 4096),
    ],
)
def test_registry_generation_and_base_odds(game, generation, base_odds):
    mechanics = get_mechanics(game)
    assert mechanics is not None
    assert mechanics.generation == generation
    assert mechanics.base_odds == base_odds
    assert game_generation(game) == generation


def test_supported_game_list_is_stable_and_complete():
    assert len(SUPPORTED_GAMES) == 30
    assert SUPPORTED_GAMES[0] == "Ruby"
    assert SUPPORTED_GAMES[-1] == "Legends: Z-A"
    assert "Legends: Z-A" in SUPPORTED_GAMES
    assert "Let's Go Pikachu" not in SUPPORTED_GAMES
    for game in SUPPORTED_GAMES:
        assert is_supported_game(game)


EXPECTED_CAPABILITIES = {
    # Generation III: breeding exists, Masuda does not.
    "Ruby": (True, False),
    "Sapphire": (True, False),
    "Emerald": (True, False),
    "FireRed": (True, False),
    "LeafGreen": (True, False),
    # Generation IV: breeding and Masuda, no Shiny Charm.
    "Diamond": (True, True),
    "Pearl": (True, True),
    "Platinum": (True, True),
    "HeartGold": (True, True),
    "SoulSilver": (True, True),
    # Generation V.
    "Black": (True, True),
    "White": (True, True),
    "Black 2": (True, True),
    "White 2": (True, True),
    # Generation VI.
    "X": (True, True),
    "Y": (True, True),
    "Omega Ruby": (True, True),
    "Alpha Sapphire": (True, True),
    # Generation VII.
    "Sun": (True, True),
    "Moon": (True, True),
    "Ultra Sun": (True, True),
    "Ultra Moon": (True, True),
    # Generation VIII.
    "Sword": (True, True),
    "Shield": (True, True),
    "Brilliant Diamond": (True, True),
    "Shining Pearl": (True, True),
    "Legends: Arceus": (False, False),
    # Generation IX.
    "Scarlet": (True, True),
    "Violet": (True, True),
    "Legends: Z-A": (False, False),
}


def test_every_game_has_explicit_breeding_and_masuda_capabilities():
    assert set(EXPECTED_CAPABILITIES) == set(SUPPORTED_GAMES)
    for game, (can_breed, masuda_supported) in EXPECTED_CAPABILITIES.items():
        mechanics = get_mechanics(game)
        assert mechanics is not None
        assert mechanics.can_breed is can_breed, game
        assert mechanics.masuda_supported is masuda_supported, game
        assert game_supports_breeding(game) is can_breed, game
        assert mechanics.has_masuda is masuda_supported, game
        assert masuda_available(game, BREEDING) is masuda_supported, game
        assert masuda_available(game, WILD) is False, game
        assert masuda_available(game, STATIC) is False, game


def test_masuda_reason_matches_capability():
    assert masuda_unavailable_reason("Platinum", BREEDING) is None
    assert "only applies to breeding" in masuda_unavailable_reason("Platinum", WILD)
    assert "no breeding" in masuda_unavailable_reason("Legends: Arceus")
    assert "no breeding" in masuda_unavailable_reason("Legends: Z-A")
    assert "not available" in masuda_unavailable_reason("FireRed", BREEDING)


def test_shiny_charm_reason_matches_capability():
    assert shiny_charm_unavailable_reason("X", WILD) is None
    assert "no Shiny Charm" in shiny_charm_unavailable_reason("Platinum", WILD)
    assert "does not affect wild" in shiny_charm_unavailable_reason(
        "Brilliant Diamond", WILD
    )


def test_counter_labels_distinguish_eggs_from_encounters():
    assert counter_label(WILD) == "Encounters"
    assert counter_label(STATIC) == "Encounters"
    assert counter_label(BREEDING) == "Eggs hatched"


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("firered", "FireRed"),
        ("Pokémon FireRed Version", "FireRed"),
        ("PT", "Platinum"),
        ("hgss", "HeartGold"),
        ("black2", "Black 2"),
        ("ORAS", "Omega Ruby"),
        ("usum", "Ultra Sun"),
        ("bdsp", "Brilliant Diamond"),
        ("PLA", "Legends: Arceus"),
        ("pokemon scarlet version", "Scarlet"),
        ("Legends: Z-A", "Legends: Z-A"),
        ("legendsza", "Legends: Z-A"),
        ("ZA", "Legends: Z-A"),
    ],
)
def test_game_aliases(alias, expected):
    assert canonicalize_game(alias) == expected


def test_unknown_game_returns_none_and_unsupported_odds():
    assert canonicalize_game("Pokémon Pinball") is None
    result = calculate_shiny_odds("Pokémon Pinball")
    assert result.supported is False
    assert result.display == "Unavailable"
    assert "not a supported game" in result.reason


def test_gen_iii_has_single_roll_and_no_bonuses():
    result = calculate_shiny_odds("FireRed", WILD, shiny_charm=True, masuda_method=True)
    assert result.supported
    assert result.total_rolls == 1
    assert result.shiny_charm_applied is False
    assert result.masuda_applied is False
    assert result.probability == pytest.approx(1 / 8192)
    assert result.one_in == pytest.approx(8192)
    assert result.display == "1 in 8,192"


def test_shiny_charm_uses_exact_compounded_probability():
    result = calculate_shiny_odds("X", WILD, shiny_charm=True)
    assert result.total_rolls == 3
    assert result.shiny_charm_applied is True
    assert result.probability == pytest.approx(compounded(4096, 3))
    assert result.one_in == pytest.approx(1 / compounded(4096, 3))
    assert result.one_in == pytest.approx(1365.666, rel=1e-3)
    assert result.display == "1 in 1,366"


def test_gen_iv_masuda_uses_five_rolls():
    result = calculate_shiny_odds("Platinum", BREEDING, masuda_method=True)
    assert result.total_rolls == 5
    assert result.masuda_applied is True
    assert result.probability == pytest.approx(compounded(8192, 5))
    assert result.one_in == pytest.approx(1638.83, rel=1e-4)


def test_gen_v_masuda_and_charm_rules():
    bw = calculate_shiny_odds("Black", BREEDING, shiny_charm=True, masuda_method=True)
    assert bw.total_rolls == 6  # Masuda only; Black/White have no charm
    assert bw.shiny_charm_applied is False

    b2w2 = calculate_shiny_odds(
        "Black 2", BREEDING, shiny_charm=True, masuda_method=True
    )
    assert b2w2.total_rolls == 8
    assert b2w2.shiny_charm_applied is True
    assert b2w2.masuda_applied is True
    assert b2w2.one_in == pytest.approx(1 / compounded(8192, 8))


def test_gen_vi_and_vii_masuda_and_charm():
    for game in ("X", "Sun"):
        plain = calculate_shiny_odds(game, BREEDING, masuda_method=True)
        combined = calculate_shiny_odds(
            game, BREEDING, shiny_charm=True, masuda_method=True
        )
        assert plain.total_rolls == 6
        assert combined.total_rolls == 8
        assert combined.one_in == pytest.approx(512.44, rel=1e-3)


def test_gen_viii_swsh_egg_roll_bug():
    charm_only = calculate_shiny_odds("Sword", BREEDING, shiny_charm=True)
    masuda_only = calculate_shiny_odds("Sword", BREEDING, masuda_method=True)
    both = calculate_shiny_odds(
        "Sword", BREEDING, shiny_charm=True, masuda_method=True
    )
    wild_charm = calculate_shiny_odds("Sword", WILD, shiny_charm=True)

    assert charm_only.total_rolls == 2
    assert charm_only.one_in == pytest.approx(2048.25, rel=1e-3)
    assert masuda_only.total_rolls == 6
    assert both.total_rolls == 8
    assert wild_charm.total_rolls == 3  # the bug is breeding-only


def test_bdsp_charm_only_affects_breeding():
    wild = calculate_shiny_odds("Brilliant Diamond", WILD, shiny_charm=True)
    static = calculate_shiny_odds("Shining Pearl", STATIC, shiny_charm=True)
    breeding = calculate_shiny_odds(
        "Brilliant Diamond", BREEDING, shiny_charm=True
    )

    assert wild.total_rolls == 1
    assert static.total_rolls == 1
    assert breeding.total_rolls == 2
    assert shiny_charm_available("Brilliant Diamond", WILD) is False
    assert shiny_charm_available("Brilliant Diamond", BREEDING) is True


def test_legends_arceus_rules():
    mechanics = get_mechanics("Legends: Arceus")
    assert mechanics.supported_methods == (WILD,)
    assert masuda_available("Legends: Arceus") is False

    result = calculate_shiny_odds("Legends: Arceus", WILD, shiny_charm=True)
    assert result.total_rolls == 4
    assert result.one_in == pytest.approx(1 / compounded(4096, 4))
    assert any("Research Level 10" in warning for warning in result.warnings)

    unsupported = calculate_shiny_odds("Legends: Arceus", STATIC)
    assert unsupported.supported is False


def test_legends_za_rules():
    mechanics = get_mechanics("Legends: Z-A")
    assert mechanics is not None
    assert mechanics.generation == 9
    assert mechanics.base_odds == 4096
    assert mechanics.supported_methods == (WILD,)
    assert mechanics.can_breed is False
    assert mechanics.masuda_supported is False
    assert masuda_available("Legends: Z-A") is False
    assert "no breeding" in masuda_unavailable_reason("Legends: Z-A")

    plain = calculate_shiny_odds("Legends: Z-A", WILD)
    charmed = calculate_shiny_odds("Legends: Z-A", WILD, shiny_charm=True)
    assert plain.total_rolls == 1
    assert plain.one_in == pytest.approx(4096)
    assert charmed.total_rolls == 4
    assert charmed.one_in == pytest.approx(1 / compounded(4096, 4))
    assert charmed.one_in == pytest.approx(1024.38, rel=1e-3)

    unsupported = calculate_shiny_odds("Legends: Z-A", BREEDING)
    assert unsupported.supported is False
    assert "Breeding" in unsupported.reason


def test_scarlet_violet_rules():
    mechanics = get_mechanics("Scarlet")
    assert mechanics.supported_methods == (WILD, BREEDING)
    assert calculate_shiny_odds("Scarlet", STATIC).supported is False

    wild = calculate_shiny_odds("Scarlet", WILD, shiny_charm=True)
    breeding = calculate_shiny_odds(
        "Violet", BREEDING, shiny_charm=True, masuda_method=True
    )
    assert wild.total_rolls == 3
    assert breeding.total_rolls == 8


def test_unknown_method_is_rejected():
    result = calculate_shiny_odds("X", "chain fishing")
    assert result.supported is False
    assert "Unknown encounter method" in result.reason


def test_cumulative_probability_and_percent():
    probability = compounded(4096, 1)
    assert cumulative_percent(probability, 0) == 0.0
    assert cumulative_percent(probability, 4096) == pytest.approx(63.21, abs=0.01)
    assert cumulative_percent(probability, 8192) == pytest.approx(86.47, abs=0.01)


@pytest.mark.parametrize(
    "value,expected",
    [
        (8192, "1 in 8,192"),
        (1365.666, "1 in 1,366"),
        (12.34, "1 in 12.3"),
        (2.5, "1 in 2.50"),
    ],
)
def test_format_one_in(value, expected):
    assert format_one_in(value) == expected


def test_exact_formula_is_not_the_linear_approximation():
    result = calculate_shiny_odds("X", WILD, shiny_charm=True)
    linear = 3 / 4096
    assert not math.isclose(result.probability, linear, rel_tol=1e-6)
    assert result.probability < linear
