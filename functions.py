from dataclasses import field
import os
import pandas as pd
from dataclasses import dataclass,replace,asdict
from uuid import uuid4

CSV_PATH = "hunts.csv"

@dataclass
class Pokemon:
    name:str
    encounter_count:int
    generation:int
    game:str 
    is_done:bool=False
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
def remove_encounter(p:Pokemon) -> Pokemon:
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


def select_hunt(dataframe: pd.DataFrame) -> Pokemon | None:
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
        return Pokemon(
            **selected_row.to_dict()
        )

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

def update_hunt_in_csv(p:Pokemon,df:pd.DataFrame,csv_path)->pd.DataFrame:
    mask = df["hunt_id"] == p.hunt_id

    if not mask.any():
        raise ValueError("Hunt not found")
    updated_row = asdict(p)

    df.loc[mask,updated_row.keys()] = updated_row.values()
    df.to_csv(csv_path,index=False)
    return df

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

def from_csv_to_Pokemon(df:pd.DataFrame) ->list[Pokemon]:
    """Maps Data from CSV to Pokemon Objects"""
    p_list:list[Pokemon] = []
    for index,row in df.iterrows():
            p_list.append(Pokemon(
            name=row["name"],
            encounter_count=row["encounter_count"],
            generation=row["generation"],
            game=row["game"],
            is_done=row["is_done"],
            hunt_id=row["hunt_id"],
            odds=row["odds"],
            shiny_charm=row["shiny_charm"]
        ))
    return p_list

def calulate_probability(p:Pokemon) -> float:
    prob = (1 - (( 1 -1/p.odds)**p.encounter_count)) * 100
    
    return prob
    
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


if __name__ == "__main__":

    df = create_csv(CSV_PATH)

    # p_list = from_csv_to_Pokemon(df)

    # print(p_list)

    selection = ""
    
    exit = False
    
    while not exit:
        print("A - Add New Hunt\n L - List Hunts \n R - Remove Hunt\n S- Select Hunt\nQ - Quit")
        
        selection = input("Enter your selection: ").lower()

        match selection:
            case 'q':
                exit = True
            case "a":
                name = input("Enter Pokemon's Name: ")
                generation = input ("Enter Generation Of Game: ")

                while not generation.isdigit():
                    generation = input ("Enter Generation Of Game: ")
                
                generation = int(generation)
                game = input("Enter Game Name: ")

                shiny_charm = input("Do you have a shiny charm? Y/N: ")
                sc = shiny_charm == "y"
                p = Pokemon(name=name,encounter_count=0,generation=generation,game=game,is_done=False,shiny_charm=sc)
                df =save_hunt_to_csv(p,df,CSV_PATH)
            case "l":
                list_hunts(df)
            case "r":
                pokemon = select_hunt(df)

                if pokemon is not None:

                    df = remove_hunt_from_csv(pokemon,df,CSV_PATH)
            case "s":
                p = select_hunt(df)
                
                if p is not None:
                    ishunting = True

                    while ishunting:
                        print("Information About Current Hunt!")
                        print("Name: ",p.name)
                        print("Game: ",p.game)
                        print("Encounters: ",p.encounter_count)
                        print("Gen: ",p.generation)
                        print("Odds: 1 in",p.odds)
                        print("Shiny Charm: ","No" if p.shiny_charm==False else "Yes")
                        prob = (1 - (( 1 -1/p.odds)**p.encounter_count)) * 100
                        print(f"Probability: {prob:.4f}%")
                        
                        selection = input("A- Add Encounter, S - Subtract Encounter \nC- Add Custom Encounter Amount, R - Remove Custom Encounter Amount\nF - Done, Q - Quit\n")

                        match selection.lower():
                            case 'a':
                                p = add_encounter(p)
                            case 's':
                                p = remove_encounter(p)
                            case 'c':
                                incounter = input("Enter Increase Amount: ")

                                while not incounter.isdigit():
                                    incounter = input("Enter Increase Amount: ")

                                incounter = int(incounter)

                                p = custom_add_encounter(p,incounter)
                            case 'd':
                                decounter = input("Enter Decrease Amount: ")

                                while not decounter.isdigit():
                                    decounter = input("Enter Decrease Amount: ")

                                decounter = int(decounter)

                                p = custom_remove_encounter(p,decounter)
                            case 'q':
                                ishunting=False
                            
                            case 'f':
                                p = mark_hunt_complete(p)
                                update_hunt_in_csv(p,df,CSV_PATH)
                                ishunting = False
                    
                    df = update_hunt_in_csv(p,df,CSV_PATH)

