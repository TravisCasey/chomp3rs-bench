"""DIPHA: an explicit boundary matrix in, a binary persistence diagram out.

The conversion lists the closure of the case's cells and nothing else. A cell is
named by its position in doubled coordinates: the face of a listed cell with
base orthant `b` sits at `2 * b + o`, for an offset `o` of 0, 1 or 2 along every
axis the cell spans and 0 along every axis it does not. A position's dimension
is the number of its odd coordinates, and its boundary is the two positions one
step either way along each odd axis. Every face of every listed cell is written
once, taking the least grade among the listed cells it is a face of, or 0 on an
ungraded case. The cost therefore follows the cells of the case rather than its
bounding box, and mixed-dimension cases are read as they are.

Positions are sorted and looked up as keys of whole 64-bit words. Each axis's
doubled coordinate takes as many bits as the case's bounding box needs, a field
that does not fit the rest of a word starts the next one, and a key has as many
words as that takes, so a box of any size and dimension has a key that cannot
overflow.

The input file is binary, every integer a little-endian 64-bit integer and every
value a double: the magic number, the type that marks a weighted boundary
matrix, 0 for a boundary rather than a coboundary matrix, the number of cells,
the ambient dimension, then per cell its dimension, per cell its value, per cell
the offset at which its boundary entries start, the number of entries, and the
entries, each the index of a face. The tool orders the cells by value, then
dimension, then index, and no face has a larger value than a cell it bounds, so
every face comes before the cells it bounds. One isolated vertex follows the
closure at the absent value, one above the largest grade in the case and 1
where the case carries no grade, so that the largest value in the complex is
never a grade of the case.

The output file is binary too: the magic number, the type that marks a
persistence diagram, the number of bars, and then per bar a dimension, a birth
and a death. A bar that never dies is written with its dimension negated and
shifted, as -k - 1 for dimension k, and its death set to the largest value in
the complex rather than to any infinity. The tool drops three kinds of bar
before it writes: one whose birth equals its death, one born at the largest
value in the complex, and one that never dies at the ambient dimension. The
second removes only the appended vertex, and a set of cells in d dimensions has
no homology at dimension d, so none of them is a bar of the case.

It computes over the integers modulo 2 only, with no option to choose the field.
The command line takes an optional `--upper_dim`, which yields bars only below
the dimension given; the run passes none of it and takes the default, which
computes every dimension. The program is run through `mpiexec -n 1`, the one
rank the run's configuration asks for.

The skip rule bounds the memory of the conversion and of the tool from the
sidecar alone, without listing the closure. The conversion holds one key for
every face of every listed cell before merging the faces cells share, `3^d` for
a top cube, at 8 bytes per key word and 2 more per key, and then about 40 bytes
per closure cell. The closure has no more cells than those keys and no more
than the whole doubled bounding box, `(2n + 1)^d` positions for a box of side
n, and no more boundary entries than either of those two complexes has. The
tool takes about 94 bytes per closure cell and 13 per boundary entry. Each
figure has a fixed baseline beside it, and all of them were measured on cases
of dimensions 3 to 8.
"""

import itertools
from math import prod
from pathlib import Path

import numpy

from bench import cases, dense
from bench.adapters import CASES_MOUNT, OUTPUT_MOUNT

NAME = "dipha"
TRACKS = {"homology", "persistence"}
ACCEPTS_MIXED_DIMENSION = True
MAXIMUM_DIMENSION = None
COEFFICIENTS = "Z/2"
BYTES_PER_CELL = None
CONSTRUCTION = None
VERSION = "commit 0b874769fbd092c07a12cebc2459adb02117c2fd"
CONVERTED_DIRECTORY = Path("cases/converted/dipha")
COMPLEX_SUFFIX = ".complex"
DIAGRAM_SUFFIX = ".diagram"
PARTIAL_SUFFIX = ".part"
MAGIC = 8067171840
WEIGHTED_BOUNDARY_MATRIX = 0
BOUNDARY = 0
INTEGER = "<i8"
VALUE = "<f8"
WORD = ">u8"
WORD_BITS = 64
FIELD_BYTES = 8
DIAGRAM_HEADER_FIELDS = 3
BAR = numpy.dtype([("dimension", INTEGER), ("birth", VALUE), ("death", VALUE)])
HOMOLOGY_TRACK = "homology"
PERSISTENCE_TRACK = "persistence"
RANKS = "1"
NEAR_END = 0
SPANNED = 1
FAR_END = 2
KEYS_PER_BLOCK = 1 << 22
CELLS_PER_BLOCK = 1 << 16
CONVERSION_BASELINE_BYTES = 64 * 1024**2
CONVERSION_BYTES_PER_KEY_BESIDES_WORDS = 2
CONVERSION_BYTES_PER_CELL = 40
TOOL_BASELINE_BYTES = 40 * 1024**2
TOOL_BYTES_PER_CELL = 94
TOOL_BYTES_PER_ENTRY = 13


