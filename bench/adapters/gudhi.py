"""GUDHI: a dense grid of top cells in, one JSON line out.

The tool is a Python module and installs no program, so it is called through a
script the run mounts. The conversion writes the case's bounding box as a
`.npy` array with one value per top cube position, which is the T-construction:
the values sit on top-dimensional cells, where a list of closed top cubes puts
them, and no doubling is needed. A position with no listed cube takes one above
the largest grade in the case, so the empty part of the box arrives last and a
bar dying there has not died inside the case.

It computes over the integers modulo any prime up to 46337, chosen with the
`homology_coeff_field` argument, and the run fixes that argument at 2, so every
measurement here is over the field of integers modulo 2.
"""

import json
from pathlib import Path

import numpy

from bench import dense
from bench.adapters import CASES_MOUNT, SCRIPTS_MOUNT

NAME = "gudhi"
TRACKS = {"homology", "persistence"}
ACCEPTS_MIXED_DIMENSION = False
MAXIMUM_DIMENSION = None
COEFFICIENTS = "Z/2"
BYTES_PER_CELL = 122
CONSTRUCTION = "T"
VERSION = (
    "release 3.13.0, tag tags/gudhi-release-3.13.0,"
    " commit 5dbe510bed5d8d700ec7243fd915769fb67964a2"
)
SCRIPT = f"{SCRIPTS_MOUNT}/gudhi_run.py"
CONVERTED_DIRECTORY = Path("cases/converted/gudhi")
SUFFIX = ".npy"
MODULUS = "2"


def version():
    return VERSION


def convert(case):
    path = CONVERTED_DIRECTORY / (case.name + SUFFIX)
    if path.exists() and path.stat().st_mtime >= case.path.stat().st_mtime:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    numpy.save(path, dense.top_cell_values(case))
    return path


def command(case, config, converted):
    argv = [
        "tools-python",
        SCRIPT,
        container_path(converted),
        "--modulus",
        MODULUS,
        "--absent-value",
        str(dense.absent_value(case)),
    ]
    if case.graded:
        argv.append("--graded")
    return argv


def container_path(path):
    """Where the container sees a file that lives under the repository's cases."""
    parts = Path(path).parts
    return str(Path(CASES_MOUNT, *parts[parts.index("cases") + 1 :]))


def parse(stdout, stderr, output_files):
    return json.loads(stdout)


def skip_reason(case, config, memory_limit_bytes):
    if case.mixed_dimension:
        return "mixed-dimension input not accepted"
    cells = dense.cell_count(case)
    if cells * BYTES_PER_CELL > memory_limit_bytes:
        gigabytes = memory_limit_bytes // 1024**3
        return (
            f"dense complex of {cells} cells at {BYTES_PER_CELL} bytes each"
            f" exceeds the {gigabytes} GB cap"
        )
    return None
