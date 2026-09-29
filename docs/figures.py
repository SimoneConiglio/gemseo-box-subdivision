# Copyright 2026 Simone Coniglio
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""Draw the figures of the documentation.

Each figure is written twice, once for the light theme and once for the dark one,
the pages including both and the theme showing the right one. The files are
committed, so that building the documentation needs no plotting:

```shell
python docs/figures.py
```

Naming some of them writes only those, which is how the animation is refreshed
without rerunning every figure that runs the benchmarks:

```shell
python docs/figures.py solve
```

The animation is a GIF on a solid background, the format having no partial
transparency, and the data profiles are drawn from the file
``python -m benchmarks.data_profiles`` writes.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib
from numpy import arange
from numpy import array
from numpy import cos
from numpy import e
from numpy import exp
from numpy import linspace
from numpy import log
from numpy import log1p
from numpy import meshgrid
from numpy import pi
from numpy import sqrt

matplotlib.use("Agg")

import operator

import matplotlib.pyplot as plt  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Sequence

DIRECTORY = Path(__file__).parent / "_static" / "figures"
"""The directory of the figures."""

LIGHT = "#24292f"
"""The foreground of the light theme."""

DARK = "#c9d1d9"
"""The foreground of the dark theme."""

ACCENT = "#e8590c"
"""The colour marking what the figure is about."""

SECOND = "#1c7ed6"
"""The colour of the second series of a figure."""

THIRD = "#2f9e44"
"""The colour of the third series of a figure."""

FOURTH = "#ae3ec9"
"""The colour of the fourth series of a figure."""


def rastrigin(x, y):
    """Return the Rastrigin function of two variables."""
    return 20.0 + x**2 - 10.0 * cos(2 * pi * x) + y**2 - 10.0 * cos(2 * pi * y)


def ackley(x, y):
    """Return the Ackley function of two variables."""
    return (
        -20.0 * exp(-0.2 * sqrt(0.5 * (x**2 + y**2)))
        - exp(0.5 * (cos(2 * pi * x) + cos(2 * pi * y)))
        + e
        + 20.0
    )


def styblinski_tang(x, y):
    """Return the Styblinski-Tang function of two variables."""
    return 0.5 * (x**4 - 16 * x**2 + 5 * x + y**4 - 16 * y**2 + 5 * y)


def griewank(x, y):
    """Return the Griewank function of two variables."""
    return 1.0 + (x**2 + y**2) / 4000.0 - cos(x) * cos(y / sqrt(2.0))


def partly_multimodal(x, y):
    """Return the partly multimodal function, Rastrigin against a parabola."""
    return 10.0 + x**2 - 10.0 * cos(2 * pi * x) + y**2


SERIES_LIGHT = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4")
"""The categorical hues of the five methods, on a light surface.

Taken in this fixed order and never cycled, so that a method keeps its hue in
every figure. Validated for the lightness band, the chroma floor, colour-vision
separation and contrast; the light steps sit below 3:1 against the surface, which
is why every figure using them is accompanied by its table.
"""

SERIES_DARK = ("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181")
"""The same five hues stepped for a dark surface, not an automatic flip."""

METHOD_LABELS = (
    "box subdivision",
    "multistart",
    "CMA-ES",
    "DIRECT",
    "EGO",
)
"""The methods, in the order their hues are assigned."""


def series(foreground: str) -> tuple[str, ...]:
    """Return the hues of the methods for the theme being drawn.

    Args:
        foreground: The foreground colour of the theme.

    Returns:
        The hue of each method, in the order of :data:`.METHOD_LABELS`.
    """
    return SERIES_LIGHT if foreground == LIGHT else SERIES_DARK


def _style(foreground: str) -> dict[str, object]:
    """Return the style of a theme.

    Args:
        foreground: The colour of the text and of the axes.

    Returns:
        The matplotlib settings.
    """
    return {
        "figure.facecolor": "none",
        "axes.facecolor": "none",
        "savefig.facecolor": "none",
        "savefig.transparent": True,
        "text.color": foreground,
        "axes.labelcolor": foreground,
        "axes.edgecolor": foreground,
        "xtick.color": foreground,
        "ytick.color": foreground,
        "axes.titlecolor": foreground,
        "font.size": 9,
        "axes.titlesize": 10,
        "legend.frameon": False,
        "legend.labelcolor": foreground,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "svg.fonttype": "none",
    }


def save(name: str, draw, extension: str = "svg") -> None:
    """Draw a figure for both themes and write it.

    Args:
        name: The name of the figure, without its extension.
        draw: The function drawing the figure, taking the foreground colour.
        extension: The format, ``"png"`` for the figures holding a filled
            contour, whose vector form weighs tens of megabytes.
    """
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    for suffix, foreground in (("", LIGHT), ("-dark", DARK)):
        with plt.rc_context(_style(foreground)):
            figure = draw(foreground)
            figure.savefig(
                DIRECTORY / f"{name}{suffix}.{extension}",
                bbox_inches="tight",
                format=extension,
                dpi=160,
            )
            plt.close(figure)


def draw_subdivision(foreground: str):
    """Draw the Cartesian subdivision of a design space."""
    figure, axes = plt.subplots(figsize=(5.2, 4.4))
    x = linspace(-4.1, 5.9, 400)
    grid_x, grid_y = meshgrid(x, x)
    axes.contourf(grid_x, grid_y, rastrigin(grid_x, grid_y), 40, cmap="Greys_r")
    breakpoints = linspace(-4.1, 5.9, 11)
    for position in breakpoints:
        axes.axvline(position, color=foreground, linewidth=0.5, alpha=0.5)
        axes.axhline(position, color=foreground, linewidth=0.5, alpha=0.5)

    axes.add_patch(
        plt.Rectangle(
            (breakpoints[4], breakpoints[4]),
            breakpoints[5] - breakpoints[4],
            breakpoints[5] - breakpoints[4],
            facecolor="none",
            edgecolor=ACCENT,
            linewidth=2.5,
        )
    )
    axes.plot([0.0], [0.0], marker="*", color=ACCENT, markersize=14, linestyle="none")
    axes.set_xlabel("$x_1$")
    axes.set_ylabel("$x_2$")
    axes.set_title(
        "One box per cell, one sub-problem per box\n"
        r"$\alpha$ selects the box, the sub-problem solves inside it"
    )
    return figure


def draw_bilevel(foreground: str):
    """Draw the exchange between the master and the sub-problem."""
    figure, axes = plt.subplots(figsize=(6.0, 2.9))
    axes.set_axis_off()
    boxes = (
        (0.02, "Master, a MINLP\nover the one-hot $\\alpha$\n(which box)", SECOND),
        (0.56, "Sub-problem, an NLP\nover $x$ inside the box\n(where in it)", THIRD),
    )
    for left, label, colour in boxes:
        axes.add_patch(
            plt.Rectangle(
                (left, 0.28),
                0.42,
                0.52,
                transform=axes.transAxes,
                facecolor="none",
                edgecolor=colour,
                linewidth=2.0,
            )
        )
        axes.text(
            left + 0.21,
            0.54,
            label,
            transform=axes.transAxes,
            ha="center",
            va="center",
            color=foreground,
        )

    axes.annotate(
        "",
        xy=(0.56, 0.66),
        xytext=(0.44, 0.66),
        xycoords=axes.transAxes,
        arrowprops={"arrowstyle": "-|>", "color": foreground, "linewidth": 1.4},
    )
    axes.text(
        0.5, 0.72, r"box $\alpha^{(i)}$", ha="center", color=foreground, fontsize=8.5
    )
    axes.annotate(
        "",
        xy=(0.44, 0.42),
        xytext=(0.56, 0.42),
        xycoords=axes.transAxes,
        arrowprops={"arrowstyle": "-|>", "color": foreground, "linewidth": 1.4},
    )
    axes.text(
        0.5,
        0.3,
        "value and post-optimal\nsensitivity, one cut",
        ha="center",
        va="center",
        color=foreground,
        fontsize=8.5,
    )
    axes.text(
        0.5,
        0.06,
        "the master keeps every cut, so each solved box narrows the choice of the next",
        ha="center",
        color=foreground,
        fontsize=8.5,
        alpha=0.85,
    )
    return figure


