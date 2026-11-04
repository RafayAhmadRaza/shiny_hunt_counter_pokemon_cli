from dataclasses import field
from pandas import DataFrame
import os
import pandas as pd
from dataclasses import dataclass,replace
from uuid import uuid4

@dataclass
class Pokemon:
    name:str
    encounter_count:int
    generation:int
    game:str 
    is_done:bool
    hunt_id:str = field(default_factory=lambda:str(uuid4()))
    odds:int | None = None
    shiny_charm: bool = False

    def __post_init__(self):
        if self.odds is None:
            self.odds = (
                8192 if self.generation <=5
                else 4096
            )
    
def add_encounter(p:Pokemon) -> Pokemon:
    return replace(
        p,
        encounter_count=p.encounter_count+1
    )
def remove_encouter(p:Pokemon) -> Pokemon:
    return replace(
        p,
        encounter_count=max(0,p.encounter_count-1)
    )

def custom_add_encounter(p:Pokemon,increase_count:int):
    if increase_count<=0:
        raise ValueError("Increase must be positive")
    return replace(
        p,
        encounter_count=p.encounter_count+increase_count
    )

def custom_remove_encounter(p:Pokemon,decrease_count:int):
    if decrease_count<=0:
        raise ValueError("Value enter must be positive")
    return replace(
        p,
        encounter_count=max(0,p.encounter_count-decrease_count)
    )

def toggle_shiny_charm(p:Pokemon)->Pokemon:
    charm_bool = not p.shiny_charm
    return replace(
        p,
        shiny_charm=charm_bool
    )

def mark_hunt_complete(p:Pokemon)-> Pokemon:
    return replace(
        p,
        is_done=True
    )

def start_new_hunt(p:Pokemon,df:pd.DataFrame,csv_path)->pd.DataFrame:
    df = save_hunt_to_csv(p,df,csv_path)
    return df


def select_hunt(dataframe: pd.DataFrame) -> str | None:
    if dataframe.empty:
        print("No hunts found. Start a new hunt with N.")
        return None

    list_hunts(dataframe, select_mode=True)

    while True:
        selection = input(
            "Enter number of hunt (Q to cancel): "
        ).strip()

        if selection.lower() == "q":
            return None

        if not selection.isdigit():
            print("Enter a valid number.")
            continue

        selection = int(selection)

        if selection >= len(dataframe):
            print("Selection out of range.")
            continue

        selected_row = dataframe.iloc[selection]
        return str(selected_row["hunt_id"])

def list_hunts(dataframe: pd.DataFrame,select_mode=False) -> None:

    if dataframe.empty:
        print("No Hunts found. Start a new hunt with N.")
        return
    
        for index, (_, row) in enumerate(dataframe.iterrows()):
            if select_mode:
                print(
                    index,
                    row["name"],
                    row["game"],
                    row["generation"]
                )
            else:
                print(
                    row["name"],
                    row["game"],
                    row["generation"]
                )
            
def save_hunt_to_csv(p:Pokemon,dataframe:pd.DataFrame,csv_path) -> pd.DataFrame:
    data_dict = {
                "name":p.name,
                "encounter_count":p.encounter_count,
                "generation":p.generation,
                "game":p.game,
                "is_done":p.is_done,
                "odds":p.odds,
                "shiny_charm":p.shiny_charm,
                "hunt_id":p.hunt_id
    }

    new_row = pd.DataFrame([data_dict])

    dataframe= pd.concat([dataframe,new_row],ignore_index=True)
    dataframe.to_csv(csv_path,index=False)
    return dataframe

def update_hunt_in_csv()->None:
    pass

def remove_hunt_from_csv(
    p: Pokemon,
    dataframe: pd.DataFrame,
    csv_path: str
) -> pd.DataFrame:

    dataframe = dataframe.loc[
        dataframe["hunt_id"] != p.hunt_id
    ].copy()

    dataframe.to_csv(csv_path, index=False)
    return dataframe
    

def load_csv(csv_path) -> pd.DataFrame: 
    return pd.read_csv(csv_path)

def create_csv(csv_path) -> pd.DataFrame: 
    
    if os.path.exists(csv_path):
        dataframe = load_csv(csv_path)
    
    else:
        dataframe = pd.DataFrame(
            columns=[
                "name",
                "encounter_count",
                "generation",
                "game",
                "is_done",
                "odds",
                "shiny_charm",
                "hunt_id"
            ]
        )

        dataframe.to_csv(csv_path,index=False)

        return dataframe

