import json
import re
from pathlib import Path

import jsonschema
from jsonargparse import ArgumentParser
from rich.console import Console
from tqdm import tqdm

from experiments.llm import (
    ChatModel,
    JsonCache,
    Message,
    Role,
)
from experiments.paths import paths
from generation.spider.spider_utilities import Database
from jqbench.execution import PythonExecutionEngine

SYSTEM_SCHEMA = """
You are an expert at SQL and JSON.
You are given a database schema (tables with columns and foreign keys).
You suggest a JSON schema to represent the dataset in a single JSON file.

**Notes**
- Choose a root table that connects to all other tables through foreign keys.
- Leverage nested objects and arrays of objects to represent one-to-one and one-to-many relationships.
- If a column has empty values, make sure it is optional in the JSON schema.

**Output format**
You return a JSON schema as a JSON object, wrapped in a ```json ``` block.
""".strip()


SYSTEM_CONVERT = """
You are an expert at converting data between JSON formats.
You are given (1) a partial JSON object and (2) a target JSON schema.
You write a Python function that converts the partial JSON object to conform to the target schema.

**Output format**
You return a Python `convert(o: dict) -> dict` function, wrapped in a ```python ``` block.
""".strip()


def get_subset(obj: dict, n: int = 10) -> dict:
    if isinstance(obj, dict):
        return {k: get_subset(v, n) for k, v in obj.items()}
    if isinstance(obj, list):
        return obj[:n]
    return obj


def get_schema(database: Database, model: ChatModel, console: Console = None) -> dict:
    schema = dict()
    for table in database.root.values():
        empty = {c.name: False for c in table.columns}
        for row in table.rows:
            for c in table.columns:
                if row[c.name] is None:
                    empty[c.name] = True
        schema[table.name] = {
            "columns": {
                c.name: {
                    "type": c.type,
                    "n_rows": len(table.rows),
                    "has_empty": empty[c.name],
                }
                for c in table.columns
            },
            "foreignKeys": table.foreignKeys,
        }
    prompt = [
        Message(role=Role.System, content=SYSTEM_SCHEMA),
        Message(role=Role.User, content=json.dumps(schema, indent=2)),
    ]
    if console:
        console.rule("[bold]📊 SCHEMA")
        console.print(json.dumps(schema, indent=2), style="dim")
    for _ in range(4):
        result = model.chat(prompt)
        result_schema = re.search(r"```json\n(.*?)```", result.text, re.DOTALL)
        if not result_schema:
            prompt.append(
                Message(
                    role=Role.User,
                    content="The output does not contain a ```json ``` block. Please try again.",
                )
            )
            continue
        # try to load
        try:
            schema_json = json.loads(result_schema.group(1))
        except json.JSONDecodeError:
            prompt.append(
                Message(
                    role=Role.User,
                    content="The JSON schema is not valid JSON. Please try again.",
                )
            )
            continue
        # try to validate
        try:
            jsonschema.Draft202012Validator.check_schema(schema_json)
        except jsonschema.exceptions.SchemaError as e:
            prompt.append(
                Message(
                    role=Role.User,
                    content=f"The JSON schema is not a valid JSON Schema: {e.message}. Please try again.",
                )
            )
            continue
        return schema_json
    return None