def draw_cuts(foreground: str):
    """Draw why a cut needs the convexification."""
    figure, (left, right) = plt.subplots(1, 2, figsize=(7.4, 3.0), sharey=True)
    alpha = linspace(0.0, 1.0, 300)
    value = 3.0 - 6.0 * alpha + 8.0 * alpha * (1.0 - alpha)

    for axes, corrected in ((left, False), (right, True)):
        axes.plot(alpha, value, color=foreground, linewidth=1.8, label="$u(\\alpha)$")
        slope = -6.0 + 8.0 - 16.0 * 0.0
        if corrected:
            slope -= 9.0
        axes.plot(
            alpha,
            value[0] + slope * alpha,
            color=ACCENT,
            linewidth=1.8,
            linestyle="--",
            label="cut at $\\alpha = 0$",
        )
        axes.plot([0.0, 1.0], [value[0], value[-1]], "o", color=SECOND, markersize=6)
        axes.set_xlabel(r"$\alpha$, relaxed between two boxes")
        axes.set_title(
            "without the convexification,\nthe cut cuts the optimum off"
            if not corrected
            else "with it, the cut stays below\nthe value at both boxes"
        )
        axes.legend(loc="upper right", fontsize=8)

    left.set_ylabel("value of the sub-problem")
    return figure


def draw_convexification(foreground: str):
    """Draw the convexification term and its effect on a cut slope."""
    figure, axes = plt.subplots(figsize=(4.8, 3.0))
    alpha = linspace(0.0, 1.0, 300)
    axes.plot(
        alpha,
        alpha * (alpha - 1.0),
        color=ACCENT,
        linewidth=2.0,
        label=r"$\alpha(\alpha-1)$",
    )
    axes.axhline(0.0, color=foreground, linewidth=0.8, alpha=0.6)
    axes.plot([0.0, 1.0], [0.0, 0.0], "o", color=SECOND, markersize=7)
    axes.annotate(
        "zero at every box,\nso the discrete problem is unchanged",
        xy=(1.0, 0.0),
        xytext=(0.30, 0.06),
        color=foreground,
        fontsize=8.5,
        arrowprops={"arrowstyle": "-", "color": foreground, "alpha": 0.6},
    )
    axes.annotate(
        r"lowered by $\kappa/4$ between them",
        xy=(0.5, -0.25),
        xytext=(0.16, -0.20),
        color=foreground,
        fontsize=8.5,
        arrowprops={"arrowstyle": "-", "color": foreground, "alpha": 0.6},
    )
    axes.set_xlabel(r"$\alpha$, relaxed")
    axes.set_title("The convexification acts in the space of the box choice")
    axes.legend(loc="lower right", fontsize=8)
    return figure


def draw_trust_region(foreground: str):
    """Draw how each metric of the trust region depends on where the run sits."""
    figure, axes_grid = plt.subplots(2, 2, figsize=(6.6, 6.4), sharex=True)
    indexes = arange(10)
    # The same two radii seen from a low incumbent and from a high one.
    rows = (
        ("catalogue values, radius 3", "indexes", 3),
        ("components changed, radius 1", "unit", 1),
    )
    incumbents = ((1, 1), (7, 6))
    for axes_row, (label, metric, radius) in zip(axes_grid, rows, strict=True):
        for axes, incumbent in zip(axes_row, incumbents, strict=True):
            admitted = 0
            for i in indexes:
                for j in indexes:
                    if metric == "unit":
                        # Every subdivision weighs one, so a candidate pays one
                        # per component it changes. int(), a sum of two NumPy
                        # booleans being their disjunction rather than a count.
                        cost = int(i != incumbent[0]) + int(j != incumbent[1])
                    else:
                        # The weight charged is the index the *incumbent* holds,
                        # so what a move costs depends on where the run sits and
                        # not on where it goes.
                        cost = (
                            int(i != incumbent[0]) * incumbent[0]
                            + int(j != incumbent[1]) * incumbent[1]
                        )

                    admitted += cost <= radius
                    axes.add_patch(
                        plt.Rectangle(
                            (i - 0.5, j - 0.5),
                            1.0,
                            1.0,
                            facecolor=SECOND if cost <= radius else "none",
                            alpha=0.35 if cost <= radius else 1.0,
                            edgecolor=foreground,
                            linewidth=0.4,
                        )
                    )

            axes.plot(
                [incumbent[0]], [incumbent[1]], marker="s", color=ACCENT, markersize=8
            )
            axes.set_xlim(-0.6, 9.6)
            axes.set_ylim(-0.6, 9.6)
            axes.set_aspect("equal")
            axes.set_title(
                f"incumbent {incumbent}: {admitted} of 100", fontsize=8.5, pad=4
            )

        axes_row[0].set_ylabel(f"{label}\n\nbox index of $x_2$", fontsize=8.5)

    for axes in axes_grid[1]:
        axes.set_xlabel("box index of $x_1$", fontsize=8.5)

    figure.suptitle(
        "The catalogue values make the region depend on where the run sits;\n"
        "counting components makes it the same everywhere",
        fontsize=9.5,
    )
    return figure


def draw_complexity(foreground: str):  # noqa: ARG001
    """Draw what grows with the dimension, the boxes or the master."""
    figure, axes = plt.subplots(figsize=(5.6, 3.2))
    dimensions = arange(1, 11)
    for subdivisions, colour in ((10, ACCENT), (2, SECOND)):
        axes.semilogy(
            dimensions,
            subdivisions**dimensions,
            color=colour,
            linewidth=1.8,
            label=f"boxes, $m={subdivisions}$",
        )
        axes.semilogy(
            dimensions,
            subdivisions * dimensions,
            color=colour,
            linewidth=1.8,
            linestyle="--",
            label=f"binaries, $m={subdivisions}$",
        )

    axes.set_xlabel("number of design variables")
    axes.set_ylabel("count")
    axes.set_title("The master grows with the binaries, not with the boxes")
    axes.legend(fontsize=8, ncols=2)
    return figure


