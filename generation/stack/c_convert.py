import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Literal, Optional, Union

from jsonargparse import ArgumentParser
from pydantic import BaseModel, Field, JsonValue
from rich.console import Console
from tqdm import tqdm

from experiments.inference.settings import Settings
from experiments.llm import (
    Agent,
    ChatModel,
    ChatRequest,
    Environment,
    Function,
    JsonCache,
    StringProperty,
    Tool,
    ToolResult,
)
from experiments.paths import paths
from generation.stack.b_extract import ExtractedBenchmark, ExtractedData
from jqbench.execution import JqExecutionEngine

data_in = Settings.data / "b_extract" / "extracted.json"
data_out = Settings.data / "c_convert" / "converted.json"

cache_root = (paths.reports.parent / "runs" / "caches") / "convert"


class ConversionTest(BaseModel):
    name: str
    input: JsonValue
    output: JsonValue


class ConversionEnvironment(BaseModel):
    tests: list[ConversionTest] = Field(default_factory=list)
    candidates: list[str] = Field(default_factory=list)


class ConversionResponse(BaseModel):
    message: str
    candidates: list[str] = Field(default_factory=list)


class ConversionTestResult(BaseModel):
    test: str
    outcome: Literal["Success", "Partial success", "Failure", "Error"]


class ConvertedExecution(BaseModel):
    expression: str
    results: list[ConversionTestResult]


class ConvertedBenchmark(BaseModel):
    identifier: int
    utterance: Optional[str] = None
    environment: ConversionEnvironment
    executions: list[ConvertedExecution]
    history: list[dict] = Field(default_factory=list)


class JsonPathEnvironment(Environment):
    def __init__(self):
        super().__init__(None)
        self.tests: dict[str, list[dict[str, Any]]] = dict()
        self.candidates = list()

    def add_test(self, name: str, i: Any, o: Any) -> None:
        self.tests[name] = {"input": i, "output": o}

    def add_candidate(self, expression: str) -> None:
        if expression not in self.candidates:
            self.candidates.append(expression)


class AddTestTool(Tool[JsonPathEnvironment]):
    def definition(self) -> Function:
        return Function(
            name="add_test",
            description="Add or update a test case for a jq expression.",
            parameters={
                "name": StringProperty(description="A unique name for the test case."),
                "input": StringProperty(
                    description="A serialized string representation of the input JSON."
                ),
                "output": StringProperty(
                    description=(
                        "A serialized string representation of the expected output JSON, following Python's `jq.all(expression, data)` output format."
                    )
                ),
            },
        )

    def execute(self, arguments, environment, *args, **kwargs):
        a_name = arguments.get("name", None)
        a_input = arguments.get("input", None)
        a_output = arguments.get("output", None)
        errors = list()
        try:
            a_input = json.loads(a_input)
        except json.JSONDecodeError as e:
            errors.append(f"Error decoding input JSON: {e}")
        try:
            a_output = json.loads(a_output)
        except json.JSONDecodeError as e:
            errors.append(f"Error decoding output JSON: {e}")
        if not isinstance(a_output, list):
            errors.append(
                "Output JSON must be a list (following `jq.all()` output format)."
            )
        if errors:
            return ToolResult(values={"errors": errors})
        update = "updated" if a_name in environment.tests else "added"
        environment.add_test(a_name, a_input, a_output)
        return ToolResult(values={"success": True, "update": update})

    def compile(self, result):
        if errors := result.values.get("errors"):
            result = "Test not added.\n"
            for error in errors:
                result += f"- {error}\n"
            return result
        if not result.values.get("success", False) or not result.values.get("update"):
            return "Test not added."
        return f"Test case {result.values.get('update')} successfully."


