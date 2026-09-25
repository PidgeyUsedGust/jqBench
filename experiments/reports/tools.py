"""Tools analysis from supplied benchmark artifacts."""

import json
from pathlib import Path

import jq
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from experiments.paths import paths
from experiments.reports import arguments, configure_plots, finish_figure, write_table
from jqbench import load
from jqbench.metrics import EvaluationSettings, ValueMatch, equals


def parse_filename(path: Path) -> tuple[str, str, str]:
    """Extract dataset, solver, and model from a result filename."""
    stem = path.stem
    # Pattern: dataset-solver-model
    parts = stem.split("-")
    dataset = parts[0]
    model = parts[-1]
    solver = "-".join(parts[1:-1])
    return dataset, solver, model


def load_results(results_dir: Path) -> list[dict]:
    """Load all result files from a directory into a list of records."""
    records = []
    for f in sorted(results_dir.glob("*.json")):
        dataset, solver, model = parse_filename(f)
        with open(f, encoding="utf-8") as fp:
            data = json.load(fp)
        records.append(
            {
                "path": f,
                "dataset": dataset,
                "solver": solver,
                "model": model,
                "solutions": data["solutions"],
            }
        )
    return records


def jq_execute(expression: str, input_data):
    """Execute a jq expression on input data (simple, no multiprocessing)."""
    try:
        compiled = jq.compile(expression)
        result = compiled.input_value(input_data).all()
        return result
    except Exception:
        return None


