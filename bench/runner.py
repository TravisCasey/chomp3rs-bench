"""The run loop: one container per measured run, one record per run.

`run_tier` expands a tier into its runs, checks whether each tool's adapter can
run the case and records a skip where it cannot, converts each case once per
tool, and measures the rest.
"""

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from bench import cases, machine, records
from bench.adapters import ADAPTERS, CASES_MOUNT, OUTPUT_MOUNT
from bench.manifest import expand
from bench.wrapper import run_measured

SCRATCH_DIRECTORY = Path("results/scratch")
WORKING_DIRECTORY = "/work"


@dataclass
class Planned:
    """One run of the tier with everything the loop needs to do it.

    `adapter` is `None` for a tool that has no adapter yet: such a run is
    listed and then left alone, and it disappears from the list as the adapter
    lands.
    """

    run: records.RecordedRun
    adapter: object | None
    case: cases.Case
    config: dict
    skip_reason: str | None


def run_tier(manifest, tier_name, *, only_tool=None, only_case=None, dry_run=False):
    tier = manifest.tiers[tier_name]
    planned = plan(manifest, tier_name, only_tool, only_case, memory_cap(tier))
    if dry_run:
        report_plan(planned, tier)
        return
    described = machine.describe()
    for entry in planned:
        if entry.adapter is None or entry.skip_reason is None:
            continue
        if not records.exists(entry.run, 0):
            records.write_skipped(
                entry.run,
                entry.skip_reason,
                entry.adapter.version(),
                entry.config,
                described,
            )
        print(f"{label(entry, 0)} skipped {entry.skip_reason}")
    doable = runnable(planned)
    converted = {}
    for entry in doable:
        key = (entry.run.case, entry.run.tool)
        if key not in converted:
            converted[key] = entry.adapter.convert(entry.case)
    for repetition in range(tier.repetitions):
        for entry in doable:
            if records.exists(entry.run, repetition):
                print(f"{label(entry, repetition)} exists")
                continue
            measure(
                entry,
                repetition,
                converted[(entry.run.case, entry.run.tool)],
                manifest.root,
                tier,
                described,
            )


def memory_cap(tier):
    return tier.memory_limit_gigabytes * 1024**3


def runnable(planned):
    return [
        entry
        for entry in planned
        if entry.adapter is not None and entry.skip_reason is None
    ]


def plan(manifest, tier_name, only_tool, only_case, memory_limit_bytes):
    planned = []
    for run in expand(manifest, tier_name):
        if only_tool is not None and run.tool != only_tool:
            continue
        if only_case is not None and run.case != only_case:
            continue
        case = cases.load_case(run.case, manifest)
        adapter = ADAPTERS.get(run.tool)
        config = configuration(manifest, run, adapter)
        planned.append(
            Planned(
                run=records.RecordedRun(
                    case=run.case,
                    tool=run.tool,
                    config=run.config,
                    tier=run.tier,
                    family=case.family,
                ),
                adapter=adapter,
                case=case,
                config=config,
                skip_reason=(
                    None
                    if adapter is None
                    else adapter.skip_reason(case, config, memory_limit_bytes)
                ),
            )
        )
    return planned


def configuration(manifest, run, adapter):
    """The configuration of a run: the name it goes by, the coefficient field the
    tool answers over, and the flags it sets."""
    named = manifest.configs.get(run.config, {"threads": 1})
    coefficients = None if adapter is None else adapter.COEFFICIENTS
    return {"name": run.config, "coefficients": coefficients, **named}


def measure(entry, repetition, converted, cases_directory, tier, described):
    adapter = entry.adapter
    SCRATCH_DIRECTORY.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(dir=SCRATCH_DIRECTORY))
    measurement = run_measured(
        adapter.command(entry.case, entry.config, converted),
        timeout_seconds=tier.timeout_seconds,
        memory_limit_bytes=memory_cap(tier),
        threads=entry.config["threads"],
        mounts=[
            (cases_directory, CASES_MOUNT, "ro"),
            (scratch, OUTPUT_MOUNT, "rw"),
        ],
        workdir=WORKING_DIRECTORY,
    )
    answer = None
    stages = None
    if measurement.status == "finished":
        parsed = adapter.parse(
            measurement.stdout, measurement.stderr, sorted(scratch.iterdir())
        )
        stages = parsed.pop("stages", None)
        answer = parsed
    records.write(
        entry.run,
        repetition,
        measurement,
        answer,
        stages,
        adapter.version(),
        entry.config,
        described,
    )
    shutil.rmtree(scratch)
    print(
        f"{label(entry, repetition)} {measurement.status}"
        f" {number(measurement.wall_seconds)} {number(measurement.peak_rss_kilobytes)}"
    )


def report_plan(planned, tier):
    for entry in planned:
        print(f"{entry.run.case} {entry.run.tool} {entry.run.config} {standing(entry)}")
    doable = runnable(planned)
    bound = len(doable) * tier.timeout_seconds * tier.repetitions
    print(
        f"{len(doable)} runs of {len(planned)}, {tier.repetitions} repetitions,"
        f" worst case {bound} seconds ({bound / 60:.1f} minutes)"
    )


def standing(entry):
    """What the loop would do with this run: run it, skip it, or pass it by."""
    if entry.adapter is None:
        return "no adapter"
    return entry.skip_reason or "run"


def convert_tier(manifest, tier_name, *, only_tool=None):
    tier = manifest.tiers[tier_name]
    for name in tier.cases:
        case = cases.load_case(name, manifest)
        for tool, adapter in ADAPTERS.items():
            if only_tool is not None and tool != only_tool:
                continue
            print(f"{name} {tool} {adapter.convert(case)}")


def label(entry, repetition):
    return f"{entry.run.case} {entry.run.tool} {entry.run.config} r{repetition}"


def number(value):
    if value is None:
        return "-"
    return f"{value:.3f}" if isinstance(value, float) else str(value)
