"""Run the ordered Stack construction filters using fresh model responses."""

import argparse
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from experiments.inference.solve import run
from experiments.paths import paths
from experiments.run import (
    Configuration,
    describe,
    load_configuration,
    preflight,
    relative_path,
    validate_output_root,
)
from generation.stack.e_filter import filter_dataset


class FilterConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    results: list[str] = Field(min_length=1)
    output: str


class ConfigurationWithFilter(Configuration):
    filter: FilterConfiguration


def execute(
    configurations, *, output_root, workers=4, dry_run=False, model_override=None
):
    output_root = output_root.resolve()
    validate_output_root(output_root)
    available, jobs, outputs = set(), [], set()
    for file in configurations:
        configuration = load_configuration(
            file, schema=ConfigurationWithFilter, model_override=model_override
        )
        job = preflight(
            configuration, output_root, workers, dry_run=dry_run, available=available
        )
        target = relative_path(output_root, configuration.filter.output)
        if (
            job.output in outputs
            or target in outputs
            or target == job.output
            or target.exists()
        ):
            raise FileExistsError(f"Duplicate or existing filtering output: {target}")
        if configuration.source == "runs" and job.benchmarks not in available:
            raise ValueError(
                f"{file} depends on an earlier selected stage: {job.benchmarks}"
            )
        results = [
            relative_path(output_root, value) for value in configuration.filter.results
        ]
        if any(result not in available | {job.output} for result in results):
            raise ValueError(f"{file} references an unselected filtering result")
        outputs.update((job.output, target))
        available.update((job.output, target))
        jobs.append((job, results, target))
    source = paths.stack / "d_collect" / "collected.json"
    if not dry_run and not source.is_file():
        raise FileNotFoundError(source)
    for job, results, target in jobs:
        describe(job)
        if not dry_run:
            run(job)
            filter_dataset(source, results, target)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("configs", nargs="*", type=Path)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--model", help="Explicit OpenRouter override for the selected stages"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    configurations = args.configs or sorted(
        Path(__file__).with_name("configurations").glob("*.yaml")
    )
    execute(
        configurations,
        output_root=args.output_root or paths.reports.parent / "runs",
        workers=args.workers,
        dry_run=args.dry_run,
        model_override=args.model,
    )


if __name__ == "__main__":
    main()
