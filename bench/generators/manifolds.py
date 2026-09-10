"""The parametric manifold generators: a circle, a 2-torus, a solid ball and
the boundary of the cube, each with closed-form Betti numbers.

A generator takes the case name, the seed, the parameters the manifest holds
and the directory to write into, and writes `<name>.csv` and `<name>.json`
there. The names under which they are called are the keys of
`bench.generators.GENERATORS`.

The circle and the torus are embedded into the ambient dimension by a random
orthonormal basis, so the cubes they occupy are not aligned with the grid in
any special way; every random draw comes from `numpy.random.default_rng(seed)`,
so a case is the same file every time it is generated.
"""

from math import pi

import numpy

from bench.cases import write_canonical, write_sidecar


def s1(name, seed, parameters, output_directory):
    """A circle, sampled about one unit apart and thickened into a tube."""
    dimension = parameters["dimension"]
    samples = parameters["samples"]
    plane = random_basis(dimension, seed)[:, :2]
    angles = 2.0 * pi * numpy.arange(samples) / samples
    radius = samples / (2.0 * pi)
    points = radius * (
        numpy.outer(numpy.cos(angles), plane[:, 0])
        + numpy.outer(numpy.sin(angles), plane[:, 1])
    )
    coordinates = thicken(floor_to_cubes(points))
    write_case(
        output_directory / f"{name}.csv",
        coordinates,
        None,
        "s1",
        "s1",
        seed,
        parameters,
        [1, 1] + [0] * (dimension - 1),
    )


def torus(name, seed, parameters, output_directory):
    """The surface of a 2-torus, sampled fine enough to need no thickening."""
    dimension = parameters["dimension"]
    samples_per_circle = parameters["samples_per_circle"]
    major_radius = parameters["major_radius"]
    minor_radius = parameters["minor_radius"]
    spacing = 2.0 * pi * (major_radius + minor_radius) / samples_per_circle
    assert spacing < 1.0
    basis = random_basis(dimension, seed)
    angles = 2.0 * pi * numpy.arange(samples_per_circle) / samples_per_circle
    major_angle, minor_angle = numpy.meshgrid(angles, angles, indexing="ij")
    major_angle = major_angle.ravel()
    minor_angle = minor_angle.ravel()
    ring_radius = major_radius + minor_radius * numpy.cos(minor_angle)
    points = (
        numpy.outer(ring_radius * numpy.cos(major_angle), basis[:, 0])
        + numpy.outer(ring_radius * numpy.sin(major_angle), basis[:, 1])
        + numpy.outer(minor_radius * numpy.sin(minor_angle), basis[:, 2])
    )
    write_case(
        output_directory / f"{name}.csv",
        floor_to_cubes(points),
        None,
        "torus",
        "torus",
        seed,
        parameters,
        [1, 2, 1] + [0] * (dimension - 2),
    )


def ball(name, seed, parameters, output_directory):
    dimension = parameters["dimension"]
    radius = parameters["radius"]
    side = 2 * radius + 1
    coordinates = numpy.indices((side,) * dimension).reshape(dimension, -1).T - radius
    write_case(
        output_directory / f"{name}.csv",
        coordinates,
        None,
        "ball",
        "ball",
        seed,
        parameters,
        [1] + [0] * dimension,
    )


def sphere(name, seed, parameters, output_directory):
    """The boundary of the unit cube, as its 2d facets of dimension d - 1."""
    dimension = parameters["dimension"]
    full_mask = (1 << dimension) - 1
    coordinates = []
    extents = []
    for axis in range(dimension):
        for value in (0, 1):
            orthant = [0] * dimension
            orthant[axis] = value
            coordinates.append(orthant)
            extents.append(full_mask ^ (1 << axis))
    write_case(
        output_directory / f"{name}.csv",
        numpy.array(coordinates, dtype=numpy.int64),
        numpy.array(extents, dtype=numpy.uint32),
        "sphere",
        "sphere",
        seed,
        parameters,
        [1] + [0] * (dimension - 2) + [1, 0],
    )


def sphere_top(name, seed, parameters, output_directory):
    """The same sphere as top cubes: a hollow box with its interior removed."""
    dimension = parameters["dimension"]
    side = parameters["side"]
    box = numpy.indices((side,) * dimension).reshape(dimension, -1).T
    interior = ((box >= 1) & (box < side - 1)).all(axis=1)
    write_case(
        output_directory / f"{name}.csv",
        box[~interior],
        None,
        "sphere",
        "sphere_top",
        seed,
        parameters,
        [1] + [0] * (dimension - 2) + [1, 0],
    )


def random_basis(dimension, seed):
    generator = numpy.random.default_rng(seed)
    basis, _ = numpy.linalg.qr(generator.standard_normal((dimension, dimension)))
    return basis


def floor_to_cubes(points):
    """Take the cube each sampled point lies in, once each."""
    return numpy.unique(numpy.floor(points).astype(numpy.int64), axis=0)


def thicken(coordinates):
    """Add the cubes one step away along each axis, in both directions.

    This is the ball of radius 1 in the L1 metric. The L-infinity ball of the
    same radius would hold 3^d cubes around each of them, which is more than a
    case can carry above a handful of dimensions; the L1 ball joins two cubes
    that meet at a corner just as the larger one does, so the thickened circle
    is a connected tube either way.
    """
    dimension = coordinates.shape[1]
    identity = numpy.identity(dimension, dtype=numpy.int64)
    steps = numpy.concatenate(
        [numpy.zeros((1, dimension), dtype=numpy.int64), identity, -identity]
    )
    thickened = (coordinates[:, None, :] + steps[None, :, :]).reshape(-1, dimension)
    return numpy.unique(thickened, axis=0)


def write_case(path, coordinates, extents, family, generator, seed, parameters, betti):
    write_canonical(path, coordinates, extents=extents)
    write_sidecar(
        path,
        columns="extent" if extents is not None else "plain",
        family=family,
        source={
            "kind": "generated",
            "generator": generator,
            "seed": seed,
            "parameters": parameters,
        },
        betti=betti,
    )
