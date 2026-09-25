from abc import ABC, abstractmethod
from typing import Optional, Union

from experiments.inference.benchmark import Problem, Program, SolutionMetadata
from experiments.llm import ChatModel, ChatRequest


class Solver(ABC):
    @abstractmethod
    def solve(
        self, problem: Problem, model: ChatModel, request: ChatRequest
    ) -> tuple[list[Program], Optional[SolutionMetadata]]:
        pass

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @property
    def parameters(self) -> dict[str, Union[str, int, float]]:
        return dict()
