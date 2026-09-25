"""Bounded execution of trusted jq/Python programs, not a security sandbox."""

import ast
import atexit
import builtins
import contextlib
import io
import json
import multiprocessing as mp
import threading
import weakref
from enum import Enum
from typing import Any

import jq
from pydantic import BaseModel, JsonValue


class ProgramKind(str, Enum):
    Jq = "jq"
    Python = "python"


class Program(BaseModel):
    kind: ProgramKind
    code: str


class ExecutionError(RuntimeError):
    """A program failed during execution."""


class JqExecutionError(ExecutionError):
    pass


class JqExecutionEngine:
    timeout = 32.0

    @staticmethod
    def compile(expression: str) -> Any:
        return jq.compile(expression)

    @staticmethod
    def execute(expression: str, input: JsonValue) -> list[JsonValue]:
        return _execute(
            Program(kind=ProgramKind.Jq, code=expression),
            input,
            JqExecutionEngine.timeout,
        )


class PythonExecutionEngine:
    timeout = 16.0

    @staticmethod
    def compile(code: str) -> str:
        """Validate syntax and the function contract without executing code."""
        tree = ast.parse(code.strip())
        if not any(isinstance(node, ast.FunctionDef) for node in tree.body):
            raise ValueError("Python programs must define a top-level function")
        builtins.compile(tree, "<jqbench>", "exec")
        return code.strip()

    @staticmethod
    def execute(code: str, input: JsonValue) -> JsonValue:
        return PythonExecutionEngine.execute_compiled(
            PythonExecutionEngine.compile(code), input
        )

    @staticmethod
    def execute_compiled(compiled: str, input: JsonValue) -> JsonValue:
        if not isinstance(compiled, str):
            raise TypeError("Expected source returned by PythonExecutionEngine.compile")
        return _execute(
            Program(kind=ProgramKind.Python, code=compiled),
            input,
            PythonExecutionEngine.timeout,
        )


def compiles(program: Program) -> bool:
    try:
        if program.kind == ProgramKind.Jq:
            JqExecutionEngine.compile(program.code)
        else:
            PythonExecutionEngine.compile(program.code)
    except (ValueError, SyntaxError, TypeError):
        return False
    return True


def run(program: Program, input: JsonValue) -> JsonValue:
    """Execute a program; failures raise rather than masquerading as JSON null."""
    if program.kind == ProgramKind.Jq:
        return JqExecutionEngine.execute(program.code, input)
    return PythonExecutionEngine.execute(program.code, input)


class _Worker:
    def __init__(self):
        self.process = None
        self.connection = None

    def __del__(self):
        self.close()

    def execute(self, program, value, timeout):
        if timeout <= 0:
            raise ValueError("Execution timeout must be positive")
        if self.process is None or not self.process.is_alive():
            self.close()
            context = mp.get_context("spawn")
            self.connection, child = context.Pipe()
            self.process = context.Process(target=_worker, args=(child,), daemon=True)
            self.process.start()
            child.close()
        try:
            self.connection.send((program.kind.value, program.code, value))
            if not self.connection.poll(timeout):
                raise TimeoutError(
                    f"{program.kind.value} execution exceeded {timeout}s"
                )
            status, payload = self.connection.recv()
        except (TimeoutError, EOFError, OSError) as error:
            self.close()
            if isinstance(error, TimeoutError):
                raise
            raise ExecutionError("Execution worker exited unexpectedly") from error
        if status == "error":
            error_type = (
                JqExecutionError if program.kind == ProgramKind.Jq else ExecutionError
            )
            raise error_type(payload)
        return payload

    def close(self):
        if self.connection is not None:
            self.connection.close()
        if self.process is not None:
            if self.process.pid is not None:
                if self.process.is_alive():
                    self.process.terminate()
                self.process.join(timeout=1)
                if self.process.is_alive():
                    self.process.kill()
                    self.process.join()
            self.process.close()
        self.connection = self.process = None


_local = threading.local()
_workers = weakref.WeakSet()
_lock = threading.Lock()


def _execute(program, value, timeout):
    if not hasattr(_local, "worker"):
        _local.worker = _Worker()
        with _lock:
            _workers.add(_local.worker)
    return _local.worker.execute(program, value, timeout)


def _shutdown():
    for worker in list(_workers):
        worker.close()


def _worker(connection):
    compiled = {}
    try:
        while True:
            try:
                kind, code, value = connection.recv()
            except EOFError:
                return
            try:
                with (
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    if kind == "jq":
                        if code not in compiled:
                            compiled[code] = jq.compile(code)
                        result = compiled[code].input_value(value).all()
                    else:
                        tree = ast.parse(code)
                        name = next(
                            node.name
                            for node in tree.body
                            if isinstance(node, ast.FunctionDef)
                        )
                        namespace = {}
                        exec(builtins.compile(tree, "<jqbench>", "exec"), namespace)
                        result = namespace[name](value)
                    # Return only JSON values, never arbitrary objects from submitted code.
                    result = json.loads(json.dumps(result, allow_nan=False))
                connection.send(("ok", result))
            except BaseException as error:
                connection.send(("error", f"{type(error).__name__}: {error}"))
    finally:
        connection.close()


atexit.register(_shutdown)
