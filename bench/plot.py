"""The figures: the summary tables of a tier turned into the paper's plots.

Reads `results/summary/<tier>/runs.csv` and `stages.csv` and writes
`figures/<tier>/fig<NN>_<name>.pdf` and `.png`, one pair per figure of
`FIGURES`. A figure whose cases or tools are not in the tables is not drawn and
prints one line saying what is missing.

The figures are typeset for a 12 pt page with a 448 pt text block: text is set
by LuaLaTeX in STIX Two Text and STIX Two Math, a wide figure is the width of
the text block and a narrow one 300 pt, and no figure carries a title, the
caption naming it instead. After every PDF is written one line prints its page
size in points and the fonts it embeds, so a wrong width or a font that fell
back shows in the terminal. Where a figure fixes a parameter when it is drawn,
such as the baseline the speedups are taken over, the same line says which,
for the caption to repeat.

A mark on a time axis is a measurement and nothing else. A run the tier stopped,
out of time or killed for memory, leaves its case without a mark for that tool,
and the last figure, the coverage matrix, shows for every case of the tier
which tools finished, were stopped, were killed, or refused it and why. On a
memory axis a killed run reached the cap, so it sits on the cap line as an open
marker. A group whose repetitions ended differently takes the worst of their
statuses, a run the tier skipped is not drawn, and a run that ended in an error
is not drawn either but is named in a printed note. A run whose answer the check
disputed is drawn where it landed inside a black ring. The legend of every
figure names the conventions that figure uses.

Every time axis carries each tool's start-up, its wall time on `ball_d2_r0`, a
single cube, as a short stroke in the tool's colour at the edge of the axis. A
case on which every tool that finished did so within three times its start-up
measures starting the tools rather than their work, so the figures that compare
tools on time leave it out; it stays in the correctness check and the coverage
matrix. The sphere figure keeps every sphere, since its point is where the
tools' times leave their start-up.

Figure 4 reads `figures/reference/table1.csv`, the published sphere timings it
compares against.

Drawing needs LuaLaTeX with the STIX Two fonts, both part of TeX Live. Invoked
as `bench plot <tier>`; see `bench.cli`.
"""

import csv
import re
import statistics
import zlib
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from types import SimpleNamespace

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

from bench import dense, manifest, summarize
from bench.adapters import cubical_ripser, gudhi, pychomp2

SUMMARY_DIRECTORY = Path("results/summary")
FIGURE_DIRECTORY = Path("figures")
REFERENCE_TABLE = FIGURE_DIRECTORY / "reference" / "table1.csv"

POINTS_PER_INCH = 72.27
TEXT_WIDTH_POINTS = 448.0
PAGE_WIDTH_INCHES = TEXT_WIDTH_POINTS / POINTS_PER_INCH
COLUMN_WIDTH_INCHES = 300.0 / POINTS_PER_INCH
ROW_HEIGHT_INCHES = 0.28
SERIES_HEIGHT_INCHES = 3.0

FULL_CONFIG = "full"
TIME_AXIS = "time"
MEMORY_AXIS = "memory"
KILOBYTES_PER_GIGABYTE = 1024 * 1024
BYTES_PER_GIGABYTE = 1024**3

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
START_UP_WIDTH = 1.6
START_UP_LENGTH = 0.035

COVERAGE_COLORS = {
    summarize.FINISHED: (OKABE_BLUE, "finished"),
    summarize.DISPUTED: (OKABE_BLUE, "finished"),
    summarize.TIMEOUT: (OKABE_ORANGE, "stopped at the timeout"),
    summarize.OUT_OF_MEMORY: (OKABE_VERMILLION, "killed at the memory cap"),
    summarize.ERROR: (INK, "ended in an error"),
    "memory": ("#bdbcb7", "refused: memory over the cap"),
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
    "dimension",
    "input",
    "absent",
)

START_UP_CASE = "ball_d2_r0"
START_UP_MULTIPLE = 3.0

FLOW_LADDERS = (
    ("lorenz_d6", "Lorenz, $d = 6$"),
    ("dadras_d8", "Dadras, $d = 8$"),
)
HIGH_DIMENSIONAL_FLOWS = (
    ("charney_devore_d12_box", "Charney-DeVore, $d = 12$, one trajectory at five box sizes", "o", True),
    ("kuramoto_sivashinsky_d16_", "Kuramoto-Sivashinsky, $d = 16$", "s", False),
)
MANIFOLD_PANELS = (
    ("circle", re.compile(r"^s1_d\d+$")),
    ("torus", re.compile(r"^torus_d\d+$")),
    ("curve of 2000 samples", re.compile(r"^curve_d\d+_n2000$")),
)
MIXED_FAMILY = "random_mixed"
PUBLISHED_FAMILY = "published"
PUBLISHED_SUFFIXES = ("_full", "_intensity")

