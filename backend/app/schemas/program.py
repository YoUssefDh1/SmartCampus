from pydantic import BaseModel, Field


class Program(BaseModel):
    id: str = Field(examples=["iit-prepa-integree"])
    school: str = Field(examples=["IIT"])
    name: str
    level: str = Field(examples=["Préparatoire"])
    duration_years: int
    description: str
    admission: str
    careers: list[str] = []
    bridges: list[str] = []
