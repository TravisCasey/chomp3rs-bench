# Dissipative flow covers

Cubical covers of chaotic trajectories from four dissipative systems, in
ambient dimensions 6 through 16. Each file is one benchmark case: one line
per top cube, comma-separated integer coordinates of the cube's base orthant,
deduplicated and in lexicographic order, no header.

## Files

| File | Ambient dim | Cubes | Box size |
| --- | --- | --- | --- |
| `lorenz_d6_box5.csv` | 6 | 788 | 5.0 |
| `lorenz_d6_box2.5.csv` | 6 | 1,781 | 2.5 |
| `lorenz_d6_box1.25.csv` | 6 | 4,758 | 1.25 |
| `lorenz_d6_box0.5.csv` | 6 | 21,425 | 0.5 |
| `lorenz_d6_box0.25.csv` | 6 | 74,129 | 0.25 |
| `lorenz_d6_box0.125.csv` | 6 | 268,329 | 0.125 |
| `dadras_d8_box24.csv` | 8 | 4,057 | 24.0 |
| `dadras_d8_box12.csv` | 8 | 9,019 | 12.0 |
| `dadras_d8_box6.csv` | 8 | 23,631 | 6.0 |
| `dadras_d8_box3.csv` | 8 | 83,404 | 3.0 |
| `charney_devore_d12_box0.05.csv` | 12 | 12,839 | 0.05 |
| `charney_devore_d12_box0.04.csv` | 12 | 16,800 | 0.04 |
| `charney_devore_d12_box0.03.csv` | 12 | 24,735 | 0.03 |
| `charney_devore_d12_box0.02.csv` | 12 | 44,798 | 0.02 |
| `charney_devore_d12_box0.01.csv` | 12 | 143,295 | 0.01 |
| `kuramoto_sivashinsky_d16_box1.csv` | 16 | 20,250 | 1.0 |
| `kuramoto_sivashinsky_d16_box0.5.csv` | 16 | 26,740 | 0.5 |
| `kuramoto_sivashinsky_d16_box0.25.csv` | 16 | 46,733 | 0.25 |
| `kuramoto_sivashinsky_d16_box0.125.csv` | 16 | 87,903 | 0.125 |

The files of each system are one trajectory read at several resolutions, so
each system forms a size ladder with everything else held fixed: the flow,
the sampling and the embedding are identical, and only the box size moves.
The Kuramoto-Sivashinsky trajectory is 30,000 samples spaced 0.2 apart along
the curve, in the eight leading principal components of the field on a
periodic domain of length 22. Its samples are already closer together than
the resampling bound at box sizes of 0.5 and above, where the cube count
follows the sample count rather than the box size, which is why its ladder
runs at finer boxes than its extent alone would suggest.

## Construction

Each system is integrated to a trajectory in its state space, then embedded
in its sphere bundle: every point is paired with the unit tangent at that
point, scaled to a fixed radius of 3.5, doubling the dimension. Positions are
divided by the box size first, so the topology layer sees a space tiled by
cubes of side 1. The embedded curve is resampled so that consecutive points
are at most 0.45 apart, below the cube side, which makes consecutive cubes
adjacent and the cover a connected tube around the curve rather than a
dotted line. Each resampled point is floored componentwise to the cube
containing it.

The position half of each file spans a box that grows as the box size
shrinks; for Charney-DeVore it runs from 6 x 11 x 11 x 12 x 20 x 18 cubes at
box size 0.05 to 24 x 49 x 53 x 55 x 94 x 84 at 0.01. The direction half
lies on a sphere of fixed radius and so spans at most 8 cubes per axis in
every file. The covers are therefore sparse in their bounding boxes, and
increasingly so with dimension.
