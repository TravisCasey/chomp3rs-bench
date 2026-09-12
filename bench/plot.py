"""The figures: the summary tables of a tier turned into the paper's plots.

Reads `results/summary/<tier>/runs.csv` and `stages.csv` and writes
`figures/<tier>/fig<NN>_<name>.pdf` and `.png`, one pair per figure of
`FIGURES`. A figure whose cases or tools are not in the tables is not drawn and
prints one line saying what is missing.

A run the tier stopped is drawn where it stopped rather than dropped. A time
axis is censored at both ends and an open marker says so at either: above, a run
out of time sits at the tier's timeout, and below, a run the timer could not
separate from zero sits at its 0.01 second resolution. A run killed for memory
is a cross, at the wall time it reached on a time axis and at the cap on a
memory axis; a run out of time has no peak to draw and is absent from a memory
axis. A group whose repetitions ended differently is drawn at its medians with
the marker of the worst of them, a run the tier skipped is not drawn, and a run
that ended in an error is not drawn either but is named in a printed note. A run
whose answer the check disputed is drawn where it landed inside a black ring.
The legend of every figure names the conventions that figure uses.

Figure 4 reads `figures/reference/table1.csv`, the published sphere timings it
compares against.

Invoked as `bench plot <tier>`; see `bench.cli`.
"""

import csv
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import matplotlib

matplotlib.use("Agg")

from matplotlib import pyplot
from matplotlib.lines import Line2D
from matplotlib.ticker import LogLocator

from bench import dense, manifest, summarize
from bench.adapters import cubical_ripser, dipha, gudhi, pychomp2

SUMMARY_DIRECTORY = Path("results/summary")
FIGURE_DIRECTORY = Path("figures")
REFERENCE_TABLE = FIGURE_DIRECTORY / "reference" / "table1.csv"

COLUMN_WIDTH_INCHES = 3.3
PAGE_WIDTH_INCHES = 6.8

FULL_CONFIG = "full"
TIME_AXIS = "time"
MEMORY_AXIS = "memory"
KILOBYTES_PER_GIGABYTE = 1024 * 1024
BYTES_PER_GIGABYTE = 1024**3
TIME_RESOLUTION_SECONDS = 0.01

FILLED_POINT = "filled"
OPEN_POINT = "open"
KILLED_POINT = "killed"

TOOL_STYLE = {
    "chomp3rs": {
        "label": "chomp3rs",
        "color": "#0d366b",
        "marker": "o",
        "dashes": "solid",
    },
    "homcubes": {
        "label": "homcubes",
        "color": "#e34948",
        "marker": "s",
        "dashes": (0, (5.0, 2.0)),
    },
    "pychomp2": {
        "label": "pyCHomP2",
        "color": "#4a3aa7",
        "marker": "^",
        "dashes": (0, (1.2, 1.6)),
    },
    "perseus": {
        "label": "Perseus",
        "color": "#1baf7a",
        "marker": "D",
        "dashes": (0, (4.0, 1.4, 1.0, 1.4)),
    },
    "gudhi": {
        "label": "GUDHI",
        "color": "#1c5cab",
        "marker": "P",
        "dashes": (0, (7.0, 1.6, 1.0, 1.6, 1.0, 1.6)),
    },
    "dipha": {
        "label": "DIPHA",
        "color": "#eda100",
        "marker": "p",
        "dashes": (0, (2.5, 1.4)),
    },
    "cubical_ripser": {
        "label": "Cubical Ripser",
        "color": "#008300",
        "marker": "*",
        "dashes": (0, (6.0, 1.4, 1.0, 1.4, 1.0, 1.4, 1.0, 1.4)),
    },
}

TOOL_ORDER = tuple(TOOL_STYLE)

