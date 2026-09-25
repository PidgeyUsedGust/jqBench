"""Datasets analysis from supplied benchmark artifacts."""

import re
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap

from experiments.paths import paths
from experiments.reports import arguments, configure_plots, finish_figure, write_table
from jqbench import load


def expr_features(expr: str) -> dict:
    """Extract complexity features from a jq expression."""
    return {
        "length": len(expr),
        "n_pipe": expr.count("|"),
        "n_def": len(re.findall(r"\bdef\b", expr)),
        "has_def": bool(re.search(r"\bdef\b", expr)),
        "has_reduce": "reduce" in expr,
        "has_try": "try" in expr,
        "has_if": bool(re.search(r"\bif\b", expr)),
        "has_recurse": "recurse" in expr,
        "n_select": len(re.findall(r"\bselect\b", expr)),
        "n_map": len(re.findall(r"\bmap\b", expr)),
    }


OPERATORS = [
    "select",
    "map",
    "group_by",
    "sort_by",
    "unique_by",
    "reduce",
    "length",
    "keys",
    "values",
    "has",
    "contains",
    "test",
    "split",
    "join",
    "tostring",
    "tonumber",
    "to_entries",
    "from_entries",
    "with_entries",
    "flatten",
    "any",
    "all",
    "add",
    "min_by",
    "max_by",
    "first",
    "last",
    "sub",
    "gsub",
    "scan",
    "match",
    "capture",
    "ascii_downcase",
    "ascii_upcase",
    "try",
    "if",
    "def",
    "recurse",
    "foreach",
    "until",
    "while",
    "limit",
]


def count_operators(benchmarks):
    counts = Counter()
    for b in benchmarks:
        expr = b["expressions"][0]
        for op in OPERATORS:
            pattern = rf"\b{re.escape(op)}\b" if op not in ("if",) else rf"\b{op}\b"
            if re.search(pattern, expr):
                counts[op] += 1
    return counts


def count_schema_fields(schema: dict) -> int:
    """Count total leaf-level fields in a JSON Schema."""
    if not isinstance(schema, dict):
        return 0
    props = schema.get("properties", {})
    total = 0
    for v in props.values():
        if v.get("type") == "object":
            total += count_schema_fields(v)
        elif v.get("type") == "array" and "items" in v:
            total += count_schema_fields(v["items"])
        else:
            total += 1
    return total


def schema_depth(schema: dict) -> int:
    """Max nesting depth of a JSON Schema."""
    if not isinstance(schema, dict):
        return 0
    props = schema.get("properties", {})
    if not props:
        return 0
    child_depths = []
    for v in props.values():
        if v.get("type") == "array" and "items" in v:
            child_depths.append(1 + schema_depth(v["items"]))
        elif v.get("type") == "object":
            child_depths.append(1 + schema_depth(v))
        else:
            child_depths.append(1)
    return max(child_depths, default=0)


def count_top_level_arrays(schema: dict) -> int:
    """Count top-level array properties (≈ tables)."""
    props = schema.get("properties", {})
    return sum(1 for v in props.values() if v.get("type") == "array")


def input_complexity(inp) -> dict:
    """Measure complexity of a single test input."""

    def _depth(obj):
        if isinstance(obj, dict):
            return 1 + max((_depth(v) for v in obj.values()), default=0)
        elif isinstance(obj, list):
            return 1 + max((_depth(i) for i in obj), default=0)
        return 0

    def _size(obj):
        if isinstance(obj, dict):
            return sum(_size(v) for v in obj.values()) + len(obj)
        elif isinstance(obj, list):
            return sum(_size(i) for i in obj) + len(obj)
        return 1

    return {"input_depth": _depth(inp), "input_size": _size(inp)}


def _expression_frame(jqspider, jqstack) -> pd.DataFrame:
    rows = []

    for b in jqstack:
        expr = b["expressions"][0]
        row = expr_features(expr)
        row["dataset"] = "jqStack"
        row["identifier"] = b["identifier"]
        row["task"] = b["tasks"][0] if b["tasks"] else None
        row["n_expressions"] = len(b["expressions"])
        row["n_inputs"] = len(b["inputs"]) if b["inputs"] else 0
        rows.append(row)

    for b in jqspider:
        expr = b["expressions"][0]
        row = expr_features(expr)
        row["dataset"] = "jqSpider"
        row["identifier"] = b["identifier"]
        row["task"] = "spider"
        row["n_expressions"] = len(b["expressions"])
        row["n_inputs"] = 0
        rows.append(row)
    df = pd.DataFrame(rows)

    return df


