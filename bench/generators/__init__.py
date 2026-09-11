"""The case generators, by name.

A manifest case that carries a `generator` key names one of these; `bench
generate` looks it up here and calls it with the case's name, seed, parameters
and the directory the case file belongs in.
"""

from bench.generators import curves, gradings, manifolds, random_cubes

GENERATORS = {
    "s1": manifolds.s1,
    "torus": manifolds.torus,
    "ball": manifolds.ball,
    "sphere": manifolds.sphere,
    "sphere_top": manifolds.sphere_top,
    "random_top": random_cubes.random_top,
    "random_mixed": random_cubes.random_mixed,
    "curve": curves.curve,
    "sweep": gradings.sweep,
    "random_grades": gradings.random_grades,
}