def draw_hierarchy(foreground: str):
    """Draw the shapes of hierarchy, and the frontier that backtracks."""
    figure, axes_row = plt.subplots(1, 3, figsize=(11.0, 3.4))
    for axes in axes_row:
        axes.set_xticks([])
        axes.set_yticks([])
        axes.set_aspect("equal")
        axes.set_xlim(0, 1)
        axes.set_ylim(0, 1)

    def grid(axes, count, origin=(0.0, 0.0), size=1.0, colour=None, width=0.6):
        """Draw a grid of boxes."""
        step = size / count
        for i in range(count):
            for j in range(count):
                axes.add_patch(
                    plt.Rectangle(
                        (origin[0] + i * step, origin[1] + j * step),
                        step,
                        step,
                        facecolor="none",
                        edgecolor=colour or foreground,
                        linewidth=width,
                    )
                )

    # Two levels: a coarse grid, one box refined.
    grid(axes_row[0], 2)
    grid(axes_row[0], 5, origin=(0.5, 0.0), size=0.5, colour=ACCENT, width=0.9)
    axes_row[0].add_patch(
        plt.Rectangle(
            (0.5, 0.0), 0.5, 0.5, facecolor="none", edgecolor=ACCENT, linewidth=2.4
        )
    )
    axes_row[0].set_title("two levels\ncoarse, then one box refined")

    # Deep: the same box split again and again.
    origin, size = (0.0, 0.0), 1.0
    for depth in range(4):
        grid(
            axes_row[1],
            2,
            origin=origin,
            size=size,
            colour=ACCENT if depth == 3 else foreground,
            width=0.9 if depth == 3 else 0.6,
        )
        size /= 2.0
        origin = (origin[0] + size, origin[1])

    axes_row[1].set_title("deep and narrow\neach level splits in two")

    # Frontier: open boxes at several levels, the next one taken marked.
    grid(axes_row[2], 2)
    grid(axes_row[2], 2, origin=(0.5, 0.5), size=0.5, colour=SECOND, width=0.9)
    grid(axes_row[2], 2, origin=(0.0, 0.0), size=0.5, colour=SECOND, width=0.9)
    axes_row[2].add_patch(
        plt.Rectangle(
            (0.25, 0.0), 0.25, 0.25, facecolor=ACCENT, alpha=0.35, edgecolor=ACCENT
        )
    )
    axes_row[2].add_patch(
        plt.Rectangle(
            (0.5, 0.75), 0.25, 0.25, facecolor=ACCENT, alpha=0.35, edgecolor=ACCENT
        )
    )
    axes_row[2].set_title("frontier\nopen boxes of every level compete")
    return figure


def draw_multiresolution(foreground: str):
    """Draw the digits of the box index, and what the encoding saves."""
    figure, axes_pair = plt.subplots(1, 2, figsize=(9.0, 3.6))

    # Left: three levels of a base-2 subdivision of one variable. Each level
    # halves the interval its predecessors selected, so the digits it selects
    # are the base-2 representation of the box index.
    axes = axes_pair[0]
    digits = (1, 0, 1)
    for level, digit in enumerate(digits):
        count = 2 ** (level + 1)
        width = 1.0 / count
        # The cell selected is the value of the digits read so far, in base two.
        selected = int("".join(str(d) for d in digits[: level + 1]), 2)
        for index in range(count):
            axes.add_patch(
                plt.Rectangle(
                    (index * width, -level - 0.35),
                    width,
                    0.7,
                    facecolor=ACCENT if index == selected else "none",
                    alpha=0.4 if index == selected else 1.0,
                    edgecolor=foreground,
                    linewidth=0.6,
                )
            )

        axes.text(
            -0.04,
            -level,
            f"level {level + 1},  $d_{level + 1}={digit}$",
            ha="right",
            va="center",
            fontsize=8.5,
            color=foreground,
        )
        axes.text(
            (selected + 0.5) * width,
            -level,
            str(selected),
            ha="center",
            va="center",
            fontsize=8,
            color=foreground,
        )

    axes.set_xlim(-0.62, 1.03)
    axes.set_ylim(-2.75, 0.75)
    axes.axis("off")
    axes.set_title(
        "Each level halves what the one above selected:\n"
        "the digits $(1,0,1)$ are box $5$ of $8$",
        fontsize=9,
    )

    # Right: the binaries a resolution costs, flat against levels.
    axes = axes_pair[1]
    resolutions = array([4, 8, 16, 32, 64, 128])
    dimension = 5
    axes.plot(
        resolutions,
        dimension * resolutions,
        marker="o",
        color=SECOND,
        label="flat, $n\\,m$",
    )
    for branching, style in ((2, "-"), (4, "--")):
        levels = log(resolutions) / log(branching)
        axes.plot(
            resolutions,
            dimension * branching * levels,
            style,
            marker="s",
            color=ACCENT,
            label=f"levels of $m={branching}$, $n\\,m\\,L$",
        )

    axes.set_xscale("log", base=2)
    axes.set_yscale("log", base=2)
    axes.set_xlabel("subdivisions per component reached")
    axes.set_ylabel("binaries of the master")
    axes.set_title(
        "Five variables: the resolution grows as a power,\nthe binaries as a product",
        fontsize=9,
    )
    axes.legend(fontsize=8)
    figure.tight_layout()
    return figure


def draw_partial_refinement(foreground: str):
    """Draw a subdivision of some of the variables only."""
    figure, axes = plt.subplots(figsize=(5.0, 4.2))
    x = linspace(-4.1, 5.9, 300)
    grid_x, grid_y = meshgrid(x, x)
    axes.contourf(grid_x, grid_y, partly_multimodal(grid_x, grid_y), 40, cmap="Greys_r")
    for position in linspace(-4.1, 5.9, 11):
        axes.axvline(position, color=ACCENT, linewidth=0.9)

    axes.plot([0.0], [0.0], marker="*", color="#ffd43b", markersize=14)
    axes.set_xlabel("$x_1$, subdivided, the objective is multimodal in it")
    axes.set_ylabel("$x_2$, left to the sub-problem")
    axes.set_title("Subdividing the variables that need it, and only those")
    return figure


def draw_problems(foreground: str):
    """Draw the benchmark problems in two dimensions."""
    problems = (
        ("Rastrigin", rastrigin, -4.1, 5.9, (0.0, 0.0)),
        ("Ackley", ackley, -28.7, 34.9, (0.0, 0.0)),
        ("Styblinski-Tang", styblinski_tang, -4.9, 5.1, (-2.903534, -2.903534)),
        ("Griewank", griewank, -58.1, 61.9, (0.0, 0.0)),
        ("Partly multimodal", partly_multimodal, -4.1, 5.9, (0.0, 0.0)),
    )
    figure, axes_grid = plt.subplots(2, 3, figsize=(8.4, 5.8))
    axes_row = axes_grid.ravel()
    axes_row[-1].set_axis_off()
    for axes, (name, function, lower, upper, optimum) in zip(
        axes_row, problems, strict=False
    ):
        x = linspace(lower, upper, 400)
        grid_x, grid_y = meshgrid(x, x)
        values = function(grid_x, grid_y)
        # A logarithmic scale, the linear one hiding the basins of the flat
        # problems behind the growth of their envelope.
        axes.contourf(grid_x, grid_y, log1p(values - values.min()), 60, cmap="viridis")
        axes.plot(
            [optimum[0]],
            [optimum[1]],
            marker="*",
            color="#ffd43b",
            markersize=13,
            markeredgecolor=LIGHT,
            markeredgewidth=0.6,
            linestyle="none",
        )
        axes.set_title(name)
        axes.set_xticks([])
        axes.set_yticks([])
        axes.set_aspect("equal")

    figure.supxlabel(
        "logarithmic colour scale, the star marking the global optimum",
        color=foreground,
        fontsize=8.5,
    )
    return figure


