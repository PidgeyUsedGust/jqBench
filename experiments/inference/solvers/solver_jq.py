import json
import re
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
    ArrayProperty,
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
from experiments.paths import paths
from jqbench.execution import JqExecutionEngine, ProgramKind
from jqbench.metrics import ValueMatch, equals


class JqSampler(Solver):
    """Sample jq expressions at higher temperatures."""

    def __init__(self, documentation: bool = False):
        self.documentation = documentation

    def solve(
        self, problem: Problem, model: ChatModel, request: ChatRequest
    ) -> tuple[list[Program], Optional[SolutionMetadata]]:
        prompt = _prompt(problem, self.documentation)
        result = model.chat(prompt, request)
        queries = [_extract(choice.message.content) for choice in result.choices]
        if Settings.verbosity == Verbosity.Debug:
            table = Table(show_lines=True)
            table.add_column("jq", vertical="middle")
            table.add_column("🤖", vertical="middle")
            for choice, query in zip(result.choices, queries):
                table.add_row(query, choice.message.content)
            Settings.console.print("> 🤖")
            Settings.console.print(table)
        return (
            [Program(kind=ProgramKind.Jq, code=query) for query in queries],
            SolutionMetadata(usage=[result.usage]),
        )

    @property
    def parameters(self) -> dict[str, Union[str, int]]:
        return {"documentation": self.documentation}


class JqAgent(Solver):
    def __init__(
        self,
        force: bool = False,
        implicit: bool = False,
        documentation: bool = False,
        iterations: int = 8,
    ):
        self.iterations = iterations
        self.force = force
        self.implicit = implicit
        self.documentation = documentation
        self.tools = list()
        if not self.implicit:
            self.tools.append(JqCodeTool())
        if documentation:
            self.tools.append(JqDocumentationSearchTool())
            self.tools.append(JqDocumentationSectionTool())

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
        if self.force:
            agent.request.tool_choice = "required"
            agent.tool_callback = lambda _result, _environment: setattr(
                agent.request, "tool_choice", "auto"
            )
        agent_environment = JqEnvironment()
        agent_result: AgentResult = agent.run(_user(problem), agent_environment)
        agent_queries = JqAgent.get_queries(agent_environment.conversation)
        metadata = SolutionMetadata(
            usage=agent_result.usage, tools=agent_result.tools, feedback=list()
        )
        if self.implicit:
            while True:
                if len(agent_queries) == 0:
                    break
                feedback = JqAgent.get_feedback(problem, agent_queries[-1])
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
                agent_queries = JqAgent.get_queries(agent_environment.conversation)
        if len(agent_queries) == 0:
            return list(), metadata
        return [Program(kind=ProgramKind.Jq, code=agent_queries[-1])], metadata

    @property
    def parameters(self) -> dict[str, Union[str, int]]:
        return {
            "documentation": self.documentation,
            "iterations": self.iterations,
            "implicit": self.implicit,
        }

    @property
    def name(self) -> str:
        name = "JqAgent"
        if self.documentation:
            name += "+Documentation"
        if self.implicit:
            name += "+Implicit"
        if self.iterations != 8:
            name += f"+{self.iterations}Iterations"
        return name

    @staticmethod
    def get_queries(conversation: list[Message, ChatResponseMessage]) -> list[str]:
        content = list()
        for m in conversation:
            if not isinstance(m, ChatResponseMessage):
                continue
            if m.content:
                content.append(m.content)
            for tool_call in m.tool_calls or list():
                if tool_call.function.name == "test_expression":
                    args = json.loads(tool_call.function.arguments)
                    content.append(f"<jq>{args.get('e', '')}</jq>")
        queries = [_extract(m) for m in content]
        return [q for q in queries if q]

    @staticmethod
    def get_feedback(problem: Problem, query: str) -> Union[str, bool]:
        # try to compile
        try:
            JqExecutionEngine.compile(query)
        except Exception as e:
            return f"Error: Unable to compile query: {e}"
        # try to execute
        if isinstance(problem.input, (Input, InputOutput)):
            outputs: list[JsonValue] = list()
            for i in problem.input.inputs:
                try:
                    outputs.append(JqExecutionEngine.execute(query, i))
                except TimeoutError:
                    return f"Error: The expression `{query}` took too long to evaluate on input `{json.dumps(i)}` and is likely non-terminating."
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
        if isinstance(problem.input, Schema):
            try:
                JqExecutionEngine.execute(query, problem.input.dataset)
            except TimeoutError:
                return f"Error: The expression `{query}` took too long to evaluate on the dataset and is likely non-terminating."
            except Exception as e:
                return f"Error: Unable to evaluate expression `{query}` on the dataset: {e}"
        return True


class JqEnvironment(Environment):
    pass


