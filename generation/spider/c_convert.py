import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from jsonargparse import ArgumentParser
from pydantic import JsonValue
from rich.console import Console
from tqdm import tqdm

from experiments.llm import (
    ChatModel,
    JsonCache,
    Message,
    Role,
)
from experiments.paths import paths
from jqbench.execution import JqExecutionEngine


def trim(obj: dict, n: int = 2) -> dict:
    if isinstance(obj, dict):
        return {k: trim(v, n) for k, v in obj.items()}
    if isinstance(obj, list):
        return [trim(v, n) for v in obj[:n]] + (["<TRUNCATED>"] if len(obj) > n else [])
    return obj


def promptify(v: Any) -> str:
    s = json.dumps(trim(v))
    s = s.replace('"<TRUNCATED>"', "... (truncated)")
    return s


SYSTEM_JQ = """
# Instructions

You are an expert at SQL and jq, more specifically, in converting SQL queries to jq expressions.
You are given:

 - A natural language description of the intended goal.
 - A SQL query that achieves this goal.
 - A schema of the JSON file on which the jq expression should be executed.
 - The expected output of the jq expressions when executed on the JSON file.

You return all jq expressions (wrapped in <jq></jq>) that achieve the intended goal.

# `jq`

You use the Python bindings for jq, which slightly differs in the output format.
More specifically, we assume that expression `e` is invoked on a JSON object `i` as `jq.all(e, i)` or `jq.compile(e).input_value(i).all()` (both are equivalent).
This causes the output to be wrapped in a JSON list, even if the result is a single value.

Some examples:
- `jq.all(".foo", {"foo": 1}) == [1]`
- `jq.all("{b: .a + 1}", {"a": 1}) == [{"b": 2}]`
- `jq.all(".[0]", [{"a": 1}, {"b": 2}]) == [{"a": 1}]`
- `jq.all("map(.[0])", [[1, 2], [3, 4]]) == [[1, 3]]`
""".strip()


SYSTEM_PYTHON = """
# Instructions

You are an expert at SQL and Python, more specifically, in converting SQL queries to Python functions.
You are given:

 - A natural language description of the intended goal.
 - A SQL query that achieves this goal.
 - A schema of the JSON file on which the Python function should be executed.
 - The expected output of the Python function when executed on the JSON file.

You return a Python function (wrapped in <python></python>) that achieves the intended goal.

# Python

You use standard Python 3.10+ with the `json` module.
You write a function `def transform(data: Any) -> Any:` that takes the JSON data as input and returns the expected output.
""".strip()


def user(test: dict, schema: dict) -> str:
    return f"""
# Task
{test["question"]}

# SQL query
{test["query"]}

# JSON schema
```json
{json.dumps(schema, indent=2)}
```

# Expected output
```json
{promptify(test["output"])}
```
""".strip()


def compare(a: JsonValue, b: JsonValue, order: bool = True) -> bool:
    if not isinstance(a, list):
        a = [a]
    if not isinstance(b, list):
        b = [b]
    if not order:
        a = sorted(a, key=lambda x: json.dumps(x, sort_keys=True))
        b = sorted(b, key=lambda x: json.dumps(x, sort_keys=True))
    return json.dumps(a) == json.dumps(b)


def convert_python(
    test: dict,
    schema: dict,
    dataset: dict,
    model: ChatModel,
    iterations: int = 4,
) -> dict:
    """Convert a SQL query to a Python function."""
    result = {"kind": "failure", "python": list(), "candidates": dict()}
    prompt = [
        Message(role=Role.System, content=SYSTEM_PYTHON),
        Message(
            role=Role.User,
            content=user(test=test, schema=schema),
        ),
    ]
    for _ in range(iterations):
        response = model.chat(messages=prompt)
        responses_python = re.findall(
            r"<python>(.*?)</python>", response.text, re.DOTALL
        )
        responses_python = [r.strip() for r in responses_python if r.strip()]
        results = list()
        errors = list()
        for response_python in responses_python:
            try:
                local_vars: dict[str, Any] = {}
                exec(response_python, {}, local_vars)
                if "transform" not in local_vars:
                    errors.append("❌ No function 'transform' found.")
                    continue
                func = local_vars["transform"]
                outputs = func(dataset)
            except Exception as e:
                errors.append(f"❌ Error executing Python function: {e}")
                continue
            result["candidates"][response_python] = outputs
            if not compare(
                outputs, test["output"], order="ORDER" in test["query"].upper()
            ):
                errors.append(
                    f"❌ Mismatch for Python function:\n{response_python}\n"
                    f"Got {promptify(outputs)}, expected {promptify(test['output'])}."
                )
                continue
            results.append(response_python)
        if results:
            result["kind"] = "success"
            result["python"] = results
            break
        prompt.append(Message(role=Role.Assistant, content=response.text))
        prompt.append(
            Message(
                role=Role.User,
                content=f"Errors:\n\n{'\n'.join(errors)}\n\nPlease try again.",
            )
        )
    return result


