"""Spider analysis from supplied benchmark artifacts."""

import json
import re
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
from scipy.stats import pearsonr

from experiments.paths import paths
from experiments.reports import arguments, configure_plots, finish_figure, write_table
from jqbench import load


def _report_conversion(
    converted_records, db_3_files, root_plots: Path, root_tables: Path, show: bool
) -> pd.DataFrame:
    db_conversion = []

    for f in db_3_files:
        with open(f, encoding="utf-8") as fp:
            data = json.load(fp)
        total = len(data)
        success = sum(
            1
            for d in data
            if d.get("converted", {}).get("jq", {}).get("kind") == "success"
        )
        db_conversion.append(
            {
                "database": f.stem,
                "total": total,
                "success": success,
                "failure": total - success,
                "rate": success / total if total > 0 else 0,
            }
        )
    df_db_conv = pd.DataFrame(db_conversion)
    df_db_conv = df_db_conv.sort_values("rate", ascending=False).reset_index(drop=True)
    print(f"Databases with 100% success: {(df_db_conv['rate'] == 1.0).sum()}")
    print(f"Databases with 0% success:   {(df_db_conv['rate'] == 0.0).sum()}")
    print(f"Mean success rate per DB:     {df_db_conv['rate'].mean() * 100:.1f}%")
    print(f"Median success rate per DB:   {df_db_conv['rate'].median() * 100:.1f}%")
    print()
    write_table(df_db_conv.describe(), root_tables / "table-01.csv")

    fig, ax = plt.subplots(figsize=(8, 4))
    sns.histplot(
        df_db_conv["rate"],
        bins=20,
        ax=ax,
        alpha=0.75,
        color=sns.color_palette("Set1")[0],
    )
    ax.set_xlabel("Conversion success rate")
    ax.set_ylabel(None)
    ax.set_yticks([])
    ax.axvline(
        df_db_conv["rate"].median(),
        color="black",
        linestyle="--",
        lw=1.5,
        label=f"median={df_db_conv['rate'].median():.2f}",
    )
    ax.legend()
    sns.despine(left=True)
    plt.tight_layout()
    plt.savefig(root_plots / "spider-conversion-rate-dist.pdf", bbox_inches="tight")
    finish_figure(show)

    n_candidates_on_failure = []

    for d in converted_records:
        jq_conv = d.get("converted", {}).get("jq", {})
        if jq_conv.get("kind") != "success":
            candidates = jq_conv.get("candidates", {})
            n_candidates_on_failure.append(len(candidates))
    print(f"Failed conversions: {len(n_candidates_on_failure)}")
    print(f"  With 0 candidates: {sum(1 for n in n_candidates_on_failure if n == 0)}")
    print(
        f"  With candidates (but wrong output): {sum(1 for n in n_candidates_on_failure if n > 0)}"
    )
    print(f"  Mean candidates per failure: {np.mean(n_candidates_on_failure):.1f}")

    return df_db_conv


