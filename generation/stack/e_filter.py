"""Select collected benchmarks not solved by any supplied filtering experiment."""

import argparse
from pathlib import Path

from experiments.inference.benchmark import Dataset, Experiment
from experiments.paths import paths
from jqbench.metrics import ValueMatch


def filter_dataset(source: Path, results: list[Path], output: Path):
    if output.exists():
        raise FileExistsError(output)
    if not results:
        raise ValueError("At least one filtering result is required")
    dataset = Dataset.model_validate_json(source.read_text(encoding="utf-8"))
    solved = {}
    for path in results:
        experiment = Experiment.model_validate_json(path.read_text(encoding="utf-8"))
        name = f"{experiment.model.name}-{experiment.input.name}"
        solved.setdefault(name, set()).update(
            solution.identifier
            for solution in experiment.solutions
            if any(
                prediction.metrics.value_match != ValueMatch.No
                for prediction in solution.predictions
            )
        )
    union = set.union(*solved.values())
    intersection = set.intersection(*solved.values())
    print(f"{len(intersection)} solved by all; {len(union)} solved by at least one.")
    result = Dataset(
        name="jqStackFiltered",
        benchmarks=[
            item for item in dataset.benchmarks if item.identifier not in union
        ],
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(f"Wrote {len(result.benchmarks)} benchmarks to {output}")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=paths.stack / "d_collect" / "collected.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("results", nargs="+", type=Path)
    args = parser.parse_args(argv)
    filter_dataset(args.source, args.results, args.output)


if __name__ == "__main__":
    main()
