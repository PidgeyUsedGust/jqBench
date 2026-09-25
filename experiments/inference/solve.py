import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from jsonargparse import ArgumentParser
from rich.console import Console
from rich.table import Table
from tqdm import tqdm

from experiments.inference.benchmark import (
    Benchmark,
    Experiment,
    InputConfiguration,
    InputKind,
    InputSet,
    Prediction,
    Solution,
    load,
)
from experiments.inference.benchmark import (
    problem as build_problem,
)
from experiments.inference.settings import Settings, Verbosity
from experiments.inference.solvers.solver import Solver
from experiments.llm import ChatModel, ChatRequest, JsonCache
from experiments.llm.configuration import ModelConfiguration
from experiments.paths import paths
from jqbench.metrics import evaluate


@dataclass
class Run:
    solver: Solver
    input: InputConfiguration
    model: ModelConfiguration
    benchmarks: Path | None = None
    input_root: Path | None = None
    select: str | None = None
    output: str | Path | None = None
    output_root: Path | None = None
    suffix: str = ""
    workers: int = 4
    cache: str | Path | None = None
    cache_root: Path | None = None
    force: bool = False
    take: int | None = None
    verbosity: Verbosity = Verbosity.Off
    debug: bool = False


def main(argv=None):
    # fmt: off
    parser = ArgumentParser()
    parser.add_argument("--benchmarks", type=Path, default=None)
    parser.add_argument("--input-root", type=Path, default=None)
    parser.add_argument("--select", type=str, default=None)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--solver", type=Solver, default=None)
    parser.add_argument("--input", type=InputConfiguration, default=InputConfiguration(kind=InputKind.Input, which=InputSet.All))
    parser.add_argument("--model", type=ModelConfiguration, default=ModelConfiguration(name="openai/gpt-4.1"))
    parser.add_argument("--suffix", type=str, default="")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--cache", type=str, default=None)
    parser.add_argument("--cache-root", type=Path, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--take", type=Optional[int], default=None)
    parser.add_argument("--verbosity", type=Verbosity, default=Verbosity.Off)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)
    args_init = parser.instantiate_classes(args)
    # fmt: on
    values = {name: getattr(args_init, name) for name in Run.__dataclass_fields__}
    run(Run(**values))


