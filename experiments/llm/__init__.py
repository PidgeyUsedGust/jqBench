"""Request, response, and agent interfaces for cache-first OpenRouter runs."""

import hashlib
import json
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .cache import JsonCache
from .provider import ProviderError, complete
from .provider import RateLimitError as RateLimitError


class Record(BaseModel):
    model_config = ConfigDict(extra="allow")

    def prepare(self):
        return self.model_dump(mode="json", exclude_none=True)


class Role(str, Enum):
    System = "system"
    Developer = "developer"
    User = "user"
    Assistant = "assistant"
    Tool = "tool"
    Function = "function"


class Message(Record):
    role: Role
    content: Any = None
    tool_call_id: str | None = None

    def prepare(self):
        if self.content is None:
            raise ValueError("A request message must have content")
        return super().prepare()


class StringProperty(Record):
    type: str = "string"
    description: str | None = None
    enum: list[str] | None = None
    pattern: str | None = None
    format: str | None = None


class ArrayProperty(Record):
    type: str = "array"
    description: str | None = None
    items: StringProperty | dict | None = None
    minItems: int | None = None
    maxItems: int | None = None


class Function(Record):
    name: str
    description: str | None = None
    parameters: dict[str, StringProperty | ArrayProperty | dict] | None = None

    def prepare(self):
        properties = {
            name: prop.prepare() if isinstance(prop, Record) else prop
            for name, prop in (self.parameters or {}).items()
        }
        function = {
            "name": self.name,
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            },
        }
        if self.description is not None:
            function["description"] = self.description
        return {"type": "function", "function": function}


class ChatRequest(Record):
    n: int | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    max_completion_tokens: int | None = None
    reasoning_effort: str | None = None
    tools: list[Function] | None = None
    tool_choice: Any = None
    response_format: dict | None = None

    def prepare(self):
        request = self.model_dump(mode="json", exclude_none=True, exclude={"tools"})
        if self.tools is not None:
            request["tools"] = [tool.prepare() for tool in self.tools]
        if request.get("n") == 1:
            request.pop("n")
        elif "n" in request:
            raise ValueError("OpenRouter runs currently support n=1 only")
        if "reasoning_effort" in request:
            request["reasoning"] = {"effort": request.pop("reasoning_effort")}
        return request


class Usage(Record):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    completion_tokens_details: dict | None = None


class ToolCallFunction(Record):
    name: str
    arguments: str


class ToolCall(Record):
    id: str
    type: str = "function"
    function: ToolCallFunction


class ChatResponseMessage(Record):
    role: Role
    content: Any = None
    tool_calls: list[ToolCall] = Field(default_factory=list)

    @field_validator("tool_calls", mode="before")
    @classmethod
    def normalize_tool_calls(cls, value):
        return [] if value is None else value

    def prepare(self):
        # Response metadata is retained on the record, not sent as another request.
        message = {"role": self.role.value, "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = [
                call.model_dump(
                    mode="json", exclude_none=True, include={"id", "type", "function"}
                )
                for call in self.tool_calls
            ]
        if "reasoning_details" in (self.model_extra or {}):
            message["reasoning_details"] = self.model_extra["reasoning_details"]
        if "content_blocks" in (self.model_extra or {}):
            message["content_blocks"] = self.model_extra["content_blocks"]
        if "content_layout" in (self.model_extra or {}):
            message["content_layout"] = self.model_extra["content_layout"]
        return message


class ChatResponseChoice(Record):
    message: ChatResponseMessage
    finish_reason: str | None = None


class ChatResponse(Record):
    choices: list[ChatResponseChoice]
    usage: Usage

    @property
    def text(self):
        if not self.choices:
            raise ValueError("Model response contains no choices")
        return self.choices[0].message.content or ""

    @property
    def json(self):
        return json.loads(self.text)

    @property
    def tools(self):
        if not self.choices:
            raise ValueError("Model response contains no choices")
        return self.choices[0].message.tool_calls


