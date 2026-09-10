"""An adapter is one module per tool. It says what the tool can do, turns a case
into the file the tool reads, builds the command line that runs it, and reads
the answer back out. Nothing else knows a tool's formats or flags.

Each module defines:

- `NAME`, the tool's name as the manifest and the records spell it.
- `TRACKS`, a subset of `{"homology", "persistence"}`: whether the tool answers
  with Betti numbers, with a barcode, or with both.
- `ACCEPTS_MIXED_DIMENSION`, whether it reads a case whose cells are not all of
  the top dimension.
- `MAXIMUM_DIMENSION`, the ambient dimension above which it refuses or breaks,
  or `None` when it has no such limit.
- `COEFFICIENTS`, one of `"Z/2"`, `"Z/p"` or `"Z"`.
- `BYTES_PER_CELL`, what one cell of the complex costs a tool that builds a
  dense grid, and `None` for a tool that follows the listed cubes instead.
- `CONSTRUCTION`, `"T"` when the tool's values sit on top-dimensional cells and
  `"V"` when they sit on vertices, and `None` when it builds no grid.
- `convert(case) -> Path`, writing under `cases/converted/<NAME>/` and
  returning the file the tool reads. It is idempotent: an output newer than the
  case file is left alone. A tool that reads the canonical file returns that
  file itself.
- `command(case, config, converted) -> list[str]`, the argv to run, with
  executables named bare and every path as the container sees it, under
  `CASES_MOUNT` for a case or a converted file and `OUTPUT_MOUNT` for anything
  the tool writes.
- `parse(stdout, stderr, output_files) -> dict`, the answer: `betti` per
  dimension on the homology track, `bar_counts` per dimension on the
  persistence track, and `stages` where the tool reports its own stage timings.
- `version() -> str`, the pinned version the container holds, as a constant.
- `skip_reason(case, config, memory_limit_bytes) -> str | None`, `None` to run
  and otherwise a short reason, so that what a tool cannot do is recorded
  rather than run into an error.

The `config` an adapter is handed is the manifest's named configuration for the
run, under its `name`. A tool with a single configuration is handed the name
`default` and one thread. The layout of the case file is on the case itself, as
its `columns`.

`CASES_MOUNT` is where the container sees the repository's `cases`, read only,
and `OUTPUT_MOUNT` is the run's own scratch directory, writable and empty at
the start of every run.
"""

CASES_MOUNT = "/work/cases"
OUTPUT_MOUNT = "/work/out"

from bench.adapters import chomp3rs

ADAPTERS = {chomp3rs.NAME: chomp3rs}