def _report_explicit_tools(
    bench_by_id, io_fixed, root_plots: Path, root_tables: Path, show: bool
) -> pd.DataFrame:
    tool_rows = []

    for r in io_fixed:
        if "+Implicit" in r["solver"] or "Python" in r["solver"]:
            continue
        for sol in r["solutions"]:
            all_tools = [t for ts in sol["metadata"]["tools"] for t in ts]
            test_tools = [t for t in all_tools if t["tool"] == "test_expression"]
            n_inputs = len(sol["inputs"]) if sol["inputs"] else 0

            # Count unique inputs tested
            tested_input_strs = [t["arguments"].get("i", "") for t in test_tools]
            unique_inputs = set(tested_input_strs)

            # Match tested inputs to benchmark inputs
            bench = bench_by_id.get(sol["identifier"])
            bench_inputs_json = (
                [json.dumps(inp, sort_keys=True) for inp in bench["inputs"]]
                if bench and bench["inputs"]
                else []
            )
            matched_inputs = set()
            for tested_str in unique_inputs:
                try:
                    tested_parsed = json.dumps(json.loads(tested_str), sort_keys=True)
                except (json.JSONDecodeError, ValueError):
                    continue
                for i, bi in enumerate(bench_inputs_json):
                    if tested_parsed == bi:
                        matched_inputs.add(i)

            # Count rounds (iterations)
            n_rounds = len(sol["metadata"]["tools"])

            # Errors in tool results
            n_errors = sum(
                1
                for t in test_tools
                if "ExecutionError" in t.get("result", {}).get("values", {})
                or "CompileError" in t.get("result", {}).get("values", {})
            )
            metrics = sol["predictions"][0]["metrics"]
            tool_rows.append(
                {
                    "model": r["model"],
                    "solver": r["solver"],
                    "identifier": sol["identifier"],
                    "n_inputs_provided": n_inputs,
                    "n_tool_calls": len(test_tools),
                    "n_unique_inputs_tested": len(unique_inputs),
                    "n_matched_inputs": len(matched_inputs),
                    "n_unmatched_inputs": len(unique_inputs) - len(matched_inputs),
                    "n_rounds": n_rounds,
                    "n_errors": n_errors,
                    "used_tools": len(test_tools) > 0,
                    "value_match": metrics["value_match"] in ("Exact", "Unwrapped"),
                    "compiles": metrics["compiles"],
                    "executes": metrics["executes"],
                }
            )
    df_tools = pd.DataFrame(tool_rows)
    print(f"Non-implicit tool usage records: {len(df_tools)}")
    write_table(
        df_tools.groupby(["solver", "model"])
        .agg(
            total=("identifier", "count"),
            used_tools=("used_tools", "sum"),
            pct_used_tools=("used_tools", "mean"),
            mean_tool_calls=("n_tool_calls", "mean"),
            mean_unique_inputs=("n_unique_inputs_tested", "mean"),
            mean_matched=("n_matched_inputs", "mean"),
            value_match_rate=("value_match", "mean"),
        )
        .round(3),
        root_tables / "table-01.csv",
    )
    df_tools_used = df_tools[df_tools["used_tools"]].copy()
    df_tools_used["input_coverage"] = (
        df_tools_used["n_matched_inputs"] / df_tools_used["n_inputs_provided"]
    )

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    sns.boxplot(
        data=df_tools_used,
        x="model",
        y="n_tool_calls",
        ax=axes[0],
        showfliers=False,
        palette="Set1",
    )
    axes[0].set_xlabel(None)
    axes[0].set_ylabel("# tool calls")
    axes[0].set_title("Tool calls per solution")
    sns.boxplot(
        data=df_tools_used,
        x="model",
        y="n_unique_inputs_tested",
        ax=axes[1],
        showfliers=False,
        palette="Set1",
    )
    axes[1].set_xlabel(None)
    axes[1].set_ylabel("# unique inputs tested")
    axes[1].set_title("Unique inputs tested")
    sns.boxplot(
        data=df_tools_used,
        x="model",
        y="input_coverage",
        ax=axes[2],
        showfliers=False,
        palette="Set1",
    )
    axes[2].set_xlabel(None)
    axes[2].set_ylabel("Input coverage")
    axes[2].set_title("Fraction of inputs tested")
    plt.tight_layout()
    plt.savefig(root_plots / "tools-non-implicit-usage.pdf", bbox_inches="tight")
    finish_figure(show)

    tool_use_rate = df_tools.groupby(["solver", "model"]).agg(
        total=("identifier", "count"),
        used=("used_tools", "sum"),
        rate=("used_tools", "mean"),
    )
    print("Tool use rate (non-implicit):")
    write_table(tool_use_rate, root_tables / "table-02.csv")

    for model in df_tools_used["model"].unique():
        sub = df_tools_used[df_tools_used["model"] == model]
        print(f"\n{model} (n={len(sub)}, with tools):")
        print(f"  Mean tool calls: {sub['n_tool_calls'].mean():.1f}")
        print(
            f"  Mean unique inputs tested: {sub['n_unique_inputs_tested'].mean():.1f}"
        )
        print(
            f"  Mean matched to benchmark: {sub['n_matched_inputs'].mean():.1f} / {sub['n_inputs_provided'].mean():.1f}"
        )
        print(f"  Mean input coverage: {sub['input_coverage'].mean():.1%}")
        print(
            f"  Fabricated inputs (unmatched): {sub['n_unmatched_inputs'].mean():.1f}"
        )

    for solver in df_tools["solver"].unique():
        sub = df_tools[df_tools["solver"] == solver]
        for model in sub["model"].unique():
            m = sub[sub["model"] == model]
            used = m[m["used_tools"]]
            not_used = m[~m["used_tools"]]
            if len(not_used) == 0 or len(used) == 0:
                continue
            print(
                f"{solver} {model}: "
                f"with tools={used['value_match'].mean():.1%} (n={len(used)}), "
                f"without={not_used['value_match'].mean():.1%} (n={len(not_used)})"
            )

    return df_tools


