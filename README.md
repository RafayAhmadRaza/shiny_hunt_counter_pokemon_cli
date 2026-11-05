# Pokémon Shiny Hunt Tracker

A simple Python terminal-based Pokémon shiny hunt tracker. Track encounters, manage multiple hunts, and save your progress locally using CSV files.

## Features

- **Multiple Hunts:** Create and manage shiny hunts for different Pokémon and games.
- **Encounter Tracking:** Increment or decrement encounter counts.
- **Custom Encounter Updates:** Add or remove a specified number of encounters at once.
- **Shiny Charm Tracking:** Record whether a hunt has the Shiny Charm.
- **Hunt Identification:** Each hunt receives a unique ID to ensure updates affect the correct Pokémon.
- **CSV Persistence:** Automatically save hunt information locally, allowing progress to persist between sessions.
- **Default Shiny Odds:** Automatically assign base shiny odds based on the Pokémon generation.

## Requirements

- Python 3.10 or newer
- pandas

## Installation

Clone the repository:

```bash
git clone <repository-url>
cd <repository-directory>
```

Install the dependencies:

```bash
pip install pandas
```

## Usage

Start the application:

```bash
python main.py
```

The application provides a terminal menu with the following options:

| Option | Description |
|---|---|
| A | Add a new shiny hunt |
| L | List existing hunts |
| R | Remove a hunt |
| S | Select and manage a hunt |
| Q | Quit the application |

When managing an individual hunt, you can:

- Add one encounter.
- Remove one encounter.
- Add a custom number of encounters.
- Remove a custom number of encounters.
- View the current hunt information.

Your hunt data is stored in `hunts.csv` in the working directory.

## Shiny Odds

The tracker assigns default base shiny odds according to the Pokémon generation:

| Generation | Default Odds |
|---|---|
| Generation I–V | 1 / 8192 |
| Generation VI onward | 1 / 4096 |

These are simplified defaults. Actual shiny odds can vary depending on the specific game, encounter method, and applicable bonuses.

## Data Storage

Hunt information is stored locally in a CSV file with the following fields:

| Field | Description |
|---|---|
| `name` | Pokémon species being hunted |
| `encounter_count` | Total recorded encounters |
| `generation` | Pokémon game generation |
| `game` | Specific Pokémon game |
| `is_done` | Whether the hunt has been completed |
| `odds` | Base shiny odds |
| `shiny_charm` | Whether the Shiny Charm is available |
| `hunt_id` | Unique identifier for the hunt |

The CSV file is created automatically when the application is first launched.

## Future Improvements

Potential additions include:

- Game-specific shiny odds.
- Improved input validation.
- Shiny Charm odds calculations.
- A more comprehensive hunt statistics system.
- Additional hunt management options.

## License

Free! Do whatever you want with the source code! If you want to you can make a UI for it!

