"""CSV persistence, migration and phasing logic for the Shiny Hunt Tracker.

The module deliberately keeps using plain CSV files (no database).  Every write
goes through :func:`_atomic_write_csv`, which writes a temporary file in the
target directory and then replaces the original with :func:`os.replace`.  A
process-level :class:`threading.RLock` serialises read-modify-write cycles so
that two Streamlit interactions cannot interleave.

Shiny odds themselves live in :mod:`shiny_mechanics`.  The legacy ``odds``
column is kept for backwards compatibility, but it is never used to calculate
probabilities.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from uuid import uuid4

import pandas as pd

from shiny_mechanics import (
    ENCOUNTER_METHODS,
    SUPPORTED_GAMES,
    WILD,
    OddsResult,
    calculate_shiny_odds,
    canonicalize_game,
    cumulative_percent,
    get_mechanics,
    masuda_available,
    shiny_charm_available,
    supported_methods,
)

# ---------------------------------------------------------------------------
# Paths and schemas
# ---------------------------------------------------------------------------

CSV_PATH = "hunts.csv"
PHASED_CSV_PATH = "phased.csv"
BACKUP_ROOT = "backups"

HUNT_COLUMNS = [
    "name",
    "encounter_count",
    "generation",
    "game",
    "is_done",
    "odds",
    "shiny_charm",
    "hunt_id",
    "encounter_method",
    "masuda_method",
]

PHASE_COLUMNS = [
    "phase",
    "target_pokemon",
    "encounter_count",
    "phased_pokemon",
    "hunt_id",
]

_HUNT_DEFAULTS = {
    "name": "",
    "encounter_count": 0,
    "generation": 0,
    "game": "",
    "is_done": False,
    "odds": None,
    "shiny_charm": False,
    "hunt_id": None,
    "encounter_method": WILD,
    "masuda_method": False,
}

_PHASE_DEFAULTS = {
    "phase": 0,
    "target_pokemon": "",
    "encounter_count": 0,
    "phased_pokemon": "",
    "hunt_id": "",
}

_CSV_LOCK = threading.RLock()


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TrackerError(Exception):
    """Base class for tracker errors."""


class ValidationError(TrackerError):
    """Raised when input or stored data fails validation."""


class DuplicateHuntError(ValidationError):
    """Raised when a hunt_id already exists."""


class DuplicatePhaseError(ValidationError):
    """Raised when a phase number already exists for a hunt."""


class ConcurrentUpdateError(TrackerError):
    """Raised when the CSV changed since the caller last looked at it."""


class TransactionError(TrackerError):
    """Raised when a two-file update could not be completed."""


# ---------------------------------------------------------------------------
# Small coercion helpers
# ---------------------------------------------------------------------------


def _coerce_bool(value, default: bool = False) -> bool:
    """Coerce a CSV value into a boolean, falling back to ``default``."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "t"}:
        return True
    if text in {"false", "0", "no", "n", "f", ""}:
        return False
    return default