def _report_reference_feedback(bench_by_id, execute: bool, io_fixed) -> None:
    if execute:
        feedback_rows = []
        for r in io_fixed:
            if "+Implicit" in r["solver"] or "Python" in r["solver"]:
                continue
            for sol in r["solutions"]:
                all_tools = [t for ts in sol["metadata"]["tools"] for t in ts]
                test_tools = [t for t in all_tools if t["tool"] == "test_expression"]
                if not test_tools:
                    continue
                bench = bench_by_id.get(sol["identifier"])
                if not bench or not bench.get("expressions"):
                    continue
                solution_expr = bench["expressions"][0]
                settings = EvaluationSettings(**(bench.get("settings") or {}))

                # Check the last test call in each round
                last_tool = test_tools[-1]
                tool_result = last_tool.get("result", {}).get("values", {})
                tool_input_str = last_tool["arguments"].get("i", "")

                if "Result" not in tool_result:
                    # Last call errored - still submitted
                    feedback_rows.append(
                        {
                            "model": r["model"],
                            "solver": r["solver"],
                            "identifier": sol["identifier"],
                            "last_call_ok": False,
                            "last_call_error": True,
                            "value_match": sol["predictions"][0]["metrics"][
                                "value_match"
                            ]
                            in ("Exact", "Unwrapped"),
                        }
                    )
                    continue

                # Compare tool output with expected output for that input
                try:
                    tool_input = json.loads(tool_input_str)
                    expected_output = jq_execute(solution_expr, tool_input)
                    actual_output = tool_result["Result"]
                    if expected_output is None:
                        last_ok = False
                    else:
                        match = equals(expected_output, actual_output, settings)
                        last_ok = match != ValueMatch.No
                except Exception:
                    last_ok = False
                feedback_rows.append(
                    {
                        "model": r["model"],
                        "solver": r["solver"],
                        "identifier": sol["identifier"],
                        "last_call_ok": last_ok,
                        "last_call_error": False,
                        "value_match": sol["predictions"][0]["metrics"]["value_match"]
                        in ("Exact", "Unwrapped"),
                    }
                )
        df_feedback = pd.DataFrame(feedback_rows)
        print(f"Feedback analysis records: {len(df_feedback)}")

        # "Feedback ignored" = last tool output didn't match expected, but model submitted anyway
        for solver in df_feedback["solver"].unique():
            sub = df_feedback[df_feedback["solver"] == solver]
            for model in sub["model"].unique():
                m = sub[sub["model"] == model]
                n_total = len(m)
                n_last_ok = m["last_call_ok"].sum()
                n_last_error = m["last_call_error"].sum()
                n_last_wrong = n_total - n_last_ok - n_last_error
                # "Ignored" = last output was wrong (not matching expected), model submitted
                n_ignored = n_last_wrong + n_last_error
                print(
                    f"{solver} {model} (n={n_total}): "
                    f"last_ok={n_last_ok} ({n_last_ok / n_total:.1%}), "
                    f"last_wrong={n_last_wrong} ({n_last_wrong / n_total:.1%}), "
                    f"last_error={n_last_error} ({n_last_error / n_total:.1%}), "
                    f"feedback_ignored={n_ignored} ({n_ignored / n_total:.1%})"
                )


