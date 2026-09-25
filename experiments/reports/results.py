"""Paper performance tables and figures from supplied benchmark artifacts."""

import difflib
import json
import re
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
from statsmodels.stats.proportion import proportion_confint
from tqdm import tqdm

from experiments.paths import paths
from experiments.reports import arguments, configure_plots, finish_figure, write_table
from jqbench import decode_record, load

VALUE_MATCH_POSITIVE = {"Exact", "Wrapped", "Unwrapped"}


def load_benchmarks(file_data: Path) -> pd.DataFrame:
    """Load public JSONL rows into benchmark analysis features."""
    with open(file_data, encoding="utf-8") as file:
        data = [decode_record(json.loads(line)) for line in file if line.strip()]
    records = [
        {
            "identifier": el.get("identifier", None),
            "tests": len(el.get("inputs", [])),
            "task": el.get("tasks", [None])[0],
            "expression": min(el["expressions"], key=len),
        }
        for el in data
    ]
    return pd.DataFrame.from_records(records)


def load_results(roots: list[Path]) -> pd.DataFrame:
    """Load experiment result JSONs -> DataFrame with correctness metrics."""
    result_files = _collect_json_files(roots)
    records = []
    for result_file in tqdm(result_files, desc="Loading results"):
        with open(result_file, encoding="utf-8") as file:
            data = json.loads(file.read())
        solver = data["solver"]
        base = {
            "dataset": data["dataset"],
            "name": solver["name"],
            **{k: v for k, v in solver.items() if k != "name"},
            **{f"input-{k}": v for k, v in data["input"].items()},
            **{f"model-{k}": v for k, v in data["model"].items()},
        }
        for solution in data["solutions"]:
            predictions = solution.get("predictions", [])
            if len(predictions) == 0:
                continue
            n = len(predictions)
            records.append(
                {
                    "identifier": solution["identifier"],
                    **base,
                    "compiles": sum(p["metrics"]["compiles"] for p in predictions) / n,
                    "executes": sum(p["metrics"]["executes"] for p in predictions) / n,
                    "value_match": sum(
                        p["metrics"]["value_match"] in VALUE_MATCH_POSITIVE
                        for p in predictions
                    )
                    / n,
                    "exact_match": sum(p["metrics"]["exact_match"] for p in predictions)
                    / n,
                }
            )
    return pd.DataFrame.from_records(records)


def load_statistics(
    roots: list[Path],
    pattern: str = "*Agent*.json",
) -> pd.DataFrame:
    """Load Agent result JSONs -> DataFrame with tool usage and feedback stats."""
    feedback_map = {
        "too long": "execute",
        "compile": "compile",
        "evaluate": "execute",
        "Expected output": "values",
    }
    result_files = _collect_json_files(roots, pattern)
    records = []
    for result_file in tqdm(result_files, desc="Loading statistics"):
        with open(result_file, encoding="utf-8") as file:
            data = json.loads(file.read())
        config = {
            "dataset": data["dataset"],
            "input-kind": data["input"]["kind"],
            "input-which": data["input"]["which"],
            "solver": data["solver"]["name"],
            "model": data["model"]["name"],
        }
        for element in data["solutions"]:
            metadata = element.get("metadata", {})
            tool_stats = Counter()
            for tools in metadata.get("tools", []):
                if len(tools) == 0:
                    continue
                tool_stats["turn_tools"] += len(tools)
                tool_stats["turns"] += 1
                for tool in tools:
                    tool_name = tool["tool"]
                    tool_values = tool.get("result", {}).get("values", {})
                    tool_result_key = next(iter(tool_values.keys()), None)
                    tool_stats[tool_name] += 1
                    tool_stats["tools"] += 1
                    if tool_name == "test_expression":
                        tool_stats[f"test:{tool_result_key}"] += 1
            feedbacks = metadata.get("feedback", [])
            for feedback in feedbacks:
                if isinstance(feedback, str):
                    for key, value in feedback_map.items():
                        if key in feedback:
                            tool_stats[f"feedback:{value}"] += 1
                            break
            tool_stats["feedback"] = len(feedbacks)
            records.append(
                {
                    "iterations": len(element["metadata"]["usage"]),
                    "identifier": element["identifier"],
                    **config,
                    **tool_stats,
                }
            )
    return pd.DataFrame.from_records(records).fillna(0)


def aggregate(
    df: pd.DataFrame,
    group: list[str] | None = None,
    metrics: list[str] | None = None,
    threshold: float = 0.9,
) -> pd.DataFrame:
    """Group, sum metrics, convert to rates."""
    group = group or DEFAULT_GROUP
    metrics = metrics or DEFAULT_METRICS
    agg = (
        df.groupby(group)
        .agg({**{m: "sum" for m in metrics}, "identifier": "nunique"})
        .reset_index()
    )
    per = agg.groupby("dataset")["identifier"].max().to_dict()
    agg["total"] = agg["dataset"].map(per)
    agg = agg[agg["total"] * threshold <= agg["identifier"]]
    for m in metrics:
        agg[m] = agg[m] / agg["total"]
    return agg


DEFAULT_GROUP = ["dataset", "solver", "model", "input-kind", "input-which"]


DEFAULT_METRICS = [
    "compiles",
    "executes",
    "value_match",
    "value_match_first",
    "feedback:compile",
    "feedback:execute",
    "feedback:values",
    "search_documentation",
    "print_documentation",
    "test_expression",
]


MODEL_DISPLAY_NAMES = {
    "spider": "\\jqSpider{}",
    "jqStackFixed": "\\jqStack{}",
    "Gpt41": "gpt-4.1",
    "Gpt41Mini": "gpt-4.1-mini",
    "Gpt5Chat": "gpt-5",
    "Gpt5ChatMini": "gpt-5-mini",
    "ClaudeOpus41": "opus-4.1",
    "Phi4": "phi-4",
    "Na": "",
    "AllButOne": "$n-1$",
    "One": "1",
    "All": "$n$",
    "Python": "py",
    "Jq": "jq",
    True: "$\\checkmark$",
    False: "",
}


DEFAULT_COLUMN_HEADERS = {
    "model": "model",
    "language": "configuration",
    "implicit": "configuration",
    "doc": "configuration",
    "feedback:compile": "feedback",
    "feedback:execute": "feedback",
    "feedback:values": "feedback",
    "test_expression": "tools",
    "search_documentation": "tools",
    "print_documentation": "tools",
    "compiles": "performance",
    "executes": "performance",
    "value": "performance",
    "value_first": "performance",
}


