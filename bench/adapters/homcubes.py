"""homcubes: a list of cubes or of cells in, one Betti number per line out.

The program reads two formats and decides which a file holds by looking for an
`x` in its first characters, so the names below are for the reader's benefit
only. A case whose cubes are all of the top dimension becomes one parenthesised
coordinate tuple per line; a case whose cells are of mixed dimension becomes one
product of closed intervals per line, `[a,a+1]` along a coordinate the cell
spans and `[a]` along one it does not, and the program adds the faces itself.
The run passes `-p 2`, which computes over the field of integers modulo 2, and
`-b`, which provides a file holding one Betti number per line starting at
dimension 0. That file has one line per ambient dimension, so it stops one
dimension below the ambient dimension and the answer is as long as the file.
The tool is refused above ambient dimension 12, and at dimension 12 on a case of
more than 5,000 cubes. The circle of 4,690 cubes at dimension 12 finished in 44.5
minutes, about 0.57 seconds a cube, while the flow covers of dimension 12, the
torus and the longer thickened curve all ran past a 20 minute timeout; 5,000
cubes is what that rate fits in a 60 minute timeout. Above dimension 19 its
reduction stage would in any event count neighbours in a 32-bit integer that
overflows at 3^20. It reads no grade, birth or other filtration value, so graded
cases are skipped.
"""

from pathlib import Path

from bench import cases
from bench.adapters import CASES_MOUNT, OUTPUT_MOUNT

NAME = "homcubes"
TRACKS = {"homology"}
ACCEPTS_MIXED_DIMENSION = True
MAXIMUM_DIMENSION = 12
CUBE_LIMIT_AT_MAXIMUM_DIMENSION = 5000
COEFFICIENTS = "Z/2"
BYTES_PER_CELL = None
CONSTRUCTION = None
VERSION = (
    "archive dated 2024-02-15,"
    " sha256 16ff175453e17c83e5cf207a7574453dbe348a26a2129759e30fce605580dbc0"
)
CONVERTED_DIRECTORY = Path("cases/converted/homcubes")
CUBE_SUFFIX = ".cub"
CELL_SUFFIX = ".cel"
BETTI_SUFFIX = ".betti"
PARTIAL_SUFFIX = ".part"


def version():
    return VERSION


def convert(case):
    suffix = CELL_SUFFIX if case.mixed_dimension else CUBE_SUFFIX
    path = CONVERTED_DIRECTORY / (case.name + suffix)
    if path.exists() and path.stat().st_mtime >= case.path.stat().st_mtime:
        return path
    coordinates, grades, extents = cases.read_canonical(case.path, case.columns)
    dimension = coordinates.shape[1]
    if case.mixed_dimension:
        lines = [
            cell_line(coordinates[index], int(extents[index]))
            for index in range(coordinates.shape[0])
        ]
    else:
        lines = [f"dimension {dimension}"]
        lines += [cube_line(row) for row in coordinates]
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(suffix + PARTIAL_SUFFIX)
    partial.write_text("\n".join(lines) + "\n")
    partial.replace(path)
    return path


def cube_line(coordinates):
    return "(" + ",".join(str(int(value)) for value in coordinates) + ")"


def cell_line(coordinates, extent):
    factors = []
    for axis, value in enumerate(coordinates):
        base = int(value)
        if extent >> axis & 1:
            factors.append(f"[{base},{base + 1}]")
        else:
            factors.append(f"[{base}]")
    return "x".join(factors)


def command(case, config, converted):
    return [
        "homcubes",
        "-p",
        "2",
        "-b",
        f"{OUTPUT_MOUNT}/{case.name}{BETTI_SUFFIX}",
        container_path(converted),
    ]


def container_path(path):
    """Where the container sees a file that lives under the repository's cases."""
    return str(Path(CASES_MOUNT) / Path(path).relative_to("cases"))


def parse(stdout, stderr, output_files):
    betti_file = next(path for path in output_files if path.suffix == BETTI_SUFFIX)
    return {"betti": [int(rank) for rank in betti_file.read_text().split()]}


def skip_reason(case, config, memory_limit_bytes):
    if case.graded:
        return "graded input not accepted"
    if case.ambient_dimension > MAXIMUM_DIMENSION:
        return f"dimension {case.ambient_dimension} above limit {MAXIMUM_DIMENSION}"
    if (
        case.ambient_dimension == MAXIMUM_DIMENSION
        and case.cube_count > CUBE_LIMIT_AT_MAXIMUM_DIMENSION
    ):
        return (
            f"{case.cube_count} cubes at dimension {MAXIMUM_DIMENSION}, over the"
            f" {CUBE_LIMIT_AT_MAXIMUM_DIMENSION} that fit a 60 minute timeout"
        )
    return None
