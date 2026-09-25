import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from jsonargparse import ArgumentParser
from tqdm import tqdm

from experiments.paths import paths
from generation.spider.spider_utilities import Column, Database, Table


def list_tables(con: sqlite3.Connection) -> list[str]:
    cur = con.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
    )
    return [r[0] for r in cur.fetchall()]


def get_table(con: sqlite3.Connection, table: str) -> Table:
    cur = con.cursor()

    # Columns (schema)
    # (cid, name, type, notnull, dflt_value, pk)
    cur.execute(f"PRAGMA table_info({table})")
    cols = cur.fetchall()
    columns = [Column(name=c[1], type=c[2] if c[2] is not None else "") for c in cols]

    # Foreign keys (if composite, each local column appears separately)
    # (id, seq, ref_table, from, to, on_update, on_delete, match)
    cur.execute(f"PRAGMA foreign_key_list({table})")
    fk_rows = cur.fetchall()
    foreign_keys: dict[str, str] = {}
    for _, _, ref_table, from_col, to_col, _, _, _ in fk_rows:
        foreign_keys[from_col] = f"{ref_table}.{to_col}"

    # Data (rows)
    rows_spec: list[dict] = []
    cur.execute(f"SELECT * FROM {table}")
    data_rows = cur.fetchall()
    col_names = [d[0] for d in cur.description]
    for r in data_rows:
        one: dict = {}
        for name, val in zip(col_names, r):
            if isinstance(val, bytes):
                try:
                    one[name] = val.decode("utf-8")
                except Exception:
                    one[name] = val.hex()
            else:
                one[name] = val
        rows_spec.append(one)

    return Table(name=table, columns=columns, foreignKeys=foreign_keys, rows=rows_spec)


def parse(file: Path, output: Path) -> dict[str, int]:
    if output.exists():
        return {"skipped": 1}
    connection = sqlite3.connect(str(file))
    connection.text_factory = lambda b: b.decode(errors="ignore")
    database = Database()
    with connection:
        tables = list_tables(connection)
        for table_name in tables:
            table = get_table(connection, table_name)
            database.root[table_name] = table
    with output.open("w", encoding="utf-8") as f:
        f.write(database.model_dump_json(indent=2))
    return {
        "tables": len(database.root),
        "rows": sum(len(t.rows) for t in database.root.values()),
    }


if __name__ == "__main__":
    # fmt: off
    parser = ArgumentParser(description="Export SQLite tables (schema + data) to JSON.")
    parser.add_argument("-d", "--database", type=Path, default=None)
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument("--force", action="store_true", help="Overwrite existing JSON files")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    # fmt: on
    args = parser.parse_args()

    # defaults
    if args.database == Path("all"):
        args.database = paths.spider / "0_raw" / "test_database"
    args.database = args.database or (
        paths.spider / "0_raw" / "test_database" / "aan_1" / "aan_1.sqlite"
    )
    args.output = paths.spider / "1_databases"

    # ensure output directory
    if args.database.is_dir():
        databases = list(args.database.rglob("*.sqlite"))
    else:
        databases = [args.database]

    # parse
    progress = tqdm(total=len(databases), disable=args.quiet)
    statistics = defaultdict(int)
    for database in databases:
        if not database.exists():
            print(f"Database file not found: {database}", file=sys.stderr)
            statistics["errors"] += 1
            progress.update(1)
            continue
        statistic = parse(database, args.output / f"{database.stem}.json")
        for k, v in statistic.items():
            statistics[k] += v
        progress.update(1)
        progress.set_postfix(statistics)
