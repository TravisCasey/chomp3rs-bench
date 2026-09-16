"""The figures: the summary tables of a tier turned into the paper's plots.

Reads `results/summary/<tier>/runs.csv` and `stages.csv` and writes
`figures/<tier>/fig<NN>_<name>.pdf` and `.png`, one pair per figure of
`FIGURES`. A figure whose cases or tools are not in the tables is not drawn and
prints one line saying what is missing.

The figures are typeset for a 12 pt page with a 448 pt text block: text is set
by LuaLaTeX in STIX Two Text and STIX Two Math, a wide figure is the width of
the text block and a narrow one 300 pt, and no figure carries a title or a note
beneath it, the caption naming what the marks mean. After every PDF is written
one line prints its page size in points and the fonts it embeds, so a wrong
width or a font that fell back shows in the terminal. Where a figure fixes a
parameter when it is drawn, such as the draws a density sweep takes its median
over, the same line says which, for the caption to repeat.

A mark on a time axis is a measurement and nothing else. A run the tier stopped,
out of time or killed for memory, leaves its case without a mark for that tool.
A figure that compares cost against size or dimension carries a second row of
peak memory on the same axis, where a run the cap killed sits on the cap line as
an open marker. A group whose repetitions ended differently takes the worst of
their statuses, a run the tier skipped is not drawn, and a run that ended in an
error is not drawn either but is named in a printed note. A run whose answer the
check disputed is drawn where it landed inside a black ring.

The last figure is the working view of a tier rather than a figure of the paper:
the coverage matrix shows for every ungraded case which tools finished, were
stopped, were killed, or refused it and why.

Drawing needs LuaLaTeX with the STIX Two fonts, both part of TeX Live. Invoked
as `bench plot <tier>`; see `bench.cli`.
"""

import csv
import re
import statistics
import zlib
from dataclasses import dataclass
from math import ceil, floor, log10
from pathlib import Path

import matplotlib

matplotlib.use("pgf")

import numpy
from matplotlib import pyplot
from matplotlib.colors import to_hex, to_rgb
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import (
    FixedLocator,
    FuncFormatter,
    LogLocator,
    NullFormatter,
    NullLocator,
)

from bench import manifest, summarize

SUMMARY_DIRECTORY = Path("results/summary")
FIGURE_DIRECTORY = Path("figures")

POINTS_PER_INCH = 72.27
TEXT_WIDTH_POINTS = 448.0
PAGE_WIDTH_INCHES = TEXT_WIDTH_POINTS / POINTS_PER_INCH
COLUMN_WIDTH_INCHES = 300.0 / POINTS_PER_INCH
ROW_HEIGHT_INCHES = 0.28
SERIES_HEIGHT_INCHES = 3.0
TWO_ROW_HEIGHT_INCHES = 4.9
LABEL_LINE_SPACING = 1.55

FULL_CONFIG = "full"
TIME_AXIS = "time"
MEMORY_AXIS = "memory"
KILOBYTES_PER_GIGABYTE = 1024 * 1024

FILLED_POINT = "filled"
OPEN_POINT = "open"
KILLED_POINT = "killed"

INK = "#1a1a19"
MUTED = "#6b6a66"
GRID = "#e4e3df"
SPINE = "#9a9994"
SURFACE = "#ffffff"
BAND = "#f4f3f0"

OKABE_ORANGE = "#e69f00"
OKABE_SKY = "#56b4e9"
OKABE_GREEN = "#009e73"
OKABE_BLUE = "#0072b2"
OKABE_VERMILLION = "#d55e00"
OKABE_PURPLE = "#cc79a7"

TOOL_STYLE = {
    "chomp3rs": {"label": "CHomP3-rs", "color": "#000000", "marker": "o", "size": 5.0},
    "homcubes": {"label": "homcubes", "color": OKABE_VERMILLION, "marker": "s", "size": 4.4},
    "pychomp2": {"label": "pyCHomP2", "color": OKABE_PURPLE, "marker": "^", "size": 5.4},
    "perseus": {"label": "Perseus", "color": OKABE_GREEN, "marker": "D", "size": 4.0},
    "gudhi": {"label": "GUDHI", "color": OKABE_ORANGE, "marker": "v", "size": 5.4},
    "dipha": {"label": "DIPHA", "color": OKABE_SKY, "marker": "p", "size": 5.6},
    "cubical_ripser": {
        "label": "Cubical Ripser",
        "color": OKABE_BLUE,
        "marker": "*",
        "size": 7.2,
    },
}

TOOL_ORDER = tuple(TOOL_STYLE)

REFERENCE_COLOR = MUTED
DISPUTED_RING_COLOR = "#000000"
DISPUTED_MARKER = "o"
LINE_WIDTH = 0.9
CAP_LINE = {"color": REFERENCE_COLOR, "linestyle": (0, (1.0, 2.0)), "linewidth": 0.9, "zorder": 1}

COVERAGE_COLORS = {
    summarize.FINISHED: (OKABE_BLUE, "finished"),
    summarize.DISPUTED: (OKABE_BLUE, "finished"),
    summarize.TIMEOUT: (OKABE_ORANGE, "stopped at the timeout"),
    summarize.OUT_OF_MEMORY: (OKABE_VERMILLION, "killed at the memory cap"),
    summarize.ERROR: (INK, "ended in an error"),
    "memory": ("#bdbcb7", "refused: memory over the cap"),
    "time": ("#f3dca8", "refused: measured to run past the timeout"),
    "dimension": ("#d9d8d3", "refused: dimension above the tool's limit"),
    "input": ("#ecebe7", "refused: input not accepted"),
    "absent": (SURFACE, "not run"),
}
COVERAGE_ORDER = (
    summarize.FINISHED,
    summarize.TIMEOUT,
    summarize.OUT_OF_MEMORY,
    summarize.ERROR,
    "memory",
    "time",
    "dimension",
    "input",
    "absent",
)

