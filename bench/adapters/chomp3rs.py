"""The chomp3rs driver: the canonical case file in, one JSON record out.

The driver reads the canonical file unchanged, grades and mixed-dimension cells
included, so there is nothing to convert and no case is skipped for its format.
It prints one JSON object on standard output holding the tool and its version,
the configuration it ran, one entry per pipeline stage with that stage's wall
time and the cell counts entering and leaving it, and an answer with the Betti
numbers and the bar counts per dimension.
"""

import json
from pathlib import Path

from bench.adapters import CASES_MOUNT

NAME = "chomp3rs"
TRACKS = {"homology", "persistence"}
ACCEPTS_MIXED_DIMENSION = True
MAXIMUM_DIMENSION = 24
COEFFICIENTS = "Z/p"
BYTES_PER_CELL = None
CONSTRUCTION = None
VERSION = "6199ed6f883d15b531f5b6068d40e8000d83833b"


def version():
    return VERSION


def convert(case):
    return case.path


def command(case, config, converted):
    argv = [
        "chomp3rs-driver",
        container_path(converted),
        "--columns",
        case.columns,
        "--backend",
        config["backend"],
        "--threads",
        str(config["threads"]),
        "--modulus",
        str(config["modulus"]),
    ]
    if "max_critical_dimension" in config:
        argv += ["--max-critical-dimension", str(config["max_critical_dimension"])]
    return argv


def container_path(path):
    """Where the container sees a file that lives under the repository's cases."""
    parts = Path(path).parts
    return str(Path(CASES_MOUNT, *parts[parts.index("cases") + 1 :]))


def parse(stdout, stderr, output_files):
    record = json.loads(stdout)
    return {**record["answer"], "stages": record["stages"]}


def skip_reason(case, config, memory_limit_bytes):
    if case.ambient_dimension > MAXIMUM_DIMENSION:
        return f"dimension {case.ambient_dimension} above limit {MAXIMUM_DIMENSION}"
    if case.graded and "max_critical_dimension" in config:
        return "critical dimension cap has no meaning on a graded case"
    return None
