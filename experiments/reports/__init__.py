"""Saved-result reports and their shared command-line and output handling."""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from experiments.paths import paths


def arguments(
    description: str,
    argv: list[str] | None = None,
    *,
    paper: bool = False,
    replay: bool = False,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--output", type=Path, default=paths.reports)
    parser.add_argument(
        "--show", action="store_true", help="Display figures as well as saving them"
    )
    if paper:
        parser.add_argument(
            "--all-runs",
            action="store_true",
            help="Include supplemental configurations",
        )
    if replay:
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Also execute reference programs for feedback analysis",
        )
    return parser.parse_args(argv)


def configure_plots(*, show: bool) -> None:
    if not show:
        plt.switch_backend("Agg")
    sns.set_style("whitegrid", {"font.family": "Times New Roman"})
    sns.set_context("paper", font_scale=2.5)
    sns.set_palette("Set1")


def write_table(value: pd.DataFrame | pd.Series, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    value.to_csv(path)
    print(value.to_string())


def finish_figure(show: bool) -> None:
    if show:
        plt.show()
    plt.close()