def draw_landscape_slice(foreground: str):
    """Draw a one-dimensional slice of each problem, on a common scale."""
    figure, axes = plt.subplots(figsize=(6.4, 3.0))
    for name, function, lower, upper, colour in (
        ("Rastrigin", rastrigin, -4.1, 5.9, ACCENT),
        ("Ackley", ackley, -28.7, 34.9, SECOND),
        ("Griewank", griewank, -58.1, 61.9, THIRD),
    ):
        x = linspace(lower, upper, 800)
        values = function(x, 0.0 * x)
        axes.plot(
            (x - lower) / (upper - lower),
            (values - values.min()) / (values.max() - values.min()),
            color=colour,
            linewidth=1.4,
            label=name,
        )

    axes.set_xlabel("position in the range of the variable")
    axes.set_ylabel("objective, normalized")
    axes.set_title("How far apart the basins are, at the same scale")
    axes.legend(fontsize=8)
    return figure


def _sample(method: str, budget: int = 400):
    """Return the points a method evaluates on Rastrigin in two dimensions.

    Args:
        method: The name of the method.
        budget: The budget in equivalent objective evaluations.

    Returns:
        The evaluated points.
    """
    import logging
    import sys

    # The benchmarks live at the root of the repository, not on the path of a
    # script run from the documentation directory.
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from benchmarks import baselines
    from benchmarks.problems import PROBLEMS

    logging.disable(logging.CRITICAL)
    points = []

    def recording(base):
        """Return a counter class recording where the objective is evaluated."""

        class Recorder(base):
            """A counter recording where the objective is evaluated."""

            def objective(self, x):  # noqa: ANN001, ANN202, D102
                points.append(x.copy())
                return super().objective(x)

        return Recorder

    # The methods using no gradient count with the plain counter, the others
    # with the budgeted one, so both have to be recorded.
    originals = (baselines.BudgetedCounter, baselines.Counter)
    baselines.BudgetedCounter = recording(originals[0])
    baselines.Counter = recording(originals[1])
    try:
        baselines.run(method, PROBLEMS["rastrigin"], 2, 11, budget)
    finally:
        baselines.BudgetedCounter, baselines.Counter = originals

    return array(points)


def draw_sampling(foreground: str):
    """Draw where each method evaluates the objective."""
    figure, axes_row = plt.subplots(1, 4, figsize=(12.0, 3.3))
    x = linspace(-4.1, 5.9, 300)
    grid_x, grid_y = meshgrid(x, x)
    values = rastrigin(grid_x, grid_y)
    titles = {
        "box_subdivision": "box subdivision",
        "multistart": "multistart of SLSQP",
        "cmaes": "CMA-ES",
        "direct": "DIRECT",
    }
    for axes, (method, title) in zip(axes_row, titles.items(), strict=True):
        axes.contourf(grid_x, grid_y, values, 30, cmap="Greys_r")
        sampled = _sample(method)
        axes.plot(
            sampled[:, 0],
            sampled[:, 1],
            marker="o",
            markersize=2.0,
            linestyle="none",
            color=ACCENT,
            alpha=0.75,
        )
        axes.plot(
            [0.0], [0.0], marker="*", color="#ffd43b", markersize=12, linestyle="none"
        )
        axes.set_title(f"{title}\n{len(sampled)} evaluations")
        axes.set_xticks([])
        axes.set_yticks([])
        axes.set_aspect("equal")

    figure.supxlabel(
        "Rastrigin in two dimensions, the same budget of 400 equivalent "
        "evaluations offered to each,\nthe star marking the global optimum. "
        "The count is what each method spent before stopping,\nnot what it was "
        "allowed.",
        color=foreground,
        fontsize=8.5,
    )
    return figure


def draw_results(foreground: str):
    """Draw the cost of the best variant and of the baselines, per problem."""
    data = _read_profiles()
    names = {"rastrigin": "Rastrigin", "ackley": "Ackley"}
    names |= {"styblinski_tang": "Styblinski", "griewank": "Griewank"}
    cells = [
        (problem, dimension) for problem in data["problems"] for dimension in ("2", "5")
    ]
    labels = [f"{names[problem]} {dimension}" for problem, dimension in cells]
    hues = series(foreground)
    methods = {"best variant": None} | {
        name: label for name, label in BASELINE_LABELS.items() if name != "egobox"
    }
    figure, axes = plt.subplots(figsize=(8.6, 3.6))
    positions = arange(len(labels))
    width = 0.2
    for index, (method, label) in enumerate(methods.items()):
        values, reached, budgets = [], [], []
        for problem, dimension in cells:
            entry = data["dimensions"][dimension]
            name = entry["ranking"][0] if label is None else method
            _, cost, count = entry["summary"][name][problem]
            values.append(cost)
            reached.append(count)
            budgets.append(entry["budget"])

        bars = axes.bar(
            positions + (index - 1.5) * width,
            values,
            width,
            color=hues[index],
            label="box subdivision, best variant" if label is None else label,
        )
        for bar, count, cost, budget in zip(
            bars, reached, values, budgets, strict=True
        ):
            if cost >= budget:
                bar.set_hatch("///")
                bar.set_edgecolor("white")

            if count:
                axes.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 30,
                    str(count),
                    ha="center",
                    fontsize=7,
                    color=hues[index],
                )

    axes.text(
        0.5,
        -0.42,
        "hatched: stopped by the budget, so the cost is the budget and the "
        "gap an upper bound",
        transform=axes.transAxes,
        ha="center",
        fontsize=7.5,
        style="italic",
    )
    axes.set_xticks(positions)
    axes.set_xticklabels(labels, rotation=20, ha="right")
    axes.set_ylabel("median equivalent evaluations")
    axes.set_title(
        "Cost at equal budget, and the starting points of five reaching the optimum",
        pad=26,
    )
    axes.legend(ncols=4, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, 1.10))
    return figure


EXTENSIONS_BUDGET = 2500
"""The budget of the comparison of the extensions."""

EXTENSIONS = {
    "Rastrigin": {
        "flat $m=2$": (4.975, 888, 0),
        "flat $m=10$": (0.0, 1920, 6),
        "2 then 5, value": (4.975, 1986, 0),
        "2 then 5, cuts": (2.452, 1947, 0),
        "deep, 4 of 2": (4.975, 1672, 0),
        "frontier": (6.700, 2500, 0),
    },
    "Ackley": {
        "flat $m=2$": (14.430, 873, 0),
        "flat $m=10$": (6.302, 2500, 0),
        "2 then 5, value": (6.302, 2417, 0),
        "2 then 5, cuts": (8.107, 2458, 0),
        "deep, 4 of 2": (0.0, 2387, 4),
        "frontier": (9.714, 2500, 0),
    },
    "Styblinski-Tang": {
        "flat $m=2$": (0.0, 486, 5),
        "flat $m=10$": (0.0, 532, 1),
        "2 then 5, value": (0.0, 872, 5),
        "2 then 5, cuts": (0.0, 987, 5),
        "deep, 4 of 2": (0.0, 1494, 5),
        "frontier": (0.0, 2500, 6),
    },
}
"""The hierarchies against the flat subdivisions, by problem.

Each entry is the median distance to the optimum, the median cost and the number
of the six starting points from which the optimum was reached.
"""