STAGE_ORDER = ("read", "build", "matching", "morse", "coreduction", "persistence")
STAGE_COLORS = ("#86b6ef", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b")

REFERENCE_COLOR = "#52514e"
SURFACE_COLOR = "#ffffff"
EDGE_COLOR = "#1a1a19"
DISPUTED_RING_COLOR = "#000000"
KILLED_MARKER = "x"
DISPUTED_MARKER = "o"

MARKER_SIZE = 4.4
LINE_WIDTH = 1.1
LEGEND_FONT_SIZE = 5.8
TICK_LABEL_FONT_SIZE = 5.5
HANDLE_WIDTH_INCHES = 0.45
CHARACTER_WIDTH_INCHES = 0.045

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

SECONDS_PER_UNIT = {"ns": 1e-9, "us": 1e-6, "ms": 1e-3, "s": 1.0, "m": 60.0}

pyplot.rcParams.update(
    {
        "figure.facecolor": SURFACE_COLOR,
        "savefig.facecolor": SURFACE_COLOR,
        "axes.facecolor": SURFACE_COLOR,
        "font.family": "DejaVu Sans",
        "font.size": 7,
        "axes.labelsize": 7,
        "axes.titlesize": 7.5,
        "xtick.labelsize": 6,
        "ytick.labelsize": 6,
        "axes.edgecolor": "#8a8983",
        "axes.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": "#dcdbd7",
        "grid.linewidth": 0.5,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "legend.frameon": False,
        "lines.solid_capstyle": "round",
        "axes.unicode_minus": False,
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
        for suffix in ("pdf", "png"):
            path = directory / f"{label}.{suffix}"
            drawn.savefig(path, dpi=300)
            print(path)
        pyplot.close(drawn)


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
    """A case name broken over two lines at the underscore nearest its middle,
    so that a column of them does not swallow the plot."""
    if len(name) < 14:
        return name
    breaks = [index for index, letter in enumerate(name) if letter == "_"]
    if not breaks:
        return name
    chosen = min(breaks, key=lambda index: abs(index - len(name) // 2))
    return f"{name[:chosen]}\n{name[chosen + 1 :]}"


def point_of(tables, row, axis):
    """Where a row sits on a time or a memory axis and which marker says how it
    got there, or `None` where the row has nothing to say on that axis. A time
    axis is censored at both ends: a run out of time sits at the tier's timeout
    and a run the timer could not separate from zero sits at its resolution, and
    both read as open markers."""
    status = row["status"]
    if axis == TIME_AXIS:
        if status == summarize.TIMEOUT:
            return number_of(row, "wall_median"), OPEN_POINT
        if status == summarize.OUT_OF_MEMORY:
            return number_of(row, "wall_median"), KILLED_POINT
        if status not in summarize.COMPARABLE:
            return None
        wall = number_of(row, "wall_median")
        if wall < TIME_RESOLUTION_SECONDS:
            return TIME_RESOLUTION_SECONDS, OPEN_POINT
        return wall, FILLED_POINT
    if status == summarize.OUT_OF_MEMORY:
        return float(tables.tier.memory_limit_gigabytes), KILLED_POINT
    if status not in summarize.COMPARABLE:
        return None
    peak = number_of(row, "peak_rss_median_kb")
    return None if peak is None else (peak / KILOBYTES_PER_GIGABYTE, FILLED_POINT)


def marker_arguments(tool, convention):
    """How a point is drawn, which says whether it is a measurement or a bound
    the tier stopped the run at."""
    style = TOOL_STYLE[tool]
    if convention == KILLED_POINT:
        return {
            "marker": KILLED_MARKER,
            "markersize": MARKER_SIZE + 1.4,
            "markeredgecolor": style["color"],
            "markerfacecolor": "none",
            "markeredgewidth": 1.3,
        }
    if convention == OPEN_POINT:
        return {
            "marker": style["marker"],
            "markersize": MARKER_SIZE + 0.6,
            "markeredgecolor": style["color"],
            "markerfacecolor": "none",
            "markeredgewidth": 1.1,
        }
    return {
        "marker": style["marker"],
        "markersize": MARKER_SIZE,
        "markeredgecolor": EDGE_COLOR,
        "markerfacecolor": style["color"],
        "markeredgewidth": 0.45,
    }


def disputed_ring_arguments():
    """The ring drawn around a point whose answer the check disputed: black,
    which belongs to no tool and stays black in grey."""
    return {
        "marker": DISPUTED_MARKER,
        "markersize": MARKER_SIZE + 4.0,
        "markeredgecolor": DISPUTED_RING_COLOR,
        "markerfacecolor": "none",
        "markeredgewidth": 1.0,
    }


def plot_series(axes, tables, tool, points, axis, connect):
    """One tool's points, each marked by what ended its run, joined by the tool's
    line through the runs that finished when the axis reads as a series."""
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
            linestyle=TOOL_STYLE[tool]["dashes"],
            linewidth=LINE_WIDTH,
            zorder=2,
        )
    for position, value, convention, status in placed:
        axes.plot(
            [position],
            [value],
            linestyle="none",
            zorder=3,
            **marker_arguments(tool, convention),
        )
        if status == summarize.DISPUTED:
            axes.plot(
                [position],
                [value],
                linestyle="none",
                zorder=4,
                **disputed_ring_arguments(),
            )


def tool_handles(tools, with_line):
    return [
        Line2D(
            [],
            [],
            label=TOOL_STYLE[tool]["label"],
            color=TOOL_STYLE[tool]["color"],
            linestyle=TOOL_STYLE[tool]["dashes"] if with_line else "none",
            linewidth=LINE_WIDTH,
            marker=TOOL_STYLE[tool]["marker"],
            markersize=MARKER_SIZE,
            markerfacecolor=TOOL_STYLE[tool]["color"],
            markeredgecolor=EDGE_COLOR,
            markeredgewidth=0.45,
        )
        for tool in tools
    ]


def censored_handles(tables, rows, axis):
    """The legend entries for the conventions this figure actually uses, so that
    a figure without a stopped run carries no explanation of one."""
    drawn = [point_of(tables, row, axis) for row in rows]
    conventions = {point[1] for point in drawn if point is not None}
    handles = []
    if OPEN_POINT in conventions:
        handles.append(
            Line2D(
                [],
                [],
                label=(
                    "open marker: censored at the timer's bound (timeout above,"
                    f" {TIME_RESOLUTION_SECONDS} s resolution below)"
                ),
                linestyle="none",
                marker="o",
                markersize=MARKER_SIZE + 0.6,
                markerfacecolor="none",
                markeredgecolor=REFERENCE_COLOR,
                markeredgewidth=1.1,
            )
        )
    if KILLED_POINT in conventions:
        cap = tables.tier.memory_limit_gigabytes
        where = "at its wall time" if axis == TIME_AXIS else "at the cap"
        handles.append(
            Line2D(
                [],
                [],
                label=f"cross: killed at the {cap} GB cap, {where}",
                linestyle="none",
                marker=KILLED_MARKER,
                markersize=MARKER_SIZE + 1.4,
                markerfacecolor="none",
                markeredgecolor=REFERENCE_COLOR,
                markeredgewidth=1.3,
            )
        )
    if axis == MEMORY_AXIS and any(row["status"] == summarize.TIMEOUT for row in rows):
        handles.append(
            Line2D(
                [],
                [],
                label=(
                    f"out of time at {tables.tier.timeout_seconds} s:"
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
                label="black ring around a marker: answer disputed",
                linestyle="none",
                **disputed_ring_arguments(),
            )
        )
    return handles


def log_scale(axes, which):
    """A logarithmic axis whose minor ticks sit only at 2 and 5, so that the
    labels of a range narrower than a decade have room to be read."""
    if which == "x":
        axes.set_xscale("log")
        axis = axes.xaxis
    else:
        axes.set_yscale("log")
        axis = axes.yaxis
    axis.set_minor_locator(LogLocator(base=10.0, subs=(2.0, 5.0), numticks=20))


def legend_columns(handles, width):
    """As many columns as the longest entry leaves room for across the figure."""
    longest = max(len(handle.get_label()) for handle in handles)
    entry = HANDLE_WIDTH_INCHES + longest * CHARACTER_WIDTH_INCHES
    return max(1, min(4, int(width / entry)))


def add_legend(figure, handles, width, above):
    columns = legend_columns(handles, width)
    room = int((width / columns - HANDLE_WIDTH_INCHES) / CHARACTER_WIDTH_INCHES)
    legend = figure.legend(
        handles=handles,
        labels=[textwrap.fill(handle.get_label(), room) for handle in handles],
        loc="lower center",
        bbox_to_anchor=(0.5, above / figure.get_figheight()),
        ncol=columns,
        fontsize=LEGEND_FONT_SIZE,
        handlelength=3.4,
        handletextpad=0.5,
        columnspacing=1.2,
        labelspacing=0.35,
        borderaxespad=0.0,
    )
    figure.canvas.draw()
    return above + legend.get_window_extent().height / figure.dpi


def finish_figure(figure, series, notes, width):
    """The legend of the series and, under it, the legend that explains the
    censored markers, with the height they took measured and kept out of the
    plot's own layout."""
    taken = 0.0
    if notes:
        taken = add_legend(figure, notes, width, taken) + 0.04
    taken = add_legend(figure, series, width, taken) + 0.08
    figure.tight_layout(rect=(0.0, taken / figure.get_figheight(), 1.0, 1.0), pad=0.7)
    return figure


def plot_by_case(axes, tables, rows, names, tools, axis):
    """A categorical case axis: one column per case with the tools spread across
    it, for a set of cases that has no measure to put them in order along."""
    positions = {name: index for index, name in enumerate(names)}
    spread = min(0.66, 0.12 * (len(tools) - 1))
    for index, tool in enumerate(tools):
        shift = spread * (index / max(len(tools) - 1, 1) - 0.5)
        points = [
            (positions[row["case"]] + shift, row)
            for row in rows
            if row["tool"] == tool and row["case"] in positions
        ]
        plot_series(axes, tables, tool, points, axis, connect=False)
    axes.set_xticks(range(len(names)))
    axes.set_xticklabels(
        [case_label(name) for name in names],
        rotation=30,
        ha="right",
        rotation_mode="anchor",
        fontsize=TICK_LABEL_FONT_SIZE,
    )
    axes.set_xlim(-0.6, len(names) - 0.4)
    axes.grid(axis="x", visible=True)


def draw_headline_flows(tables, width, label):
    rows = [row for row in cross_tool_rows(tables) if row["case"] in FLOW_COVERS]
    note_errors(label, rows)
    tools = tools_present(tables, rows, TIME_AXIS)
    if not tools:
        return "no measured run on a flow cover in the tables"
    measured = drawn_cases(tables, rows, TIME_AXIS)
    names = [name for name in FLOW_COVERS if name in measured]
    figure, axes = pyplot.subplots(figsize=(width, 3.6))
    plot_by_case(axes, tables, rows, names, tools, TIME_AXIS)
    log_scale(axes, "y")
    axes.set_ylabel("wall time (s), median over repetitions")
    axes.set_title("Wall time per tool on the flow covers")
    return finish_figure(
        figure,
        tool_handles(tools, False),
        censored_handles(tables, rows, TIME_AXIS),
        width,
    )


def draw_ladder_d12(tables, width, label):
    rows = [
        row for row in cross_tool_rows(tables) if row["case"].startswith(LADDER_PREFIX)
    ]
    note_errors(label, rows)
    tools = tools_present(tables, rows, TIME_AXIS)
    if not tools:
        return "no measured run on the Charney-DeVore ladder in the tables"
    figure, axes = pyplot.subplots(figsize=(width, 3.4))
    for tool in tools:
        points = [
            (number_of(row, "cube_count"), row) for row in rows if row["tool"] == tool
        ]
        plot_series(axes, tables, tool, points, TIME_AXIS, connect=True)
    log_scale(axes, "x")
    log_scale(axes, "y")
    axes.set_xlabel("cubes in the cover")
    axes.set_ylabel("wall time (s)")
    axes.set_title("The Charney-DeVore ladder, d = 12")
    return finish_figure(
        figure,
        tool_handles(tools, True),
        censored_handles(tables, rows, TIME_AXIS),
        width,
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
    figure, panels = pyplot.subplots(
        1, len(families), figsize=(width, 3.2), sharey=True, squeeze=False
    )
    for axes, family in zip(panels[0], families):
        for tool in tools:
            points = [
                (number_of(row, "ambient_dimension"), row)
                for row in rows
                if row["tool"] == tool and row["family"] == family
            ]
            plot_series(axes, tables, tool, points, TIME_AXIS, connect=True)
        log_scale(axes, "y")
        axes.set_xlabel("ambient dimension d")
        axes.set_title(family)
    panels[0][0].set_ylabel("wall time (s)")
    return finish_figure(
        figure,
        tool_handles(tools, True),
        censored_handles(tables, rows, TIME_AXIS),
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
    3^d - 1 cells, so the times compare directly."""
    rows = [row for row in cross_tool_rows(tables) if SPHERE_CASE.match(row["case"])]
    note_errors(label, rows)
    tools = tools_present(tables, rows, TIME_AXIS)
    if not tools:
        return "no measured run on a sphere_d<k> case in the tables"
    reference = read_rows(REFERENCE_TABLE)
    figure, axes = pyplot.subplots(figsize=(width, 3.4))
    for tool in tools:
        points = [
            (number_of(row, "ambient_dimension"), row)
            for row in rows
            if row["tool"] == tool
        ]
        plot_series(axes, tables, tool, points, TIME_AXIS, connect=True)
    axes.plot(
        [float(entry["dimension"]) for entry in reference],
        [elapsed_seconds(entry["time_elapsed"]) for entry in reference],
        color=REFERENCE_COLOR,
        linestyle=(0, (2.0, 1.5)),
        linewidth=LINE_WIDTH,
        marker="+",
        markersize=MARKER_SIZE,
        zorder=2,
    )
    log_scale(axes, "y")
    axes.set_xlabel("ambient dimension d")
    axes.set_ylabel("wall time (s)")
    axes.set_title("Time on the sphere_d<k> cases")
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
            markersize=MARKER_SIZE,
        )
    )
    notes = [
        Line2D(
            [],
            [],
            label="both sides compute the same complex, 3^d - 1 cells",
            linestyle="none",
            marker="none",
        ),
        *censored_handles(tables, rows, TIME_AXIS),
    ]
    return finish_figure(figure, series, notes, width)


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
        return "no random_top_d<k>_p<p> case in the tables"
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
    tools = tools_present(tables, [row for _, row in points], TIME_AXIS)
    if not tools:
        return "no measured run on a random_top_d<k>_p<p> case in the tables"
    figure, axes = pyplot.subplots(figsize=(width, 3.4))
    for tool in tools:
        plot_series(
            axes,
            tables,
            tool,
            [(density, row) for density, row in points if row["tool"] == tool],
            TIME_AXIS,
            connect=True,
        )
    log_scale(axes, "y")
    axes.set_xlabel("share of box positions holding a cube, p")
    axes.set_ylabel("wall time (s)")
    axes.set_title(f"Random top cubes at d = {dimension}")
    return finish_figure(
        figure,
        tool_handles(tools, True),
        censored_handles(tables, [row for _, row in points], TIME_AXIS),
        width,
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
    figure, axes = pyplot.subplots(figsize=(width, 3.6))
    plot_by_case(axes, tables, rows, names, tools, TIME_AXIS)
    log_scale(axes, "y")
    axes.set_ylabel("wall time (s)")
    axes.set_title("Mixed-dimension cases, on the tools that read them")
    return finish_figure(
        figure,
        tool_handles(tools, False),
        censored_handles(tables, rows, TIME_AXIS),
        width,
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
    figure, axes = pyplot.subplots(figsize=(width, 3.4))
    for tool in tools:
        points = [
            (number_of(row, "grade_count"), row) for row in rows if row["tool"] == tool
        ]
        plot_series(axes, tables, tool, points, TIME_AXIS, connect=True)
    axes.set_xscale("log", base=2)
    log_scale(axes, "y")
    axes.set_xlabel("grades in the filtration")
    axes.set_ylabel("wall time (s)")
    axes.set_title(f"Persistence on {base}")
    return finish_figure(
        figure,
        tool_handles(tools, True),
        censored_handles(tables, rows, TIME_AXIS),
        width,
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
    figure, axes = pyplot.subplots(figsize=(width, 3.4))
    bottoms = [0.0] * len(drawn)
    for stage, color in zip(STAGE_ORDER, STAGE_COLORS):
        heights = [seconds.get((config, stage), 0.0) for config in drawn]
        axes.bar(
            positions,
            heights,
            bottom=bottoms,
            width=0.68,
            color=color,
            edgecolor=SURFACE_COLOR,
            linewidth=0.8,
            label=stage,
        )
        bottoms = [bottom + height for bottom, height in zip(bottoms, heights)]
    axes.set_xticks(positions)
    axes.set_xticklabels([str(tables.configs[config]["threads"]) for config in drawn])
    axes.set_xlabel("threads (1 is the sequential backend)")
    axes.set_ylabel("wall time per stage (s)")
    axes.set_title(f"chomp3rs stages on {case}")
    axes.grid(axis="x", visible=False)
    stages, _ = axes.get_legend_handles_labels()
    return finish_figure(figure, stages[::-1], [], width)


def dense_cells(adapter, box):
    """The cells the tool's dense complex would hold over this bounding box, by
    the tool's own count."""
    own = getattr(adapter, "complex_cells", None)
    if own is not None:
        return own(box)
    return dense.cell_count(box, adapter.CONSTRUCTION)


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
    figure, axes = pyplot.subplots(figsize=(width, 3.6))
    for tool in tools:
        points = [
            (number_of(row, "bounding_box_volume"), row)
            for row in drawn
            if row["tool"] == tool
        ]
        plot_series(axes, tables, tool, points, MEMORY_AXIS, connect=False)
    for adapter in DENSE_ADAPTERS:
        axes.axvline(
            skip_boundary_volume(adapter, dimension, cap_bytes),
            color=TOOL_STYLE[adapter.NAME]["color"],
            linestyle=TOOL_STYLE[adapter.NAME]["dashes"],
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
    axes.set_ylabel("peak memory (GB), median over repetitions")
    axes.set_title("Peak memory against the size of the box")
    notes = [
        Line2D(
            [],
            [],
            label=f"vertical line: skip rule boundary, d = {dimension} cube",
            color=REFERENCE_COLOR,
            linestyle=(0, (5.0, 2.0)),
            linewidth=LINE_WIDTH,
        ),
        Line2D(
            [],
            [],
            label=f"horizontal line: the {tables.tier.memory_limit_gigabytes} GB cap",
            color=REFERENCE_COLOR,
            linestyle=(0, (1.0, 2.0)),
            linewidth=0.9,
        ),
        *censored_handles(tables, drawn, MEMORY_AXIS),
    ]
    return finish_figure(figure, tool_handles(tools, False), notes, width)


def draw_published_sets(tables, width, label):
    rows = [row for row in cross_tool_rows(tables) if row["family"] == PUBLISHED_FAMILY]
    note_errors(label, rows)
    tools = tools_present(tables, rows, TIME_AXIS)
    if not tools:
        return "no measured run on a published image set in the tables"
    volume_of = {row["case"]: number_of(row, "bounding_box_volume") for row in rows}
    names = sorted(
        drawn_cases(tables, rows, TIME_AXIS), key=lambda name: volume_of[name]
    )
    figure, axes = pyplot.subplots(figsize=(width, 3.6))
    plot_by_case(axes, tables, rows, names, tools, TIME_AXIS)
    log_scale(axes, "y")
    axes.set_ylabel("wall time (s)")
    axes.set_title("The published image sets, smallest box first")
    return finish_figure(
        figure,
        tool_handles(tools, False),
        censored_handles(tables, rows, TIME_AXIS),
        width,
    )


DENSE_ADAPTERS = (gudhi, dipha, cubical_ripser, pychomp2)

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
)
