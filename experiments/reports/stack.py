"""Stack analysis from supplied benchmark artifacts."""

import json
import re
import warnings
from collections import Counter
from difflib import SequenceMatcher
from itertools import product
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap, LogNorm
from scipy.stats import kruskal, pearsonr, spearmanr
from scipy.stats import t as t_dist
from upsetplot import UpSet, from_indicators

from experiments.paths import paths
from experiments.reports import arguments, configure_plots, finish_figure, write_table
from jqbench import load


def annotate_bars(ax):
    ymax = ax.get_ylim()[1]
    for p in ax.patches:
        h = int(p.get_height())
        if h == 0:
            continue
        ax.text(
            p.get_x() + p.get_width() / 2,
            h + (ymax * 0.01),
            str(h),
            ha="center",
            va="bottom",
        )


def annotate_stacked(ax):
    for p in ax.patches:
        h_val = p.get_height()
        if h_val == 0:
            continue
        h = str(int(h_val))
        top = p.get_y() + p.get_height()
        ax.text(
            p.get_x() + p.get_width() / 2,
            top * 1.05,
            h,
            ha="center",
            va="bottom",
        )


def sim(a, b):
    a = a.replace(" ", "").replace("\n", "")
    b = b.replace(" ", "").replace("\n", "")
    return SequenceMatcher(None, a, b).ratio()


def sim_all(candidates: list[str], expressions: list[str]):
    if not candidates:
        return np.nan
    return np.mean([sim(a, b) for a, b in product(candidates, expressions)])


def expr_features(expr: str) -> dict:
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


def build_traj_rows(trajectories, model_name):
    rows = []
    for r in trajectories:
        n_execs = len(r["executions"])
        n_tests = len(r["environment"]["tests"])
        n_candidates = len(r["environment"]["candidates"])
        add_test = 0
        run_tests = 0
        for h in r.get("history", []):
            if "tool_calls" in h:
                for tc in h["tool_calls"]:
                    name = tc["function"]["name"]
                    if name == "add_test":
                        add_test += 1
                    elif name == "run_tests":
                        run_tests += 1
        first_pass_rate = 0.0
        if n_execs > 0 and r["executions"][0]["results"]:
            results = r["executions"][0]["results"]
            first_pass_rate = sum(
                1 for res in results if res["outcome"] == "Pass"
            ) / len(results)
        last_pass_rate = 0.0
        if n_execs > 0 and r["executions"][-1]["results"]:
            results = r["executions"][-1]["results"]
            last_pass_rate = sum(
                1 for res in results if res["outcome"] == "Pass"
            ) / len(results)
        final_expr = r["environment"]["candidates"][-1] if n_candidates > 0 else ""
        feats = expr_features(final_expr)
        rows.append(
            {
                "identifier": r["identifier"],
                "model": model_name,
                "expression": final_expr,
                "n_iterations": n_execs,
                "n_tests": n_tests,
                "n_candidates": n_candidates,
                "add_test_calls": add_test,
                "run_test_calls": run_tests,
                "tests_added_beyond_initial": max(0, add_test - n_tests),
                "first_pass_rate": first_pass_rate,
                "last_pass_rate": last_pass_rate,
                **feats,
            }
        )
    return rows


def parse_doc_functions(doc_path=paths.docs / "index.md"):
    doc = doc_path.read_text(encoding="utf-8")
    return [
        e
        for f in re.findall(r"`(.+?)`", doc)
        if re.match(r"^@?[a-zA-Z_]+$", e := f.strip('"').split("(")[0]) is not None
    ]


def get_functions(expression, doc_functions):
    return [f for f in doc_functions if re.search(rf"\b{f}\b", expression)]


def max_nesting_depth(expr):
    """Max depth of (), [], {} nesting."""
    depth = max_depth = 0
    for ch in expr:
        if ch in "([{":
            depth += 1
            max_depth = max(max_depth, depth)
        elif ch in ")]}":
            depth = max(0, depth - 1)
    return max_depth


def count_variable_bindings(expr):
    """Count 'as $var' patterns."""
    return len(re.findall(r"\bas\s+\$", expr))


def count_control_flow(expr):
    """Count control flow constructs: if, try, reduce, foreach, label, //,  ?."""
    keywords = len(re.findall(r"\b(if|try|reduce|foreach|label|until|limit)\b", expr))
    alt_op = expr.count("//")
    optional = len(re.findall(r"\.\w+\?", expr))  # .foo? patterns
    return keywords + alt_op + optional


def count_constructions(expr):
    """Count object {} and array [] construction sites."""
    return expr.count("{") + expr.count("[")


def count_string_interpolations(expr):
    r"""Count \(...) string interpolation patterns."""
    return len(re.findall(r"\\\(", expr))


