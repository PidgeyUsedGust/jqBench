import json
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Optional, Self, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    PlainSerializer,
    model_validator,
)

from experiments.inference.utilities import count_values
from experiments.llm import AgentToolCall, Usage
from experiments.llm.configuration import ModelConfiguration
from experiments.paths import paths
from jqbench import DATASETS, Benchmark, Dataset, decode_record, resolve_inputfile
from jqbench import load as load_dataset
from jqbench.execution import JqExecutionEngine, Program
from jqbench.metrics import Metrics


class InputKind(Enum):
    Empty = "Empty"
    Examples = "Examples"
    Input = "Input"
    InputOutput = "InputOutput"
    Schema = "Schema"


class InputSet(Enum):
    All = "All"
    AllButOne = "AllButOne"
    Na = "Na"
    One = "One"


class InputConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: InputKind
    which: InputSet

    @property
    def name(self) -> str:
        if self.kind == InputKind.Empty:
            return f"kind={self.kind.value}"
        return f"kind={self.kind.value}-which={self.which.value}"

    @model_validator(mode="after")
    def validate(self) -> Self:
        if self.kind in {InputKind.Empty, InputKind.Schema}:
            self.which = InputSet.Na
        return self


class Input(BaseModel):
    kind: Literal[InputKind.Input] = InputKind.Input
    inputs: list[JsonValue]


class InputOutput(BaseModel):
    kind: Literal[InputKind.InputOutput] = InputKind.InputOutput
    inputs: list[JsonValue]
    outputs: list[JsonValue]


class Schema(BaseModel):
    kind: Literal[InputKind.Schema] = InputKind.Schema
    jsonschema: JsonValue
    jsonoutput: Optional[JsonValue] = None
    dataset: JsonValue


ProblemInput = Annotated[Union[Input, InputOutput, Schema], Field(discriminator="kind")]
InputPath = Annotated[
    Path, PlainSerializer(lambda value: value.as_posix(), return_type=str)
]


class Problem(BaseModel):
    utterance: Optional[str] = None
    input: Optional[ProblemInput] = None


class Prediction(BaseModel):
    program: Program
    metrics: Metrics


class SolutionMetadata(BaseModel):
    usage: list[Usage] = Field(default_factory=list)
    tools: list[list[AgentToolCall]] = Field(default_factory=list)
    feedback: list[Union[str, bool]] = Field(default_factory=list)


class Solution(BaseModel):
    identifier: Union[str, int]
    inputs: Optional[list[JsonValue]] = None
    inputfile: Optional[InputPath] = None
    solutions: list[str]
    predictions: list[Prediction]
    metadata: Optional[SolutionMetadata] = None


class Experiment(BaseModel):
    dataset: str
    solver: dict[str, Union[str, int, float]]
    input: InputConfiguration
    model: ModelConfiguration
    solutions: list[Solution] = Field(default_factory=list)


def problem(benchmark: Benchmark, configuration: InputConfiguration) -> Problem:
    if configuration.kind == InputKind.Empty:
        return Problem(utterance=benchmark.utterance)
    inputs = []
    if configuration.kind != InputKind.Schema and not benchmark.inputs:
        raise ValueError("Example-based problems require benchmark inputs")
    match configuration.which:
        case InputSet.One:
            inputs = benchmark.inputs[:1]
        case InputSet.All:
            inputs = benchmark.inputs
        case InputSet.AllButOne:
            if len(benchmark.inputs) < 2:
                raise ValueError("AllButOne requires at least two benchmark inputs")
            if len(benchmark.inputs) == 2:
                inputs = benchmark.inputs[:1]
            else:
                ishort = min(
                    enumerate(benchmark.inputs), key=lambda x: count_values(x[1])
                )
                inputs = [ishort[1]] + [
                    i for j, i in enumerate(benchmark.inputs) if j != ishort[0]
                ][: len(benchmark.inputs) - 2]
    i = None
    u = benchmark.utterance
    match configuration.kind:
        case InputKind.Input:
            i = Input(inputs=inputs)
        case InputKind.InputOutput | InputKind.Examples:
            i = InputOutput(
                inputs=inputs,
                outputs=[
                    JqExecutionEngine.execute(benchmark.expressions[0], i)
                    for i in inputs
                ],
            )
            if configuration.kind == InputKind.Examples:
                u = None
        case InputKind.Schema:
            d = (
                json.loads(benchmark.inputfile.read_text())["data"]
                if benchmark.inputfile
                else None
            )
            i = Schema(
                jsonschema=benchmark.jsonschema,
                dataset=d,
                jsonoutput=benchmark.jsonoutput,
            )
    return Problem(utterance=u, input=i)


def load(
    file: Path, debug: Optional[int] = None, *, input_root: Optional[Path] = None
) -> Dataset:
    if str(file) in DATASETS:
        data = load_dataset(str(file), path=paths.data)
    else:
        if file.suffix == ".jsonl":
            payload = {
                "name": DATASETS[file.stem],
                "benchmarks": [
                    decode_record(json.loads(line))
                    for line in file.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ],
            }
        else:
            payload = json.loads(file.read_text(encoding="utf-8"))
        for benchmark in payload["benchmarks"]:
            if benchmark.get("inputfile") is not None:
                benchmark["inputfile"] = resolve_inputfile(
                    benchmark["inputfile"], root=input_root or paths.data
                )
        data = Dataset.model_validate(payload)
    if debug:
        data.benchmarks = [
            i for i in data.benchmarks if str(i.identifier) == str(debug)
        ]
    return data
