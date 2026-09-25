import json
from typing import Any, Optional, Union

from pydantic import JsonValue
from rich.table import Table

from experiments.inference.benchmark import (
    Input,
    InputOutput,
    Problem,
    Schema,
    SolutionMetadata,
)
from experiments.inference.settings import Settings, Verbosity
from experiments.inference.solvers.solver import Program, Solver
from experiments.inference.utilities import render_message
from experiments.llm import (
    Agent,
    AgentResult,
    ChatModel,
    ChatRequest,
    ChatResponseMessage,
    Environment,
    Function,
    Message,
    Role,
    StringProperty,
    Tool,
    ToolResult,
)
from jqbench.execution import ProgramKind, PythonExecutionEngine, compiles
from jqbench.metrics import ValueMatch, equals


class PythonSampler(Solver):
    """Sample Python functions at higher temperatures."""

    def __init__(self):
        pass

    def solve(
        self, problem: Problem, model: ChatModel, request: ChatRequest
    ) -> tuple[list[Program], Optional[SolutionMetadata]]:
        prompt = _prompt(problem)
        result = model.chat(prompt, request)
        queries = [_extract(choice.message.content) for choice in result.choices]
        if Settings.verbosity == Verbosity.Debug:
            table = Table(show_lines=True)
            table.add_column("Python", vertical="middle")
            table.add_column("🤖", vertical="middle")
            for choice, query in zip(result.choices, queries):
                table.add_row(query, choice.message.content)
            Settings.console.print("> 🤖")
            Settings.console.print(table)
        return [
            Program(kind=ProgramKind.Python, code=query) for query in queries
        ], SolutionMetadata(usage=[result.usage])

    @property
    def parameters(self) -> dict[str, Union[str, int]]:
        return dict()


class PythonAgent(Solver):
    def __init__(self, implicit: bool = False, iterations: int = 8):
        self.iterations = iterations
        self.implicit = implicit
        self.tools = list()
        if not implicit:
            self.tools = [PythonCodeTool()]

    def solve(
        self, problem: Problem, model: ChatModel, request: ChatRequest
    ) -> tuple[list[Program], Optional[SolutionMetadata]]:
        tools = (
            "\n"
            + "\n".join(
                f"- {tool.definition().name}: {tool.instruction}" for tool in self.tools
            )
            if len(self.tools) > 0
            else " <none>"
        )
        agent = Agent(
            model=model,
            system=SYSTEM_AGENT.format(tools=tools).strip(),
            tools=self.tools,
            request=request.model_copy(update={"max_tokens": 2048}),
            iterations=self.iterations,
            console=Settings.console,
        )
        agent_environment = PythonEnvironment()
        agent_result: AgentResult = agent.run(_user(problem), agent_environment)
        agent_queries = PythonAgent.get_queries(agent_environment.conversation)
        metadata = SolutionMetadata(
            usage=agent_result.usage, tools=agent_result.tools, feedback=list()
        )
        if self.implicit:
            while True:
                if len(agent_queries) == 0:
                    break
                feedback = PythonAgent.get_feedback(problem, agent_queries[-1])
                metadata.feedback.append(feedback)
                if isinstance(feedback, bool) and feedback is True:
                    break
                agent_environment.conversation.append(
                    Message(
                        role=Role.User,
                        content=(
                            f"{feedback}\n\nPlease provide a corrected expression."
                        ),
                    )
                )
                next_result = agent.resume(agent_environment)
                metadata.usage.extend(next_result.usage)
                metadata.tools.extend(next_result.tools)
                if len(next_result.usage) == 0:
                    break
                agent_result = next_result
                agent_queries = PythonAgent.get_queries(agent_environment.conversation)
        if len(agent_queries) == 0:
            return list(), metadata
        return [Program(kind=ProgramKind.Python, code=agent_queries[-1])], metadata

    @staticmethod
    def get_queries(conversation: list[Message, ChatResponseMessage]) -> list[str]:
        content = list()
        for m in conversation:
            if not isinstance(m, ChatResponseMessage):
                continue
            if m.content and not m.tool_calls:
                content.append(m.content)
                continue
            for tool_call in m.tool_calls:
                if tool_call.function.name == "test_function":
                    args = json.loads(tool_call.function.arguments)
                    content.append(f"<python>{args.get('f', '')}</python>")
        queries = [_extract(m) for m in content]
        return [q for q in queries if q]

    @staticmethod
    def get_feedback(problem: Problem, query: str) -> Union[str, bool]:
        if not compiles(Program(kind=ProgramKind.Python, code=query)):
            return f"Error: Unable to compile query: {query}"
        # try to execute
        if isinstance(problem.input, (Input, InputOutput)):
            outputs: list[JsonValue] = list()
            for i in problem.input.inputs:
                try:
                    outputs.append(PythonExecutionEngine.execute(query, i))
                except Exception as e:
                    return f"Error: Unable to evaluate expression `{query}` on input `{json.dumps(i)}`: {e}"
            if isinstance(problem.input, Input):
                return True
            if isinstance(problem.input, InputOutput):
                errors = list()
                for o, e in zip(outputs, problem.input.outputs):
                    if equals(e, o) == ValueMatch.No:
                        errors.append(
                            f"Error: Expected output `{json.dumps(e)}`, but got `{json.dumps(o)}`."
                        )
                if len(errors) == 0:
                    return True
                return "\n".join(errors)
        return True

    @property
    def parameters(self) -> dict[str, Union[str, int]]:
        return {
            "iterations": self.iterations,
            "implicit": self.implicit,
        }

    @property
    def name(self) -> str:
        name = "PythonAgent"
        if self.implicit:
            name += "+Implicit"
        return name


