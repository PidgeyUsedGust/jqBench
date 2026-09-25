"""Fresh-run settings and historical model provenance."""

from pydantic import BaseModel, ConfigDict, Field

from . import ChatRequest


class ModelConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    id: str | None = None
    n: int = Field(default=1, ge=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    reasoning: str | None = None

    @property
    def specification(self) -> str:
        selected = self.id or (self.name if "/" in self.name else None)
        if selected is None:
            raise ValueError(
                f"Historical model {self.name!r} requires an explicit OpenRouter model override"
            )
        if "/" not in selected or any(character.isspace() for character in selected):
            raise ValueError(
                "Use an explicit OpenRouter model ID such as openai/gpt-4.1"
            )
        return selected

    @property
    def request(self) -> ChatRequest:
        return ChatRequest(
            n=self.n,
            temperature=self.temperature,
            reasoning_effort=self.reasoning,
            max_tokens=16000,
        )