def _report_implicit_feedback(
    io_fixed, root_plots: Path, root_tables: Path, show: bool
) -> pd.DataFrame:
    implicit_rows = []

    for r in io_fixed:
        if "+Implicit" not in r["solver"]:
            continue
        for sol in r["solutions"]:
            fb = sol["metadata"].get("feedback", [])
            if not sol.get("predictions") or not fb:
                continue
            metrics = sol["predictions"][0]["metrics"]

            # Classify each feedback entry
            n_pass = sum(1 for f in fb if f is True)
            n_fail = len(fb) - n_pass

            # Classify feedback error types
            compile_errors = sum(
                1 for f in fb if isinstance(f, str) and "compile" in f.lower()
            )
            exec_errors = sum(
                1 for f in fb if isinstance(f, str) and "Unable to evaluate" in f
            )
            value_errors = sum(
                1 for f in fb if isinstance(f, str) and "Expected output" in f
            )

            # Did the model end on a pass or fail?
            final_pass = fb[-1] is True if fb else False
            first_pass = fb[0] is True if fb else False
            implicit_rows.append(
                {
                    "model": r["model"],
                    "solver": r["solver"],
                    "identifier": sol["identifier"],
                    "n_attempts": len(fb),
                    "n_pass": n_pass,
                    "n_fail": n_fail,
                    "compile_errors": compile_errors,
                    "exec_errors": exec_errors,
                    "value_errors": value_errors,
                    "first_pass": first_pass,
                    "final_pass": final_pass,
                    "value_match": metrics["value_match"] in ("Exact", "Unwrapped"),
                    "compiles": metrics["compiles"],
                    "executes": metrics["executes"],
                }
            )
    df_implicit = pd.DataFrame(implicit_rows)
    print(f"Implicit mode records: {len(df_implicit)}")
    implicit_summary = (
        df_implicit.groupby(["solver", "model"])
        .agg(
            total=("identifier", "count"),
            mean_attempts=("n_attempts", "mean"),
            first_pass_rate=("first_pass", "mean"),
            final_pass_rate=("final_pass", "mean"),
            value_match_rate=("value_match", "mean"),
        )
        .round(3)
    )
    print("Implicit mode summary:")
    write_table(implicit_summary, root_tables / "table-03.csv")
    df_implicit_jq = df_implicit[~df_implicit["solver"].str.contains("Python")].copy()

    g = sns.catplot(
        data=df_implicit_jq,
        x="n_attempts",
        col="model",
        kind="count",
        col_wrap=2,
        height=3,
        aspect=1.8,
        alpha=0.75,
        color=sns.color_palette("Set1")[0],
        saturation=1,
    )

    for ax in g.axes.flat:
        ax.set_xlabel("# attempts")
        ax.set_ylabel(None)
        ax.set_yticks([])
    sns.despine(left=True)
    plt.tight_layout()
    plt.savefig(root_plots / "tools-implicit-attempts.pdf", bbox_inches="tight")
    finish_figure(show)

    for solver in sorted(df_implicit["solver"].unique()):
        sub = df_implicit[df_implicit["solver"] == solver]
        for model in sorted(sub["model"].unique()):
            m = sub[sub["model"] == model]
            n = len(m)
            first_pass = m["first_pass"].sum()
            final_pass = m["final_pass"].sum()
            final_fail = n - final_pass
            # "Ignored" = ended with failing feedback
            print(
                f"{solver:>45s} {model:<18s} | "
                f"first_pass={first_pass:>5} ({first_pass / n:.1%}), "
                f"final_pass={final_pass:>5} ({final_pass / n:.1%}), "
                f"feedback_ignored={final_fail:>5} ({final_fail / n:.1%})"
            )
    error_rows = []

    for solver in sorted(df_implicit_jq["solver"].unique()):
        sub = df_implicit_jq[df_implicit_jq["solver"] == solver]
        for model in sorted(sub["model"].unique()):
            m = sub[sub["model"] == model]
            error_rows.append(
                {
                    "solver": solver,
                    "model": model,
                    "Compile errors": m["compile_errors"].sum(),
                    "Execution errors": m["exec_errors"].sum(),
                    "Value mismatches": m["value_errors"].sum(),
                }
            )
    df_errors = pd.DataFrame(error_rows)
    df_errors_melted = df_errors.melt(
        id_vars=["solver", "model"],
        value_vars=["Compile errors", "Execution errors", "Value mismatches"],
        var_name="Error type",
        value_name="Count",
    )
    df_errors_melted["label"] = (
        df_errors_melted["solver"].str.replace("JqAgent", "").str.strip("+")
        + " "
        + df_errors_melted["model"]
    )
    df_errors_melted["label"] = df_errors_melted["label"].str.strip()

    fig, ax = plt.subplots(figsize=(12, 5))
    sns.barplot(
        data=df_errors_melted,
        x="label",
        y="Count",
        hue="Error type",
        ax=ax,
        alpha=0.75,
    )
    plt.xticks(rotation=45, ha="right")
    ax.set_xlabel(None)
    sns.despine()
    plt.tight_layout()
    plt.savefig(root_plots / "tools-implicit-error-types.pdf", bbox_inches="tight")
    finish_figure(show)

    return df_implicit


def _report_modes(io_fixed, root_plots: Path, root_tables: Path, show: bool) -> None:
    comparison_rows = []

    for r in io_fixed:
        if "Python" in r["solver"]:
            continue
        is_implicit = "+Implicit" in r["solver"]
        has_doc = "+Documentation" in r["solver"]
        mode = []
        if is_implicit:
            mode.append("Implicit")
        if has_doc:
            mode.append("Documentation")
        if not mode:
            mode.append("Explicit")
        mode_str = "+".join(mode)

        for sol in r["solutions"]:
            if not sol.get("predictions"):
                continue
            metrics = sol["predictions"][0]["metrics"]
            comparison_rows.append(
                {
                    "model": r["model"],
                    "mode": mode_str,
                    "identifier": sol["identifier"],
                    "value_match": metrics["value_match"] in ("Exact", "Unwrapped"),
                    "compiles": metrics["compiles"],
                    "executes": metrics["executes"],
                }
            )
    df_compare = pd.DataFrame(comparison_rows)
    comparison_summary = (
        df_compare.groupby(["model", "mode"])
        .agg(
            total=("identifier", "count"),
            compiles=("compiles", "mean"),
            executes=("executes", "mean"),
            value_match=("value_match", "mean"),
        )
        .round(3)
    )
    print("Performance by mode:")
    write_table(comparison_summary, root_tables / "table-04.csv")

    fig, ax = plt.subplots(figsize=(12, 5))
    pivot = df_compare.groupby(["model", "mode"])["value_match"].mean().unstack("mode")
    pivot.plot.bar(ax=ax, alpha=0.75)
    ax.set_ylabel("Value match rate")
    ax.set_xlabel(None)
    ax.legend(title="Mode", bbox_to_anchor=(1.02, 1), loc="upper left")
    plt.xticks(rotation=0)
    sns.despine()
    plt.tight_layout()
    plt.savefig(root_plots / "tools-mode-comparison.pdf", bbox_inches="tight")
    finish_figure(show)


