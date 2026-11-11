# Shiny Mechanics Reference

This document records the shiny-odds mechanics used by the tracker, the
formula behind the numbers, the per-game capabilities, the source material, and
the cases the tracker deliberately does **not** model.

The single source of truth in code is [`shiny_mechanics.py`](shiny_mechanics.py).
The CSV `odds` column is a legacy column kept for compatibility only; it is
never used to calculate a probability.

Research date: **11 November 2026**.

---

## 1. The formula

Shiny checks are independent rolls. A game can give more than one roll per
encounter or egg, so the chance of at least one shiny in one attempt is
**compounded**, not simply `rolls / base_odds`:

```text
p_attempt = 1 - (1 - 1 / base_odds) ** total_rolls
```

The probability of at least one shiny after `n` attempts is:

```text
p_cumulative = 1 - (1 - p_attempt) ** n
```

The tracker uses the exact formula everywhere. For example, three rolls at
`1/4096` give:

```text
1 - (1 - 1/4096)^3 = 0.000732...  ->  ~1 in 1365.67
```

not `3/4096 = 0.0007324...` (the linear approximation is slightly higher).
Displayed `1 in N` values round for readability; calculations keep full
precision.

The tracker distinguishes:

- **Odds per encounter** for wild and static hunts.
- **Odds per egg** for breeding hunts.
- **Cumulative chance** after the current number of encounters or eggs.

Breeding counters are labelled **Eggs hatched**, never encounters.

---

## 2. Base odds

| Generation | Base odds per roll |
|---|---|
| III | 1 in 8,192 |
| IV | 1 in 8,192 |
| V | 1 in 8,192 |
| VI | 1 in 4,096 |
| VII | 1 in 4,096 |
| VIII | 1 in 4,096 |
| IX | 1 in 4,096 |

The Shiny Charm adds rolls on top of the base roll, except where noted. The
Masuda Method adds rolls to **breeding** only.

---

## 3. Per-game capability and odds matrix

Only games whose ordinary shiny mechanics could be verified are listed. The
game selectbox in the app is built from this registry. Capabilities are stored
explicitly for each game; the generation number alone is never used to decide
whether breeding or the Masuda Method exists.

`Methods` lists the encounter methods the tracker offers. `Charm` lists where
the Shiny Charm actually adds rolls.

| Game | Gen | Methods | Breeding | Masuda | Charm | Base odds | Masuda odds | Masuda + Charm |
|---|:---:|---|:---:|:---:|---|---|---|---|
| Ruby | III | Wild, Breeding, Static | Yes | No | No | 1/8,192 | n/a | n/a |
| Sapphire | III | Wild, Breeding, Static | Yes | No | No | 1/8,192 | n/a | n/a |
| Emerald | III | Wild, Breeding, Static | Yes | No | No | 1/8,192 | n/a | n/a |
| FireRed | III | Wild, Breeding, Static | Yes | No | No | 1/8,192 | n/a | n/a |
| LeafGreen | III | Wild, Breeding, Static | Yes | No | No | 1/8,192 | n/a | n/a |
| Diamond | IV | Wild, Breeding, Static | Yes | Yes | No | 1/8,192 | 1/1,638.8 | n/a (no Charm) |
| Pearl | IV | Wild, Breeding, Static | Yes | Yes | No | 1/8,192 | 1/1,638.8 | n/a (no Charm) |
| Platinum | IV | Wild, Breeding, Static | Yes | Yes | No | 1/8,192 | 1/1,638.8 | n/a (no Charm) |
| HeartGold | IV | Wild, Breeding, Static | Yes | Yes | No | 1/8,192 | 1/1,638.8 | n/a (no Charm) |
| SoulSilver | IV | Wild, Breeding, Static | Yes | Yes | No | 1/8,192 | 1/1,638.8 | n/a (no Charm) |
| Black | V | Wild, Breeding, Static | Yes | Yes | No | 1/8,192 | 1/1,365.8 | n/a (no Charm) |
| White | V | Wild, Breeding, Static | Yes | Yes | No | 1/8,192 | 1/1,365.8 | n/a (no Charm) |
| Black 2 | V | Wild, Breeding, Static | Yes | Yes | All methods | 1/8,192 | 1/1,365.8 | 1/1,024.4 |
| White 2 | V | Wild, Breeding, Static | Yes | Yes | All methods | 1/8,192 | 1/1,365.8 | 1/1,024.4 |
| X | VI | Wild, Breeding, Static | Yes | Yes | All methods | 1/4,096 | 1/683.1 | 1/512.4 |
| Y | VI | Wild, Breeding, Static | Yes | Yes | All methods | 1/4,096 | 1/683.1 | 1/512.4 |
| Omega Ruby | VI | Wild, Breeding, Static | Yes | Yes | All methods | 1/4,096 | 1/683.1 | 1/512.4 |
| Alpha Sapphire | VI | Wild, Breeding, Static | Yes | Yes | All methods | 1/4,096 | 1/683.1 | 1/512.4 |
| Sun | VII | Wild, Breeding, Static | Yes | Yes | All methods | 1/4,096 | 1/683.1 | 1/512.4 |
| Moon | VII | Wild, Breeding, Static | Yes | Yes | All methods | 1/4,096 | 1/683.1 | 1/512.4 |
| Ultra Sun | VII | Wild, Breeding, Static | Yes | Yes | All methods | 1/4,096 | 1/683.1 | 1/512.4 |
| Ultra Moon | VII | Wild, Breeding, Static | Yes | Yes | All methods | 1/4,096 | 1/683.1 | 1/512.4 |
| Sword | VIII | Wild, Breeding, Static | Yes | Yes | All methods | 1/4,096 | 1/683.1 | 1/512.4 |
| Shield | VIII | Wild, Breeding, Static | Yes | Yes | All methods | 1/4,096 | 1/683.1 | 1/512.4 |
| Brilliant Diamond | VIII | Wild, Breeding, Static | Yes | Yes | Breeding only | 1/4,096 | 1/683.1 | 1/512.4 |
| Shining Pearl | VIII | Wild, Breeding, Static | Yes | Yes | Breeding only | 1/4,096 | 1/683.1 | 1/512.4 |
| Legends: Arceus | VIII | Wild | **No** | **No** | Wild only | 1/4,096 | n/a | n/a |
| Scarlet | IX | Wild, Breeding | Yes | Yes | Wild, breeding | 1/4,096 | 1/683.1 | 1/512.4 |
| Violet | IX | Wild, Breeding | Yes | Yes | Wild, breeding | 1/4,096 | 1/683.1 | 1/512.4 |
| Legends: Z-A | IX | Wild | **No** | **No** | Wild only | 1/4,096 | n/a | n/a |