class PythonEnvironment(Environment):
    pass


class PythonCodeTool(Tool[PythonEnvironment]):
    """Execute Python code on given inputs."""

    instruction = "Before showing a function to the user, use this tool to test the function on the provided input (if any) or on custom input."

    def definition(self) -> Function:
        return Function(
            name="test_function",
            description=(
                "Execute a Python function `f` on a given input `i` and print the result."
            ),
            parameters={
                "f": StringProperty(description="The function to evaluate."),
                "i": StringProperty(description="The serialized input JSON object"),
            },
        )

    def execute(
        self,
        arguments: dict[str, Any],
        environment: PythonEnvironment,
        identifier: str = None,
    ) -> ToolResult:
        # try to parse the values
        values = dict()
        try:
            compiled = PythonExecutionEngine.compile(arguments.get("f", None))
        except Exception as e:
            values["CompileError"] = f"Error compiling Python function: {e}"
        try:
            value = json.loads(arguments.get("i", "null"))
        except Exception as e:
            values["InputError"] = f"Error parsing input JSON: {e}"
        if len(values) == 0:
            try:
                values["Result"] = PythonExecutionEngine.execute_compiled(
                    compiled, value
                )
            except Exception as e:
                values["ExecutionError"] = f"Error executing Python function: {e}"
        return ToolResult(values=values)

    def compile(self, result: ToolResult) -> str:
        return "\n".join(f"**{k}**: `{v}`" for k, v in result.values.items())


def _user(problem: Problem) -> str:
    prompt = f"Task: {problem.utterance}"
    if (i := problem.input) is not None:
        prompt += "\n\n"
        match i:
            case Input():
                prompt += "The function should execute on the following JSON:\n"
                for value in i.inputs:
                    prompt += f"- `{json.dumps(value)}`\n"
            case InputOutput():
                prompt += "The function should match the following (input JSON -> output JSON) examples:\n"
                for x, y in zip(i.inputs, i.outputs):
                    prompt += f"- `{json.dumps(x)}` -> `{json.dumps(y)}`\n"
            case Schema():
                prompt += (
                    "The function should execute on JSON that follows the following schema:\n"
                    "```json\n"
                    "{schema}\n"
                    "```\n\n"
                    "The output format is either a single value or a list of records that follows the same schema."
                ).format(schema=json.dumps(i.jsonschema, indent=2))
    return prompt


def _prompt(problem: Problem) -> list[Message]:
    global SYSTEM
    prompt = [
        Message(role=Role.System, content=SYSTEM),
        Message(role=Role.User, content=_user(problem)),
    ]
    if Settings.verbosity == Verbosity.Debug:
        for message in prompt:
            render_message(message)
    return prompt


def _extract(answer: str) -> str:
    if "<python>" in answer and "</python>" in answer:
        start = answer.find("<python>") + 8
        end = answer.find("</python>", start)
        return answer[start:end].strip()
    if "```python" in answer and "```" in answer:
        start = answer.find("```python") + 9
        end = answer.find("```", start)
        return answer[start:end].strip()
    return answer.strip()


def _increase_indent(block: str) -> str:
    lines = block.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#"):
            lines[i] = f"#{line}"
    return "\n".join(lines)


SYSTEM = """
You are a helpful assistant that helps users write Python functions that transform JSON.
Wrap the suggested Python function in <python></python> tags without surrounding quotes.

# Python Details

The Python function `f` will be executed with the provided input `i` as `f(i)`.
Note that you should not provide this code: you should only provide the Python function itself.

Some examples:

<python>
def f(i):
    return i["foo"]
</python>
is executed as `f({"foo": 1}) == 1`.

<python>
def f(i):
    return {"b": i["a"] + 1}
</python>
is executed as `f({"a": 1}) == {"b": 2}`.

<python>
def f(i):
    return i[0]
</python>
is executed as `f([{"a": 1}, {"b": 2}]) == {"a": 1}`.

<python>
def f(i):
    return [x[0] for x in i]
</python>
is executed as `f([[1, 2], [3, 4]]) == [1, 3]`.
"""

SYSTEM_AGENT = """
You are a helpful assistant that helps users write Python functions that transform JSON.
In your final answer, wrap the suggested Python function in <python></python> tags without surrounding quotes.

# Tools

It is highly recommended to use the tools at your disposal:{tools}
Make sure to use at least one of these tools.

# Python Details

The Python function `f` will be executed with the provided input `i` as `f(i)`.
Note that you should not provide this code: you should only provide the Python function itself.

Some examples:

<python>
def f(i):
    return i["foo"]
</python>
is executed as `f({{"foo": 1}}) == 1`.

<python>
def f(i):
    return {{"b": i["a"] + 1}}
</python>
is executed as `f({{"a": 1}}) == {{"b": 2}}`.

<python>
def f(i):
    return i[0]
</python>
is executed as `f([{{"a": 1}}, {{"b": 2}}]) == {{"a": 1}}`.

<python>
def f(i):
    return [x[0] for x in i]
</python>
is executed as `f([[1, 2], [3, 4]]) == [1, 3]`.
"""
