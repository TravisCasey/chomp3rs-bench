"""The random cubical sets: a box of top cubes kept independently, and a list
of maximal cubes of mixed dimension placed at random in a box.

A generator takes the case name, the seed, the parameters the manifest holds
and the directory to write into, and writes `<name>.csv` and `<name>.json`
there. The names under which they are called are the keys of
`bench.generators.GENERATORS`.

Neither family has a closed-form answer, so neither sidecar carries one: the
correctness check decides these cases by the tools agreeing with each other.
Every random draw comes from `numpy.random.default_rng(seed)`, so a case is the
same file every time it is generated.
"""

import numpy

from bench.generators.manifolds import write_case


def random_top(name, seed, parameters, output_directory):
    """Every top cube of a box, kept independently with a fixed probability."""
    dimension = parameters["dimension"]
    side = parameters["side"]
    probability = parameters["probability"]
    generator = numpy.random.default_rng(seed)
    box = numpy.indices((side,) * dimension).reshape(dimension, -1).T
    kept = generator.random(box.shape[0]) < probability
    write_case(
        output_directory / f"{name}.csv",
        box[kept],
        None,
        "random_top",
        "random_top",
        seed,
        parameters,
        None,
    )


def random_mixed(name, seed, parameters, output_directory):
    """Cubes of mixed dimension at random places in a box, keeping the maximal.

    Each cube takes a dimension drawn uniformly from the range the parameters
    give, the axes it spans drawn uniformly among the sets of axes of that
    size, and a base orthant uniform in the box. Cubes drawn twice are dropped
    to one, and then every cube that is a face of another listed cube is
    dropped, so what is written is the maximal cells of the set the draw named.
    """
    dimension = parameters["dimension"]
    side = parameters["side"]
    count = parameters["count"]
    minimum_cube_dimension = parameters["minimum_cube_dimension"]
    maximum_cube_dimension = parameters["maximum_cube_dimension"]
    generator = numpy.random.default_rng(seed)
    bases = generator.integers(0, side, size=(count, dimension))
    cube_dimensions = generator.integers(
        minimum_cube_dimension, maximum_cube_dimension + 1, size=count
    )
    spans = numpy.zeros((count, dimension), dtype=bool)
    for index in range(count):
        axes = generator.permutation(dimension)[: cube_dimensions[index]]
        spans[index, axes] = True
    bases, spans = without_duplicates(bases, spans)
    bases, spans = without_faces(bases, spans)
    write_case(
        output_directory / f"{name}.csv",
        bases,
        extent_masks(spans),
        "random_mixed",
        "random_mixed",
        seed,
        parameters,
        None,
    )


def without_duplicates(bases, spans):
    _, first = numpy.unique(
        numpy.concatenate([bases, spans], axis=1), axis=0, return_index=True
    )
    kept = numpy.sort(first)
    return bases[kept], spans[kept]


def without_faces(bases, spans):
    kept = numpy.array(
        [is_maximal(index, bases, spans) for index in range(bases.shape[0])]
    )
    return bases[kept], spans[kept]


def is_maximal(index, bases, spans):
    """Whether the cube at `index` is a face of no other cube in the list.

    A cube is a face of another when it spans a subset of the other's axes and
    lies on it: where the face spans an axis it sits exactly where the other
    cube does, where only the other cube spans an axis the face sits at either
    end of it, and where neither spans an axis the two sit at the same place.
    """
    span = spans[index]
    offset = bases[index] - bases
    spanned_subset = (spans | ~span).all(axis=1)
    lies_on = numpy.where(
        spans & ~span, (offset == 0) | (offset == 1), offset == 0
    ).all(axis=1)
    faces = spanned_subset & lies_on
    faces[index] = False
    return not faces.any()


def extent_masks(spans):
    dimension = spans.shape[1]
    weights = 1 << numpy.arange(dimension, dtype=numpy.uint32)
    return (spans * weights).sum(axis=1).astype(numpy.uint32)