def version():
    return VERSION


def convert(case):
    path = CONVERTED_DIRECTORY / (case.name + COMPLEX_SUFFIX)
    if path.exists() and path.stat().st_mtime >= case.path.stat().st_mtime:
        return path
    coordinates, grades, extents = cases.read_canonical(case.path, case.columns)
    dimension = coordinates.shape[1]
    fields, words = key_layout(case)
    keys = face_keys(2 * (coordinates - dense.box_minima(case)), grades, extents, fields, words)
    del coordinates, extents
    first = first_of_each_position(keys, words)
    cells = keys[first, :words]
    if grades is None:
        values = numpy.zeros(cells.shape[0], dtype=VALUE)
    else:
        values = keys[first, words].astype(VALUE)
    del keys, first
    dimensions = numpy.zeros(cells.shape[0], dtype=INTEGER)
    for word, shift in fields:
        dimensions += ((cells[:, word] >> numpy.uint64(shift)) & numpy.uint64(1)).astype(INTEGER)
    offsets = numpy.concatenate(([0], numpy.cumsum(2 * dimensions)))
    count = cells.shape[0] + 1
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(COMPLEX_SUFFIX + PARTIAL_SUFFIX)
    with partial.open("wb") as binary:
        header = [MAGIC, WEIGHTED_BOUNDARY_MATRIX, BOUNDARY, count, dimension]
        numpy.array(header, dtype=INTEGER).tofile(binary)
        numpy.append(dimensions, 0).astype(INTEGER).tofile(binary)
        del dimensions
        numpy.append(values, dense.absent_value_of(grades)).astype(VALUE).tofile(binary)
        del values
        offsets.astype(INTEGER).tofile(binary)
        numpy.array([offsets[-1]], dtype=INTEGER).tofile(binary)
        del offsets
        write_boundaries(binary, cells, fields, words)
    partial.replace(path)
    return path


def key_layout(case):
    """Where each axis's doubled coordinate sits in a position's key, as the
    word and the shift within it, and how many words the key takes."""
    fields = []
    word = 0
    free = WORD_BITS
    for minimum, maximum in case.bounding_box:
        width = (2 * (maximum - minimum) + FAR_END).bit_length()
        if width > free:
            word += 1
            free = WORD_BITS
        free -= width
        fields.append((word, free))
    return fields, word + 1


def packed(doubled, fields, words):
    """Doubled coordinates, one row per position, packed into key words."""
    result = numpy.zeros((doubled.shape[0], words), dtype=numpy.uint64)
    for axis, (word, shift) in enumerate(fields):
        result[:, word] |= doubled[:, axis].astype(numpy.uint64) << numpy.uint64(shift)
    return result