FLOW_PANELS = (
    ("lorenz_d6", "Lorenz, $d = 6$"),
    ("dadras_d8", "Dadras, $d = 8$"),
    ("charney_devore_d12", "Charney-DeVore, $d = 12$"),
    ("kuramoto_sivashinsky_d16", "Kuramoto-Sivashinsky, $d = 16$"),
)
MANIFOLD_PANELS = (
    ("circle", re.compile(r"^s1_d(\d+)$")),
    ("torus", re.compile(r"^torus_d(\d+)$")),
    ("curve", re.compile(r"^curve_d(\d+)_n2000$")),
    ("tangent-bundle curve", re.compile(r"^curve_tb_d(\d+)$")),
)
MIXED_FAMILY = "random_mixed"
PUBLISHED_FAMILY = "published"
THRESHOLDED_SUFFIX = "_full"
INTENSITY_SUFFIX = "_intensity"
PUBLISHED_SUFFIXES = (THRESHOLDED_SUFFIX, INTENSITY_SUFFIX)

STAGE_BARS = (
    ("read and build", ("read", "build")),
    ("matching", ("matching",)),
    ("Morse", ("morse",)),
    ("coreduction", ("coreduction",)),
    ("persistence", ("persistence",)),
)
STAGE_RAMP = ("#a3b4c6", "#8098b3", "#5f7a98", "#43607d", "#243a52")
STAGE_LABEL_INSIDE = 12.0
STAGE_SIZE_TOKEN = re.compile(
    r"_(box[0-9.]+|n\d+|p[0-9.]+|side\d+|draw\d+|r\d+|d\d+|random_g\d+|minimal|coarse|fine)"
)

LADDER_CASE = re.compile(r"^(.+)_box([0-9.]+)$")
DENSITY_CASE = re.compile(r"^random_top_d(\d+)_side(\d+)_p([0-9.]+)_draw(\d+)$")
GRADED_CASE = re.compile(r"^(.+)_random_g(\d+)$")
FONT_NAME = re.compile(rb"/BaseFont\s*/(?:[A-Z]{6}\+)?([A-Za-z0-9-]+)")
PDF_STREAM = re.compile(rb"stream\r?\n(.*?)endstream", re.S)

pyplot.rcParams.update(
    {
        "pgf.texsystem": "lualatex",
        "pgf.rcfonts": False,
        "text.usetex": True,
        "pgf.preamble": (
            r"\usepackage{fontspec}\usepackage{unicode-math}"
            r"\setmainfont{STIX Two Text}\setmathfont{STIX Two Math}"
        ),
        "font.family": "serif",
        "font.size": 9,
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        "figure.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "axes.edgecolor": SPINE,
        "axes.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": GRID,
        "grid.linewidth": 0.5,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "xtick.minor.width": 0.4,
        "ytick.minor.width": 0.4,
        "xtick.major.size": 3,
        "ytick.major.size": 3,
        "xtick.minor.size": 1.8,
        "ytick.minor.size": 1.8,
        "xtick.color": SPINE,
        "ytick.color": SPINE,
        "xtick.labelcolor": INK,
        "ytick.labelcolor": INK,
        "axes.labelcolor": INK,
        "text.color": INK,
        "legend.frameon": False,
        "legend.handletextpad": 0.5,
        "legend.columnspacing": 1.3,
        "axes.unicode_minus": False,
        "figure.constrained_layout.use": True,
        "figure.constrained_layout.h_pad": 0.03,
        "figure.constrained_layout.w_pad": 0.03,
    }
)


@dataclass
class Tables:
    tier: manifest.Tier
    configs: dict
    runs: list[dict]
    stages: list[dict]


def plot_tier(loaded, tier_name):
    tables = read_tables(loaded, tier_name)
    directory = FIGURE_DIRECTORY / tier_name
    directory.mkdir(parents=True, exist_ok=True)
    for number, name, width, draw in FIGURES:
        label = f"fig{number:02d}_{name}"
        drawn = draw(tables, width, label)
        if isinstance(drawn, str):
            print(f"{label} not drawn: {drawn}")
            continue
        figure, chosen = drawn
        path = directory / f"{label}.pdf"
        figure.savefig(path)
        figure.savefig(directory / f"{label}.png", dpi=300)
        pyplot.close(figure)
        print(f"{path} {check_line(figure, path)}{chosen}")


def check_line(figure, path):
    """The page size of the PDF in TeX points and the fonts it embeds, read
    from the file itself, so that the width budget and the typeface are checked
    on every draw rather than trusted."""
    width = figure.get_figwidth() * POINTS_PER_INCH
    height = figure.get_figheight() * POINTS_PER_INCH
    data = path.read_bytes()
    fonts = set(FONT_NAME.findall(data))
    for match in PDF_STREAM.finditer(data):
        try:
            fonts.update(FONT_NAME.findall(zlib.decompress(match.group(1))))
        except zlib.error:
            continue
    names = " ".join(sorted(font.decode() for font in fonts)) or "none"
    return f"{width:.0f} x {height:.0f} pt, fonts {names}"