def get_converter(
    database: Database,
    schema: dict,
    model: ChatModel,
    n: int = 10,
    console: Console = None,
) -> dict:
    partial = {table.name: table.rows[:n] for table in database.root.values()}
    whole = {table.name: table.rows for table in database.root.values()}
    user = f"""
Here is the target JSON schema:
```json
{json.dumps(schema, indent=2)}
```

Here are the first {n} rows of each table in the database, represented as a JSON object that maps table names to arrays of rows.
```json
{json.dumps(partial, indent=2)}
```
    """.strip()
    prompt = [
        Message(role=Role.System, content=SYSTEM_CONVERT),
        Message(role=Role.User, content=user),
    ]
    for _ in range(4):
        if console:
            console.rule("[bold]🤖 CONVERSION[/bold]")
        result = model.chat(prompt)
        result_function = re.search(r"```python\n(.*?)```", result.text, re.DOTALL)
        if not result_function:
            if console:
                console.print("[red]No ```python ``` block found.[/red]")
            prompt.append(
                Message(
                    role=Role.User,
                    content="The output does not contain a ```python ``` block. Please try again.",
                )
            )
            continue
        result_function = result_function.group(1)
        if console:
            console.print(result_function, style="dim")
        # try to compile
        if console:
            console.rule("[bold]🛠️ COMPILATION[/bold]")
        try:
            compiled = PythonExecutionEngine.compile(result_function)
        except Exception as e:
            if console:
                console.print(f"[red]Compilation error: {e}[/red]")
            prompt.append(
                Message(
                    role=Role.User,
                    content=f"The Python code does not compile: {e}. Please try again.",
                )
            )
            continue
        if console:
            console.print("✅ Compiled successfully.")
            console.rule("[bold]⚙️ EXECUTION[/bold]")
        try:
            output = PythonExecutionEngine.execute_compiled(compiled, whole)
        except Exception as e:
            if console:
                console.print(f"[red]Execution error: {e}[/red]")
            prompt.append(
                Message(
                    role=Role.User,
                    content=f"The Python code does not run on the full data: {e}. Please try again.",
                )
            )
            continue
        if len(output) == 0:
            if console:
                console.print("[red]The output is empty.[/red]")
            prompt.append(
                Message(
                    role=Role.User,
                    content="The output is empty. Please try again.",
                )
            )
            continue
        if console:
            console.print(json.dumps(get_subset(output, 2), indent=2), style="dim")
            console.rule("[bold]✅ VALIDATION[/bold]")
        try:
            jsonschema.Draft202012Validator(schema).validate(output)
        except jsonschema.ValidationError as e:
            if console:
                console.print(f"[red]Validation error: {e.message}[/red]")
            prompt.append(
                Message(
                    role=Role.User,
                    content=f"The output does not conform to the target JSON schema: {e.message}. Please try again.",
                )
            )
            continue
        if console:
            console.print("✅ Validated successfully.")
        return output
    return None


def jsonify(database: Database, model: ChatModel, verbose: bool) -> dict:
    console = Console() if verbose else None
    schema = get_schema(database, model, console=console)
    if not schema:
        return None
    convert = get_converter(database, schema, model, console=console)
    if not convert:
        return None
    return {
        "schema": schema,
        "data": convert,
    }


if __name__ == "__main__":
    root_spider = paths.spider

    # fmt: off
    parser = ArgumentParser()
    parser.add_argument("-d", "--database", type=Path, default=None)
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument("-m", "--model", type=str, default="openai/gpt-4.1")
    parser.add_argument("-c", "--cache", type=str, default="auto")
    parser.add_argument("--force", action="store_true", help="Overwrite existing JSON files")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    args = parser.parse_args()
    # fmt: on

    # defaults
    if args.database == Path("all"):
        args.database = root_spider / "1_databases"
    args.database = args.database or (root_spider / "1_databases")
    args.output = args.output or (root_spider / "2_jsonified")
    args.output.mkdir(parents=True, exist_ok=True)

    # load
    if args.database.is_dir():
        databases = list(args.database.glob("*.json"))
    else:
        databases = [args.database]

    # load model
    if args.cache == "auto":
        args.cache = (
            paths.reports.parent / "runs" / "caches"
        ) / f"jsonify-{args.model.replace('/', '--')}.json"
    model_spec = args.model
    model_cache = JsonCache(args.cache) if args.cache else None
    model = ChatModel(model=model_spec, cache=model_cache)

    progress = tqdm(total=len(databases), disable=args.verbose)
    statistics = {"success": 0, "failed": 0}
    for database_file in databases:
        output_file = args.output / f"{database_file.stem}.json"
        if output_file.exists() and not args.force:
            progress.update(1)
            continue
        database = Database.model_validate_json(
            database_file.read_text(encoding="utf-8")
        )
        jsonified = jsonify(database, model, verbose=args.verbose)
        if not jsonified:
            print(f"Failed to jsonify {database_file}.")
            statistics["failed"] += 1
            continue
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(jsonified, indent=2))
        statistics["success"] += 1
        progress.update(1)
        progress.set_postfix(statistics)
