# chomp3rs-bench

A benchmark comparison of [chomp3rs](https://github.com/TravisCasey/CHomP3-rs),
a cubical homology engine for high-dimensional complexes given by their maximal
cubes, against other cubical homology programs on a common set of inputs.

The suite generates and converts inputs, runs every tool under one measurement
wrapper inside one container, checks that the tools agree on the answer, and
turns the results into tables and figures.

## Layout

- `bench/` is the Python package that drives everything: the generators that
  write cases, the converters that put a case in a tool's input format, one
  adapter per tool, the measurement wrapper, the correctness check, the tables
  and the figures.
- `driver/` is the Rust program that calls the chomp3rs API and prints its
  answer, its stage timings and its cell counts as JSON. It is the only Rust in
  the repository.
- `cases/` holds the benchmark inputs and `cases/manifest.toml`, which lists
  every case, every tool configuration and every tier.
- `Containerfile` builds the one image that holds every tool compared and the
  driver, each at a pinned revision.
- `results/` holds one JSON record per measured run under `results/runs/` and
  the summary tables under `results/summary/`.
- `figures/` holds the figures, one directory per tier, and under
  `figures/reference/` the published timings one figure draws beside them.
- `docs/` holds `docs/tools.md`, the record of where each tool came from, which
  version is built, and the limits its adapter enforces.

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

## Prerequisites

- A Linux host with rootless Podman. The measurements here were taken with
  Podman's `crun` runtime; `krun` runs a container inside a virtual machine and
  is not suitable for timing one. Every measured run starts a container with
  `--network=none`; only the image build needs `--network=host`.
- `uv`, which manages the Python side and installs the `bench` command.
- Network access for the image build and for the first `bench generate`, which
  downloads about 320 MB of published volumes.

The numbers below were measured on a machine with 16 cores and 30 GB of memory,
and every tier requests a 24 GB cap, which assumes a machine of about that size.
The cap is a tier's `memory_limit_gigabytes` in `cases/manifest.toml`; set a
smaller one there for a smaller machine. That number is also what each tool's
estimated memory for a case is checked against, and a tool that would need more
is skipped, so a smaller machine measures a smaller comparison and not merely
the same one under a tighter cap.

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

## The tools compared

`docs/tools.md` records, for each tool, where its source came from, which
version the image builds, its licence, the coefficient fields it offers, and the
limits its adapter enforces with the reason for each.

chomp3rs itself is measured in two configurations. `full` keeps every dimension
and is the one every figure that compares tools uses. `production` caps the
critical dimension at 2 and appears as a second labelled row, whose answer is
compared only in dimensions 0 and 1, the dimensions that cap leaves meaningful.

## Preparing the inputs

Install the Python side and the `bench` command:

```
uv sync
```

Every `bench` command below is run from the root of the repository, because the
manifest, the cases and the results are named relative to it.

Then write the inputs:

```
uv run bench generate
```

`generate` runs the generator of every case whose file is missing, downloads the
published volumes, and writes the sidecar of every case that has none, printing
one line per file it writes. Repeating it costs nothing: a case whose file and
sidecar are both there is passed over, so a second run prints nothing at all.
`--force` rewrites a case anyway, and `--only <case>` restricts the command to
one case.

Each tool reads its own input format. To write those before measuring:

```
uv run bench convert smoke
```

## Running

Measurements are taken one tier at a time. A tier names the cases to measure,
how many times each measurement is repeated, how long one run may take before
it is stopped, and how much memory one run may use before it is killed.

| Tier | Budget | Measured | Repetitions | Timeout per run | Memory cap |
| --- | --- | --- | --- | --- | --- |
| `smoke` | 10 minutes | 3 minutes 42 seconds | 1 | 1 minute | 24 GB |
| `quick` | 1 hour | 47 minutes | 3 | 5 minutes | 24 GB |
| `nightly` | 8 hours | not yet measured | 3 | 20 minutes | 24 GB |
| `full` | 48 hours | not yet measured | 5 | 60 minutes | 24 GB |

What each tier holds beyond the smaller ones:

- `smoke` is the correctness gate: one of the smaller cases of every family,
  with a graded case, a mixed-dimension case and a volume among them.
- `quick` adds the coarse flow covers, the smaller manifolds, the smaller
  random cases, the small gradings and the downsampled volumes.
- `nightly` adds the flow ladder in dimension 12, the medium manifolds, the
  remaining cases in dimension 8, the grading sweeps, the thread-scaling study
  and the volumes at full resolution.
- `full` adds every case left, among them the flow covers in dimension 16, the
  two largest balls, the largest random cases, and the circle, torus and curve
  in dimension 16.

The gate is run as:

```
uv run bench run smoke && uv run bench check smoke
```

`run` measures every tool on every case the tier asks for, one container per
run, and writes one record per run under `results/runs/<tier>/`. `check` reads
those records and compares the answers, against the closed form on a case that
has one and otherwise tool against tool; it exits non-zero when two answers
disagree, and reports as unchecked a case that no two tools answered.

A run a tool cannot do is recorded as skipped with the reason rather than
attempted, so a tool that reads no mixed-dimension input, or that would need
more memory than the cap allows, costs nothing. A tier that was interrupted is
resumed by running it again: it converts the cases of every run it can do, as
it did the first time, and then passes over each run whose record already
exists. To measure a case again, delete its records first.

```
uv run bench run <tier> --dry-run
```

prints one line per run saying whether it would run or be skipped and why, and
ends with a ceiling: every run that is not skipped charged the whole of its
timeout.

| Tier | Runnable | Planned | Ceiling |
| --- | --- | --- | --- |
| `smoke` | 70 | 88 | 70 minutes |
| `quick` | 291 | 368 | 73 hours |
| `nightly` | 548 | 788 | 548 hours |
| `full` | 592 | 892 | 2960 hours |

## Checking the answers

```
uv run bench check smoke
```

`check` takes one of two paths per case. A case whose sidecar carries a closed
form is compared against it, however many tools answered; one answering tool is
enough. A case without one is decided tool against tool, and counts as checked
only where two or more tools answered it and agreed; with a single tool behind
it, it is reported as unchecked, which is not a failure.

`check` changes one field of a record and nothing else: a record that is part of
a disagreement has its `status` written as `disputed`, and a record that is not
part of one has it written back to `finished`. It exits non-zero when any record
is disputed.

## Summary tables

```
uv run bench summarize smoke
```

writes two tables under `results/summary/<tier>/`.

`runs.csv` has one row per case, tool and configuration, under these columns:
the case with `case`, `family`, `ambient_dimension`, `cube_count`,
`bounding_box_volume`, `graded` and `grade_count`; the tool with `tool` and
`tool_version`; the configuration with `config`, `threads` and `modulus`; the
outcome with `status`, `repetitions` and `statuses`; the cost with
`wall_median`, `wall_min`, `wall_max`, `user_median`, `system_median`,
`peak_rss_median_kb` and `peak_rss_max_kb`; `answer` as a JSON list; `image_id`
and `repository_commit` for what produced it; and `skip_reason` on a skipped
row. The chomp3rs `production` row carries its answer in dimensions 0 and 1
only.

`stages.csv` has one row per stage of each chomp3rs run: the case, the
configuration, the stage, its median seconds, and the cells going in and coming
out.

A repetition the tier stopped still counts towards its row, censored at the
limit it hit rather than at the number the kill left behind: one stopped for
time carries the tier's timeout as its wall time, one stopped for memory carries
the cap as its peak. A group whose repetitions ended differently keeps its
measured medians, takes the worst of their statuses, and lists the mix in its
`statuses` column.

## Figures

```
uv run bench plot smoke
```

writes `figures/<tier>/fig<NN>_<name>.pdf` and `.png`. The eleven figures are,
in order, `headline_flows`, `ladder_d12`, `dimension_manifolds`,
`sphere_table1`, `density_random_top`, `mixed_dimension`, `grade_count`,
`thread_scaling`, `memory_volume`, `published_sets` and `coverage`. A figure
whose cases or tools the tier's tables do not hold is not drawn, and one line
says what was missing, so a smaller tier yields a subset of the eleven.

A mark on a time axis is a measurement. A run the tier stopped is drawn in a
lane beside the axes instead, in the column or row of its case: an open marker
for a run out of time, a cross for a run killed for memory. On a memory axis a
killed run reached the cap and sits on the cap line as an open marker, while a
run out of time has no peak to draw and is absent. An answer the check disputed
is drawn inside a black ring, and a run that ended in an error is not drawn at
all but is named in a printed line. Every figure's legend names the conventions
that figure uses. The last figure, `coverage`, shows for every ungraded case of
the tier which tools finished, were stopped, were killed, or refused it and why.

Figure 4 draws `figures/reference/table1.csv`, a transcription of Table 1(a) of
arXiv 2105.09870, beside the suite's own sphere cases.

## Reading a result record

One run of one tool on one case is one file:

```
results/runs/<tier>/<case>__<tool>__<config>__r<repetition>.json
```

It holds the case and its family; the tool and its version; the configuration,
which is its name, its coefficient field and its thread count, and for chomp3rs
the backend, the modulus, the maximum critical dimension where one is set, and
on the `production` configuration the `check_dimensions` its answer is compared
on; the tier and the repetition; the wall, user and system seconds and the peak
resident set size in kilobytes; the status; the answer, which is the Betti
numbers and, on the persistence track, the bar counts, with the finite and
essential bars beside them on a chomp3rs record; the driver's six stages
with their seconds and cell counts, on chomp3rs records only; and the machine,
which is its hostname, processor model, kernel, image identifier and repository
commit. A run a tool declared it cannot do is a record with repetition 0, no
measurements and a `skip_reason`.

The wrapper runs each tool under `timeout -s KILL` and `/usr/bin/time -v` inside
a container capped with `--memory`, and reads how the run ended out of the two.
The status is one of six:

- `finished`: the run ended normally.
- `disputed`: it ended normally and `check` found its answer in a disagreement.
- `timeout`: it passed the tier's timeout and was killed. The wall time is the
  wrapper's own clock, and there are no user, system or peak figures, because
  the kill takes `time` with it.
- `out_of_memory`: the cap killed it. Its measured wall time is kept and its
  peak is the cap.
- `error`: any other nonzero exit.
- `skipped`: the tool declared it could not do the run.

## Rerunning a case

A record that is already there is a run already done, which is what lets an
interrupted tier resume: the run loop passes over it and never measures it
again. To measure a case again, delete its records under `results/runs/<tier>/`
and run the tier again. Result files are not edited by hand; a wrong result is
deleted and measured again.

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

## Deferred comparisons

Two comparisons the suite is built for and does not yet run.

**The lift comparison.** chomp3rs and pyCHomP2 both lift a homology class back
to a cycle and a cocycle of the original complex, which the Betti numbers alone
do not give. Timing both lifts on the H^1 bars of the flow covers attaches as a
flag on the driver and a second pyCHomP2 configuration.

**The MPI study.** DIPHA distributes its matrix reduction across MPI ranks and
chomp3rs has an MPI feature of its own. Measuring both at 1, 2, 4, 8 and 16
ranks says how each of them scales with the ranks it is given. It attaches as a
tier with a rank axis and a wrapper that submits a job instead of starting a
single container.

## License

GPL-3.0-or-later. See `LICENSE`.