DEFAULT_COLUMN_RENAMES = {
    "feedback:compile": "c?",
    "feedback:execute": "e?",
    "feedback:values": "v?",
    "compiles": "c?",
    "executes": "e?",
    "value": "v?",
    "value_first": "v@1",
    "search_documentation": "search",
    "print_documentation": "print",
    "test_expression": "test",
}


DEFAULT_HEADER_ORDER = ["model", "configuration", "feedback", "tools", "performance"]


LATEX_GROUP_DISPLAY = {
    "model": ("\\textsc{model}", ""),
    "configuration": ("{\\scshape configuration}", "\\tnote{1}"),
    "feedback": ("{\\scshape \\# feedback}", ""),
    "tools": ("{\\scshape \\# tools}", ""),
    "performance": ("{\\scshape performance}", ""),
}


LATEX_SUBCOLUMN_DISPLAY = {
    ("model", "model"): "",
    ("configuration", "language"): "\\multicolumn{1}{c}{\\faIcon{language}}",
    ("configuration", "doc"): "\\faIcon{search}\\faIcon{print}",
    ("configuration", "implicit"): "\\faIcon{check}",
    ("tools", "search"): "\\faIcon{search}",
    ("tools", "print"): "\\faIcon{print}",
    ("tools", "test"): "\\faIcon{code}",
}


LATEX_COLUMN_ALIGN = {
    ("model", "model"): "L",
    ("configuration", "language"): "l",
    ("configuration", "doc"): "c",
    ("configuration", "implicit"): "c",
}


def parametrize(df: pd.DataFrame) -> pd.DataFrame:
    """Extract config columns from solver name, apply display-name replacements."""
    df = df.copy()
    df["language"] = df["solver"].str.extract(r"^(Jq|Python)")
    df["doc"] = df["solver"].str.contains("Documentation")
    df["run"] = ~df["solver"].str.contains("Implicit")
    df["implicit"] = df["solver"].str.contains("Implicit")
    df = df.rename(
        columns={
            "input-kind": "data",
            "input-which": "examples",
            "value_match": "value",
            "value_match_first": "value_first",
        },
    )
    df = df.replace(MODEL_DISPLAY_NAMES)
    df = df.drop(columns=["solver", "total", "identifier"], errors="ignore")
    return df


