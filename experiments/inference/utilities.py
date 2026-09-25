import pandas as pd
from pydantic import JsonValue
from rich.padding import Padding
from rich.style import Style
from rich.table import Table

from experiments.inference.settings import Settings
from experiments.llm import Message, Role


def count_values(v: JsonValue) -> int:
    if isinstance(v, list):
        return sum(count_values(i) for i in v)
    if isinstance(v, dict):
        return sum(count_values(i) for i in v.values())
    return 1


def render_message(message: Message) -> None:
    if message.content is None:
        return
    role = {
        Role.User: "👤",
        Role.Assistant: "🤖",
        Role.System: "⚙️",
        Role.Tool: "⛏️",
    }
    Settings.console.print(
        f"> {role[message.role]}  {message.role.value.capitalize()}:"
    )
    Settings.console.print(Padding.indent(message.content, 2), highlight=False)


def render_table(df: pd.DataFrame) -> None:
    table = Table()
    table.add_column("metric@k", style=Style(bold=True))
    for h in df.columns:
        table.add_column(h)
    for r in df.itertuples(index=True):
        table.add_row(*map(str, r))
    Settings.console.print(table)
