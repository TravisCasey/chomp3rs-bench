"""DIPHA: a dense grid of vertex values in, a binary persistence diagram out.

The values sit on the grid's vertices, which is the V-construction: a lattice of
m points per axis becomes a complex of 2m - 1 cell positions per axis, a cell
takes the largest value among its vertices, and two cubes meeting only at a
corner come out separate where the cube list means them connected. The
conversion therefore doubles the grid, so every cell of the case is a lattice
point of its own, and a case of any dimensions reaches the tool that way,
mixed-dimension cases included.

The input file is binary, every integer a little-endian 64-bit integer and every
value a double: the magic number, the type that marks image data, the number of
grid points, the ambient dimension, one size per axis, and then one value per
grid point with the first axis varying fastest.

The output file is binary too: the magic number, the type that marks a
persistence diagram, the number of bars, and then per bar a dimension, a birth
and a death. A bar that never dies is written with its dimension negated and
shifted, as -k - 1 for dimension k, and its death set to the largest value in
the complex rather than to any infinity. The tool drops three kinds of bar
before it writes: one whose birth equals its death, one born at the largest
value in the complex, and one that never dies at the ambient dimension. None of
them is a bar of the case, since the doubled grid always carries the absent
value on the empty part of its box and a box has no homology above dimension 0.

It computes over the integers modulo 2 only, with no option to choose the field.
The command line takes an optional `--upper_dim`, which yields bars only below
the dimension given; the run passes none of it and takes the default, which
computes every dimension. The program is run through `mpiexec -n 1`, the one
rank the run's configuration asks for.
"""

from pathlib import Path

import numpy

from bench import dense
from bench.adapters import CASES_MOUNT, OUTPUT_MOUNT

NAME = "dipha"
TRACKS = {"homology", "persistence"}
ACCEPTS_MIXED_DIMENSION = True
MAXIMUM_DIMENSION = None
COEFFICIENTS = "Z/2"
BYTES_PER_CELL = 82
CONSTRUCTION = "V"
VERSION = "commit 0b874769fbd092c07a12cebc2459adb02117c2fd"
CONVERTED_DIRECTORY = Path("cases/converted/dipha")
COMPLEX_SUFFIX = ".complex"
DIAGRAM_SUFFIX = ".diagram"
MAGIC = 8067171840
IMAGE_DATA = 1
INTEGER = "<i8"
VALUE = "<f8"
FIELD_BYTES = 8
DIAGRAM_HEADER_FIELDS = 3
BAR = numpy.dtype([("dimension", INTEGER), ("birth", VALUE), ("death", VALUE)])
HOMOLOGY_TRACK = "homology"
PERSISTENCE_TRACK = "persistence"
RANKS = "1"


def version():
    return VERSION


def convert(case):
    path = CONVERTED_DIRECTORY / (case.name + COMPLEX_SUFFIX)
    if path.exists() and path.stat().st_mtime >= case.path.stat().st_mtime:
        return path
    values = dense.doubled_vertex_values(case)
    header = numpy.array(
        [MAGIC, IMAGE_DATA, values.size, values.ndim, *values.shape], dtype=INTEGER
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as binary:
        header.tofile(binary)
        values.ravel(order="F").astype(VALUE, copy=False).tofile(binary)
    return path


def command(case, config, converted):
    return [
        "mpiexec",
        "-n",
        RANKS,
        "dipha",
        container_path(converted),
        f"{OUTPUT_MOUNT}/{output_name(case)}",
    ]


def output_name(case):
    """The name the diagram is written under, carrying to `parse` the track, the
    ambient dimension and the absent value, none of which `parse` is given."""
    track = PERSISTENCE_TRACK if case.graded else HOMOLOGY_TRACK
    absent = dense.absent_value(case)
    return f"{track}-{case.ambient_dimension}-{absent}{DIAGRAM_SUFFIX}"


def container_path(path):
    """Where the container sees a file that lives under the repository's cases."""
    parts = Path(path).parts
    return str(Path(CASES_MOUNT, *parts[parts.index("cases") + 1 :]))


def parse(stdout, stderr, output_files):
    path = next(path for path in output_files if path.suffix == DIAGRAM_SUFFIX)
    track, ambient, absent = path.stem.split("-")
    bars = numpy.fromfile(path, dtype=BAR, offset=DIAGRAM_HEADER_FIELDS * FIELD_BYTES)
    counts = [0] * (int(ambient) + 1)
    for bar in bars:
        if bar["birth"] < int(absent):
            counts[bar_dimension(int(bar["dimension"]))] += 1
    key = "bar_counts" if track == PERSISTENCE_TRACK else "betti"
    return {key: counts}


def bar_dimension(written):
    """The dimension of a bar, which the tool writes as -k - 1 for a bar of
    dimension k that never dies."""
    return written if written >= 0 else -written - 1


def skip_reason(case, config, memory_limit_bytes):
    cells = dense.cell_count(case, CONSTRUCTION)
    if cells * BYTES_PER_CELL > memory_limit_bytes:
        gigabytes = memory_limit_bytes // 1024**3
        return (
            f"dense complex of {cells} cells at {BYTES_PER_CELL} bytes each"
            f" exceeds the {gigabytes} GB cap"
        )
    return None