THREAD_CONFIGS = ("threads_1", "threads_2", "threads_4", "threads_8", "threads_16")
SPEEDUP_BASELINES = ("threads_1", FULL_CONFIG)
PHYSICAL_CORES = 8
THREAD_RAMP = ("#9ecae1", "#08306b")

MEMORY_GROUPS = (
    (3, 3, "$d = 3$"),
    (4, 8, "$d$ from 4 to 8"),
    (9, None, "$d$ of 9 and above"),
)

LADDER_CASE = re.compile(r"^(.+)_box([0-9.]+)$")
SPHERE_CASE = re.compile(r"^sphere_d(\d+)$")
DENSITY_CASE = re.compile(r"^random_top_d(\d+)_side(\d+)_p([0-9.]+)_draw(\d+)$")
GRADED_CASE = re.compile(r"^(.+)_random_g(\d+)$")
FONT_NAME = re.compile(rb"/BaseFont\s*/(?:[A-Z]{6}\+)?([A-Za-z0-9-]+)")
PDF_STREAM = re.compile(rb"stream\r?\n(.*?)endstream", re.S)

SECONDS_PER_UNIT = {"ns": 1e-9, "us": 1e-6, "ms": 1e-3, "s": 1.0, "m": 60.0}

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


def start_up_seconds(tables):
    """Each tool's wall time on the single cube, where it finished."""
    return {
        row["tool"]: number_of(row, "wall_median")
        for row in cross_tool_rows(tables)
        if row["case"] == START_UP_CASE and row["status"] in summarize.COMPARABLE
    }


def timed_rows(tables):
    """The cross-tool rows of the cases that measure work: the single cube is
    left out, and so is every case on which each tool that finished did so
    within `START_UP_MULTIPLE` times its start-up."""
    floors = start_up_seconds(tables)
    near = {}
    for row in cross_tool_rows(tables):
        if row["status"] in summarize.COMPARABLE and row["tool"] in floors:
            near.setdefault(row["case"], []).append(
                number_of(row, "wall_median") < START_UP_MULTIPLE * floors[row["tool"]]
            )
    left_out = {case for case, flags in near.items() if all(flags)} | {START_UP_CASE}
    return [row for row in cross_tool_rows(tables) if row["case"] not in left_out]


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


def plot_series(axes, tables, tool, points, axis, connect, horizontal=False):
    """One tool's points, joined by the tool's line through the measurements
    when the axis reads as a series. A run the cap killed is drawn on the cap
    line of a memory axis and is never joined."""
    placed = []
    for position, row in points:
        point = point_of(tables, row, axis)
        if point is not None:
            placed.append((position, point[0], point[1], row["status"]))
    placed.sort(key=lambda entry: entry[0])
    joined = [entry for entry in placed if entry[2] == FILLED_POINT]
    if connect and len(joined) > 1:
        positions = [entry[0] for entry in joined]
        values = [entry[1] for entry in joined]
        axes.plot(
            *((values, positions) if horizontal else (positions, values)),
            color=TOOL_STYLE[tool]["color"],
            linewidth=LINE_WIDTH,
            zorder=2,
        )
    for position, value, convention, status in placed:
        shown = OPEN_POINT if convention == KILLED_POINT else FILLED_POINT
        coordinates = ([value], [position]) if horizontal else ([position], [value])
        axes.plot(
            *coordinates, linestyle="none", zorder=3, **marker_arguments(tool, shown)
        )
        if status == summarize.DISPUTED:
            axes.plot(
                *coordinates, linestyle="none", zorder=4, **disputed_ring_arguments()
            )


def draw_start_up(axes, floors, tools, horizontal=False):
    """Each tool's start-up as a short stroke in its colour at the far edge of
    the time axis, inside the right edge where time runs up the page and just
    above the top where it runs across, away from the fastest marks; says
    whether any was drawn."""
    drawn = False
    for tool in tools:
        if tool not in floors:
            continue
        seconds = floors[tool]
        if horizontal:
            coordinates = ([seconds, seconds], [1.0, 1.0 + START_UP_LENGTH])
            transform = axes.get_xaxis_transform()
        else:
            coordinates = ([1.0 - START_UP_LENGTH, 1.0], [seconds, seconds])
            transform = axes.get_yaxis_transform()
        axes.plot(
            *coordinates,
            transform=transform,
            color=TOOL_STYLE[tool]["color"],
            linewidth=START_UP_WIDTH,
            solid_capstyle="butt",
            clip_on=False,
            zorder=5,
        )
        drawn = True
    if drawn and not horizontal:
        widen_right(axes, 2.5 * START_UP_LENGTH)
    return drawn


