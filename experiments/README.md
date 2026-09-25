# Experiments

Run new experiments or report saved results.
For methodology and dataset generation, see the [paper](https://openreview.net/forum?id=VStKtgGXUc).
For package usage, see the [jqBench README](../README.md).

## Setup

Run all commands below from the checkout's `code` directory:

```powershell
uv sync
```

Paths come from [config.yaml](../config.yaml), or `JQBENCH_CONFIG`; relative paths resolve against that file.
Follow the [artifact instructions](../../artifacts/README.md) to extract archives for historical reports.
Public datasets are in `..\data`.

## Fresh runs

Choose a YAML file from [configurations](configurations).
Omitting the path selects all configurations; `--dry-run` makes no model calls and needs no artifacts.

```powershell
uv run python -m experiments.run --dry-run
uv run python -m experiments.run <configuration.yaml> --output-root ..\artifacts\runs\fresh
```

Set `OPENROUTER_API_KEY` for live requests: **cache misses can incur charges**.
Fully cached runs need no credentials or network.
`model.name` is the historical label; `model.id` is the OpenRouter endpoint.
If `model.id` is null, supply `--model <provider/model>` or edit it in the YAML.
Replacement-model runs are new experiments, not guaranteed reproductions of paper results.

Use fresh output roots separate from supplied data, results, and caches; existing result targets are rejected.
Responses use writable caches under the output root, not the archived cache format.
Concurrent processes need separate roots.

## Saved reports

These commands read historical results without model calls:

```powershell
uv run python -m experiments.reports.results
uv run python -m experiments.reports.stack
uv run python -m experiments.reports.spider
uv run python -m experiments.reports.datasets
uv run python -m experiments.reports.tools
```

`results` produces paper tables and result plots; `stack` and `spider` produce construction plots; `datasets` and `tools` summarize datasets and tool use.
Use `--output <directory>` to change the report destination and `--show` to display plots.
Add `--all-runs` to `reports.results` to include supplemental runs.

For a specific result file, including fresh outputs, use the separate inference report below.
Its run means differ from paper aggregation; see the [artifact README](../../artifacts/README.md) for coverage and reproduction limitations.

```powershell
uv run python -m experiments.reports.inference --results <result.json>
```

## Replay

Replay explicitly executes a saved prediction and reference for one case:

```powershell
uv run python -m experiments.replay --results <result.json> --case <identifier> --execute
```

Use `--input-root <directory>` for inputs relative to a generation-stage root.
The tools report also runs references only with `--execute`.
Stored programs are executable code, **not sandboxed**; only execute trusted programs.