def _report_database_structure(
    db_3_files,
    df_db_conv: pd.DataFrame,
    root: Path,
    root_plots: Path,
    root_tables: Path,
    show: bool,
) -> None:
    db_structure_records = []

    for f in db_3_files:
        db_name = f.stem
        db_file = root / "1_databases" / f"{db_name}.json"
        json_file = root / "2_jsonified" / f"{db_name}.json"
        if not db_file.exists() or not json_file.exists():
            continue
        with open(db_file, encoding="utf-8") as fp:
            db_data = json.load(fp)
        with open(json_file, encoding="utf-8") as fp:
            json_data = json.load(fp)
        nested_data = json_data.get("data", {})
        n_tables = len(db_data) if isinstance(db_data, dict) else 0
        nesting = _get_nesting(nested_data)
        db_structure_records.append(
            {
                "database": db_name,
                "tables": n_tables,
                "nesting": nesting,
            }
        )
    df_structure = pd.DataFrame(db_structure_records)
    print(f"Databases analyzed: {len(df_structure)}")
    write_table(df_structure.describe(), root_tables / "table-02.csv")
    write_table(df_structure.head(10), root_tables / "table-03.csv")
    ct = (
        df_structure.groupby(["nesting", "tables"])
        .size()
        .unstack(fill_value=0)
        .sort_index(axis=0)
        .sort_index(axis=1)
    )
    annot_matrix = ct.astype(object)
    annot_matrix[annot_matrix == 0] = ""
    colors = ["#ffffff", sns.color_palette("Set1")[0]]
    cmap = LinearSegmentedColormap.from_list("clean", colors, N=256)
    mask = ct == 0

    fig, ax = plt.subplots(figsize=(7, 4.5))
    sns.heatmap(
        ct,
        cmap=cmap,
        mask=mask,
        cbar=False,
        annot=annot_matrix,
        fmt="",
        annot_kws={"color": "black", "fontsize": 14},
        linewidths=1,
        linecolor="white",
        square=True,
        ax=ax,
    )

    for i in range(ct.shape[0]):
        for j in range(ct.shape[1]):
            if ct.iloc[i, j] == 0:
                ax.add_patch(
                    plt.Rectangle(
                        (j, i), 1, 1, fill=True, color="#f5f5f5", ec="white", lw=1.5
                    )
                )
    ax.grid(False)
    ax.set_xlabel("# of tables")
    ax.set_ylabel("Nesting depth")
    ax.invert_yaxis()
    ax.tick_params(length=0)
    plt.tight_layout()
    plt.savefig(root_plots / "spider-tables-nesting.pdf", bbox_inches="tight")
    finish_figure(show)

    df_db_analysis = df_db_conv.merge(df_structure, on="database", how="inner")
    df_db_analysis = df_db_analysis[df_db_analysis["rate"] > 0.0]
    df_db_analysis_no_outlier = df_db_analysis[df_db_analysis["tables"] <= 14]

    fig, axes = plt.subplots(1, 2, figsize=(8, 5))
    sns.regplot(
        data=df_db_analysis_no_outlier,
        x="tables",
        y="rate",
        ax=axes[0],
        scatter_kws={"s": 60, "alpha": 0.6},
        line_kws={"color": "black", "lw": 2},
    )
    r, p = pearsonr(
        df_db_analysis_no_outlier["tables"], df_db_analysis_no_outlier["rate"]
    )
    sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
    axes[0].set_xlabel("# of tables")
    axes[0].set_ylabel("Conversion success rate")
    axes[0].set_title(f"r = {r:.3f}{sig}")
    sns.regplot(
        data=df_db_analysis,
        x="nesting",
        y="rate",
        ax=axes[1],
        scatter_kws={"s": 60, "alpha": 0.6},
        line_kws={"color": "black", "lw": 2},
    )
    r, p = pearsonr(df_db_analysis["nesting"], df_db_analysis["rate"])
    sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
    axes[1].set_xlabel("Nesting depth")
    axes[1].set_ylabel("Conversion success rate")
    axes[1].set_title(f"r = {r:.3f}{sig}")
    plt.tight_layout()
    plt.savefig(root_plots / "spider-complexity-vs-conversion.pdf", bbox_inches="tight")
    finish_figure(show)


