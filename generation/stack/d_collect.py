import glob
import json
import os
from collections import Counter

from pydantic import JsonValue
from tqdm import tqdm

from experiments.inference.benchmark import Benchmark, Dataset
from experiments.inference.settings import Settings
from generation.stack.c_convert import ConversionTest, ConvertedBenchmark

data_in_dir = Settings.data / "c_convert"
data_out = Settings.data / "d_collect" / "collected.json"


def collect(converted: ConvertedBenchmark) -> Benchmark | None:
    """Convert a ConvertedBenchmark into a Benchmark.

    Returns None if no valid execution can be found according to the criteria.
    """
    if not converted.executions:
        return None

    def _classify(execution):
        outcomes = [result.outcome for result in execution.results]
        success_count = outcomes.count("Success")
        partial_count = outcomes.count("Partial success")
        failure_count = outcomes.count("Failure")
        error_count = outcomes.count("Error")
        total = len(outcomes)

        return {
            "execution": execution,
            "success": success_count,
            "partial": partial_count,
            "failure": failure_count,
            "error": error_count,
            "total": total,
            "outcomes": outcomes,
        }

    categorized = [_classify(e) for e in converted.executions]

    # C1: All "Success" outcomes
    all_success = [c for c in categorized if c["success"] == c["total"]]
    if all_success:
        return _build_benchmark(
            converted,
            [c["execution"].expression for c in all_success],
            converted.environment.tests,
        )

    # C2: All "Partial success" outcomes
    all_partial = [c for c in categorized if c["partial"] == c["total"]]
    if all_partial:
        return _build_benchmark(
            converted,
            [c["execution"].expression for c in all_partial],
            converted.environment.tests,
        )

    # C3: Mix of "Partial success" and "Success"
    mixed_success_partial = [
        c
        for c in categorized
        if c["success"] + c["partial"] == c["total"]
        and c["success"] > 0
        and c["partial"] > 0
    ]
    if mixed_success_partial:
        return _build_benchmark(
            converted,
            [c["execution"].expression for c in mixed_success_partial],
            converted.environment.tests,
        )

    # C4: All successes except for a single Failure (if at least 5 tests)
    # All failures must be on the same test
    single_failure = [
        c
        for c in categorized
        if c["total"] >= 5
        and c["failure"] == 1
        and c["success"] + c["partial"] == c["total"] - 1
    ]
    if single_failure:
        # Collect which test failed for each execution
        failed_tests = [
            result.test
            for c in single_failure
            for result in c["execution"].results
            if result.outcome == "Failure"
        ]
        # Check if all failures are on the same test
        if len(set(failed_tests)) == 1:
            return _build_benchmark(
                converted,
                [c["execution"].expression for c in single_failure],
                [
                    test
                    for test in converted.environment.tests
                    if test.name != failed_tests[0]
                ],
            )

    # No valid execution found
    return None


def _collect_leaves(o: JsonValue) -> set:
    leaves = set()
    if isinstance(o, dict):
        for v in o.values():
            leaves.update(_collect_leaves(v))
    elif isinstance(o, list):
        for v in o:
            leaves.update(_collect_leaves(v))
    else:
        leaves.add(o)
    return leaves


def _collect_keys(o: JsonValue) -> set:
    keys = set()
    if isinstance(o, dict):
        for k, v in o.items():
            keys.add(k)
            keys.update(_collect_keys(v))
    elif isinstance(o, list):
        for v in o:
            keys.update(_collect_keys(v))
    return keys


def _is_subset(i: JsonValue, o: JsonValue) -> bool:
    """Check if output `o` is a subset of input `i`."""
    if isinstance(i, dict) and isinstance(o, dict):
        return all(k in i and _is_subset(i[k], v) for k, v in o.items())
    if isinstance(i, list) and isinstance(o, list):
        return all(any(_is_subset(ie, oe) for ie in i) for oe in o)
    return i == o


def _is_extract(i: JsonValue, o: JsonValue) -> bool:
    """Check if all leaf values in output `o` are present in input `i`."""
    leaves_i = _collect_leaves(i) - {None}
    leaves_o = _collect_leaves(o) - {None}
    return leaves_o.issubset(leaves_i)


def _is_transform(i: JsonValue, o: JsonValue) -> bool:
    """Check if `o` has exactly the same structure as `i` while allowing any leaf values to differ."""
    if isinstance(i, dict):
        if not isinstance(o, dict):
            return False
        if i.keys() != o.keys():
            return False
        return all(_is_transform(i[k], o[k]) for k in i.keys())
    if isinstance(i, list):
        if not isinstance(o, list):
            return False
        if len(i) != len(o):
            return False
        return all(_is_transform(iv, ov) for iv, ov in zip(i, o))
    return not isinstance(o, (dict, list))