def _report_expression_summary(
    df: pd.DataFrame, root_plots: Path, root_tables: Path, show: bool
) -> None:
    write_table(df.head(), root_tables / "table-01.csv")
    summary = df.groupby("dataset").agg(
        count=("identifier", "size"),
        expr_len_median=("length", "median"),
        expr_len_mean=("length", "mean"),
        pipe_median=("n_pipe", "median"),
        pipe_mean=("n_pipe", "mean"),
        pct_def=("has_def", "mean"),
        pct_reduce=("has_reduce", "mean"),
        pct_if=("has_if", "mean"),
        pct_try=("has_try", "mean"),
    )
    summary["pct_def"] = (summary["pct_def"] * 100).round(1)
    summary["pct_reduce"] = (summary["pct_reduce"] * 100).round(1)
    summary["pct_if"] = (summary["pct_if"] * 100).round(1)
    summary["pct_try"] = (summary["pct_try"] * 100).round(1)
    write_table(summary, root_tables / "table-02.csv")

    fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)

    for ax, metric, label in zip(
        axes,
        ["length", "n_pipe"],
        ["expression length (chars)", "# of pipe ( | )"],
    ):
        sns.histplot(
            data=df,
            x=metric,
            hue="dataset",
            stat="density",
            common_norm=False,
            bins=30,
            alpha=0.5,
            ax=ax,
        )
        ax.set_xlabel(label)
        ax.set_ylabel("density" if ax == axes[0] else "")
    plt.tight_layout()
    plt.savefig(root_plots / "datasets-expr-distributions.pdf", bbox_inches="tight")
    finish_figure(show)


def _report_operators(
    jqspider, jqstack, root_plots: Path, root_tables: Path, show: bool
) -> None:
    ops_stack = count_operators(jqstack)
    ops_spider = count_operators(jqspider)
    all_ops = sorted(
        set(ops_stack) | set(ops_spider),
        key=lambda o: -(ops_stack.get(o, 0) + ops_spider.get(o, 0)),
    )
    df_ops = pd.DataFrame(
        {
            "operator": all_ops,
            "jqStack": [100 * ops_stack.get(o, 0) / len(jqstack) for o in all_ops],
            "jqSpider": [100 * ops_spider.get(o, 0) / len(jqspider) for o in all_ops],
        }
    )
    df_ops_top = df_ops.head(20)
    write_table(df_ops_top, root_tables / "table-03.csv")
    df_ops_melt = df_ops_top.melt(
        id_vars="operator", var_name="dataset", value_name="pct"
    )

    fig, ax = plt.subplots(figsize=(10, 5))
    sns.barplot(
        data=df_ops_melt,
        x="operator",
        y="pct",
        hue="dataset",
        ax=ax,
        alpha=0.85,
    )
    ax.set_ylabel("% of benchmarks")
    ax.set_xlabel(None)
    ax.tick_params(axis="x", rotation=45)
    plt.tight_layout()
    plt.savefig(root_plots / "datasets-operator-usage.pdf", bbox_inches="tight")
    finish_figure(show)


