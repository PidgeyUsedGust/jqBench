"""Run paper configurations with cache-first OpenRouter inference."""

import argparse
import json
from pathlib import Path, PureWindowsPath
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from experiments.inference.benchmark import InputConfiguration
from experiments.inference.solve import Run, run
from experiments.inference.solvers.solver_jq import JqAgent, JqSampler
from experiments.inference.solvers.solver_python import PythonAgent
from experiments.llm.configuration import ModelConfiguration
from experiments.paths import ROOT, paths


class SolverConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["JqAgent", "PythonAgent", "JqSampler"]
    implicit: bool | None = None
    documentation: bool | None = None
    iterations: int | None = Field(default=None, ge=1)

    def build(self):
        cls = {"JqAgent": JqAgent, "PythonAgent": PythonAgent, "JqSampler": JqSampler}[
            self.name
        ]
        return cls(**self.model_dump(exclude={"name"}, exclude_none=True))


class Configuration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["data", "stack", "runs"] = "data"
    dataset: str
    solver: SolverConfiguration
    input: InputConfiguration
    model: ModelConfiguration
    cache: str
    output: str

    @model_validator(mode="after")
    def validate_solver(self):
        if self.solver.name == "PythonAgent" and self.solver.documentation is not None:
            raise ValueError("Python solvers do not support documentation")
        if self.solver.name == "JqSampler" and (
            self.solver.implicit is not None or self.solver.iterations is not None
        ):
            raise ValueError("Sampler configurations do not accept agent options")
        return self


def relative_path(root: Path, value: str) -> Path:
    path = Path(value)
    if (
        not value
        or "\\" in value
        or PureWindowsPath(value).drive
        or path.is_absolute()
        or ".." in path.parts
    ):
        raise ValueError(f"Expected a relative configuration path: {value!r}")
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f"Configuration path escapes its root: {value!r}")
    return target


def load_configuration(
    path: Path, *, schema=Configuration, model_override: str | None = None
) -> Configuration:
    with path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    configuration = schema.model_validate(payload)
    if model_override is not None:
        configuration.model.id = model_override
    return configuration


def prepare(configuration: Configuration, output_root: Path, workers: int) -> Run:
    roots = {"data": paths.data, "stack": paths.stack, "runs": output_root}
    return Run(
        solver=configuration.solver.build(),
        input=configuration.input,
        model=configuration.model,
        benchmarks=relative_path(roots[configuration.source], configuration.dataset),
        input_root=paths.stack if configuration.source == "stack" else paths.data,
        cache=relative_path(output_root / "caches", configuration.cache),
        output=relative_path(output_root, configuration.output),
        workers=workers,
    )


def validate_output_root(output_root: Path):
    protected = (paths.data, paths.stack, paths.spider, paths.results, paths.caches)
    if any(
        output_root.is_relative_to(root) or root.is_relative_to(output_root)
        for root in protected
    ):
        raise ValueError(
            "The output root must be separate from supplied data, results, and caches"
        )


def preflight(
    configuration: Configuration,
    output_root: Path,
    workers: int,
    *,
    dry_run=False,
    available=None,
):
    if workers < 1:
        raise ValueError("workers must be positive")
    available = available or set()
    job = prepare(configuration, output_root, workers)
    if job.output.exists():
        raise FileExistsError(
            f"Choose a fresh output root; refusing to overwrite {job.output}"
        )
    configuration.model.request.prepare()
    if (
        configuration.model.id is not None
        or "/" in configuration.model.name
        or not dry_run
    ):
        _ = configuration.model.specification
    if not dry_run:
        if not job.benchmarks.is_file() and job.benchmarks not in available:
            raise FileNotFoundError(job.benchmarks)
        if job.cache.exists():
            from experiments.llm import JsonCache

            JsonCache(job.cache)
    return job


def describe(job):
    unresolved = job.model.id is None and "/" not in job.model.name
    print(
        json.dumps(
            {
                "dataset": str(job.benchmarks),
                "output": str(job.output),
                "cache": str(job.cache),
                "historical_model": job.model.name,
                "openrouter_model": job.model.id
                or (job.model.name if not unresolved else None),
                "requires_model_override": unresolved,
                "request": job.model.request.prepare(),
                "input": job.input.model_dump(mode="json"),
            },
            indent=2,
        )
    )


def execute(
    configurations: list[Path],
    *,
    output_root: Path,
    workers: int = 4,
    dry_run: bool = False,
    model_override: str | None = None,
):
    output_root = output_root.resolve()
    validate_output_root(output_root)
    prepared = [
        load_configuration(path, model_override=model_override)
        for path in configurations
    ]
    jobs = [
        preflight(configuration, output_root, workers, dry_run=dry_run)
        for configuration in prepared
    ]
    outputs = [job.output for job in jobs]
    caches = [job.cache for job in jobs]
    if len(set(outputs)) != len(outputs) or set(outputs) & set(caches):
        raise ValueError("Duplicate or overlapping output/cache targets")
    for job in jobs:
        describe(job)
        if not dry_run:
            run(job)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("configs", nargs="*", type=Path)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--model", help="Explicit OpenRouter ID overriding the selected configurations"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and display without model calls or requiring artifacts",
    )
    args = parser.parse_args(argv)
    configurations = args.configs or sorted(
        (ROOT / "experiments" / "configurations").glob("*.yaml")
    )
    if not configurations:
        parser.error("No experiment configurations selected")
    execute(
        configurations,
        output_root=args.output_root or paths.reports.parent / "runs",
        workers=args.workers,
        dry_run=args.dry_run,
        model_override=args.model,
    )


if __name__ == "__main__":
    main()
