from typing import Union

from pydantic import BaseModel, Field, RootModel


class Column(BaseModel):
    name: str
    type: str


class Table(BaseModel):
    name: str
    columns: list[Column]
    foreignKeys: dict[str, str]
    rows: list[dict[str, Union[str, int, float, None]]]


class Database(RootModel):
    root: dict[str, Table] = Field(default_factory=dict)
