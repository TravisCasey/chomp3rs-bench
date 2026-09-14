"""pyCHomP2: a Python module, called through a script the run mounts.

The engine takes no list of cubes. Its only constructor takes a box and fills it
with 2^d cells per box position, identifying the far side of the box with the
near side, so a case reaches it as its bounding box padded by two along every
axis, the margin the module's own homology helper uses, with a value on every
cell: the least grade among the listed cubes in the cell's star, and one above
the largest grade in the case where no listed cube is in the star, so that the
empty part of the box stays out of the answer. One layer of padding is not
enough: on cases whose cubes reach the box edges the engine then loses classes.

The answer derives from a connection matrix. On an ungraded case its cell counts
at grade 0 are the Betti numbers. On a graded case the counts are not bar
counts, because they count the cells that end a bar alongside the cells that
start one, so the script pairs the connection matrix's boundary itself and reads
a bar whose death is the absent value as never dying. The engine works over the
integers modulo 2 only, and the construction here places top cubes in the box
and nothing else, so mixed-dimension cases are skipped.
"""

import json
from math import prod
from pathlib import Path

from bench.adapters import CASES_MOUNT, SCRIPTS_MOUNT

NAME = "pychomp2"
TRACKS = {"homology", "persistence"}
ACCEPTS_MIXED_DIMENSION = False
MAXIMUM_DIMENSION = None
COEFFICIENTS = "Z/2"
BYTES_PER_CELL = 14
CONSTRUCTION = "T"
VERSION = "commit b7b11af5fc387a6f55f42dd8fabb8d710e50d7c6 (1.1.2)"
SCRIPT = f"{SCRIPTS_MOUNT}/pychomp2_run.py"
PADDING = 2


def version():
    return VERSION


def convert(case):
    return case.path


def command(case, config, converted):
    return [
        "tools-python",
        SCRIPT,
        container_path(converted),
        "--columns",
        case.columns,
        "--modulus",
        "2",
    ]


def container_path(path):
    """Where the container sees a file that lives under the repository's cases."""
    parts = Path(path).parts
    return str(Path(CASES_MOUNT, *parts[parts.index("cases") + 1 :]))


def parse(stdout, stderr, output_files):
    return json.loads(stdout)


def skip_reason(case, config, memory_limit_bytes):
    if case.mixed_dimension:
        return "mixed-dimension input not accepted"
    cells = complex_cells(case)
    if cells * BYTES_PER_CELL > memory_limit_bytes:
        gigabytes = memory_limit_bytes // 1024**3
        return (
            f"dense complex of {cells} cells at {BYTES_PER_CELL} bytes each"
            f" exceeds the {gigabytes} GB cap"
        )
    return None


def complex_cells(case):
    """The cells of the dense complex: 2^d for every position of the bounding
    box padded by two along every axis."""
    volume = prod(
        maximum - minimum + 1 + PADDING for minimum, maximum in case.bounding_box
    )
    return volume * 2**case.ambient_dimension