def read_tables(loaded, tier_name):
    directory = SUMMARY_DIRECTORY / tier_name
    return Tables(
        tier=loaded.tiers[tier_name],
        configs=loaded.configs,
        runs=read_rows(directory / "runs.csv"),
        stages=read_rows(directory / "stages.csv"),
    )


def read_rows(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def number_of(row, column):
    text = row[column]
    return float(text) if text else None


def cross_tool_rows(tables):
    """The rows a figure comparing tools draws: one configuration per tool, the
    chomp3rs one being `full`."""
    return [
        row
        for row in tables.runs
        if row["tool"] != manifest.CHOMP3RS or row["config"] == FULL_CONFIG
    ]


def tools_present(tables, rows, axis):
    """The tools the figure has a point for, in the fixed order, so that a tool
    every one of whose runs was skipped stays out of the legend."""
    return [
        tool
        for tool in TOOL_ORDER
        if any(
            row["tool"] == tool and point_of(tables, row, axis) is not None
            for row in rows
        )
    ]


def drawn_cases(tables, rows, axis):
    """The cases some tool has a point for, so that a case no tool finished
    takes no room on a categorical axis."""
    return {row["case"] for row in rows if point_of(tables, row, axis) is not None}


def note_errors(label, rows):
    """One line per run that ended in an error, which no figure draws, so that
    nothing leaves a figure without saying so."""
    for row in rows:
        if row["status"] == summarize.ERROR:
            print(f"{label}: {row['case']} {row['tool']} ended in an error, not drawn")


def case_label(name):
    return name.replace("_", " ")


def point_of(tables, row, axis):
    """Where a row sits on a time or a memory axis and which marker says how it
    got there, or `None` where the row has nothing to say on that axis."""
    status = row["status"]
    if axis == MEMORY_AXIS and status == summarize.OUT_OF_MEMORY:
        return float(tables.tier.memory_limit_gigabytes), KILLED_POINT
    if status not in summarize.COMPARABLE:
        return None
    if axis == TIME_AXIS:
        seconds = number_of(row, "wall_median")
        return None if seconds is None else (seconds, FILLED_POINT)
    peak = number_of(row, "peak_rss_median_kb")
    return None if peak is None else (peak / KILOBYTES_PER_GIGABYTE, FILLED_POINT)


def marker_arguments(tool, convention):
    """How a point is drawn: filled for a measurement, open for a run the cap
    killed, which is drawn on the cap line of a memory axis."""
    style = TOOL_STYLE[tool]
    if convention == OPEN_POINT:
        return {
            "marker": style["marker"],
            "markersize": style["size"] + 0.4,
            "markeredgecolor": style["color"],
            "markerfacecolor": "none",
            "markeredgewidth": 1.0,
        }
    return {
        "marker": style["marker"],
        "markersize": style["size"],
        "markeredgecolor": SURFACE,
        "markerfacecolor": style["color"],
        "markeredgewidth": 0.5,
    }


def disputed_ring_arguments():
    """The ring drawn around a point whose answer the check disputed: black,
    which belongs to no tool and stays black in grey."""
    return {
        "marker": DISPUTED_MARKER,
        "markersize": TOOL_STYLE[manifest.CHOMP3RS]["size"] + 4.0,
        "markeredgecolor": DISPUTED_RING_COLOR,
        "markerfacecolor": "none",
        "markeredgewidth": 0.9,
    }


def plot_series(axes, tables, tool, points, axis, connect, horizontal=False, gap=None):
    """One tool's points, joined by the tool's line through the measurements
    when the axis reads as a series. A run the cap killed is drawn on the cap
    line of a memory axis and is never joined, and where `gap` is given the line
    breaks across a step wider than it, so that no line crosses a size or a
    dimension the tier did not measure. CHomP3-rs, the reference series, is
    drawn above the others, so another tool's mark at the same place never hides
    it."""
    above = 1 if tool == manifest.CHOMP3RS else 0
    placed = []
    for position, row in points:
        point = point_of(tables, row, axis)
        if point is not None:
            placed.append((position, point[0], point[1], row["status"]))
    placed.sort(key=lambda entry: entry[0])
    joined = [entry for entry in placed if entry[2] == FILLED_POINT]
    if connect and len(joined) > 1:
        for segment in split_on_gap(joined, gap):
            if len(segment) < 2:
                continue
            positions = [entry[0] for entry in segment]
            values = [entry[1] for entry in segment]
            axes.plot(
                *((values, positions) if horizontal else (positions, values)),
                color=TOOL_STYLE[tool]["color"],
                linewidth=LINE_WIDTH,
                zorder=2 + above,
            )
    for position, value, convention, status in placed:
        shown = OPEN_POINT if convention == KILLED_POINT else FILLED_POINT
        coordinates = ([value], [position]) if horizontal else ([position], [value])
        axes.plot(
            *coordinates,
            linestyle="none",
            zorder=4 + above,
            **marker_arguments(tool, shown),
        )
        if status == summarize.DISPUTED:
            axes.plot(
                *coordinates, linestyle="none", zorder=6, **disputed_ring_arguments()
            )


def split_on_gap(entries, gap):
    if gap is None:
        return [entries]
    segments, current = [], []
    for entry in entries:
        if current and entry[0] - current[-1][0] > gap:
            segments.append(current)
            current = []
        current.append(entry)
    if current:
        segments.append(current)
    return segments


def measured_step(positions):
    """The step a series was measured at, which is the least distance between
    two of its positions; a line breaks across a wider one."""
    ordered = sorted(set(positions))
    steps = [second - first for first, second in zip(ordered, ordered[1:])]
    return min(steps) if steps else None


def tool_handles(tools, with_line):
    return [
        Line2D(
            [],
            [],
            label=TOOL_STYLE[tool]["label"],
            color=TOOL_STYLE[tool]["color"],
            linestyle="-" if with_line else "none",
            linewidth=LINE_WIDTH,
            **marker_arguments(tool, FILLED_POINT),
        )
        for tool in tools
    ]


def log_scale(axes, which, numticks=12):
    """A logarithmic axis labelled at the decades, with unlabelled minor ticks
    at 2, 3 and 5."""
    if which == "x":
        axes.set_xscale("log")
        axis = axes.xaxis
    else:
        axes.set_yscale("log")
        axis = axes.yaxis
    axis.set_major_locator(LogLocator(base=10.0, numticks=numticks))
    axis.set_minor_locator(LogLocator(base=10.0, subs=(2.0, 3.0, 5.0), numticks=20))
    axis.set_minor_formatter(NullFormatter())


def count_ticks(axes):
    """A cube-count axis labelled in thousands at as few round values as the
    span allows, so that every panel of a figure labels its counts alike."""
    low, high = sorted(axes.get_xlim())
    values = []
    for subs in ((1, 2, 5), (1, 3), (1,)):
        values = [
            step * 10**power
            for power in range(0, 10)
            for step in subs
            if low <= step * 10**power <= high
        ]
        if len(values) <= 6:
            break
    axes.xaxis.set_major_locator(FixedLocator(values))
    axes.xaxis.set_major_formatter(
        FuncFormatter(
            lambda value, _: f"{value / 1e6:g}M"
            if value >= 1e6
            else (f"{value / 1000:g}k" if value >= 1000 else f"{value:g}")
        )
    )
    axes.xaxis.set_minor_formatter(NullFormatter())
    axes.set_xlim(low, high)


def integer_ticks(axes, values):
    """Ticks at the even integers a series was measured at, which is as many as
    a panel of a four-panel figure has room to label."""
    ordered = sorted(set(values))
    even = [value for value in ordered if value % 2 == 0] or ordered
    axes.xaxis.set_major_locator(FixedLocator(even))
    axes.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
    axes.xaxis.set_minor_locator(NullLocator())
    axes.set_xlim(ordered[0] - 0.5, ordered[-1] + 0.5)


def case_axis_label(axes, axis_name, panel_title):
    """The label under a panel: what the axis measures, then the case it is
    measured on, set a little apart."""
    axes.set_xlabel(f"{axis_name}\n{panel_title}", linespacing=LABEL_LINE_SPACING)


def legend_columns(handles, width):
    """As many columns as the longest entry leaves room for across the figure."""
    longest = max(len(handle.get_label()) for handle in handles)
    entry = 0.4 + longest * 0.058
    return max(1, min(4, int(width / entry), len(handles)))


def finish_figure(figure, series, width, chosen=""):
    """The legend of the series above the axes, placed by the layout. Nothing
    is set beneath the axes; the paper's caption carries the conventions."""
    figure.legend(
        handles=series,
        loc="outside upper center",
        ncol=legend_columns(series, width),
        handlelength=1.8,
        borderaxespad=0.2,
    )
    return figure, chosen


def series_panels(width, height, columns, share_y=False):
    """The axes of a figure whose values run up the page, one panel per column."""
    figure, panels = pyplot.subplots(
        1, columns, figsize=(width, height), squeeze=False, sharey=share_y
    )
    return figure, list(panels[0])


def time_and_memory_panels(width, columns, height=TWO_ROW_HEIGHT_INCHES):
    """A row of wall time above a row of peak memory, one column per panel, the
    columns sharing their size or dimension axis and the rows their scale."""
    figure, grid = pyplot.subplots(
        2,
        columns,
        figsize=(width, height),
        squeeze=False,
        sharex="col",
        sharey="row",
        gridspec_kw={"height_ratios": [1.15, 1]},
    )
    return figure, grid


def draw_time_and_memory(tables, grid, column, rows, position_of, connect=True, gap=None):
    """One column of a time-and-memory figure: every tool's wall time above its
    peak memory, against the same positions."""
    used = []
    for line, axis in enumerate((TIME_AXIS, MEMORY_AXIS)):
        axes = grid[line][column]
        for tool in TOOL_ORDER:
            points = [(position_of(row), row) for row in rows if row["tool"] == tool]
            if not any(point_of(tables, row, axis) is not None for _, row in points):
                continue
            plot_series(axes, tables, tool, points, axis, connect=connect, gap=gap)
            if tool not in used:
                used.append(tool)
        log_scale(axes, "y")
        if axis == MEMORY_AXIS:
            axes.axhline(tables.tier.memory_limit_gigabytes, **CAP_LINE)
    return used


def label_time_and_memory(grid):
    grid[0][0].set_ylabel("wall time (s)")
    grid[1][0].set_ylabel("peak memory (GB)")


def draw_flow_ladders(tables, width, label):
    """Wall time and peak memory against cube count on the flow covers, one
    panel per system, each one trajectory at several box sizes."""
    rows = [
        row
        for row in cross_tool_rows(tables)
        if row["family"] == "flows" and row["graded"] == "false"
    ]
    note_errors(label, rows)
    panels = []
    for prefix, title in FLOW_PANELS:
        panel = [row for row in rows if row["case"].startswith(prefix)]
        if drawn_cases(tables, panel, TIME_AXIS):
            panels.append((title, panel))
    if not panels:
        return "no measured run on a flow cover in the tables"
    figure, grid = time_and_memory_panels(width, len(panels))
    used = []
    for column, (title, panel) in enumerate(panels):
        for tool in draw_time_and_memory(
            tables, grid, column, panel, lambda row: number_of(row, "cube_count")
        ):
            if tool not in used:
                used.append(tool)
        for line in (0, 1):
            log_scale(grid[line][column], "x")
        count_ticks(grid[1][column])
        case_axis_label(grid[1][column], "cubes in the cover", title)
    label_time_and_memory(grid)
    return finish_figure(
        figure, tool_handles([t for t in TOOL_ORDER if t in used], True), width
    )


def draw_dimension_manifolds(tables, width, label):
    """Wall time and peak memory against ambient dimension on the parametric
    families, one panel per shape."""
    rows = [
        row
        for row in cross_tool_rows(tables)
        if row["graded"] == "false"
        and any(pattern.match(row["case"]) for _, pattern in MANIFOLD_PANELS)
    ]
    note_errors(label, rows)
    panels = []
    for title, pattern in MANIFOLD_PANELS:
        panel = [row for row in rows if pattern.match(row["case"])]
        if drawn_cases(tables, panel, TIME_AXIS):
            panels.append((title, pattern, panel))
    if not panels:
        return "no measured run on a circle, torus or curve case in the tables"
    figure, grid = time_and_memory_panels(width, len(panels))
    used = []
    for column, (title, pattern, panel) in enumerate(panels):
        dimension_of = lambda row: float(pattern.match(row["case"]).group(1))
        measured = [
            dimension_of(row)
            for row in panel
            if point_of(tables, row, TIME_AXIS) is not None
        ]
        for tool in draw_time_and_memory(
            tables, grid, column, panel, dimension_of, gap=measured_step(measured)
        ):
            if tool not in used:
                used.append(tool)
        integer_ticks(grid[1][column], measured)
        case_axis_label(grid[1][column], "ambient dimension $d$", title)
    label_time_and_memory(grid)
    return finish_figure(
        figure, tool_handles([t for t in TOOL_ORDER if t in used], True), width
    )


def draw_spread(axes, tables, tool, entries):
    """One tool's median over the draws at each density, joined across the
    densities, with a stroke from the least to the greatest draw; a density at
    which no draw finished has no mark."""
    by_density = {}
    disputed = set()
    for density, row in entries:
        point = point_of(tables, row, TIME_AXIS)
        if point is None:
            continue
        by_density.setdefault(density, []).append(point[0])
        if row["status"] == summarize.DISPUTED:
            disputed.add(density)
    densities = sorted(by_density)
    medians = [statistics.median(by_density[density]) for density in densities]
    color = TOOL_STYLE[tool]["color"]
    if len(densities) > 1:
        axes.plot(densities, medians, color=color, linewidth=LINE_WIDTH, zorder=2)
    for density, median in zip(densities, medians):
        values = by_density[density]
        axes.plot(
            [density, density], [min(values), max(values)], color=color, linewidth=0.8, zorder=2
        )
        axes.plot(
            [density], [median], linestyle="none", zorder=3, **marker_arguments(tool, FILLED_POINT)
        )
        if density in disputed:
            axes.plot(
                [density], [median], linestyle="none", zorder=4, **disputed_ring_arguments()
            )


def draw_density_random_top(tables, width, label):
    """Wall time against the share of box positions holding a cube, one panel
    per dimension of the sweep, each point the median over the draws."""
    groups = {}
    draws = set()
    for row in cross_tool_rows(tables):
        match = DENSITY_CASE.match(row["case"])
        if match:
            key = (int(match.group(1)), int(match.group(2)))
            groups.setdefault(key, []).append((float(match.group(3)), row))
            draws.add(int(match.group(4)))
    note_errors(label, [row for entries in groups.values() for _, row in entries])
    panels = sorted(
        key
        for key, entries in groups.items()
        if drawn_cases(tables, [row for _, row in entries], TIME_AXIS)
    )
    if not panels:
        return "no measured run on a random_top density sweep in the tables"
    rows = [row for key in panels for _, row in groups[key]]
    figure, axes_list = series_panels(width, SERIES_HEIGHT_INCHES, len(panels))
    for axes, (dimension, side) in zip(axes_list, panels):
        entries = groups[(dimension, side)]
        panel_tools = tools_present(tables, [row for _, row in entries], TIME_AXIS)
        for tool in panel_tools:
            draw_spread(
                axes,
                tables,
                tool,
                [(density, row) for density, row in entries if row["tool"] == tool],
            )
        log_scale(axes, "y")
        densities = sorted({density for density, _ in entries})
        axes.xaxis.set_major_locator(FixedLocator(densities))
        axes.set_xticklabels([f"{density:g}" for density in densities])
        case_axis_label(
            axes, "share of positions holding a cube", f"$d = {dimension}$, side {side}"
        )
    axes_list[0].set_ylabel("wall time (s)")
    return finish_figure(
        figure,
        tool_handles(tools_present(tables, rows, TIME_AXIS), True),
        width,
        chosen=f", each point the median and range over {len(draws)} draws",
    )


def draw_mixed_dimension(tables, width, label):
    """Wall time and peak memory against cube count on the random
    mixed-dimension cases, one panel per ambient dimension."""
    rows = [
        row
        for row in cross_tool_rows(tables)
        if row["family"] == MIXED_FAMILY and row["status"] != summarize.SKIPPED
    ]
    note_errors(label, rows)
    panels = []
    for dimension in sorted({int(row["ambient_dimension"]) for row in rows}):
        panel = [row for row in rows if int(row["ambient_dimension"]) == dimension]
        if drawn_cases(tables, panel, TIME_AXIS):
            panels.append((dimension, panel))
    if not panels:
        return "no measured run on a random mixed-dimension case in the tables"
    figure, grid = time_and_memory_panels(width, len(panels))
    used = []
    for column, (dimension, panel) in enumerate(panels):
        for tool in draw_time_and_memory(
            tables, grid, column, panel, lambda row: number_of(row, "cube_count")
        ):
            if tool not in used:
                used.append(tool)
        for line in (0, 1):
            log_scale(grid[line][column], "x")
        low, high = grid[1][column].get_xlim()
        grid[1][column].set_xlim(low / 1.3, high * 1.3)
        count_ticks(grid[1][column])
        case_axis_label(grid[1][column], "cubes in the case", f"$d = {dimension}$")
    label_time_and_memory(grid)
    return finish_figure(
        figure, tool_handles([t for t in TOOL_ORDER if t in used], True), width
    )


def draw_grade_count(tables, width, label):
    """Wall time against the number of grades on the randomly graded cases, one
    panel per case graded at more than one count."""
    by_base = {}
    for row in cross_tool_rows(tables):
        match = GRADED_CASE.match(row["case"])
        if match and row["graded"] == "true":
            by_base.setdefault(match.group(1), []).append(row)
    note_errors(label, [row for group in by_base.values() for row in group])
    bases = sorted(
        base
        for base, group in by_base.items()
        if len(
            {
                row["grade_count"]
                for row in group
                if point_of(tables, row, TIME_AXIS) is not None
            }
        )
        >= 2
    )
    if not bases:
        return "fewer than two grade counts measured on any randomly graded case"
    rows = [row for base in bases for row in by_base[base]]
    figure, axes_list = series_panels(width, SERIES_HEIGHT_INCHES, len(bases))
    for axes, base in zip(axes_list, bases):
        group = by_base[base]
        panel_tools = tools_present(tables, group, TIME_AXIS)
        for tool in panel_tools:
            points = [
                (number_of(row, "grade_count"), row) for row in group if row["tool"] == tool
            ]
            plot_series(axes, tables, tool, points, TIME_AXIS, connect=True)
        counts = sorted({number_of(row, "grade_count") for row in group})
        axes.set_xscale("log")
        axes.xaxis.set_major_locator(FixedLocator(counts))
        axes.set_xticklabels(
            [str(int(count)) for count in counts],
            rotation=35,
            ha="right",
            rotation_mode="anchor",
        )
        axes.xaxis.set_minor_locator(NullLocator())
        log_scale(axes, "y")
        case_axis_label(axes, "grades in the filtration", case_label(base))
    axes_list[0].set_ylabel("wall time (s)")
    return finish_figure(
        figure, tool_handles(tools_present(tables, rows, TIME_AXIS), True), width
    )


def plot_rows(axes, tables, rows, names, tools, axis):
    """One row per case, the tools spread along the axis of that row, for a set
    of cases that has no measure to put them in order along."""
    positions = {name: index for index, name in enumerate(names)}
    for index in range(0, len(names), 2):
        axes.axhspan(index - 0.5, index + 0.5, color=BAND, linewidth=0, zorder=0)
    for tool in tools:
        points = [
            (positions[row["case"]], row)
            for row in rows
            if row["tool"] == tool and row["case"] in positions
        ]
        plot_series(axes, tables, tool, points, axis, False, horizontal=True)
    log_scale(axes, "x")
    if axis == MEMORY_AXIS:
        axes.axvline(tables.tier.memory_limit_gigabytes, **CAP_LINE)
    axes.grid(axis="y", visible=False)
    axes.grid(axis="x", visible=True)
    axes.set_yticks(range(len(names)))
    axes.set_ylim(len(names) - 0.5, -0.5)
    axes.tick_params(axis="y", length=0)
    axes.spines["left"].set_visible(False)


def draw_published_sets(tables, width, label):
    """The published image volumes, thresholded and graded by intensity, in two
    blocks: wall time beside peak memory, one row per volume."""
    rows = [
        row
        for row in cross_tool_rows(tables)
        if row["family"] == PUBLISHED_FAMILY and row["case"].endswith(PUBLISHED_SUFFIXES)
    ]
    note_errors(label, rows)
    tools = tools_present(tables, rows, TIME_AXIS)
    if not tools:
        return "no measured run on a published volume at full resolution in the tables"
    cubes = {row["case"]: number_of(row, "cube_count") for row in rows}
    drawn = drawn_cases(tables, rows, TIME_AXIS)
    blocks = []
    for suffix, title in (
        (THRESHOLDED_SUFFIX, "thresholded"),
        (INTENSITY_SUFFIX, "graded by intensity"),
    ):
        names = sorted(
            (name for name in drawn if name.endswith(suffix)), key=lambda n: cubes[n]
        )
        if names:
            blocks.append((title, suffix, names))
    height = ROW_HEIGHT_INCHES * sum(len(names) for _, _, names in blocks) + 1.7
    figure, grid = pyplot.subplots(
        len(blocks),
        2,
        figsize=(width, height),
        squeeze=False,
        sharex="col",
        sharey="row",
        gridspec_kw={"height_ratios": [len(names) for _, _, names in blocks]},
    )
    for line, (title, suffix, names) in enumerate(blocks):
        for column, axis in enumerate((TIME_AXIS, MEMORY_AXIS)):
            plot_rows(grid[line][column], tables, rows, names, tools, axis)
        grid[line][0].set_yticklabels(
            [case_label(name[: -len(suffix)]) for name in names]
        )
        grid[line][0].set_title(title, loc="left", fontsize=9, color=INK)
    grid[-1][0].set_xlabel("wall time (s)")
    grid[-1][1].set_xlabel("peak memory (GB)")
    return finish_figure(figure, tool_handles(tools, False), width)


def stage_totals(tables):
    """The seconds each case spent in the driver's stages, on the configuration
    the comparison uses."""
    totals = {}
    for row in tables.stages:
        if row["config"] == FULL_CONFIG:
            case = totals.setdefault(row["case"], {})
            case[row["stage"]] = case.get(row["stage"], 0.0) + float(row["seconds_median"])
    return totals


def stage_case_groups(tables, totals):
    """The cases the stage figure draws: the costliest of each family, one per
    shape or system, and for the graded cases the least and greatest grade count
    of the costliest base."""
    shape = {}
    for row in tables.runs:
        if row["tool"] == manifest.CHOMP3RS and row["case"] in totals:
            shape[row["case"]] = (row["family"], row["graded"] == "true", row["grade_count"])
    cost = {case: sum(stages.values()) for case, stages in totals.items()}

    def largest(predicate, limit):
        chosen = {}
        for case, (family, graded, _) in shape.items():
            if not predicate(case, family, graded):
                continue
            key = STAGE_SIZE_TOKEN.sub("", case)
            if key not in chosen or cost[case] > cost[chosen[key]]:
                chosen[key] = case
        return sorted(chosen.values(), key=lambda case: -cost[case])[:limit]

    groups = [
        ("flow covers", largest(lambda c, f, g: f == "flows" and not g, 3)),
        (
            "manifolds",
            largest(lambda c, f, g: f in ("s1", "torus", "curve") and not g, 3),
        ),
        ("random cubes", largest(lambda c, f, g: f in ("random_top", MIXED_FAMILY) and not g, 3)),
        (
            "images, thresholded",
            largest(lambda c, f, g: f == PUBLISHED_FAMILY and c.endswith(THRESHOLDED_SUFFIX), 2),
        ),
        (
            "images, graded by intensity",
            largest(lambda c, f, g: f == PUBLISHED_FAMILY and c.endswith(INTENSITY_SUFFIX), 2),
        ),
    ]
    graded = [case for case, (_, is_graded, _) in shape.items() if is_graded and GRADED_CASE.match(case)]
    if graded:
        base = max(
            {GRADED_CASE.match(case).group(1) for case in graded},
            key=lambda name: max(
                cost[case] for case in graded if GRADED_CASE.match(case).group(1) == name
            ),
        )
        counts = sorted(
            (case for case in graded if GRADED_CASE.match(case).group(1) == base),
            key=lambda case: int(GRADED_CASE.match(case).group(2)),
        )
        groups.insert(2, ("randomly graded", [counts[0], counts[-1]] if len(counts) > 1 else counts))
    return [(title, names) for title, names in groups if names]


def draw_stage_shares(tables, width, label):
    """Where CHomP3-rs spends its time: the share of its stage total each stage
    takes, one row per case grouped by family, with the stage total beside it."""
    totals = stage_totals(tables)
    if not totals:
        return "no CHomP3-rs stage timing in the tables"
    groups = stage_case_groups(tables, totals)
    if not groups:
        return "no case with a stage timing and a row in the runs table"
    count = sum(len(names) for _, names in groups)
    height = ROW_HEIGHT_INCHES * count + 0.32 * len(groups) + 1.0
    figure, grid = pyplot.subplots(
        len(groups),
        2,
        figsize=(width, height),
        squeeze=False,
        sharex="col",
        gridspec_kw={"height_ratios": [len(names) for _, names in groups], "width_ratios": [3.0, 1.0]},
    )
    for line, (title, names) in enumerate(groups):
        left, right = grid[line]
        for index, name in enumerate(names):
            total = sum(totals[name].values())
            start = 0.0
            for position, (_, members) in enumerate(STAGE_BARS):
                share = 100 * sum(totals[name].get(m, 0.0) for m in members) / total
                if share <= 0:
                    continue
                left.barh(
                    index,
                    max(share - 0.5, 0.15),
                    left=start + 0.25,
                    height=0.64,
                    color=STAGE_RAMP[position],
                    linewidth=0,
                    zorder=2,
                )
                if share >= STAGE_LABEL_INSIDE:
                    left.text(
                        start + share / 2,
                        index,
                        f"{share:.0f}\\%",
                        ha="center",
                        va="center",
                        fontsize=7,
                        color=INK if position < 2 else SURFACE,
                        zorder=3,
                    )
                start += share
            right.plot(
                [total],
                [index],
                linestyle="none",
                zorder=4,
                **marker_arguments(manifest.CHOMP3RS, FILLED_POINT),
            )
        for axes in (left, right):
            axes.set_ylim(len(names) - 0.5, -0.5)
            axes.set_yticks(range(len(names)))
            axes.tick_params(axis="y", length=0)
            axes.spines["left"].set_visible(False)
            axes.grid(axis="y", visible=False)
            if line < len(groups) - 1:
                axes.spines["bottom"].set_visible(False)
                axes.tick_params(axis="x", which="both", length=0)
        left.set_yticklabels([case_label(name) for name in names])
        right.set_yticklabels([])
        left.set_xlim(0, 100)
        right.grid(axis="x", visible=True)
        left.set_title(title, loc="left", fontsize=9, color=INK)
    log_scale(grid[-1][1], "x", numticks=6)
    grid[-1][0].set_xlabel("share of the CHomP3-rs stage total (\\%)")
    grid[-1][1].set_xlabel("stage total (s)")
    handles = [
        Patch(facecolor=STAGE_RAMP[position], label=name)
        for position, (name, _) in enumerate(STAGE_BARS)
    ]
    figure.legend(
        handles=handles,
        loc="outside upper center",
        ncol=len(STAGE_BARS),
        handlelength=1.4,
        borderaxespad=0.2,
    )
    return figure, ""


def coverage_kind(row):
    """What a cell of the coverage matrix shows: the status of the run, or for
    a run the tier skipped, the kind of rule that refused it."""
    if row["status"] != summarize.SKIPPED:
        return row["status"]
    reason = row["skip_reason"]
    if reason.endswith("GB cap"):
        return "memory"
    if "above limit" in reason:
        return "dimension"
    if "timeout" in reason:
        return "time"
    return "input"


def draw_coverage(tables, width, label):
    """The working view of a tier rather than a figure of the paper: one cell
    per tool and ungraded case, showing which tools finished, were stopped, were
    killed, or refused the case and by which kind of rule."""
    rows = [row for row in cross_tool_rows(tables) if row["graded"] == "false"]
    if not rows:
        return "no ungraded case in the tables"
    families = []
    cases = {}
    for row in rows:
        if row["family"] not in cases:
            families.append(row["family"])
            cases[row["family"]] = []
        if row["case"] not in cases[row["family"]]:
            cases[row["family"]].append(row["case"])
    names = [name for family in families for name in cases[family]]
    kind_of = {(row["case"], row["tool"]): coverage_kind(row) for row in rows}
    figure, axes = pyplot.subplots(figsize=(width, 2.6))
    axes.grid(False)
    for spine in axes.spines.values():
        spine.set_visible(False)
    present = set()
    for column, name in enumerate(names):
        for line, tool in enumerate(TOOL_ORDER):
            kind = kind_of.get((name, tool), "absent")
            present.add(kind)
            axes.add_patch(
                Rectangle(
                    (column + 0.06, line + 0.06),
                    0.88,
                    0.88,
                    facecolor=COVERAGE_COLORS[kind][0],
                    edgecolor=SPINE if kind == "absent" else "none",
                    linewidth=0.3,
                )
            )
    start = 0
    for family in families:
        count = len(cases[family])
        axes.plot(
            [start + 0.1, start + count - 0.1],
            [-0.35, -0.35],
            color=INK,
            linewidth=0.6,
            clip_on=False,
        )
        axes.text(
            start + count / 2,
            -0.55,
            case_label(family),
            ha="left",
            va="bottom",
            fontsize=8,
            rotation=35,
            rotation_mode="anchor",
        )
        start += count
    axes.set_xlim(0, len(names))
    axes.set_ylim(len(TOOL_ORDER), 0)
    axes.set_xticks([])
    axes.set_yticks([line + 0.5 for line in range(len(TOOL_ORDER))])
    axes.set_yticklabels([TOOL_STYLE[tool]["label"] for tool in TOOL_ORDER])
    axes.tick_params(length=0)
    axes.set_xlabel(
        f"the {len(names)} ungraded cases of the {tables.tier.name} tier,"
        " in manifest order, grouped by family"
    )
    handles = [
        Patch(
            facecolor=COVERAGE_COLORS[kind][0],
            edgecolor=SPINE if kind == "absent" else "none",
            linewidth=0.5,
            label=COVERAGE_COLORS[kind][1],
        )
        for kind in COVERAGE_ORDER
        if kind in present
    ]
    figure.legend(
        handles=handles,
        loc="outside lower center",
        ncol=3,
        handlelength=1.2,
        handleheight=1.0,
        borderaxespad=0.2,
    )
    return figure, ""


FIGURES = (
    (1, "flow_ladders", PAGE_WIDTH_INCHES, draw_flow_ladders),
    (2, "dimension_manifolds", PAGE_WIDTH_INCHES, draw_dimension_manifolds),
    (3, "density_random_top", PAGE_WIDTH_INCHES, draw_density_random_top),
    (4, "mixed_dimension", PAGE_WIDTH_INCHES, draw_mixed_dimension),
    (5, "grade_count", PAGE_WIDTH_INCHES, draw_grade_count),
    (6, "published_sets", PAGE_WIDTH_INCHES, draw_published_sets),
    (7, "stage_shares", PAGE_WIDTH_INCHES, draw_stage_shares),
    (8, "coverage", PAGE_WIDTH_INCHES, draw_coverage),
)
