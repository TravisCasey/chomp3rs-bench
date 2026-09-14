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
such as the dimension the density figure picks, the same line says which, for
the caption to repeat.

A mark on a time axis is a measurement. A run the tier stopped, out of time or
killed for memory, is drawn in a lane beside the axes instead, in the column or
row of its case, as an open marker when it ran out of time and a cross when it
was killed; the lane appears only on a figure that has such a run. On a memory
axis a killed run reached the cap, so it sits on the cap line as an open marker.
A group whose repetitions ended differently is drawn at its medians with the
marker of the worst of them, a run the tier skipped is not drawn, and a run
that ended in an error is not drawn either but is named in a printed note. A run
whose answer the check disputed is drawn where it landed inside a black ring.
The legend of every figure names the conventions that figure uses, and the last
figure, the coverage matrix, shows for every case of the tier which tools
finished, were stopped, were killed, or refused it and why.

Figure 4 reads `figures/reference/table1.csv`, the published sphere timings it
compares against.

Drawing needs LuaLaTeX with the STIX Two fonts, both part of TeX Live. Invoked
as `bench plot <tier>`; see `bench.cli`.
"""

import csv
import re
import zlib
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import matplotlib

matplotlib.use("pgf")

from matplotlib import pyplot
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import FixedLocator, LogLocator, NullFormatter

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

STAGE_ORDER = ("read", "build", "matching", "morse", "coreduction", "persistence")
STAGE_COLORS = ("#cfe0f0", "#a9c6e4", "#7fa9d6", "#5a8bc4", "#3a6fae", "#0b3d6b")

REFERENCE_COLOR = MUTED
DISPUTED_RING_COLOR = "#000000"
KILLED_MARKER = "x"
DISPUTED_MARKER = "o"
LINE_WIDTH = 0.9

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

THREAD_CONFIGS = ("threads_2", "threads_4", "threads_8", "threads_16")
MIXED_DIMENSION_SKIP = "mixed-dimension input not accepted"
LADDER_PREFIX = "charney_devore_d12_box"
MANIFOLD_FAMILIES = ("s1", "torus")
PUBLISHED_FAMILY = "published"

FLOW_COVERS = (
    "lorenz_d6_coarse",
    "lorenz_d6_fine",
    "dadras_d8_coarse",
    "dadras_d8_fine",
    "charney_devore_d12_box0.05",
    "charney_devore_d12_box0.04",
    "charney_devore_d12_box0.03",
    "charney_devore_d12_box0.02",
    "charney_devore_d12_box0.01",
    "kuramoto_sivashinsky_d16_minimal",
    "kuramoto_sivashinsky_d16_coarse",
    "kuramoto_sivashinsky_d16_fine",
)

SPHERE_CASE = re.compile(r"^sphere_d(\d+)$")
DENSITY_CASE = re.compile(r"^random_top_d(\d+)_p([0-9.]+)$")
GRADED_CASE = re.compile(r"^(.+)_(?:sweep|random)_g(\d+)$")
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
    chomp3rs one being `full` rather than the restricted `production`."""
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
    """The cases some tool has a point for, so that a case every tool skipped
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
    got there, or `None` where the row has nothing to say on that axis. On a
    time axis a stopped run has no value of its own; it is drawn in the lane."""
    status = row["status"]
    if axis == TIME_AXIS:
        if status == summarize.TIMEOUT:
            return float(tables.tier.timeout_seconds), OPEN_POINT
        if status == summarize.OUT_OF_MEMORY:
            return number_of(row, "wall_median"), KILLED_POINT
        if status not in summarize.COMPARABLE:
            return None
        return number_of(row, "wall_median"), FILLED_POINT
    if status == summarize.OUT_OF_MEMORY:
        return float(tables.tier.memory_limit_gigabytes), KILLED_POINT
    if status not in summarize.COMPARABLE:
        return None
    peak = number_of(row, "peak_rss_median_kb")
    return None if peak is None else (peak / KILOBYTES_PER_GIGABYTE, FILLED_POINT)


def needs_lane(tables, rows):
    """Whether a time figure has a stopped run to put in a lane."""
    return any(
        (point := point_of(tables, row, TIME_AXIS)) is not None
        and point[1] != FILLED_POINT
        for row in rows
    )


