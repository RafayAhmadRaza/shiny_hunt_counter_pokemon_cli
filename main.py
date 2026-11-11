"""Streamlit UI for the Pokémon Shiny Hunt Tracker."""

from __future__ import annotations

import streamlit as st

from functions import (
    CSV_PATH,
    PHASED_CSV_PATH,
    ConcurrentUpdateError,
    Pokemon,
    TrackerError,
    ValidationError,
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
    record_phase,
    update_hunt_in_csv,
)
from shiny_mechanics import (
    BREEDING,
    SUPPORTED_GAMES,
    counter_label,
    cumulative_percent,
    encounter_method_label,
    get_mechanics,
    masuda_available,
    masuda_unavailable_reason,
    shiny_charm_available,
    shiny_charm_unavailable_reason,
)

st.set_page_config(
    page_title="Shiny Hunt Tracker",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Small UI helpers
# ---------------------------------------------------------------------------


def set_flash(message: str, kind: str = "success") -> None:
    st.session_state["_flash"] = (kind, message)


def show_flash() -> None:
    flash = st.session_state.pop("_flash", None)
    if flash is None:
        return
    kind, message = flash
    if kind == "error":
        st.error(message)
    elif kind == "warning":
        st.warning(message)
    else:
        st.success(message)


def save_and_rerun(pokemon: Pokemon) -> None:
    try:
        update_hunt_in_csv(pokemon, load_hunts(CSV_PATH), CSV_PATH)
    except TrackerError as error:
        st.error(str(error))
        return
    st.rerun()


def adjust_counter(pokemon: Pokemon, amount: int) -> None:
    try:
        updated = custom_add_encounter(pokemon, amount)
    except TrackerError as error:
        st.error(str(error))
        return
    save_and_rerun(updated)


def decrease_counter(pokemon: Pokemon, amount: int) -> None:
    try:
        updated = custom_remove_encounter(pokemon, amount)
    except TrackerError as error:
        st.error(str(error))
        return
    save_and_rerun(updated)


def attempt_count_text(count: int, method: str) -> str:
    """Describe a counter using the method's unit (encounters or eggs)."""
    return f"{count:,} {counter_label(method).lower()}"


def hunt_header(pokemon: Pokemon) -> None:
    mechanics = get_mechanics(pokemon.game)
    details = [
        pokemon.game,
        f"Gen {pokemon.generation}",
        encounter_method_label(pokemon.encounter_method),
    ]
    if pokemon.shiny_charm:
        details.append("Shiny Charm")
    if pokemon.masuda_method:
        details.append("Masuda Method")
    st.markdown(f"**{pokemon.name}**")
    st.caption(" | ".join(details))
    if mechanics is None:
        st.warning(
            f"'{pokemon.game}' is not a supported game, so shiny odds are "
            "unavailable. The hunt is preserved exactly as stored."
        )


def render_odds(pokemon: Pokemon) -> None:
    result = hunt_odds(pokemon)
    if not result.supported:
        st.warning(result.reason or "Odds are unavailable for this hunt.")
        return

    total_chance = cumulative_percent(result.probability, pokemon.encounter_count)
    per_attempt_label = (
        "Odds per egg" if pokemon.encounter_method == BREEDING else "Odds per encounter"
    )
    c1, c2, c3 = st.columns(3)
    c1.metric(per_attempt_label, result.display)
    c2.metric("Shiny rolls", result.total_rolls)
    c3.metric("Chance so far", f"{total_chance:.2f}%")

    st.progress(
        min(max(total_chance / 100.0, 0.0), 1.0),
        text=(
            f"{total_chance:.2f}% chance of at least one shiny after "
            f"{attempt_count_text(pokemon.encounter_count, pokemon.encounter_method)}"
        ),
    )
    st.caption(f"Base rate: 1 in {result.base_odds:,} per roll.")

    if result.warnings:
        st.caption(" ".join(result.warnings))


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------


@st.dialog("Record a phase")
def phase_dialog(pokemon: Pokemon, expected_next_phase: int) -> None:
    st.write(
        f"Record a shiny that appeared before **{pokemon.name}**. "
        "The hunt keeps all of its settings; only the counter is reset to zero."
    )
    st.caption(
        f"Target: {pokemon.name} | {pokemon.game} | "
        f"{encounter_method_label(pokemon.encounter_method)} | "
        f"current counter {pokemon.encounter_count:,}"
    )

    with st.form("phase_form"):
        encountered = st.text_input(
            "Pokémon that appeared",
            placeholder="e.g. Boldore",
        )
        encounters = st.number_input(
            f"{counter_label(pokemon.encounter_method)} in this phase",
            min_value=0,
            max_value=10_000_000,
            value=max(0, int(pokemon.encounter_count)),
            step=1,
        )
        save_col, cancel_col = st.columns(2)
        save = save_col.form_submit_button("Record phase", type="primary")
        cancel = cancel_col.form_submit_button("Cancel")

    if cancel:
        st.rerun()

    if save:
        try:
            record_phase(
                pokemon.hunt_id,
                encountered,
                int(encounters),
                expected_encounter_count=pokemon.encounter_count,
                expected_next_phase=expected_next_phase,
            )
        except ConcurrentUpdateError as error:
            st.error(str(error))
        except (ValidationError, TrackerError) as error:
            st.error(str(error))
        else:
            set_flash(
                f"Phase {expected_next_phase} recorded for {pokemon.name}. "
                "The counter was reset to 0."
            )
            st.rerun()


@st.dialog("Delete hunt?")
def delete_dialog(pokemon: Pokemon) -> None:
    st.warning(
        f"Delete **{pokemon.name}** ({pokemon.game}) and all of its recorded "
        "phases? This action cannot be undone from the app."
    )
    st.caption("A timestamped backup is created before anything is written.")
    delete_col, cancel_col = st.columns(2)
    if delete_col.button("Delete hunt", type="primary", key="confirm_delete"):
        try:
            delete_hunt(pokemon)
        except TrackerError as error:
            st.error(str(error))
        else:
            set_flash(f"Deleted {pokemon.name}.", "warning")
            st.rerun()
    if cancel_col.button("Cancel", key="cancel_delete"):
        st.rerun()


# ---------------------------------------------------------------------------
# Load and migrate data
# ---------------------------------------------------------------------------

try:
    report = migrate_csvs(CSV_PATH, PHASED_CSV_PATH)
except Exception as error:  # noqa: BLE001 - show a friendly fatal error
    st.error(f"Could not load the tracker data: {error}")
    st.stop()

if report.changed and (report.notes or report.backup_dir):
    st.session_state["_migration_notes"] = list(report.notes)
    st.session_state["_migration_backup"] = report.backup_dir

df = load_hunts(CSV_PATH)
phases_df = load_phases(PHASED_CSV_PATH, hunts_df=df)
pokemon_list = from_csv_to_Pokemon(df)
phases_by_hunt = group_phases_by_hunt(phases_df)
phase_rows = phase_summary(phases_df)
hunts_by_id = {p.hunt_id: p for p in pokemon_list}

active_hunts = [p for p in pokemon_list if not p.is_done]
completed_hunts = [p for p in pokemon_list if p.is_done]

st.title("Shiny Hunt Tracker")
st.caption(
    "Track encounters, eggs, phases and game-specific shiny odds. "
    "All data stays in local CSV files."
)

show_flash()

if report.unsupported_hunts:
    st.warning(
        "These hunts use games the odds registry does not support: "
        + ", ".join(report.unsupported_hunts)
        + ". Their data is preserved, but odds are shown as unavailable."
    )

migration_notes = st.session_state.get("_migration_notes")
if migration_notes:
    backup_dir = st.session_state.get("_migration_backup")
    with st.expander("Data migration applied", expanded=False):
        for note in migration_notes:
            st.write(f"- {note}")
        if backup_dir:
            st.caption(f"Backup created in `{backup_dir}`.")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

total_attempts = sum(p.encounter_count for p in pokemon_list)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Active hunts", len(active_hunts))
m2.metric("Total attempts", f"{total_attempts:,}")
m3.metric("Phases recorded", len(phases_df))
m4.metric("Completed hunts", len(completed_hunts))


# ---------------------------------------------------------------------------
# Add a hunt
# ---------------------------------------------------------------------------

with st.expander("Add a new hunt", expanded=False):
    game = st.selectbox(
        "Game",
        SUPPORTED_GAMES,
        key="new_game",
        help="Only games with researched shiny mechanics are listed.",
    )
    mechanics = get_mechanics(game)
    method_key = f"new_method_{game}"
    if method_key not in st.session_state:
        # Carry the last selected method across game switches when the new game
        # supports it, so switching games does not silently reset the form.
        remembered = st.session_state.get("_last_method")
        st.session_state[method_key] = (
            remembered
            if remembered in mechanics.supported_methods
            else mechanics.supported_methods[0]
        )
    method = st.selectbox(
        "Encounter method",
        mechanics.supported_methods,
        format_func=encounter_method_label,
        key=method_key,
        help="Only methods with a verified shiny mechanic for this game are shown.",
    )
    st.session_state["_last_method"] = method
    if not mechanics.can_breed:
        st.caption(f"{game} has no breeding. Only wild encounters are available.")
    charm_ok = shiny_charm_available(game, method)
    masuda_ok = masuda_available(game, method)
    charm_reason = shiny_charm_unavailable_reason(game, method)
    masuda_reason = masuda_unavailable_reason(game, method)

    with st.form("new_hunt_form", clear_on_submit=True):
        name = st.text_input(
            "Pokémon name",
            placeholder="e.g. Axew",
            key="new_name",
        )
        charm = st.checkbox(
            "Shiny Charm",
            value=False,
            disabled=not charm_ok,
            key="new_charm",
            help=(
                "The Shiny Charm affects this game and method."
                if charm_ok
                else charm_reason
            ),
        )
        masuda = st.checkbox(
            "Masuda Method",
            value=False,
            disabled=not masuda_ok,
            key="new_masuda",
            help=(
                "The Masuda Method can be enabled for breeding in this game."
                if masuda_ok
                else masuda_reason
            ),
        )
        if not masuda_ok and masuda_reason:
            st.caption(masuda_reason)
        elif masuda_ok:
            st.caption("Masuda Method is available for breeding in this game.")
        if not charm_ok and charm_reason:
            st.caption(charm_reason)
        st.caption(
            f"Generation {mechanics.generation} | base odds 1 in "
            f"{mechanics.base_odds:,} per roll"
        )
        submitted = st.form_submit_button("Add hunt", type="primary")

    if submitted:
        try:
            new_hunt(
                name=name,
                game=game,
                encounter_method=method,
                shiny_charm=charm,
                masuda_method=masuda,
            )
        except TrackerError as error:
            st.error(str(error))
        else:
            set_flash(f"Added {name.strip()} ({game}).")
            st.rerun()


# ---------------------------------------------------------------------------
# Active hunts
# ---------------------------------------------------------------------------

st.subheader("Active hunts")

if not active_hunts:
    st.caption("No active hunts. Add one above to start counting.")

for pokemon in active_hunts:
    header_col, counter_col = st.columns([4, 1], vertical_alignment="center")
    with header_col:
        hunt_header(pokemon)
    with counter_col:
        st.metric(
            counter_label(pokemon.encounter_method),
            f"{pokemon.encounter_count:,}",
        )

    render_odds(pokemon)

    amount_col, minus_col, plus_col = st.columns([2, 1, 1])
    amount = amount_col.number_input(
        "Custom amount",
        min_value=1,
        max_value=1_000_000,
        value=1,
        step=1,
        key=f"amount_{pokemon.hunt_id}",
    )
    if minus_col.button(
        "Remove", key=f"minus_{pokemon.hunt_id}", use_container_width=True
    ):
        decrease_counter(pokemon, int(amount))
    if plus_col.button(
        "Add", key=f"plus_{pokemon.hunt_id}", use_container_width=True
    ):
        adjust_counter(pokemon, int(amount))

    action_col, phase_col, delete_col = st.columns([2, 1, 1])

    charm_available = shiny_charm_available(pokemon.game, pokemon.encounter_method)
    with action_col:
        charm = st.checkbox(
            "Shiny Charm",
            value=bool(pokemon.shiny_charm and charm_available),
            disabled=not charm_available,
            key=f"charm_{pokemon.hunt_id}",
            help=(
                "Shiny Charm applies to this hunt."
                if charm_available
                else shiny_charm_unavailable_reason(
                    pokemon.game, pokemon.encounter_method
                )
            ),
        )
        if charm != pokemon.shiny_charm:
            pokemon.shiny_charm = charm
            save_and_rerun(pokemon)

    with phase_col:
        next_phase = next_phase_number(phases_df, pokemon.hunt_id)
        if st.button(
            "Record phase",
            key=f"phase_{pokemon.hunt_id}",
            use_container_width=True,
        ):
            phase_dialog(pokemon, next_phase)

    with delete_col:
        if st.button(
            "Delete",
            key=f"delete_{pokemon.hunt_id}",
            use_container_width=True,
        ):
            delete_dialog(pokemon)

    with st.expander("Hunt settings", expanded=False):
        hunt_mechanics = get_mechanics(pokemon.game)
        settings_method = st.selectbox(
            "Encounter method",
            (
                hunt_mechanics.supported_methods
                if hunt_mechanics
                else [pokemon.encounter_method]
            ),
            index=(
                hunt_mechanics.supported_methods.index(pokemon.encounter_method)
                if hunt_mechanics
                and pokemon.encounter_method in hunt_mechanics.supported_methods
                else 0
            ),
            format_func=encounter_method_label,
            key=f"settings_method_{pokemon.hunt_id}",
        )
        settings_charm_ok = shiny_charm_available(pokemon.game, settings_method)
        settings_masuda_ok = masuda_available(pokemon.game, settings_method)
        settings_charm_reason = shiny_charm_unavailable_reason(
            pokemon.game, settings_method
        )
        settings_masuda_reason = masuda_unavailable_reason(
            pokemon.game, settings_method
        )
        with st.form(key=f"settings_form_{pokemon.hunt_id}"):
            settings_charm = st.checkbox(
                "Shiny Charm",
                value=bool(pokemon.shiny_charm and settings_charm_ok),
                disabled=not settings_charm_ok,
                key=f"settings_charm_{pokemon.hunt_id}",
                help=(
                    "Shiny Charm applies to this method."
                    if settings_charm_ok
                    else settings_charm_reason
                ),
            )
            settings_masuda = st.checkbox(
                "Masuda Method",
                value=bool(pokemon.masuda_method and settings_masuda_ok),
                disabled=not settings_masuda_ok,
                key=f"settings_masuda_{pokemon.hunt_id}",
                help=(
                    "Masuda Method applies to breeding in this game."
                    if settings_masuda_ok
                    else settings_masuda_reason
                ),
            )
            if not settings_masuda_ok and settings_masuda_reason:
                st.caption(settings_masuda_reason)
            if not settings_charm_ok and settings_charm_reason:
                st.caption(settings_charm_reason)
            apply_settings = st.form_submit_button("Apply settings")

        if apply_settings:
            updated = Pokemon(
                name=pokemon.name,
                encounter_count=pokemon.encounter_count,
                generation=pokemon.generation,
                game=pokemon.game,
                is_done=pokemon.is_done,
                hunt_id=pokemon.hunt_id,
                shiny_charm=settings_charm,
                encounter_method=settings_method,
                masuda_method=settings_masuda,
            )
            save_and_rerun(updated)

    done = st.checkbox(
        "Mark hunt complete",
        value=pokemon.is_done,
        key=f"done_{pokemon.hunt_id}",
    )
    if done != pokemon.is_done:
        pokemon.is_done = done
        save_and_rerun(pokemon)

    st.divider()


# ---------------------------------------------------------------------------
# Completed hunts
# ---------------------------------------------------------------------------

st.subheader("Completed hunts")

if not completed_hunts:
    st.caption("No completed hunts yet.")
else:
    for pokemon in completed_hunts:
        with st.expander(
            f"{pokemon.name} | {pokemon.game} | "
            f"{attempt_count_text(pokemon.encounter_count, pokemon.encounter_method)}"
        ):
            hunt_header(pokemon)
            render_odds(pokemon)
            reopen_col, delete_col = st.columns([1, 1])
            if reopen_col.button(
                "Reopen hunt",
                key=f"reopen_{pokemon.hunt_id}",
                use_container_width=True,
            ):
                pokemon.is_done = False
                save_and_rerun(pokemon)
            if delete_col.button(
                "Delete",
                key=f"delete_done_{pokemon.hunt_id}",
                use_container_width=True,
            ):
                delete_dialog(pokemon)


# ---------------------------------------------------------------------------
# Phase history
# ---------------------------------------------------------------------------

st.subheader("Phase history")
st.caption(
    "Phases are grouped by the original hunt. They are separate from completed "
    "hunts and never create a new hunt."
)

if phase_rows.empty:
    st.info("No phases recorded yet. Use Record phase on an active hunt.")
else:
    for _, summary in phase_rows.iterrows():
        hunt_id = str(summary["hunt_id"])
        group = phases_by_hunt.get(hunt_id)
        if group is None:
            continue
        target = str(summary["target_pokemon"]) or "Unknown target"
        hunt = hunts_by_id.get(hunt_id)
        unit = (
            counter_label(hunt.encounter_method).lower() if hunt is not None else "attempts"
        )
        label = (
            f"{target} | {int(summary['phase_count'])} phase(s) | "
            f"{int(summary['total_encounters']):,} {unit}"
        )
        with st.expander(label):
            if hunt is not None:
                st.caption(
                    f"Hunt ID `{hunt_id}` | {hunt.game} | "
                    f"{encounter_method_label(hunt.encounter_method)} | "
                    f"current counter {hunt.encounter_count:,}"
                )
            else:
                st.caption(f"Hunt ID `{hunt_id}` | the original hunt no longer exists")

            count_column = (
                counter_label(hunt.encounter_method) if hunt is not None else "Attempts"
            )
            display = group[
                ["phase", "phased_pokemon", "encounter_count", "target_pokemon"]
            ].rename(
                columns={
                    "phase": "Phase",
                    "phased_pokemon": "Encountered",
                    "encounter_count": count_column,
                    "target_pokemon": "Target",
                }
            )
            st.dataframe(
                display,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Phase": st.column_config.NumberColumn(format="%d"),
                    count_column: st.column_config.NumberColumn(format="%d"),
                },
            )


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
st.caption(
    "Odds use the exact compounded formula "
    "`1 - (1 - 1/base_odds)^rolls`. See `SHINY_MECHANICS.md` for sources and "
    "unsupported mechanics."
)