class RunTestTool(Tool[JsonPathEnvironment]):
    def definition(self) -> Function:
        return Function(
            name="run_tests",
            description="Execute a jq expression on the tests.",
            parameters={
                "jq": StringProperty(
                    description=(
                        "The jq expression `e` to evaluate on the input `i` as `i | jq e` or `jq.all(e, i)`."
                    )
                )
            },
        )

    def execute(
        self,
        arguments: dict[str, Any],
        environment: JsonPathEnvironment,
        *args,
        **kwargs,
    ) -> ToolResult:
        try:
            JqExecutionEngine.compile((expression := arguments.get("jq", None)))
        except Exception as e:
            return ToolResult(
                values={"error": f"Error compiling jq expression '{expression}': {e}"}
            )
        environment.add_candidate(expression)
        result = dict()
        for name, test in environment.tests.items():
            try:
                values = JqExecutionEngine.execute(expression, test["input"])
                value_dump = json.dumps(values, sort_keys=True)
                if value_dump == json.dumps(test["output"], sort_keys=True):
                    result[name] = "Success"
                    continue
                if value_dump == json.dumps([test["output"]], sort_keys=True):
                    result[name] = (
                        "Partial success: result has correct value but is wrapped in a list."
                    )
                    continue
                result[name] = (
                    f"Failure: output `{values}` does not match the expected result ({test['output']})."
                )
            except Exception as e:
                result[name] = f"Error: {e}"
        return ToolResult(values=result)

    def compile(self, result: ToolResult) -> str:
        return json.dumps(result.values, indent=2)


def format_question(
    expressions: list[str],
    utterance: str,
    data: list,
) -> str:
    if isinstance(expressions, str):
        expressions = [expressions]
    formatted = f"""
Task: "{utterance}"

The following commands potentially achieve the task:
{"\n".join(f"- `{e}`" for e in expressions)}
You can (and are encouraged to) change them before running the tests.
                 """.strip()

    examples = list()
    inputs = list()
    for element in data:
        if not isinstance(element, ExtractedData):
            continue
        i = element.input
        o = element.output
        if i is None:
            continue
        if o is None:
            inputs.append(f"- `{json.dumps(i)}`")
        else:
            examples.append(f"- `{json.dumps(i)}` -> `{json.dumps(o)}`")

    if len(examples) > 0:
        formatted += "\n\n"
        formatted += (
            "The following (input -> output) examples can serve as inspiration to create test cases. "
            "Note that these are not guaranteed to be correct.\n"
        )
        formatted += "\n".join(examples)
        formatted += "\nIf applicable, make sure that objects in test cases include all required fields."
    if len(inputs) > 0:
        formatted += "\n\n"
        formatted += (
            "The following inputs can serve as inspiration to create test cases. "
            "Note that these are not guaranteed to be correct.\n"
        )
        formatted += "\n".join(inputs)
        formatted += "\nIf applicable, make sure that objects in test cases include all required fields."
    return formatted