def draw_extensions(foreground: str):
    """Draw what the hierarchies are worth against the flat subdivisions."""
    methods = tuple(next(iter(EXTENSIONS.values())))
    colours = (SECOND, "#4dabf7", ACCENT, "#f08c00", THIRD, "#868e96")
    figure, axes_grid = plt.subplots(2, 3, figsize=(11.5, 5.4), sharex="col")
    positions = arange(len(methods))
    for column, (problem, methods_of) in enumerate(EXTENSIONS.items()):
        gaps = [methods_of[method][0] for method in methods]
        costs = [methods_of[method][1] for method in methods]
        reached = [methods_of[method][2] for method in methods]
        for row, (values, label) in enumerate((
            (gaps, "distance to the optimum"),
            (costs, "equivalent evaluations"),
        )):
            axes = axes_grid[row][column]
            drawn = [0.0 if value is None else value for value in values]
            bars = axes.bar(positions, drawn, 0.68, color=colours)
            if row == 1:
                # A cost reaching the budget is a run the budget stopped, so its
                # gap in the row above is an upper bound and not a result.
                for bar, cost in zip(bars, costs, strict=True):
                    if cost is not None and cost >= EXTENSIONS_BUDGET:
                        bar.set_hatch("///")
                        bar.set_edgecolor("white")

            for bar, value, count in zip(bars, values, reached, strict=True):
                if value is None:
                    axes.text(
                        bar.get_x() + bar.get_width() / 2,
                        0.0,
                        "not run",
                        ha="center",
                        va="bottom",
                        rotation=90,
                        fontsize=7,
                        color=foreground,
                        alpha=0.7,
                    )
                elif row == 0 and count:
                    axes.text(
                        bar.get_x() + bar.get_width() / 2,
                        max(drawn) * 0.02 + value,
                        "\u2713" * count,
                        ha="center",
                        fontsize=6.5,
                        color=colours[list(bars).index(bar)],
                    )

            if row == 0 and max(drawn) <= 1e-6:
                # Every run solved the problem: a bar chart of zeros says
                # nothing, so the panel says it in words.
                axes.set_ylim(0.0, 1.0)
                axes.text(
                    positions.mean(),
                    0.45,
                    "every configuration reaches the optimum,\nthey differ in cost",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color=foreground,
                )
            elif row == 0:
                axes.set_ylim(0.0, max(drawn) * 1.25)

            if column == 0:
                axes.set_ylabel(label)

            if row == 0:
                axes.set_title(problem)
            else:
                axes.set_xticks(positions)
                axes.set_xticklabels(methods, rotation=35, ha="right", fontsize=8)

    figure.suptitle(
        "Five variables, one budget of 2500, median over six starting points, "
        "a tick per run reaching the optimum;\nhatched costs are runs the budget "
        "stopped, whose gap above is an upper bound",
        fontsize=9.5,
    )
    figure.tight_layout()
    return figure


ENCODINGS_BUDGET = 2500
"""The budget of the comparison of the encodings."""

ENCODINGS = {
    "Rastrigin": {
        "flat $m=10$": (0.000, 50, 10, 2103, 3),
        "flat $m=16$": (1.990, 80, 16, 1706, 0),
        "$m=2$, $L=4$": (2.985, 40, 16, 2500, 0),
        "$m=2$, $L=5$": (5.252, 50, 32, 2338, 0),
        "$m=4$, $L=2$": (1.990, 40, 16, 1953, 1),
        "$m=4$, $L=3$": (3.142, 60, 64, 1409, 1),
        "$m=2$, $L=4$, pos.": (7.043, 40, 16, 2500, 0),
    },
    "Ackley": {
        "flat $m=10$": (6.302, 50, 10, 2500, 0),
        "flat $m=16$": (12.632, 80, 16, 2500, 0),
        "$m=2$, $L=4$": (7.076, 40, 16, 2500, 0),
        "$m=2$, $L=5$": (14.819, 50, 32, 2500, 0),
        "$m=4$, $L=2$": (7.398, 40, 16, 2457, 0),
        "$m=4$, $L=3$": (6.280, 60, 64, 2500, 0),
        "$m=2$, $L=4$, pos.": (16.807, 40, 16, 2500, 0),
    },
    "Styblinski-Tang": {
        "flat $m=10$": (14.137, 50, 10, 598, 1),
        "flat $m=16$": (0.000, 80, 16, 973, 2),
        "$m=2$, $L=4$": (14.435, 40, 16, 1281, 0),
        "$m=2$, $L=5$": (14.700, 50, 32, 1280, 0),
        "$m=4$, $L=2$": (0.266, 40, 16, 920, 1),
        "$m=4$, $L=3$": (5.667, 60, 64, 840, 0),
        "$m=2$, $L=4$, pos.": (3.675, 40, 16, 1656, 1),
    },
}
"""The encodings against the flat subdivisions, by problem.

Each entry is the median distance to the optimum, the binaries of the master, the
subdivisions per component reached, the median cost, and the number of the three
starting points from which the optimum was reached.
"""


def draw_encodings(foreground: str):
    """Draw what the multi-resolution encoding buys, and what it does not."""
    problems = tuple(ENCODINGS)
    names = tuple(next(iter(ENCODINGS.values())))
    figure, axes_grid = plt.subplots(
        2,
        len(problems),
        figsize=(4.6 * len(problems), 5.6),
        sharex="col",
        squeeze=False,
    )
    positions = arange(len(names))
    # The flat encodings first, in a colour of their own.
    colours = [
        SECOND
        if name.startswith("flat")
        else ACCENT
        if "pos." not in name
        else "#868e96"
        for name in names
    ]
    for column, problem in enumerate(problems):
        entries = ENCODINGS[problem]
        gaps = [entries[name][0] for name in names]
        binaries = [entries[name][1] for name in names]
        costs = [entries[name][3] for name in names]
        reached = [entries[name][4] for name in names]

        axes = axes_grid[0][column]
        bars = axes.bar(positions, gaps, 0.68, color=colours)
        for bar, cost, count in zip(bars, costs, reached, strict=True):
            if cost >= ENCODINGS_BUDGET:
                bar.set_hatch("///")
                bar.set_edgecolor("white")

            if count:
                axes.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(gaps) * 0.02,
                    "\u2713" * count,
                    ha="center",
                    fontsize=6.5,
                    color=foreground,
                )

        axes.set_ylim(0.0, max(gaps) * 1.2)
        axes.set_title(problem)
        if column == 0:
            axes.set_ylabel("distance to the optimum")

        axes = axes_grid[1][column]
        axes.bar(positions, binaries, 0.68, color=colours)
        axes.set_xticks(positions)
        axes.set_xticklabels(names, rotation=35, ha="right", fontsize=8)
        if column == 0:
            axes.set_ylabel("binaries of the master")

    figure.suptitle(
        "Five variables, one budget of 2500, median over three starting points. "
        "The encodings reach\ntheir resolution on fewer binaries; hatched runs "
        "were stopped by the budget",
        fontsize=9.5,
    )
    figure.tight_layout()
    return figure


