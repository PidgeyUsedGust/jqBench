"""Load and evaluate jqBench without the research repository."""

from .execution import (
    ExecutionError,
    JqExecutionEngine,
    JqExecutionError,
    Program,
    ProgramKind,
    PythonExecutionEngine,
    compiles,
    run,
)
from .loading import (
    DATASETS,
    Benchmark,
    Dataset,
    InputPath,
    decode_record,
    evaluate_benchmark,
    load,
    resolve_inputfile,
)
from .metrics import (
    EvaluationSettings,
    MetricNames,
    Metrics,
    ValueMatch,
    aggregate,
    equals,
    evaluate,
)

__all__ = [
    "Benchmark",
    "Dataset",
    "DATASETS",
    "InputPath",
    "load",
    "decode_record",
    "resolve_inputfile",
    "Program",
    "ProgramKind",
    "ExecutionError",
    "JqExecutionError",
    "JqExecutionEngine",
    "PythonExecutionEngine",
    "compiles",
    "run",
    "EvaluationSettings",
    "Metrics",
    "MetricNames",
    "ValueMatch",
    "equals",
    "evaluate",
    "evaluate_benchmark",
    "aggregate",
]