def _coerce_int(value, default: int = 0) -> int:
    """Coerce a CSV value into an integer, falling back to ``default``."""
    try:
        if value is None or pd.isna(value):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clean_text(value) -> str:
    """Strip a value to text, treating ``None`` and NaN as an empty string."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _values_equal(left, right) -> bool:
    """Compare two CSV values while tolerating NaN and type differences."""
    try:
        left_na = left is None or pd.isna(left)
    except (TypeError, ValueError):
        left_na = left is None
    try:
        right_na = right is None or pd.isna(right)
    except (TypeError, ValueError):
        right_na = right is None
    if left_na or right_na:
        return left_na and right_na
    return str(left).strip() == str(right).strip()


def _sanitize_method(game: str, method: str) -> str:
    """Return a method the game supports, defaulting to wild encounters."""
    methods = supported_methods(game)
    method = _clean_text(method).lower()
    if not methods:
        return method if method in ENCOUNTER_METHODS else WILD
    if method in methods:
        return method
    return WILD if WILD in methods else methods[0]


def _fallback_odds(generation: int) -> int:
    """Legacy base odds for games without a mechanics registry entry."""
    return 8192 if generation <= 5 else 4096


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Pokemon:
    """A single shiny hunt.

    ``odds`` is the legacy base-odds column.  It is filled from the mechanics
    registry for supported games but calculations always go through
    :func:`calculate_shiny_odds`.
    """

    name: str
    encounter_count: int = 0
    generation: int = 0
    game: str = ""
    is_done: bool = False
    hunt_id: str = field(default_factory=lambda: str(uuid4()))
    odds: int | None = None
    shiny_charm: bool = False
    encounter_method: str = WILD
    masuda_method: bool = False

    def __post_init__(self) -> None:
        """Sanitise fields and derive metadata from the mechanics registry."""
        self.name = _clean_text(self.name)
        self.game = _clean_text(self.game)
        self.encounter_count = max(0, _coerce_int(self.encounter_count, 0))
        self.is_done = _coerce_bool(self.is_done)
        self.hunt_id = _clean_text(self.hunt_id) or str(uuid4())

        canonical = canonicalize_game(self.game)
        mechanics = get_mechanics(self.game)
        if mechanics is not None:
            self.game = canonical or mechanics.name
            self.generation = mechanics.generation
            self.odds = mechanics.base_odds
        else:
            self.generation = _coerce_int(self.generation, 0)
            self.odds = _coerce_int(self.odds, 0) or _fallback_odds(self.generation)

        self.encounter_method = _sanitize_method(self.game, self.encounter_method)
        self.shiny_charm = bool(self.shiny_charm)
        self.masuda_method = bool(self.masuda_method)

        # Sanitise bonuses that cannot apply to this game/method.
        if mechanics is not None:
            self.shiny_charm = bool(
                self.shiny_charm
                and shiny_charm_available(self.game, self.encounter_method)
            )
            self.masuda_method = bool(
                self.masuda_method
                and masuda_available(self.game, self.encounter_method)
            )
        else:
            self.masuda_method = False

    @classmethod
    def from_row(cls, row) -> "Pokemon":
        """Build a sanitised Pokemon from a CSV row (Series or mapping)."""
        get = row.get if hasattr(row, "get") else lambda key, default=None: row[key]
        return cls(
            name=get("name", ""),
            encounter_count=get("encounter_count", 0),
            generation=get("generation", 0),
            game=get("game", ""),
            is_done=get("is_done", False),
            hunt_id=get("hunt_id", ""),
            odds=get("odds", None),
            shiny_charm=get("shiny_charm", False),
            encounter_method=get("encounter_method", WILD),
            masuda_method=get("masuda_method", False),
        )

    def to_row(self) -> dict:
        """Convert the hunt into a CSV-ready mapping."""
        return {column: getattr(self, column) for column in HUNT_COLUMNS}

    @property
    def odds_result(self) -> OddsResult:
        """Authoritative odds result for this hunt."""
        return calculate_shiny_odds(
            self.game,
            self.encounter_method,
            self.shiny_charm,
            self.masuda_method,
        )


@dataclass
class Phased:
    """One shiny that appeared before the target."""

    target_pokemon: str
    encounter_count: int
    phased_pokemon: str
    hunt_id: str
    phase: int = 1

    def to_row(self) -> dict:
        """Convert the phase into a CSV-ready mapping."""
        return {column: getattr(self, column) for column in PHASE_COLUMNS}


@dataclass
class MigrationReport:
    """Outcome of :func:`migrate_csvs`."""

    hunts_changed: bool
    phases_changed: bool
    backup_dir: str | None = None
    notes: tuple[str, ...] = ()
    unsupported_hunts: tuple[str, ...] = ()
    hunts_rows: int = 0
    phase_rows: int = 0

    @property
    def changed(self) -> bool:
        """Whether either CSV was changed by the migration."""
        return self.hunts_changed or self.phases_changed


# ---------------------------------------------------------------------------
# Atomic persistence helpers
# ---------------------------------------------------------------------------


def _read_csv_safe(csv_path: str) -> pd.DataFrame:
    """Read a CSV, returning an empty DataFrame when it is missing/empty."""
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(csv_path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _atomic_write_csv(dataframe: pd.DataFrame, csv_path: str) -> None:
    """Write a DataFrame atomically (temp file + os.replace + fsync)."""
    directory = os.path.dirname(os.path.abspath(csv_path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=".shiny_tracker_", suffix=".csv.tmp", dir=directory
    )
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            dataframe.to_csv(handle, index=False)
            handle.flush()
            os.fsync(handle.fileno())

        # mkstemp creates 0600 files; keep the original mode (or 0644 for new
        # files) so the CSV stays readable like a normal data file.
        if os.path.exists(csv_path):
            mode = os.stat(csv_path).st_mode & 0o777
        else:
            mode = 0o644
        try:
            os.chmod(temp_path, mode)
        except OSError:
            pass

        os.replace(temp_path, csv_path)
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def _backup_files(
    paths, reason: str, backup_root: str | None = None
) -> str | None:
    """Copy existing CSV files into a timestamped backup directory.

    By default the ``backups`` directory is created next to the first CSV, so
    tests and alternate data directories never write into the project root.
    """
    existing = [path for path in paths if os.path.exists(path)]
    if not existing:
        return None

    if backup_root is None:
        backup_root = os.path.join(
            os.path.dirname(os.path.abspath(existing[0])), BACKUP_ROOT
        )

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = os.path.join(backup_root, f"{reason}_{timestamp}")
    suffix = 1
    while os.path.exists(destination):
        destination = os.path.join(backup_root, f"{reason}_{timestamp}_{suffix}")
        suffix += 1
    os.makedirs(destination, exist_ok=True)
    for path in existing:
        shutil.copy2(path, os.path.join(destination, os.path.basename(path)))
    return destination


def _validate_hunts_df(dataframe: pd.DataFrame) -> None:
    """Raise :class:`ValidationError` when hunt rows break the schema."""
    missing = [column for column in HUNT_COLUMNS if column not in dataframe.columns]
    if missing:
        raise ValidationError(f"Missing hunt column(s): {', '.join(missing)}")

    ids = dataframe["hunt_id"].map(_clean_text)
    if ids.eq("").any():
        raise ValidationError("Every hunt needs a non-empty hunt_id.")
    if ids.duplicated().any():
        duplicates = sorted(set(ids[ids.duplicated()]))
        raise ValidationError(f"Duplicate hunt_id(s): {', '.join(duplicates)}")

    counts = pd.to_numeric(dataframe["encounter_count"], errors="coerce")
    if counts.isna().any() or (counts < 0).any():
        raise ValidationError("Encounter counts must be non-negative integers.")


def _validate_phases_df(dataframe: pd.DataFrame) -> None:
    """Raise :class:`ValidationError` when phase rows break the schema."""
    missing = [column for column in PHASE_COLUMNS if column not in dataframe.columns]
    if missing:
        raise ValidationError(f"Missing phase column(s): {', '.join(missing)}")

    if dataframe.empty:
        return

    if dataframe["phased_pokemon"].map(_clean_text).eq("").any():
        raise ValidationError("Every phase needs a non-empty phased_pokemon.")
    if dataframe["hunt_id"].map(_clean_text).eq("").any():
        raise ValidationError("Every phase needs a non-empty hunt_id.")

    counts = pd.to_numeric(dataframe["encounter_count"], errors="coerce")
    if counts.isna().any() or (counts < 0).any():
        raise ValidationError("Phase encounter counts must be non-negative integers.")

    phases = pd.to_numeric(dataframe["phase"], errors="coerce")
    if phases.isna().any() or (phases < 1).any():
        raise ValidationError("Phase numbers must be positive integers.")

    pairs = list(zip(dataframe["hunt_id"].map(_clean_text), phases.astype(int)))
    if len(pairs) != len(set(pairs)):
        raise DuplicatePhaseError("Duplicate phase number for the same hunt.")


# ---------------------------------------------------------------------------
# Normalisation / migration (pure functions)
# ---------------------------------------------------------------------------


def _normalise_hunts_df(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, bool, list[str]]:
    """Return a sanitised copy of a hunts DataFrame plus change information."""
    notes: list[str] = []
    changed = False
    original_columns = list(dataframe.columns)
    working = dataframe.copy()

    if working.columns.duplicated().any():
        working = working.loc[:, ~working.columns.duplicated()].copy()
        changed = True
        notes.append("Removed duplicate CSV columns.")

    for column, default in _HUNT_DEFAULTS.items():
        if column not in working.columns:
            working[column] = default
            changed = True
            notes.append(f"Added missing column '{column}'.")

    for column, default in _HUNT_DEFAULTS.items():
        if working[column].isna().any():
            working[column] = working[column].where(working[column].notna(), default)
            changed = True

    extra_columns = [c for c in working.columns if c not in HUNT_COLUMNS]
    rows: list[dict] = []
    seen_ids: set[str] = set()

    for _, source_row in working.iterrows():
        name = _clean_text(source_row["name"])
        raw_game = _clean_text(source_row["game"])
        canonical_game = canonicalize_game(raw_game)
        game = canonical_game or raw_game
        mechanics = get_mechanics(game)

        generation = (
            mechanics.generation
            if mechanics is not None
            else _coerce_int(source_row["generation"], 0)
        )
        method = _sanitize_method(game, _clean_text(source_row["encounter_method"]))
        shiny_charm = _coerce_bool(source_row["shiny_charm"])
        masuda_method = _coerce_bool(source_row["masuda_method"])

        if mechanics is not None:
            shiny_charm = bool(shiny_charm and shiny_charm_available(game, method))
            masuda_method = bool(masuda_method and masuda_available(game, method))
        else:
            masuda_method = False

        odds = (
            mechanics.base_odds
            if mechanics is not None
            else (_coerce_int(source_row["odds"], 0) or _fallback_odds(generation))
        )
        encounter_count = max(0, _coerce_int(source_row["encounter_count"], 0))
        is_done = _coerce_bool(source_row["is_done"])
        hunt_id = _clean_text(source_row["hunt_id"])

        if not hunt_id:
            hunt_id = str(uuid4())
            changed = True
            notes.append(f"Assigned a hunt_id to '{name or 'unnamed'}'.")
        if hunt_id in seen_ids:
            old_id = hunt_id
            hunt_id = str(uuid4())
            changed = True
            notes.append(
                f"Replaced duplicate hunt_id '{old_id}' for '{name or 'unnamed'}'."
            )
        seen_ids.add(hunt_id)

        row = {
            "name": name,
            "encounter_count": encounter_count,
            "generation": generation,
            "game": game,
            "is_done": is_done,
            "odds": odds,
            "shiny_charm": shiny_charm,
            "hunt_id": hunt_id,
            "encounter_method": method,
            "masuda_method": masuda_method,
        }
        for extra in extra_columns:
            row[extra] = source_row[extra]
        rows.append(row)

        for column in HUNT_COLUMNS:
            if column in original_columns and not _values_equal(
                source_row[column], row[column]
            ):
                changed = True
                break

    result = pd.DataFrame(rows, columns=HUNT_COLUMNS + extra_columns)
    if not result.empty:
        result["encounter_count"] = result["encounter_count"].astype(int)
        result["generation"] = result["generation"].astype(int)
        result["is_done"] = result["is_done"].astype(bool)
        result["odds"] = result["odds"].astype(int)
        result["shiny_charm"] = result["shiny_charm"].astype(bool)
        result["hunt_id"] = result["hunt_id"].astype(str)
        result["encounter_method"] = result["encounter_method"].astype(str)
        result["masuda_method"] = result["masuda_method"].astype(bool)

    return result.reset_index(drop=True), changed, notes


def _normalise_phases_df(
    dataframe: pd.DataFrame, hunts_df: pd.DataFrame
) -> tuple[pd.DataFrame, bool, list[str]]:
    """Return a sanitised phases DataFrame, mapping old columns when needed."""
    notes: list[str] = []
    changed = False
    original_columns = list(dataframe.columns)
    working = dataframe.copy()

    renames = {}
    if "target_pokemon" not in working.columns and "name" in working.columns:
        renames["name"] = "target_pokemon"
    if "phased_pokemon" not in working.columns and "pokemon_phased_on" in working.columns:
        renames["pokemon_phased_on"] = "phased_pokemon"
    if renames:
        working = working.rename(columns=renames)
        changed = True
        notes.append(
            "Migrated legacy phase columns: "
            + ", ".join(f"{old} -> {new}" for old, new in renames.items())
            + "."
        )

    # The legacy phase_count column is not part of the current schema.  Fold a
    # usable value into `phase` when the real phase number is missing, then
    # remove the column.  Known legacy names are also removed once their data
    # has been renamed.
    if "phase_count" in working.columns:
        if "phase" not in working.columns:
            working["phase"] = 0
        legacy_count = working["phase_count"].map(lambda value: _coerce_int(value, 0))
        current_phase = working["phase"].map(lambda value: _coerce_int(value, 0))
        use_legacy = (current_phase < 1) & (legacy_count > 0)
        if use_legacy.any():
            working.loc[use_legacy, "phase"] = legacy_count[use_legacy]
        working = working.drop(columns=["phase_count"])
        changed = True
        notes.append("Merged legacy 'phase_count' into 'phase' and removed it.")

    for legacy_name in ("name", "pokemon_phased_on"):
        if legacy_name in working.columns:
            working = working.drop(columns=[legacy_name])
            changed = True
            notes.append(f"Dropped legacy phase column '{legacy_name}'.")

    if working.columns.duplicated().any():
        working = working.loc[:, ~working.columns.duplicated()].copy()
        changed = True
        notes.append("Removed duplicate phase CSV columns.")

    for column, default in _PHASE_DEFAULTS.items():
        if column not in working.columns:
            working[column] = default
            changed = True
            notes.append(f"Added missing phase column '{column}'.")

    for column, default in _PHASE_DEFAULTS.items():
        if working[column].isna().any():
            working[column] = working[column].where(working[column].notna(), default)
            changed = True

    # Build lookup tables for legacy rows that only stored the target name.
    name_to_id: dict[str, str] = {}
    if not hunts_df.empty:
        for _, hunt in hunts_df.iterrows():
            key = _clean_text(hunt["name"]).lower()
            if key and key not in name_to_id:
                name_to_id[key] = _clean_text(hunt["hunt_id"])

    extra_columns = [c for c in working.columns if c not in PHASE_COLUMNS]
    rows: list[dict] = []
    used_phases: dict[str, set[int]] = {}

    for _, source_row in working.iterrows():
        target = _clean_text(source_row["target_pokemon"])
        phased = _clean_text(source_row["phased_pokemon"])
        hunt_id = _clean_text(source_row["hunt_id"])
        encounter_count = max(0, _coerce_int(source_row["encounter_count"], 0))

        if not any([target, phased, hunt_id]):
            # Completely blank legacy row: drop it.
            changed = True
            continue

        if not hunt_id and target:
            mapped = name_to_id.get(target.lower())
            if mapped:
                changed = True
                notes.append(
                    f"Mapped phase target '{target}' to hunt_id '{mapped}'."
                )
                hunt_id = mapped

        used = used_phases.setdefault(hunt_id, set())
        phase = _coerce_int(source_row["phase"], 0)
        if phase < 1 or phase in used:
            phase = max(used, default=0) + 1
            changed = True
            notes.append(
                f"Assigned phase {phase} to '{phased or target or 'phase'}' "
                f"for hunt '{hunt_id or 'unknown'}'."
            )
        used.add(phase)

        row = {
            "phase": phase,
            "target_pokemon": target,
            "encounter_count": encounter_count,
            "phased_pokemon": phased,
            "hunt_id": hunt_id,
        }
        for extra in extra_columns:
            row[extra] = source_row[extra]
        rows.append(row)

        for column in PHASE_COLUMNS:
            if column in original_columns and not _values_equal(
                source_row[column], row[column]
            ):
                changed = True
                break

    result = pd.DataFrame(rows, columns=PHASE_COLUMNS + extra_columns)
    if not result.empty:
        result["phase"] = result["phase"].astype(int)
        result["encounter_count"] = result["encounter_count"].astype(int)
        result["hunt_id"] = result["hunt_id"].astype(str)

    return result.reset_index(drop=True), changed, notes


# ---------------------------------------------------------------------------
# Loading and migration
# ---------------------------------------------------------------------------


def load_csv(csv_path: str = CSV_PATH) -> pd.DataFrame:
    """Raw CSV loader kept for backwards compatibility."""
    return _read_csv_safe(csv_path)


def load_hunts(csv_path: str = CSV_PATH) -> pd.DataFrame:
    """Load hunts with the current schema and sanitised values (no write)."""
    dataframe, _, _ = _normalise_hunts_df(_read_csv_safe(csv_path))
    return dataframe


def load_phases(
    csv_path: str = PHASED_CSV_PATH, hunts_df: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Load phases with the current schema and sanitised values (no write).

    When ``hunts_df`` is not supplied, the hunts file next to the phases file
    is used (so alternate data directories and tests stay isolated).
    """
    if hunts_df is None:
        hunts_path = os.path.join(
            os.path.dirname(os.path.abspath(csv_path)), os.path.basename(CSV_PATH)
        )
        hunts_df = load_hunts(hunts_path) if os.path.exists(hunts_path) else load_hunts()
    dataframe, _, _ = _normalise_phases_df(_read_csv_safe(csv_path), hunts_df)
    return dataframe