def _report_pipeline(root: Path, root_plots: Path, root_tables: Path, show: bool):
    with open(root / "a_find" / "status.json", encoding="utf-8") as f:
        find_status = json.load(f)

    with open(root / "b_extract" / "extracted.json", encoding="utf-8") as f:
        extracted = json.load(f)
    n_posts = sum(1 for _ in open(root / "a_find" / "posts.jsonl", encoding="utf-8"))
    n_extracted = len(extracted)
    convert_counts = {}

    for name in ["converted-gpt5chat", "converted-claudeopus46", "converted-gpt52chat"]:
        with open(root / "c_convert" / f"{name}.json", encoding="utf-8") as f:
            successes = len(json.load(f))
        with open(root / "c_convert" / f"{name}-failures.json", encoding="utf-8") as f:
            failures = len(json.load(f))
        label = name.replace("converted-", "")
        convert_counts[label] = {
            "success": successes,
            "failure": failures,
            "total": successes + failures,
        }
    n_converted_total = sum(v["success"] for v in convert_counts.values())

    with open(root / "d_collect" / "collected.json", encoding="utf-8") as f:
        collected = json.load(f)["benchmarks"]
    n_collected = len(collected)
    filtered_counts = {}

    for name in ["filtered-gpt5chat", "filtered-claudeopus41"]:
        with open(root / "e_filtered" / f"{name}.json", encoding="utf-8") as f:
            filtered_counts[name.replace("filtered-", "")] = len(
                json.load(f)["benchmarks"]
            )

    with open(root / "f_fixes" / "fixes-1.json", encoding="utf-8") as f:
        fixes = json.load(f)
    n_fixes_skipped = sum(1 for fix in fixes if fix.get("skipped", False))
    n_fixes_applied = len(fixes) - n_fixes_skipped
    jqstack = load("jqStack", path=paths.data).model_dump(mode="json")["benchmarks"]
    n_final = len(jqstack)
    print("=== Pipeline Funnel ===")
    print(f"Matches found (a_find):       {len(find_status['matches']):>7,}")
    print(f"Posts downloaded (a_find):     {n_posts:>7,}")
    print(f"Extracted Q&A (b_extract):    {n_extracted:>7,}")
    print()

    for model, v in convert_counts.items():
        print(
            f"Converted \u2014 {model}:  {v['success']:>6,} success / {v['failure']:>4,} failure  (total: {v['total']:>6,})"
        )
    print(f"Total converted (success):    {n_converted_total:>7,}")
    print()
    print(f"Collected (d_collect):        {n_collected:>7,}")

    for model, count in filtered_counts.items():
        print(f"Filtered \u2014 {model}:       {count:>7,}")
    print(
        f"Fixes checked (f_fixes):      {len(fixes):>7,}  (applied: {n_fixes_applied}, skipped: {n_fixes_skipped})"
    )
    print(f"Final jqStack (g_fixed):      {n_final:>7,}")
    funnel_labels = [
        "a_find\nmatches",
        "a_find\nposts",
        "b_extract",
    ]
    funnel_values = [
        len(find_status["matches"]),
        n_posts,
        n_extracted,
    ]

    for model, v in convert_counts.items():
        funnel_labels.append(f"c_convert\n{model}")
        funnel_values.append(v["success"])
    funnel_labels += ["d_collect", "g_fixed\n(jqStack)"]
    funnel_values += [n_collected, n_final]

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.bar(
        range(len(funnel_labels)),
        funnel_values,
        color=sns.color_palette("Set2", len(funnel_labels)),
    )
    ax.set_xticks(range(len(funnel_labels)))
    ax.set_xticklabels(funnel_labels, fontsize=12)
    ax.set_ylabel("Number of cases")
    ax.set_title("Pipeline Funnel: Cases at Each Step")

    for i, val in enumerate(funnel_values):
        ax.text(
            i,
            val + max(funnel_values) * 0.01,
            f"{val:,}",
            ha="center",
            va="bottom",
            fontsize=11,
        )
    sns.despine()
    plt.tight_layout()
    plt.savefig(root_plots / "stack-pipeline-funnel.pdf", bbox_inches="tight")
    finish_figure(show)

    found_df = pd.DataFrame(
        list(find_status["found"].items()), columns=["Keyword", "Count"]
    )
    found_df = found_df.sort_values("Count", ascending=False).reset_index(drop=True)
    write_table(found_df, root_tables / "table-01.csv")
    type_counts = Counter(m["type"] for m in find_status["matches"])
    print("Match types:", dict(type_counts))
    convert_rate_df = pd.DataFrame(
        [
            {
                "Model": model,
                "Success": v["success"],
                "Failure": v["failure"],
                "Rate": f"{v['success'] / v['total'] * 100:.1f}%",
            }
            for model, v in convert_counts.items()
        ]
    )
    write_table(convert_rate_df, root_tables / "table-02.csv")

    return extracted, collected, jqstack


