"""pyCHomP2 on one canonical case file: one JSON line out.

The pychomp engine builds nothing from a list of cubes. Its only constructor
takes a box, the grid counts along each axis, and fills it with 2^d cells per
box position, identifying the far side of the box with the near side. The
engine drops the last layer of each axis as a fringe, so a case reaches it as
the case's bounding box padded by one along every axis, with the listed cubes
shifted to start at 0 and a value on every cell. A cell takes the least grade
among the listed cubes in its star, and a cell with no listed cube in its star
takes the absent value, one above the largest grade in the case, which keeps
the empty part of the box out of the answer. The values are given per top cube
to the engine's own `construct_grading`, which takes the least grade over the
top cubes in a cell's star in C++. An ungraded case is that same construction
with grade 0 on every listed cube, and its Betti numbers are the connection
matrix's cell counts at grade 0, where no boundary entry stays within grade 0.

On a graded case those cell counts are not bar counts: they count the cells
that end a bar alongside the cells that start one. The bars come from reducing
the connection matrix's boundary here, which pairs each cell with the bar it
ends. A bar whose death is the absent value dies outside the case and so never
dies, and a bar born at the absent value is not in the case at all.

The engine works over the integers modulo 2 only, so `--modulus` states the
field of the run rather than choosing it.

Invoked as

    tools-python pychomp2_run.py <case file> --columns <layout> --modulus 2

with `--columns` either `plain` or `graded`. One JSON line goes to standard
output, `{"betti": [...]}` on an ungraded case and `{"bar_counts": [...]}` on a
graded one, with one entry per dimension from 0 to the ambient dimension.
"""

import argparse
import json

from pychomp import ConnectionMatrix, CubicalComplex, GradedComplex, construct_grading

PADDING = 1


def read_canonical(path, columns):
    """The cubes of a canonical case file and the grade of each, every grade 0
    on an ungraded case."""
    cubes = []
    grades = []
    with open(path) as handle:
        for line in handle:
            fields = line.strip().split(",")
            grades.append(int(fields.pop()) if columns == "graded" else 0)
            cubes.append([int(field) for field in fields])
    return cubes, grades


def connection_matrix(cubes, grades, absent_grade):
    """The connection matrix of the padded box graded by the listed cubes."""
    dimension = len(cubes[0])
    minima = [min(cube[axis] for cube in cubes) for axis in range(dimension)]
    maxima = [max(cube[axis] for cube in cubes) for axis in range(dimension)]
    box = [maxima[axis] - minima[axis] + 1 + PADDING for axis in range(dimension)]
    complex_of_box = CubicalComplex(box)
    top_shape = 2**dimension - 1
    grade_of_cube = {}
    for cube, grade in zip(cubes, grades):
        position = [cube[axis] - minima[axis] for axis in range(dimension)]
        grade_of_cube[complex_of_box.cell_index(position, top_shape)] = grade

    def top_cube_grade(cell):
        return grade_of_cube.get(cell, absent_grade)

    grading = construct_grading(complex_of_box, top_cube_grade)
    return ConnectionMatrix(GradedComplex(complex_of_box, grading))


def bars(connection):
    """Pair the connection matrix's cells into bars, each a triple of dimension,
    birth grade and death grade, with the death `None` where the bar never dies.
    """
    reduced = connection.complex()
    dimension_of = {}
    for cell_dimension in range(reduced.dimension() + 1):
        for cell in reduced(cell_dimension):
            dimension_of[cell] = cell_dimension
    grade_of = {cell: connection.value(cell) for cell in dimension_of}
    order = sorted(
        dimension_of, key=lambda cell: (grade_of[cell], dimension_of[cell], cell)
    )
    position_of = {cell: position for position, cell in enumerate(order)}
    columns = {}
    claimed_by = {}
    for position, cell in enumerate(order):
        column = {position_of[face] for face in reduced.boundary({cell})}
        while column:
            lowest = max(column)
            if lowest not in claimed_by:
                break
            column ^= columns[claimed_by[lowest]]
        if column:
            columns[position] = column
            claimed_by[max(column)] = position
    paired = []
    for lowest, position in claimed_by.items():
        paired.append(
            (
                dimension_of[order[lowest]],
                grade_of[order[lowest]],
                grade_of[order[position]],
            )
        )
    ending = set(claimed_by.values())
    for position, cell in enumerate(order):
        if position in claimed_by or position in ending:
            continue
        paired.append((dimension_of[cell], grade_of[cell], None))
    return paired


def bar_counts(connection, absent_grade, dimension):
    """One count per dimension of the bars the case has: a bar born at the
    absent value is outside the case, and a bar dying there never dies."""
    counts = [0] * (dimension + 1)
    for cell_dimension, birth, death in bars(connection):
        if birth >= absent_grade:
            continue
        if death is None or death >= absent_grade or birth < death:
            counts[cell_dimension] += 1
    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("case")
    parser.add_argument("--columns", required=True)
    parser.add_argument("--modulus", type=int, required=True)
    arguments = parser.parse_args()
    cubes, grades = read_canonical(arguments.case, arguments.columns)
    dimension = len(cubes[0])
    absent_grade = max(grades) + 1
    connection = connection_matrix(cubes, grades, absent_grade)
    if arguments.columns == "graded":
        answer = {"bar_counts": bar_counts(connection, absent_grade, dimension)}
    else:
        answer = {"betti": connection.count()[0]}
    print(json.dumps(answer))


main()
