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

## License

GPL-3.0-or-later. See `LICENSE`.