def sort_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Sort rows by model + language + config combination."""

    def _sort_key(v: str) -> int:
        if "Jq" in v:
            has_implicit = "Implicit" in v
            has_doc = "Doc" in v
            return {
                (False, False): 0,
                (False, True): 1,
                (True, False): 2,
                (True, True): 3,
            }[(has_implicit, has_doc)]
        return 4

    df = df.copy()
    df["_sort"] = (
        df["model"]
        + df["language"].apply(lambda v: f"+{v}")
        + df["implicit"].str.replace("$\\checkmark$", "+Implicit")
        + df["doc"].str.replace("$\\checkmark$", "+Doc")
    )
    return df.sort_values(by="_sort", key=lambda s: s.apply(_sort_key)).drop(
        columns=["_sort"]
    )


def format_columns(
    df: pd.DataFrame,
    column_headers: dict[str, str] | None = None,
    column_renames: dict[str, str] | None = None,
    header_order: list[str] | None = None,
    drop_columns: list[tuple[str, str]] | None = None,
    zero_placeholder: str = "--",
) -> pd.DataFrame:
    """Apply column ordering, MultiIndex headers, renaming, and zero replacement."""
    column_headers = column_headers or DEFAULT_COLUMN_HEADERS
    column_renames = column_renames or DEFAULT_COLUMN_RENAMES
    header_order = header_order or DEFAULT_HEADER_ORDER

    # Order columns by header groups
    group_cols = {key: [] for key in header_order}
    for col in df.columns:
        header = column_headers.get(col)
        if header and header in group_cols:
            group_cols[header].append(col)
    ordered = []
    for grp in header_order:
        ordered.extend(group_cols[grp])
    leftovers = [c for c in df.columns if c not in ordered]
    ordered.extend(leftovers)
    result = df[ordered].copy()

    # Build MultiIndex
    tuples = [(column_headers.get(col, col), col) for col in result.columns]
    result.columns = pd.MultiIndex.from_tuples(tuples)

    # Rename second level
    result = result.rename(columns=column_renames, level=1)

    # Replace zeros
    result = result.replace({0.0: zero_placeholder})

    # Drop columns
    if drop_columns:
        result = result.drop(columns=drop_columns, errors="ignore")

    return result


def build_table(
    df: pd.DataFrame,
    *,
    filter_expr: str | None = None,
    solver_filter: str | None = None,
    input_kinds: set[str] | None = None,
    input_which: set[str] | None = None,
    group: list[str] | None = None,
    metrics: list[str] | None = None,
    threshold: float = 0.9,
    column_headers: dict[str, str] | None = None,
    column_renames: dict[str, str] | None = None,
    header_order: list[str] | None = None,
    drop_columns: list[tuple[str, str]] | None = None,
    zero_placeholder: str = "--",
) -> pd.DataFrame:
    """End-to-end: filter -> aggregate -> parametrize -> sort -> format."""
    view = df.copy()
    if filter_expr:
        view = view.query(filter_expr)
    if solver_filter:
        view = view[view.solver.str.contains(solver_filter)]
    agg = aggregate(view, group=group, metrics=metrics, threshold=threshold)

    if input_kinds is not None:
        agg = agg[agg["input-kind"].isin(input_kinds)]
    if input_which is not None:
        agg = agg[agg["input-which"].isin(input_which)]
    agg = agg.reset_index(drop=True)
    result = parametrize(agg)
    result = sort_rows(result)
    result = format_columns(
        result,
        column_headers=column_headers,
        column_renames=column_renames,
        header_order=header_order,
        drop_columns=drop_columns,
        zero_placeholder=zero_placeholder,
    )
    return result


def to_latex(
    df: pd.DataFrame,
    drop_columns: list[tuple[str, str]] | None = None,
    float_format: str = "%.2f",
) -> str:
    """Render a MultiIndex DataFrame as a tabulary LaTeX table."""
    out = df.copy()
    if drop_columns:
        out = out.drop(columns=drop_columns, errors="ignore")
    cols = list(out.columns)  # list of (group, name) tuples

    # --- column alignment ---
    col_spec = "".join(LATEX_COLUMN_ALIGN.get(c, "r") for c in cols)

    # --- group spans (consecutive columns with the same first level) ---
    groups: list[tuple[str, int]] = []
    for col in cols:
        g = col[0]
        if groups and groups[-1][0] == g:
            groups[-1] = (g, groups[-1][1] + 1)
        else:
            groups.append((g, 1))

    # --- first header row ---
    header_parts = []
    for group, count in groups:
        content, suffix = LATEX_GROUP_DISPLAY.get(group, (group, ""))
        if count > 1:
            header_parts.append(f"\\multicolumn{{{count}}}{{c}}{{{content}}}{suffix}")
        else:
            header_parts.append(f"{content}{suffix}")
    header_row = " & ".join(header_parts) + " \\\\"

    # --- cmidrule row (only for multi-column groups) ---
    cmidrules = []
    idx = 1
    for group, count in groups:
        if count > 1:
            cmidrules.append(f"\\cmidrule(lr){{{idx}-{idx + count - 1}}}")
        idx += count
    cmidrule_row = " ".join(cmidrules)

    # --- second header row (sub-column icons / names) ---
    sub_parts = []
    for col in cols:
        sub_parts.append(LATEX_SUBCOLUMN_DISPLAY.get(col, col[1]))
    sub_row = " & ".join(sub_parts) + " \\\\"

    # --- data rows ---
    data_rows = []
    for _, row in out.iterrows():
        parts = []
        for col in cols:
            val = row[col]
            if pd.isna(val):
                parts.append("")
            elif isinstance(val, str):
                parts.append(val)
            else:
                parts.append(float_format % val)
        data_rows.append(" & ".join(parts) + " \\\\")
    lines = [
        f"\\begin{{tabulary}}{{\\linewidth}}{{{col_spec}}}",
        "\\toprule",
        header_row,
        cmidrule_row,
        sub_row,
        "\\midrule",
        *data_rows,
        "\\bottomrule",
        "\\end{tabulary}",
    ]
    return "\n".join(lines) + "\n"


def to_markdown(
    df: pd.DataFrame,
    drop_columns: list[tuple[str, str]] | None = None,
) -> str:
    """Render a MultiIndex DataFrame as a markdown table string."""
    out = df.copy()
    if drop_columns:
        out = out.drop(columns=drop_columns, errors="ignore")
    return out.to_markdown(index=False)


def save_table(
    df: pd.DataFrame,
    name: str,
    output_dir: Path | None = None,
    drop_columns: list[tuple[str, str]] | None = None,
    float_format: str = "%.2f",
) -> None:
    """Save a table as both .tex and .md files."""
    output_dir = output_dir or paths.reports / "tables"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{name}.tex").write_text(
        to_latex(df, drop_columns=drop_columns, float_format=float_format),
        encoding="utf-8",
    )
    (output_dir / f"{name}.md").write_text(
        to_markdown(df, drop_columns=drop_columns),
        encoding="utf-8",
    )


def parse_doc_functions(doc_path: Path = paths.docs / "index.md") -> list[str]:
    """Extract jq function names from the documentation index."""
    doc = doc_path.read_text(encoding="utf-8")
    return [
        e
        for f in re.findall(r"`(.+?)`", doc)
        if re.match(r"^@?[a-zA-Z_]+$", e := f.strip('"').split("(")[0]) is not None
    ]


def get_functions(expression: str, doc_functions: list[str]) -> list[str]:
    """Return jq functions found in an expression."""
    return [f for f in doc_functions if re.search(rf"\b{f}\b", expression)]


def compute_function_usage(expressions: pd.Series, doc_functions: list[str]) -> Counter:
    """Count how often each function appears across all expressions."""
    fn_usage = Counter()
    for expr in tqdm(expressions, desc="Counting functions"):
        fn_usage.update(set(get_functions(expr, doc_functions)))
    return fn_usage


def max_nesting_depth(expr: str) -> int:
    """Max depth of (), [], {} nesting."""
    depth = max_depth = 0
    for ch in expr:
        if ch in "([{":
            depth += 1
            max_depth = max(max_depth, depth)
        elif ch in ")]}":
            depth = max(0, depth - 1)
    return max_depth


def count_variable_bindings(expr: str) -> int:
    """Count 'as $var' patterns."""
    return len(re.findall(r"\bas\s+\$", expr))


def count_control_flow(expr: str) -> int:
    """Count control flow constructs: if, try, reduce, foreach, label, until, limit, //, .foo?."""
    keywords = len(re.findall(r"\b(if|try|reduce|foreach|label|until|limit)\b", expr))
    alt_op = expr.count("//")
    optional = len(re.findall(r"\.\w+\?", expr))
    return keywords + alt_op + optional


def count_constructions(expr: str) -> int:
    """Count object {} and array [] construction sites."""
    return expr.count("{") + expr.count("[")


def count_string_interpolations(expr: str) -> int:
    r"""Count \(...) string interpolation patterns."""
    return len(re.findall(r"\\\(", expr))


def count_definitions(expr: str) -> int:
    """Count function definitions (def keyword)."""
    return len(re.findall(r"\bdef\b", expr))


def tag_complexity(
    expression: str,
    doc_functions: list[str],
    fn_usage: Counter,
) -> dict[str, float]:
    """Compute complexity metrics for a jq expression."""
    functions = get_functions(expression, doc_functions)
    num_functions = len(functions)
    num_unique = len(set(functions))
    avg_rarity = (
        sum(1.0 / fn_usage[f] for f in functions if fn_usage[f] > 0) / num_functions
        if num_functions > 0
        else 0.0
    )
    return {
        "complexity:unique_functions": float(num_unique),
        "complexity:pipes": float(expression.count("|")),
        "complexity:nesting_depth": float(max_nesting_depth(expression)),
        "complexity:variable_bindings": float(count_variable_bindings(expression)),
        "complexity:control_flow": float(count_control_flow(expression)),
        "complexity:constructions": float(count_constructions(expression)),
        "complexity:function_rarity": float(avg_rarity),
        "complexity:definitions": float(count_definitions(expression)),
    }


def save_figure(
    fig,
    name: str,
    output_dir: Path | None = None,
    formats: list[str] | None = None,
    dpi: int = 300,
) -> None:
    """Save a matplotlib figure in the given formats."""
    formats = formats or ["pdf", "png"]
    output_dir = output_dir or paths.reports / "plots"
    output_dir.mkdir(parents=True, exist_ok=True)
    for fmt in formats:
        fig.savefig(output_dir / f"{name}.{fmt}", dpi=dpi, bbox_inches="tight")


