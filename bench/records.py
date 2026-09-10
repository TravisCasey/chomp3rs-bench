"""Result records: one JSON file per run of one tool on one case.

A record lives at `results/runs/<tier>/<case>__<tool>__<config>__r<n>.json` and
holds what was run, what it cost, what it measured and what produced it. The
name is the identity of the run, so a record that is already there is a run
already done: the run loop leaves it alone and an interrupted tier resumes
where it stopped. Rerunning a run means deleting its record first. The only
change ever made to a record that is already written is the correctness check
writing its `status`, which moves from `finished` to `disputed` when the record
is part of a disagreement and back to `finished` when it is not.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from bench.manifest import Run

RUNS_DIRECTORY = Path("results/runs")


@dataclass
class RecordedRun(Run):
    """A run of a tier together with the family of its case."""

    family: str


def path_of(run, repetition):
    directory = RUNS_DIRECTORY / run.tier
    return directory / f"{run.case}__{run.tool}__{run.config}__r{repetition}.json"


def exists(run, repetition):
    return path_of(run, repetition).exists()


def write(run, repetition, measurement, answer, stages, tool_version, config, machine):
    record = heading(run, repetition, tool_version, config)
    record["wall_seconds"] = measurement.wall_seconds
    record["user_seconds"] = measurement.user_seconds
    record["system_seconds"] = measurement.system_seconds
    record["peak_rss_kilobytes"] = measurement.peak_rss_kilobytes
    record["status"] = measurement.status
    record["answer"] = answer
    record["stages"] = stages
    record["machine"] = machine
    return save(run, repetition, record)


def write_skipped(run, skip_reason, tool_version, config, machine):
    """Record that a tool declared it cannot do this run, and why."""
    record = heading(run, 0, tool_version, config)
    record["wall_seconds"] = None
    record["user_seconds"] = None
    record["system_seconds"] = None
    record["peak_rss_kilobytes"] = None
    record["status"] = "skipped"
    record["answer"] = None
    record["stages"] = None
    record["machine"] = machine
    record["skip_reason"] = skip_reason
    return save(run, 0, record)


def heading(run, repetition, tool_version, config):
    return {
        "case": run.case,
        "family": run.family,
        "tool": run.tool,
        "tool_version": tool_version,
        "config": config,
        "tier": run.tier,
        "repetition": repetition,
    }


def save(run, repetition, record):
    return save_at(path_of(run, repetition), record)


def save_at(path, record):
    """Write the record beside its name and move it on, so a half-written record
    never looks like a finished run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".json.part")
    partial.write_text(json.dumps(record, indent=2) + "\n")
    partial.replace(path)
    return path


def paths_in(tier, directory=RUNS_DIRECTORY):
    return sorted((directory / tier).glob("*.json"))


def read(path):
    return json.loads(path.read_text())