def migrate_csvs(
    hunts_path: str = CSV_PATH,
    phases_path: str = PHASED_CSV_PATH,
    *,
    backup: bool = True,
    write: bool = True,
) -> MigrationReport:
    """Migrate both CSVs to the current schema.

    The function is idempotent: running it on already-migrated files performs
    no write and creates no backup.  Existing IDs, counts, completion flags and
    valid charm settings are preserved; only impossible settings are cleared.
    """
    with _CSV_LOCK:
        hunts_raw = _read_csv_safe(hunts_path)
        phases_raw = _read_csv_safe(phases_path)
        hunts_df, hunts_changed, hunts_notes = _normalise_hunts_df(hunts_raw)
        phases_df, phases_changed, phases_notes = _normalise_phases_df(
            phases_raw, hunts_df
        )

        hunts_changed = hunts_changed or not os.path.exists(hunts_path)
        phases_changed = phases_changed or not os.path.exists(phases_path)

        backup_dir = None
        if write and (hunts_changed or phases_changed):
            if backup:
                backup_dir = _backup_files([hunts_path, phases_path], "migration")
            if hunts_changed:
                _atomic_write_csv(hunts_df, hunts_path)
            if phases_changed:
                _atomic_write_csv(phases_df, phases_path)

        unsupported = tuple(
            sorted(
                {
                    _clean_text(row["game"])
                    for _, row in hunts_df.iterrows()
                    if get_mechanics(_clean_text(row["game"])) is None
                }
            )
        )

        return MigrationReport(
            hunts_changed=hunts_changed,
            phases_changed=phases_changed,
            backup_dir=backup_dir,
            notes=tuple(hunts_notes + phases_notes),
            unsupported_hunts=unsupported,
            hunts_rows=len(hunts_df),
            phase_rows=len(phases_df),
        )