def face_keys(doubled_bases, grades, extents, fields, words):
    """One row per face of every listed cell, shared faces not yet merged: the
    position's key words, then on a graded case one more word holding the grade
    of the cell the face was taken from."""
    count, dimension = doubled_bases.shape
    if extents is None:
        extents = numpy.full(count, (1 << dimension) - 1)
    groups = [
        (numpy.flatnonzero(extents == mask), face_offsets(int(mask), dimension))
        for mask in numpy.unique(extents)
    ]
    width = words + (grades is not None)
    total = sum(listed.size * offsets.shape[0] for listed, offsets in groups)
    keys = numpy.empty((total, width), dtype=WORD)
    begin = 0
    for listed, offsets in groups:
        shifts = packed(offsets, fields, words)
        cells_per_block = max(1, KEYS_PER_BLOCK // offsets.shape[0])
        for block in range(0, listed.size, cells_per_block):
            chosen = listed[block : block + cells_per_block]
            end = begin + chosen.size * offsets.shape[0]
            rows = keys[begin:end].reshape(chosen.size, offsets.shape[0], width)
            bases = packed(doubled_bases[chosen], fields, words)
            rows[:, :, :words] = bases[:, None, :] + shifts[None, :, :]
            if grades is not None:
                rows[:, :, words] = grades[chosen][:, None]
            begin = end
    return keys


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


def first_of_each_position(keys, words):
    """Sort the rows in place, whole keys compared byte by byte, and mark the
    first row of every position, which on a graded case carries its least
    grade."""
    keys.view(f"V{keys.shape[1] * FIELD_BYTES}")[:, 0].sort()
    native = keys.view(numpy.uint64)
    first = numpy.zeros(keys.shape[0], dtype=bool)
    first[0] = True
    for word in range(words):
        first[1:] |= native[1:, word] != native[:-1, word]
    return first


def write_boundaries(binary, cells, fields, words):
    """Write the boundary entries of every cell in order: along each odd axis,
    the index of the position one step down and then of the one a step up."""
    haystack = cells.view(f"V{words * FIELD_BYTES}")[:, 0]
    for begin in range(0, cells.shape[0], CELLS_PER_BLOCK):
        block = cells[begin : begin + CELLS_PER_BLOCK].astype(numpy.uint64)
        spans = numpy.empty((block.shape[0], len(fields)), dtype=bool)
        faces = numpy.empty((block.shape[0], len(fields), 2, words), dtype=numpy.uint64)
        for axis, (word, shift) in enumerate(fields):
            step = numpy.zeros(words, dtype=numpy.uint64)
            step[word] = numpy.uint64(1) << numpy.uint64(shift)
            spans[:, axis] = (block[:, word] >> numpy.uint64(shift)) & numpy.uint64(1)
            faces[:, axis, 0] = block - step
            faces[:, axis, 1] = block + step
        queries = numpy.ascontiguousarray(faces[spans].reshape(-1, words), dtype=WORD)
        needles = queries.view(f"V{words * FIELD_BYTES}")[:, 0]
        numpy.searchsorted(haystack, needles).astype(INTEGER).tofile(binary)


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


def closure_bounds(case):
    """Upper bounds, from the sidecar alone, on the face keys the conversion
    holds, the cells of the closure and its boundary entries."""
    dimension = case.ambient_dimension
    keys = case.cube_count * 3**dimension
    box_cells = dense.cell_count(case)
    box_entries = sum(
        2 * (maximum - minimum + 1) * box_cells // (2 * (maximum - minimum) + 3)
        for minimum, maximum in case.bounding_box
    )
    cube_entries = case.cube_count * 2 * dimension * 3 ** (dimension - 1)
    return keys, min(keys, box_cells), min(cube_entries, box_entries)


def skip_reason(case, config, memory_limit_bytes):
    keys, cells, entries = closure_bounds(case)
    words = key_layout(case)[1] + case.graded
    conversion = (
        CONVERSION_BASELINE_BYTES
        + keys * (words * FIELD_BYTES + CONVERSION_BYTES_PER_KEY_BESIDES_WORDS)
        + cells * CONVERSION_BYTES_PER_CELL
    )
    tool = (
        TOOL_BASELINE_BYTES
        + cells * TOOL_BYTES_PER_CELL
        + entries * TOOL_BYTES_PER_ENTRY
    )
    gigabytes = memory_limit_bytes // 1024**3
    if conversion > memory_limit_bytes:
        return (
            f"conversion holding {keys} face keys of {words} words needs about"
            f" {conversion / 1024**3:.1f} GB, over the {gigabytes} GB cap"
        )
    if tool > memory_limit_bytes:
        return (
            f"explicit complex of up to {cells} cells and {entries} boundary"
            f" entries needs about {tool / 1024**3:.1f} GB, over the"
            f" {gigabytes} GB cap"
        )
    return None