SMALL_BUDGET = {
    # problem, dimension -> per method: (gap, reached out of three, seconds per run)
    ("Rastrigin", 2): (
        (0.000, 3, 1.0),
        (0.000, 2, 0.2),
        (0.995, 0, 0.1),
        (0.000, 3, 0.02),
        (0.000, 2, 147.9),
    ),
    ("Ackley", 2): (
        (0.000, 2, 0.6),
        (9.581, 0, 0.2),
        (0.000, 3, 0.1),
        (0.000, 3, 0.02),
        (0.320, 0, 161.9),
    ),
    ("Styblinski-Tang", 2): (
        (0.000, 3, 0.7),
        (0.000, 3, 0.1),
        (0.000, 2, 0.04),
        (0.000, 3, 0.02),
        (0.286, 0, 0.1),
    ),
    ("Griewank", 2): (
        (0.007, 0, 0.9),
        (0.067, 0, 0.1),
        (0.048, 0, 0.04),
        (0.009, 0, 0.02),
        (0.008, 0, 160.5),
    ),
    ("Rastrigin", 5): (
        (8.572, 0, 0.5),
        (9.950, 0, 0.2),
        (11.204, 0, 0.04),
        (4.976, 0, 0.02),
        (1.994, 0, 439.7),
    ),
    ("Ackley", 5): (
        (14.430, 0, 0.4),
        (17.062, 0, 0.1),
        (0.052, 0, 0.04),
        (0.107, 0, 0.02),
        (2.900, 0, 376.2),
    ),
    ("Styblinski-Tang", 5): (
        (0.000, 2, 0.6),
        (14.137, 1, 0.1),
        (0.003, 0, 0.04),
        (0.000, 3, 0.02),
        (0.138, 0, 20.1),
    ),
    ("Griewank", 5): (
        (0.061, 0, 0.4),
        (0.096, 0, 0.2),
        (0.381, 0, 0.04),
        (0.011, 0, 0.02),
        (0.104, 0, 424.8),
    ),
}
"""The five methods at one budget of 500 evaluations, by problem and dimension."""


def draw_small_budget(foreground: str):
    """Draw what each method reaches, and costs, when evaluations are scarce."""
    colours = series(foreground)
    problems = ("Rastrigin", "Ackley", "Styblinski-Tang", "Griewank")
    figure, axes_grid = plt.subplots(2, 2, figsize=(10.5, 5.8), sharex="col")
    positions = arange(len(problems))
    width = 0.16
    for column, dimension in enumerate((2, 5)):
        gaps_axes = axes_grid[0][column]
        cost_axes = axes_grid[1][column]
        for index, label in enumerate(METHOD_LABELS):
            offset = (index - 2) * width
            gaps = [SMALL_BUDGET[p, dimension][index][0] for p in problems]
            reached = [SMALL_BUDGET[p, dimension][index][1] for p in problems]
            seconds = [SMALL_BUDGET[p, dimension][index][2] for p in problems]
            bars = gaps_axes.bar(
                positions + offset,
                gaps,
                width * 0.88,
                color=colours[index],
                label=label,
            )
            # A mark under the axis per starting point reaching the optimum, so
            # that "solved" is not read off a bar of height zero. It is pinned to
            # the axis in its fraction, the symlog scale having no useful
            # coordinate below zero.
            for bar, count in zip(bars, reached, strict=True):
                if count:
                    gaps_axes.annotate(
                        "\u25cf" * count,
                        (bar.get_x() + bar.get_width() / 2, 0.0),
                        xycoords=("data", "axes fraction"),
                        xytext=(0, -9),
                        textcoords="offset points",
                        ha="center",
                        va="top",
                        fontsize=4.5,
                        color=colours[index],
                        annotation_clip=False,
                    )

            cost_axes.bar(
                positions + offset,
                seconds,
                width * 0.88,
                color=colours[index],
                label=label,
            )

        # The gaps span zero to seventeen, so a linear axis hides every
        # near-solved cell; symlog keeps zero at the baseline and compresses the
        # tail. The dots below the axis carry "solved" on their own.
        gaps_axes.set_yscale("symlog", linthresh=0.01, linscale=0.4)
        gaps_axes.set_ylim(bottom=0.0)
        gaps_axes.set_title(f"{dimension} variables", fontsize=10)
        gaps_axes.tick_params(labelbottom=False)
        cost_axes.set_yscale("log")
        cost_axes.set_xticks(positions)
        cost_axes.set_xticklabels(problems, rotation=20, ha="right", fontsize=8)
        if column == 0:
            gaps_axes.set_ylabel("distance to the optimum")
            cost_axes.set_ylabel("seconds per run")

    axes_grid[0][0].legend(
        ncols=5, fontsize=8, loc="lower center", bbox_to_anchor=(1.06, 1.12)
    )
    figure.suptitle(
        "One budget of 500 evaluations: what each method reaches, and what it "
        "costs to run.\nA dot below the axis per starting point reaching the "
        "optimum; the cost of an evaluation itself is not counted.",
        fontsize=9.5,
        y=1.10,
    )
    figure.tight_layout()
    return figure


def draw_density(foreground: str):  # noqa: ARG001
    """Draw what the subdivision density does at five variables."""
    figure, axes = plt.subplots(figsize=(7.2, 3.4))
    labels = ("Rastrigin", "Ackley", "Styblinski-Tang", "Griewank")
    # Median distance to the optimum, five variables, budget 2500.
    gaps = {
        2: (4.975, 14.430, 0.0, 0.061),
        4: (6.700, 12.632, 0.0, 0.224),
        10: (0.0, 6.302, 14.137, 0.027),
        16: (1.990, 12.632, 0.0, 0.054),
        24: (3.589, 8.526, 14.435, 0.084),
    }
    colours = ("#adb5bd", SECOND, ACCENT, THIRD, "#862e9c")
    positions = arange(len(labels))
    width = 0.17
    for index, (density, values) in enumerate(gaps.items()):
        axes.bar(
            positions + (index - 2) * width,
            values,
            width,
            color=colours[index],
            label=f"$m={density}$ ({5 * density} binaries)",
        )

    axes.set_xticks(positions)
    axes.set_xticklabels(labels, rotation=12, ha="right")
    axes.set_ylabel("distance to the optimum")
    axes.set_title(
        "Five variables: the useful density sits between the basins and the binaries",
        fontsize=10,
        pad=24,
    )
    axes.legend(ncols=5, fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, 1.12))
    return figure


DATA_PROFILES = Path(__file__).parent / "_static" / "data_profiles.json"
"""The profiles written by ``python -m benchmarks.data_profiles``."""

BASELINE_LABELS = {
    "multistart": "multistart",
    "cmaes": "CMA-ES",
    "direct": "DIRECT",
    "egobox": "EGO",
}
"""The label of each baseline of the data profiles."""


def _read_profiles() -> dict:
    """Return what ``python -m benchmarks.data_profiles`` wrote."""
    import json

    return json.loads(DATA_PROFILES.read_text(encoding="utf-8"))


def _plot_profile(axes, points, **settings) -> None:  # noqa: ANN001
    """Draw a profile from the evaluations where it changes.

    Args:
        axes: The axes.
        points: The evaluation and the fraction at each change.
        **settings: The settings of the line.
    """
    evaluations, ratios = zip(*points, strict=True)
    settings.setdefault("linewidth", 1.5)
    axes.plot(evaluations, ratios, drawstyle="steps-post", **settings)


