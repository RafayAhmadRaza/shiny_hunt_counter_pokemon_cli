from os import name
import pandas as pd
from dataclasses import dataclass,asdict

@dataclass
class Pokemon:
    name:str
    encounter_count:int
    generation:int
    game:str 
    isDone:bool
    odds:int | None = None
    shiny_charm: bool = False

    def __post_init__(self):
        if not self.odds:
            self.odds = (
                8192 if self.generation <=5
                else 4096
            )
    