class JqCodeTool(Tool[JqEnvironment]):
    """Execute JQ on given inputs."""

    instruction = "Before showing an expression to the user, use this tool to test the expression on the provided input (if any) or on custom input."

    def definition(self) -> Function:
        return Function(
            name="test_expression",
            description=(
                "Execute a jq expression `e` on a given input `i` using the Python bindings for jq as `jq.all(e, i)` and print the result."
            ),
            parameters={
                "e": StringProperty(description="The expression to evaluate."),
                "i": StringProperty(description="The serialized input JSON object"),
            },
        )

    def execute(
        self,
        arguments: dict[str, Any],
        environment: JqEnvironment,
        identifier: str = None,
    ) -> ToolResult:
        # try to parse the values
        values = dict()
        try:
            JqExecutionEngine.compile((query := arguments.get("e", None)))
        except Exception as e:
            values["CompileError"] = f"Error compiling jq expression: {e}"
        try:
            value = json.loads(arguments.get("i", "null"))
        except Exception as e:
            values["InputError"] = f"Error parsing input JSON: {e}"
        if len(values) == 0:
            try:
                values["Result"] = JqExecutionEngine.execute(query, value)
            except TimeoutError:
                values["ExecutionError"] = (
                    f"Error executing jq expression: timeout after {JqExecutionEngine.timeout} seconds."
                )
            except Exception as e:
                values["ExecutionError"] = f"Error executing jq expression: {e}"
        return ToolResult(values=values)

    def compile(self, result: ToolResult) -> str:
        return "\n".join(f"**{k}**: `{v}`" for k, v in result.values.items())


class JqDocumentationSearchTool(Tool[JqEnvironment]):
    instruction = (
        "Search for operators and built-ins in the documentation using keyword search."
    )

    def __init__(self):
        super().__init__()
        self._index: list[str] = None

    def definition(self) -> Function:
        return Function(
            name="search_documentation",
            description=(
                "Searches for built-in function and operators whose description contains either of the keywords. "
                "For each result, prints (1) the name of the section in the documentation, (2) the signature, and (3) a short description."
            ),
            parameters={
                "keywords": ArrayProperty(
                    description="A list of keywords to search for.",
                    items=StringProperty(
                        description='An operator, built-in, or keyword to search for. Examples keywords are "map_values" (built-in), "try" (keyword), or "math" (keyword).'
                    ),
                ),
            },
        )

    def execute(
        self,
        arguments: dict[str, Any],
        environment: JqEnvironment,
        identifier: str = None,
    ) -> ToolResult:
        keywords = [k.lower() for k in arguments.get("keywords", list())]
        lines = list()
        for line in self.index:
            for keyword in keywords:
                if keyword in line and line not in lines:
                    lines.append(line)
        return ToolResult(values={"lines": lines})

    def compile(self, result: ToolResult) -> str:
        return "\n".join(f"- {line}" for line in result.values["lines"])

    @property
    def index(self) -> list[str]:
        if self._index is None:
            with open(paths.docs / "index.md", encoding="utf-8") as f:
                self._index = list()
                for line in f.read().splitlines():
                    if line.startswith("- "):
                        self._index.append(line[2:])
        return self._index


class JqDocumentationSectionTool(Tool[JqEnvironment]):
    instruction = "Print sections of the documentation."

    def __init__(self):
        super().__init__()
        self._index: dict[str, str] = None
        self._names: dict[str, str] = None

    def definition(self) -> Function:
        return Function(
            name="print_documentation",
            description=(
                "Prints specific sections of the documentation for built-in functions, operators and control flow statements. "
                "Each section contains the signature, a description, and some examples on how to use the function/operator/control flow statement. "
                "Use the `search_documentation` tool to find the exact name of the section."
            ),
            parameters={
                "sections": ArrayProperty(
                    description="A list of sections to print.",
                    items=StringProperty(
                        description='A section of the documentation to print. Examples are "map_values" and ".." or "recursive_descent" (pointing to the same section).'
                    ),
                ),
            },
        )

    def execute(
        self,
        arguments: dict[str, Any],
        environment: JqEnvironment,
        identifier: str = None,
    ) -> ToolResult:
        sections = [s.lower() for s in arguments.get("sections", list())]
        found = list()
        missing = list()
        for section in sections:
            if (f := self.find(section)) is not None:
                found.append(f)
            else:
                missing.append(section)
        return ToolResult(values={"sections": found, "missing": missing})

    def compile(self, result: ToolResult) -> str:
        compiled = ""
        if len(missing := result.values.get("missing", list())) > 0:
            compiled += f"⚠️ The following sections were not found in the documentation: {', '.join(missing)}\n\n"
        if len(sections := result.values.get("sections", list())) > 0:
            compiled += "\n\n".join(sections)
        return compiled

    def find(self, section: str) -> Optional[str]:
        if self._index is None:
            self._index = dict()
            self._names = dict()
            for file in (paths.docs / "manual").glob("*.md"):
                data = file.read_text(encoding="utf-8").strip()
                if data.startswith("# `"):
                    first = data.splitlines()[0]
                    header = first[3 : first.find("`", 3)].strip().lower()
                    header = header[0 : header.find("(")].strip()
                    self._names[header] = file.stem
                self._index[file.stem] = _increase_indent(data)
        if section in self._index:
            return self._index[section]
        if section in self._names and self._names[section] in self._index:
            return self._index[self._names[section]]
        return None


