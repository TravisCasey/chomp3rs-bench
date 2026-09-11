"""The grading generators: the cubes of a base case with a grade added.

A grading case names a base case in its parameters; `bench generate` resolves
that name to the base's canonical file and hands the generator the file's path
and the base's column layout alongside the manifest's own parameters. The
generator reads the base's cubes, gives each one a grade and writes
`<name>.csv` and `<name>.json` into the directory it is given, in the base's
shape with the grades added and the base's extents kept. The names under which
they are called are the keys of `bench.generators.GENERATORS`.
"""

import json

import numpy

from bench.cases import read_canonical, sidecar_path, write_canonical, write_sidecar

RESOLVED_KEYS = ("base_path", "base_columns")
CHUNK_ROWS = 128


def sweep(name, seed, parameters, output_directory):
    coordinates, extents, base = read_base(parameters)
    grade_count = parameters["grade_count"]
    positions = coordinates[:, parameters["axis"]]
    minimum = positions.min()
    extent = positions.max() - minimum + 1
    grades = (positions - minimum) * grade_count // extent
    write_graded_case(
        name,
        seed,
        parameters,
        output_directory,
        "sweep",
        coordinates,
        grades,
        extents,
        base,
        sweep_bar_counts(coordinates, grades, base),
    )


def random_grades(name, seed, parameters, output_directory):
    coordinates, extents, base = read_base(parameters)
    generator = numpy.random.default_rng(seed)
    grades = generator.integers(0, parameters["grade_count"], size=coordinates.shape[0])
    write_graded_case(
        name,
        seed,
        parameters,
        output_directory,
        "random_grades",
        coordinates,
        grades,
        extents,
        base,
        None,
    )


def read_base(parameters):
    """The base case's cubes, the extent masks it carries where it has them,
    and its sidecar."""
    base_path = parameters["base_path"]
    coordinates, _, extents = read_canonical(base_path, parameters["base_columns"])
    base = json.loads(sidecar_path(base_path).read_text())
    return coordinates, extents, base


def write_graded_case(
    name,
    seed,
    parameters,
    output_directory,
    generator,
    coordinates,
    grades,
    extents,
    base,
    bar_counts,
):
    path = output_directory / f"{name}.csv"
    write_canonical(path, coordinates, grades=grades, extents=extents)
    write_sidecar(
        path,
        columns="graded_extent" if extents is not None else "graded",
        family=base["family"],
        source={
            "kind": "generated",
            "generator": generator,
            "seed": seed,
            "parameters": {
                key: value
                for key, value in parameters.items()
                if key not in RESOLVED_KEYS
            },
        },
        bar_counts=bar_counts,
    )


def sweep_bar_counts(coordinates, grades, base):
    """The bars of a sweep where the closed form holds, and `None` elsewhere."""
    circle = [1, 1] + [0] * (coordinates.shape[1] - 1)
    if base.get("betti") != circle:
        return None
    if broken_grade(coordinates, grades) is not None:
        return None
    return circle


def broken_grade(coordinates, grades):
    """The least grade whose sublevel set is more than one piece, or `None`
    where every sublevel set is connected.

    The cubes arrive grade by grade and a pair of them joins once both are
    there, so the pieces are counted by how many of the joins found their two
    cubes already together.
    """
    pairs = adjacent_pairs(coordinates)
    pair_grades = grades[pairs].max(axis=1)
    parent = list(range(coordinates.shape[0]))
    pieces = 0
    for grade in numpy.unique(grades):
        pieces += int((grades == grade).sum())
        for first, second in pairs[pair_grades == grade]:
            pieces -= int(join(parent, int(first), int(second)))
        if pieces != 1:
            return int(grade)
    return None


def adjacent_pairs(coordinates):
    """Every pair of cubes whose base orthants differ by at most one on every
    axis. That is exactly the pairs whose closures meet where every cube is
    top-dimensional, which the bases that can carry a closed form are; a cube
    spanning only some of its axes can come out paired with one its closure
    does not meet.
    """
    count = coordinates.shape[0]
    pairs = []
    for start in range(0, count, CHUNK_ROWS):
        block = coordinates[start : start + CHUNK_ROWS]
        distances = numpy.abs(block[:, None, :] - coordinates[None, :, :]).max(axis=2)
        rows, columns = numpy.nonzero(distances <= 1)
        rows = rows + start
        touching = rows < columns
        pairs.append(numpy.stack([rows[touching], columns[touching]], axis=1))
    return numpy.concatenate(pairs)


def join(parent, first, second):
    """Put two cubes in one piece, and say whether they were two pieces."""
    first = representative(parent, first)
    second = representative(parent, second)
    if first == second:
        return False
    parent[second] = first
    return True


def representative(parent, index):
    while parent[index] != index:
        parent[index] = parent[parent[index]]
        index = parent[index]
    return index