def marker_arguments(tool, convention):
    """How a point is drawn, which says whether it is a measurement or a run
    the tier stopped."""
    style = TOOL_STYLE[tool]
    if convention == KILLED_POINT:
        return {
            "marker": KILLED_MARKER,
            "markersize": style["size"] + 1.2,
            "markeredgecolor": style["color"],
            "markerfacecolor": "none",
            "markeredgewidth": 1.2,
        }
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


def plot_series(axes, lane, tables, tool, points, axis, connect, horizontal=False):
    """One tool's points, each marked by what ended its run, joined by the tool's
    line through the runs that finished when the axis reads as a series. A run
    the tier stopped goes to the lane on a time axis and to the cap line on a
    memory axis."""
    placed = []
    for position, row in points:
        point = point_of(tables, row, axis)
        if point is not None:
            placed.append((position, point[0], point[1], row["status"]))
    placed.sort(key=lambda entry: entry[0])
    joined = [entry for entry in placed if entry[2] == FILLED_POINT]
    if connect and len(joined) > 1:
        axes.plot(
            [entry[0] for entry in joined],
            [entry[1] for entry in joined],
            color=TOOL_STYLE[tool]["color"],
            linewidth=LINE_WIDTH,
            zorder=2,
        )
    for position, value, convention, status in placed:
        if convention == FILLED_POINT:
            target, where, arguments = axes, value, marker_arguments(tool, FILLED_POINT)
        elif axis == MEMORY_AXIS:
            target, where, arguments = axes, value, marker_arguments(tool, OPEN_POINT)
        else:
            target, where, arguments = lane, 0.0, marker_arguments(tool, convention)
        coordinates = ([where], [position]) if horizontal else ([position], [where])
        target.plot(*coordinates, linestyle="none", zorder=3, **arguments)
        if status == summarize.DISPUTED:
            target.plot(
                *coordinates, linestyle="none", zorder=4, **disputed_ring_arguments()
            )


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


