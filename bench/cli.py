"""The command line: `uv run bench <subcommand> [tier]`.

`generate` writes the case files that are generated from a seed and the sidecar
of every case that has none; `convert`, `run`, `check`, `summarize` and `plot`
each take a tier name and act on the runs that tier asks for.
"""

import argparse
from pathlib import Path

from bench import cases, generators, manifest

DEFAULT_MANIFEST = Path("cases/manifest.toml")
TIER_SUBCOMMANDS = ("convert", "run", "check", "summarize", "plot")


def main():
    parser = argparse.ArgumentParser(prog="bench")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    generate.add_argument("--only")
    generate.add_argument("--force", action="store_true")
    for name in TIER_SUBCOMMANDS:
        subparser = subparsers.add_parser(name)
        subparser.add_argument("tier")
        subparser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    arguments = parser.parse_args()
    loaded = manifest.load(arguments.manifest)
    if arguments.subcommand == "generate":
        run_generators(loaded, arguments.only, arguments.force)
        write_missing_sidecars(loaded)
    else:
        print_runs(loaded, arguments.tier)


def run_generators(loaded, only, force):
    for entry in loaded.cases.values():
        if entry.generator is None or (only is not None and entry.name != only):
            continue
        written = entry.path.exists() and cases.sidecar_path(entry.path).exists()
        if written and not force:
            continue
        entry.path.parent.mkdir(parents=True, exist_ok=True)
        generators.GENERATORS[entry.generator](
            entry.name, entry.seed, entry.parameters, entry.path.parent
        )
        print(f"{entry.name} {entry.path}")


def write_missing_sidecars(loaded):
    for entry in loaded.cases.values():
        if entry.generator is not None:
            continue
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
