"""Cubical Ripser: a dense grid of top cells in, one bar per line out.

The program run is `tcubicalripser`, the T-construction of the two the project
builds: its values sit on top-dimensional cells, where a list of closed top
cubes puts them, so the case's own grid goes in and no doubling is needed. A
position with no listed cube takes one above the largest grade in the case, so
the empty part of the box arrives last and a bar dying there has not died
inside the case.

The input format is chosen by the file's extension and by nothing else. The
conversion writes the Perseus text grid under `.txt`: the ambient dimension on
the first line, then one line per axis giving that axis's size in array order,
then one value per grid position with the first axis varying fastest. A `-1` in
such a file does not mean the grade minus one, it means the program's threshold,
so the absent value is written as itself and never as `-1`.

The output file `--output` names ends in `.csv` and is one bar per line, the
dimension, the birth and the death, with the coordinates of the cells that
created and destroyed the bar dropped by `--location none`. The death of a bar
that never dies is the largest double rather than an infinity, so a bar counts
in its dimension when its birth is below the absent value and below its death.
Standard output carries the pair counts and the time taken.

`--maxdim` defaults to 3 and the program clamps it to one below the ambient
dimension, so every dimension a case of the dimensions this tool accepts can
carry is computed without passing the flag. It works over the integers modulo 2
only, with no option to choose the field. It reads one value per position of one
grid, so mixed-dimension cases are skipped, and its readers refuse an ambient
dimension above 4.
"""

from pathlib import Path

import numpy

from bench import dense
from bench.adapters import CASES_MOUNT, OUTPUT_MOUNT

NAME = "cubical_ripser"
TRACKS = {"homology", "persistence"}
ACCEPTS_MIXED_DIMENSION = False
MAXIMUM_DIMENSION = 4
COEFFICIENTS = "Z/2"
BYTES_PER_CELL = 14
CONSTRUCTION = "T"
VERSION = "commit e9632f2466674c07cda0db2f178da26007194496"
PROGRAM = "tcubicalripser"
CONVERTED_DIRECTORY = Path("cases/converted/cubical_ripser")
GRID_SUFFIX = ".txt"
DIAGRAM_SUFFIX = ".csv"
LOCATION = "none"
HOMOLOGY_TRACK = "homology"
PERSISTENCE_TRACK = "persistence"


def version():
    return VERSION


def convert(case):
    path = CONVERTED_DIRECTORY / (case.name + GRID_SUFFIX)
    if path.exists() and path.stat().st_mtime >= case.path.stat().st_mtime:
        return path
    values = dense.top_cell_values(case)
    header = [str(values.ndim), *(str(side) for side in values.shape)]
    flattened = values.ravel(order="F").astype(numpy.int64, copy=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as text:
        text.write("\n".join(header) + "\n")
        numpy.savetxt(text, flattened, fmt="%d")
    return path


def command(case, config, converted):
    return [
        PROGRAM,
        "--location",
        LOCATION,
        "--output",
        f"{OUTPUT_MOUNT}/{output_name(case)}",
        container_path(converted),
    ]


def output_name(case):
    """The name the bars are written under, carrying to `parse` the track, the
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
    counts = [0] * (int(ambient) + 1)
    for line in path.read_text().split("\n"):
        if not line.strip():
            continue
        dimension, birth, death = line.split(",")
        if float(birth) < int(absent) and float(birth) < float(death):
            counts[int(dimension)] += 1
    key = "bar_counts" if track == PERSISTENCE_TRACK else "betti"
    return {key: counts}


def skip_reason(case, config, memory_limit_bytes):
    if case.ambient_dimension > MAXIMUM_DIMENSION:
        return f"dimension {case.ambient_dimension} above limit {MAXIMUM_DIMENSION}"
    if case.mixed_dimension:
        return "mixed-dimension input not accepted"
    cells = dense.cell_count(case, CONSTRUCTION)
    if cells * BYTES_PER_CELL > memory_limit_bytes:
        gigabytes = memory_limit_bytes // 1024**3
        return (
            f"dense complex of {cells} cells at {BYTES_PER_CELL} bytes each"
            f" exceeds the {gigabytes} GB cap"
        )
    return None
