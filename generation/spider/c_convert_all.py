"""Run Spider conversion sequentially for the available JSON database files."""

import subprocess

from experiments.paths import ROOT, paths


def main():
    for database in sorted((paths.spider / "2_jsonified").glob("*.json")):
        subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "generation.spider.c_convert",
                "--dataset",
                database.stem,
                "--cache",
                "auto",
                "-v",
            ],
            cwd=ROOT,
            check=True,
        )


if __name__ == "__main__":
    main()