system = """
# Instructions

You are an expert at jq.
Your goal is to create and test jq expressions that solve the given task.

You can add or update test cases by using the `add_test` tool.
You can execute an expression on all test cases using the `run_tests` tool.

# Testing

- Make sure to add between four and six test cases that cover different aspects of the task.
- Make sure to run the tests before making a final suggestion.
- If an expression is correct but the test is incorrect, you need to update the test case to match the correct output.
  - If all tests achieve "Partial success", you do not need to update the tests.
  - If all tests achieve "Success" or all tests achieve "Partial success", you can suggest the expression as a candidate solution.
- Make sure that new test cases follow the same JSON schema as the provided examples.
  - If the input contains an object, make sure that new objects follow the same structure and include all required fields.
  - If the input looks like it will be consistent, you should not test for edge cases.
- Unless explicitly part of the task, do not add tests for:
  - Empty, null, missing or invalid inputs.
  - Special characters or escaping.

# Output format

In your final response, include all candidate jq expressions that solve the task.
Each expression is wrapped in triple backticks without newlines, for example, ```{b: .a + 1}```.

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


def convert(
    original: ExtractedBenchmark,
    iterations: int = 8,
    verbose: bool = True,
) -> ConvertedBenchmark:
    """Convert a raw expression to jq expressions."""
    environment = JsonPathEnvironment()
    prompt = system
    agent = Agent(
        model=model,
        system=prompt,
        tools=[AddTestTool(), RunTestTool()],
        request=ChatRequest(max_tokens=16000),
        console=Console(quiet=not verbose),
        iterations=iterations,
    )
    response = agent.run(
        format_question(
            list(set(e.jq for e in original.expressions)),
            original.task.low,
            data=original.data,
        ),
        environment=environment,
    )
    response_candidates: list[str] = [
        e.strip() for e in re.findall(r"```([^`]+)```", response.message or "")
    ]
    execution_environment = JsonPathEnvironment()
    execution_tool = RunTestTool()
    execution_environment.tests = environment.tests
    executions = list()
    for candidate in set(environment.candidates + response_candidates):
        candidate_result = execution_tool.execute(
            {"jq": candidate}, execution_environment
        ).values
        if "error" in candidate_result:
            continue
        executions.append(
            ConvertedExecution(
                expression=candidate,
                results=[
                    ConversionTestResult(
                        test=test_name,
                        outcome=test_value.split(":")[0],
                    )
                    for test_name, test_value in candidate_result.items()
                ],
            )
        )
    return ConvertedBenchmark(
        identifier=original.identifier,
        utterance=original.task.low,
        environment=ConversionEnvironment(
            tests=[
                ConversionTest(
                    name=name,
                    input=test["input"],
                    output=test["output"],
                )
                for name, test in environment.tests.items()
            ],
            candidates=environment.candidates,
        ),
        history=[m.prepare() for m in environment.conversation],
        executions=executions,
    )


if __name__ == "__main__":
    # fmt: off
    parser = ArgumentParser()
    parser.add_argument("--skip", type=int, default=0)
    parser.add_argument("--take", type=int, default=0)
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--iterations", type=int, default=8)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--debug", type=Union[int, str, bool], default=None)
    parser.add_argument("--force", action="store_true", default=False)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--failures", type=str, default=None)
    args = parser.parse_args()
    # fmt: on

    # resolve output path
    if args.output:
        data_out = Settings.data / "c_convert" / args.output
    else:
        data_out = (
            Settings.data
            / "c_convert"
            / f"converted-{args.model.replace('/', '--')}.json"
        )
    data_out.parent.mkdir(parents=True, exist_ok=True)

    debugging = args.debug not in {None, False, 0, "0", "false", "False"}

    # load model
    model_spec = args.model
    model_cache = JsonCache(
        cache_root / f"convert-{args.model.replace('/', '--')}.json"
    )
    model = ChatModel(model=model_spec, cache=model_cache)

    # load done
    if data_out.exists():
        done = json.load(open(data_out, "r", encoding="utf-8"))
        done = [ConvertedBenchmark.model_validate(d) for d in done]
    else:
        done = list()
    if args.force:
        really = input(
            f"⚠️  Are you sure you want to re-process {len(done)} done items? (y/n) "
        )
        if really.lower() != "y":
            exit(0)
        done = list()
    print(f"⚡  Loaded {len(done)} done items.")

    # load data
    data = json.load(open(data_in, encoding="utf-8"))
    data: list[ExtractedBenchmark] = [
        ExtractedBenchmark.model_validate(d) for d in data if len(d) > 1
    ]
    data.sort(key=lambda p: p.identifier or 0)
    # filter by failures
    if args.failures:
        failures = json.load(open(args.failures, "r", encoding="utf-8"))
        failure_ids = {d["identifier"] for d in failures}
        data = [p for p in data if p.identifier in failure_ids]
        print(f"⚡  Filtered to {len(data)} items from failures file.")
    if debugging:
        data = [p for p in data if p.identifier == int(args.debug)]
        done = list()
    else:
        data = [p for p in data if not any(p.identifier == t.identifier for t in done)]
        if args.skip:
            data = data[args.skip :]
        if args.take:
            data = data[: args.take]
    print(f"⚡  Loaded {len(data)} todo items.")

    def save():
        d = json.dumps(
            [
                b.model_dump(mode="json")
                for b in sorted(done, key=lambda p: p.identifier or 0)
            ],
            indent=2,
        )
        if debugging:
            print(
                f"⚡  Saving debug output to {data_out.with_stem(f'{data_out.stem}.debug')}"
            )
            with open(
                data_out.with_stem(f"{data_out.stem}.debug"), "w", encoding="utf-8"
            ) as f:
                f.write(d)
            return
        with open(data_out, "w", encoding="utf-8") as f:
            f.write(d)

    if args.workers <= 1:
        for element in tqdm(data, disable=debugging):
            result = convert(element, args.iterations, args.debug is not None)
            done.append(result)
            if len(done) % 10 == 0:
                save()
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(convert, e, args.iterations, args.debug is not None): e
                for e in data
            }
            for future in tqdm(
                as_completed(futures), total=len(futures), disable=debugging
            ):
                try:
                    result = future.result()
                    if result is None:
                        continue
                    done.append(result)
                    if len(done) % 10 == 0:
                        save()
                except Exception as e:
                    print(f"❌  Error processing {futures[future].identifier}: {e}")

    save()