def _report_translations(
    converted_records, root_plots: Path, root_tables: Path, show: bool
) -> None:
    conv_rows = []

    for d in converted_records:
        jq_conv = d.get("converted", {}).get("jq", {})
        if jq_conv.get("kind") != "success":
            continue
        expressions = jq_conv.get("jq", [])
        if not expressions:
            continue
        expr = expressions[0]
        query = d.get("query", "")
        query_upper = query.upper()
        out = d.get("query_output")
        conv_rows.append(
            {
                "database": d["db_id"],
                "query": query,
                "expression": expr,
                "output_type": type(out).__name__,
                "n_join": query_upper.count("JOIN"),
                "has_where": "WHERE" in query_upper,
                "has_groupby": "GROUP BY" in query_upper,
                "has_orderby": "ORDER BY" in query_upper,
                "has_having": "HAVING" in query_upper,
                "has_subquery": query_upper.count("SELECT") > 1,
                "has_agg": any(
                    agg in query_upper for agg in ["COUNT", "SUM", "AVG", "MAX", "MIN"]
                ),
                "n_pipe": expr.count("|"),
                "expr_length": len(expr),
                "has_select": bool(re.search(r"\bselect\b", expr)),
                "has_map": bool(re.search(r"\bmap\b", expr)),
                "has_group_by": bool(re.search(r"\bgroup_by\b", expr)),
                "has_sort_by": bool(re.search(r"\bsort_by\b", expr)),
                "has_unique": bool(re.search(r"\bunique\b", expr)),
                "has_reduce": "reduce" in expr,
                "has_def": bool(re.search(r"\bdef\b", expr)),
            }
        )
    df_conv = pd.DataFrame(conv_rows)
    print(f"Successfully converted queries: {len(df_conv)}")
    write_table(df_conv.describe(), root_tables / "table-04.csv")

    fig, ax = plt.subplots(figsize=(4, 5))
    sns.regplot(
        data=df_conv,
        x="n_join",
        y="n_pipe",
        x_jitter=0.2,
        y_jitter=0.2,
        ax=ax,
        scatter_kws={"s": 60, "alpha": 0.5},
        line_kws={"color": "black", "lw": 2},
    )
    r, p = pearsonr(df_conv["n_join"], df_conv["n_pipe"])
    sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
    ax.set_xlabel("# of SQL JOINs")
    ax.set_ylabel("# of jq pipes ( | )")
    ax.set_title(f"r = {r:.3f}{sig}")
    plt.tight_layout()
    plt.savefig(root_plots / "spider-join-pipe-corr.pdf", bbox_inches="tight")
    finish_figure(show)

    sql_features = [
        "has_where",
        "has_groupby",
        "has_orderby",
        "has_having",
        "has_subquery",
        "has_agg",
    ]
    jq_metrics = ["n_pipe", "expr_length"]

    for metric in jq_metrics:
        rows = []
        for feat in sql_features:
            label = feat.replace("has_", "").upper()
            rows.append(
                {
                    "SQL Feature": label,
                    "Present": "Yes",
                    metric: df_conv.loc[df_conv[feat], metric].mean(),
                }
            )
            rows.append(
                {
                    "SQL Feature": label,
                    "Present": "No",
                    metric: df_conv.loc[~df_conv[feat], metric].mean(),
                }
            )
        df_feat = pd.DataFrame(rows)

        fig, ax = plt.subplots(figsize=(10, 4))
        sns.barplot(
            data=df_feat, x="SQL Feature", y=metric, hue="Present", ax=ax, alpha=0.75
        )
        ax.set_ylabel(f"Mean {metric.replace('_', ' ')}")
        ax.set_xlabel(None)
        plt.tight_layout()
        plt.savefig(
            root_plots / f"spider-sql-features-vs-{metric}.pdf", bbox_inches="tight"
        )
        finish_figure(show)

    df_conv_nonnull = df_conv[df_conv["output_type"] != "NoneType"]

    g = sns.catplot(
        data=df_conv_nonnull,
        x="output_type",
        kind="count",
        order=df_conv_nonnull["output_type"]
        .value_counts()
        .sort_values(ascending=False)
        .index,
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
    ax.set_xlabel("Output type")
    ax.set_ylabel(None)
    ax.set_yticks([])
    sns.despine(left=True)
    plt.savefig(root_plots / "spider-output-types.pdf", bbox_inches="tight")
    finish_figure(show)

    type_rows = []

    for d in converted_records:
        out = d.get("query_output")
        t = type(out).__name__
        jq_kind = d.get("converted", {}).get("jq", {}).get("kind")
        type_rows.append({"output_type": t, "success": jq_kind == "success"})
    df_type = pd.DataFrame(type_rows)
    type_summary = (
        df_type.groupby("output_type")
        .agg(total=("success", "count"), success=("success", "sum"))
        .assign(rate=lambda x: x["success"] / x["total"])
        .sort_values("total", ascending=False)
    )
    write_table(type_summary, root_tables / "table-05.csv")


def _report_sql_features(raw_queries, root_plots: Path, show: bool) -> None:
    sql_feat_rows = []

    for d in raw_queries:
        q = d["query"].upper()
        sql_feat_rows.append(
            {
                "db_id": d["db_id"],
                "n_join": q.count("JOIN"),
                "WHERE": "WHERE" in q,
                "GROUP BY": "GROUP BY" in q,
                "ORDER BY": "ORDER BY" in q,
                "HAVING": "HAVING" in q,
                "LIMIT": "LIMIT" in q,
                "INTERSECT": "INTERSECT" in q,
                "EXCEPT": "EXCEPT" in q,
                "UNION": "UNION" in q,
                "Subquery": q.count("SELECT") > 1,
            }
        )
    df_sql = pd.DataFrame(sql_feat_rows)
    clause_cols = [
        "WHERE",
        "GROUP BY",
        "ORDER BY",
        "HAVING",
        "LIMIT",
        "INTERSECT",
        "EXCEPT",
        "UNION",
        "Subquery",
    ]
    feat_counts = df_sql[clause_cols].sum().sort_values(ascending=True)

    fig, ax = plt.subplots(figsize=(8, 5))
    feat_counts.plot.barh(ax=ax, color=sns.color_palette("Set1")[0], alpha=0.75)

    for i, (val, name) in enumerate(zip(feat_counts.values, feat_counts.index)):
        ax.text(val + 5, i, str(int(val)), va="center")
    ax.set_xlabel("# of queries")
    ax.set_ylabel(None)
    ax.set_title(f"SQL Feature Prevalence (n={len(df_sql):,})")
    sns.despine()
    plt.tight_layout()
    plt.savefig(root_plots / "spider-sql-features.pdf", bbox_inches="tight")
    finish_figure(show)

    agg_counts = Counter()

    for d in raw_queries:
        q = d["query"].upper()
        for agg in ["COUNT", "SUM", "AVG", "MAX", "MIN"]:
            if agg in q:
                agg_counts[agg] += 1
    agg_df = pd.DataFrame(agg_counts.most_common(), columns=["Aggregation", "Count"])

    fig, ax = plt.subplots(figsize=(6, 3))
    sns.barplot(
        data=agg_df,
        x="Aggregation",
        y="Count",
        ax=ax,
        alpha=0.75,
        color=sns.color_palette("Set1")[1],
    )

    for p in ax.patches:
        h = int(p.get_height())
        ax.text(p.get_x() + p.get_width() / 2, h + 5, str(h), ha="center", va="bottom")
    ax.set_ylabel(None)
    ax.set_yticks([])
    ax.set_xlabel(None)
    sns.despine(left=True)
    plt.tight_layout()
    plt.savefig(root_plots / "spider-aggregations.pdf", bbox_inches="tight")
    finish_figure(show)

    join_counts = df_sql["n_join"].value_counts().sort_index()

    fig, ax = plt.subplots(figsize=(6, 3))
    join_counts.plot.bar(ax=ax, color=sns.color_palette("Set1")[0], alpha=0.75)

    for i, (idx, val) in enumerate(join_counts.items()):
        ax.text(i, val + 5, str(val), ha="center", va="bottom")
    ax.set_xlabel("# of JOINs")
    ax.set_ylabel(None)
    ax.set_yticks([])
    sns.despine(left=True)
    plt.tight_layout()
    plt.savefig(root_plots / "spider-join-distribution.pdf", bbox_inches="tight")
    finish_figure(show)


def _report_benchmarks(root_plots: Path, show: bool, spider_benchmarks) -> pd.DataFrame:
    df_bench = pd.DataFrame(
        [
            {
                "identifier": b["identifier"],
                "database": b["identifier"].rsplit(".", 1)[0],
                "expression": b["expressions"][0] if b["expressions"] else "",
                "expr_length": len(b["expressions"][0]) if b["expressions"] else 0,
                "n_pipe": b["expressions"][0].count("|") if b["expressions"] else 0,
                "order": b.get("settings", {}).get("order", False),
            }
            for b in spider_benchmarks
        ]
    )

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    sns.histplot(
        df_bench["expr_length"],
        bins=30,
        ax=axes[0],
        alpha=0.75,
        color=sns.color_palette("Set1")[0],
    )
    axes[0].set_xlabel("Expression length (chars)")
    axes[0].set_ylabel(None)
    axes[0].set_yticks([])
    axes[0].axvline(
        df_bench["expr_length"].median(), color="black", linestyle="--", lw=1.5
    )
    sns.histplot(
        df_bench["n_pipe"],
        bins=range(0, df_bench["n_pipe"].max() + 2),
        ax=axes[1],
        alpha=0.75,
        color=sns.color_palette("Set1")[1],
    )
    axes[1].set_xlabel("# of pipes ( | )")
    axes[1].set_ylabel(None)
    axes[1].set_yticks([])
    axes[1].axvline(df_bench["n_pipe"].median(), color="black", linestyle="--", lw=1.5)
    sns.despine(left=True)
    plt.tight_layout()
    plt.savefig(root_plots / "spider-expression-complexity.pdf", bbox_inches="tight")
    finish_figure(show)

    print(
        f"Expression length: median={df_bench['expr_length'].median():.0f}, mean={df_bench['expr_length'].mean():.0f}"
    )
    print(
        f"Pipe count: median={df_bench['n_pipe'].median():.0f}, mean={df_bench['n_pipe'].mean():.1f}"
    )
    jq_builtins = [
        "select",
        "map",
        "group_by",
        "sort_by",
        "unique",
        "unique_by",
        "length",
        "keys",
        "values",
        "flatten",
        "add",
        "any",
        "all",
        "min_by",
        "max_by",
        "reduce",
        "recurse",
        "to_entries",
        "from_entries",
        "ascii_downcase",
        "ascii_upcase",
        "test",
        "split",
        "join",
        "tostring",
        "tonumber",
        "not",
        "limit",
        "first",
        "last",
        "nth",
        "if",
        "def",
        "try",
        "as",
    ]
    builtin_counts = Counter()

    for _, row in df_bench.iterrows():
        expr = row["expression"]
        for func in jq_builtins:
            if re.search(rf"\b{func}\b", expr):
                builtin_counts[func] += 1
    top_builtins = pd.DataFrame(
        builtin_counts.most_common(15), columns=["Function", "Count"]
    )

    fig, ax = plt.subplots(figsize=(10, 5))
    sns.barplot(
        data=top_builtins,
        x="Function",
        y="Count",
        ax=ax,
        alpha=0.75,
        color=sns.color_palette("Set1")[0],
    )

    for p in ax.patches:
        h = int(p.get_height())
        ax.text(p.get_x() + p.get_width() / 2, h + 2, str(h), ha="center", va="bottom")
    ax.set_ylabel(None)
    ax.set_yticks([])
    ax.set_xlabel(None)
    plt.xticks(rotation=45, ha="right")
    sns.despine(left=True)
    plt.tight_layout()
    plt.savefig(root_plots / "spider-jq-builtins.pdf", bbox_inches="tight")
    finish_figure(show)

    db_bench_counts = df_bench["database"].value_counts()

    fig, ax = plt.subplots(figsize=(14, 5))
    db_bench_counts.head(20).plot.bar(
        ax=ax, color=sns.color_palette("Set1")[0], alpha=0.75
    )

    for i, (idx, val) in enumerate(db_bench_counts.head(20).items()):
        ax.text(i, val + 0.5, str(val), ha="center", va="bottom")
    ax.set_xlabel(None)
    ax.set_ylabel("# of benchmarks")
    ax.set_title(
        f"Top 20 Databases by Benchmark Count (total: {len(db_bench_counts)} DBs)"
    )
    plt.xticks(rotation=45, ha="right")
    sns.despine()
    plt.tight_layout()
    plt.savefig(root_plots / "spider-benchmarks-per-db.pdf", bbox_inches="tight")
    finish_figure(show)

    print(
        f"Benchmarks per DB: mean={db_bench_counts.mean():.1f}, median={db_bench_counts.median():.0f}, "
        f"min={db_bench_counts.min()}, max={db_bench_counts.max()}"
    )

    return df_bench


def _report_conversion_features(
    converted_records, root_plots: Path, root_tables: Path, show: bool
) -> None:
    all_conv_rows = []

    for d in converted_records:
        q = d.get("query", "").upper()
        jq_kind = d.get("converted", {}).get("jq", {}).get("kind")
        all_conv_rows.append(
            {
                "success": jq_kind == "success",
                "n_join": q.count("JOIN"),
                "has_where": "WHERE" in q,
                "has_groupby": "GROUP BY" in q,
                "has_orderby": "ORDER BY" in q,
                "has_having": "HAVING" in q,
                "has_subquery": q.count("SELECT") > 1,
            }
        )
    df_all = pd.DataFrame(all_conv_rows)
    join_success = (
        df_all.groupby("n_join")
        .agg(
            total=("success", "count"),
            success=("success", "sum"),
        )
        .assign(rate=lambda x: x["success"] / x["total"])
    )
    print("Success rate by JOIN count:")
    write_table(join_success, root_tables / "table-06.csv")
    sql_feats = [
        "has_where",
        "has_groupby",
        "has_orderby",
        "has_having",
        "has_subquery",
    ]
    feat_success = []

    for feat in sql_feats:
        label = feat.replace("has_", "").upper()
        present = df_all[df_all[feat]]
        absent = df_all[~df_all[feat]]
        feat_success.append(
            {
                "Feature": label,
                "With: success rate": f"{present['success'].mean() * 100:.1f}%"
                if len(present) > 0
                else "N/A",
                "Without: success rate": f"{absent['success'].mean() * 100:.1f}%"
                if len(absent) > 0
                else "N/A",
                "With: count": len(present),
                "Without: count": len(absent),
            }
        )
    write_table(pd.DataFrame(feat_success), root_tables / "table-07.csv")

    fig, ax = plt.subplots(figsize=(8, 4))
    colors = [sns.color_palette("Set1")[0], sns.color_palette("Set1")[1]]
    join_success[["success", "total"]].assign(
        failure=lambda x: x["total"] - x["success"]
    ).drop(columns="total")[["success", "failure"]].plot.bar(
        stacked=True, ax=ax, color=colors, alpha=0.75
    )
    ax.set_xlabel("# of SQL JOINs")
    ax.set_ylabel("# of queries")
    ax.legend(["Success", "Failure"])
    plt.xticks(rotation=0)
    sns.despine()
    plt.tight_layout()
    plt.savefig(root_plots / "spider-join-vs-success.pdf", bbox_inches="tight")
    finish_figure(show)


def generate(output: Path, *, show: bool = False) -> None:
    root_tables = output / "spider" / "tables"
    root_tables.mkdir(parents=True, exist_ok=True)
    configure_plots(show=show)
    root = paths.spider
    root_plots = output / "spider" / "plots"
    root_plots.mkdir(parents=True, exist_ok=True)
    with open(root / "0_raw" / "test.json", encoding="utf-8") as f:
        raw_queries = json.load(f)
    n_raw_queries = len(raw_queries)
    raw_db_ids = sorted(set(d["db_id"] for d in raw_queries))
    n_raw_dbs = len(raw_db_ids)
    db_1_files = sorted((root / "1_databases").glob("*.json"))
    n_db_1 = len(db_1_files)
    db_2_files = sorted((root / "2_jsonified").glob("*.json"))
    n_db_2 = len(db_2_files)
    db_2_names = {f.stem for f in db_2_files}
    db_3_files = sorted((root / "3_converted").glob("*.json"))
    n_db_3 = len(db_3_files)
    db_3_names = {f.stem for f in db_3_files}
    n_queries_converted = 0
    n_jq_success = 0
    n_jq_failure = 0
    converted_records = []
    for f in db_3_files:
        with open(f, encoding="utf-8") as fp:
            data = json.load(fp)
        n_queries_converted += len(data)
        for d in data:
            jq_kind = d.get("converted", {}).get("jq", {}).get("kind")
            if jq_kind == "success":
                n_jq_success += 1
            else:
                n_jq_failure += 1
            converted_records.append(d)
    spider_data = load("jqSpider", path=paths.data).model_dump(mode="json")
    spider_benchmarks = spider_data["benchmarks"]
    n_final = len(spider_benchmarks)
    n_raw_queries_dropped = sum(1 for d in raw_queries if d["db_id"] not in db_3_names)
    print("=== Pipeline Funnel ===")
    print(
        f"Raw Spider queries (0_raw):         {n_raw_queries:>6,}  ({n_raw_dbs} databases)"
    )
    print(f"Databases extracted (1_databases):   {n_db_1:>6,}")
    print(f"Databases jsonified (2_jsonified):   {n_db_2:>6,}")
    print(f"Databases converted (3_converted):   {n_db_3:>6,}")
    print(
        f"  Queries reaching conversion:       {n_queries_converted:>6,}  (lost {n_raw_queries_dropped} from dropped DBs)"
    )
    print(
        f"  jq conversion success:             {n_jq_success:>6,}  ({n_jq_success / n_queries_converted * 100:.1f}%)"
    )
    print(
        f"  jq conversion failure:             {n_jq_failure:>6,}  ({n_jq_failure / n_queries_converted * 100:.1f}%)"
    )
    print(f"Final jqSpider (4_compiled):          {n_final:>6,}")
    funnel_labels = [
        "0_raw\nqueries",
        "1_databases",
        "2_jsonified",
        "3_converted\n(DBs)",
        "3_converted\n(queries)",
        "3_converted\n(jq success)",
        "4_compiled\n(jqSpider)",
    ]
    funnel_values = [
        n_raw_queries,
        n_db_1,
        n_db_2,
        n_db_3,
        n_queries_converted,
        n_jq_success,
        n_final,
    ]
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.bar(
        range(len(funnel_labels)),
        funnel_values,
        color=sns.color_palette("Set2", len(funnel_labels)),
    )
    ax.set_xticks(range(len(funnel_labels)))
    ax.set_xticklabels(funnel_labels, fontsize=12)
    ax.set_ylabel("Count")
    ax.set_title("Pipeline Funnel: Spider to jqSpider")
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
    plt.savefig(root_plots / "spider-pipeline-funnel.pdf", bbox_inches="tight")
    finish_figure(show)
    db_1_names = {f.stem for f in db_1_files}
    lost_1_to_2 = sorted(db_1_names - db_2_names)
    lost_2_to_3 = sorted(db_2_names - db_3_names)
    print(
        f"Databases lost 1_databases -> 2_jsonified ({len(lost_1_to_2)}): {lost_1_to_2}"
    )
    print(
        f"Databases lost 2_jsonified -> 3_converted ({len(lost_2_to_3)}): {lost_2_to_3}"
    )
    lost_dbs = set(raw_db_ids) - db_3_names
    lost_query_count = sum(1 for d in raw_queries if d["db_id"] in lost_dbs)
    print(
        f"\nRaw test DBs lost before conversion ({len(lost_dbs)}): {sorted(lost_dbs)}"
    )
    print(f"Queries lost from dropped DBs: {lost_query_count}")
    df_db_conv = _report_conversion(
        converted_records, db_3_files, root_plots, root_tables, show
    )
    _report_database_structure(
        db_3_files, df_db_conv, root, root_plots, root_tables, show
    )
    _report_translations(converted_records, root_plots, root_tables, show)
    _report_sql_features(raw_queries, root_plots, show)
    df_bench = _report_benchmarks(root_plots, show, spider_benchmarks)
    _report_conversion_features(converted_records, root_plots, root_tables, show)
    print("=" * 50)
    print("jqSpider Dataset Summary")
    print("=" * 50)
    print("Source: Spider text-to-SQL benchmark (test set)")
    print(f"Raw SQL queries:              {n_raw_queries:>6,}")
    print(f"Raw databases:                {n_raw_dbs:>6}")
    print(f"Databases successfully jsonified: {n_db_2:>4}")
    print(f"Databases with conversions:      {n_db_3:>4}")
    print(f"Queries reaching conversion:  {n_queries_converted:>6,}")
    print(
        f"jq conversion success:        {n_jq_success:>6,}  ({n_jq_success / n_queries_converted * 100:.1f}%)"
    )
    print(f"Final jqSpider benchmarks:      {n_final:>6,}")
    print()
    print(f"Unique databases in final:       {df_bench['database'].nunique():>4}")
    print(
        f"Expression length (median):   {df_bench['expr_length'].median():>6.0f} chars"
    )
    print(f"Pipe count (median):          {df_bench['n_pipe'].median():>6.0f}")
    print(
        f"Order-sensitive benchmarks:   {df_bench['order'].sum():>6}  ({df_bench['order'].mean() * 100:.1f}%)"
    )


def main(argv: list[str] | None = None) -> None:
    args = arguments(__doc__, argv)
    generate(args.output, show=args.show)


def _get_nesting(d):
    """Compute the nesting depth of a JSON value."""
    if isinstance(d, dict):
        return 1 + max((_get_nesting(v) for v in d.values()), default=0)
    elif isinstance(d, list):
        return 1 + max((_get_nesting(i) for i in d), default=0)
    else:
        return 0


if __name__ == "__main__":
    main()