Notes:

- **Generation III** has breeding but predates the Masuda Method, so Masuda is
  unavailable even though eggs exist.
- **Legends: Arceus** has no breeding, and its static/fixed encounters are
  shiny-locked.
- **Legends: Z-A** has no breeding and no eggs. Baby Pokémon appear in the wild
  zones instead. Its wild encounters use a 1/4,096 base rate and the Shiny Charm
  adds three rolls.
- **Scarlet/Violet** fixed/static symbol encounters are shiny-locked and
  unaffected by the Shiny Charm, so the tracker does not offer the static
  method.
- **Sword/Shield** statics are supported in general, but some scripted
  encounters are shiny-locked or charm-immune (see limitations).
- **Brilliant Diamond/Shining Pearl** statics are supported except for the gift
  Mew and Jirachi.
- **Black/White** have no Shiny Charm; **Black 2/White 2** introduce it.
- **Diamond/Pearl/Platinum/HeartGold/SoulSilver** have no Shiny Charm.

---

## 4. Shiny Charm rules

The Shiny Charm adds extra rolls. The exact total depends on the game and, in
some games, on the encounter method.

| Game(s) | Charm affects | Total rolls with charm | Approx. odds |
|---|---|---|---|
| Gen III | Nothing (no Shiny Charm) | 1 | 1/8,192 |
| Gen IV | Nothing (no Shiny Charm) | 1 | 1/8,192 |
| Black/White | Nothing (no Shiny Charm) | 1 | 1/8,192 |
| Black 2/White 2 | Wild, breeding, static | 3 | 1/2,731.0 |
| Gen VI | Wild, breeding, static | 3 | 1/1,365.7 |
| Gen VII | Wild, breeding, static | 3 | 1/1,365.7 |
| Sword/Shield | Wild and static | 3 | 1/1,365.7 |
| Sword/Shield | Breeding | 2 (egg-roll bug) | 1/2,048.3 |
| BDSP | Breeding only | 2 (egg-roll bug) | 1/2,048.3 |
| BDSP | Wild and static | 1 | 1/4,096 |
| Legends: Arceus | Wild | 4 | 1/1,024.4 |
| Scarlet/Violet | Wild | 3 | 1/1,365.7 |
| Scarlet/Violet | Breeding | 2 (egg-roll bug) | 1/2,048.3 |
| Legends: Z-A | Wild | 4 | 1/1,024.4 |

The app disables the Shiny Charm checkbox when it has no effect for the
selected game and method, and explains why.

### Generation VIII/IX breeding egg-roll bug

In Sword/Shield, BDSP and Scarlet/Violet, when a breeding bonus applies, the
initial egg roll is skipped and replaced by the bonus rolls. The tracker models
this exactly:

| Breeding case | Rolls | Approx. odds |
|---|---:|---|
| No charm, no Masuda | 1 | 1/4,096 |
| Charm only | 2 | 1/2,048.3 |
| Masuda only | 6 | 1/683.1 |
| Masuda + charm | 8 | 1/512.4 |

This is why charm-only breeding is `~1 in 2048.25`, not `~1 in 1365.7`.

---

## 5. Masuda Method rules

The Masuda Method applies only when breeding with a Pokémon from a different
language game. It adds rolls to the single base roll. It was introduced in
Generation IV. Games without breeding never offer it.