def _profile_axes(axes, dimension: str, budget: int, title: str) -> None:  # noqa: ANN001
    """Set the axes of a panel of profiles.

    Args:
        axes: The axes.
        dimension: The number of design variables.
        budget: The budget of the panel.
        title: The title of the panel.
    """
    axes.set_title(f"{dimension} variables: {title}", fontsize=9.5)
    axes.set_xlim(1, budget)
    axes.set_ylim(0.0, 1.02)
    axes.yaxis.set_major_formatter(
        matplotlib.ticker.PercentFormatter(xmax=1.0, decimals=0)
    )
    axes.grid(alpha=0.25)


EXPLORING = ("probes_8", "probes_16", "ceiling_30", "ceiling_10", "margin_100")
"""The variants changing how the master explores, a hue each."""

RESOLVING = (
    "density_10",
    "proposed_density",
    "proposed_density_free",
    "multi_resolution",
    "deep_hierarchy",
)
"""The variants changing what the subdivision resolves, a hue each."""

AT_DENSITY_10 = {"density_10_ceiling_10": "ceiling_10"}
"""The exploring variants measured again at ten subdivisions per variable."""


def draw_variant_profiles(foreground: str):
    """Draw the profiles of the variants, one row per dimension."""
    data = _read_profiles()
    labels = data["labels"]
    hues = series(foreground)
    dimensions = data["dimensions"]
    figure, axes_grid = plt.subplots(
        len(dimensions),
        2,
        figsize=(10.4, 3.3 * len(dimensions)),
        sharey=True,
        squeeze=False,
    )
    for row, (dimension, entry) in zip(axes_grid, dimensions.items(), strict=True):
        profiles = entry["profiles"]
        budget = entry["budget"]
        for axes, names, title in (
            (row[0], EXPLORING, "how the master explores"),
            (row[1], RESOLVING, "what the subdivision resolves"),
        ):
            _plot_profile(
                axes,
                profiles["swept"],
                color=foreground,
                alpha=0.55,
                label=labels["swept"],
            )
            for hue, name in zip(hues, names, strict=False):
                if name in profiles:
                    _plot_profile(
                        axes,
                        profiles[name],
                        color=hue,
                        linestyle=":" if name == "proposed_density" else "-",
                        label=labels[name],
                    )

            _profile_axes(axes, dimension, budget, title)

        # The exploring variants at the density resolving Rastrigin, dashed in
        # the hue of the same variant at the default density, beside the swept
        # configuration at that density.
        if "density_10" in profiles and AT_DENSITY_10.keys() & profiles.keys():
            _plot_profile(
                row[0],
                profiles["density_10"],
                color=foreground,
                alpha=0.55,
                linestyle="--",
                label=labels["density_10"],
            )

        for name, twin in AT_DENSITY_10.items():
            if name in profiles:
                _plot_profile(
                    row[0],
                    profiles[name],
                    color=hues[EXPLORING.index(twin)],
                    linestyle="--",
                    label=labels[name],
                )

        row[0].set_ylabel("targets reached")

    for axes in axes_grid[-1]:
        axes.set_xlabel("equivalent evaluations")
        axes.legend(fontsize=7, loc="lower right", ncols=1)

    axes_grid[0][0].legend(fontsize=7, loc="lower right")
    axes_grid[0][1].legend(fontsize=7, loc="lower right")
    figure.tight_layout()
    return figure


def draw_data_profiles(foreground: str):
    """Draw the best variant against the baselines, one panel per dimension."""
    data = _read_profiles()
    hues = series(foreground)
    dimensions = data["dimensions"]
    figure, axes_grid = plt.subplots(
        1, len(dimensions), figsize=(9.6, 3.6), sharey=True, squeeze=False
    )
    axes_row = axes_grid[0]
    for axes, (dimension, entry) in zip(axes_row, dimensions.items(), strict=True):
        profiles = entry["profiles"]
        best = entry["ranking"][0]
        _plot_profile(
            axes,
            profiles[best],
            color=hues[0],
            linewidth=2.2,
            label=f"box subdivision: {data['labels'][best]}",
        )
        for hue, (name, label) in zip(hues[1:], BASELINE_LABELS.items(), strict=True):
            _plot_profile(axes, profiles[name], color=hue, label=label)
            # EGO's budget is shorter, so its curve is marked where it was
            # stopped rather than extended as if it had finished.
            end, ratio = profiles[name][-1]
            if end < entry["budget"]:
                axes.plot(end, ratio, marker="o", color=hue, markersize=4)

        optimal = len(entry["best_target_is_the_optimum"])
        _profile_axes(
            axes,
            dimension,
            entry["budget"],
            f"best target the optimum on {optimal} of {len(data['problems'])}",
        )
        axes.set_xlabel("equivalent evaluations")
        axes.legend(fontsize=7, loc="lower right")

    axes_row[0].set_ylabel("targets reached")
    figure.tight_layout()
    return figure


SOLVE_SEED = 11
"""The seed of the starting point of the animated run."""

BACKGROUNDS = {LIGHT: "#ffffff", DARK: "#14181e"}
"""The background of each theme, a GIF having no partial transparency."""


def _trace_solve():
    """Run the method on Rastrigin in two dimensions, recording every box.

    The run is the one of the README, the scenario with its default settings
    over ten subdivisions per variable, so what the animation shows is what a
    user gets.

    Returns:
        The box, the evaluated points, and the cost and best value once solved,
        of each box in the order the master chose them.
    """
    import logging

    sys.path.insert(0, str(Path(__file__).parent.parent))

    from benchmarks.baselines import _design_space
    from benchmarks.baselines import _starting_point
    from benchmarks.problems import PROBLEMS
    from benchmarks.problems import Counter
    from benchmarks.problems import Objective
    from numpy import argmax

    from gemseo_box_subdivision import BoxSubdivisionScenario
    from gemseo_box_subdivision.disciplines.box_mapping import BoxMapping

    logging.disable(logging.CRITICAL)
    problem = PROBLEMS["rastrigin"]
    solves = []
    current = [None]

    def run(self, input_data):  # noqa: ANN001, ANN202
        """Record the box the sub-problem is being solved in."""
        current[0] = tuple(
            int(i) for i in argmax(input_data["x_box"].reshape(2, -1), 1)
        )
        return original(self, input_data)

    class Recorder(Counter):
        """A counter recording each evaluation in the box it belongs to."""

        def objective(self, x):  # noqa: ANN001, ANN202, D102
            value = super().objective(x)
            if not solves or solves[-1]["box"] != current[0]:
                solves.append({"box": current[0], "points": [], "values": []})

            solves[-1]["points"].append(x.copy())
            solves[-1]["values"].append(value)
            solves[-1]["cost"] = self.cost(2, adjoint=True)
            solves[-1]["best"] = self.best
            return value

        def gradient(self, x):  # noqa: ANN001, ANN202, D102
            gradient = super().gradient(x)
            if solves:
                solves[-1]["cost"] = self.cost(2, adjoint=True)

            return gradient

    counter = Recorder(problem)
    original = BoxMapping._run
    BoxMapping._run = run
    try:
        BoxSubdivisionScenario(
            [Objective(counter, 2)],
            "f",
            _design_space(problem, 2, _starting_point(problem, 2, SOLVE_SEED)),
            n_subdivisions=10,
        ).execute()
    finally:
        BoxMapping._run = original
        logging.disable(logging.NOTSET)

    for solve in solves:
        solve["points"] = array(solve["points"])

    return solves