def _report_stack_tasks(df: pd.DataFrame, root_plots: Path, show: bool) -> None:
    df_stack = df[df["dataset"] == "jqStack"].copy()

    g = sns.catplot(
        data=df_stack,
        x="task",
        kind="count",
        order=df_stack["task"].value_counts().index,
        height=3.5,
        aspect=2,
        alpha=0.75,
        color=sns.color_palette("Set1")[0],
        saturation=1,
    )
    ax = g.ax
    ymax = ax.get_ylim()[1]
    ax.set_ylim(0, ymax * 1.08)

    for p in ax.patches:
        h = int(p.get_height())
        if h == 0:
            continue
        x = p.get_x() + p.get_width() / 2
        ax.text(x, h + (ymax * 0.01), str(h), ha="center", va="bottom")
    ax.set_xlabel(None)
    ax.set_ylabel(None)
    ax.set_yticks([])
    sns.despine(left=True)
    plt.savefig(root_plots / "stack-task-categories.pdf", bbox_inches="tight")
    finish_figure(show)

    fig, axes = plt.subplots(1, 2, figsize=(14, 4))
    order = (
        df_stack.groupby("task")["length"].median().sort_values(ascending=False).index
    )
    sns.boxplot(
        data=df_stack,
        x="task",
        y="length",
        order=order,
        ax=axes[0],
        showfliers=False,
    )
    axes[0].set_ylabel("expression length (chars)")
    axes[0].set_xlabel(None)
    sns.boxplot(
        data=df_stack,
        x="task",
        y="n_pipe",
        order=order,
        ax=axes[1],
        showfliers=False,
    )
    axes[1].set_ylabel("# of pipe ( | )")
    axes[1].set_xlabel(None)
    plt.tight_layout()
    plt.savefig(root_plots / "stack-task-complexity.pdf", bbox_inches="tight")
    finish_figure(show)

    g = sns.catplot(
        data=df_stack,
        x="n_expressions",
        kind="count",
        height=3,
        aspect=1.5,
        alpha=0.75,
        color=sns.color_palette("Set1")[0],
        saturation=1,
    )
    ax = g.ax
    ymax = ax.get_ylim()[1]
    ax.set_ylim(0, ymax * 1.08)

    for p in ax.patches:
        h = int(p.get_height())
        if h == 0:
            continue
        x = p.get_x() + p.get_width() / 2
        ax.text(x, h + (ymax * 0.01), str(h), ha="center", va="bottom")
    ax.set_xlabel("# of alternative expressions")
    ax.set_ylabel(None)
    ax.set_yticks([])
    sns.despine(left=True)
    plt.savefig(root_plots / "stack-alternative-expressions.pdf", bbox_inches="tight")
    finish_figure(show)


def _report_spider_schemas(
    jqspider, root_plots: Path, root_tables: Path, show: bool
) -> None:
    spider_rows = []

    for b in jqspider:
        db = b["identifier"].rsplit(".", 1)[0]
        s = b["jsonschema"]
        spider_rows.append(
            {
                "identifier": b["identifier"],
                "database": db,
                "n_fields": count_schema_fields(s),
                "depth": schema_depth(s),
                "n_tables": count_top_level_arrays(s),
            }
        )
    df_spider_schema = pd.DataFrame(spider_rows)
    df_spider_db = df_spider_schema.groupby("database").first().reset_index()
    print(f"Unique databases: {len(df_spider_db)}")
    write_table(
        df_spider_db[["database", "n_tables", "depth", "n_fields"]].describe(),
        root_tables / "table-04.csv",
    )
    ct = (
        df_spider_db.groupby(["depth", "n_tables"])
        .size()
        .unstack(fill_value=0)
        .sort_index(axis=0)
        .sort_index(axis=1)
    )
    annot = ct.astype(object)
    annot[annot == 0] = ""
    base = sns.color_palette("Set1")[0]
    colors = [(base[0], base[1], base[2], a) for a in np.linspace(0, 0.75, 8)]
    cmap = LinearSegmentedColormap.from_list("alpha_base", colors)

    fig, ax = plt.subplots(figsize=(5, 4))
    sns.heatmap(
        ct,
        cmap=cmap,
        cbar=False,
        annot=annot,
        fmt="",
        annot_kws={"color": "black"},
        ax=ax,
    )
    ax.grid(False)
    ax.set_xlabel("# of tables")
    ax.set_ylabel("nesting depth")
    ax.invert_yaxis()
    plt.tight_layout()
    plt.savefig(root_plots / "spider-schema-heatmap.pdf", bbox_inches="tight")
    finish_figure(show)

    bmarks_per_db = (
        df_spider_schema.groupby("database").size().sort_values(ascending=False)
    )

    fig, ax = plt.subplots(figsize=(12, 4))
    bmarks_per_db.plot.bar(ax=ax, color=sns.color_palette("Set1")[0], alpha=0.75)
    ax.set_ylabel("# of benchmarks")
    ax.set_xlabel(None)
    ax.tick_params(axis="x", rotation=45)
    plt.tight_layout()
    plt.savefig(root_plots / "spider-benchmarks-per-db.pdf", bbox_inches="tight")
    finish_figure(show)