def create_csv(csv_path: str = CSV_PATH) -> pd.DataFrame:
    """Create the hunts CSV if needed and return the normalised DataFrame."""
    with _CSV_LOCK:
        exists = os.path.exists(csv_path)
        dataframe, changed, _ = _normalise_hunts_df(_read_csv_safe(csv_path))
        if changed or not exists:
            if exists:
                _backup_files([csv_path], "migration")
            _atomic_write_csv(dataframe, csv_path)
        return dataframe


def create_phase_csv(
    csv_path: str = PHASED_CSV_PATH, hunts_path: str = CSV_PATH
) -> pd.DataFrame:
    """Create the phases CSV if needed and return the normalised DataFrame."""
    with _CSV_LOCK:
        exists = os.path.exists(csv_path)
        hunts_df = load_hunts(hunts_path)
        dataframe, changed, _ = _normalise_phases_df(
            _read_csv_safe(csv_path), hunts_df
        )
        if changed or not exists:
            if exists:
                _backup_files([csv_path], "migration")
            _atomic_write_csv(dataframe, csv_path)
        return dataframe


# ---------------------------------------------------------------------------
# Hunt creation / persistence
# ---------------------------------------------------------------------------


def new_hunt(
    name: str,
    game: str,
    encounter_method: str = WILD,
    shiny_charm: bool = False,
    masuda_method: bool = False,
    csv_path: str = CSV_PATH,
) -> Pokemon:
    """Validate and persist a brand-new hunt, returning it."""
    name = _clean_text(name)
    if not name:
        raise ValidationError("Pokémon name cannot be empty.")

    mechanics = get_mechanics(game)
    if mechanics is None:
        raise ValidationError(
            f"'{game}' is not a supported game. Choose one of the supported games."
        )

    method = _clean_text(encounter_method).lower() or WILD
    if method not in mechanics.supported_methods:
        supported = ", ".join(mechanics.supported_methods)
        raise ValidationError(
            f"{mechanics.name} does not support the '{method}' encounter method. "
            f"Supported methods: {supported}."
        )

    # Bonus flags are sanitised rather than rejected: a disabled checkbox can
    # still carry a stale value in Streamlit, and stored legacy rows may contain
    # combinations that never applied.  The hunt itself is still created.
    pokemon = Pokemon(
        name=name,
        encounter_count=0,
        generation=mechanics.generation,
        game=mechanics.name,
        is_done=False,
        shiny_charm=bool(
            shiny_charm and shiny_charm_available(mechanics.name, method)
        ),
        encounter_method=method,
        masuda_method=bool(
            masuda_method and masuda_available(mechanics.name, method)
        ),
    )

    with _CSV_LOCK:
        dataframe = load_hunts(csv_path)
        save_hunt_to_csv(pokemon, dataframe, csv_path)
    return pokemon


