from pydantic import BaseModel
class LoginIn(BaseModel): email:str; password:str
class RenameIn(BaseModel): name:str
class MarketSearchIn(BaseModel):
 make:str
 model:str
 year:int|None=None