def load_trajectories(path: Path, fixed_ids: set) -> list[dict]:
    """Extract difficulty metrics from trajectory records that appear in the fixed dataset."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    rows = []
    for r in data:
        if r["identifier"] not in fixed_ids:
            continue
        rows.append(
            {
                "identifier": r["identifier"],
                "difficulty:iterations": len(r["executions"]),
            }
        )
    return rows


def load_per_iteration_data(
    roots: list[Path],
    pattern: str = "*Implicit*.json",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load per-iteration solve / feedback data from Implicit solver results
    (excluding Documentation variants)."""
    files = [
        f
        for root in roots
        for f in root.rglob(pattern)
        if "Documentation" not in f.name
    ]
    sol_rows, fb_rows = [], []
    for result_file in tqdm(files, desc="Loading per-iteration data"):
        with open(result_file, encoding="utf-8") as f:
            data = json.load(f)
        cfg = {
            "dataset": data["dataset"],
            "solver": data["solver"]["name"],
            "input-kind": data["input"]["kind"],
            "input-which": data["input"]["which"],
            "model": data["model"]["name"],
        }
        for sol in data["solutions"]:
            feedbacks = sol.get("metadata", {}).get("feedback", [])
            solved_at = None
            for i, fb in enumerate(feedbacks):
                if fb is True:
                    fb_type = "correct"
                    if solved_at is None:
                        solved_at = i + 1
                elif isinstance(fb, str):
                    fb_type = "other"
                    for key, val in _feedback_classify.items():
                        if key in fb:
                            fb_type = val
                            break
                else:
                    fb_type = "other"
                fb_rows.append(
                    {
                        "identifier": sol["identifier"],
                        **cfg,
                        "iteration": i + 1,
                        "feedback_type": fb_type,
                        "feedback_raw": fb if isinstance(fb, str) else str(fb),
                    }
                )
            sol_rows.append(
                {
                    "identifier": sol["identifier"],
                    **cfg,
                    "n_iterations": len(feedbacks),
                    "solved_at": solved_at,
                }
            )
    return (
        pd.DataFrame.from_records(sol_rows),
        pd.DataFrame.from_records(fb_rows),
    )


_feedback_classify = {
    "too long": "execute",
    "compile": "compile",
    "evaluate": "execute",
    "Expected output": "values",
}


def _load_report_data(all_runs: bool, root_results: list[Path], root_tables: Path):
    file_data = paths.data / "jqStack.jsonl"
    df_benchmarks = load_benchmarks(file_data)
    df_statistics = load_statistics(root_results)
    df_results = load_results(root_results)
    if not all_runs:
        supplemental = (
            (df_results["dataset"] == "spider")
            & (df_results["name"] == "PythonAgent+Implicit")
            & (df_results["model-name"] == "Phi4")
        )
        df_results = df_results.loc[~supplemental]
    df_results = df_results.rename(columns={"name": "solver", "model-name": "model"})
    df_results = df_results.merge(df_benchmarks, how="outer", on="identifier")
    df = pd.merge(
        df_results,
        df_statistics,
        on=["identifier", "dataset", "solver", "input-kind", "input-which", "model"],
        how="left",
        suffixes=("", "_stats"),
    )
    df = df[~df.solver.isna()]
    is_implicit_only = df["solver"].str.contains("Implicit") & ~df[
        "solver"
    ].str.contains("Documentation")
    df["value_match_first"] = (
        df["value_match"]
        .where(df["iterations_stats"] == 1, 0.0)
        .where(df["iterations_stats"].notna())
        .where(is_implicit_only)
    )
    write_table(df, root_tables / "table-01.csv")

    return df_benchmarks, df_results, df


def _report_tables(df: pd.DataFrame, root_tables: Path) -> None:
    table_stack = build_table(
        df,
        filter_expr="`input-kind` == 'InputOutput' and dataset == 'jqStackFixed'",
        solver_filter="Agent",
        drop_columns=[
            ("data", "data"),
            ("examples", "examples"),
            ("dataset", "dataset"),
            ("run", "run"),
        ],
    )
    save_table(table_stack, "table1", root_tables)
    print(to_latex(table_stack))
    write_table(table_stack, root_tables / "table-02.csv")
    table_stack_fbe = build_table(
        df,
        filter_expr="`input-kind` == 'Examples' and dataset == 'jqStackFixed'",
        solver_filter="Agent",
        drop_columns=[
            ("data", "data"),
            ("examples", "examples"),
            ("dataset", "dataset"),
            ("run", "run"),
            ("doc", "doc"),
            ("implicit", "implicit"),
        ],
    )
    save_table(table_stack_fbe, "table3", root_tables)
    print(to_latex(table_stack_fbe))
    table_spider = build_table(
        df,
        filter_expr="dataset == 'spider'",
        solver_filter="Agent",
        drop_columns=[
            ("data", "data"),
            ("examples", "examples"),
            ("dataset", "dataset"),
            ("run", "run"),
            ("configuration", "doc"),
            ("feedback", "v?"),
            ("tools", "search"),
            ("tools", "print"),
        ],
    )
    save_table(table_spider, "table2", root_tables)
    print(to_latex(table_spider))
    write_table(table_spider, root_tables / "table-03.csv")