def _report_filtering(root_plots: Path, root_tables: Path, show: bool) -> None:
    filter_root = paths.results / "filter" / "kind=InputOutput-which=AllButOne"
    filter_files = {
        "Gpt5Chat (jqStack)": "jqStack-JqSampler-Gpt5Chat.json",
        "ClaudeOpus41 (jqStackFiltered)": "jqStackFiltered-JqSampler-ClaudeOpus41.json",
    }
    filter_rows = []

    for label, fname in filter_files.items():
        with open(filter_root / fname, encoding="utf-8") as f:
            data = json.load(f)
        sols = data["solutions"]
        total = len(sols)
        metrics_list = [s["predictions"][0]["metrics"] for s in sols]
        compiles = sum(m["compiles"] for m in metrics_list)
        executes = sum(m["executes"] for m in metrics_list)
        exact = sum(m["exact_match"] for m in metrics_list)
        value_match = sum(
            1 for m in metrics_list if m["value_match"] in ("Exact", "Unwrapped")
        )
        filter_rows.append(
            {
                "Model": label,
                "Total": total,
                "Compiles": compiles,
                "Executes": executes,
                "Value Match": value_match,
                "Exact Match": exact,
                "Compile %": f"{compiles / total * 100:.1f}%",
                "Execute %": f"{executes / total * 100:.1f}%",
                "Value Match %": f"{value_match / total * 100:.1f}%",
                "Exact Match %": f"{exact / total * 100:.1f}%",
            }
        )
    filter_df = pd.DataFrame(filter_rows)
    print("=== Filtering Success Rate (InputOutput, AllButOne) ===")
    write_table(
        filter_df[
            [
                "Model",
                "Total",
                "Compiles",
                "Compile %",
                "Executes",
                "Execute %",
                "Value Match",
                "Value Match %",
                "Exact Match",
                "Exact Match %",
            ]
        ],
        root_tables / "table-03.csv",
    )
    filter_result_files = {
        "Gpt5Chat": "jqStack-JqSampler-Gpt5Chat.json",
        "ClaudeOpus41": "jqStackFiltered-JqSampler-ClaudeOpus41.json",
    }
    solve_records = []

    for model_label, fname in filter_result_files.items():
        with open(filter_root / fname, encoding="utf-8") as f:
            data = json.load(f)
        for sol in data["solutions"]:
            m = sol["predictions"][0]["metrics"]
            if m["value_match"] in ("Exact", "Unwrapped"):
                solve_records.append(
                    {"identifier": sol["identifier"], "model": model_label}
                )
    df_solve = pd.DataFrame(solve_records)
    models = sorted(df_solve["model"].unique())
    coverage = (
        df_solve.assign(solved=1)
        .pivot_table(index="identifier", columns="model", values="solved", fill_value=0)
        .astype(bool)
    )
    upset_input = from_indicators(models, coverage.reset_index())

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", category=FutureWarning, module="upsetplot.plotting"
        )
        fig = plt.figure(figsize=(9, 6))
        ax = UpSet(
            upset_input,
            subset_size="count",
            sort_categories_by=None,
            sort_by="cardinality",
            with_lines=False,
            min_subset_size=5,
            facecolor="#e41a1c",
        ).plot(fig=fig)

        for p in ax["intersections"].patches:
            p.set_alpha(0.75)
        for p in ax["totals"].patches:
            p.set_alpha(0.75)
        for coll in ax["matrix"].collections:
            alpha = coll.get_facecolor()[:, -1]
            alpha[alpha == 1.0] = 0.75
            face = coll.get_facecolor()
            face[:, -1] = alpha
            coll.set_facecolor(face)
            coll.set_edgecolor(face)
    ax["intersections"].grid(visible=False)
    ax["intersections"].set_ylabel("Intersection")
    ax["totals"].grid(visible=False)
    ax["totals"].set_xlabel("Total")
    ax["totals"].invert_yaxis()
    ax["totals"].xaxis.tick_top()
    fig.savefig(root_plots / "stack-filter-upset.pdf", bbox_inches="tight")
    finish_figure(show)


def _report_benchmarks(
    collected, jqstack, root_plots: Path, root_tables: Path, show: bool
) -> None:
    df_bench = pd.DataFrame(
        [
            {
                "id": b["identifier"],
                "tests": len(b["inputs"]),
                "expressions": len(b["expressions"]),
                "task": b["tasks"][0] if b["tasks"] else None,
            }
            for b in jqstack
        ]
    )

    g = sns.catplot(
        data=df_bench,
        x="tests",
        kind="count",
        height=3,
        aspect=2,
        alpha=0.75,
        color=sns.color_palette("Set1")[0],
        saturation=1,
    )
    ax = g.ax
    ax.set_xlabel("# of tests")
    ax.set_ylabel(None)
    ax.set_yticks([])
    annotate_bars(ax)
    sns.despine(left=True)
    plt.savefig(root_plots / "stack-tests-distribution.pdf", bbox_inches="tight")
    finish_figure(show)

    df_collected = pd.DataFrame(
        [
            {
                "id": b["identifier"],
                "task": b["tasks"][0] if b["tasks"] else None,
                "stage": "collected",
            }
            for b in collected
        ]
    )
    df_final = pd.DataFrame(
        [
            {
                "id": b["identifier"],
                "task": b["tasks"][0] if b["tasks"] else None,
                "stage": "jqStack",
            }
            for b in jqstack
        ]
    )
    task_counts = (
        pd.DataFrame(
            {
                "Collected": df_collected["task"].value_counts(),
                "jqStack": df_final["task"].value_counts(),
            }
        )
        .fillna(0)
        .astype(int)
    )
    task_counts = task_counts.sort_values("Collected", ascending=False)
    write_table(task_counts, root_tables / "table-04.csv")
    task_counts["Retention %"] = (
        task_counts["jqStack"] / task_counts["Collected"] * 100
    ).round(1)
    write_table(task_counts, root_tables / "table-05.csv")
    final_ids = {b["identifier"] for b in jqstack}
    df_task_stage = pd.DataFrame(
        [
            {
                "task": b["tasks"][0] if b["tasks"] else None,
                "kept": b["identifier"] in final_ids,
            }
            for b in collected
        ]
    )
    df_task_stage["task"] = (
        df_task_stage["task"].replace({"other": "Complex"}).str.capitalize()
    )
    df_task_stage["task"] = pd.Categorical(
        df_task_stage["task"],
        categories=df_task_stage["task"]
        .value_counts()
        .sort_values(ascending=False)
        .index,
        ordered=True,
    )

    fig, ax = plt.subplots(figsize=(8, 4))
    sns.histplot(
        data=df_task_stage,
        x="task",
        hue="kept",
        multiple="stack",
        discrete=True,
        ax=ax,
    )

    for p in ax.patches:
        if p.get_y() <= 0:
            old_h = p.get_height()
            p.set_y(0.5)
            p.set_height(max(old_h - 0.5, 0))
    ax.set_yscale("log")
    ax.grid(visible=False)
    ax.legend_.set_title("Kept")
    plt.xticks(rotation=45, ha="right")
    plt.xlabel(None)
    plt.ylabel(None)
    annotate_stacked(ax)
    ylo, yhi = ax.get_ylim()
    ax.set_ylim(ylo, yhi * 4)
    ax.legend_.set_bbox_to_anchor((1.0, 1.02))
    plt.savefig(root_plots / "stack-tasks-collected-vs-final.pdf", bbox_inches="tight")
    finish_figure(show)


