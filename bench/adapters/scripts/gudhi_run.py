"""GUDHI on one dense grid of top cells: one JSON line out.

GUDHI is a Python module and installs no program, so the run calls it through
this script. The grid arrives as a `.npy` array holding one value per top cube
position of the case's bounding box: the cube's grade where a cube is listed, 0
on an ungraded case, and the absent value, one above the largest grade in the
case, where no cube is listed. `top_dimensional_cells=` is the T-construction,
which is the complex a list of closed top cubes means; the alternative
`vertices=` puts the values on the grid's vertices instead and separates two
cubes that meet only at a corner.

The Betti numbers come from `persistent_betti_numbers(0, 0)`, the ranks of the
classes born at or before 0 and alive after it, and not from `betti_numbers()`,
which its own documentation says always returns [1, 0, 0, ...] because cubes at
infinite filtration value are not removed from the complex. The list runs from
dimension 0 to the ambient dimension, one entry longer than the case has
dimensions.

The bars come from `persistence`, which returns a pair of dimension and birth
and death per bar, with `inf` as the death of a bar that never dies. Its default
`min_persistence` of 0.0 drops every bar whose death does not exceed its birth,
which is what the case is worth: with `min_persistence=-1.0` every cell whose
birth equals its death returns a bar of its own. A death at the absent value is
not a death in the case, since that value is the moment the part of the box with
no listed cube arrives, so such a bar never dies; a bar born at the absent value
is outside the case. Every bar left is one of the case's, whether it dies inside
the case or never, so the birth is the whole of the rule.

`--modulus` chooses the coefficient field, which must be prime, and is the one
argument of `persistence` the suite sets.

Invoked as

    tools-python gudhi_run.py <grid file> --modulus 2 --absent-value <n> [--graded]

with `--graded` where the case carries grades. One JSON line goes to standard
output, `{"betti": [...]}` on an ungraded case and `{"bar_counts": [...]}` on a
graded one, with one entry per dimension from 0 to the ambient dimension.
"""

import argparse
import json

import gudhi
import numpy


def bar_counts(pairs, absent_value, dimension):
    """One count per dimension of the bars the case has: a bar born at the
    absent value is outside the case, and every other bar the tool returns is
    one of the case's, dying inside it or, where its death is the absent value
    or infinite, never."""
    counts = [0] * (dimension + 1)
    for bar_dimension, (birth, _) in pairs:
        if birth < absent_value:
            counts[bar_dimension] += 1
    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("grid")
    parser.add_argument("--modulus", type=int, required=True)
    parser.add_argument("--absent-value", type=int, required=True)
    parser.add_argument("--graded", action="store_true")
    arguments = parser.parse_args()
    grid = numpy.load(arguments.grid)
    cubical = gudhi.CubicalComplex(top_dimensional_cells=grid)
    pairs = cubical.persistence(homology_coeff_field=arguments.modulus)
    if arguments.graded:
        answer = {"bar_counts": bar_counts(pairs, arguments.absent_value, grid.ndim)}
    else:
        answer = {"betti": cubical.persistent_betti_numbers(0, 0)}
    print(json.dumps(answer))


main()
