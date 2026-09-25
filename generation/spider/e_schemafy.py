import json
from copy import deepcopy

from tqdm import tqdm

from experiments.inference.benchmark import Dataset
from experiments.paths import paths
from jqbench.execution import JqExecutionEngine


def anonymize(o: dict) -> dict:
    o = deepcopy(o)
    if isinstance(o, list):
        if len(o) == 0:
            return o
        return [anonymize(o[0])]
    if isinstance(o, dict):
        # return {f"key{i+1}": anonymize(v) for i, v in enumerate(o.values())}
        a = {("value", anonymize(v)) for v in o.values()}
        return {f"key{i + 1}": v for i, (_, v) in enumerate(sorted(a))}
    return "value"


if __name__ == "__main__":
    root = paths.spider

    data_json = root / "2_jsonified"
    data_compiled = root / "4_compiled" / "spider.json"
    data_out = root / "5_schemafied" / "spider.json"
    data_out.parent.mkdir(parents=True, exist_ok=True)

    dataset = Dataset.model_validate_json(data_compiled.read_text(encoding="utf-8"))
    data = None
    data_name = None
    unique = set()
    for benchmark in tqdm(dataset.benchmarks):
        if data_name != benchmark.inputfile.stem:
            data_name = benchmark.inputfile.stem
            data_path = data_json / f"{data_name}.json"
            data = json.loads(data_path.read_text(encoding="utf-8"))
        expression = benchmark.expressions[0]
        try:
            output = JqExecutionEngine.execute(expression, data["data"])
        except Exception:
            continue
        benchmark.jsonoutput = anonymize(output)
        unique.add(json.dumps(benchmark.jsonoutput))

    print("Schemas.")
    for s in unique:
        print(s)

    with open(data_out, "w", encoding="utf-8") as f:
        f.write(dataset.model_dump_json(indent=2))
