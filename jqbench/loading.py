"""Passive benchmark loading from an explicit local root or the Hugging Face Hub."""

import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated, Self

from pydantic import BaseModel, Field, JsonValue, PlainSerializer, model_validator

from .execution import Program
from .metrics import EvaluationSettings, Metrics, evaluate

REPOSITORY = "PidgeyUsedGust/jqBench"
DATASETS = {
    "jqStack": "jqStackFixed",
    "jqStackEasy": "jqStackEasy",
    "jqSpider": "spider",
}
InputPath = Annotated[
    Path, PlainSerializer(lambda value: value.as_posix(), return_type=str)
]


class Benchmark(BaseModel):
    identifier: str | int
    utterance: str
    expressions: list[str]
    inputs: list[JsonValue] | None = None
    tasks: list[str] = Field(default_factory=list)
    inputfile: InputPath | None = None
    jsonschema: JsonValue = None
    jsonoutput: JsonValue = None
    settings: EvaluationSettings | None = None

    @model_validator(mode="after")
    def validate_inputs(self) -> Self:
        if self.inputs is not None and self.inputfile is not None:
            raise ValueError("Benchmark cannot have both inputs and inputfile")
        return self


class Dataset(BaseModel):
    name: str
    benchmarks: list[Benchmark]


def load(
    name: str,
    *,
    path: str | Path | None = None,
    download: bool = False,
    revision: str | None = None,
) -> Dataset:
    """Load local data first; download=True permits a complete, pinned Hub fallback."""
    if name not in DATASETS:
        raise ValueError(f"Unknown dataset {name!r}; choose from {', '.join(DATASETS)}")
    root = path if path is not None else os.environ.get("JQBENCH_DATA")
    if root is not None:
        root = Path(root).expanduser().resolve()
        try:
            with (root / f"{name}.jsonl").open(encoding="utf-8") as handle:
                records = [
                    decode_record(json.loads(line)) for line in handle if line.strip()
                ]
            for record in records:
                if record.get("inputfile") is not None:
                    record["inputfile"] = resolve_inputfile(
                        record["inputfile"], root=root
                    )
            return Dataset(name=DATASETS[name], benchmarks=records)
        except FileNotFoundError:
            if not download:
                raise
    elif not download:
        raise ValueError(
            "Set JQBENCH_DATA, pass load(..., path=...), or opt in with download=True"
        )
    return _load_hub(name, revision)


def decode_record(row: dict) -> dict:
    decoded = {}
    for key, value in row.items():
        target = key[:-5] if key.endswith("_json") else key
        if target in decoded:
            raise ValueError(f"Duplicate decoded benchmark field: {target}")
        decoded[target] = json.loads(value) if key.endswith("_json") else value
    return decoded


def resolve_inputfile(value: str | Path, *, root: str | Path | None = None) -> Path:
    relative = _input_relative(str(value))
    root = root if root is not None else os.environ.get("JQBENCH_DATA")
    if root is None:
        raise ValueError("Provide an input root or set JQBENCH_DATA")
    base = Path(root).expanduser().resolve()
    candidate = (base / relative).resolve()
    if not candidate.is_relative_to(base):
        raise ValueError(f"Input is outside its dataset root: {value!r}")
    if not candidate.is_file():
        raise FileNotFoundError(f"Input {value!r} is missing: {candidate}")
    return candidate


def evaluate_benchmark(program: Program, benchmark: Benchmark) -> Metrics:
    inputs = benchmark.inputs
    if inputs is None:
        if benchmark.inputfile is None:
            raise ValueError("Benchmark has neither inputs nor inputfile")
        with benchmark.inputfile.open(encoding="utf-8") as handle:
            inputs = [json.load(handle)["data"]]
    return evaluate(program, inputs, benchmark.expressions, benchmark.settings)


def _input_relative(value):
    windows, relative = PureWindowsPath(value), PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or windows.drive
        or windows.root
        or relative.is_absolute()
        or ".." in relative.parts
    ):
        raise ValueError(f"Expected a portable relative input path: {value!r}")
    return Path(*relative.parts)


def _load_hub(name, revision):
    try:
        from datasets import load_dataset
        from huggingface_hub import HfApi, hf_hub_download
    except ImportError as error:
        raise ImportError("Hub downloads require the jqbench[hub] extra") from error
    commit = HfApi().dataset_info(REPOSITORY, revision=revision).sha
    rows = load_dataset(REPOSITORY, name=name, split="data", revision=commit)
    records = [decode_record(dict(row)) for row in rows]
    for record in records:
        if record.get("inputfile") is not None:
            filename = _input_relative(record["inputfile"]).as_posix()
            record["inputfile"] = hf_hub_download(
                REPOSITORY, filename, repo_type="dataset", revision=commit
            )
    return Dataset(name=DATASETS[name], benchmarks=records)