def _report_similarity(extracted, jqstack, root_plots: Path, show: bool):
    extracted_by_id = {}

    for e in extracted:
        eid = e["id"]
        candidates = [
            c["jq"]
            for c in e.get("expressions", [])
            if isinstance(c, dict) and "jq" in c
        ]
        if candidates:
            extracted_by_id[eid] = candidates
    sim_rows = []

    for b in jqstack:
        bid = b["identifier"]
        candidates = extracted_by_id.get(bid) or extracted_by_id.get(str(bid), [])
        expressions = b["expressions"]
        sim_rows.append(
            {
                "id": bid,
                "candidates": candidates,
                "expressions": expressions,
                "similarity": sim_all(candidates, expressions),
            }
        )
    df_sim = pd.DataFrame(sim_rows)
    print(f"Matched: {df_sim['similarity'].notna().sum()} / {len(df_sim)}")
    height = 3
    aspect = 2
    plt.figure(figsize=(height * aspect, height))
    ax = sns.histplot(df_sim.similarity.dropna(), bins=10)
    ax.set_ylabel(None)
    ax.set_xlabel("Similarity")
    ax.set_yticks([])
    ax.grid(False)
    sns.despine(left=True)
    plt.savefig(root_plots / "stack-similarity.pdf", bbox_inches="tight")
    finish_figure(show)

    return extracted_by_id, df_sim


