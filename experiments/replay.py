"""Explicitly execute a saved prediction and reference program for one case."""

import argparse
import json
from pathlib import Path

from experiments.paths import paths
from jqbench import resolve_inputfile
from jqbench.execution import Program, ProgramKind, run


def replay(results: Path, identifier: str, *, input_root: Path | None = None):
    data = json.loads(results.read_text(encoding="utf-8"))["solutions"]
    record = next(
        (item for item in data if str(item["identifier"]) == str(identifier)), None
    )
    if record is None:
        raise ValueError(f"Case {identifier} is absent from {results}")
    if not record["predictions"]:
        raise ValueError(f"Case {identifier} has no saved prediction")
    reference = Program(kind=ProgramKind.Jq, code=record["solutions"][0])
    prediction = Program.model_validate(record["predictions"][0]["program"])
    inputs = record["inputs"]
    if inputs is None:
        inputs = [
            json.loads(
                resolve_inputfile(
                    record["inputfile"], root=input_root or paths.data
                ).read_text(encoding="utf-8")
            )["data"]
        ]
    for value in inputs:
        print(f"Input: {value}")
        print(f"Reference output: {run(reference, value)}")
        print(f"Prediction output: {run(prediction, value)}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument(
        "--input-root",
        type=Path,
        default=None,
        help="Root for intermediate input references; defaults to public data",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Authorize execution of the stored programs",
    )
    args = parser.parse_args(argv)
    if not args.execute:
        parser.error("Stored programs are executable code; pass --execute to run them")
    replay(args.results, args.case, input_root=args.input_root)


if __name__ == "__main__":
    main()