def save_hunt_to_csv(
    pokemon: Pokemon, dataframe: pd.DataFrame, csv_path: str = CSV_PATH
) -> pd.DataFrame:
    """Append a hunt to the CSV atomically, preventing duplicate IDs."""
    with _CSV_LOCK:
        dataframe, _, _ = _normalise_hunts_df(dataframe)
        if not dataframe.empty and pokemon.hunt_id in set(
            dataframe["hunt_id"].astype(str)
        ):
            raise DuplicateHuntError(f"Hunt '{pokemon.hunt_id}' already exists.")

        new_row = pd.DataFrame([pokemon.to_row()], columns=HUNT_COLUMNS)
        extra_columns = [c for c in dataframe.columns if c not in HUNT_COLUMNS]
        result = pd.concat([dataframe, new_row], ignore_index=True)
        result = result.reindex(columns=HUNT_COLUMNS + extra_columns)
        _validate_hunts_df(result)
        _atomic_write_csv(result, csv_path)
        return result


def update_hunt_in_csv(
    pokemon: Pokemon, dataframe: pd.DataFrame, csv_path: str = CSV_PATH
) -> pd.DataFrame:
    """Replace one hunt row (matched by hunt_id) atomically."""
    with _CSV_LOCK:
        dataframe, _, _ = _normalise_hunts_df(dataframe)
        mask = dataframe["hunt_id"].astype(str) == str(pokemon.hunt_id)
        matches = int(mask.sum())
        if matches == 0:
            raise ValidationError("Hunt not found.")
        if matches > 1:
            raise ValidationError("Multiple hunts share this hunt_id; refusing to update.")

        for column, value in pokemon.to_row().items():
            dataframe.loc[mask, column] = value
        _validate_hunts_df(dataframe)
        _atomic_write_csv(dataframe, csv_path)
        return dataframe


