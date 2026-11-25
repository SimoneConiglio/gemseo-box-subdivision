"""Draw the data profiles of the best variant and of the baselines (Figure 5).

Reads ``docs/_static/data_profiles.json``, written by
``python -m benchmarks.data_profiles``, and writes ``data_profiles.pdf`` next to
this script. Run from the root of the repository.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

DATA = Path("docs/_static/data_profiles.json")
OUTPUT = Path(__file__).with_name("data_profiles.pdf")

BEST = {"2": "probes_16", "5": "density_10"}
"""The best variant of each dimension, as in Table 8."""

SERIES = (
    ("best", "#2b74d6", "-", 2.6),
    ("multistart", "#e8603c", "-", 1.6),
    ("cmaes", "#1fa774", "-", 1.6),
    ("direct", "#e8a202", "-", 1.6),
    ("egobox", "#e377c2", "-", 1.6),
    ("tunneling", "#6b4fbb", "--", 1.6),
)
"""Key, colour, line style and width of each series, in a fixed order."""

LABELS = {
    "multistart": "multistart",
    "cmaes": "CMA-ES",
    "direct": "DIRECT",
    "egobox": "EGO",
    "tunneling": "tunneling",
}

EGO_BUDGET = 500


def steps(points: list[list[float]], end: int) -> tuple[list[float], list[float]]:
    """Return the staircase of a profile given by its change points.

    Args:
        points: The evaluations at which the fraction changes, and the fraction.
        end: The last evaluation to draw.

    Returns:
        The abscissae and the ordinates of the staircase.
    """
    xs, ys = [0.0], [0.0]
    for x, y in points:
        if x > end:
            break
        xs += [x, x]
        ys += [ys[-1], y]
    xs.append(end)
    ys.append(ys[-1])
    return xs, ys


def main() -> None:
    """Draw the figure."""
    data = json.loads(DATA.read_text(encoding="utf-8"))
    labels = data["labels"]
    plt.rcParams.update({
        "font.size": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
    })
    figure, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
    for axis, dimension in zip(axes, ("2", "5"), strict=True):
        entry = data["dimensions"][dimension]
        budget = entry["budget"]
        for key, colour, style, width in SERIES:
            name = BEST[dimension] if key == "best" else key
            label = f"box subdivision: {labels[name]}" if key == "best" else LABELS[key]
            end = min(budget, EGO_BUDGET) if key == "egobox" else budget
            xs, ys = steps(entry["profiles"][name], end)
            axis.plot(
                xs,
                ys,
                style,
                color=colour,
                lw=width,
                label=label,
                zorder=3 if key == "best" else 2,
            )
            if key == "egobox":
                axis.plot([end], [ys[-1]], "o", color=colour, ms=5, zorder=3)
        optimal = len(entry["best_target_is_the_optimum"])
        total = len(data["problems"])
        axis.set_title(
            f"{dimension} variables: best target the optimum on {optimal} of {total}"
        )
        axis.set_xlim(0, budget)
        axis.set_ylim(0, 1.02)
        axis.set_xlabel("equivalent evaluations")
        axis.grid(color="#e6e6e6", lw=0.6)
        axis.yaxis.set_major_formatter(mpl.ticker.PercentFormatter(1.0))
        axis.legend(loc="lower right", frameon=False, fontsize=8)
    axes[0].set_ylabel("targets reached")
    figure.tight_layout()
    figure.savefig(OUTPUT)


if __name__ == "__main__":
    main()