def _report_stack_inputs(jqstack, root_plots: Path, show: bool) -> None:
    input_rows = []

    for b in jqstack:
        if not b["inputs"]:
            continue
        for inp in b["inputs"]:
            ic = input_complexity(inp)
            ic["identifier"] = b["identifier"]
            ic["task"] = b["tasks"][0] if b["tasks"] else None
            input_rows.append(ic)
    df_inputs = pd.DataFrame(input_rows)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    sns.histplot(
        data=df_inputs,
        x="input_depth",
        bins=range(0, df_inputs["input_depth"].max() + 2),
        ax=axes[0],
        alpha=0.75,
        color=sns.color_palette("Set1")[0],
    )
    axes[0].set_xlabel("input nesting depth")
    axes[0].set_ylabel("count")
    sns.histplot(
        data=df_inputs,
        x="input_size",
        bins=30,
        ax=axes[1],
        alpha=0.75,
        color=sns.color_palette("Set1")[0],
    )
    axes[1].set_xlabel("input size (# nodes)")
    axes[1].set_ylabel("count")
    plt.tight_layout()
    plt.savefig(root_plots / "stack-input-complexity.pdf", bbox_inches="tight")
    finish_figure(show)


def _report_feature_comparison(df: pd.DataFrame, root_plots: Path, show: bool) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    for dataset, color in zip(["jqStack", "jqSpider"], sns.color_palette("Set1")):
        subset = df[df["dataset"] == dataset]
        sorted_lens = np.sort(subset["length"].values)
        cdf = np.arange(1, len(sorted_lens) + 1) / len(sorted_lens)
        axes[0].plot(sorted_lens, cdf, label=dataset, color=color, lw=2)
    axes[0].set_xlabel("expression length (chars)")
    axes[0].set_ylabel("CDF")
    axes[0].legend()

    for dataset, color in zip(["jqStack", "jqSpider"], sns.color_palette("Set1")):
        subset = df[df["dataset"] == dataset]
        sorted_pipes = np.sort(subset["n_pipe"].values)
        cdf = np.arange(1, len(sorted_pipes) + 1) / len(sorted_pipes)
        axes[1].plot(sorted_pipes, cdf, label=dataset, color=color, lw=2)
    axes[1].set_xlabel("# of pipe ( | )")
    axes[1].set_ylabel("CDF")
    axes[1].legend()
    plt.tight_layout()
    plt.savefig(root_plots / "datasets-cdf-comparison.pdf", bbox_inches="tight")
    finish_figure(show)

    features = ["has_def", "has_reduce", "has_if", "has_try", "has_recurse"]
    feature_labels = [
        "def (functions)",
        "reduce",
        "if/then/else",
        "try/catch",
        "recurse",
    ]
    feat_rows = []

    for feat, label in zip(features, feature_labels):
        for ds in ["jqStack", "jqSpider"]:
            pct = df[df["dataset"] == ds][feat].mean() * 100
            feat_rows.append({"feature": label, "dataset": ds, "pct": pct})
    df_feats = pd.DataFrame(feat_rows)

    fig, ax = plt.subplots(figsize=(8, 4))
    sns.barplot(
        data=df_feats,
        x="feature",
        y="pct",
        hue="dataset",
        ax=ax,
        alpha=0.85,
    )
    ax.set_ylabel("% of benchmarks")
    ax.set_xlabel(None)
    ax.tick_params(axis="x", rotation=20)
    plt.tight_layout()
    plt.savefig(root_plots / "datasets-feature-comparison.pdf", bbox_inches="tight")
    finish_figure(show)


def generate(output: Path, *, show: bool = False) -> None:
    root_tables = output / "datasets" / "tables"
    root_tables.mkdir(parents=True, exist_ok=True)
    configure_plots(show=show)
    root_plots = output / "datasets" / "plots"
    root_plots.mkdir(parents=True, exist_ok=True)
    jqstack = load("jqStack", path=paths.data).model_dump(mode="json")["benchmarks"]
    jqspider = load("jqSpider", path=paths.data).model_dump(mode="json")["benchmarks"]
    print(f"jqStack:  {len(jqstack):,} benchmarks")
    print(f"jqSpider: {len(jqspider):,} benchmarks")
    df = _expression_frame(jqspider, jqstack)
    _report_expression_summary(df, root_plots, root_tables, show)
    _report_operators(jqspider, jqstack, root_plots, root_tables, show)
    _report_stack_tasks(df, root_plots, show)
    _report_spider_schemas(jqspider, root_plots, root_tables, show)
    _report_stack_inputs(jqstack, root_plots, show)
    _report_feature_comparison(df, root_plots, show)


def main(argv: list[str] | None = None) -> None:
    args = arguments(__doc__, argv)
    generate(args.output, show=args.show)


if __name__ == "__main__":
    main()
