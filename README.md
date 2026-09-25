# jqBench

Load jqStack, jqStackEasy, and jqSpider, execute jq or Python programs, and evaluate their correctness with the `jqbench` package.

## Install

Requires Python 3.12+.
From the checkout's `code` directory:

```powershell
pip install .
```

Use `pip install ".[hub]"` to enable optional Hugging Face downloads.
Datasets are separate from the installed package.

## Quickstart

Save this as a Python file and run it from `code`:

```python
from jqbench import Program, aggregate, evaluate_benchmark, load

if __name__ == "__main__":
    dataset = load("jqStack", path=r"..\data")
    benchmark = dataset.benchmarks[0]
    print(benchmark.identifier, benchmark.utterance)
    candidate = Program(kind="jq", code=".")
    score = evaluate_benchmark(candidate, benchmark)
    print(score.model_dump())
    print(aggregate([score]))
```

`path` selects the data directory and overrides `JQBENCH_DATA`.
To download when local files are unavailable, use `load("jqSpider", download=True)`; add `revision="<commit>"` to pin the Hub version.
Loading does not execute programs.
See the [data README](../data/README.md) for datasets and schemas.

## API overview

All names below are available from `jqbench`.

| API                                                                        | Purpose                                                              |
| -------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `load(name, *, path=None, download=False, revision=None)`                  | Return a `Dataset` with typed `Benchmark` records in `.benchmarks`.  |
| `Program(kind=..., code=...)`, `compiles(program)`, `run(program, input)`  | Describe, check, and execute a program.                              |
| `evaluate_benchmark(program, benchmark)`                                   | Evaluate a candidate against a benchmark's references and settings.  |
| `evaluate(program, inputs, solutions, settings=None)`                      | Evaluate explicit inputs against jq reference expressions.           |
| `aggregate(metrics)`                                                       | Average compilation, execution, exact-match, and value-match scores. |
| `equals(expected, actual, settings=None)`, `EvaluationSettings`, `Metrics` | Compare JSON values, configure comparison, and represent scores.     |

Programs use `kind="jq"` or `kind="python"`; Python code defines a top-level function accepting one JSON value.
`run` returns a list of outputs for jq and the function's JSON result for Python.
Execution failures raise errors.

Keep the `__main__` guard: execution uses spawned worker processes.
Workers are **not a security sandbox**; only execute trusted programs.

For research workflows, see [Experiments](experiments/README.md).