def remove_hunt_from_csv(
    pokemon: Pokemon,
    dataframe: pd.DataFrame,
    csv_path: str = CSV_PATH,
    phases_path: str | None = None,
) -> pd.DataFrame:
    """Remove a hunt (and optionally its phases) atomically.

    When ``phases_path`` is given, the phase file is also cleaned up in the
    same transaction.  If the second write fails, the first is rolled back.
    """
    with _CSV_LOCK:
        dataframe, _, _ = _normalise_hunts_df(dataframe)
        mask = dataframe["hunt_id"].astype(str) == str(pokemon.hunt_id)
        if int(mask.sum()) == 0:
            raise ValidationError("Hunt not found.")
        if int(mask.sum()) > 1:
            raise ValidationError("Multiple hunts share this hunt_id; refusing to delete.")

        new_hunts = dataframe.loc[~mask].reset_index(drop=True)

        if phases_path is None:
            _backup_files([csv_path], "delete")
            _atomic_write_csv(new_hunts, csv_path)
            return new_hunts

        phases_df = load_phases(phases_path, dataframe)
        new_phases = phases_df.loc[
            phases_df["hunt_id"].astype(str) != str(pokemon.hunt_id)
        ].reset_index(drop=True)

        _backup_files([csv_path, phases_path], "delete")
        phases_written = False
        try:
            _atomic_write_csv(new_phases, phases_path)
            phases_written = True
            _atomic_write_csv(new_hunts, csv_path)
        except Exception as exc:  # noqa: BLE001 - re-raised as a domain error
            if phases_written:
                try:
                    _atomic_write_csv(phases_df, phases_path)
                except Exception as restore_exc:  # pragma: no cover - catastrophic
                    raise TransactionError(
                        "Deleting the hunt failed and the phase file could not be "
                        "restored. A backup was created before the attempt."
                    ) from restore_exc
            raise TransactionError(
                "Deleting the hunt failed; the phase file was restored."
            ) from exc
        return new_hunts


def delete_hunt(
    pokemon: Pokemon,
    dataframe: pd.DataFrame | None = None,
    csv_path: str = CSV_PATH,
    phases_path: str = PHASED_CSV_PATH,
) -> pd.DataFrame:
    """Convenience wrapper that deletes a hunt and all of its phases."""
    if dataframe is None:
        dataframe = load_hunts(csv_path)
    return remove_hunt_from_csv(pokemon, dataframe, csv_path, phases_path)


# ---------------------------------------------------------------------------
# Phasing
# ---------------------------------------------------------------------------


def next_phase_number(phases_df: pd.DataFrame, hunt_id: str) -> int:
    """Return the next phase number for a hunt (1 for the first phase)."""
    if phases_df.empty:
        return 1
    matches = phases_df.loc[
        phases_df["hunt_id"].astype(str) == str(hunt_id), "phase"
    ]
    if matches.empty:
        return 1
    return int(pd.to_numeric(matches, errors="coerce").max()) + 1


def validate_phase_input(phased_pokemon: str, encounter_count) -> tuple[str, int]:
    """Validate phase dialog input without touching the filesystem."""
    name = _clean_text(phased_pokemon)
    if not name:
        raise ValidationError("Enter the Pokémon that phased the hunt.")
    count = _coerce_int(encounter_count, -1)
    if count < 0:
        raise ValidationError("Encounter count must be a non-negative integer.")
    return name, count