class ChatModel:
    def __init__(self, model: str, cache: JsonCache | None = None):
        if "/" not in model:
            raise ValueError("An explicit OpenRouter model ID is required")
        self.model = model
        if cache is None:
            from experiments.paths import paths

            namespace = hashlib.sha256(model.encode("utf-8")).hexdigest()[:16]
            cache = JsonCache(
                paths.reports.parent
                / "runs"
                / "caches"
                / f"openrouter-{namespace}.json"
            )
        self.cache = cache

    def chat(self, messages, request=None):
        prompt = (request or ChatRequest()).prepare()
        prompt["messages"] = [message.prepare() for message in messages]
        prompt["model"] = self.model
        prompt["provider"] = {"require_parameters": True}
        prompt["stream"] = False

        def fetch():
            response = _parse_response(complete(prompt))
            return response.model_dump(mode="json", exclude_none=True)

        payload = self.cache.get_or_create(prompt, fetch)
        return _parse_response(payload)


class ToolResult(Record):
    values: dict[str, Any] = Field(default_factory=dict)
    files: dict[str, Path] = Field(default_factory=dict)


class AgentToolCall(Record):
    identifier: str
    tool: str
    arguments: dict[str, Any]
    result: ToolResult


class AgentResult(Record):
    message: str | None = None
    tools: list[list[AgentToolCall]] = Field(default_factory=list)
    usage: list[Usage] = Field(default_factory=list)


class Environment:
    def __init__(self, root=None):
        self.root = root
        self.conversation = []

    @property
    def iterations(self):
        return sum(isinstance(turn, ChatResponseMessage) for turn in self.conversation)


E = TypeVar("E", bound=Environment)


class Tool(ABC, Generic[E]):
    @abstractmethod
    def definition(self) -> Function:
        raise NotImplementedError

    @abstractmethod
    def execute(self, arguments, environment: E, identifier=None) -> ToolResult:
        raise NotImplementedError

    @abstractmethod
    def compile(self, result: ToolResult) -> str:
        raise NotImplementedError


class Agent(Generic[E]):
    def __init__(
        self,
        model,
        system=None,
        tools=None,
        tool_callback=None,
        request=None,
        iterations=8,
        console=None,
    ):
        self.model, self.system = model, system
        self.tools = list(tools or [])
        self.tool_map = {tool.definition().name: tool for tool in self.tools}
        self.tool_callback = tool_callback
        self.request = request or ChatRequest()
        self.request.tools = [tool.definition() for tool in self.tools] or None
        self.iterations, self.console = iterations, console

    def run(self, utterance, environment):
        environment.conversation.clear()
        if self.system:
            environment.conversation.append(
                Message(role=Role.System, content=self.system)
            )
        if utterance:
            environment.conversation.append(Message(role=Role.User, content=utterance))
        return self.resume(environment)

    def resume(self, environment):
        result = AgentResult()
        while environment.iterations < self.iterations:
            response = self.model.chat(environment.conversation, self.request)
            if not response.choices:
                raise ValueError("An agent response requires at least one choice")
            choice = response.choices[0]
            turn = choice.message
            result.usage.append(response.usage)
            environment.conversation.append(turn)
            if self.console and turn.content:
                self.console.print(turn.content, markup=False, highlight=False)
            if turn.tool_calls:
                calls = []
                result.tools.append(calls)
                for call in turn.tool_calls:
                    name = call.function.name
                    if name not in self.tool_map:
                        raise ValueError(f"Agent received an unknown tool: {name!r}")
                    tool = self.tool_map[name]
                    arguments = json.loads(call.function.arguments)
                    outcome = tool.execute(
                        arguments=arguments, environment=environment, identifier=call.id
                    )
                    compiled = tool.compile(outcome)
                    environment.conversation.append(
                        Message(role=Role.Tool, content=compiled, tool_call_id=call.id)
                    )
                    calls.append(
                        AgentToolCall(
                            identifier=call.id,
                            tool=name,
                            arguments=arguments,
                            result=outcome,
                        )
                    )
                    if self.tool_callback:
                        self.tool_callback(outcome, environment)
            if choice.finish_reason == "stop":
                if turn.content:
                    result.message = turn.content
                break
        return result


def _parse_response(payload):
    try:
        parsed = ChatResponse.model_validate(payload)
    except ValueError as error:
        raise ProviderError("Invalid OpenRouter response schema") from error
    if not parsed.choices:
        raise ProviderError("OpenRouter response contains no choices")
    for choice in parsed.choices:
        if choice.finish_reason in {"error", "content_filter"}:
            raise ProviderError(f"OpenRouter completion failed: {choice.finish_reason}")
        if not choice.message.content and not choice.message.tool_calls:
            raise ProviderError(
                "OpenRouter response contains neither content nor tool calls"
            )
    return parsed
