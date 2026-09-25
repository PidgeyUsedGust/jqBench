"""Repository-only research paths; never used by the installed benchmark API."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Paths:
    def __init__(self):
        self._values = None

    def __getattr__(self, name):
        if name == "docs":
            return ROOT / "documentation"
        if self._values is None:
            import yaml

            config = (
                Path(os.environ.get("JQBENCH_CONFIG", ROOT / "config.yaml"))
                .expanduser()
                .resolve()
            )
            with config.open(encoding="utf-8") as handle:
                values = yaml.safe_load(handle)
            required = {
                "data",
                "stack",
                "spider",
                "results",
                "caches",
                "reports",
                "posts",
            }
            if not isinstance(values, dict) or set(values) != required:
                raise ValueError(
                    f"{config} must define exactly these paths: {sorted(required)}"
                )
            self._values = {}
            for key, value in values.items():
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(
                        f"Configuration path {key!r} must be a nonempty string"
                    )
                candidate = Path(value).expanduser()
                self._values[key] = (config.parent / candidate).resolve()
        if name not in self._values:
            raise AttributeError(name)
        return self._values[name]


paths = Paths()