def _draw_solve_frame(foreground: str, solves, index: int, landscape):
    """Draw the run once the first boxes are solved.

    Args:
        foreground: The foreground colour of the theme.
        solves: The boxes in the order they were solved.
        index: The number of boxes solved.
        landscape: The grid and the values of the objective over it.

    Returns:
        The figure.
    """
    grid_x, grid_y, values, breakpoints = landscape
    width = breakpoints[1] - breakpoints[0]
    figure, (left, right) = plt.subplots(
        1, 2, figsize=(8.4, 3.9), gridspec_kw={"width_ratios": (1.0, 1.15)}
    )
    figure.set_facecolor(BACKGROUNDS[foreground])
    figure.subplots_adjust(wspace=0.32)
    left.contourf(grid_x, grid_y, values, 30, cmap="Greys_r")
    for position in breakpoints:
        left.axvline(position, color=foreground, linewidth=0.4, alpha=0.45)
        left.axhline(position, color=foreground, linewidth=0.4, alpha=0.45)

    done = solves[:index]
    best = min(done, key=operator.itemgetter("best")) if done else None
    for solve in done:
        i, j = solve["box"]
        left.add_patch(
            plt.Rectangle(
                (breakpoints[i], breakpoints[j]),
                width,
                width,
                facecolor=SECOND,
                alpha=0.35,
                linewidth=0,
            )
        )
        local = solve["points"][int(array(solve["values"]).argmin())]
        left.plot(*local, marker="o", markersize=2.5, color=SECOND, linestyle="none")

    if done:
        last = done[-1]
        i, j = last["box"]
        left.add_patch(
            plt.Rectangle(
                (breakpoints[i], breakpoints[j]),
                width,
                width,
                facecolor="none",
                edgecolor=ACCENT,
                linewidth=2.2,
            )
        )
        left.plot(
            last["points"][:, 0],
            last["points"][:, 1],
            marker="o",
            markersize=2.5,
            linewidth=1.0,
            color=ACCENT,
        )
        incumbent = best["points"][int(array(best["values"]).argmin())]
        left.plot(
            *incumbent,
            marker="o",
            markersize=9,
            markerfacecolor="none",
            markeredgecolor=THIRD,
            markeredgewidth=2.0,
            linestyle="none",
        )

    left.plot(
        [0.0], [0.0], marker="*", color="#ffd43b", markersize=11, linestyle="none"
    )
    left.set_xlim(breakpoints[0], breakpoints[-1])
    left.set_ylim(breakpoints[0], breakpoints[-1])
    left.set_aspect("equal")
    left.set_xticks([])
    left.set_yticks([])
    left.set_xlabel("$x_1$")
    left.set_ylabel("$x_2$")
    n_boxes = (len(breakpoints) - 1) ** 2
    left.set_title(
        f"{index} of {n_boxes} boxes solved"
        if index
        else f"Rastrigin cut into {n_boxes} boxes"
    )

    costs = [0] + [solve["cost"] for solve in solves]
    bests = [solves[0]["best"]] + [solve["best"] for solve in solves]
    right.step(costs, bests, where="post", color=foreground, alpha=0.15, linewidth=1.2)
    if index:
        right.step(
            costs[: index + 1],
            bests[: index + 1],
            where="post",
            color=ACCENT,
            linewidth=1.8,
        )
        right.plot(costs[index], bests[index], marker="o", color=ACCENT, markersize=5)

    right.set_yscale("symlog", linthresh=0.1)
    right.set_xlim(0, costs[-1] * 1.03)
    right.set_xlabel("equivalent evaluations")
    right.set_ylabel("best objective so far")
    right.grid(alpha=0.25)
    right.set_title(
        f"{costs[index]} evaluations, best {bests[index]:.3g}"
        if index
        else "the master picks a box, a local solver descends in it"
    )
    return figure


def animate_solve(name: str = "solve") -> None:
    """Animate a run of the method on Rastrigin in two dimensions, per theme.

    Each frame is one more box solved: the box the master has just chosen in
    orange with the path of the local solver inside it, the boxes already
    solved in blue, the incumbent circled in green, and on the right the best
    value against the evaluations spent.

    Args:
        name: The name of the animation, without its extension.
    """
    from io import BytesIO

    from PIL import Image

    solves = _trace_solve()
    x = linspace(-4.1, 5.9, 300)
    grid_x, grid_y = meshgrid(x, x)
    landscape = (grid_x, grid_y, rastrigin(grid_x, grid_y), linspace(-4.1, 5.9, 11))
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    for suffix, foreground in (("", LIGHT), ("-dark", DARK)):
        frames = []
        with plt.rc_context({
            **_style(foreground),
            "savefig.transparent": False,
            "savefig.facecolor": BACKGROUNDS[foreground],
        }):
            for index in range(len(solves) + 1):
                figure = _draw_solve_frame(foreground, solves, index, landscape)
                buffer = BytesIO()
                figure.savefig(buffer, format="png", dpi=100)
                plt.close(figure)
                buffer.seek(0)
                frames.append(Image.open(buffer).convert("RGB"))

        # One palette for every frame, so that the colours do not flicker.
        palette = frames[-1].quantize(colors=128, method=Image.Quantize.MEDIANCUT)
        frames = [
            frame.quantize(palette=palette, dither=Image.Dither.NONE)
            for frame in frames
        ]
        durations = [1500] + [550] * (len(frames) - 2) + [3500]
        frames[0].save(
            DIRECTORY / f"{name}{suffix}.gif",
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=0,
            optimize=True,
        )


FIGURES = {
    "subdivision": (draw_subdivision, "png"),
    "bilevel": (draw_bilevel, "svg"),
    "cuts": (draw_cuts, "svg"),
    "convexification": (draw_convexification, "svg"),
    "trust_region": (draw_trust_region, "svg"),
    "complexity": (draw_complexity, "svg"),
    "hierarchy": (draw_hierarchy, "svg"),
    "multiresolution": (draw_multiresolution, "svg"),
    "partial_refinement": (draw_partial_refinement, "png"),
    "problems": (draw_problems, "png"),
    "landscape_slice": (draw_landscape_slice, "svg"),
    "sampling": (draw_sampling, "png"),
    "results": (draw_results, "svg"),
    "extensions": (draw_extensions, "svg"),
    "density": (draw_density, "svg"),
    "small_budget": (draw_small_budget, "svg"),
    "encodings": (draw_encodings, "svg"),
    "variant_profiles": (draw_variant_profiles, "svg"),
    "data_profiles": (draw_data_profiles, "svg"),
}
"""The figures, by name, with the format each is written in."""

ANIMATIONS = {"solve": animate_solve}
"""The animations, by name, each written as a GIF."""


def main(names: Sequence[str] = ()) -> None:
    """Write the figures and the animations, for both themes.

    Args:
        names: The names of those to write. If empty, write them all.
    """
    for name, (draw, extension) in FIGURES.items():
        if not names or name in names:
            save(name, draw, extension)
            print(f"{name}.{extension}")  # noqa: T201

    for name, animate in ANIMATIONS.items():
        if not names or name in names:
            animate(name)
            print(f"{name}.gif")  # noqa: T201


if __name__ == "__main__":
    main(sys.argv[1:])