def widen_right(axes, share):
    """Extend the horizontal axis to the right by `share` of its width, so that
    no mark sits under the strokes at the right edge."""
    low, high = axes.get_xlim()
    if axes.get_xscale() == "log":
        axes.set_xlim(low, high * (high / low) ** share)
    else:
        axes.set_xlim(low, high + (high - low) * share)


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


def note_handle(label, convention):
    arguments = marker_arguments(manifest.CHOMP3RS, convention)
    arguments["markeredgecolor"] = REFERENCE_COLOR
    return Line2D([], [], label=label, linestyle="none", **arguments)


def convention_handles(tables, rows, axis, start_up_drawn):
    """The legend entries for the conventions this figure actually uses, so that
    a figure without a killed run or a disputed answer carries no explanation of
    one."""
    handles = []
    if start_up_drawn:
        handles.append(
            Line2D(
                [],
                [],
                label="stroke at the axis edge, in the tool's colour: its start-up on one cube",
                color=REFERENCE_COLOR,
                linewidth=START_UP_WIDTH,
                solid_capstyle="butt",
            )
        )
    drawn = [point_of(tables, row, axis) for row in rows]
    if axis == MEMORY_AXIS:
        cap = tables.tier.memory_limit_gigabytes
        if any(point is not None and point[1] == KILLED_POINT for point in drawn):
            handles.append(
                note_handle(
                    f"open marker on the cap line: killed at the {cap} GB cap", OPEN_POINT
                )
            )
        if any(row["status"] == summarize.TIMEOUT for row in rows):
            handles.append(
                Line2D(
                    [],
                    [],
                    label=(
                        f"stopped at the {tables.tier.timeout_seconds} s timeout:"
                        " no peak measured, not drawn"
                    ),
                    linestyle="none",
                    marker="none",
                )
            )
    if any(
        row["status"] == summarize.DISPUTED and point is not None
        for row, point in zip(rows, drawn)
    ):
        handles.append(
            Line2D(
                [],
                [],
                label="black ring: answer disputed",
                linestyle="none",
                **disputed_ring_arguments(),
            )
        )
    return handles


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


def label_narrow_log(axes, which):
    """Label the minor ticks too, as plain numbers, where a logarithmic axis
    spans less than two decades and would otherwise carry one label or none."""
    low, high = axes.get_xlim() if which == "x" else axes.get_ylim()
    low, high = sorted((low, high))
    if low <= 0 or high / low >= 100:
        return
    axis = axes.xaxis if which == "x" else axes.yaxis
    plain = FuncFormatter(lambda value, _: f"{value:g}")
    axis.set_major_formatter(plain)
    axis.set_minor_formatter(plain)


def integer_ticks(axes, values):
    """Ticks at the integers a series was measured at and nowhere else."""
    values = sorted(set(values))
    axes.xaxis.set_major_locator(FixedLocator(values))
    axes.set_xticklabels([str(int(value)) for value in values])
    axes.set_xlim(values[0] - 0.3, values[-1] + 0.3)


def legend_columns(handles, width):
    """As many columns as the longest entry leaves room for across the figure."""
    longest = max(len(handle.get_label()) for handle in handles)
    entry = 0.4 + longest * 0.058
    return max(1, min(4, int(width / entry), len(handles)))


