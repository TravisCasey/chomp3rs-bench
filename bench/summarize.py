"""The summary tables: one row per case, tool and configuration.

Reads the records of a tier and writes `results/summary/<tier>/runs.csv`, one
row per group of repetitions with the case's shape, what the run cost and the
answer it gave, and `results/summary/<tier>/stages.csv`, one row per stage of
each chomp3rs run. A repetition the tier killed still counts towards the row:
one killed for taking too long counts the tier's timeout as its wall time, one
killed for taking too much memory counts the tier's cap as its peak, so a
measurement stopped at a limit reads as that limit rather than as the number
the kill happened to leave behind.

Invoked as `bench summarize <tier> [--runs-directory PATH]`; see `bench.cli`.
"""

import csv
import json
import statistics
from pathlib import Path

from bench import cases, manifest, records

SUMMARY_DIRECTORY = Path("results/summary")

SKIPPED = "skipped"
FINISHED = "finished"
DISPUTED = "disputed"
TIMEOUT = "timeout"
OUT_OF_MEMORY = "out_of_memory"
ERROR = "error"

COMPARABLE = (FINISHED, DISPUTED)
STATUS_ORDER = (SKIPPED, FINISHED, DISPUTED, TIMEOUT, OUT_OF_MEMORY, ERROR)

RUN_COLUMNS = (
    "case",
    "family",
    "ambient_dimension",
    "cube_count",
    "bounding_box_volume",
    "graded",
    "grade_count",
    "tool",
    "tool_version",
    "config",
    "threads",
    "modulus",
    "status",
    "repetitions",
    "statuses",
    "wall_median",
    "wall_min",
    "wall_max",
    "user_median",
    "system_median",
    "peak_rss_median_kb",
    "peak_rss_max_kb",
    "answer",
    "image_id",
    "repository_commit",
    "skip_reason",
)

STAGE_COLUMNS = ("case", "config", "stage", "seconds_median", "cells_in", "cells_out")


def summarize_tier(loaded, tier_name, runs_directory=records.RUNS_DIRECTORY):
    tier = loaded.tiers[tier_name]
    grouped = group_by_run(tier_name, runs_directory)
    run_rows = []
    stage_rows = []
    for key in ordered_keys(loaded, tier_name, grouped):
        case_name, tool, config_name = key
        case = cases.load_case(case_name, loaded)
        run_rows.append(run_row(tier, case, grouped[key]))
        if tool == manifest.CHOMP3RS:
            stage_rows.extend(stage_rows_of(case_name, config_name, grouped[key]))
    directory = SUMMARY_DIRECTORY / tier_name
    directory.mkdir(parents=True, exist_ok=True)
    write_table(directory / "runs.csv", RUN_COLUMNS, run_rows)
    write_table(directory / "stages.csv", STAGE_COLUMNS, stage_rows)
    print(f"{directory / 'runs.csv'} {len(run_rows)} rows")
    print(f"{directory / 'stages.csv'} {len(stage_rows)} rows")


def group_by_run(tier_name, runs_directory):
    """The records of a tier gathered by case, tool and configuration, each
    group in the order of its repetitions."""
    grouped = {}
    for path in records.paths_in(tier_name, runs_directory):
        record = records.read(path)
        key = (record["case"], record["tool"], record["config"]["name"])
        grouped.setdefault(key, []).append(record)
    for group in grouped.values():
        group.sort(key=lambda record: record["repetition"])
    return grouped


def ordered_keys(loaded, tier_name, grouped):
    """The groups in the order the tier asks for its runs, with any group the
    tier no longer names after them."""
    ordered = []
    named = set()
    for run in manifest.expand(loaded, tier_name):
        key = (run.case, run.tool, run.config)
        if key in named or key not in grouped:
            continue
        named.add(key)
        ordered.append(key)
    for key in sorted(grouped):
        if key in named:
            continue
        print(f"records the tier no longer names: {key[0]} {key[1]} {key[2]}")
        ordered.append(key)
    return ordered


