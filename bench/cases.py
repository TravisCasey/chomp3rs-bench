"""The canonical case format, its sidecars and the in-memory case record.

A canonical file has one line per maximal cube and no header, with the fields
`x_1,...,x_d[,grade][,extent]`: the integer coordinates of the cube's base
orthant, an optional non-negative integer grade, and an optional extent string
of `d` characters `0` or `1` where character `i` is `1` when the cube spans
coordinate `i`. A file with no extent column lists top cubes only. Beside every
case file sits a sidecar `<name>.json` holding the case's shape and, where one
is known, its answer.

Used by the generators, the converters and the run loop; see `bench.cli` for
the command line.
"""

import json
from dataclasses import dataclass
from math import prod
from pathlib import Path

import numpy


@dataclass
class Case:
    name: str
    path: Path
    family: str
    ambient_dimension: int
    cube_count: int
    graded: bool
    mixed_dimension: bool
    grade_count: int | None
    bounding_box: list[list[int]]
    bounding_box_volume: int
    betti: list[int] | None
    bar_counts: list[int] | None
    source: dict


def read_canonical(path, columns):
    """Read a canonical file into coordinates, grades and extent masks.

    `columns` is the manifest's declaration of the file's layout, one of
    `plain`, `graded`, `extent` and `graded_extent`.
    """
    lines = Path(path).read_text().splitlines()
    has_grade = columns in ("graded", "graded_extent")
    has_extent = columns in ("extent", "graded_extent")
    dimension = len(lines[0].split(",")) - int(has_grade) - int(has_extent)
    if has_extent:
        rows = [line.split(",") for line in lines]
        coordinates = numpy.array(
            [row[:dimension] for row in rows], dtype=numpy.int64
        )
        grades = None
        if has_grade:
            grades = numpy.array(
                [row[dimension] for row in rows], dtype=numpy.int64
            )
        extents = numpy.array(
            [extent_mask(row[-1]) for row in rows], dtype=numpy.uint32
        )
    else:
        table = numpy.loadtxt(path, delimiter=",", dtype=numpy.int64, ndmin=2)
        coordinates = table[:, :dimension]
        grades = table[:, dimension] if has_grade else None
        extents = None
    return coordinates, grades, extents


def extent_mask(extent):
    """Turn an extent string into a bit mask with bit `i` for character `i`."""
    return sum(1 << axis for axis, character in enumerate(extent) if character == "1")


def extent_string(mask, dimension):
    return "".join("1" if mask >> axis & 1 else "0" for axis in range(dimension))


def write_canonical(path, coordinates, grades=None, extents=None):
    dimension = coordinates.shape[1]
    lines = []
    for index in range(coordinates.shape[0]):
        fields = [str(int(value)) for value in coordinates[index]]
        if grades is not None:
            fields.append(str(int(grades[index])))
        if extents is not None:
            fields.append(extent_string(int(extents[index]), dimension))
        lines.append(",".join(fields))
    Path(path).write_text("\n".join(lines) + "\n")


def sidecar_path(case_path):
    return Path(case_path).with_suffix(".json")


def write_sidecar(case_path, **fields):
    """Write the sidecar of a case file, measuring the file for its shape.

    The caller passes the manifest's `columns`, the `family` and the `source`,
    and `betti` and `bar_counts` when the case has a known answer; everything
    else is read off the cubes.
    """
    coordinates, grades, extents = read_canonical(case_path, fields.pop("columns"))
    dimension = int(coordinates.shape[1])
    minima = coordinates.min(axis=0)
    maxima = coordinates.max(axis=0)
    bounding_box = [
        [int(minimum), int(maximum)] for minimum, maximum in zip(minima, maxima)
    ]
    full_mask = (1 << dimension) - 1
    record = {
        "family": fields["family"],
        "ambient_dimension": dimension,
        "cube_count": int(coordinates.shape[0]),
        "graded": grades is not None,
        "mixed_dimension": extents is not None and bool((extents != full_mask).any()),
        "grade_count": int(numpy.unique(grades).size) if grades is not None else None,
        "bounding_box": bounding_box,
        "bounding_box_volume": prod(
            maximum - minimum + 1 for minimum, maximum in bounding_box
        ),
        "source": fields["source"],
    }
    for key in ("betti", "bar_counts"):
        if fields.get(key) is not None:
            record[key] = fields[key]
    path = sidecar_path(case_path)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return path


def load_case(name, manifest):
    entry = manifest.cases[name]
    record = json.loads(sidecar_path(entry.path).read_text())
    return Case(
        name=name,
        path=entry.path,
        family=record["family"],
        ambient_dimension=record["ambient_dimension"],
        cube_count=record["cube_count"],
        graded=record["graded"],
        mixed_dimension=record["mixed_dimension"],
        grade_count=record["grade_count"],
        bounding_box=record["bounding_box"],
        bounding_box_volume=record["bounding_box_volume"],
        betti=record.get("betti"),
        bar_counts=record.get("bar_counts"),
        source=record["source"],
    )
