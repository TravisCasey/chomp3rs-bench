"""Perseus: a sparse list of top cubes in, one interval file per dimension out.

The mode the run selects is `scubtop`, the sparse cubical toplex, and not the
neighbouring `cubtop`, which is a dense grid in a different file. The file is
the ambient dimension on its first line and then one line per top cube, the
`d` integer coordinates of the cube's base orthant followed by the cube's
birth. Births must be at least one, a birth of zero ending the program in a
segmentation fault, so a canonical grade becomes that grade plus one and an
ungraded case is written with every birth one. The conversion also shifts the
coordinates so that every axis starts at zero, a translation of the whole case
that leaves its homology alone and keeps negative coordinates out of the file.
A cube listed twice keeps the first birth given rather than the smallest, so
each maximal cube of the case appears once, as it does in the canonical file.

The program works over the integers modulo 2 only, with no option to choose the
field, and reads top-dimensional cubes only, so mixed-dimension cases are
skipped. It materialises every face of every top cube, 3^d cells each, before it
reduces anything, so a case is skipped when one cube alone would exceed the
memory cap.
"""

from pathlib import Path

from bench import cases
from bench.adapters import CASES_MOUNT, OUTPUT_MOUNT

NAME = "perseus"
TRACKS = {"homology", "persistence"}
ACCEPTS_MIXED_DIMENSION = False
MAXIMUM_DIMENSION = None
COEFFICIENTS = "Z/2"
BYTES_PER_CELL = None
CONSTRUCTION = None
VERSION = (
    "4.0 beta, sha256 7279091080b8b6ef8d8bbcf470a76398b752f102def222a9740f2e85ad8c7925"
)
CONVERTED_DIRECTORY = Path("cases/converted/perseus")
SUFFIX = ".txt"
PARTIAL_SUFFIX = ".part"
MODE = "scubtop"
BIRTH_SHIFT = 1
NEVER_DIES = -1
CELLS_PER_CUBE_BASE = 3
BYTES_PER_MATERIALISED_CELL = 1400
HOMOLOGY_PREFIX = "homology"
PERSISTENCE_PREFIX = "persistence"


def version():
    return VERSION


def convert(case):
    path = CONVERTED_DIRECTORY / (case.name + SUFFIX)
    if path.exists() and path.stat().st_mtime >= case.path.stat().st_mtime:
        return path
    coordinates, grades, _ = cases.read_canonical(case.path, case.columns)
    shifted = coordinates - coordinates.min(axis=0)
    lines = [str(shifted.shape[1])]
    for index in range(shifted.shape[0]):
        birth = BIRTH_SHIFT if grades is None else int(grades[index]) + BIRTH_SHIFT
        lines.append(
            " ".join(str(int(value)) for value in shifted[index]) + f" {birth}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(SUFFIX + PARTIAL_SUFFIX)
    partial.write_text("\n".join(lines) + "\n")
    partial.replace(path)
    return path


def command(case, config, converted):
    return [
        "perseus",
        MODE,
        container_path(converted),
        f"{OUTPUT_MOUNT}/{output_prefix(case)}",
    ]


def output_prefix(case):
    """The prefix Perseus names its output files after, carrying the track and
    the ambient dimension through to `parse`."""
    track = PERSISTENCE_PREFIX if case.graded else HOMOLOGY_PREFIX
    return f"{track}-{case.ambient_dimension}"


def container_path(path):
    """Where the container sees a file that lives under the repository's cases."""
    parts = Path(path).parts
    return str(Path(CASES_MOUNT, *parts[parts.index("cases") + 1 :]))


def parse(stdout, stderr, output_files):
    track = None
    dimension = None
    counts = {}
    for path in output_files:
        prefix, _, tail = path.stem.rpartition("_")
        if not tail.isdigit():
            continue
        track, _, ambient = prefix.rpartition("-")
        dimension = int(ambient)
        counts[int(tail)] = bars_counted(path, track)
    answer = [counts.get(index, 0) for index in range(dimension + 1)]
    key = "bar_counts" if track == PERSISTENCE_PREFIX else "betti"
    return {key: answer}


def bars_counted(path, track):
    """The bars of one interval file the track asks for: those that never die on
    the homology track, and on the persistence track those too along with every
    bar whose birth is below its death."""
    counted = 0
    for line in path.read_text().split("\n"):
        if not line.strip():
            continue
        birth, death = (int(field) for field in line.split())
        if death == NEVER_DIES:
            counted += 1
        elif track == PERSISTENCE_PREFIX and birth < death:
            counted += 1
    return counted


def skip_reason(case, config, memory_limit_bytes):
    if case.mixed_dimension:
        return "mixed-dimension input not accepted"
    cells = CELLS_PER_CUBE_BASE**case.ambient_dimension
    if cells * BYTES_PER_MATERIALISED_CELL > memory_limit_bytes:
        gigabytes = memory_limit_bytes // 1024**3
        return (
            f"one cube of {cells} cells at {BYTES_PER_MATERIALISED_CELL} bytes each"
            f" exceeds the {gigabytes} GB cap"
        )
    return None
