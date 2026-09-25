"""Correctness metrics independent of models, experiment state, or presentation."""

import json
from enum import Enum

from pydantic import BaseModel, JsonValue

from .execution import ExecutionError, Program, ProgramKind, compiles, run


class EvaluationSettings(BaseModel):
    keys: bool = True
    order: bool = False


class ValueMatch(str, Enum):
    No = "No"
    Exact = "Exact"
    Wrapped = "Wrapped"
    Unwrapped = "Unwrapped"


class Metrics(BaseModel):
    compiles: bool
    executes: bool
    value_match: ValueMatch
    exact_match: bool


MetricNames = Enum("MetricNames", ((v, v) for v in Metrics.model_fields), type=str)


def aggregate(metrics: list[Metrics]) -> dict[MetricNames, float]:
    if not metrics:
        raise ValueError("Cannot aggregate an empty collection of metrics")
    return {
        name: sum(
            getattr(metric, name.value) != ValueMatch.No
            if name.value == "value_match"
            else getattr(metric, name.value)
            for metric in metrics
        )
        / len(metrics)
        for name in MetricNames
    }


def evaluate(
    program: Program,
    inputs: list[JsonValue],
    solutions: list[str],
    settings: EvaluationSettings | None = None,
) -> Metrics:
    if not inputs or not solutions:
        raise ValueError("Evaluation requires nonempty inputs and reference solutions")
    settings = settings or EvaluationSettings()
    # Invalid references are benchmark errors, not incorrect candidate programs.
    expected = [
        [run(Program(kind=ProgramKind.Jq, code=solution), value) for value in inputs]
        for solution in solutions
    ]
    result = Metrics(
        compiles=compiles(program),
        executes=False,
        value_match=ValueMatch.No,
        exact_match=False,
    )
    if not result.compiles:
        return result
    try:
        outputs = [run(program, value) for value in inputs]
    except (ExecutionError, TimeoutError):
        return result
    result.executes = True
    result.exact_match = program.kind == ProgramKind.Jq and program.code in solutions
    ranks = {
        ValueMatch.No: 0,
        ValueMatch.Unwrapped: 1,
        ValueMatch.Wrapped: 2,
        ValueMatch.Exact: 3,
    }
    matches = []
    for values in expected:
        match = [
            equals(reference, actual, settings)
            for reference, actual in zip(values, outputs, strict=True)
        ]
        matches.append(match[0] if len(set(match)) == 1 else ValueMatch.No)
    result.value_match = max(matches, key=ranks.__getitem__)
    return result


def equals(
    expected: JsonValue, actual: JsonValue, settings: EvaluationSettings | None = None
) -> ValueMatch:
    settings = settings or EvaluationSettings()
    try:
        expected, actual = _canonical(expected, settings), _canonical(actual, settings)
        if _serialized(expected) == _serialized(actual):
            return ValueMatch.Exact
        if _serialized(expected) == _serialized([actual]):
            return ValueMatch.Wrapped
        if _serialized([expected]) == _serialized(actual):
            return ValueMatch.Unwrapped
    except (TypeError, ValueError):
        return ValueMatch.No
    return ValueMatch.No


def _canonical(value, settings):
    if isinstance(value, dict):
        if settings.keys:
            return {key: _canonical(item, settings) for key, item in value.items()}
        return sorted(
            (_canonical(item, settings) for item in value.values()), key=_serialized
        )
    if isinstance(value, list):
        items = [_canonical(item, settings) for item in value]
        # Retain the historical comparator: order is ignored only in keyless mode.
        return (
            sorted(items, key=_serialized)
            if not settings.keys and not settings.order
            else items
        )
    return value


def _serialized(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)
