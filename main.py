import streamlit as st
from functions import (
    CSV_PATH,
    create_csv,
    remove_hunt_from_csv,
    custom_add_encounter,
    custom_remove_encounter,
    save_hunt_to_csv,
    remove_hunt_from_csv,
    update_hunt_in_csv,
    calulate_probability,
    from_csv_to_Pokemon,
    update_hunt_in_csv,
    Pokemon
)

@st.dialog("AreYouSure")
def areyousure(p,df):
    st.write("Are you sure you want to delete this hunt.")

    c1,c2 = st.columns(2)
    with c1:
        if st.button("Yes", key="remove_yes"):
            df = remove_hunt_from_csv(p, df, CSV_PATH)
            st.rerun()

    with c2:
        if st.button("No", key="remove_no"):
            st.rerun()


st.title("Shiny Hunt Tracker")

df = create_csv(CSV_PATH)
st.write(df)
p_list = from_csv_to_Pokemon(df)

total_encounters=0
total_hunts = 0
active_hunts=0
for p in p_list:
    total_encounters+=p.encounter_count
    if not p.is_done:
        active_hunts+=1
    total_hunts+=1



col1,col2,col3 = st.columns(3)
col1.write("## Total Encounters")
col1.write(f"### {total_encounters}")
col2.write("## Active Hunts")
col2.write(f"### {active_hunts}")
col3.write("## Total Hunts")
col3.write(f"### {total_hunts}")


st.divider()


for p in p_list:
    if not p.is_done:
        with st.container(border=True):

            col1, col2, col3 = st.columns([1, 5, 1],vertical_alignment="center")

            with col1:
                if st.button("Minus", key=f"remove_{p.hunt_id}",width="content"):
                    p = custom_remove_encounter(p,1)
                    update_hunt_in_csv(p,df,CSV_PATH)
                    st.rerun()
            
            with col2:
                st.markdown(
                    f"<h3 style='text-align: center;'>{p.name}</h3>",
                    unsafe_allow_html=True
                )

                col_game, col_gen = st.columns(2)

                col_game.markdown(
                    f"<div style='text-align: center;'><b>Game</b><br>{p.game}</div>",
                    unsafe_allow_html=True
                )

                col_gen.markdown(
                    f"<div style='text-align: center;'><b>Generation</b><br>{p.generation}</div>",
                    unsafe_allow_html=True
                )

                col_enc, col_odds = st.columns(2)

                col_enc.markdown(
                    f"<div style='text-align: center;'><b>Encounters</b><br>{p.encounter_count}</div>",
                    unsafe_allow_html=True
                )

                col_odds.markdown(
                    f"<div style='text-align: center;'><b>Odds</b><br>1/{p.odds}</div>",
                    unsafe_allow_html=True
                )

                probability = calulate_probability(p)

                st.markdown(
                    f"<h4 style='text-align: center;'>Probability: {probability:.2f}%</h4>",
                    unsafe_allow_html=True
                )

                c1, checkbox_col, _ = st.columns([1, 2, 1])

                with c1:
                    if st.button("remove",key=f"remove_hunt{p.hunt_id}"):
                        
                        areyousure(p,df)


                with checkbox_col:
                    shiny_charm = st.checkbox(
                        "Shiny Charm",
                        value=p.shiny_charm,
                        key=f"charm_{p.hunt_id}"
                    )
                with _:
                    is_done = st.checkbox(
                        "Hunt Done",
                        value=p.is_done,
                        key=f"done_{p.hunt_id}"
                    )

                isChanged = False
                
                if shiny_charm != p.shiny_charm:
                    p.shiny_charm = shiny_charm
                    isChanged=True
                if p.is_done != is_done:
                    p.is_done = is_done
                    isChanged = True

                if isChanged:
                    update_hunt_in_csv(p,df,CSV_PATH)
                    st.rerun()


            with col3:
                if st.button("Add", key=f"add_{p.hunt_id}",width="content"):
                    p = custom_add_encounter(p,1)
                    update_hunt_in_csv(p,df,CSV_PATH)
                    st.rerun()

if "show_form" not in st.session_state:
    st.session_state.show_form = False

if st.button("Add New Hunt"):
    st.session_state.show_form = True

if st.session_state.show_form:
    with st.form("my_form", clear_on_submit=True):
        st.write("New Hunt")

        name = st.text_input("Enter Pokemon Name")
        game = st.text_input("Enter Game Name")
        generation = st.number_input(
            "Enter Game Generation", 1, 9
        )

        
        shiny_charm = st.checkbox("Have Shiny Charm?")

        submitted = st.form_submit_button("Submit")

        if submitted:
            new_p = Pokemon(
                name=name,
                game=game,
                generation=generation,
                encounter_count=0,
                shiny_charm=shiny_charm
            )

            save_hunt_to_csv(new_p, df, CSV_PATH)

            st.session_state.show_form = False
            st.rerun()

st.write("History")

for p in p_list:
    if p.is_done:
        with st.container(border=True):

            col1, col2, col3 = st.columns([1, 5, 1],vertical_alignment="center")

            with col2:
                st.markdown(
                    f"<h3 style='text-align: center;'>{p.name}</h3>",
                    unsafe_allow_html=True
                )

                col_game, col_gen = st.columns(2)

                col_game.markdown(
                    f"<div style='text-align: center;'><b>Game</b><br>{p.game}</div>",
                    unsafe_allow_html=True
                )

                col_gen.markdown(
                    f"<div style='text-align: center;'><b>Generation</b><br>{p.generation}</div>",
                    unsafe_allow_html=True
                )

                col_enc, col_odds = st.columns(2)

                col_enc.markdown(
                    f"<div style='text-align: center;'><b>Encounters</b><br>{p.encounter_count}</div>",
                    unsafe_allow_html=True
                )

                col_odds.markdown(
                    f"<div style='text-align: center;'><b>Odds</b><br>1/{p.odds}</div>",
                    unsafe_allow_html=True
                )

                probability = calulate_probability(p)

                st.markdown(
                    f"<h4 style='text-align: center;'>Probability: {probability:.2f}%</h4>",
                    unsafe_allow_html=True
                )

