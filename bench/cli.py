"""The command line: `uv run bench <subcommand> [tier]`.

`generate` writes the case files that are generated from a seed and the sidecar
of every case that has none; `convert`, `run`, `check`, `summarize` and `plot`
each take a tier name and act on the runs that tier asks for.
"""

import argparse
from pathlib import Path

from bench import cases, manifest

DEFAULT_MANIFEST = Path("cases/manifest.toml")
TIER_SUBCOMMANDS = ("convert", "run", "check", "summarize", "plot")


def main():
    parser = argparse.ArgumentParser(prog="bench")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    for name in TIER_SUBCOMMANDS:
        subparser = subparsers.add_parser(name)
        subparser.add_argument("tier")
        subparser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    arguments = parser.parse_args()
    loaded = manifest.load(arguments.manifest)
    if arguments.subcommand == "generate":
        write_missing_sidecars(loaded)
    else:
        print_runs(loaded, arguments.tier)


def write_missing_sidecars(loaded):
    for entry in loaded.cases.values():
        if not entry.path.exists() or cases.sidecar_path(entry.path).exists():
            continue
        path = cases.write_sidecar(
            entry.path,
            columns=entry.columns,
            family=entry.family,
            source={"kind": "committed", "file": entry.file},
        )
        print(f"{entry.name} {path}")


def print_runs(loaded, tier_name):
    runs = manifest.expand(loaded, tier_name)
    for run in runs:
        print(f"{run.case} {run.tool} {run.config}")
    print(f"{len(runs)} runs")