def record_phase(
    hunt_id: str,
    phased_pokemon: str,
    encounter_count,
    *,
    hunts_path: str = CSV_PATH,
    phases_path: str = PHASED_CSV_PATH,
    expected_encounter_count: int | None = None,
    expected_next_phase: int | None = None,
    backup: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, Phased]:
    """Record a phase and reset the original hunt's counter to zero.

    The hunt keeps its ``hunt_id``, target name, game, generation, method,
    bonuses and ``is_done`` flag.  No new hunt is created.

    ``expected_encounter_count`` and ``expected_next_phase`` provide optimistic
    concurrency/duplicate protection: if the CSV changed since the dialog was
    opened, :class:`ConcurrentUpdateError` is raised and nothing is written.

    The phase file is written first; if the hunts file write fails, the phase
    file is restored from its in-memory original, so the two files stay in sync.
    """
    name, count = validate_phase_input(phased_pokemon, encounter_count)
    hunt_key = _clean_text(hunt_id)
    if not hunt_key:
        raise ValidationError("A hunt_id is required to record a phase.")

    with _CSV_LOCK:
        hunts_df = load_hunts(hunts_path)
        phases_df = load_phases(phases_path, hunts_df)

        mask = hunts_df["hunt_id"].astype(str) == hunt_key
        if int(mask.sum()) == 0:
            raise ValidationError("Hunt not found.")
        if int(mask.sum()) > 1:
            raise ValidationError("Multiple hunts share this hunt_id; refusing to phase.")

        current_count = int(hunts_df.loc[mask, "encounter_count"].iloc[0])
        if (
            expected_encounter_count is not None
            and int(expected_encounter_count) != current_count
        ):
            raise ConcurrentUpdateError(
                "The encounter count changed since this dialog was opened. "
                "Close the dialog and try again."
            )

        phase_number = next_phase_number(phases_df, hunt_key)
        if expected_next_phase is not None and int(expected_next_phase) != phase_number:
            raise ConcurrentUpdateError(
                "Another phase was recorded since this dialog was opened. "
                "Close the dialog and try again."
            )

        target = _clean_text(hunts_df.loc[mask, "name"].iloc[0])
        record = Phased(
            target_pokemon=target,
            encounter_count=count,
            phased_pokemon=name,
            hunt_id=hunt_key,
            phase=phase_number,
        )

        new_phases = pd.concat(
            [
                phases_df.reindex(columns=PHASE_COLUMNS),
                pd.DataFrame([record.to_row()], columns=PHASE_COLUMNS),
            ],
            ignore_index=True,
        )
        _validate_phases_df(new_phases)

        new_hunts = hunts_df.copy()
        new_hunts.loc[mask, "encounter_count"] = 0
        _validate_hunts_df(new_hunts)

        if backup:
            _backup_files([hunts_path, phases_path], "phase")

        phases_written = False
        try:
            _atomic_write_csv(new_phases, phases_path)
            phases_written = True
            _atomic_write_csv(new_hunts, hunts_path)
        except Exception as exc:  # noqa: BLE001 - re-raised as a domain error
            if phases_written:
                try:
                    _atomic_write_csv(phases_df, phases_path)
                except Exception as restore_exc:  # pragma: no cover - catastrophic
                    raise TransactionError(
                        "Recording the phase failed and the phase file could not "
                        "be restored. A backup was created before the attempt."
                    ) from restore_exc
            raise TransactionError(
                "Recording the phase failed. The counter was not reset and the "
                "phase list was restored."
            ) from exc

        return new_hunts, new_phases, record


def phases_for_hunt(phases_df: pd.DataFrame, hunt_id: str) -> pd.DataFrame:
    """Return one hunt's phases in numeric order."""
    if phases_df.empty:
        return phases_df.reindex(columns=PHASE_COLUMNS).reset_index(drop=True)
    matches = phases_df.loc[
        phases_df["hunt_id"].astype(str) == str(hunt_id)
    ].copy()
    if matches.empty:
        return matches.reindex(columns=PHASE_COLUMNS).reset_index(drop=True)
    matches["phase"] = pd.to_numeric(matches["phase"], errors="coerce").astype(int)
    return matches.sort_values("phase").reset_index(drop=True)


