"""Central registry of Pokémon shiny mechanics and the authoritative odds calculator.

The data in this module was researched from Bulbapedia, Serebii and independent
odds references.  See ``SHINY_MECHANICS.md`` for the per-game notes, the source
URLs and the known disagreements between sources.

Everything here is local: the tracker never needs an internet connection at
runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

# ---------------------------------------------------------------------------
# Encounter methods
# ---------------------------------------------------------------------------

WILD = "wild"
BREEDING = "breeding"
STATIC = "static"

ENCOUNTER_METHODS = (WILD, BREEDING, STATIC)

ENCOUNTER_METHOD_LABELS = {
    WILD: "Wild encounters",
    BREEDING: "Breeding (eggs)",
    STATIC: "Static encounters",
}

COUNTER_LABELS = {
    WILD: "Encounters",
    BREEDING: "Eggs hatched",
    STATIC: "Encounters",
}


def encounter_method_label(method: str) -> str:
    """Human-readable label for an encounter method."""
    return ENCOUNTER_METHOD_LABELS.get(method, str(method))


def counter_label(method: str) -> str:
    """The counter label appropriate for the encounter method."""
    return COUNTER_LABELS.get(method, "Encounters")


# ---------------------------------------------------------------------------
# Game mechanics registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GameMechanics:
    """Shiny mechanics for one canonical game.

    Capabilities are stored explicitly per game rather than inferred from the
    generation.  This matters for games such as Legends: Arceus and Legends:
    Z-A, which are modern games without breeding, and for Generation III, which
    has breeding but predates the Masuda Method.

    ``base_odds`` is the denominator of the base single-roll shiny chance.

    ``can_breed`` records whether the game has a breeding/egg mechanic at all.
    ``masuda_supported`` records whether that game implements the Masuda
    Method.  It must always imply ``can_breed`` and a breeding method.

    ``shiny_charm_methods`` lists the encounter methods for which the Shiny
    Charm actually adds rolls in that game.  An empty set means the game has no
    Shiny Charm.

    ``masuda_rerolls`` is the number of *extra* rolls the Masuda Method adds
    while breeding.  ``None`` means Masuda does not exist (or the game has no
    breeding).  Note that the Masuda page lists rerolls, so the total number of
    rolls is normally ``1 + rerolls``.

    ``breeding_skips_initial_roll`` models the Generation VIII/IX egg shiny-roll
    bug: if any bonus roll applies while breeding, the initial roll is skipped,
    so the total number of rolls equals the bonus rolls only.
    """

    name: str
    generation: int
    base_odds: int
    supported_methods: tuple[str, ...]
    can_breed: bool
    masuda_supported: bool
    shiny_charm_methods: frozenset[str] = field(default_factory=frozenset)
    masuda_rerolls: int | None = None
    shiny_charm_rerolls: int = 2
    breeding_skips_initial_roll: bool = False
    notes: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.can_breed and BREEDING in self.supported_methods:
            raise ValueError(f"{self.name}: breeding method requires can_breed.")
        if self.masuda_supported:
            if not self.can_breed or BREEDING not in self.supported_methods:
                raise ValueError(
                    f"{self.name}: Masuda support requires breeding support."
                )
            if self.masuda_rerolls is None:
                raise ValueError(
                    f"{self.name}: Masuda support requires masuda_rerolls."
                )

    @property
    def has_shiny_charm(self) -> bool:
        return bool(self.shiny_charm_methods)

    @property
    def has_masuda(self) -> bool:
        return self.masuda_supported


_BULBAPEDIA_SHINY = "https://bulbapedia.bulbagarden.net/wiki/Shiny_Pok%C3%A9mon"
_BULBAPEDIA_CHARM = "https://bulbapedia.bulbagarden.net/wiki/Shiny_Charm"
_BULBAPEDIA_MASUDA = "https://bulbapedia.bulbagarden.net/wiki/Masuda_method"
_SEREBII_SHINY = "https://www.serebii.net/games/shiny.shtml"
_SEREBII_BDSP = "https://www.serebii.net/brilliantdiamondshiningpearl/shinypokemon.shtml"
_SEREBII_PLA = "https://www.serebii.net/legendsarceus/shinypokemon.shtml"
_SEREBII_SWSH = "https://www.serebii.net/swordshield/shinypokemon.shtml"
_SEREBII_SV = "https://www.serebii.net/scarletviolet/shinypokemon.shtml"
_SEREBII_ZA = "https://www.serebii.net/legendsz-a/shinypokemon.shtml"
_ROTOMLABS_BDSP = "https://rotomlabs.net/brilliant-diamond-shining-pearl/shiny-rates"
_ROTOMLABS_PLA = "https://rotomlabs.net/legends-arceus/shiny-rates"


def _mechanics(
    name: str,
    generation: int,
    base_odds: int,
    *,
    methods: tuple[str, ...] = (WILD, BREEDING, STATIC),
    can_breed: bool = True,
    masuda_supported: bool = False,
    charm_methods: tuple[str, ...] = (),
    masuda_rerolls: int | None = None,
    charm_rerolls: int = 2,
    skip_initial_on_breeding_bonus: bool = False,
    notes: tuple[str, ...] = (),
    sources: tuple[str, ...] = (_BULBAPEDIA_SHINY, _BULBAPEDIA_CHARM, _BULBAPEDIA_MASUDA),
) -> GameMechanics:
    return GameMechanics(
        name=name,
        generation=generation,
        base_odds=base_odds,
        supported_methods=methods,
        can_breed=can_breed,
        masuda_supported=masuda_supported,
        shiny_charm_methods=frozenset(charm_methods),
        masuda_rerolls=masuda_rerolls,
        shiny_charm_rerolls=charm_rerolls,
        breeding_skips_initial_roll=skip_initial_on_breeding_bonus,
        notes=notes,
        sources=sources,
    )


_ALL_METHODS = (WILD, BREEDING, STATIC)
_NO_CHARM: tuple[str, ...] = ()

# The order here is the order used by the game selectbox.
_SUPPORTED_GAME_ORDER = (
    # Generation III
    "Ruby",
    "Sapphire",
    "Emerald",
    "FireRed",
    "LeafGreen",
    # Generation IV
    "Diamond",
    "Pearl",
    "Platinum",
    "HeartGold",
    "SoulSilver",
    # Generation V
    "Black",
    "White",
    "Black 2",
    "White 2",
    # Generation VI
    "X",
    "Y",
    "Omega Ruby",
    "Alpha Sapphire",
    # Generation VII
    "Sun",
    "Moon",
    "Ultra Sun",
    "Ultra Moon",
    # Generation VIII
    "Sword",
    "Shield",
    "Brilliant Diamond",
    "Shining Pearl",
    "Legends: Arceus",
    # Generation IX
    "Scarlet",
    "Violet",
    "Legends: Z-A",
)

_GEN3 = ("Ruby", "Sapphire", "Emerald", "FireRed", "LeafGreen")
_GEN4 = ("Diamond", "Pearl", "Platinum", "HeartGold", "SoulSilver")
_GEN6 = ("X", "Y", "Omega Ruby", "Alpha Sapphire")
_GEN7 = ("Sun", "Moon", "Ultra Sun", "Ultra Moon")


def _build_registry() -> dict[str, GameMechanics]:
    registry: dict[str, GameMechanics] = {}

    # Generation III: single 1/8192 roll, no Shiny Charm, no Masuda Method.
    # Breeding exists, but the Masuda Method was not introduced until Gen IV.
    for game in _GEN3:
        registry[game] = _mechanics(
            game,
            3,
            8192,
            can_breed=True,
            masuda_supported=False,
            notes=(
                "Generation III has no Shiny Charm and predates the Masuda Method.",
                "Breeding and static encounters use the same single 1/8192 roll.",
            ),
        )

    # Generation IV: no Shiny Charm; Masuda Method introduced (5 total rolls).
    for game in _GEN4:
        registry[game] = _mechanics(
            game,
            4,
            8192,
            can_breed=True,
            masuda_supported=True,
            masuda_rerolls=4,
            notes=(
                "Generation IV has no Shiny Charm.",
                "Masuda Method: 4 extra rolls + 1 base roll = 5 total rolls (~1/1638.8).",
                "Serebii's older shiny page lists 1/2048 for Gen IV Masuda (4 rolls); "
                "Bulbapedia and modern research use 5 rolls. This tracker uses 5.",
            ),
        )

    # Generation V: Black/White have no charm; B2W2 introduce it.
    for game in ("Black", "White"):
        registry[game] = _mechanics(
            game,
            5,
            8192,
            can_breed=True,
            masuda_supported=True,
            masuda_rerolls=5,
            notes=(
                "Black and White do not have the Shiny Charm.",
                "Masuda Method: 5 extra rolls + 1 base roll = 6 total rolls (~1/1365.75).",
            ),
        )

    for game in ("Black 2", "White 2"):
        registry[game] = _mechanics(
            game,
            5,
            8192,
            can_breed=True,
            masuda_supported=True,
            charm_methods=_ALL_METHODS,
            masuda_rerolls=5,
            notes=(
                "Black 2 and White 2 introduce the Shiny Charm.",
                "Shiny Charm adds 2 rolls (3 total) and affects wild, static and breeding.",
                "Masuda + Shiny Charm stacks: 6 + 2 = 8 total rolls (~1/1024).",
            ),
        )

    # Generation VI: 1/4096 base; charm adds 2 rolls; Masuda adds 5.
    for game in _GEN6:
        registry[game] = _mechanics(
            game,
            6,
            4096,
            can_breed=True,
            masuda_supported=True,
            charm_methods=_ALL_METHODS,
            masuda_rerolls=5,
            notes=(
                "Shiny Charm adds 2 rolls (3 total, ~1/1365.67).",
                "Masuda Method: 5 extra rolls + 1 base roll = 6 total (~1/683.08).",
                "Masuda + Shiny Charm: 8 total rolls (~1/512.44).",
            ),
        )

    # Generation VII: same roll structure as Gen VI for ordinary encounters.
    for game in _GEN7:
        registry[game] = _mechanics(
            game,
            7,
            4096,
            can_breed=True,
            masuda_supported=True,
            charm_methods=_ALL_METHODS,
            masuda_rerolls=5,
            notes=(
                "Shiny Charm adds 2 rolls (3 total, ~1/1365.67).",
                "Masuda Method: 5 extra rolls + 1 base roll = 6 total (~1/683.08).",
                "Masuda + Shiny Charm: 8 total rolls (~1/512.44).",
                "SOS battles/DexNav are special methods and are not modelled.",
            ),
        )

    # Generation VIII: Sword/Shield.
    for game in ("Sword", "Shield"):
        registry[game] = _mechanics(
            game,
            8,
            4096,
            can_breed=True,
            masuda_supported=True,
            charm_methods=_ALL_METHODS,
            masuda_rerolls=6,
            skip_initial_on_breeding_bonus=True,
            notes=(
                "Shiny Charm adds 2 rolls for wild/static encounters (3 total).",
                "Breeding has the Gen VIII egg-roll bug: any bonus skips the initial roll.",
                "Breeding charm-only: 2 total rolls (~1/2048.25), not 3.",
                "Masuda: 6 total rolls (~1/683.08); Masuda + charm: 8 total (~1/512.44).",
                "Brilliant Pokémon, Dynamax Adventures, dens and curry are special methods "
                "and are not modelled.",
                "Some scripted/static encounters are charm-immune or shiny-locked.",
            ),
            sources=(
                _BULBAPEDIA_SHINY,
                _BULBAPEDIA_CHARM,
                _BULBAPEDIA_MASUDA,
                _SEREBII_SWSH,
            ),
        )

    # Generation VIII: BDSP — charm only affects breeding.
    for game in ("Brilliant Diamond", "Shining Pearl"):
        registry[game] = _mechanics(
            game,
            8,
            4096,
            can_breed=True,
            masuda_supported=True,
            charm_methods=(BREEDING,),
            masuda_rerolls=6,
            skip_initial_on_breeding_bonus=True,
            notes=(
                "The Shiny Charm only affects breeding in BDSP.",
                "Wild, static and Poké Radar encounters stay at 1/4096 with the charm.",
                "Breeding charm-only: 2 total rolls (~1/2048.25) due to the Gen VIII egg bug.",
                "Masuda: 6 total rolls (~1/683.08); Masuda + charm: 8 total (~1/512.44).",
                "Static encounters are not shiny-locked except the gift Mew and Jirachi.",
            ),
            sources=(
                _BULBAPEDIA_SHINY,
                _BULBAPEDIA_CHARM,
                _BULBAPEDIA_MASUDA,
                _SEREBII_BDSP,
                _ROTOMLABS_BDSP,
            ),
        )

    # Generation VIII: Legends: Arceus — no breeding; static encounters are shiny-locked.
    registry["Legends: Arceus"] = _mechanics(
        "Legends: Arceus",
        8,
        4096,
        methods=(WILD,),
        can_breed=False,
        masuda_supported=False,
        charm_methods=(WILD,),
        charm_rerolls=3,
        notes=(
            "Legends: Arceus has no breeding.",
            "All static encounters are shiny-locked, so the static method is not supported.",
            "Shiny Charm adds 3 extra rolls: 4 total (~1/1024).",
            "The charm requires Research Level 10 for every species, so in practice a "
            "charmed hunt also has at least the Level 10 bonus (5 rolls, ~1/819.6). "
            "Pokédex research and outbreaks are not modelled here.",
        ),
        sources=(
            _BULBAPEDIA_SHINY,
            _BULBAPEDIA_CHARM,
            _SEREBII_PLA,
            _ROTOMLABS_PLA,
        ),
    )

    # Generation IX: Scarlet/Violet. Static/fixed encounters are shiny-locked and
    # charm-immune, so only wild and breeding are supported.
    for game in ("Scarlet", "Violet"):
        registry[game] = _mechanics(
            game,
            9,
            4096,
            methods=(WILD, BREEDING),
            can_breed=True,
            masuda_supported=True,
            charm_methods=(WILD, BREEDING),
            masuda_rerolls=6,
            skip_initial_on_breeding_bonus=True,
            notes=(
                "Fixed/static symbol encounters are shiny-locked and unaffected by the "
                "Shiny Charm; the static method is therefore not supported.",
                "Shiny Charm adds 2 rolls for wild encounters (3 total, ~1/1365.67).",
                "Breeding has the Gen IX egg-roll bug: charm-only is 2 total rolls "
                "(~1/2048.25). Masuda is 6 (~1/683.08); Masuda + charm is 8 (~1/512.44).",
                "Mass outbreaks and Sparkling Power sandwiches are special methods and "
                "are not modelled.",
            ),
            sources=(
                _BULBAPEDIA_SHINY,
                _BULBAPEDIA_CHARM,
                _BULBAPEDIA_MASUDA,
                _SEREBII_SV,
            ),
        )

    # Generation IX: Legends: Z-A. No breeding or eggs, so no Masuda Method.
    # Wild encounters are 1/4096; the Shiny Charm adds 3 rolls (4 total).
    registry["Legends: Z-A"] = _mechanics(
        "Legends: Z-A",
        9,
        4096,
        methods=(WILD,),
        can_breed=False,
        masuda_supported=False,
        charm_methods=(WILD,),
        charm_rerolls=3,
        notes=(
            "Legends: Z-A has no breeding and no eggs, so the Masuda Method is "
            "not available.",
            "Wild encounters use a 1/4096 base rate.",
            "The Shiny Charm adds 3 extra rolls: 4 total (~1/1024.38).",
            "Static/fixed encounters are not modelled by this tracker.",
        ),
        sources=(
            _BULBAPEDIA_SHINY,
            _BULBAPEDIA_CHARM,
            _SEREBII_ZA,
        ),
    )

    return registry


GAME_MECHANICS: dict[str, GameMechanics] = _build_registry()
SUPPORTED_GAMES: tuple[str, ...] = tuple(
    game for game in _SUPPORTED_GAME_ORDER if game in GAME_MECHANICS
)


# ---------------------------------------------------------------------------
# Game name aliases
# ---------------------------------------------------------------------------


def _name_key(name: str) -> str:
    """Normalize a game name for alias matching."""
    text = str(name).strip().lower().replace("é", "e")
    text = re.sub(r"[^a-z0-9]+", "", text)
    # Accept common "Pokémon ... Version" and "... Version 2" spellings.
    changed = True
    while changed:
        changed = False
        if text.startswith("pokemon"):
            text = text[len("pokemon"):]
            changed = True
        if text.endswith("version"):
            text = text[: -len("version")]
            changed = True
    return text


_EXTRA_ALIASES: dict[str, str] = {
    # Generation III
    "firered": "FireRed",
    "fr": "FireRed",
    "leafgreen": "LeafGreen",
    "lg": "LeafGreen",
    "ruby": "Ruby",
    "sapphire": "Sapphire",
    "emerald": "Emerald",
    "rse": "Emerald",
    # Generation IV
    "diamond": "Diamond",
    "pearl": "Pearl",
    "platinum": "Platinum",
    "pt": "Platinum",
    "heartgold": "HeartGold",
    "hg": "HeartGold",
    "soulsilver": "SoulSilver",
    "hgss": "HeartGold",
    # Generation V
    "black": "Black",
    "white": "White",
    "black2": "Black 2",
    "white2": "White 2",
    "b2": "Black 2",
    "w2": "White 2",
    "bw": "Black",
    # Generation VI
    "x": "X",
    "y": "Y",
    "omegaruby": "Omega Ruby",
    "or": "Omega Ruby",
    "alphasapphire": "Alpha Sapphire",
    "as": "Alpha Sapphire",
    "oras": "Omega Ruby",
    "xy": "X",
    # Generation VII
    "sun": "Sun",
    "moon": "Moon",
    "ultrasun": "Ultra Sun",
    "ultramoon": "Ultra Moon",
    "usum": "Ultra Sun",
    "sm": "Sun",
    # Generation VIII
    "sword": "Sword",
    "shield": "Shield",
    "swsh": "Sword",
    "brilliantdiamond": "Brilliant Diamond",
    "shiningpearl": "Shining Pearl",
    "bdsp": "Brilliant Diamond",
    "legendsarceus": "Legends: Arceus",
    "pla": "Legends: Arceus",
    # Generation IX
    "scarlet": "Scarlet",
    "violet": "Violet",
    "sv": "Scarlet",
    "legendsza": "Legends: Z-A",
    "za": "Legends: Z-A",
}

# Canonical names themselves always resolve to themselves.
for _game in SUPPORTED_GAMES:
    _EXTRA_ALIASES[_name_key(_game)] = _game


def canonicalize_game(name: str) -> str | None:
    """Return the canonical supported game name, or ``None`` if unsupported."""
    if name is None:
        return None
    key = _name_key(name)
    if not key:
        return None
    return _EXTRA_ALIASES.get(key)


def get_mechanics(game: str) -> GameMechanics | None:
    """Return mechanics for a game name/alias, or ``None`` if unsupported."""
    canonical = canonicalize_game(game)
    if canonical is None:
        return None
    return GAME_MECHANICS.get(canonical)


def is_supported_game(game: str) -> bool:
    return canonicalize_game(game) is not None


def game_generation(game: str) -> int | None:
    mechanics = get_mechanics(game)
    return mechanics.generation if mechanics else None


def supported_methods(game: str) -> tuple[str, ...]:
    mechanics = get_mechanics(game)
    if mechanics is None:
        return ()
    return mechanics.supported_methods


def game_supports_breeding(game: str) -> bool:
    """Whether the game has a breeding/egg mechanic at all."""
    mechanics = get_mechanics(game)
    return bool(mechanics and mechanics.can_breed)


def shiny_charm_available(game: str, encounter_method: str = WILD) -> bool:
    mechanics = get_mechanics(game)
    if mechanics is None:
        return False
    method = str(encounter_method or WILD).strip().lower()
    return method in mechanics.shiny_charm_methods


def masuda_available(game: str, encounter_method: str = BREEDING) -> bool:
    """Whether Masuda can be selected for this game and method.

    Masuda is a breeding-only mechanic.  The explicit ``masuda_supported``
    field in the registry decides whether the game implements it; the
    generation number is never used as a proxy.
    """
    mechanics = get_mechanics(game)
    if mechanics is None:
        return False
    method = str(encounter_method or "").strip().lower()
    return bool(
        method == BREEDING
        and mechanics.masuda_supported
        and BREEDING in mechanics.supported_methods
    )


def masuda_unavailable_reason(
    game: str, encounter_method: str = BREEDING
) -> str | None:
    """Explain why Masuda cannot be selected, or return ``None`` if it can."""
    mechanics = get_mechanics(game)
    if mechanics is None:
        return f"'{game}' is not a supported game."
    method = str(encounter_method or "").strip().lower()
    if not mechanics.can_breed:
        return (
            f"{mechanics.name} has no breeding, so the Masuda Method is not "
            "available."
        )
    if not mechanics.masuda_supported:
        return f"The Masuda Method is not available in {mechanics.name}."
    if method != BREEDING:
        return "The Masuda Method only applies to breeding (eggs)."
    if method not in mechanics.supported_methods:
        return (
            f"{encounter_method_label(method)} is not supported for "
            f"{mechanics.name}."
        )
    return None


def shiny_charm_unavailable_reason(
    game: str, encounter_method: str = WILD
) -> str | None:
    """Explain why the Shiny Charm cannot be selected, or ``None`` if it can."""
    mechanics = get_mechanics(game)
    if mechanics is None:
        return f"'{game}' is not a supported game."
    method = str(encounter_method or WILD).strip().lower()
    if shiny_charm_available(game, method):
        return None
    if not mechanics.has_shiny_charm:
        return f"{mechanics.name} has no Shiny Charm."
    if method not in mechanics.supported_methods:
        return (
            f"{encounter_method_label(method)} is not supported for "
            f"{mechanics.name}."
        )
    return (
        f"The Shiny Charm does not affect "
        f"{encounter_method_label(method).lower()} in {mechanics.name}."
    )


# ---------------------------------------------------------------------------
# Odds calculation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OddsResult:
    """Result of the authoritative per-encounter odds calculation."""

    supported: bool
    game: str
    encounter_method: str
    base_odds: int | None = None
    total_rolls: int | None = None
    probability: float | None = None
    one_in: float | None = None
    shiny_charm_applied: bool = False
    masuda_applied: bool = False
    warnings: tuple[str, ...] = ()
    reason: str | None = None

    @property
    def percent(self) -> float | None:
        """Per-encounter probability as a percentage."""
        return None if self.probability is None else self.probability * 100.0

    @property
    def display(self) -> str:
        """Human-readable ``1 in N`` representation."""
        if not self.supported or self.one_in is None:
            return "Unavailable"
        return format_one_in(self.one_in)


def format_one_in(one_in: float) -> str:
    """Format a ``1 in N`` value without misleading precision."""
    if one_in >= 1000:
        return f"1 in {one_in:,.0f}"
    if one_in >= 10:
        return f"1 in {one_in:,.1f}"
    return f"1 in {one_in:,.2f}"


def _unsupported(game: str, method: str, reason: str) -> OddsResult:
    return OddsResult(
        supported=False,
        game=str(game),
        encounter_method=str(method),
        reason=reason,
    )


def calculate_shiny_odds(
    game: str,
    encounter_method: str = WILD,
    shiny_charm: bool = False,
    masuda_method: bool = False,
) -> OddsResult:
    """Calculate the authoritative per-encounter shiny probability.

    The probability is compounded over all shiny rolls:

        p = 1 - (1 - 1 / base_odds) ** total_rolls

    This deliberately does *not* use the simplified ``total_rolls / base_odds``
    approximation.  The exact formula gives values such as ~1/1365.67 for three
    rolls at 1/4096 and ~1/512.44 for eight rolls.
    """
    mechanics = get_mechanics(game)
    if mechanics is None:
        return _unsupported(
            game,
            encounter_method,
            f"'{game}' is not a supported game. No odds are calculated.",
        )

    method = str(encounter_method or WILD).strip().lower()
    if method not in ENCOUNTER_METHODS:
        return _unsupported(
            game,
            method,
            f"Unknown encounter method '{encounter_method}'.",
        )
    if method not in mechanics.supported_methods:
        return _unsupported(
            mechanics.name,
            method,
            f"{encounter_method_label(method)} is not supported for {mechanics.name}.",
        )

    warnings: list[str] = []

    charm_applied = bool(
        shiny_charm
        and method in mechanics.shiny_charm_methods
        and mechanics.shiny_charm_rerolls > 0
    )
    if shiny_charm and not charm_applied:
        warnings.append(
            f"The Shiny Charm does not affect {encounter_method_label(method).lower()} "
            f"in {mechanics.name}."
        )

    masuda_applied = bool(
        masuda_method
        and method == BREEDING
        and mechanics.masuda_supported
        and mechanics.masuda_rerolls is not None
    )
    if masuda_method and not masuda_applied:
        reason = masuda_unavailable_reason(mechanics.name, method)
        if reason:
            warnings.append(reason)

    base_rolls = 1
    bonus_rolls = 0
    if masuda_applied:
        bonus_rolls += int(mechanics.masuda_rerolls)
    if charm_applied:
        bonus_rolls += mechanics.shiny_charm_rerolls

    # Generation VIII/IX egg bug: a bonus roll skips the initial roll.
    if (
        method == BREEDING
        and mechanics.breeding_skips_initial_roll
        and bonus_rolls > 0
    ):
        total_rolls = bonus_rolls
    else:
        total_rolls = base_rolls + bonus_rolls

    probability = 1.0 - (1.0 - (1.0 / mechanics.base_odds)) ** total_rolls
    one_in = 1.0 / probability

    if mechanics.name == "Legends: Arceus" and charm_applied:
        warnings.append(
            "Legends: Arceus: Pokédex research bonuses are not modelled. The charm "
            "requires Research Level 10, so a charmed hunt's real minimum is 5 rolls "
            "(~1/819.6), not 4."
        )
    if mechanics.name in ("Brilliant Diamond", "Shining Pearl") and shiny_charm:
        if method != BREEDING:
            warnings.append(
                "In BDSP the Shiny Charm only affects breeding; this hunt uses base odds."
            )
    if mechanics.name in ("Sword", "Shield"):
        warnings.append(
            "Special methods (Brilliant Pokémon, Dynamax Adventures, dens, curry) and "
            "shiny-locked encounters are not modelled."
        )
    if mechanics.name in ("Scarlet", "Violet"):
        warnings.append(
            "Special methods (mass outbreaks, Sparkling Power sandwiches, Tera Raids) "
            "and shiny-locked encounters are not modelled."
        )

    return OddsResult(
        supported=True,
        game=mechanics.name,
        encounter_method=method,
        base_odds=mechanics.base_odds,
        total_rolls=total_rolls,
        probability=probability,
        one_in=one_in,
        shiny_charm_applied=charm_applied,
        masuda_applied=masuda_applied,
        warnings=tuple(warnings),
    )


def cumulative_probability(probability: float, encounters: int) -> float:
    """Cumulative probability (0-1) of at least one shiny after N encounters."""
    if probability is None:
        return 0.0
    n = max(0, int(encounters))
    if n == 0:
        return 0.0
    return 1.0 - (1.0 - probability) ** n


def cumulative_percent(probability: float, encounters: int) -> float:
    """Cumulative probability as a percentage."""
    return cumulative_probability(probability, encounters) * 100.0
