"""Run-level means and distributions from saved inference results."""

from pathlib import Path
from typing import Union

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from jsonargparse import ArgumentParser
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table
from rich.text import Text
from tqdm import tqdm

from experiments.inference.benchmark import Experiment
from experiments.paths import paths
from jqbench.metrics import aggregate


class ResultSettings(BaseModel):
    write: bool = True
    plot: bool = False
    save: bool = False
    save_raw: bool = False
    path: Path | None = None


def metric_at_k(n: int, c: int, k: int) -> float:
    """Estimate pass@k from n samples with c correct predictions."""
    if c == 0:
        return 0.0
    if n - c < k:
        return 1.0
    product = 1.0
    for i in range(n - c + 1, n + 1):
        product *= 1.0 - k / i
    return 1.0 - product


def table(df: pd.DataFrame) -> pd.DataFrame:
    group = df.groupby(
        ["dataset", "name", "model-name", "input-kind", "input-which"]
    ).agg(
        count=("compiles", "count"),
        compiles=("compiles", "mean"),
        executes=("executes", "mean"),
        value_match=("value_match", "mean"),
        exact_match=("exact_match", "mean"),
    )
    group = group.sort_values(by=["input-kind", "input-which", "name"])
    return group


def write_table(df: pd.DataFrame) -> None:
    group = table(df).reset_index()
    rich_table = Table()

    for col in group.columns:
        if col in ["compiles", "executes", "value_match", "exact_match"]:
            rich_table.add_column(col, justify="right")
        else:
            rich_table.add_column(col)

    best_values = {}
    for name in group["model-name"].unique():
        model_data = group[group["model-name"] == name]
        best_values[name] = {}
        for metric in ["compiles", "executes", "value_match", "exact_match"]:
            best_values[name][metric] = model_data[metric].max()

    previous_input_kind = None
    for _, row in group.iterrows():
        if row["input-kind"] != previous_input_kind:
            if previous_input_kind is not None:
                rich_table.add_section()
            previous_input_kind = row["input-kind"]
        row_data = []
        for col in group.columns:
            value = row[col]
            if col in ["compiles", "executes", "value_match", "exact_match"]:
                if value == best_values[row["model-name"]][col]:
                    row_data.append(Text(f"{value:.3f}", style="bold"))
                else:
                    row_data.append(f"{value:.3f}")
            else:
                row_data.append(str(value))
        rich_table.add_row(*row_data)

    console = Console()
    console.print(rich_table)


def save_table(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    group = table(df)
    if path.suffix == ".csv":
        group.to_csv(path)
    if path.suffix == ".tex":
        group.to_latex(path)
    if path.suffix == ".md":
        group.reset_index().to_markdown(path)


def plot_distribution(df: pd.DataFrame, path: Path, metric: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for (model, input_kind, input_which), data in df.groupby(
        ["model-name", "input-kind", "input-which"]
    ):
        name = f"{model}-{input_kind}-{input_which}".lower()
        figure, ax = plt.subplots()
        sns.histplot(
            data=data, x=metric, binwidth=0.1, binrange=(0, 1), stat="percent", ax=ax
        )
        ax.set(xlim=(0, 1), ylim=(0, None), title=name)
        figure.savefig(path / f"{name}.png")
        plt.close(figure)


def load_results(result_paths: list[Path]) -> pd.DataFrame:
    files = []
    for result in result_paths:
        if result.is_dir():
            files.extend(result.rglob("*.json"))
        else:
            files.append(result)

    records = []
    for file in tqdm(files):
        data = Experiment.model_validate_json(file.read_text(encoding="utf-8"))
        base_input = {
            f"input-{k}": v for k, v in data.input.model_dump(mode="json").items()
        }
        base_model = {
            f"model-{k}": v for k, v in data.model.model_dump(mode="json").items()
        }
        base = {
            **data.solver,
            **base_input,
            **base_model,
        }
        for solution in data.solutions:
            if len(solution.predictions) == 0:
                continue
            solution_metrics = [p.metrics for p in solution.predictions]
            solution_aggregated = {
                k.name: v for k, v in aggregate(solution_metrics).items()
            }
            records.append(
                {
                    "identifier": solution.identifier,
                    "dataset": data.dataset,
                    **base,
                    **solution_aggregated,
                }
            )
    return pd.DataFrame.from_records(records)


def generate(result_paths: list[Path], settings: ResultSettings) -> None:
    df = load_results(result_paths)
    if df.empty:
        raise ValueError("No saved predictions found in the supplied results")
    output = settings.path or paths.reports
    if settings.save_raw:
        output.mkdir(parents=True, exist_ok=True)
        df.to_csv(output / "results-raw.csv", index=False)

    if settings.write:
        print("\nℹ️")
        print("Found", len(df), "solutions")
        print("  on", len(df["model-name"].unique()), "models,")
        print("  using", len(df["name"].unique()), "solvers.")
        print("\n📈")
        write_table(df)

    if settings.save:
        save_table(df, output / "results.csv")
        save_table(df, output / "results.md")

    if settings.plot:
        plot_distribution(df, output / "value_match", "value_match")


def main(argv: list[str] | None = None) -> None:
    plt.rcParams.update({"font.size": 16, "font.family": "Times New Roman"})
    sns.set_style("whitegrid")
    sns.set_palette("pastel")

    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Union[Path, list[Path]], default=None)
    parser.add_argument("--settings", type=ResultSettings, default=ResultSettings())
    args = parser.instantiate_classes(parser.parse_args(argv))
    result_paths = args.results or [paths.results]
    if isinstance(result_paths, Path):
        result_paths = [result_paths]
    generate(result_paths, args.settings)


if __name__ == "__main__":
    main()