def group_phases_by_hunt(phases_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Group phases by ``hunt_id``, preserving phase order."""
    if phases_df.empty:
        return {}
    result: dict[str, pd.DataFrame] = {}
    for hunt_id, group in phases_df.groupby("hunt_id", sort=False):
        ordered = group.copy()
        ordered["phase"] = pd.to_numeric(ordered["phase"], errors="coerce").astype(int)
        result[str(hunt_id)] = ordered.sort_values("phase").reset_index(drop=True)
    return result


def phase_summary(phases_df: pd.DataFrame) -> pd.DataFrame:
    """One summary row per hunt that has recorded phases."""
    columns = [
        "hunt_id",
        "target_pokemon",
        "phase_count",
        "total_encounters",
        "last_phase",
        "last_phased_pokemon",
    ]
    if phases_df.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for hunt_id, group in group_phases_by_hunt(phases_df).items():
        last = group.iloc[-1]
        rows.append(
            {
                "hunt_id": hunt_id,
                "target_pokemon": _clean_text(last["target_pokemon"]),
                "phase_count": int(len(group)),
                "total_encounters": int(
                    pd.to_numeric(group["encounter_count"], errors="coerce")
                    .fillna(0)
                    .sum()
                ),
                "last_phase": int(last["phase"]),
                "last_phased_pokemon": _clean_text(last["phased_pokemon"]),
            }
        )
    result = pd.DataFrame(rows, columns=columns)
    return result.sort_values("target_pokemon", key=lambda s: s.str.lower()).reset_index(
        drop=True
    )


# ---------------------------------------------------------------------------
# Encounter helpers
# ---------------------------------------------------------------------------


def add_encounter(pokemon: Pokemon) -> Pokemon:
    """Return a copy of the hunt with one more encounter."""
    return replace(pokemon, encounter_count=pokemon.encounter_count + 1)


def remove_encounter(pokemon: Pokemon) -> Pokemon:
    """Return a copy of the hunt with one fewer encounter (never below zero)."""
    return replace(pokemon, encounter_count=max(0, pokemon.encounter_count - 1))


def custom_add_encounter(pokemon: Pokemon, increase_count: int) -> Pokemon:
    """Return a copy of the hunt with ``increase_count`` extra encounters."""
    increase_count = _coerce_int(increase_count, 0)
    if increase_count <= 0:
        raise ValidationError("Increase must be positive.")
    return replace(pokemon, encounter_count=pokemon.encounter_count + increase_count)


def custom_remove_encounter(pokemon: Pokemon, decrease_count: int) -> Pokemon:
    """Return a copy of the hunt with ``decrease_count`` encounters removed."""
    decrease_count = _coerce_int(decrease_count, 0)
    if decrease_count <= 0:
        raise ValidationError("Value entered must be positive.")
    return replace(
        pokemon, encounter_count=max(0, pokemon.encounter_count - decrease_count)
    )


def toggle_shiny_charm(pokemon: Pokemon) -> Pokemon:
    """Return a copy of the hunt with the Shiny Charm flag flipped."""
    return replace(pokemon, shiny_charm=not pokemon.shiny_charm)


def mark_hunt_complete(pokemon: Pokemon) -> Pokemon:
    """Return a copy of the hunt marked as complete."""
    return replace(pokemon, is_done=True)


# ---------------------------------------------------------------------------
# Odds helpers
# ---------------------------------------------------------------------------


def hunt_odds(pokemon: Pokemon) -> OddsResult:
    """Authoritative odds result for a hunt."""
    return calculate_shiny_odds(
        pokemon.game,
        pokemon.encounter_method,
        pokemon.shiny_charm,
        pokemon.masuda_method,
    )


def calulate_probability(pokemon: Pokemon) -> float:
    """Cumulative shiny probability (percentage) for the hunt.

    The misspelling is kept for backwards compatibility with the original UI.
    """
    result = hunt_odds(pokemon)
    if not result.supported or result.probability is None:
        return 0.0
    return cumulative_percent(result.probability, pokemon.encounter_count)


def calculate_probability(pokemon: Pokemon) -> float:
    """Correctly spelled alias for :func:`calulate_probability`."""
    return calulate_probability(pokemon)


def hunt_probability_percent(pokemon: Pokemon) -> float:
    """Cumulative shiny probability (percentage) for the hunt."""
    return calulate_probability(pokemon)


# ---------------------------------------------------------------------------
# Backwards-compatible conversion / terminal helpers
# ---------------------------------------------------------------------------


def from_csv_to_Pokemon(dataframe: pd.DataFrame) -> list[Pokemon]:
    """Map CSV rows to sanitised Pokemon objects."""
    return [Pokemon.from_row(row) for _, row in dataframe.iterrows()]


def list_phases(dataframe: pd.DataFrame) -> None:
    """Print recorded phases in a readable terminal format."""
    if dataframe.empty:
        print("No phases recorded yet.")
        return
    for _, row in dataframe.iterrows():
        print(
            f"Phase {row['phase']}: "
            f"Target: {row['target_pokemon']} | "
            f"Found: {row['phased_pokemon']} | "
            f"Encounters: {row['encounter_count']}"
        )


def list_hunts(dataframe: pd.DataFrame, select_mode: bool = False) -> None:
    """Print hunts in a readable terminal format, optionally numbered."""
    if dataframe.empty:
        print("No hunts found. Start a new hunt.")
        return
    for index, (_, row) in enumerate(dataframe.iterrows()):
        prefix = f"{index} " if select_mode else ""
        print(prefix, row["name"], row["game"], row["generation"])


def select_hunt(dataframe: pd.DataFrame) -> Pokemon | None:
    """Prompt the user to choose a hunt, returning ``None`` when cancelled."""
    if dataframe.empty:
        print("No hunts found. Start a new hunt.")
        return None

    list_hunts(dataframe, select_mode=True)
    while True:
        selection = input("Enter number of hunt (Q to cancel): ").strip()
        if selection.lower() == "q":
            return None
        if not selection.isdigit():
            print("Enter a valid number.")
            continue
        index = int(selection)
        if index < 0 or index >= len(dataframe):
            print("Selection out of range.")
            continue
        return Pokemon.from_row(dataframe.iloc[index])


if __name__ == "__main__":  # pragma: no cover - legacy terminal interface
    df = create_csv(CSV_PATH)
    create_phase_csv(PHASED_CSV_PATH)

    running = True
    while running:
        print("A - Add New Hunt\nL - List Hunts\nR - Remove Hunt\nS - Select Hunt\nQ - Quit")
        selection = input("Enter your selection: ").lower()

        if selection == "q":
            running = False
        elif selection == "a":
            name = input("Enter Pokémon's name: ")
            print("Supported games:", ", ".join(SUPPORTED_GAMES))
            game = input("Enter game: ")
            try:
                pokemon = new_hunt(name=name, game=game)
                print(f"Added {pokemon.name} ({pokemon.game}).")
            except TrackerError as error:
                print(f"Error: {error}")
        elif selection == "l":
            list_hunts(load_hunts())
        elif selection == "r":
            pokemon = select_hunt(load_hunts())
            if pokemon is not None:
                delete_hunt(pokemon)
                print("Hunt removed.")
        elif selection == "s":
            pokemon = select_hunt(load_hunts())
            if pokemon is None:
                continue
            hunting = True
            while hunting:
                result = hunt_odds(pokemon)
                print(f"\n{pokemon.name} ({pokemon.game})")
                print(f"Encounters: {pokemon.encounter_count}")
                print(f"Odds: {result.display}")
                print(f"Probability: {calulate_probability(pokemon):.4f}%")
                action = input(
                    "A - Add encounter, S - Subtract encounter, "
                    "C - Custom add, D - Custom remove, F - Done, Q - Back\n"
                ).lower()
                if action == "q":
                    hunting = False
                elif action == "f":
                    pokemon = mark_hunt_complete(pokemon)
                    update_hunt_in_csv(pokemon, load_hunts())
                    hunting = False
                elif action in {"a", "s"}:
                    pokemon = (
                        add_encounter(pokemon)
                        if action == "a"
                        else remove_encounter(pokemon)
                    )
                    update_hunt_in_csv(pokemon, load_hunts())
                elif action in {"c", "d"}:
                    raw = input("Amount: ")
                    if not raw.isdigit() or int(raw) <= 0:
                        print("Enter a positive number.")
                        continue
                    pokemon = (
                        custom_add_encounter(pokemon, int(raw))
                        if action == "c"
                        else custom_remove_encounter(pokemon, int(raw))
                    )
                    update_hunt_in_csv(pokemon, load_hunts())