def _report_trajectories(root: Path, root_plots: Path, root_tables: Path, show: bool):
    with open(root / "c_convert" / "converted-gpt5chat.json", encoding="utf-8") as f:
        trajectories_gpt = json.load(f)

    with open(
        root / "c_convert" / "converted-claudeopus46.json", encoding="utf-8"
    ) as f:
        trajectories_claude = json.load(f)
    print(f"Trajectories (GPT): {len(trajectories_gpt):,}")
    print(f"Trajectories (Claude): {len(trajectories_claude):,}")
    df_traj = pd.DataFrame(
        build_traj_rows(trajectories_gpt, "Gpt5Chat")
        + build_traj_rows(trajectories_claude, "ClaudeOpus46")
    )
    df_traj["n_iterations"] = df_traj["n_iterations"].clip(upper=8)
    print(f"Total trajectories: {len(df_traj):,}")
    write_table(df_traj.describe(), root_tables / "table-06.csv")

    g = sns.catplot(
        data=df_traj,
        x="n_iterations",
        kind="count",
        height=3,
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
    ax.set_xlabel("# of iterations (expression attempts)")
    ax.set_ylabel(None)
    ax.set_yticks([])
    sns.despine(left=True)
    plt.savefig(root_plots / "stack-iteration-distribution.pdf", bbox_inches="tight")
    finish_figure(show)

    return trajectories_gpt, trajectories_claude, df_traj


def _report_trajectory_complexity(
    df_traj: pd.DataFrame, root_plots: Path, show: bool
) -> None:
    doc_functions = parse_doc_functions()
    fn_usage = Counter()

    for expr in df_traj["expression"]:
        fn_usage.update(set(get_functions(expr, doc_functions)))
    rows_extra = []

    for _, row in df_traj.iterrows():
        expr = row["expression"]
        funcs = get_functions(expr, doc_functions)
        unique_funcs = set(funcs)
        n_func = len(funcs)
        weighted_unique = sum(
            1.0 / fn_usage[f] for f in unique_funcs if fn_usage[f] > 0
        )
        avg_rarity = (
            sum(1.0 / fn_usage[f] for f in funcs if fn_usage[f] > 0) / n_func
            if n_func > 0
            else 0.0
        )
        rows_extra.append(
            {
                "n_functions": n_func,
                "weighted_unique_fn": weighted_unique,
                "rarity": avg_rarity,
                "nesting_depth": max_nesting_depth(expr),
                "variable_bindings": count_variable_bindings(expr),
                "control_flow": count_control_flow(expr),
                "constructions": count_constructions(expr),
                "string_interp": count_string_interpolations(expr),
            }
        )
    df_extra = pd.DataFrame(rows_extra)

    for col in df_extra.columns:
        df_traj[col] = df_extra[col].values
    metrics = [
        ("n_functions", "Functions"),
        ("weighted_unique_fn", "Weighted unique fn."),
        ("n_pipe", "Pipes"),
        ("length", "Length (chars)"),
        ("rarity", "Rarity"),
        ("nesting_depth", "Nesting depth"),
        ("variable_bindings", "Variable bindings"),
        ("control_flow", "Control flow"),
        ("constructions", "Constructions"),
        ("string_interp", "String interpolation"),
    ]

    for model in ["Gpt5Chat", "ClaudeOpus46"]:
        df_m = df_traj[df_traj["model"] == model]
        print(f"=== Pearson correlations with n_iterations — {model} ===")
        for col, label in sorted(
            metrics,
            key=lambda m: abs(pearsonr(df_m[m[0]], df_m["n_iterations"])[0]),
            reverse=True,
        ):
            r_val, p_val = pearsonr(df_m[col], df_m["n_iterations"])
            sig = (
                "***"
                if p_val < 0.001
                else "**"
                if p_val < 0.01
                else "*"
                if p_val < 0.05
                else ""
            )
            print(f"  {label:<25s}  r = {r_val:+.3f}  p = {p_val:.4f} {sig}")
        print()
    n_metrics = len(metrics)
    ncols = 5
    nrows = (n_metrics + ncols - 1) // ncols

    for model in ["Gpt5Chat", "ClaudeOpus46"]:
        df_m = df_traj[df_traj["model"] == model]
        fig, axes = plt.subplots(
            nrows, ncols, figsize=(4 * ncols, 4 * nrows), sharey=True
        )
        axes = axes.flatten()

        for ax, (col, label) in zip(axes, metrics):
            sns.regplot(
                data=df_m,
                x=col,
                y="n_iterations",
                ax=ax,
                scatter_kws={"s": 40, "alpha": 0.4},
                line_kws={"color": "black", "lw": 2},
                x_jitter=0.3,
                y_jitter=0.2,
            )
            r_val, p_val = pearsonr(df_m[col], df_m["n_iterations"])
            sig = (
                "***"
                if p_val < 0.001
                else "**"
                if p_val < 0.01
                else "*"
                if p_val < 0.05
                else ""
            )
            ax.set_xlabel(label)
            ax.set_title(f"r = {r_val:.3f}{sig}")
            if ax in axes[::ncols]:
                ax.set_ylabel("# of iterations")
            else:
                ax.set_ylabel(None)

        for ax in axes[n_metrics:]:
            ax.set_visible(False)
        fig.suptitle(model, fontsize=16, y=1.01)
        plt.tight_layout()
        plt.savefig(
            root_plots / f"stack-complexity-vs-iterations-{model}.pdf",
            bbox_inches="tight",
        )
        finish_figure(show)


def _report_iteration_distribution(
    _cmap_red, df_traj: pd.DataFrame, root_plots: Path, show: bool
) -> None:
    models = ["Gpt5Chat", "ClaudeOpus46"]
    display_names = {"Gpt5Chat": "gpt-5", "ClaudeOpus46": "opus-4.6"}

    fig, axes = plt.subplots(2, 1, figsize=(8, 6))
    all_iters = sorted(df_traj["n_iterations"].unique())

    for ax, model in zip(axes, models):
        df_m = df_traj[df_traj["model"] == model]
        r_val, p_val = pearsonr(df_m["n_pipe"], df_m["n_iterations"])

        # Build count matrix with consistent iteration index
        ct = df_m.groupby(["n_pipe", "n_iterations"]).size().reset_index(name="count")
        pivot = ct.pivot(index="n_iterations", columns="n_pipe", values="count").fillna(
            0
        )
        pivot = pivot.reindex(all_iters, fill_value=0)

        # Heatmap of counts (log-scale colour norm for better contrast)
        pivot_display = pivot.replace(0, np.nan)
        sns.heatmap(
            pivot_display.iloc[::-1],
            cmap=_cmap_red,
            norm=LogNorm(vmin=1),
            linewidths=0.3,
            linecolor="white",
            ax=ax,
            cbar_kws={"label": "Count", "shrink": 0.8},
            square=False,
        )

        # Regression line + 95% confidence band overlay
        pipe_vals = np.array(sorted(pivot.columns))
        iter_vals = np.array(sorted(pivot.index))
        x = df_m["n_pipe"].values.astype(float)
        y = df_m["n_iterations"].values.astype(float)
        n = len(x)
        slope, intercept = np.polyfit(x, y, 1)
        x_fit = np.linspace(pipe_vals.min(), pipe_vals.max(), 100)
        y_fit = slope * x_fit + intercept

        # Standard error of the regression prediction
        x_mean = x.mean()
        residuals = y - (slope * x + intercept)
        se_residuals = np.sqrt(np.sum(residuals**2) / (n - 2))
        se_line = se_residuals * np.sqrt(
            1 / n + (x_fit - x_mean) ** 2 / np.sum((x - x_mean) ** 2)
        )
        t_crit = t_dist.ppf(0.975, df=n - 2)
        y_upper = y_fit + t_crit * se_line
        y_lower = y_fit - t_crit * se_line

        # Convert to heatmap axes (column index, inverted row index)
        x_hm = np.interp(x_fit, pipe_vals, np.arange(len(pipe_vals))) + 0.5
        y_hm = np.interp(y_fit, iter_vals, np.arange(len(iter_vals)))
        y_hm = len(iter_vals) - y_hm - 0.5
        y_upper_hm = np.interp(y_upper, iter_vals, np.arange(len(iter_vals)))
        y_upper_hm = len(iter_vals) - y_upper_hm - 0.5
        y_lower_hm = np.interp(y_lower, iter_vals, np.arange(len(iter_vals)))
        y_lower_hm = len(iter_vals) - y_lower_hm - 0.5
        ax.plot(x_hm, y_hm, color="black", lw=2.5, ls="--")
        ax.fill_between(x_hm, y_upper_hm, y_lower_hm, color="black", alpha=0.15)
        ax.grid(False)
        ax.set_title(f"{display_names[model]}  (r = {r_val:.3f})")
        ax.set_xlabel("# of pipes")
        ax.set_ylabel("# of iterations")
    plt.tight_layout()
    plt.savefig(root_plots / "stack-pipes-vs-iterations.pdf", bbox_inches="tight")
    finish_figure(show)


def _report_similarity_iterations(
    _cmap_red,
    collected,
    df_sim: pd.DataFrame,
    df_traj: pd.DataFrame,
    extracted_by_id,
    root_plots: Path,
    show: bool,
) -> None:
    df_traj_sim = df_traj.merge(
        df_sim[["id", "similarity"]].dropna(),
        left_on="identifier",
        right_on="id",
        how="inner",
    )
    df_traj_sim["sim_bin"] = (df_traj_sim["similarity"] * 10).round().astype(int) / 10
    models = ["Gpt5Chat", "ClaudeOpus46"]
    display_names = {"Gpt5Chat": "gpt-5", "ClaudeOpus46": "opus-4.6"}

    fig, axes = plt.subplots(2, 1, figsize=(8, 6))
    all_iters = sorted(df_traj_sim["n_iterations"].unique())

    for ax, model in zip(axes, models):
        df_m = df_traj_sim[df_traj_sim["model"] == model]
        r_val, p_val = pearsonr(df_m["similarity"], df_m["n_iterations"])
        ct = df_m.groupby(["sim_bin", "n_iterations"]).size().reset_index(name="count")
        pivot = ct.pivot(
            index="n_iterations", columns="sim_bin", values="count"
        ).fillna(0)
        pivot = pivot.reindex(all_iters, fill_value=0)
        pivot_display = pivot.replace(0, np.nan)
        sns.heatmap(
            pivot_display.iloc[::-1],
            cmap=_cmap_red,
            norm=LogNorm(vmin=1),
            linewidths=0.3,
            linecolor="white",
            ax=ax,
            cbar_kws={"label": "Count", "shrink": 0.8},
            square=False,
        )

        # Show x-tick labels only at 0.2 intervals
        xtick_positions = ax.get_xticks()
        xtick_labels = [t.get_text() for t in ax.get_xticklabels()]
        ax.set_xticks(xtick_positions)
        ax.set_xticklabels(
            [
                lbl if float(lbl) % 0.2 < 0.01 or float(lbl) % 0.2 > 0.19 else ""
                for lbl in xtick_labels
            ]
        )

        # Regression line + 95% CI overlay
        sim_vals = np.array(sorted(pivot.columns))
        iter_vals = np.array(sorted(pivot.index))
        x = df_m["similarity"].values.astype(float)
        y = df_m["n_iterations"].values.astype(float)
        n = len(x)
        slope, intercept = np.polyfit(x, y, 1)
        x_fit = np.linspace(sim_vals.min(), sim_vals.max(), 100)
        y_fit = slope * x_fit + intercept
        x_mean = x.mean()
        residuals = y - (slope * x + intercept)
        se_residuals = np.sqrt(np.sum(residuals**2) / (n - 2))
        se_line = se_residuals * np.sqrt(
            1 / n + (x_fit - x_mean) ** 2 / np.sum((x - x_mean) ** 2)
        )
        t_crit = t_dist.ppf(0.975, df=n - 2)
        y_upper = y_fit + t_crit * se_line
        y_lower = y_fit - t_crit * se_line

        # Map to heatmap coordinates
        x_hm = np.interp(x_fit, sim_vals, np.arange(len(sim_vals))) + 0.5
        y_hm = np.interp(y_fit, iter_vals, np.arange(len(iter_vals)))
        y_hm = len(iter_vals) - y_hm - 0.5
        y_upper_hm = np.interp(y_upper, iter_vals, np.arange(len(iter_vals)))
        y_upper_hm = len(iter_vals) - y_upper_hm - 0.5
        y_lower_hm = np.interp(y_lower, iter_vals, np.arange(len(iter_vals)))
        y_lower_hm = len(iter_vals) - y_lower_hm - 0.5
        ax.plot(x_hm, y_hm, color="black", lw=2.5, ls="--")
        ax.fill_between(x_hm, y_upper_hm, y_lower_hm, color="black", alpha=0.15)
        ax.grid(False)
        ax.set_title(f"{display_names[model]}  (r = {r_val:.3f})")
        ax.set_xlabel("Candidate similarity")
        ax.set_ylabel("# of iterations")
    plt.tight_layout()
    plt.savefig(root_plots / "stack-similarity-vs-iterations.pdf", bbox_inches="tight")
    finish_figure(show)

    sim_rows_all = []

    for b in collected:
        bid = b["identifier"]
        candidates = extracted_by_id.get(bid) or extracted_by_id.get(str(bid), [])
        expressions = b["expressions"]
        sim_rows_all.append(
            {
                "id": bid,
                "similarity": sim_all(candidates, expressions),
            }
        )
    df_sim_all = pd.DataFrame(sim_rows_all)
    df_traj_sim_all = df_traj.merge(
        df_sim_all[["id", "similarity"]].dropna(),
        left_on="identifier",
        right_on="id",
        how="inner",
    )
    df_traj_sim_all["sim_bin"] = (df_traj_sim_all["similarity"] * 10).round().astype(
        int
    ) / 10
    print(
        f"Benchmarks: {len(df_traj_sim_all):,} (was {len(df_traj_sim):,} jqStack only)"
    )
    models = ["Gpt5Chat", "ClaudeOpus46"]
    display_names = {"Gpt5Chat": "gpt-5", "ClaudeOpus46": "opus-4.6"}

    fig, axes = plt.subplots(2, 1, figsize=(8, 6))
    all_iters = sorted(df_traj_sim_all["n_iterations"].unique())

    for ax, model in zip(axes, models):
        df_m = df_traj_sim_all[df_traj_sim_all["model"] == model]
        r_val, p_val = pearsonr(df_m["similarity"], df_m["n_iterations"])
        ct = df_m.groupby(["sim_bin", "n_iterations"]).size().reset_index(name="count")
        pivot = ct.pivot(
            index="n_iterations", columns="sim_bin", values="count"
        ).fillna(0)
        pivot = pivot.reindex(all_iters, fill_value=0)
        pivot_display = pivot.replace(0, np.nan)
        sns.heatmap(
            pivot_display.iloc[::-1],
            cmap=_cmap_red,
            norm=LogNorm(vmin=1),
            linewidths=0.3,
            linecolor="white",
            ax=ax,
            cbar_kws={"label": "Count", "shrink": 0.8},
            square=False,
        )
        xtick_positions = ax.get_xticks()
        xtick_labels = [t.get_text() for t in ax.get_xticklabels()]
        ax.set_xticks(xtick_positions)
        ax.set_xticklabels(
            [
                lbl if float(lbl) % 0.2 < 0.01 or float(lbl) % 0.2 > 0.19 else ""
                for lbl in xtick_labels
            ]
        )
        sim_vals = np.array(sorted(pivot.columns))
        iter_vals = np.array(sorted(pivot.index))
        x = df_m["similarity"].values.astype(float)
        y = df_m["n_iterations"].values.astype(float)
        n = len(x)
        slope, intercept = np.polyfit(x, y, 1)
        x_fit = np.linspace(sim_vals.min(), sim_vals.max(), 100)
        y_fit = slope * x_fit + intercept
        x_mean = x.mean()
        residuals = y - (slope * x + intercept)
        se_residuals = np.sqrt(np.sum(residuals**2) / (n - 2))
        se_line = se_residuals * np.sqrt(
            1 / n + (x_fit - x_mean) ** 2 / np.sum((x - x_mean) ** 2)
        )
        t_crit = t_dist.ppf(0.975, df=n - 2)
        y_upper = y_fit + t_crit * se_line
        y_lower = y_fit - t_crit * se_line
        x_hm = np.interp(x_fit, sim_vals, np.arange(len(sim_vals))) + 0.5
        y_hm = np.interp(y_fit, iter_vals, np.arange(len(iter_vals)))
        y_hm = len(iter_vals) - y_hm - 0.5
        y_upper_hm = np.interp(y_upper, iter_vals, np.arange(len(iter_vals)))
        y_upper_hm = len(iter_vals) - y_upper_hm - 0.5
        y_lower_hm = np.interp(y_lower, iter_vals, np.arange(len(iter_vals)))
        y_lower_hm = len(iter_vals) - y_lower_hm - 0.5
        ax.plot(x_hm, y_hm, color="black", lw=2.5, ls="--")
        ax.fill_between(x_hm, y_upper_hm, y_lower_hm, color="black", alpha=0.15)
        ax.grid(False)
        ax.set_title(f"{display_names[model]}  (r = {r_val:.3f})")
        ax.set_xlabel("Candidate similarity")
        ax.set_ylabel("# of iterations")
    plt.tight_layout()
    plt.savefig(
        root_plots / "stack-similarity-vs-iterations-all.pdf", bbox_inches="tight"
    )
    finish_figure(show)


def _report_similarity_progression(
    collected,
    df_traj: pd.DataFrame,
    jqstack,
    root_plots: Path,
    show: bool,
    trajectories_claude,
    trajectories_gpt,
) -> None:
    expr_map = {b["identifier"]: b["expressions"] for b in jqstack}
    traj_rows = []

    for model_name, trajectories in [
        ("Gpt5Chat", trajectories_gpt),
        ("ClaudeOpus46", trajectories_claude),
    ]:
        for r in trajectories:
            bid = r["identifier"]
            if bid not in expr_map:
                continue
            final_exprs = expr_map[bid]
            candidates = r["environment"]["candidates"]
            for i, cand in enumerate(candidates):
                s = np.mean([sim(cand, fe) for fe in final_exprs])
                traj_rows.append(
                    {
                        "identifier": bid,
                        "model": model_name,
                        "iteration": min(i + 1, 8),  # clip to match df_traj
                        "similarity": s,
                    }
                )
    df_prog = pd.DataFrame(traj_rows)
    display_names = {"Gpt5Chat": "gpt-5", "ClaudeOpus46": "opus-4.6"}

    fig, axes = plt.subplots(2, 1, figsize=(8, 6), sharex=True)

    for ax, model in zip(axes, ["Gpt5Chat", "ClaudeOpus46"]):
        df_m = df_prog[df_prog["model"] == model]
        sns.boxplot(
            data=df_m,
            x="iteration",
            y="similarity",
            ax=ax,
            showfliers=False,
            saturation=1,
            color=sns.color_palette("Set1")[0],
        )
        for patch in ax.patches:
            patch.set_alpha(0.75)
        # Overlay mean line
        means = df_m.groupby("iteration")["similarity"].mean()
        ax.plot(
            means.index - 1,
            means.values,
            color="black",
            marker="o",
            ms=5,
            lw=2,
            zorder=5,
        )
        ax.grid(False)
        ax.set_title(display_names[model])
        ax.set_ylabel(None)
        if ax == axes[-1]:
            ax.set_xlabel("Iteration")
        else:
            ax.set_xlabel(None)
    fig.supylabel("Similarity to Solution")
    plt.tight_layout()
    plt.savefig(root_plots / "stack-similarity-progression.pdf", bbox_inches="tight")
    finish_figure(show)

    for model in ["Gpt5Chat", "ClaudeOpus46"]:
        df_m = df_prog[df_prog["model"] == model]
        groups = [g["similarity"].values for _, g in df_m.groupby("iteration")]
        stat, p = kruskal(*groups)
        rho, p_rho = spearmanr(df_m["iteration"], df_m["similarity"])
        print(f"{display_names[model]}:")
        print(f"  Kruskal-Wallis H = {stat:.2f}, p = {p:.4g}")
        print(f"  Spearman rho = {rho:+.3f}, p = {p_rho:.4g}")
        print()
    expr_map_all = {b["identifier"]: b["expressions"] for b in collected}
    traj_rows_all = []

    for model_name, trajectories in [
        ("Gpt5Chat", trajectories_gpt),
        ("ClaudeOpus46", trajectories_claude),
    ]:
        for r in trajectories:
            bid = r["identifier"]
            if bid not in expr_map_all:
                continue
            final_exprs = expr_map_all[bid]
            candidates = r["environment"]["candidates"]
            for i, cand in enumerate(candidates):
                iteration = i + 1
                if iteration > 7:
                    continue
                s = np.mean([sim(cand, fe) for fe in final_exprs])
                traj_rows_all.append(
                    {
                        "identifier": bid,
                        "model": model_name,
                        "iteration": iteration,
                        "similarity": s,
                    }
                )
    df_prog_all = pd.DataFrame(traj_rows_all)
    print(f"Rows: {len(df_prog_all):,} (was {len(df_prog):,} for jqStack only)")
    display_names = {"Gpt5Chat": "gpt-5", "ClaudeOpus46": "opus-4.6"}

    fig, axes = plt.subplots(2, 1, figsize=(8, 6), sharex=True)

    for ax, model in zip(axes, ["Gpt5Chat", "ClaudeOpus46"]):
        df_m = df_prog_all[df_prog_all["model"] == model]
        sns.boxplot(
            data=df_m,
            x="iteration",
            y="similarity",
            ax=ax,
            showfliers=False,
            saturation=1,
            color=sns.color_palette("Set1")[0],
        )
        for patch in ax.patches:
            patch.set_alpha(0.75)
        means = df_m.groupby("iteration")["similarity"].mean()
        ax.plot(
            means.index - 1,
            means.values,
            color="black",
            marker="o",
            ms=5,
            lw=2,
            zorder=5,
        )
        ax.grid(False)
        ax.set_title(display_names[model])
        ax.set_ylabel(None)
        if ax == axes[-1]:
            ax.set_xlabel("Iteration")
        else:
            ax.set_xlabel(None)
    fig.supylabel("Similarity to Solution")
    plt.tight_layout()
    plt.savefig(
        root_plots / "stack-similarity-progression-all.pdf", bbox_inches="tight"
    )
    finish_figure(show)

    for model in ["Gpt5Chat", "ClaudeOpus46"]:
        df_m = df_prog_all[df_prog_all["model"] == model]
        groups = [g["similarity"].values for _, g in df_m.groupby("iteration")]
        stat, p = kruskal(*groups)
        rho, p_rho = spearmanr(df_m["iteration"], df_m["similarity"])
        print(f"{display_names[model]}:")
        print(f"  Kruskal-Wallis H = {stat:.2f}, p = {p:.4g}")
        print(f"  Spearman rho = {rho:+.3f}, p = {p_rho:.4g}")
        print()
    print(
        f"n_iterations range: {df_traj['n_iterations'].min()} – {df_traj['n_iterations'].max()}"
    )
    print(df_traj["n_iterations"].value_counts().sort_index())


def _report_test_creation(df_traj: pd.DataFrame, root_plots: Path, show: bool) -> None:
    df_traj_nonzero = df_traj[df_traj["n_iterations"] > 0]

    fig, ax = plt.subplots(figsize=(6, 5))
    sns.boxplot(
        data=df_traj_nonzero,
        x="n_iterations",
        y="first_pass_rate",
        ax=ax,
        showfliers=False,
    )
    ax.set_xlabel("# of iterations")
    ax.set_ylabel("first-attempt pass rate")
    plt.tight_layout()
    plt.savefig(root_plots / "stack-first-pass-vs-iterations.pdf", bbox_inches="tight")
    finish_figure(show)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    sns.histplot(
        data=df_traj,
        x="add_test_calls",
        bins=range(0, df_traj["add_test_calls"].max() + 2),
        ax=axes[0],
        alpha=0.75,
        color=sns.color_palette("Set1")[0],
    )
    axes[0].set_xlabel("add_test calls during creation")
    axes[0].set_ylabel("count")
    sns.histplot(
        data=df_traj,
        x="n_tests",
        bins=range(0, df_traj["n_tests"].max() + 2),
        ax=axes[1],
        alpha=0.75,
        color=sns.color_palette("Set1")[1],
    )
    axes[1].set_xlabel("# of tests in final benchmark")
    axes[1].set_ylabel("count")
    plt.tight_layout()
    plt.savefig(root_plots / "stack-test-creation.pdf", bbox_inches="tight")
    finish_figure(show)

    replaced = (df_traj["add_test_calls"] > df_traj["n_tests"]).sum()
    print(
        f"Benchmarks where tests were replaced (add_test > final tests): {replaced} ({100 * replaced / len(df_traj):.1f}%)"
    )


def generate(output: Path, *, show: bool = False) -> None:
    root_tables = output / "stack" / "tables"
    root_tables.mkdir(parents=True, exist_ok=True)
    configure_plots(show=show)
    root = paths.stack
    root_plots = output / "stack" / "plots"
    root_plots.mkdir(parents=True, exist_ok=True)
    extracted, collected, jqstack = _report_pipeline(
        root, root_plots, root_tables, show
    )
    _report_filtering(root_plots, root_tables, show)
    _report_benchmarks(collected, jqstack, root_plots, root_tables, show)
    extracted_by_id, df_sim = _report_similarity(extracted, jqstack, root_plots, show)
    trajectories_gpt, trajectories_claude, df_traj = _report_trajectories(
        root, root_plots, root_tables, show
    )
    _report_trajectory_complexity(df_traj, root_plots, show)
    _set1_red = sns.color_palette("Set1")[0]
    _cmap_red = LinearSegmentedColormap.from_list("set1_red", ["white", _set1_red])
    _report_iteration_distribution(_cmap_red, df_traj, root_plots, show)
    _report_similarity_iterations(
        _cmap_red, collected, df_sim, df_traj, extracted_by_id, root_plots, show
    )
    _report_similarity_progression(
        collected,
        df_traj,
        jqstack,
        root_plots,
        show,
        trajectories_claude,
        trajectories_gpt,
    )
    _report_test_creation(df_traj, root_plots, show)


def main(argv: list[str] | None = None) -> None:
    args = arguments(__doc__, argv)
    generate(args.output, show=args.show)


if __name__ == "__main__":
    main()
