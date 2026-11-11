# Pokémon Shiny Hunt Tracker

A local Streamlit app for tracking Pokémon shiny hunts, encounter/egg counters,
game-specific shiny odds, and **phases** (shinies found before the target).

All data lives in plain CSV files. There is no database and no account.

## Features

- **Game-aware odds:** base odds, Shiny Charm and Masuda Method come from one
  researched per-game registry (`shiny_mechanics.py`). Breeding and Masuda
  support are explicit per-game capabilities, not assumptions based on
  generation.
- **Exact probability:** uses `1 - (1 - 1/base_odds)^rolls`, compounded over
  the number of encounters or eggs. It does not use a stale stored odds value.
- **Encounter methods:** wild, breeding and static, limited to the methods the
  selected game actually supports. Breeding hunts show eggs hatched and odds
  per egg rather than encounters.
- **Correct Masuda UI:** Masuda is selectable only for breeding in games that
  implement it. Wild/static selections, and games without breeding such as
  Legends: Arceus and Legends: Z-A, disable it with an explanation.
- **Phasing:** record a shiny found before the target. The original hunt keeps
  its `hunt_id`, target, game, generation, settings and completion status; only
  the counter resets to zero. Phase numbers restart at 1 for every hunt.
- **Phase history:** grouped by `hunt_id`, separate from completed hunts, and
  shown in expandable sections.
- **Safe persistence:**
  - both CSVs are validated before writing;
  - writes use a temporary file + `os.replace` (atomic on the same filesystem);
  - duplicate `hunt_id` values and duplicate phase numbers are rejected;
  - the two-file phase/delete transactions roll back the first file if the
    second write fails;
  - timestamped backups are created before migration and before phase/delete
    writes.
- **Backwards-compatible migration:** old CSVs are upgraded in place with
  defaults (`wild`, Masuda off) while preserving IDs, counters, targets,
  completion flags and valid charm settings.

## Requirements

- Python 3.10 or newer
- `pandas`
- `streamlit`

For the test suite:

- `pytest`

## Installation

```bash
git clone <repository-url>
cd <repository-directory>
python -m venv .venv
source .venv/bin/activate
pip install pandas streamlit pytest
```

## Running the app

```bash
streamlit run main.py
```

Streamlit opens the app in your browser (usually
`http://localhost:8501`). All paths are relative to the directory you run the
command from, so run it from the project root.

A minimal legacy terminal loop is still available with `python functions.py`,
but the Streamlit app is the supported interface.

## Using the tracker

### Add a hunt

1. Open **Add a new hunt**.
2. Pick a supported game. The generation is derived from the game.
3. Pick an encounter method. Only verified methods for that game are listed.
4. Enter the Pokémon name.
5. Toggle the Shiny Charm / Masuda Method when they apply. The app disables
   them when the game or method does not support them and shows the reason.
6. Press **Add hunt**.

Masuda is a breeding-only mechanic. It becomes selectable when the chosen game
supports breeding and the method is **Breeding**. Switching to wild or static
encounters disables it again; switching back re-enables it. Games without
breeding, including Legends: Arceus and Legends: Z-A, never offer it.

The new row starts at zero encounters and receives a fresh UUID.

### Count encounters or eggs

Use **Custom amount** plus **Add** / **Remove**. The counter never goes below
zero. Each hunt shows the per-encounter or per-egg odds, the number of shiny
rolls, and the cumulative chance after the current counter.

### Record a phase

1. Click **Record phase** on an active hunt.
2. Enter the Pokémon that appeared. It cannot be blank.
3. Enter the number of encounters/eggs in that phase.
4. Press **Record phase**.

The app writes one row to `phased.csv`, resets that hunt's counter to zero and
keeps everything else. **Cancel**, or closing the dialog, writes nothing.

Phase numbers are calculated per `hunt_id`: the first phase is always 1, the
next is 2, and another hunt's phases do not affect them.

If the CSV changed while the dialog was open, the record is rejected rather
than overwriting newer progress.

### Complete, reopen and delete

- **Mark hunt complete** moves the hunt into **Completed hunts**.
- **Reopen hunt** moves it back to active.
- **Delete** removes the hunt and its phases after a confirmation dialog, and
  creates a backup first.