def censored_handles(tables, rows, axis):
    """The legend entries for the conventions this figure actually uses, so that
    a figure without a stopped run carries no explanation of one."""
    drawn = [point_of(tables, row, axis) for row in rows]
    conventions = {point[1] for point in drawn if point is not None}
    handles = []
    cap = tables.tier.memory_limit_gigabytes
    if axis == TIME_AXIS:
        if OPEN_POINT in conventions:
            handles.append(
                note_handle(
                    f"open marker in the lane: stopped at the"
                    f" {tables.tier.timeout_seconds} s timeout",
                    OPEN_POINT,
                )
            )
        if KILLED_POINT in conventions:
            handles.append(
                note_handle(f"cross in the lane: killed at the {cap} GB cap", KILLED_POINT)
            )
    else:
        if KILLED_POINT in conventions:
            handles.append(
                note_handle(
                    f"open marker on the cap line: killed at the {cap} GB cap",
                    OPEN_POINT,
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


def log_scale(axes, which):
    """A logarithmic axis labelled at the decades, with unlabelled minor ticks
    at 2, 3 and 5."""
    if which == "x":
        axes.set_xscale("log")
        axis = axes.xaxis
    else:
        axes.set_yscale("log")
        axis = axes.yaxis
    axis.set_major_locator(LogLocator(base=10.0, numticks=12))
    axis.set_minor_locator(LogLocator(base=10.0, subs=(2.0, 3.0, 5.0), numticks=20))
    axis.set_minor_formatter(NullFormatter())


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


def style_lane(lane, horizontal):
    """The lane that holds the runs the tier stopped: shaded, unscaled, and
    labelled once."""
    lane.set_facecolor(BAND)
    lane.grid(False)
    for spine in lane.spines.values():
        spine.set_visible(False)
    lane.tick_params(axis="both", length=0)
    if horizontal:
        lane.set_xlim(-1.0, 1.0)
        lane.set_xticks([0.0])
        lane.set_xticklabels(["did not\nfinish"])
    else:
        lane.set_ylim(-1.0, 1.0)
        lane.set_yticks([0.0])
        lane.set_yticklabels(["did not finish"])


def series_panels(width, height, columns, lane, share_y=False):
    """The axes of a figure whose time axis is vertical, one panel per column,
    each under its own lane when the figure has a stopped run to show."""
    if lane:
        figure, panels = pyplot.subplots(
            2,
            columns,
            figsize=(width, height),
            squeeze=False,
            height_ratios=(1, 8),
            sharex="col",
            sharey="row" if share_y else False,
        )
        for panel in panels[0]:
            style_lane(panel, horizontal=False)
        return figure, list(panels[1]), list(panels[0])
    figure, panels = pyplot.subplots(
        1, columns, figsize=(width, height), squeeze=False, sharey=share_y
    )
    return figure, list(panels[0]), [None] * columns


def rows_panel(width, height, lane):
    """The axes of a figure with one row per case and time running across,
    with the lane to its right when the figure has a stopped run to show."""
    if lane:
        figure, panels = pyplot.subplots(
            1, 2, figsize=(width, height), squeeze=False, width_ratios=(9, 1), sharey=True
        )
        style_lane(panels[0][1], horizontal=True)
        return figure, panels[0][0], panels[0][1]
    figure, axes = pyplot.subplots(figsize=(width, height))
    return figure, axes, None


def plot_rows(figure_parts, tables, rows, names, tools):
    """One row per case, the tools spread along the time axis of that row, for
    a set of cases that has no measure to put them in order along."""
    figure, axes, lane = figure_parts
    positions = {name: index for index, name in enumerate(names)}
    for index in range(0, len(names), 2):
        axes.axhspan(index - 0.5, index + 0.5, color=BAND, linewidth=0, zorder=0)
    for tool in tools:
        points = [
            (positions[row["case"]], row)
            for row in rows
            if row["tool"] == tool and row["case"] in positions
        ]
        plot_series(axes, lane, tables, tool, points, TIME_AXIS, False, horizontal=True)
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


def draw_headline_flows(tables, width, label):
    rows = [row for row in cross_tool_rows(tables) if row["case"] in FLOW_COVERS]
    note_errors(label, rows)
    tools = tools_present(tables, rows, TIME_AXIS)
    if not tools:
        return "no measured run on a flow cover in the tables"
    measured = drawn_cases(tables, rows, TIME_AXIS)
    names = [name for name in FLOW_COVERS if name in measured]
    parts = rows_panel(width, rows_height(names), needs_lane(tables, rows))
    plot_rows(parts, tables, rows, names, tools)
    return finish_figure(
        parts[0], tool_handles(tools, False), censored_handles(tables, rows, TIME_AXIS), width
    )


def draw_ladder_d12(tables, width, label):
    rows = [
        row for row in cross_tool_rows(tables) if row["case"].startswith(LADDER_PREFIX)
    ]
    note_errors(label, rows)
    tools = tools_present(tables, rows, TIME_AXIS)
    if not tools:
        return "no measured run on the Charney-DeVore ladder in the tables"
    figure, (axes,), (lane,) = series_panels(width, 3.0, 1, needs_lane(tables, rows))
    for tool in tools:
        points = [
            (number_of(row, "cube_count"), row) for row in rows if row["tool"] == tool
        ]
        plot_series(axes, lane, tables, tool, points, TIME_AXIS, connect=True)
    log_scale(axes, "x")
    log_scale(axes, "y")
    axes.set_xlabel("cubes in the cover")
    axes.set_ylabel("wall time (s)")
    return finish_figure(
        figure, tool_handles(tools, True), censored_handles(tables, rows, TIME_AXIS), width
    )


def draw_dimension_manifolds(tables, width, label):
    rows = [
        row
        for row in cross_tool_rows(tables)
        if row["family"] in MANIFOLD_FAMILIES and row["graded"] == "false"
    ]
    note_errors(label, rows)
    tools = tools_present(tables, rows, TIME_AXIS)
    if not tools:
        return "no measured run on an ungraded s1 or torus case in the tables"
    families = [
        family
        for family in MANIFOLD_FAMILIES
        if any(row["family"] == family for row in rows)
    ]
    figure, panels, lanes = series_panels(
        width, 3.0, len(families), needs_lane(tables, rows), share_y=True
    )
    for axes, lane, family in zip(panels, lanes, families):
        dimensions = []
        for tool in tools:
            points = [
                (number_of(row, "ambient_dimension"), row)
                for row in rows
                if row["tool"] == tool and row["family"] == family
            ]
            dimensions += [
                position
                for position, row in points
                if point_of(tables, row, TIME_AXIS) is not None
            ]
            plot_series(axes, lane, tables, tool, points, TIME_AXIS, connect=True)
        log_scale(axes, "y")
        integer_ticks(axes, dimensions)
        axes.set_xlabel(f"ambient dimension $d$, {family}")
    panels[0].set_ylabel("wall time (s)")
    return finish_figure(
        figure, tool_handles(tools, True), censored_handles(tables, rows, TIME_AXIS), width
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
    3^d - 1 cells, so the times compare directly."""
    rows = [row for row in cross_tool_rows(tables) if SPHERE_CASE.match(row["case"])]
    note_errors(label, rows)
    tools = tools_present(tables, rows, TIME_AXIS)
    if not tools:
        return "no measured run on a sphere case in the tables"
    reference = read_rows(REFERENCE_TABLE)
    figure, (axes,), (lane,) = series_panels(width, 3.0, 1, needs_lane(tables, rows))
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
        plot_series(axes, lane, tables, tool, points, TIME_AXIS, connect=True)
    axes.plot(
        [float(entry["dimension"]) for entry in reference],
        [elapsed_seconds(entry["time_elapsed"]) for entry in reference],
        color=REFERENCE_COLOR,
        linestyle=(0, (2.0, 1.5)),
        linewidth=LINE_WIDTH,
        marker="+",
        markersize=5.0,
        zorder=2,
    )
    log_scale(axes, "y")
    integer_ticks(axes, dimensions)
    axes.xaxis.set_major_locator(FixedLocator([d for d in sorted(set(dimensions)) if d % 2 == 0]))
    axes.set_xticklabels([str(int(d)) for d in sorted(set(dimensions)) if d % 2 == 0])
    axes.set_xlabel("ambient dimension $d$")
    axes.set_ylabel("wall time (s)")
    series = tool_handles(tools, True)
    series.append(
        Line2D(
            [],
            [],
            label="arXiv:2105.09870 Table 1(a), one core",
            color=REFERENCE_COLOR,
            linestyle=(0, (2.0, 1.5)),
            linewidth=LINE_WIDTH,
            marker="+",
            markersize=5.0,
        )
    )
    return finish_figure(figure, series, censored_handles(tables, rows, TIME_AXIS), width)


def draw_density_random_top(tables, width, label):
    matched = [
        (DENSITY_CASE.match(row["case"]), row) for row in cross_tool_rows(tables)
    ]
    note_errors(label, [row for match, row in matched if match is not None])
    by_dimension = {}
    for match, row in matched:
        if match is None:
            continue
        by_dimension.setdefault(int(match.group(1)), []).append(
            (float(match.group(2)), row)
        )
    if not by_dimension:
        return "no random_top case in the tables"
    measured = {
        value: {
            density
            for density, row in entries
            if point_of(tables, row, TIME_AXIS) is not None
        }
        for value, entries in by_dimension.items()
    }
    dimension = max(measured, key=lambda value: (len(measured[value]), value))
    points = by_dimension[dimension]
    rows = [row for _, row in points]
    tools = tools_present(tables, rows, TIME_AXIS)
    if not tools:
        return "no measured run on a random_top case in the tables"
    figure, (axes,), (lane,) = series_panels(width, 3.0, 1, needs_lane(tables, rows))
    for tool in tools:
        plot_series(
            axes,
            lane,
            tables,
            tool,
            [(density, row) for density, row in points if row["tool"] == tool],
            TIME_AXIS,
            connect=True,
        )
    log_scale(axes, "y")
    densities = sorted({density for density, _ in points})
    axes.xaxis.set_major_locator(FixedLocator(densities))
    axes.set_xticklabels([f"{density:g}" for density in densities])
    axes.set_xlabel("share of box positions holding a cube, $p$")
    axes.set_ylabel("wall time (s)")
    return finish_figure(
        figure,
        tool_handles(tools, True),
        censored_handles(tables, rows, TIME_AXIS),
        width,
        chosen=f", drawn at d = {dimension}",
    )


def draw_mixed_dimension(tables, width, label):
    refused = {
        row["case"] for row in tables.runs if row["skip_reason"] == MIXED_DIMENSION_SKIP
    }
    rows = [
        row
        for row in cross_tool_rows(tables)
        if row["case"] in refused and row["status"] != summarize.SKIPPED
    ]
    note_errors(label, rows)
    tools = tools_present(tables, rows, TIME_AXIS)
    if not tools:
        return "no measured run on a mixed-dimension case in the tables"
    shape_of = {
        row["case"]: (row["family"], number_of(row, "ambient_dimension"))
        for row in rows
    }
    names = sorted(
        drawn_cases(tables, rows, TIME_AXIS),
        key=lambda name: shape_of[name] + (name,),
    )
    parts = rows_panel(width, rows_height(names), needs_lane(tables, rows))
    plot_rows(parts, tables, rows, names, tools)
    return finish_figure(
        parts[0], tool_handles(tools, False), censored_handles(tables, rows, TIME_AXIS), width
    )


def draw_grade_count(tables, width, label):
    by_base = {}
    for row in cross_tool_rows(tables):
        match = GRADED_CASE.match(row["case"])
        if match is None or row["graded"] != "true":
            continue
        by_base.setdefault(match.group(1), []).append(row)
    note_errors(label, [row for group in by_base.values() for row in group])
    if not by_base:
        return "no graded case in the tables"
    measured = {
        name: {
            row["grade_count"]
            for row in group
            if point_of(tables, row, TIME_AXIS) is not None
        }
        for name, group in by_base.items()
    }
    base = max(measured, key=lambda name: len(measured[name]))
    if len(measured[base]) < 2:
        return "fewer than two grade counts measured on any graded case in the tables"
    rows = by_base[base]
    tools = tools_present(tables, rows, TIME_AXIS)
    figure, (axes,), (lane,) = series_panels(width, 3.0, 1, needs_lane(tables, rows))
    for tool in tools:
        points = [
            (number_of(row, "grade_count"), row) for row in rows if row["tool"] == tool
        ]
        plot_series(axes, lane, tables, tool, points, TIME_AXIS, connect=True)
    counts = sorted({number_of(row, "grade_count") for row in rows})
    axes.set_xscale("log", base=2)
    axes.xaxis.set_major_locator(FixedLocator(counts))
    axes.set_xticklabels([str(int(count)) for count in counts])
    axes.xaxis.set_minor_locator(FixedLocator([]))
    log_scale(axes, "y")
    axes.set_xlabel("grades in the filtration")
    axes.set_ylabel("wall time (s)")
    return finish_figure(
        figure,
        tool_handles(tools, True),
        censored_handles(tables, rows, TIME_AXIS),
        width,
        chosen=f", drawn on {base}",
    )


def draw_thread_scaling(tables, width, label):
    note_errors(label, [row for row in tables.runs if row["config"] in THREAD_CONFIGS])
    threaded = [row for row in tables.stages if row["config"] in THREAD_CONFIGS]
    if not threaded:
        return "no chomp3rs thread configuration in the stage table"
    counts = {}
    for row in threaded:
        counts[row["case"]] = counts.get(row["case"], 0) + 1
    case = max(counts, key=lambda name: (counts[name], name))
    configs = [FULL_CONFIG, *THREAD_CONFIGS]
    seconds = {}
    for row in tables.stages:
        if row["case"] == case and row["config"] in configs:
            seconds[(row["config"], row["stage"])] = float(row["seconds_median"])
    drawn = [config for config in configs if any(key[0] == config for key in seconds)]
    positions = range(len(drawn))
    figure, axes = pyplot.subplots(figsize=(width, 3.0))
    bottoms = [0.0] * len(drawn)
    for stage, color in zip(STAGE_ORDER, STAGE_COLORS):
        heights = [seconds.get((config, stage), 0.0) for config in drawn]
        axes.bar(
            positions,
            heights,
            bottom=bottoms,
            width=0.68,
            color=color,
            edgecolor=SURFACE,
            linewidth=0.8,
            label=stage,
        )
        bottoms = [bottom + height for bottom, height in zip(bottoms, heights)]
    axes.set_xticks(positions)
    axes.set_xticklabels([str(tables.configs[config]["threads"]) for config in drawn])
    axes.set_xlabel("threads (1 is the sequential backend)")
    axes.set_ylabel("wall time per stage (s)")
    axes.grid(axis="x", visible=False)
    stages, _ = axes.get_legend_handles_labels()
    return finish_figure(figure, stages[::-1], [], width, chosen=f", drawn on {case}")


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


def draw_memory_volume(tables, width, label):
    rows = cross_tool_rows(tables)
    note_errors(label, rows)
    drawn = [row for row in rows if point_of(tables, row, MEMORY_AXIS) is not None]
    tools = tools_present(tables, drawn, MEMORY_AXIS)
    if not tools:
        return "no row carries a peak memory in the tables"
    dimensions = [int(row["ambient_dimension"]) for row in drawn]
    dimension = max(
        set(dimensions), key=lambda value: (dimensions.count(value), -value)
    )
    cap_bytes = tables.tier.memory_limit_gigabytes * BYTES_PER_GIGABYTE
    figure, axes = pyplot.subplots(figsize=(width, 3.4))
    for tool in tools:
        points = [
            (number_of(row, "bounding_box_volume"), row)
            for row in drawn
            if row["tool"] == tool
        ]
        plot_series(axes, None, tables, tool, points, MEMORY_AXIS, connect=False)
    for adapter in DENSE_ADAPTERS:
        axes.axvline(
            skip_boundary_volume(adapter, dimension, cap_bytes),
            color=TOOL_STYLE[adapter.NAME]["color"],
            linestyle=(0, (4.0, 2.0)),
            linewidth=LINE_WIDTH,
            zorder=1,
        )
    axes.axhline(
        tables.tier.memory_limit_gigabytes,
        color=REFERENCE_COLOR,
        linestyle=(0, (1.0, 2.0)),
        linewidth=0.9,
        zorder=1,
    )
    log_scale(axes, "x")
    log_scale(axes, "y")
    axes.set_xlabel("bounding box volume (positions)")
    axes.set_ylabel("peak memory (GB)")
    notes = [
        Line2D(
            [],
            [],
            label=f"dashed vertical, in the tool's colour: its skip boundary for a d = {dimension} cube",
            color=REFERENCE_COLOR,
            linestyle=(0, (4.0, 2.0)),
            linewidth=LINE_WIDTH,
        ),
        Line2D(
            [],
            [],
            label=f"dotted horizontal: the {tables.tier.memory_limit_gigabytes} GB cap",
            color=REFERENCE_COLOR,
            linestyle=(0, (1.0, 2.0)),
            linewidth=0.9,
        ),
        *censored_handles(tables, drawn, MEMORY_AXIS),
    ]
    return finish_figure(
        figure,
        tool_handles(tools, False),
        notes,
        width,
        chosen=f", boundaries at d = {dimension},"
        f" {TOOL_STYLE[cubical_ripser.NAME]['label']} also refused above"
        f" dimension {cubical_ripser.MAXIMUM_DIMENSION}",
    )


def draw_published_sets(tables, width, label):
    rows = [row for row in cross_tool_rows(tables) if row["family"] == PUBLISHED_FAMILY]
    note_errors(label, rows)
    tools = tools_present(tables, rows, TIME_AXIS)
    if not tools:
        return "no measured run on a published image set in the tables"
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
    parts = rows_panel(width, rows_height(names), needs_lane(tables, rows))
    plot_rows(parts, tables, rows, names, tools)
    return finish_figure(
        parts[0], tool_handles(tools, False), censored_handles(tables, rows, TIME_AXIS), width
    )


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
    (1, "headline_flows", PAGE_WIDTH_INCHES, draw_headline_flows),
    (2, "ladder_d12", COLUMN_WIDTH_INCHES, draw_ladder_d12),
    (3, "dimension_manifolds", PAGE_WIDTH_INCHES, draw_dimension_manifolds),
    (4, "sphere_table1", COLUMN_WIDTH_INCHES, draw_sphere_table1),
    (5, "density_random_top", COLUMN_WIDTH_INCHES, draw_density_random_top),
    (6, "mixed_dimension", PAGE_WIDTH_INCHES, draw_mixed_dimension),
    (7, "grade_count", COLUMN_WIDTH_INCHES, draw_grade_count),
    (8, "thread_scaling", COLUMN_WIDTH_INCHES, draw_thread_scaling),
    (9, "memory_volume", PAGE_WIDTH_INCHES, draw_memory_volume),
    (10, "published_sets", PAGE_WIDTH_INCHES, draw_published_sets),
    (11, "coverage", PAGE_WIDTH_INCHES, draw_coverage),
)
