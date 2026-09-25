from enum import Enum

from rich.console import Console

from experiments.paths import paths


class Verbosity(Enum):
    Debug = "debug"
    All = "all"
    Off = "off"


class Settings:
    verbosity: Verbosity = Verbosity.Off
    console: Console = Console(quiet=True)

    data = paths.stack