## Data storage

### `hunts.csv`

| Column | Meaning |
|---|---|
| `name` | Target Pokémon |
| `encounter_count` | Current encounters/eggs since the last phase |
| `generation` | Derived from `game` for supported games |
| `game` | Canonical supported game name |
| `is_done` | Hunt completed |
| `odds` | Legacy base-odds column (not used in calculations) |
| `shiny_charm` | Shiny Charm enabled and applicable |
| `hunt_id` | Stable UUID; never changed by phasing |
| `encounter_method` | `wild`, `breeding`, or `static` |
| `masuda_method` | Masuda Method enabled and applicable |

### `phased.csv`

| Column | Meaning |
|---|---|
| `phase` | Phase number for that hunt, starting at 1 |
| `target_pokemon` | The original target's name |
| `encounter_count` | Encounters/eggs in that phase |
| `phased_pokemon` | Pokémon that appeared |
| `hunt_id` | The original hunt's ID |

Legacy phase files used `name, phase, encounter_count, pokemon_phased_on,
phase_count`. Migration renames `name` → `target_pokemon` and
`pokemon_phased_on` → `phased_pokemon`, and maps rows to a `hunt_id` by target
name.

## Migration and backups

Both CSVs are migrated automatically when the app starts. Migration is
idempotent: once the current schema is present, later starts do not rewrite the
files or create new backups.

Backups are written to `backups/<reason>_<timestamp>/` next to the CSVs. Both
the pre-extension backup and the automatic migration backup are kept locally.

The `/tmp` path is never used for tracker data; all writes stay in the project
directory (or the directory you run the app from).

## Shiny odds and sources

The full researched mechanics, per-game roll counts, source URLs and known
disagreements are documented in [`SHINY_MECHANICS.md`](SHINY_MECHANICS.md).

Highlights:

- Gen III–V base odds: 1/8192; Gen VI–IX: 1/4096.
- Shiny Charm adds 2 rolls (3 total) in most games, but 3 extra rolls in
  Legends: Arceus and Legends: Z-A, only affects breeding in BDSP, and does not
  exist in Gen III/IV or Black/White.
- Masuda Method: 5 rolls in Gen IV, 6 rolls from Gen V onward, stacking with
  the charm where both exist.
- Gen VIII/IX breeding has an egg-roll bug: charm-only breeding is 2 rolls,
  Masuda is 6, and Masuda + charm is 8.
- Gen III has breeding but no Masuda Method. Legends: Arceus and Legends: Z-A
  have no breeding, so they have no Masuda Method either.
- Gen IV Masuda is 5 rolls here. Serebii's older page says 4; the discrepancy
  is documented.

Unsupported games (Gen I/II, Let's Go, spin-offs) are reported explicitly.
Their existing rows are preserved, but no odds are calculated. Legends: Arceus
and Legends: Z-A are supported for wild encounters.

## Tests

```bash
python -m pytest -q
```

The suite covers:

- registry values, explicit per-game breeding/Masuda capabilities, aliases,
  charm/Masuda combinations, egg-roll bug and the exact compounded formula;
- hunt creation, sanitisation, counter helpers, persistence and duplicate
  protection;
- phasing: per-hunt phase numbering, counter reset, settings/completion
  preservation, invalid input, stale-dialog rejection and rollback;
- legacy CSV migration and idempotency;
- a Streamlit `AppTest` smoke test that boots the UI and creates a hunt.

## Limitations

- Special methods are not modelled: chain fishing, Poké Radar, hordes, SOS
  battles, DexNav, Brilliant Pokémon, Dynamax Adventures, Max Raid dens,
  curry, Ramanas Park, mass outbreaks, Sparkling Power sandwiches, Tera Raids,
  and shiny-locked static encounters.
- Legends: Arceus Research Level 10 is not modelled; the app warns that a
  charmed hunt's practical minimum is 5 rolls.
- Legends: Z-A is modelled for wild encounters only; static/fixed encounters
  are not modelled.
- The tracker is single-user. There is no multi-user locking; the in-process
  lock only protects against overlapping Streamlit interactions in one server
  process.
- CSV edits made outside the app are not watched live; reload the page.

## License

Free! Do whatever you want with the source code.
