# Tools

The programs the suite compares, each built at a fixed version inside the
container. The adapters under `bench/adapters/` show how each one is called
and what it reads and writes; this file records where each came from, which
version, and the limits the adapters enforce.

| Tool | What it does | Source | Version | Licence | Coefficients |
| --- | --- | --- | --- | --- | --- |
| chomp3rs | template matching per orthant, coreduction, barcode | `https://github.com/TravisCasey/CHomP3-rs` | commit `2f15ddbcf96f9df2650000bf8265c28e782ce57a` | GPL-3.0-or-later | Z/p, p chosen |
| homcubes (CHomP, Pawel Pilarczyk) | algebraic reduction of a cube list | `http://www.pawelpilarczyk.com/chomp/download/chomp-full.zip` | archive dated 2024-02-15, sha256 `16ff175453e17c83e5cf207a7574453dbe348a26a2129759e30fce605580dbc0`, prints `ver. 3.07` | GPL-3.0-or-later | Z, or Z/p with `-p p` |
| pyCHomP2 (Shaun Harker's CHomP, Python binding) | discrete Morse theory on a dense box | `https://github.com/marciogameiro/pyCHomP2` | commit `b7b11af5fc387a6f55f42dd8fabb8d710e50d7c6` (1.1.2) | MIT | Z/2 only |
| Perseus (Vidit Nanda) | discrete Morse theory on a cube list | `https://people.maths.ox.ac.uk/nanda/source/perseus_4_beta.zip` | 4.0 beta, sha256 `7279091080b8b6ef8d8bbcf470a76398b752f102def222a9740f2e85ad8c7925` | unstated | Z/2 only |
| GUDHI | persistent homology of a dense grid, called as a Python module | `https://github.com/GUDHI/gudhi-devel` | release 3.13.0, tag `tags/gudhi-release-3.13.0`, commit `5dbe510bed5d8d700ec7243fd915769fb67964a2` | MIT | Z/p, p chosen |
| DIPHA | distributed matrix reduction on a dense grid | `https://github.com/DIPHA/dipha` | commit `0b874769fbd092c07a12cebc2459adb02117c2fd` | LGPL-3.0-or-later | Z/2 only |
| Cubical Ripser | Ripser's reduction adapted to a dense cubical grid | `https://github.com/shizuo-kaji/CubicalRipser` | commit `e9632f2466674c07cda0db2f178da26007194496` | LGPL-3.0-or-later, but the licence file in the repository is the GPL | Z/2 only |

## Limits the adapters enforce

- chomp3rs is refused above ambient dimension 24. Its cube and orthant types
  hold a fixed-size array of that many coordinates and its reader rejects a file
  with more columns than that. The limit is there because the grade table the
  library keeps for one orthant is dense in 2^d. It reads the canonical file
  unchanged, grades and mixed-dimension cells included, so no case is skipped
  for its format.
- homcubes is refused above ambient dimension 19. Its reduction stage counts
  neighbours in a 32-bit integer that overflows at 3^20, and above that
  dimension it either fails to allocate or returns a wrong reduction while
  appearing to succeed. It has no filtration track, so graded cases skip it.
- pyCHomP2 takes only a box with a value per cell, never a cube list, so it is
  a dense tool: it is skipped when the box would need more memory than the
  cap, at about 24 bytes per cell with 2^d cells per box position. Its output
  is the cells of a connection matrix, not bars; the adapter pairs them
  itself.
- Perseus materialises every face of every cube, 3^d cells per cube, so one
  cube alone needs about 1.4 KB times 3^d. It cannot run at ambient dimension
  16 under the suite's memory cap and is skipped there. It reads top cubes
  only, so mixed-dimension cases skip it.
- GUDHI takes a dense grid with one value per top cube, which is the complex
  the cube list already means, so the grid needs no conversion. It is a dense
  tool: it is skipped when the complex, `(2n + 1)^d` cells for a case of grid
  side n in d dimensions, needs more than the memory cap at about 122 bytes a
  cell. It reads top cells or vertices and never a listing of faces of mixed
  dimension, so mixed-dimension cases skip it.
- DIPHA puts its values on the grid's vertices, and the complex it builds from
  them is not the one a list of closed top cubes means: two cubes meeting only
  at a corner are connected in the cube list and separate in DIPHA's complex.
  The converter therefore doubles the grid, giving a cell with base orthant b
  and extent mask e the vertex 2b + e of a lattice of 2n + 1 points per axis,
  which restores the intended answer. It is skipped when the complex, `(4n +
  1)^d` cells for a case of grid side n in d dimensions, needs more than the
  memory cap at about 82 bytes a cell.
- Cubical Ripser is refused above ambient dimension 4. Its own array reader
  stops there with the message that the input should be 1, 2, 3 or 4
  dimensional. It takes a dense grid with one value per top cube, so the grid
  needs no conversion, and it is skipped when the complex, `(2n + 1)^d` cells
  for a case of grid side n in d dimensions, needs more than the memory cap at
  about 14 bytes a cell. It reads top cells only, so mixed-dimension cases skip
  it.

## Build notes

- homcubes builds every program from a `COMPILE` variable of its own and never
  reads `CXXFLAGS`, so the container recipe sets that variable on the make
  command line to compile it with the same flags as the other tools.
- GUDHI is installed as a prebuilt wheel and is the one tool not compiled with
  the image's flags.
- Perseus does not compile under a current C++ standard library without three
  one-line changes marking constant members `const`; the container recipe
  applies them.
- pyCHomP2 needs `pybind11` installed before its build and the environment
  variable `CMAKE_PREFIX_PATH` pointing at the directory `pybind11` reports,
  which its own instructions omit; the container recipe does both.
- DIPHA asks for a version of cmake older than any current one and does not
  configure without `-DCMAKE_POLICY_VERSION_MINIMUM=3.5`; the container recipe
  passes it. No source change is needed.
- Cubical Ripser looks for `nanobind` while configuring even when only its two
  command line programs are wanted, and it looks for it through whichever
  Python interpreter cmake finds; the container recipe installs `nanobind` and
  names the interpreter with `-DPython_EXECUTABLE`.