def run_row(tier, case, group):
    first = group[0]
    config = first["config"]
    measured = [record for record in group if record["status"] != SKIPPED]
    row = {
        "case": case.name,
        "family": case.family,
        "ambient_dimension": case.ambient_dimension,
        "cube_count": case.cube_count,
        "bounding_box_volume": case.bounding_box_volume,
        "graded": "true" if case.graded else "false",
        "grade_count": blank_if_none(case.grade_count),
        "tool": first["tool"],
        "tool_version": first["tool_version"],
        "config": config["name"],
        "threads": config["threads"],
        "modulus": blank_if_none(config.get("modulus")),
        "status": worst_status(group),
        "repetitions": len(measured),
        "statuses": status_counts(group),
        "answer": answer_of(case, group),
        "image_id": first["machine"]["image_id"],
        "repository_commit": first["machine"]["repository_commit"],
        "skip_reason": first.get("skip_reason", ""),
    }
    row.update(measurement_columns(tier, measured))
    return row


def worst_status(group):
    return max((record["status"] for record in group), key=STATUS_ORDER.index)


def status_counts(group):
    """How many repetitions ended each way, empty where they all ended alike."""
    counted = {status: 0 for status in STATUS_ORDER}
    for record in group:
        counted[record["status"]] += 1
    ended = [(status, count) for status, count in counted.items() if count > 0]
    if len(ended) < 2:
        return ""
    return ",".join(f"{status}={count}" for status, count in ended)


def answer_of(case, group):
    """The first answer the repetitions agreed on, narrowed to the dimensions a
    restricted configuration declares its answer holds on, which is the window
    the correctness check compares it on."""
    key = "bar_counts" if case.graded else "betti"
    for record in group:
        if record["status"] not in COMPARABLE:
            continue
        answer = record["answer"][key]
        dimensions = record["config"].get("check_dimensions")
        if dimensions is not None:
            answer = [answer[dimension] for dimension in dimensions]
        return json.dumps(answer, separators=(",", ":"))
    return ""


def measurement_columns(tier, measured):
    """Each statistic over the repetitions that carry a value for it, a killed
    repetition counted at the limit it reached: a run killed for taking too long
    counts the tier's timeout as its wall time and has no processor time and no
    peak to count, and a run killed for taking too much memory counts the tier's
    cap as its peak and its own real wall and processor time."""
    wall = present(wall_of(tier, record) for record in measured)
    user = present(record["user_seconds"] for record in measured)
    system = present(record["system_seconds"] for record in measured)
    peak = present(peak_of(tier, record) for record in measured)
    return {
        "wall_median": median_or_blank(wall),
        "wall_min": min_or_blank(wall),
        "wall_max": max_or_blank(wall),
        "user_median": median_or_blank(user),
        "system_median": median_or_blank(system),
        "peak_rss_median_kb": median_or_blank(peak),
        "peak_rss_max_kb": max_or_blank(peak),
    }


def wall_of(tier, record):
    if record["status"] == TIMEOUT:
        return tier.timeout_seconds
    return record["wall_seconds"]


def peak_of(tier, record):
    if record["status"] == OUT_OF_MEMORY:
        return tier.memory_limit_gigabytes * 1024 * 1024
    return record["peak_rss_kilobytes"]


def present(values):
    return [value for value in values if value is not None]


def stage_rows_of(case_name, config_name, group):
    comparable = [record for record in group if record["status"] in COMPARABLE]
    if not comparable:
        return []
    rows = []
    for index, stage in enumerate(comparable[0]["stages"]):
        seconds = [record["stages"][index]["seconds"] for record in comparable]
        rows.append(
            {
                "case": case_name,
                "config": config_name,
                "stage": stage["name"],
                "seconds_median": statistics.median(seconds),
                "cells_in": stage["cells_in"],
                "cells_out": stage["cells_out"],
            }
        )
    return rows


def blank_if_none(value):
    return "" if value is None else value


def median_or_blank(values):
    return statistics.median(values) if values else ""


def min_or_blank(values):
    return min(values) if values else ""


def max_or_blank(values):
    return max(values) if values else ""


def write_table(path, columns, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