def convert_jq(
    test: dict,
    schema: dict,
    dataset: dict,
    model: ChatModel,
    iterations: int = 4,
) -> dict:
    """Convert a raw expression to jq expressions."""
    result = {"kind": "failure", "jq": list(), "candidates": dict()}
    prompt = [
        Message(role=Role.System, content=SYSTEM_JQ),
        Message(
            role=Role.User,
            content=user(test=test, schema=schema),
        ),
    ]
    for _ in range(iterations):
        response = model.chat(messages=prompt)
        responses_jq = re.findall(r"<jq>(.*?)</jq>", response.text, re.DOTALL)
        responses_jq = [r.strip() for r in responses_jq if r.strip()]
        results = list()
        errors = list()
        for response_jq in responses_jq:
            try:
                outputs = JqExecutionEngine.execute(response_jq, dataset)
            except Exception as e:
                errors.append(
                    f"❌ Error executing jq expression '{response_jq.replace('\n', '\\n')}': {e}"
                )
                continue
            result["candidates"][response_jq] = outputs
            if not compare(
                outputs, test["output"], order="ORDER" in test["query"].upper()
            ):
                errors.append(
                    f"❌ Mismatch for jq expression '{response_jq.replace('\n', '\\n')}'. "
                    f"Got {promptify(outputs)}, expected {promptify(test['output'])}."
                )
                continue
            results.append(response_jq)
        if results:
            result["kind"] = "success"
            result["jq"] = results
            break
        prompt.append(Message(role=Role.Assistant, content=response.text))
        prompt.append(
            Message(
                role=Role.User,
                content=f"Errors:\n\n{'\n'.join(errors)}\n\nPlease try again.",
            )
        )
    return result


def execute(query: str, database: sqlite3.Connection) -> JsonValue:
    cursor = database.cursor()
    cursor.execute(query)
    columns = [column[0] for column in cursor.description]
    results = cursor.fetchall()
    if len(results) == 0:
        return None
    if len(results) == 1 and len(results[0]) == 1:
        return results[0][0]
    if all(len(row) == 1 for row in results):
        return [row[0] for row in results]
    result = [dict(zip(columns, row)) for row in results]
    if len(result) == 1:
        return result[0]
    return result


def answers(tests: list[dict[str, Any]], database: Path) -> None:
    connection = sqlite3.connect(database)
    for test in tests:
        try:
            test["output"] = execute(test["query"], connection)
        except Exception:
            test["output"] = None


if __name__ == "__main__":
    root = paths.spider

    data_tests = root / "0_raw" / "test.json"
    databases_sql = root / "0_raw" / "test_database"
    databases_json = root / "2_jsonified"
    database_names = [db.stem for db in databases_json.glob("*.json")]

    # fmt: off
    parser = ArgumentParser()
    parser.add_argument("-d", "--dataset", type=str, choices=database_names, required=True)
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument("-m", "--model", type=str, default="openai/gpt-4.1")
    parser.add_argument("-c", "--cache", type=str, default=None)
    parser.add_argument("-f", "--force", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    # fmt: on

    console = Console(quiet=not args.verbose)

    # load model
    if args.cache == "auto":
        args.cache = (
            (paths.reports.parent / "runs" / "caches")
            / "convert-spider"
            / f"{args.model.replace('/', '--')}"
            / f"{args.dataset}.json"
        )
    model_spec = args.model
    model_cache = JsonCache(args.cache) if args.cache else None
    model = ChatModel(model=model_spec, cache=model_cache)
    console.print(f"➡️  Using model {args.model} with cache {args.cache}.")

    # load tests
    tests = json.load(data_tests.open(encoding="utf-8"))
    tests = [t for t in tests if t["db_id"] == args.dataset]
    console.print(f"➡️  Loaded {len(tests)} tests from {args.dataset}.")

    # prepare SQL
    answers(tests, databases_sql / args.dataset / f"{args.dataset}.sqlite")
    console.print(
        f"➡️  Found {len([t for t in tests if t.get('output') is not None])} answers."
    )

    # load database
    database = json.load(
        (databases_json / f"{args.dataset}.json").open(encoding="utf-8")
    )

    if args.output is None:
        args.output = root / "3_converted" / f"{args.dataset}.json"
        args.output.parent.mkdir(parents=True, exist_ok=True)

    # initialize results
    converted = list()
    if args.output.exists() and not args.force:
        with open(args.output, encoding="utf-8") as f:
            converted.extend(json.load(f))

    progress = tqdm(total=len(tests), initial=len(converted), disable=not args.verbose)
    for test in tests:
        if any(c["question"] == test["question"] for c in converted):
            progress.update(1)
            continue
        test_result = {
            "jq": convert_jq(
                test=test,
                schema=database["schema"],
                dataset=database["data"],
                model=model,
                # console=console,
            )
        }
        if test_result["jq"]["kind"] == "failure":
            test_result["python"] = convert_python(
                test=test,
                schema=database["schema"],
                dataset=database["data"],
                model=model,
                # console=console,
            )
        converted.append(
            {
                "db_id": test["db_id"],
                "question": test["question"],
                "query": test["query"],
                "query_output": test["output"],
                "converted": test_result,
            }
        )
        progress.update(1)
        if args.debug:
            break

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(json.dumps(converted, indent=2))