def _user(problem: Problem) -> str:
    prompt = ""
    if problem.utterance:
        prompt = f"Task: {problem.utterance}"
    if (i := problem.input) is not None:
        prompt += "\n\n"
        match i:
            case Input():
                prompt += "The query should execute on the following JSON:\n"
                for value in i.inputs:
                    prompt += f"- `{json.dumps(value)}`\n"
            case InputOutput():
                prompt += "The query should match the following (input JSON -> output JSON) examples:\n"
                for x, y in zip(i.inputs, i.outputs):
                    prompt += f"- `{json.dumps(x)}` -> `{json.dumps(y)}`\n"
            case Schema():
                prompt += (
                    "The query should execute on JSON that follows the following schema:\n"
                    "```json\n"
                    "{schema}\n"
                    "```\n\n"
                    "The output format is either a single value or a list of records that follows the same schema."
                ).format(schema=json.dumps(i.jsonschema, indent=2))
    return prompt.strip()


def _system(documentation: bool = False) -> str:
    global DOCUMENTATION, SYSTEM
    if documentation:
        if DOCUMENTATION is None:
            with open(paths.docs / "index.md") as f:
                DOCUMENTATION = f.read()
        return SYSTEM + "\n" + DOCUMENTATION
    return SYSTEM


def _prompt(problem: Problem, documentation: bool) -> list[Message]:
    prompt = [
        Message(role=Role.System, content=_system(documentation)),
        Message(role=Role.User, content=_user(problem)),
    ]
    if Settings.verbosity == Verbosity.Debug:
        for message in prompt:
            render_message(message)
    return prompt


def _extract(answer: str) -> str:
    if "<think>" in answer and "</think>" in answer:
        start = answer.find("<think>") + 7
        end = answer.find("</think>", start)
        answer = answer[: start - 7] + answer[end + 8 :]
    if "<jq>" in answer and "</jq>" in answer:
        queries = re.findall(r"<jq>(.*?)</jq>", answer, flags=re.DOTALL)
        queries = [q.strip() for q in queries if q.strip()]
        if len(queries) > 0:
            return queries[-1]
    if "```jq" in answer and "```" in answer:
        start = answer.find("```jq") + 6
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
You are a helpful assistant that helps users write jq queries.
Wrap the suggested jq query in <jq></jq> tags without surrounding quotes.

# jq Details

The jq will be executed using the Python bindings for jq with the `jq.all(expression, input)` function.
This causes the output to be wrapped in a JSON list, even if the result is a single value.
Note that you should not provide this code: you should only provide the jq expression itself.

Some examples:
- <jq>.foo</jq> is executed as `jq.all(".foo", {"foo": 1}) == [1]`
- <jq>{b: .a + 1}</jq> is executed as `jq.all("{b: .a + 1}", {"a": 1}) == [{"b": 2}]`
- <jq>.[0]</jq> is executed as `jq.all(".[0]", [{"a": 1}, {"b": 2}]) == [{"a": 1}]`
- <jq>map(.[0])</jq> is executed as `jq.all("map(.[0])", [[1, 2], [3, 4]]) == [[1, 3]]`
"""

SYSTEM_AGENT = """
You are a helpful assistant that helps users write jq queries.
In your final answer, wrap the suggested jq query in <jq></jq> tags without surrounding quotes.

# Tools

It is highly recommended to use the tools at your disposal:{tools}
Make sure to use at least one of these tools.

# jq Details

The jq will be executed using the Python bindings for jq with the `jq.all(expression, input)` function.
This causes the output to be wrapped in a JSON list, even if the result is a single value.
Note that you should not provide this code: you should only provide the jq expression itself.

Some examples:
- <jq>.foo</jq> is executed as `jq.all(".foo", {{"foo": 1}}) == [1]`
- <jq>{{b: .a + 1}}</jq> is executed as `jq.all("{{b: .a + 1}}", {{"a": 1}}) == [{{"b": 2}}]`
- <jq>.[0]</jq> is executed as `jq.all(".[0]", [{{"a": 1}}, {{"b": 2}}]) == [{{"a": 1}}]`
- <jq>map(.[0])</jq> is executed as `jq.all("map(.[0])", [[1, 2], [3, 4]]) == [[1, 3]]`
"""

DOCUMENTATION = None