def finish_figure(figure, series, notes, width, chosen=""):
    """The legend of the series above the axes and, when the figure uses one,
    the legend of the conventions below them, both placed by the layout."""
    figure.legend(
        handles=series,
        loc="outside upper center",
        ncol=legend_columns(series, width),
        handlelength=1.8,
        borderaxespad=0.2,
    )
    if notes:
        figure.legend(
            handles=notes,
            loc="outside lower center",
            ncol=legend_columns(notes, width),
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


def plot_rows(axes, tables, rows, names, tools):
    """One row per case, the tools spread along the time axis of that row, for
    a set of cases that has no measure to put them in order along."""
    positions = {name: index for index, name in enumerate(names)}
    for index in range(0, len(names), 2):
        axes.axhspan(index - 0.5, index + 0.5, color=BAND, linewidth=0, zorder=0)
    for tool in tools:
        points = [
            (positions[row["case"]], row)
            for row in rows
            if row["tool"] == tool and row["case"] in positions
        ]
        plot_series(axes, tables, tool, points, TIME_AXIS, False, horizontal=True)
    log_scale(axes, "x")
    axes.grid(axis="y", visible=False)
    axes.grid(axis="x", visible=True)
    axes.set_yticks(range(len(names)))
    axes.set_yticklabels([case_label(name) for name in names])
    axes.set_ylim(len(names) - 0.5, -0.5)
    axes.tick_params(axis="y", length=0)
    axes.spines["left"].set_visible(False)
    axes.set_xlabel("wall time (s)")


def rows_height(names):
    return ROW_HEIGHT_INCHES * len(names) + 0.9


def draw_rows_figure(tables, width, rows, names, tools):
    figure, axes = pyplot.subplots(figsize=(width, rows_height(names)))
    plot_rows(axes, tables, rows, names, tools)
    start_up_drawn = draw_start_up(
        axes, start_up_seconds(tables), tools, horizontal=True
    )
    return finish_figure(
        figure,
        tool_handles(tools, False),
        convention_handles(tables, rows, TIME_AXIS, start_up_drawn),
        width,
    )


def draw_flow_ladders(tables, width, label):
    """Wall time against cube count on the Lorenz and Dadras covers, each one
    trajectory at several box sizes, one panel per system."""
    prefixes = dict(FLOW_LADDERS)
    rows = [
        row
        for row in timed_rows(tables)
        if (match := LADDER_CASE.match(row["case"])) and match.group(1) in prefixes
    ]
    note_errors(label, rows)
    panels = [
        (prefix, title)
        for prefix, title in FLOW_LADDERS
        if drawn_cases(
            tables,
            [row for row in rows if LADDER_CASE.match(row["case"]).group(1) == prefix],
            TIME_AXIS,
        )
    ]
    if not panels:
        return "no measured run on the Lorenz or Dadras covers in the tables"
    floors = start_up_seconds(tables)
    figure, axes_list = series_panels(
        width, SERIES_HEIGHT_INCHES, len(panels), share_y=True
    )
    start_up_drawn = False
    for axes, (prefix, title) in zip(axes_list, panels):
        panel_rows = [
            row for row in rows if LADDER_CASE.match(row["case"]).group(1) == prefix
        ]
        panel_tools = tools_present(tables, panel_rows, TIME_AXIS)
        for tool in panel_tools:
            points = [
                (number_of(row, "cube_count"), row)
                for row in panel_rows
                if row["tool"] == tool
            ]
            plot_series(axes, tables, tool, points, TIME_AXIS, connect=True)
        log_scale(axes, "x")
        log_scale(axes, "y")
        label_narrow_log(axes, "x")
        axes.set_xlabel(f"cubes in the cover, {title}")
        start_up_drawn |= draw_start_up(axes, floors, panel_tools)
    axes_list[0].set_ylabel("wall time (s)")
    return finish_figure(
        figure,
        tool_handles(tools_present(tables, rows, TIME_AXIS), True),
        convention_handles(tables, rows, TIME_AXIS, start_up_drawn),
        width,
    )


def draw_high_dimensional_flows(tables, width, label):
    """CHomP3-rs alone on the flow covers of dimension 12 and 16, which no
    competing tool finishes: wall time against cube count."""
    prefixes = tuple(prefix for prefix, *_ in HIGH_DIMENSIONAL_FLOWS)
    rows = [
        row
        for row in tables.runs
        if row["tool"] == manifest.CHOMP3RS
        and row["config"] == FULL_CONFIG
        and row["case"].startswith(prefixes)
    ]
    note_errors(label, rows)
    groups = []
    for prefix, title, marker, connect in HIGH_DIMENSIONAL_FLOWS:
        points = sorted(
            (number_of(row, "cube_count"), number_of(row, "wall_median"), row["status"])
            for row in rows
            if row["case"].startswith(prefix) and row["status"] in summarize.COMPARABLE
        )
        if points:
            groups.append((title, marker, connect, points))
    if not groups:
        return "no measured CHomP3-rs run on the flow covers of dimension 12 or 16"
    figure, (axes,) = series_panels(width, SERIES_HEIGHT_INCHES, 1)
    series = []
    for title, marker, connect, points in groups:
        if connect and len(points) > 1:
            axes.plot(
                [point[0] for point in points],
                [point[1] for point in points],
                color="#000000",
                linewidth=LINE_WIDTH,
                zorder=2,
            )
        for cubes, seconds, status in points:
            axes.plot(
                [cubes],
                [seconds],
                linestyle="none",
                marker=marker,
                markersize=5.0,
                markerfacecolor="#000000",
                markeredgecolor=SURFACE,
                markeredgewidth=0.5,
                zorder=3,
            )
            if status == summarize.DISPUTED:
                axes.plot(
                    [cubes], [seconds], linestyle="none", zorder=4, **disputed_ring_arguments()
                )
        series.append(
            Line2D(
                [],
                [],
                label=title,
                color="#000000",
                linestyle="-" if connect else "none",
                linewidth=LINE_WIDTH,
                marker=marker,
                markersize=5.0,
                markerfacecolor="#000000",
                markeredgecolor=SURFACE,
            )
        )
    log_scale(axes, "x")
    log_scale(axes, "y")
    label_narrow_log(axes, "x")
    label_narrow_log(axes, "y")
    axes.set_xlabel("cubes in the cover")
    axes.set_ylabel("wall time (s)")
    return finish_figure(
        figure, series, convention_handles(tables, rows, TIME_AXIS, False), width
    )


def draw_dimension_manifolds(tables, width, label):
    rows = [
        row
        for row in timed_rows(tables)
        if row["graded"] == "false"
        and any(pattern.match(row["case"]) for _, pattern in MANIFOLD_PANELS)
    ]
    note_errors(label, rows)
    panels = [
        (title, pattern)
        for title, pattern in MANIFOLD_PANELS
        if drawn_cases(
            tables, [row for row in rows if pattern.match(row["case"])], TIME_AXIS
        )
    ]
    if not panels:
        return "no measured run on an ungraded circle, torus or curve case in the tables"
    floors = start_up_seconds(tables)
    figure, axes_list = series_panels(
        width, SERIES_HEIGHT_INCHES, len(panels), share_y=True
    )
    start_up_drawn = False
    for axes, (title, pattern) in zip(axes_list, panels):
        panel_rows = [row for row in rows if pattern.match(row["case"])]
        panel_tools = tools_present(tables, panel_rows, TIME_AXIS)
        dimensions = []
        for tool in panel_tools:
            points = [
                (number_of(row, "ambient_dimension"), row)
                for row in panel_rows
                if row["tool"] == tool
            ]
            dimensions += [
                position
                for position, row in points
                if point_of(tables, row, TIME_AXIS) is not None
            ]
            plot_series(axes, tables, tool, points, TIME_AXIS, connect=True)
        log_scale(axes, "y")
        integer_ticks(axes, dimensions)
        axes.set_xlabel(f"ambient dimension $d$\n{title}")
        start_up_drawn |= draw_start_up(axes, floors, panel_tools)
    axes_list[0].set_ylabel("wall time (s)")
    return finish_figure(
        figure,
        tool_handles(tools_present(tables, rows, TIME_AXIS), True),
        convention_handles(tables, rows, TIME_AXIS, start_up_drawn),
        width,
    )


def elapsed_seconds(text):
    """A Table 1(a) time cell in seconds, its stated uncertainty dropped."""
    words = text.split("+/-")[0].split()
    return sum(
        float(amount) * SECONDS_PER_UNIT[unit]
        for amount, unit in zip(words[0::2], words[1::2])
    )


def draw_sphere_table1(tables, width, label):
    """The sphere_d<k> cases beside the published times for the same complex.
    Each sphere_d<k> case lists the 2d facets of the d-cube and the complex is
    their closure, which is the paper's S^d: the two sides compute the same
    3^d - 1 cells. The published times are taken inside one process, so
    CHomP3-rs's own stage total is drawn beside its wall time."""
    rows = [row for row in cross_tool_rows(tables) if SPHERE_CASE.match(row["case"])]
    note_errors(label, rows)
    tools = tools_present(tables, rows, TIME_AXIS)
    if not tools:
        return "no measured run on a sphere case in the tables"
    reference = read_rows(REFERENCE_TABLE)
    figure, (axes,) = series_panels(width, SERIES_HEIGHT_INCHES, 1)
    dimensions = [float(entry["dimension"]) for entry in reference]
    for tool in tools:
        points = [
            (number_of(row, "ambient_dimension"), row)
            for row in rows
            if row["tool"] == tool
        ]
        dimensions += [
            position
            for position, row in points
            if point_of(tables, row, TIME_AXIS) is not None
        ]
        plot_series(axes, tables, tool, points, TIME_AXIS, connect=True)
    own = {}
    for row in tables.stages:
        match = SPHERE_CASE.match(row["case"])
        if match and row["config"] == FULL_CONFIG:
            dimension = float(match.group(1))
            own[dimension] = own.get(dimension, 0.0) + float(row["seconds_median"])
    stage_style = {
        "color": "#000000",
        "linestyle": (0, (1.0, 1.5)),
        "linewidth": LINE_WIDTH,
        "marker": "o",
        "markersize": 4.0,
        "markerfacecolor": SURFACE,
        "markeredgecolor": "#000000",
        "markeredgewidth": 0.8,
    }
    if own:
        ordered = sorted(own)
        axes.plot(ordered, [own[dimension] for dimension in ordered], zorder=2, **stage_style)
    reference_style = {
        "color": REFERENCE_COLOR,
        "linestyle": (0, (2.0, 1.5)),
        "linewidth": LINE_WIDTH,
        "marker": "+",
        "markersize": 5.0,
    }
    axes.plot(
        [float(entry["dimension"]) for entry in reference],
        [elapsed_seconds(entry["time_elapsed"]) for entry in reference],
        zorder=2,
        **reference_style,
    )
    log_scale(axes, "y")
    integer_ticks(axes, dimensions)
    even = [value for value in sorted(set(dimensions)) if value % 2 == 0]
    axes.xaxis.set_major_locator(FixedLocator(even))
    axes.set_xticklabels([str(int(value)) for value in even])
    axes.set_xlabel("ambient dimension $d$")
    axes.set_ylabel("wall time (s)")
    start_up_drawn = draw_start_up(axes, start_up_seconds(tables), tools)
    series = tool_handles(tools, True)
    if own:
        series.append(
            Line2D([], [], label="CHomP3-rs, its stages alone, without start-up", **stage_style)
        )
    series.append(
        Line2D([], [], label="arXiv:2105.09870 Table 1(a), one core", **reference_style)
    )
    return finish_figure(
        figure,
        series,
        convention_handles(tables, rows, TIME_AXIS, start_up_drawn),
        width,
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
    floors = start_up_seconds(tables)
    rows = [row for key in panels for _, row in groups[key]]
    figure, axes_list = series_panels(width, SERIES_HEIGHT_INCHES, len(panels))
    start_up_drawn = False
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
        axes.set_xlabel(f"share of positions holding a cube\n$d = {dimension}$, side {side}")
        start_up_drawn |= draw_start_up(axes, floors, panel_tools)
    axes_list[0].set_ylabel("wall time (s)")
    return finish_figure(
        figure,
        tool_handles(tools_present(tables, rows, TIME_AXIS), True),
        convention_handles(tables, rows, TIME_AXIS, start_up_drawn),
        width,
        chosen=f", each point the median and range over {len(draws)} draws",
    )


def draw_mixed_dimension(tables, width, label):
    rows = [
        row
        for row in timed_rows(tables)
        if row["family"] == MIXED_FAMILY and row["status"] != summarize.SKIPPED
    ]
    note_errors(label, rows)
    tools = tools_present(tables, rows, TIME_AXIS)
    if not tools:
        return "no measured run on a random mixed-dimension case in the tables"
    shape_of = {
        row["case"]: (number_of(row, "ambient_dimension"), number_of(row, "cube_count"))
        for row in rows
    }
    names = sorted(
        drawn_cases(tables, rows, TIME_AXIS), key=lambda name: shape_of[name] + (name,)
    )
    return draw_rows_figure(tables, width, rows, names, tools)


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
    floors = start_up_seconds(tables)
    rows = [row for base in bases for row in by_base[base]]
    figure, axes_list = series_panels(width, SERIES_HEIGHT_INCHES, len(bases))
    start_up_drawn = False
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
        axes.set_xlabel(f"grades in the filtration\n{case_label(base)}")
        start_up_drawn |= draw_start_up(axes, floors, panel_tools)
    axes_list[0].set_ylabel("wall time (s)")
    return finish_figure(
        figure,
        tool_handles(tools_present(tables, rows, TIME_AXIS), True),
        convention_handles(tables, rows, TIME_AXIS, start_up_drawn),
        width,
    )


def color_ramp(count):
    """`count` shades of one blue, light to dark."""
    start, end = (numpy.array(to_rgb(color)) for color in THREAD_RAMP)
    return [
        to_hex(start + (end - start) * (index / max(1, count - 1)))
        for index in range(count)
    ]


def draw_thread_scaling(tables, width, label):
    """CHomP3-rs's speedup against thread count, one line per case of the
    thread sweep, darker for a case whose one-thread run is longer."""
    note_errors(
        label,
        [
            row
            for row in tables.runs
            if row["tool"] == manifest.CHOMP3RS and row["config"] in THREAD_CONFIGS
        ],
    )
    seconds = {
        (row["case"], row["config"]): number_of(row, "wall_median")
        for row in tables.runs
        if row["tool"] == manifest.CHOMP3RS
        and row["config"] in (*THREAD_CONFIGS, FULL_CONFIG)
        and row["status"] in summarize.COMPARABLE
    }
    threaded = {case for case, config in seconds if config in THREAD_CONFIGS[1:]}
    baselines = {}
    for case in threaded:
        for config in SPEEDUP_BASELINES:
            if (case, config) in seconds:
                baselines[case] = (config, seconds[(case, config)])
                break
    cases = sorted(baselines, key=lambda case: baselines[case][1])
    if not cases:
        return "no CHomP3-rs thread configuration with a baseline in the tables"
    counts = [tables.configs[config]["threads"] for config in THREAD_CONFIGS]
    handles = []
    lines = []
    for case, color in zip(cases, color_ramp(len(cases))):
        config, baseline = baselines[case]
        points = [
            (tables.configs[threads]["threads"], baseline / seconds[(case, threads)])
            for threads in THREAD_CONFIGS
            if (case, threads) in seconds
        ]
        style = {
            "color": color,
            "linewidth": LINE_WIDTH,
            "marker": "o",
            "markersize": 4.0,
            "markerfacecolor": color,
            "markeredgecolor": SURFACE,
            "markeredgewidth": 0.5,
        }
        lines.append((points, style))
        handles.append(Line2D([], [], label=case_label(case), **style))
    height = SERIES_HEIGHT_INCHES + 0.2 * ceil(len(handles) / legend_columns(handles, width))
    figure, (axes,) = series_panels(width, height, 1)
    for points, style in lines:
        axes.plot([point[0] for point in points], [point[1] for point in points], zorder=3, **style)
    ideal = {"color": REFERENCE_COLOR, "linestyle": (0, (4.0, 2.0)), "linewidth": LINE_WIDTH}
    cores = {"color": REFERENCE_COLOR, "linestyle": (0, (1.0, 2.0)), "linewidth": 0.9}
    axes.plot(counts, counts, zorder=1, **ideal)
    axes.axvline(PHYSICAL_CORES, zorder=1, **cores)
    plain = FuncFormatter(lambda value, _: f"{value:g}")
    for axis, scale in ((axes.xaxis, axes.set_xscale), (axes.yaxis, axes.set_yscale)):
        scale("log", base=2)
        axis.set_major_locator(FixedLocator(counts))
        axis.set_major_formatter(plain)
        axis.set_minor_locator(NullLocator())
    axes.grid(axis="x", visible=True)
    axes.set_xlabel("threads")
    axes.set_ylabel("speedup")
    notes = [
        Line2D([], [], label="dashed: speedup equal to the thread count", **ideal),
        Line2D([], [], label=f"dotted: the machine's {PHYSICAL_CORES} cores", **cores),
    ]
    over = {config for config, _ in baselines.values()}
    chosen = (
        ", speedup over one thread on the parallel backend"
        if over == {"threads_1"}
        else ", speedup over the sequential backend where no one-thread run exists"
    )
    return finish_figure(figure, handles, notes, width, chosen=chosen)


def dense_cells(adapter, box):
    """The cells the tool's dense complex would hold over this bounding box, by
    the tool's own count."""
    own = getattr(adapter, "complex_cells", None)
    if own is not None:
        return own(box)
    return dense.cell_count(box)


def skip_boundary_volume(adapter, dimension, cap_bytes):
    """The bounding box volume at which the tool's dense complex first reaches
    the cap, the box taken as a cube of equal sides."""
    side = 1
    while True:
        box = SimpleNamespace(
            ambient_dimension=dimension,
            bounding_box=[(0, side - 1)] * dimension,
        )
        if dense_cells(adapter, box) * adapter.BYTES_PER_CELL > cap_bytes:
            return float(side**dimension)
        side += 1


def in_group(row, low, high):
    dimension = int(row["ambient_dimension"])
    return dimension >= low and (high is None or dimension <= high)


def draw_memory_volume(tables, width, label):
    """Peak memory against bounding box volume, one panel per group of ambient
    dimensions, with each dense tool's skip boundary on the panels whose least
    dimension it can take."""
    rows = cross_tool_rows(tables)
    note_errors(label, rows)
    drawn = [row for row in rows if point_of(tables, row, MEMORY_AXIS) is not None]
    tools = tools_present(tables, drawn, MEMORY_AXIS)
    if not tools:
        return "no row carries a peak memory in the tables"
    groups = [
        group for group in MEMORY_GROUPS if any(in_group(row, *group[:2]) for row in drawn)
    ]
    cap_bytes = tables.tier.memory_limit_gigabytes * BYTES_PER_GIGABYTE
    boundary = {"linestyle": (0, (4.0, 2.0)), "linewidth": LINE_WIDTH}
    cap = {"color": REFERENCE_COLOR, "linestyle": (0, (1.0, 2.0)), "linewidth": 0.9}
    figure, axes_list = series_panels(width, 3.4, len(groups), share_y=True)
    boundaries_drawn = False
    for axes, (low, high, title) in zip(axes_list, groups):
        group_rows = [row for row in drawn if in_group(row, low, high)]
        for tool in tools:
            points = [
                (number_of(row, "bounding_box_volume"), row)
                for row in group_rows
                if row["tool"] == tool
            ]
            plot_series(axes, tables, tool, points, MEMORY_AXIS, connect=False)
        if high is not None:
            for adapter in DENSE_ADAPTERS:
                limit = getattr(adapter, "MAXIMUM_DIMENSION", None)
                if limit is None or low <= limit:
                    axes.axvline(
                        skip_boundary_volume(adapter, low, cap_bytes),
                        color=TOOL_STYLE[adapter.NAME]["color"],
                        zorder=1,
                        **boundary,
                    )
                    boundaries_drawn = True
        axes.axhline(tables.tier.memory_limit_gigabytes, zorder=1, **cap)
        log_scale(axes, "x", numticks=5)
        log_scale(axes, "y")
        axes.set_xlabel(f"bounding box volume\n{title}")
    axes_list[0].set_ylabel("peak memory (GB)")
    notes = []
    if boundaries_drawn:
        notes.append(
            Line2D(
                [],
                [],
                label="dashed vertical, in the tool's colour: its skip boundary for a cube of the panel's least dimension",
                color=REFERENCE_COLOR,
                **boundary,
            )
        )
    notes.append(
        Line2D(
            [], [], label=f"dotted horizontal: the {tables.tier.memory_limit_gigabytes} GB cap", **cap
        )
    )
    notes += convention_handles(tables, drawn, MEMORY_AXIS, False)
    return finish_figure(
        figure,
        tool_handles(tools, False),
        notes,
        width,
        chosen=f", {TOOL_STYLE[cubical_ripser.NAME]['label']} also refused above"
        f" dimension {cubical_ripser.MAXIMUM_DIMENSION}",
    )


def draw_published_sets(tables, width, label):
    rows = [
        row
        for row in timed_rows(tables)
        if row["family"] == PUBLISHED_FAMILY and row["case"].endswith(PUBLISHED_SUFFIXES)
    ]
    note_errors(label, rows)
    tools = tools_present(tables, rows, TIME_AXIS)
    if not tools:
        return "no measured run on a published volume at full resolution in the tables"
    own_time = {
        row["case"]: number_of(row, "wall_median")
        for row in rows
        if row["tool"] == manifest.CHOMP3RS and row["status"] in summarize.COMPARABLE
    }
    volume_of = {row["case"]: number_of(row, "bounding_box_volume") for row in rows}
    names = sorted(
        drawn_cases(tables, rows, TIME_AXIS),
        key=lambda name: (own_time.get(name, float("inf")), volume_of[name]),
    )
    return draw_rows_figure(tables, width, rows, names, tools)


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
    return "input"


def draw_coverage(tables, width, label):
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


DENSE_ADAPTERS = (gudhi, cubical_ripser, pychomp2)

FIGURES = (
    (1, "flow_ladders", PAGE_WIDTH_INCHES, draw_flow_ladders),
    (2, "high_dimensional_flows", COLUMN_WIDTH_INCHES, draw_high_dimensional_flows),
    (3, "dimension_manifolds", PAGE_WIDTH_INCHES, draw_dimension_manifolds),
    (4, "sphere_table1", COLUMN_WIDTH_INCHES, draw_sphere_table1),
    (5, "density_random_top", PAGE_WIDTH_INCHES, draw_density_random_top),
    (6, "mixed_dimension", PAGE_WIDTH_INCHES, draw_mixed_dimension),
    (7, "grade_count", PAGE_WIDTH_INCHES, draw_grade_count),
    (8, "thread_scaling", COLUMN_WIDTH_INCHES, draw_thread_scaling),
    (9, "memory_volume", PAGE_WIDTH_INCHES, draw_memory_volume),
    (10, "published_sets", PAGE_WIDTH_INCHES, draw_published_sets),
    (11, "coverage", PAGE_WIDTH_INCHES, draw_coverage),
)