def _report_rounds(io_fixed, root_plots: Path, root_tables: Path, show: bool) -> None:
    round_rows = []

    for r in io_fixed:
        if "+Implicit" in r["solver"] or "Python" in r["solver"]:
            continue
        for sol in r["solutions"]:
            n_inputs = len(sol["inputs"]) if sol["inputs"] else 0
            for round_idx, round_tools in enumerate(sol["metadata"]["tools"]):
                test_calls = [t for t in round_tools if t["tool"] == "test_expression"]
                unique_inputs_in_round = len(
                    set(t["arguments"].get("i", "") for t in test_calls)
                )
                round_rows.append(
                    {
                        "model": r["model"],
                        "solver": r["solver"],
                        "identifier": sol["identifier"],
                        "round": round_idx,
                        "n_test_calls": len(test_calls),
                        "n_unique_inputs": unique_inputs_in_round,
                        "n_inputs_provided": n_inputs,
                    }
                )
    df_rounds = pd.DataFrame(round_rows)

    if len(df_rounds) > 0:
        print("Per-round tool usage:")
        write_table(
            df_rounds.groupby("model")
            .agg(
                total_rounds=("round", "count"),
                mean_calls_per_round=("n_test_calls", "mean"),
                mean_unique_inputs_per_round=("n_unique_inputs", "mean"),
            )
            .round(2),
            root_tables / "table-05.csv",
        )

        # Distribution of inputs tested per round
        fig, ax = plt.subplots(figsize=(8, 4))
        sns.histplot(
            data=df_rounds,
            x="n_unique_inputs",
            hue="model",
            multiple="dodge",
            discrete=True,
            ax=ax,
            alpha=0.75,
            shrink=0.8,
        )
        ax.set_xlabel("# unique inputs tested per round")
        ax.set_ylabel("# rounds")
        sns.despine()
        plt.tight_layout()
        plt.savefig(root_plots / "tools-inputs-per-round.pdf", bbox_inches="tight")
        finish_figure(show)


def _report_documentation(io_fixed, root_tables: Path) -> None:
    doc_rows = []

    for r in io_fixed:
        if "+Documentation" not in r["solver"]:
            continue
        for sol in r["solutions"]:
            if not sol.get("predictions"):
                continue
            all_tools = [t for ts in sol["metadata"]["tools"] for t in ts]
            search_tools = [t for t in all_tools if t["tool"] == "search_documentation"]
            test_tools = [t for t in all_tools if t["tool"] == "test_expression"]
            metrics = sol["predictions"][0]["metrics"]
            doc_rows.append(
                {
                    "model": r["model"],
                    "solver": r["solver"],
                    "identifier": sol["identifier"],
                    "n_doc_searches": len(search_tools),
                    "n_test_calls": len(test_tools),
                    "used_docs": len(search_tools) > 0,
                    "used_tests": len(test_tools) > 0,
                    "value_match": metrics["value_match"] in ("Exact", "Unwrapped"),
                }
            )
    df_docs = pd.DataFrame(doc_rows)

    if len(df_docs) > 0:
        doc_summary = (
            df_docs.groupby("model")
            .agg(
                total=("identifier", "count"),
                used_docs_rate=("used_docs", "mean"),
                used_tests_rate=("used_tests", "mean"),
                mean_doc_searches=("n_doc_searches", "mean"),
                mean_test_calls=("n_test_calls", "mean"),
                value_match=("value_match", "mean"),
            )
            .round(3)
        )
        print("Documentation+Implicit tool usage:")
        write_table(doc_summary, root_tables / "table-06.csv")

    if len(df_docs) > 0:
        for model in sorted(df_docs["model"].unique()):
            m = df_docs[df_docs["model"] == model]
            used = m[m["used_docs"]]
            not_used = m[~m["used_docs"]]
            if len(used) == 0 or len(not_used) == 0:
                print(
                    f"{model}: all {'used' if len(not_used) == 0 else 'skipped'} docs"
                )
                continue
            print(
                f"{model}: with docs={used['value_match'].mean():.1%} (n={len(used)}), "
                f"without={not_used['value_match'].mean():.1%} (n={len(not_used)})"
            )


