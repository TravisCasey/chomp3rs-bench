"""The dense grid a tool builds from a case: its shape, its cost and its values.

A tool that takes a grid rather than a list of cubes takes it in the
T-construction: the values sit on top-dimensional cells, one per position of
the case's bounding box, which is the complex a list of closed top cubes already
means.

A position of the grid that no listed cube reaches takes the absent value, one
above the largest grade in the case and 1 where the case carries no grade. That
value arrives last in the filtration, so the empty part of the box stays out of
the answer and a bar dying there has not died inside the case.

`cell_count` is what a dense adapter's `skip_reason` measures a case by: the
cells of the complex the tool builds, one cell per position of a grid of side
`2n + 1` per axis, the closure of the top cells.

`top_cell_values` reads every listed cube as a top cube, and a mixed-dimension
case has no such grid; the adapters of those tools skip such a case.
"""

from math import prod

import numpy

from bench import cases


def grid_shape(case):
    return tuple(maximum - minimum + 1 for minimum, maximum in case.bounding_box)


def cell_count(case):
    """The cells of the complex the tool builds from the grid."""
    return prod(2 * side + 1 for side in grid_shape(case))


def absent_value(case):
    _, grades, _ = cases.read_canonical(case.path, case.columns)
    return absent_value_of(grades)


def absent_value_of(grades):
    return 1 if grades is None else int(grades.max()) + 1


def top_cell_values(case):
    """The grid: the cube's grade, or 0 on an ungraded case, at every position
    of the bounding box a cube is listed at, and the absent value at every other
    position."""
    coordinates, grades, _ = cases.read_canonical(case.path, case.columns)
    values = numpy.full(grid_shape(case), absent_value_of(grades), dtype=numpy.float64)
    positions = coordinates - box_minima(case)
    values[tuple(positions.T)] = 0.0 if grades is None else grades
    return values


def box_minima(case):
    return numpy.array([minimum for minimum, _ in case.bounding_box])
