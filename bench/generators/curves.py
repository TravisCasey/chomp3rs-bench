"""The random thickened curve: a closed curve of a few Fourier modes, sampled
along its length and floored to the cubes it passes through.

The generator takes the case name, the seed, the parameters the manifest holds
and the directory to write into, and writes `<name>.csv` and `<name>.json`
there. The name under which it is called is a key of
`bench.generators.GENERATORS`.

Under `tangent_bundle` the curve lives in half the ambient dimension and every
sample is paired with the unit tangent there scaled to a fixed radius, the
embedding the dissipative flow covers use. The curve is scaled so that
consecutive samples are a mean of 0.45 apart, measured on the embedded points,
and then resampled by inserting points so that no consecutive pair is further
apart than that. A gap below the cube side makes consecutive cubes meet, so the
cover is a connected tube around a closed curve. The sidecar records the Betti
numbers of a circle, which hold where the tube does not touch itself; a case
where it does is caught by the correctness check as a disagreement with the
sidecar. Every random draw comes from `numpy.random.default_rng(seed)`, so a
case is the same file every time it is generated.
"""

from math import pi

import numpy

from bench.generators.manifolds import floor_to_cubes, write_case

GAP = 0.45
TANGENT_RADIUS = 3.5
BISECTION_STEPS = 60


def curve(name, seed, parameters, output_directory):
    dimension = parameters["dimension"]
    modes = parameters["modes"]
    samples = parameters["samples"]
    tangent_bundle = parameters["tangent_bundle"]
    generator = numpy.random.default_rng(seed)
    curve_dimension = dimension // 2 if tangent_bundle else dimension
    cosine_coefficients = generator.standard_normal((modes, curve_dimension))
    sine_coefficients = generator.standard_normal((modes, curve_dimension))
    harmonics = numpy.arange(1, modes + 1)
    phases = numpy.outer(2.0 * pi * numpy.arange(samples) / samples, harmonics)
    positions = (
        numpy.cos(phases) @ cosine_coefficients
        + numpy.sin(phases) @ sine_coefficients
    )
    if tangent_bundle:
        velocities = (
            (-numpy.sin(phases) * harmonics) @ cosine_coefficients
            + (numpy.cos(phases) * harmonics) @ sine_coefficients
        )
        lengths = numpy.linalg.norm(velocities, axis=1, keepdims=True)
        directions = TANGENT_RADIUS * velocities / lengths
    else:
        directions = numpy.zeros((samples, 0))
    scale = curve_scale(positions, directions)
    points = resampled(numpy.concatenate([scale * positions, directions], axis=1))
    assert step_lengths(points).max() < 1.0
    write_case(
        output_directory / f"{name}.csv",
        floor_to_cubes(points),
        None,
        "curve",
        "curve",
        seed,
        parameters,
        [1, 1] + [0] * (dimension - 1),
    )


def curve_scale(positions, directions):
    """The factor on the curve that puts the mean gap between consecutive
    embedded points at `GAP`.

    The tangent half of an embedding does not move with the factor, so the mean
    gap is not proportional to it, but it does grow with it, and a bisection
    finds the factor.
    """
    position_steps = step_lengths(positions)
    direction_steps = step_lengths(directions)

    def mean_gap(factor):
        return numpy.hypot(factor * position_steps, direction_steps).mean()

    low = 0.0
    high = 1.0
    while mean_gap(high) < GAP:
        high *= 2.0
    for _ in range(BISECTION_STEPS):
        middle = 0.5 * (low + high)
        if mean_gap(middle) < GAP:
            low = middle
        else:
            high = middle
    return high


def step_lengths(points):
    return numpy.linalg.norm(numpy.diff(closed(points), axis=0), axis=1)


def closed(points):
    """The points with the first repeated at the end, so that the step from the
    last sample back to the first counts as one of the curve's steps."""
    return numpy.concatenate([points, points[:1]])


def resampled(points):
    """The points with enough inserted along each step that no step is longer
    than `GAP`."""
    loop = closed(points)
    pieces = []
    for index, length in enumerate(step_lengths(points)):
        steps = max(1, int(numpy.ceil(length / GAP)))
        fractions = numpy.arange(steps) / steps
        step = loop[index + 1] - loop[index]
        pieces.append(loop[index] + numpy.outer(fractions, step))
    return numpy.concatenate(pieces)
