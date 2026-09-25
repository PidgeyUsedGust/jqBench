import json
from pathlib import Path

from jsonargparse import ArgumentParser
from tqdm import tqdm

from experiments.paths import paths
from jqbench import Benchmark, Dataset, EvaluationSettings

if __name__ == "__main__":
    root = paths.spider

    data_tests = root / "0_raw" / "test.json"
    databases_sql = root / "0_raw" / "test_database"
    databases_json = root / "2_jsonified"
    database_names = [db.stem for db in databases_json.glob("*.json")]

    # fmt: off
    parser = ArgumentParser()
    parser.add_argument("-d", "--dataset", type=str, choices=database_names, default=None)
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    # fmt: on

    args.dataset = args.dataset or database_names
    if isinstance(args.dataset, str):
        args.dataset = [args.dataset]
    args.output = args.output or root / "4_compiled" / "spider.json"
    args.output.parent.mkdir(parents=True, exist_ok=True)

    benchmarks = list()
    progress = tqdm(total=len(args.dataset))
    for dataset_name in args.dataset:
        dataset_jsonified = root / "2_jsonified" / f"{dataset_name}.json"
        dataset_converted = root / "3_converted" / f"{dataset_name}.json"
        if not dataset_converted.exists():
            progress.update(1)
            continue
        dataset = json.loads(dataset_converted.read_text())
        dataset_schema = json.loads(dataset_jsonified.read_text())["schema"]
        for item in dataset:
            item_jq = item["converted"]["jq"]
            if (item_jq["kind"] == "success") and item.get(
                "query_output", None
            ) is not None:
                benchmarks.append(
                    Benchmark(
                        identifier=f"{item['db_id']}.{len(benchmarks)}",
                        utterance=item["question"],
                        expressions=item_jq["jq"],
                        inputfile=Path(dataset_jsonified.relative_to(root).as_posix()),
                        tasks=["spider"],
                        jsonschema=dataset_schema,
                        settings=EvaluationSettings(
                            keys=False,
                            order=(
                                ("ORDER BY" in item["query"])
                                and isinstance(item["query_output"], list)
                            ),
                        ),
                    )
                )
        progress.update(1)
        progress.set_postfix(benchmarks=len(benchmarks))

    dataset = Dataset(name="spider", benchmarks=benchmarks)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(dataset.model_dump_json(indent=2))
