"""The command line: `uv run bench <subcommand> [tier]`.

`generate` writes the case files that are generated from a seed and the sidecar
of every case that has none; `convert`, `run`, `check`, `summarize` and `plot`
each take a tier name and act on the runs that tier asks for. `convert` and
`run` narrow to one tool with `--tool`, `run` narrows to one case with `--case`,
and `--dry-run` prints what `run` would do and what it would cost at worst
without running anything. `check` and `summarize` read the records under
`--runs-directory`, `results/runs` by default, and `check` exits 1 when it finds
a record it disputes. `plot` reads the tables `summarize` wrote and draws the
figures under `figures/<tier>/`.
"""

import argparse
from pathlib import Path

from bench import cases, check, generators, manifest, plot, records, runner, summarize

DEFAULT_MANIFEST = Path("cases/manifest.toml")
TIER_SUBCOMMANDS = ("convert", "run", "check", "summarize", "plot")


def main():
    parser = argparse.ArgumentParser(prog="bench")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    generate.add_argument("--only")
    generate.add_argument("--force", action="store_true")
    tier_parsers = {}
    for name in TIER_SUBCOMMANDS:
        subparser = subparsers.add_parser(name)
        subparser.add_argument("tier")
        subparser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
        tier_parsers[name] = subparser
    tier_parsers["convert"].add_argument("--tool")
    tier_parsers["run"].add_argument("--tool")
    tier_parsers["run"].add_argument("--case")
    tier_parsers["run"].add_argument("--dry-run", action="store_true")
    tier_parsers["check"].add_argument(
        "--runs-directory", type=Path, default=records.RUNS_DIRECTORY
    )
    tier_parsers["summarize"].add_argument(
        "--runs-directory", type=Path, default=records.RUNS_DIRECTORY
    )
    arguments = parser.parse_args()
    loaded = manifest.load(arguments.manifest)
    if arguments.subcommand == "generate":
        run_generators(loaded, arguments.only, arguments.force)
        write_missing_sidecars(loaded)
    elif arguments.subcommand == "convert":
        runner.convert_tier(loaded, arguments.tier, only_tool=arguments.tool)
    elif arguments.subcommand == "run":
        runner.run_tier(
            loaded,
            arguments.tier,
            only_tool=arguments.tool,
            only_case=arguments.case,
            dry_run=arguments.dry_run,
        )
    elif arguments.subcommand == "check":
        report = check.check_tier(loaded, arguments.tier, arguments.runs_directory)
        check.print_report(report)
        if report.disputed:
            raise SystemExit(1)
    elif arguments.subcommand == "summarize":
        summarize.summarize_tier(loaded, arguments.tier, arguments.runs_directory)
    else:
        plot.plot_tier(loaded, arguments.tier)


def run_generators(loaded, only, force):
    """Run the generators, the cases that grade another case last so that the
    case one of them names as its `base` has been written by the time it runs."""
    ordered = sorted(
        loaded.cases.values(), key=lambda entry: "base" in entry.parameters
    )
    for entry in ordered:
        if entry.generator is None or (only is not None and entry.name != only):
            continue
        written = entry.path.exists() and cases.sidecar_path(entry.path).exists()
        if written and not force:
            continue
        entry.path.parent.mkdir(parents=True, exist_ok=True)
        generators.GENERATORS[entry.generator](
            entry.name,
            entry.seed,
            resolved_parameters(loaded, entry),
            entry.path.parent,
        )
        print(f"{entry.name} {entry.path}")


def resolved_parameters(loaded, entry):
    """The case's parameters, with the file and the layout of the case its
    `base` names added where it has one."""
    if "base" not in entry.parameters:
        return entry.parameters
    base = loaded.cases[entry.parameters["base"]]
    return {
        **entry.parameters,
        "base_path": base.path,
        "base_columns": base.columns,
    }


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