def _is_keys(i: JsonValue, o: JsonValue) -> bool:
    """Check if `o` only contains keys from `i` as values."""
    leaves = _collect_leaves(o) - {None}
    keys = _collect_keys(i)
    if all(isinstance(leaf, str) and leaf in keys for leaf in leaves):
        return True
    return False


def get_task(tests: list[ConversionTest]) -> str:
    inputs = [test.input for test in tests]
    outputs = [test.output for test in tests]
    if all(len(o) == 1 for o in outputs):
        outputs = [o[0] for o in outputs]
    if len(inputs) != len(outputs):
        return "n/a"
    if all(_is_subset(i, o) for i, o in zip(inputs, outputs)):
        return "subset"
    if all(_is_subset(o, i) for i, o in zip(inputs, outputs)):
        return "superset"
    if all(_is_extract(i, o) for i, o in zip(inputs, outputs)):
        return "extract"
    if all(_is_extract(o, i) for i, o in zip(inputs, outputs)):
        return "augment"
    if all(_is_transform(i, o) for i, o in zip(inputs, outputs)):
        return "transform"
    if all(_is_keys(i, o) for i, o in zip(inputs, outputs)):
        return "keys"
    return "other"


def _build_benchmark(
    converted: ConvertedBenchmark, expressions: list[str], tests: list[ConversionTest]
) -> Benchmark:
    """Build a Benchmark from the converted data and selected expressions/tests."""
    return Benchmark(
        identifier=converted.identifier,
        utterance=converted.utterance or "",
        expressions=expressions,
        inputs=[test.input for test in tests],
        tasks=[get_task(tests)],
    )


if __name__ == "__main__":
    data_out.parent.mkdir(parents=True, exist_ok=True)

    # load all converted-{model}.json files (excluding failures)
    converted_files = sorted(glob.glob(str(data_in_dir / "converted-*.json")))
    converted_files = [
        f for f in converted_files if "-failures" not in os.path.basename(f)
    ]

    by_model = dict()
    all_data = list()
    for filepath in converted_files:
        model_name = (
            os.path.basename(filepath).replace("converted-", "").replace(".json", "")
        )
        items = json.load(open(filepath, "r", encoding="utf-8"))
        items = [
            ConvertedBenchmark.model_validate(d)
            for d in tqdm(items, desc=f"  Parsing {os.path.basename(filepath)}")
        ]
        by_model[model_name] = items
        all_data.extend(items)
        print(f"⚡  Loaded {len(items)} items from {os.path.basename(filepath)}.")

    # group by identifier
    by_identifier = dict()
    for converted in all_data:
        by_identifier.setdefault(converted.identifier, list()).append(converted)
    print(f"⚡  Found {len(by_identifier)} unique identifiers.")

    collected = list()
    n_tests = Counter()
    skipped = 0
    failed_ids = set()

    for identifier, versions in tqdm(sorted(by_identifier.items()), desc="Collecting"):
        success = False
        for converted in versions:
            result = collect(converted)
            if result is not None:
                n_tests[len(result.inputs)] += 1
                if 4 <= len(result.inputs) <= 6:
                    collected.append(result)
                    success = True
                    break
        if not success:
            skipped += 1
            failed_ids.add(identifier)

    print(f"✅  Successfully collected {len(collected)} benchmarks.")
    print(f"⏭️   Skipped {skipped} items (no valid execution found).")

    # write collected
    dataset = Dataset(name="jqStack", benchmarks=collected)
    with open(data_out, "w", encoding="utf-8") as f:
        f.write(dataset.model_dump_json(indent=2))
    print(f"✅  Wrote {len(collected)} benchmarks to {data_out}.")

    # write per-model failures
    for model_name, items in by_model.items():
        failures = [cb for cb in items if cb.identifier in failed_ids]
        failures_path = data_in_dir / f"converted-{model_name}-failures.json"
        with open(failures_path, "w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    [b.model_dump(mode="json") for b in failures],
                    indent=2,
                )
            )
        print(f"⏭️   Wrote {len(failures)} failures to {failures_path}.")

    print("📊  Statistics:")
    for n, count in sorted(n_tests.items()):
        print(f"  - {n} tests: {count} benchmarks")
