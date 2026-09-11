"""The dense grid a tool builds from a case: its shape, its cost and its values.

A tool that takes a grid rather than a list of cubes takes it in one of two
constructions. In the T-construction the values sit on top-dimensional cells,
one per position of the case's bounding box, which is the complex a list of
closed top cubes already means. In the V-construction they sit on the grid's
vertices, and the complex built from them is a different one: two cubes meeting
only at a corner are connected in the cube list and separate there. The
converter for such a tool doubles the grid, giving the cell with base orthant
`b` and extent mask `e` the lattice point `2 * b + e`, so that every cell of the
case is a point of its own and the intended answer comes back.

A position of either grid that no listed cell reaches takes the absent value,
one above the largest grade in the case and 1 where the case carries no grade.
That value arrives last in the filtration, so the empty part of the box stays
out of the answer and a bar dying there has not died inside the case.

`cell_count` is what a dense adapter's `skip_reason` measures a case by: the
cells of the complex the tool builds. That is one cell per position of a grid of
side `2n + 1` per axis in the T-construction, the closure of the top cells, and
in the V-construction one per point and per gap between points of the doubled
lattice, `4n + 1` per axis.

`top_cell_values` reads every listed cube as a top cube, which is what a
T-construction tool takes and what a mixed-dimension case has no grid for; the
adapters of those tools skip such a case. `doubled_vertex_values` takes a case
of any dimensions, which is why the doubled grid is defined on cells rather than
on top cubes.
"""

import itertools
from math import prod

import numpy

from bench import cases

TOP_CELLS = "T"
DOUBLED_VERTICES = "V"
NEAR_END = 0
SPANNED = 1
FAR_END = 2


def grid_shape(case, construction):
    sides = [maximum - minimum + 1 for minimum, maximum in case.bounding_box]
    if construction == TOP_CELLS:
        return tuple(sides)
    return tuple(2 * side + 1 for side in sides)


def cell_count(case, construction):
    """The cells of the complex the tool builds from the grid."""
    sides = grid_shape(case, construction)
    if construction == TOP_CELLS:
        return prod(2 * side + 1 for side in sides)
    return prod(2 * side - 1 for side in sides)


def absent_value(case):
    _, grades, _ = cases.read_canonical(case.path, case.columns)
    return absent_value_of(grades)


def absent_value_of(grades):
    return 1 if grades is None else int(grades.max()) + 1


def top_cell_values(case):
    """The T-construction grid: the cube's grade, or 0 on an ungraded case, at
    every position of the bounding box a cube is listed at, and the absent value
    at every other position."""
    coordinates, grades, _ = cases.read_canonical(case.path, case.columns)
    values = numpy.full(
        grid_shape(case, TOP_CELLS), absent_value_of(grades), dtype=numpy.float64
    )
    positions = coordinates - box_minima(case)
    values[tuple(positions.T)] = 0.0 if grades is None else grades
    return values


def doubled_vertex_values(case):
    """The V-construction grid: every face of every listed cell takes the least
    grade among the cells it is a face of, or 0 on an ungraded case, at its own
    point of the doubled lattice, and every point no cell reaches takes the
    absent value."""
    coordinates, grades, extents = cases.read_canonical(case.path, case.columns)
    dimension = coordinates.shape[1]
    values = numpy.full(
        grid_shape(case, DOUBLED_VERTICES),
        absent_value_of(grades),
        dtype=numpy.float64,
    )
    bases = 2 * (coordinates - box_minima(case))
    if extents is None:
        extents = numpy.full(coordinates.shape[0], (1 << dimension) - 1)
    for mask in numpy.unique(extents):
        listed = extents == mask
        offsets = face_offsets(int(mask), dimension)
        points = (bases[listed][:, None, :] + offsets).reshape(-1, dimension)
        if grades is None:
            values[tuple(points.T)] = 0.0
        else:
            spread = numpy.repeat(grades[listed], offsets.shape[0])
            numpy.minimum.at(values, tuple(points.T), spread)
    return values


def face_offsets(extent, dimension):
    """Where the faces of a cell of this extent sit in doubled coordinates,
    relative to the cell's own base: along an axis the cell spans, a face either
    spans it too or takes one of its two ends, and along an axis the cell does
    not span, every face sits where the cell does."""
    axes = [
        (NEAR_END, SPANNED, FAR_END) if extent >> axis & 1 else (NEAR_END,)
        for axis in range(dimension)
    ]
    return numpy.array(list(itertools.product(*axes)), dtype=numpy.int64)


def box_minima(case):
    return numpy.array([minimum for minimum, _ in case.bounding_box])