def run(args: Run) -> Experiment:
    if args.solver is None:
        raise ValueError("A solver is required")
    if args.workers < 1:
        raise ValueError("workers must be positive")

    # # apply settings
    Settings.verbosity = args.verbosity
    Settings.console = Console(quiet=(Settings.verbosity == Verbosity.Off))

    # load classes
    solver: Solver = args.solver
    solver_name = f"{solver.name}{args.suffix}"
    solver_parameters = {"name": solver_name, **solver.parameters}
    input_configuration: InputConfiguration = args.input
    model_configuration: ModelConfiguration = args.model

    # load data
    dataset = load(
        args.benchmarks or (paths.data / "jqStack.jsonl"),
        debug=args.select,
        input_root=args.input_root,
    )

    # set defaults
    auto1 = input_configuration.name
    auto2 = f"{dataset.name}-{solver_name}-{model_configuration.specification.replace(chr(47), chr(45))}"
    if args.cache == "auto":
        args.cache_root = args.cache_root or (paths.reports.parent / "runs" / "caches")
        args.cache = args.cache_root / auto1 / f"{auto2}.json"
    if args.output == "auto":
        args.output_root = args.output_root or (paths.reports.parent / "runs")
        args.output = args.output_root / auto1 / f"{auto2}.json"
    if isinstance(args.output, str) and not args.output.endswith(".json"):
        args.output = Path(args.output) / auto1 / f"{auto2}.json"
    print(f"Using cache file: {args.cache}")
    print(f"Using output file: {args.output}")

    # load model
    model = ChatModel(
        model=model_configuration.specification,
        cache=JsonCache(args.cache) if args.cache is not None else None,
    )

    # load existing results
    output = None
    experiment = None
    if args.output is not None:
        if (output := Path(args.output)).exists() and not args.force:
            with open(output, encoding="utf-8") as f:
                experiment = Experiment.model_validate_json(f.read())
            if not (
                experiment.dataset == dataset.name
                and experiment.solver == solver_parameters
                and experiment.input == input_configuration
                and experiment.model == model_configuration
            ):
                raise ValueError("Incompatible experiment configurations.")
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
    experiment = experiment or Experiment(
        dataset=dataset.name,
        solver={"name": solver_name, **solver.parameters},
        input=input_configuration,
        model=model_configuration,
    )

    # filter out completed benchmarks
    todo = dataset.benchmarks
    if not args.force and (args.select is None):
        done = {r.identifier for r in experiment.solutions}
        todo = [d for d in todo if d.identifier not in done]
        Settings.console.print(
            f"> 🏁  {len(experiment.solutions)} solutions already present, {len(todo)} to go."
        )
    if args.take:
        todo = todo[: args.take]

    # remove to-do from experiment solutions
    experiment.solutions = [
        s
        for s in experiment.solutions
        if s.identifier not in {b.identifier for b in todo}
    ]

    if len(todo) >= 10 and args.output is None:
        raise ValueError("Refusing to run large experiments without output file.")

    print(f"⚙️  Starting solving {len(todo)} benchmarks using {solver_name}.")

    if args.select is not None:
        Settings.verbosity = Verbosity.Debug
        Settings.console.quiet = False
        args.debug = True

    # define solver
    def solve(
        benchmark: Benchmark, solver: Solver, model: ChatModel, request: ChatRequest
    ) -> Solution:
        problem = build_problem(benchmark, input_configuration)
        candidates, meta = solver.solve(problem, model, request)
        inputs = (
            benchmark.inputs
            if benchmark.inputs is not None
            else [json.loads(benchmark.inputfile.read_text(encoding="utf-8"))["data"]]
        )
        predictions = [
            Prediction(
                program=candidate,
                metrics=evaluate(
                    program=candidate,
                    inputs=inputs,
                    solutions=benchmark.expressions,
                    settings=benchmark.settings,
                ),
            )
            for candidate in candidates
        ]
        return Solution(
            identifier=benchmark.identifier,
            inputs=benchmark.inputs,
            inputfile=Path(
                benchmark.inputfile.relative_to(
                    (args.input_root or paths.data).resolve()
                ).as_posix()
            )
            if benchmark.inputfile
            else None,
            solutions=benchmark.expressions,
            predictions=predictions,
            metadata=meta,
        )

    # initialize progress bar
    progress = tqdm(
        total=len(todo),
        disable=len(todo) <= 1,
        desc=f"{solver_name} - {model_configuration.name} - {input_configuration.name}",
    )
    postfix = {"errors": 0, "rate": 0}

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                solve, benchmark, solver, model, model_configuration.request
            ): benchmark
            for benchmark in todo
        }
        for future in as_completed(futures):
            benchmark = futures[future]
            try:
                solution = future.result()
            except Exception as error:
                for pending in futures:
                    pending.cancel()
                if output is not None and args.select is None:
                    output.write_text(
                        experiment.model_dump_json(indent=2), encoding="utf-8"
                    )
                progress.close()
                raise RuntimeError(
                    f"Experiment failed for benchmark {benchmark.identifier}"
                ) from error
            experiment.solutions.append(solution)
            if Settings.verbosity == Verbosity.Debug:
                table = Table(
                    "Program", "Compiles", "Executes", "Value Match", "Exact Match"
                )
                for p in solution.predictions:
                    table.add_row(
                        p.program.code,
                        str(p.metrics.compiles),
                        str(p.metrics.executes),
                        str(p.metrics.value_match),
                        str(p.metrics.exact_match),
                    )
                    table.add_section()
                Settings.console.print("> 💯")
                Settings.console.print(table)
            if (output is not None) and (progress.n % 10 == 0):
                o = experiment.model_dump_json(indent=2)
                with open(output, "w", encoding="utf-8") as f:
                    f.write(o)
            progress.update(1)
            progress.set_postfix(postfix)

    if (args.select is None) and (output is not None):
        o = experiment.model_dump_json(indent=2)
        with open(output, "w", encoding="utf-8") as f:
            f.write(o)
    progress.close()
    return experiment


if __name__ == "__main__":
    main()