def _report_complexity(
    df: pd.DataFrame, df_benchmarks: pd.DataFrame, root_plots: Path, show: bool
):
    doc_functions = parse_doc_functions()
    fn_usage = compute_function_usage(df_benchmarks["expression"], doc_functions)
    complexity_cols = (
        df_benchmarks["expression"]
        .apply(lambda expr: tag_complexity(expr, doc_functions, fn_usage))
        .apply(pd.Series)
    )
    df_with_complexity = df.merge(
        df_benchmarks[["identifier"]].join(complexity_cols), on="identifier", how="left"
    )
    df_complexity = df_with_complexity[
        (df_with_complexity.solver == "JqAgent+Implicit")
        & (df_with_complexity.dataset == "jqStackFixed")
        & (df_with_complexity["input-kind"] == "InputOutput")
        & df_with_complexity.model.isin(
            {"Gpt5Chat", "ClaudeOpus41", "Gpt5ChatMini", "Phi4"}
        )
    ].copy()
    c_cols = [c for c in df_complexity.columns if c.startswith("complexity:")]
    metric_labels = {
        "complexity:unique_functions": "Unique Functions",
        "complexity:pipes": "Pipes",
        "complexity:nesting_depth": "Nesting Depth",
        "complexity:variable_bindings": "Variable Bindings",
        "complexity:control_flow": "Control Flow",
        "complexity:constructions": "Constructions",
        "complexity:function_rarity": "Function Rarity",
        "complexity:definitions": "Function Definitions",
    }
    n_metrics = len(c_cols)

    fig, axes = plt.subplots(
        2, (n_metrics + 1) // 2, figsize=(3.5 * ((n_metrics + 1) // 2), 8), sharey=True
    )
    axes = axes.flatten()

    for ax, col in zip(axes, c_cols):
        df_complexity[f"{col}_bin"] = pd.qcut(
            df_complexity[col], q=5, duplicates="drop"
        )
        bin_order = sorted(df_complexity[f"{col}_bin"].dropna().unique())
        records = []
        for model in df_complexity["model"].unique():
            df_m = df_complexity[df_complexity["model"] == model]
            for i, b in enumerate(bin_order):
                grp = df_m[df_m[f"{col}_bin"] == b]
                n = len(grp)
                k = int(grp["value_match"].sum())
                rate = k / n if n > 0 else float("nan")
                lo, hi = (
                    proportion_confint(k, n, alpha=0.05, method="wilson")
                    if n > 0
                    else (0, 0)
                )
                records.append(
                    {
                        "model": MODEL_DISPLAY_NAMES.get(model, model),
                        "bin_idx": i,
                        "rate": rate,
                        "ci_lo": lo,
                        "ci_hi": hi,
                    }
                )
        df_binned = pd.DataFrame(records)
        for model, grp in df_binned.groupby("model"):
            grp = grp.sort_values("bin_idx")
            ax.plot(grp["bin_idx"], grp["rate"], marker="o", label=model, linewidth=2)
            ax.fill_between(grp["bin_idx"], grp["ci_lo"], grp["ci_hi"], alpha=0.15)
        label = metric_labels.get(col, col.replace("complexity:", ""))
        ax.set_xlabel(label)
        ax.set_xticks(range(len(bin_order)))
        ax.set_xticklabels([f"Q{i + 1}" for i in range(len(bin_order))])
        if ax in axes[:: ((n_metrics + 1) // 2)]:
            ax.set_ylabel("Value Match Rate")
        ax.set_ylim(0, 1.05)

    for ax in axes[n_metrics:]:
        ax.set_visible(False)
    axes[-1].legend(title="Model", bbox_to_anchor=(1.05, 1), loc="upper left")
    fig.tight_layout()
    save_figure(fig, "complexity-binned", root_plots)
    finish_figure(show)

    return df_with_complexity, df_complexity, c_cols


def _report_principal_component(
    df_complexity: pd.DataFrame, keep_cols, root_plots: Path, show: bool
) -> None:
    X_raw = df_complexity[keep_cols].fillna(0).values.astype(float)
    X = (X_raw - X_raw.mean(axis=0)) / (X_raw.std(axis=0) + 1e-12)
    _, S, Vt = np.linalg.svd(X, full_matrices=False)
    pc1 = Vt[0]
    explained = S[0] ** 2 / (S**2).sum()
    df_complexity["complexity_score"] = X @ pc1
    loading_labels = {
        "unique_functions": "Unique Functions",
        "pipes": "Pipes",
        "nesting_depth": "Nesting Depth",
        "variable_bindings": "Variable Bindings",
        "control_flow": "Control Flow",
        "constructions": "Constructions",
        "function_rarity": "Function Rarity",
        "definitions": "Function Definitions",
    }

    fig, (ax_load, ax_perf) = plt.subplots(
        1,
        2,
        figsize=(10, 4),
        gridspec_kw={"width_ratios": [1, 1.4]},
    )
    names = [loading_labels.get(c.replace("complexity:", ""), c) for c in keep_cols]
    weights = pc1.tolist()
    order = np.argsort(weights)
    _set1 = sns.color_palette("Set1")
    ax_load.barh(
        [names[i] for i in order],
        [weights[i] for i in order],
        color=[_set1[1] if w >= 0 else _set1[0] for w in (weights[i] for i in order)],
    )
    ax_load.set_xlabel("Loading")
    ax_load.set_title(f"PC1 ({explained:.0%} var.)")
    ax_load.axvline(0, color="grey", linewidth=0.8)
    df_complexity["score_bin"] = pd.qcut(
        df_complexity["complexity_score"], q=5, duplicates="drop"
    )
    bin_order = sorted(df_complexity["score_bin"].dropna().unique())

    for model in sorted(df_complexity["model"].unique()):
        df_m = df_complexity[df_complexity["model"] == model]
        records = []
        for i, b in enumerate(bin_order):
            grp = df_m[df_m["score_bin"] == b]
            n = len(grp)
            k = int(grp["value_match"].sum())
            rate = k / n if n > 0 else float("nan")
            lo, hi = (
                proportion_confint(k, n, alpha=0.05, method="wilson")
                if n > 0
                else (0, 0)
            )
            records.append({"bin_idx": i, "rate": rate, "ci_lo": lo, "ci_hi": hi})
        r = pd.DataFrame(records)
        label = MODEL_DISPLAY_NAMES.get(model, model)
        ax_perf.plot(r["bin_idx"], r["rate"], marker="o", label=label, linewidth=2)
        ax_perf.fill_between(r["bin_idx"], r["ci_lo"], r["ci_hi"], alpha=0.15)
    ax_perf.set_xlabel("Complexity (quintile)")
    ax_perf.set_ylabel("Value Match Rate")
    ax_perf.set_xticks(range(len(bin_order)))
    ax_perf.set_xticklabels([f"Q{i + 1}" for i in range(len(bin_order))])
    ax_perf.set_ylim(0, 1.05)
    ax_perf.legend(title="Model", bbox_to_anchor=(1.05, 1), loc="upper left")
    fig.tight_layout()
    save_figure(fig, "complexity-composite", root_plots)
    finish_figure(show)


def _report_two_components(
    c_cols, df_complexity: pd.DataFrame, root_plots: Path, show: bool
) -> None:
    keep_cols_2 = c_cols
    X_raw_2 = df_complexity[keep_cols_2].fillna(0).values.astype(float)
    X_2 = (X_raw_2 - X_raw_2.mean(axis=0)) / (X_raw_2.std(axis=0) + 1e-12)
    _, S_2, Vt_2 = np.linalg.svd(X_2, full_matrices=False)
    pc1_2 = Vt_2[0]
    pc2_2 = Vt_2[1]
    var_exp = S_2[:2] ** 2 / (S_2**2).sum()
    scores_2pc = X_2 @ Vt_2[:2].T  # (n, 2)
    df_complexity["pc1"] = scores_2pc[:, 0]
    df_complexity["pc2"] = scores_2pc[:, 1]
    loading_labels_2 = {
        "unique_functions": "Unique Func.",
        "pipes": "Pipes",
        "nesting_depth": "Nesting",
        "variable_bindings": "Var. Bindings",
        "control_flow": "Control Flow",
        "constructions": "Obj/Arr Constr.",
        "function_rarity": "Func. Rarity",
        "definitions": "Definitions",
    }
    names_2 = [
        loading_labels_2.get(c.replace("complexity:", ""), c) for c in keep_cols_2
    ]
    _set1 = sns.color_palette("Set1")

    fig, axes = plt.subplots(
        2,
        2,
        figsize=(12, 8),
        gridspec_kw={"width_ratios": [1, 1.4]},
    )
    w1 = pc1_2.tolist()
    order1 = np.argsort(w1)
    axes[0, 0].barh(
        [names_2[i] for i in order1],
        [w1[i] for i in order1],
        color=[_set1[1] if w >= 0 else _set1[0] for w in (w1[i] for i in order1)],
    )
    axes[0, 0].set_xlabel("Loading")
    axes[0, 0].set_title(f"PC1 ({var_exp[0]:.0%} var.)")
    axes[0, 0].axvline(0, color="grey", linewidth=0.8)
    df_complexity["pc1_bin"] = pd.qcut(df_complexity["pc1"], q=5, duplicates="drop")
    bin_order_1 = sorted(df_complexity["pc1_bin"].dropna().unique())

    for model in sorted(df_complexity["model"].unique()):
        df_m = df_complexity[df_complexity["model"] == model]
        records = []
        for i, b in enumerate(bin_order_1):
            grp = df_m[df_m["pc1_bin"] == b]
            n = len(grp)
            k = int(grp["value_match"].sum())
            rate = k / n if n > 0 else float("nan")
            lo, hi = (
                proportion_confint(k, n, alpha=0.05, method="wilson")
                if n > 0
                else (0, 0)
            )
            records.append({"bin_idx": i, "rate": rate, "ci_lo": lo, "ci_hi": hi})
        r = pd.DataFrame(records)
        label = MODEL_DISPLAY_NAMES.get(model, model)
        axes[0, 1].plot(r["bin_idx"], r["rate"], marker="o", label=label, linewidth=2)
        axes[0, 1].fill_between(r["bin_idx"], r["ci_lo"], r["ci_hi"], alpha=0.15)
    axes[0, 1].set_xlabel("PC1 (quintile)")
    axes[0, 1].set_ylabel("Value Match Rate")
    axes[0, 1].set_xticks(range(len(bin_order_1)))
    axes[0, 1].set_xticklabels([f"Q{i + 1}" for i in range(len(bin_order_1))])
    axes[0, 1].set_ylim(0, 1.05)
    axes[0, 1].legend(title="Model", bbox_to_anchor=(1.05, 1), loc="upper left")
    w2 = pc2_2.tolist()
    order2 = np.argsort(w2)
    axes[1, 0].barh(
        [names_2[i] for i in order2],
        [w2[i] for i in order2],
        color=[_set1[1] if w >= 0 else _set1[0] for w in (w2[i] for i in order2)],
    )
    axes[1, 0].set_xlabel("Loading")
    axes[1, 0].set_title(f"PC2 ({var_exp[1]:.0%} var.)")
    axes[1, 0].axvline(0, color="grey", linewidth=0.8)
    df_complexity["pc2_bin"] = pd.qcut(df_complexity["pc2"], q=5, duplicates="drop")
    bin_order_2 = sorted(df_complexity["pc2_bin"].dropna().unique())

    for model in sorted(df_complexity["model"].unique()):
        df_m = df_complexity[df_complexity["model"] == model]
        records = []
        for i, b in enumerate(bin_order_2):
            grp = df_m[df_m["pc2_bin"] == b]
            n = len(grp)
            k = int(grp["value_match"].sum())
            rate = k / n if n > 0 else float("nan")
            lo, hi = (
                proportion_confint(k, n, alpha=0.05, method="wilson")
                if n > 0
                else (0, 0)
            )
            records.append({"bin_idx": i, "rate": rate, "ci_lo": lo, "ci_hi": hi})
        r = pd.DataFrame(records)
        label = MODEL_DISPLAY_NAMES.get(model, model)
        axes[1, 1].plot(r["bin_idx"], r["rate"], marker="o", label=label, linewidth=2)
        axes[1, 1].fill_between(r["bin_idx"], r["ci_lo"], r["ci_hi"], alpha=0.15)
    axes[1, 1].set_xlabel("PC2 (quintile)")
    axes[1, 1].set_ylabel("Value Match Rate")
    axes[1, 1].set_xticks(range(len(bin_order_2)))
    axes[1, 1].set_xticklabels([f"Q{i + 1}" for i in range(len(bin_order_2))])
    axes[1, 1].set_ylim(0, 1.05)
    fig.tight_layout()
    save_figure(fig, "complexity-composite-2pc", root_plots)
    finish_figure(show)


def _report_complexity_drop(
    df_complexity: pd.DataFrame, keep_cols, root_plots: Path, show: bool
) -> None:
    nice_names = {
        "complexity:unique_functions": "Unique Functions",
        "complexity:pipes": "Pipes",
        "complexity:nesting_depth": "Nesting Depth",
        "complexity:variable_bindings": "Variable Bindings",
        "complexity:control_flow": "Control Flow",
        "complexity:constructions": "Objects / Arrays",
        "complexity:function_rarity": "Function Rarity",
        "complexity:definitions": "Function Definitions",
    }
    models_ordered = ["ClaudeOpus41", "Gpt5Chat", "Gpt5ChatMini", "Phi4"]
    drop_rows = []

    for model in models_ordered:
        df_m = df_complexity[df_complexity["model"] == model]
        for col in keep_cols:
            med = df_m[col].median()
            low = df_m[df_m[col] <= med]["value_match"].mean()
            high = df_m[df_m[col] > med]["value_match"].mean()
            drop_rows.append(
                {
                    "Model": MODEL_DISPLAY_NAMES.get(model, model),
                    "Metric": nice_names[col],
                    "drop": low - high,
                }
            )
    df_drop = pd.DataFrame(drop_rows).pivot(
        index="Metric", columns="Model", values="drop"
    )
    df_drop = df_drop[[MODEL_DISPLAY_NAMES.get(m, m) for m in models_ordered]]
    _set1 = sns.color_palette("Set1")
    _cmap_set1 = LinearSegmentedColormap.from_list(
        "set1_rg", [_set1[0], (1, 1, 1), _set1[2]]
    )

    fig, ax = plt.subplots(figsize=(8, 5))
    sns.heatmap(
        df_drop,
        annot=True,
        fmt=".2f",
        cmap=_cmap_set1,
        center=0,
        linewidths=0.5,
        ax=ax,
        cbar_kws={"label": "$\\Delta$ accuracy"},
        annot_kws={"size": 14},
    )
    ax.set_ylabel("")
    ax.set_xlabel("")
    ax.tick_params(axis="y", rotation=0)
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right", rotation_mode="anchor")
    fig.tight_layout()
    save_figure(fig, "complexity-heatmap", root_plots)
    finish_figure(show)


def _report_complexity_profiles(
    df_complexity: pd.DataFrame, root_plots: Path, show: bool
) -> None:
    radar_cols = [
        "complexity:unique_functions",
        "complexity:pipes",
        "complexity:nesting_depth",
        "complexity:control_flow",
        "complexity:constructions",
        "complexity:variable_bindings",
        "complexity:function_rarity",
        "complexity:definitions",
    ]
    radar_labels = [
        "Unique Functions",
        "Pipes",
        "Nesting Depth",
        "Control Flow",
        "Constructions",
        "Variable Bindings",
        "Function Rarity",
        "Function Definitions",
    ]
    norm_min = df_complexity[radar_cols].min()
    norm_range = df_complexity[radar_cols].max() - norm_min
    norm_range = norm_range.replace(0, 1)  # avoid /0
    models_radar = ["ClaudeOpus41", "Gpt5Chat", "Gpt5ChatMini", "Phi4"]
    n = len(models_radar)
    angles = np.linspace(0, 2 * np.pi, len(radar_cols), endpoint=False).tolist()
    angles += angles[:1]  # close the loop

    fig, axes = plt.subplots(1, n, figsize=(4 * n, 4.5), subplot_kw={"polar": True})

    for ax, model in zip(axes, models_radar):
        df_m = df_complexity[df_complexity["model"] == model]
        solved = df_m[df_m["value_match"] >= 0.5]
        failed = df_m[df_m["value_match"] < 0.5]
        vals_solved = ((solved[radar_cols].mean() - norm_min) / norm_range).tolist()
        vals_failed = ((failed[radar_cols].mean() - norm_min) / norm_range).tolist()
        vals_solved += vals_solved[:1]
        vals_failed += vals_failed[:1]
        ax.fill(angles, vals_solved, alpha=0.15, color="tab:green")
        ax.plot(
            angles,
            vals_solved,
            "o-",
            color="tab:green",
            label=f"Solved ({len(solved)})",
            linewidth=2,
        )
        ax.fill(angles, vals_failed, alpha=0.15, color="tab:red")
        ax.plot(
            angles,
            vals_failed,
            "o-",
            color="tab:red",
            label=f"Failed ({len(failed)})",
            linewidth=2,
        )
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(radar_labels, size=10)
        ax.set_ylim(0, 1)
        ax.set_title(MODEL_DISPLAY_NAMES.get(model, model), pad=18, fontsize=13)
        ax.legend(loc="lower right", fontsize=7, bbox_to_anchor=(1.2, -0.1))
    fig.suptitle("Solved vs failed complexity profile", y=1.02, fontsize=15)
    fig.tight_layout()
    save_figure(fig, "complexity-radar", root_plots)
    finish_figure(show)


def _report_creation_difficulty(
    df_benchmarks: pd.DataFrame,
    df_with_complexity: pd.DataFrame,
    root: Path,
    root_plots: Path,
    show: bool,
) -> None:
    fixed_ids = set(df_benchmarks["identifier"])
    traj_gpt = load_trajectories(
        root / "c_convert" / "converted-gpt5chat.json", fixed_ids
    )
    traj_claude = load_trajectories(
        root / "c_convert" / "converted-claudeopus46.json", fixed_ids
    )
    df_diff_gpt = pd.DataFrame(traj_gpt)
    df_diff_claude = pd.DataFrame(traj_claude)

    with open(root / "b_extract" / "extracted.json", encoding="utf-8") as f:
        extracted = json.load(f)
    fixed_data = load("jqStack", path=paths.data).model_dump(mode="json")
    fixed_exprs = {
        b["identifier"]: min(b["expressions"], key=len)
        for b in fixed_data["benchmarks"]
    }
    ext_by_id = {r["id"]: r for r in extracted}
    dist_rows = []

    for ident, final_expr in fixed_exprs.items():
        r = ext_by_id.get(ident)
        if not r:
            continue
        ext_jqs = [e["jq"] for e in r["expressions"] if "jq" in e]
        best_sim = (
            max(
                difflib.SequenceMatcher(None, ejq, final_expr).ratio()
                for ejq in ext_jqs
            )
            if ext_jqs and final_expr
            else 0
        )
        dist_rows.append(
            {"identifier": ident, "difficulty:dist_from_original": 1.0 - best_sim}
        )
    df_dist = pd.DataFrame(dist_rows)
    print(f"GPT-5 trajectories matched:  {len(df_diff_gpt)}")
    print(f"Claude trajectories matched: {len(df_diff_claude)}")
    print(f"Distance records:            {len(df_dist)}")
    models_eval = {"Gpt5Chat", "ClaudeOpus41", "Gpt5ChatMini", "Phi4"}
    panels = [
        ("Iterations\n(gpt-5)", df_diff_gpt, "difficulty:iterations"),
        ("Iterations\n(claude)", df_diff_claude, "difficulty:iterations"),
        ("Dist. from\noriginal", df_dist, "difficulty:dist_from_original"),
    ]

    fig, axes = plt.subplots(1, len(panels), figsize=(4 * len(panels), 4), sharey=True)

    for ax, (title, df_diff, col) in zip(axes, panels):
        df_merged = df_with_complexity.merge(df_diff, on="identifier", how="inner")
        df_merged = df_merged[
            (df_merged.solver == "JqAgent+Implicit")
            & (df_merged.dataset == "jqStackFixed")
            & (df_merged["input-kind"] == "InputOutput")
            & df_merged.model.isin(models_eval)
        ].copy()
        df_merged[f"{col}_bin"] = pd.qcut(df_merged[col], q=5, duplicates="drop")
        bin_order = sorted(df_merged[f"{col}_bin"].dropna().unique())
        records = []
        for model in df_merged["model"].unique():
            df_m = df_merged[df_merged["model"] == model]
            for i, b in enumerate(bin_order):
                grp = df_m[df_m[f"{col}_bin"] == b]
                n = len(grp)
                k = int(grp["value_match"].sum())
                rate = k / n if n > 0 else float("nan")
                lo, hi = (
                    proportion_confint(k, n, alpha=0.05, method="wilson")
                    if n > 0
                    else (0, 0)
                )
                records.append(
                    {
                        "model": MODEL_DISPLAY_NAMES.get(model, model),
                        "bin_idx": i,
                        "rate": rate,
                        "ci_lo": lo,
                        "ci_hi": hi,
                    }
                )
        df_binned = pd.DataFrame(records)
        for model, grp in df_binned.groupby("model"):
            grp = grp.sort_values("bin_idx")
            ax.plot(grp["bin_idx"], grp["rate"], marker="o", label=model, linewidth=2)
            ax.fill_between(grp["bin_idx"], grp["ci_lo"], grp["ci_hi"], alpha=0.15)
        ax.set_xlabel(title)
        ax.set_xticks(range(len(bin_order)))
        ax.set_xticklabels([f"Q{i + 1}" for i in range(len(bin_order))])
        if ax == axes[0]:
            ax.set_ylabel("Value Match Rate")
        ax.set_ylim(0, 1.05)
    axes[-1].legend(title="Model", bbox_to_anchor=(1.05, 1), loc="upper left")
    fig.tight_layout()
    save_figure(fig, "creation-difficulty", root_plots)
    finish_figure(show)


def _report_iterations(
    df_results: pd.DataFrame, root_plots: Path, root_results: list[Path], show: bool
) -> None:
    df_iter_solutions, df_iter_feedback = load_per_iteration_data(root_results)
    df_cum = df_iter_solutions[
        (df_iter_solutions["input-kind"] == "InputOutput")
        & (df_iter_solutions["dataset"] == "jqStackFixed")
    ].copy()
    _vm = df_results[
        (df_results["dataset"] == "jqStackFixed")
        & df_results["solver"].str.contains("Implicit")
        & ~df_results["solver"].str.contains("Doc")
        & (df_results["input-kind"] == "InputOutput")
        & df_results["solver"].str.contains("Jq")
    ][["identifier", "model", "value_match"]]
    df_cum = df_cum.merge(_vm, on=["identifier", "model"], how="left")
    max_iter = int(df_cum["n_iterations"].max())

    fig, ax = plt.subplots(figsize=(8, 5))

    for (solver, model), grp in sorted(
        df_cum.groupby(["solver", "model"]),
        key=lambda x: x[0],
    ):
        lang = "jq" if "Jq" in solver else "py"
        if lang == "py":
            continue
        total = len(grp)
        label = f"{MODEL_DISPLAY_NAMES.get(model, model)}"
        rates_vm = [
            ((grp["solved_at"].le(k)) & (grp["value_match"] >= 1.0)).sum() / total
            for k in range(1, max_iter + 1)
        ]
        ax.plot(range(1, max_iter + 1), rates_vm, marker="o", label=label, linewidth=2)
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Cumulative Value Match")
    ax.set_xticks(range(1, max_iter + 1))
    ax.set_ylim(0, 1.05)
    ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
    fig.tight_layout()
    save_figure(fig, "cumulative-solution-rate", root_plots)
    finish_figure(show)

    df_fb = df_iter_feedback[
        (df_iter_feedback["input-kind"] == "InputOutput")
        & (df_iter_feedback["dataset"] == "jqStackFixed")
        & df_iter_feedback["solver"].str.contains("Jq")
    ].copy()
    fb_order = ["compile", "execute", "values", "correct"]
    _palette = sns.color_palette("Set1")
    fb_colors = {
        "compile": _palette[0],  # red
        "execute": _palette[3],  # orange
        "values": _palette[1],  # blue
        "correct": _palette[2],  # green
    }
    models_plot = [
        m
        for m in ["ClaudeOpus41", "Gpt5Chat", "Gpt5ChatMini", "Phi4"]
        if m in df_fb["model"].unique()
    ]
    n_models = len(models_plot)

    fig, axes = plt.subplots(1, n_models, figsize=(4 * n_models, 4), sharey=True)

    if n_models == 1:
        axes = [axes]

    for ax, model in zip(axes, models_plot):
        df_m = df_fb[df_fb["model"] == model]
        total_problems = df_m["identifier"].nunique()
        max_it = int(df_m["iteration"].max())
        counts = (
            df_m.groupby(["iteration", "feedback_type"]).size().unstack(fill_value=0)
        )
        for ft in fb_order:
            if ft not in counts.columns:
                counts[ft] = 0
        counts = counts[fb_order]
        fracs = counts / total_problems
        bottom = pd.Series(0.0, index=fracs.index)
        for ft in fb_order:
            ax.bar(
                fracs.index,
                fracs[ft],
                bottom=bottom,
                color=fb_colors[ft],
                label=ft.capitalize(),
                width=0.7,
            )
            bottom += fracs[ft]
        ax.set_xlabel("Iteration")
        ax.set_title(MODEL_DISPLAY_NAMES.get(model, model))
        ax.set_xticks(range(1, max_it + 1))
        if ax == axes[0]:
            ax.set_ylabel("Fraction of Problems")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, bbox_to_anchor=(1.05, 0.5), loc="center left")
    fig.tight_layout()
    save_figure(fig, "feedback-per-iteration", root_plots)
    finish_figure(show)


def generate(output: Path, *, show: bool = False, all_runs: bool = False) -> None:
    root_tables = output / "results" / "tables"
    root_tables.mkdir(parents=True, exist_ok=True)
    root_plots = output / "results" / "plots"
    configure_plots(show=show)
    root = paths.stack
    root_results = [
        paths.results / "fixed",
        paths.results / "spider" / "kind=Schema-which=Na",
    ]
    df_benchmarks, df_results, df = _load_report_data(
        all_runs, root_results, root_tables
    )
    _report_tables(df, root_tables)
    df_with_complexity, df_complexity, c_cols = _report_complexity(
        df, df_benchmarks, root_plots, show
    )
    keep_cols = c_cols
    _report_principal_component(df_complexity, keep_cols, root_plots, show)
    _report_two_components(c_cols, df_complexity, root_plots, show)
    _report_complexity_drop(df_complexity, keep_cols, root_plots, show)
    _report_complexity_profiles(df_complexity, root_plots, show)
    _report_creation_difficulty(
        df_benchmarks, df_with_complexity, root, root_plots, show
    )
    _report_iterations(df_results, root_plots, root_results, show)


def main(argv: list[str] | None = None) -> None:
    args = arguments(__doc__, argv, paper=True)
    generate(args.output, show=args.show, all_runs=args.all_runs)


def _collect_json_files(
    roots: list[Path],
    pattern: str = "*.json",
) -> list[Path]:
    """Collect JSON files from one or more root directories."""
    files = []
    for root in roots:
        files.extend(root.rglob(pattern))
    return files


if __name__ == "__main__":
    main()