| Game(s) | Masuda total rolls | Approx. odds | With Shiny Charm |
|---|---:|---|---|
| Gen III | Not available (predates Masuda) | n/a | n/a |
| Gen IV | 5 | 1/1,638.8 | n/a (no Charm) |
| Black/White | 6 | 1/1,365.8 | n/a (no Charm) |
| Black 2/White 2 | 6 | 1/1,365.8 | 8 rolls, 1/1,024.4 |
| Gen VI | 6 | 1/683.1 | 8 rolls, 1/512.4 |
| Gen VII | 6 | 1/683.1 | 8 rolls, 1/512.4 |
| Sword/Shield | 6 | 1/683.1 | 8 rolls, 1/512.4 |
| BDSP | 6 | 1/683.1 | 8 rolls, 1/512.4 |
| Legends: Arceus | Not available (no breeding) | n/a | n/a |
| Scarlet/Violet | 6 | 1/683.1 | 8 rolls, 1/512.4 |
| Legends: Z-A | Not available (no breeding) | n/a | n/a |

Masuda is selectable only when the selected encounter method is **Breeding**.
Selecting wild or static encounters disables it and explains that Masuda only
applies to eggs. Switching games or methods updates the option immediately; it
is never permanently locked by an earlier selection.

### Gen IV source disagreement

Serebii's older general shiny page describes the Gen IV Masuda Method as four
rolls (`~1/2048`). Bulbapedia and modern independent research describe five
rolls (`~1/1638.8`). This tracker follows Bulbapedia/modern research and uses
**five rolls**. The discrepancy is recorded here rather than silently
averaged.

---

## 6. Legends: Arceus caveat

The tracker models the Shiny Charm as **3 extra rolls** for wild encounters
(4 total, `~1/1024.4`). In the real game the charm requires Research Level 10
for the species, and Research Level 10 itself adds a roll. A charmed hunt
therefore has a practical minimum of **5 rolls** (`~1/819.6`), before
outbreaks, Perfect research entries or other bonuses.

The tracker does not model Pokédex research levels, outbreaks, or other
bonuses. The app displays this caveat whenever the PLA charm is applied.

---

## 7. Deliberately unsupported games/methods

The tracker does not calculate odds for:

- **Generation I and II** (no standard shiny mechanic as modelled here).
- **Let's Go, Pikachu!/Eevee!** (catch-combo and lure mechanics).
- Spin-offs (Mystery Dungeon, Ranger, Pokéwalker, etc.).
- **Gen VI chain fishing, Poké Radar and hordes.**
- **Gen VII SOS battles and DexNav.**
- **Gen VIII Brilliant Pokémon, Dynamax Adventures, Max Raid dens, curry,
  Poké Radar, Ramanas Park.**
- **Gen IX mass outbreaks, Sparkling Power sandwiches, Tera Raid battles,
  and shiny-locked static encounters.**
- **Legends: Z-A static/fixed encounters** (not modelled by this tracker).
- Shiny-locked gifts/scripted encounters in any game.

Legends: Arceus and Legends: Z-A **are** supported games for wild encounters.
They are not unsupported games; they simply have no breeding or Masuda Method.

For unsupported games the app keeps existing CSV rows intact, shows the odds
as unavailable, and reports the game in a warning. New hunts can only be
created for supported games.

---

## 8. Sources

Primary references:

- Bulbapedia — Shiny Pokémon:
  https://bulbapedia.bulbagarden.net/wiki/Shiny_Pok%C3%A9mon
- Bulbapedia — Shiny Charm:
  https://bulbapedia.bulbagarden.net/wiki/Shiny_Charm
- Bulbapedia — Masuda method:
  https://bulbapedia.bulbagarden.net/wiki/Masuda_method
- Serebii — general shiny mechanics:
  https://www.serebii.net/games/shiny.shtml
- Serebii — Sword/Shield shiny Pokémon:
  https://www.serebii.net/swordshield/shinypokemon.shtml
- Serebii — Brilliant Diamond/Shining Pearl shiny Pokémon:
  https://www.serebii.net/brilliantdiamondshiningpearl/shinypokemon.shtml
- Serebii — Legends: Arceus shiny Pokémon:
  https://www.serebii.net/legendsarceus/shinypokemon.shtml
- Serebii — Scarlet/Violet shiny Pokémon:
  https://www.serebii.net/scarletviolet/shinypokemon.shtml
- Serebii — Legends: Z-A shiny Pokémon:
  https://www.serebii.net/legendsz-a/shinypokemon.shtml
- RotomLabs — BDSP shiny rates:
  https://rotomlabs.net/brilliant-diamond-shining-pearl/shiny-rates
- RotomLabs — Legends: Arceus shiny rates:
  https://rotomlabs.net/legends-arceus/shiny-rates

Where sources disagree, the disagreement is called out in the relevant
section above. No odds were invented or extrapolated from unsupported games.

---

## 9. Implementation map

| Concern | Location |
|---|---|
| Game registry, explicit breeding/Masuda capabilities, aliases, method labels | `shiny_mechanics.py` |
| `calculate_shiny_odds`, `cumulative_probability` | `shiny_mechanics.py` |
| CSV schema, migration, atomic writes | `functions.py` |
| Phase transaction and rollback | `functions.py` (`record_phase`) |
| Streamlit dialogs/cards/history | `main.py` |
| Automated tests | `tests/` |
