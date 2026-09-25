# jqBench

Load **jqStack**, **jqStackEasy**, and **jqSpider**, execute jq or Python programs, and evaluate their correctness with the `jqbench` package.

See the [dataset README on Hugging Face](https://huggingface.co/datasets/PidgeyUsedGust/jqBench/blob/main/README.md) for dataset descriptions, schemas, and shared input files.

## Install

Requires Python 3.12+.
From the checkout's `code` directory:

```powershell
pip install .
```

For optional Hugging Face downloads, install the `hub` extra instead:

```powershell
pip install ".[hub]"
```

Datasets are distributed separately from the installed package.

## Quickstart

This self-contained example evaluates a jq program against a small hypothetical benchmark; no dataset download is needed.
Save it as a Python file:

```python
import json

from jqbench import Benchmark, Program, aggregate, evaluate_benchmark, run

if __name__ == "__main__":
    benchmark = Benchmark(identifier="example", utterance="Return the person's name.", inputs=[{"name": "Ada", "age": 36}], expressions=[".name"])
    candidate = Program(kind="jq", code=".name")
    print(json.dumps(run(candidate, {"name": "Ada", "age": 36})))
    score = evaluate_benchmark(candidate, benchmark)
    print(json.dumps(score.model_dump(mode="json")))
    print(json.dumps({name.value: value for name, value in aggregate([score]).items()}))
```

Illustrative output for this hypothetical benchmark (not a captured run):

```text
["Ada"]
{"compiles": true, "executes": true, "value_match": "Exact", "exact_match": true}
{"compiles": 1.0, "executes": 1.0, "value_match": 1.0, "exact_match": 1.0}
```

The candidate matches the reference expression and produces the expected value.
`aggregate` reports averages across a nonempty collection of scores.

Keep the `__main__` guard when executing or evaluating programs: execution uses spawned worker processes.
Workers are **not a security sandbox**; only execute trusted programs.

## Load datasets

Load local data from `code`, with the data directory alongside it:

```python
from jqbench import load

dataset = load("jqStack", path=r"..\data")
benchmark = dataset.benchmarks[0]
```

`path` selects the data directory and overrides `JQBENCH_DATA`.
Without either, loading requires an explicit opt-in to download.
With the `hub` extra installed, allow a Hub download when local data is unavailable:

```python
from jqbench import load

dataset = load("jqSpider", download=True)
```

Add `revision="<commit>"` to pin the Hub version; downloaded rows and shared input files use the same resolved commit.
Loading returns typed records in `dataset.benchmarks` and does not execute programs.

## API overview

All names below are available from `jqbench`.

| API                                                       | Purpose                                                                     |
| --------------------------------------------------------- | --------------------------------------------------------------------------- |
| `load(name, *, path=None, download=False, revision=None)` | Load a named dataset from local files or, with opt-in, the Hub.             |
| `Dataset`                                                 | Hold a dataset's name and typed records in `.benchmarks`.                   |
| `Benchmark`                                               | Describe a task, reference expressions, inputs, and evaluation settings.    |
| `Program(kind=..., code=...)`                             | Describe a jq or Python candidate program.                                  |
| `compiles(program)`                                       | Return whether the program passes compilation checks, without executing it. |
| `run(program, input)`                                     | Execute a program on one JSON input and return its output.                  |
| `evaluate_benchmark(program, benchmark)`                  | Return `Metrics` using a benchmark's inputs, references, and settings.      |
| `evaluate(program, inputs, solutions, settings=None)`     | Return `Metrics` for explicit inputs and jq reference expressions.          |
| `aggregate(metrics)`                                      | Return mean scores keyed by `MetricNames`; requires a nonempty collection.  |
| `equals(expected, actual, settings=None)`                 | Return a `ValueMatch` category, not a boolean, when comparing JSON values.  |
| `EvaluationSettings`                                      | Configure how JSON keys and array order affect comparison.                  |
| `Metrics`                                                 | Hold compilation, execution, value-match, and exact-match results.          |

## Execution and evaluation

Programs use `kind="jq"` or `kind="python"`; Python code defines a top-level function accepting one JSON value.
`run` returns a list of outputs for jq and the function's JSON result for Python.
Direct execution failures raise errors.
Evaluation records candidate compilation and execution failures in the scores; invalid reference programs raise errors.
Exact match checks whether a jq candidate's source equals a reference expression; value match compares the resulting JSON values.

For research workflows, see [Experiments](experiments/README.md).

## Citation

If you use jqBench in your research, please cite the jqBench paper:

```bibtex
@inproceedings{verbruggen2026iclr-jqbench,
  title     = {{jqBench: A Benchmark for Reading and Editing JSON from Natural Language And/or Examples}},
  author    = {Verbruggen, Gust and Parnin, Chris and Le, Vu and Gulwani, Sumit},
  booktitle = {International Conference on Learning Representations},
  year      = {2026},
  url       = {https://mlanthology.org/iclr/2026/verbruggen2026iclr-jqbench/}
}
```
