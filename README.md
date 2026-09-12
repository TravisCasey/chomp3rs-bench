# chomp3rs-bench

A benchmark comparison of [chomp3rs](https://github.com/TravisCasey/CHomP3-rs),
a cubical homology engine for high-dimensional complexes given by their maximal
cubes, against other cubical homology programs on a common set of inputs.

The suite generates and converts inputs, runs every tool under one measurement
wrapper inside one container, checks that the tools agree on the answer, and
turns the results into tables and figures.

## Layout

`bench/` is the Python package that drives everything, `cases/` holds the
benchmark inputs and the manifest that lists them, and `docs/` holds the notes
on the tools being compared.

The package installs one command, which is run as
`uv run bench <subcommand> [tier]`, where the tier is `smoke`, `quick`,
`nightly` or `full` and names how much of the manifest to work through:

- `generate` writes the inputs that come from a seed and the sidecar file that
  records the shape of each case.
- `convert` writes each case in the input format of every tool that will read
  it.
- `run` measures every tool on every case the tier asks for.
- `check` compares the answers the tools gave.
- `summarize` turns the measurements into tables.
- `plot` turns them into figures.

## Building the image

Every tool the suite compares, and the driver that calls chomp3rs, is built once
inside one container image, each at the revision the `Containerfile` pins. From
the root of the repository:

```
podman build --network=host -t chomp3rs-bench .
```

The image records what it holds. To read the revision of every tool in it:

```
podman run --rm localhost/chomp3rs-bench cat /opt/tools/PINS
```

Each tool is on the image's `PATH` under `/opt/tools/bin`, the Python-hosted
tools are reached through the interpreter `tools-python`, and the repository
is mounted at `/work` when a case is run.

## Published image volumes

One family of cases comes from scanned and simulated volumes that earlier work
on cubical persistence measured. The volumes are the ones included in:

- H. Wagner, C. Chen and E. Vucini, "Efficient computation of persistent
  homology for cubical data", in Topological Methods in Data Analysis and
  Visualization II, Springer, 2012. Its table of timings covers Silicium,
  Fuel, Marschner-Lobb, Neghip, Hydrogene, Engine, Tooth, Aneurysm, Bonsai and
  Foot, all from the Volvis voxel data repository.
- N. Otter, M. A. Porter, U. Tillmann, P. Grindrod and H. A. Harrington, "A
  roadmap for the computation of persistent homology", EPJ Data Science 6:17,
  2017. Its one cubical benchmark is a 512 x 512 x 512 rotational angiography
  scan of a head with an aneurysm, which it calls vertebra and which it also
  took from Volvis.

The Volvis repository those papers cite no longer serves data. Every volume
they used is carried by the Open SciVis Datasets collection at
`http://klacansky.com/open-scivis-datasets/`, which credits Volvis as its
source. Each file sits at `<collection>/<name>/<name>_<grid>_<type>.raw` under
the archive name in the table below, as a raw array of little-endian values
with no header.

### How the volumes are licensed and used here

The collection states no licence, for itself or for any volume in it. Its one
request is that each dataset be cited so that its authors are credited. The
suite is arranged to respect that: the volumes are downloaded when a case is
generated, each download is checked against the sha512 hash the collection
publishes for it, and no volume and nothing derived from one is kept in this
repository. Every case records the URL it came from and that hash beside its
cubes, and each volume is credited below by the acknowledgement.

### From a volume to a case

A volume is a grid of intensities; a case is a list of cubes. Two numbers make
the one into the other, and both are recorded with the case.

The threshold decides which voxels are occupied: a voxel is occupied when its
value is at least the threshold. Each threshold below is chosen so that
between about 5 and 30 percent of the volume is occupied, which keeps the
material of interest and drops the air around it; the one volume that does not
allow such a threshold is noted where it appears.

The downsampling factor decides how fine the result is. The volume is cut into
blocks of that many voxels along each axis, and a block is occupied when any
voxel in it is occupied; each occupied block becomes one cube. Where an axis
does not divide by the factor, the voxels past the last whole block along it
are dropped, so a 41 voxel axis downsampled by 2 gives 20 blocks and the last
voxel is left out. A factor of 1 is the volume at full resolution. Every volume
enters twice, once downsampled and once at full resolution, so that the same
shape can be measured at two sizes.

| Dataset | Archive name | Grid | Threshold | Occupied | Factor |
| --- | --- | --- | --- | --- | --- |
| Silicium | `silicium` | 98 x 34 x 34 | 128 | 12% | 2 |
| Fuel | `fuel` | 64 x 64 x 64 | 1 | 5% | 2 |
| Marschner-Lobb | `marschner_lobb` | 41 x 41 x 41 | 224 | 11% | 2 |
| Neghip | `neghip` | 64 x 64 x 64 | 32 | 15% | 2 |
| Hydrogene | `hydrogen_atom` | 128 x 128 x 128 | 8 | 11% | 2 |
| Engine | `engine` | 256 x 256 x 128 | 144 | 5% | 2 |
| Tooth | `tooth` | 103 x 94 x 161 | 176 | 7% | 2 |
| Aneurysm | `aneurism` | 256 x 256 x 256 | 1 | 1% | 2 |
| Bonsai | `bonsai` | 256 x 256 x 256 | 128 | 5% | 2 |
| Foot | `foot` | 256 x 256 x 256 | 64 | 5% | 2 |
| vertebra | `vertebra` | 512 x 512 x 512 | 450 | 5% | 8 |

Credit for each volume, as the collection gives it: Silicium and Neghip to the
VolVis distribution of SUNY Stony Brook; Fuel and Hydrogene to SFB 382 of the
German Research Council (DFG); Marschner-Lobb to Marschner and Lobb; Engine to
General Electric; Aneurysm and Foot to Philips Research, Hamburg; Bonsai to S.
Roettger, VIS, University of Stuttgart; vertebra to Michael Meissner,
Viatronix Inc. The collection names no source for Tooth.

## License

GPL-3.0-or-later. See `LICENSE`.