def _print_summary(df_implicit: pd.DataFrame, df_tools: pd.DataFrame) -> None:
    print("=" * 60)
    print("Tool Use Analysis Summary")
    print("=" * 60)
    print("\n--- Non-Implicit (Explicit tool use) ---")

    for solver in df_tools["solver"].unique():
        sub = df_tools[df_tools["solver"] == solver]
        for model in sub["model"].unique():
            m = sub[sub["model"] == model]
            used = m[m["used_tools"]]
            print(f"  {solver} {model}:")
            print(f"    Tool use rate: {m['used_tools'].mean():.1%}")
            if len(used) > 0:
                print(
                    f"    Mean tool calls (when used): {used['n_tool_calls'].mean():.1f}"
                )
                print(
                    f"    Mean inputs tested (when used): {used['n_unique_inputs_tested'].mean():.1f} / {used['n_inputs_provided'].mean():.1f}"
                )
    print("\n--- Implicit (Automatic feedback) ---")

    for solver in sorted(df_implicit["solver"].unique()):
        sub = df_implicit[df_implicit["solver"] == solver]
        for model in sorted(sub["model"].unique()):
            m = sub[sub["model"] == model]
            print(f"  {solver} {model}:")
            print(f"    Mean attempts: {m['n_attempts'].mean():.1f}")
            print(f"    First-attempt pass: {m['first_pass'].mean():.1%}")
            print(f"    Final pass: {m['final_pass'].mean():.1%}")
            print(f"    Feedback ignored (final fail): {(~m['final_pass']).mean():.1%}")


def generate(output: Path, *, show: bool = False, execute: bool = False) -> None:
    root_tables = output / "tools" / "tables"
    root_tables.mkdir(parents=True, exist_ok=True)
    configure_plots(show=show)
    root_results = paths.results
    root_plots = output / "tools" / "plots"
    root_plots.mkdir(parents=True, exist_ok=True)
    benchmarks = load("jqStack", path=paths.data).model_dump(mode="json")["benchmarks"]
    bench_by_id = {b["identifier"]: b for b in benchmarks}
    print(f"Loaded {len(benchmarks)} benchmarks")
    io_fixed = load_results(root_results / "fixed" / "kind=InputOutput-which=AllButOne")
    for r in io_fixed:
        is_implicit = "+Implicit" in r["solver"]
        has_doc = "+Documentation" in r["solver"]
        is_python = "Python" in r["solver"]
        n_tools = sum(
            1
            for s in r["solutions"]
            if any(len(ts) > 0 for ts in s["metadata"]["tools"])
        )
        n_feedback = sum(1 for s in r["solutions"] if s["metadata"].get("feedback"))
        print(
            f"{r['solver']:>45s} | {r['model']:<18s} | "
            f"implicit={is_implicit!s:<5s} doc={has_doc!s:<5s} python={is_python!s:<5s} | "
            f"sols={len(r['solutions']):>5} tools={n_tools:>5} feedback={n_feedback:>5}"
        )
    df_tools = _report_explicit_tools(
        bench_by_id, io_fixed, root_plots, root_tables, show
    )
    _report_reference_feedback(bench_by_id, execute, io_fixed)
    df_implicit = _report_implicit_feedback(io_fixed, root_plots, root_tables, show)
    _report_modes(io_fixed, root_plots, root_tables, show)
    _report_rounds(io_fixed, root_plots, root_tables, show)
    _report_documentation(io_fixed, root_tables)
    _print_summary(df_implicit, df_tools)


def main(argv: list[str] | None = None) -> None:
    args = arguments(__doc__, argv, replay=True)
    generate(args.output, show=args.show, execute=args.execute)


if __name__ == "__main__":
    main()
