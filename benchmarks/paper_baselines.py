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
"""Write the tables of the comparison with the baselines for the manuscript.

The tables are written from ``docs/_static/statistics.json``,
``docs/_static/small_budget.json`` and ``docs/_static/data_profiles.json``, so
that they follow the runs, to ``paper/tables``:

- ``baselines.tex``: median distance, median cost and successes;
- ``tests.tex``: the paired tests of the success, after Holm correction;
- ``profiles.tex``: the areas, the fractions of the targets reached and the
  differences of area with their bootstrap intervals;
- ``small.tex``: the comparison with a budget of $500$ evaluations.

```shell
python -m benchmarks.paper_baselines
```
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
STATIC = ROOT / "docs" / "_static"
TABLES = ROOT / "paper" / "tables"

PROBLEMS = ("rastrigin", "ackley", "styblinski_tang", "griewank")
HEADERS = ("Rastrigin", "Ackley", "Styblinski--Tang", "Griewank")

METHODS = {
    "swept": "box subdivision",
    "density_10": "box subdivision",
    "multistart": "multistart, 50 starts",
    "multistart_10": "multistart, 10 starts",
    "cmaes": "CMA-ES",
    "ipop_cmaes": "IPOP-CMA-ES",
    "direct": "DIRECT",
    "direct_global": "DIRECT, not locally biased",
    "mlsl": "MLSL",
    "tunneling": "tunneling",
    "egobox": "EGO$\\ddagger$",
}
"""The label of each method, in the order of the tables."""

DETERMINISTIC = ("direct", "direct_global")
"""The methods giving the same run from every starting point."""

SIGNIFICANCE = 0.05


def _gap(value: float) -> str:
    """Format a distance to the optimum."""
    if abs(value) < 5e-3:  # noqa: PLR2004
        return "0.00"
    if abs(value) < 0.1:  # noqa: PLR2004
        return f"{value:.3f}"
    return f"{value:.2f}"


def _medians(runs: list[dict], method: str, problem: str) -> tuple[float, int, int]:
    """Return the median distance, the median cost and the successes."""
    from statistics import median  # noqa: PLC0415

    own = [r for r in runs if r["method"] == method and r["problem"] == problem]
    return (
        median(r["gap"] for r in own),
        round(median(r["cost"] for r in own)),
        sum(r["reached"] for r in own),
    )


def _methods(entry: dict) -> list[str]:
    """Return the methods of a dimension, the method first."""
    present = {r["method"] for r in entry["runs"]}
    return [entry["method"]] + [
        m for m in METHODS if m in present and m not in {"swept", "density_10"}
    ]


def baselines(statistics: dict) -> str:
    """Return the table of the median distances, costs and successes."""
    lines = [
        "\\begin{table}[t]",
        "  \\centering",
        "  \\caption{Comparison of the method, swept with ten subdivisions per",
        "    variable, with the baselines, $500n$ equivalent evaluations, twenty",
        "    starting points: median distance $\\cdot$ median cost $\\cdot$ number of",
        "    starting points from which the optimum is reached. $\\ddagger$ EGO is",
        "    run with $500$ evaluations.}",
        "  \\label{tab:baselines}",
        "  \\scriptsize",
        "  \\setlength{\\tabcolsep}{2.5pt}",
        "  \\begin{tabular}{l" + "l" * len(PROBLEMS) + "}",
        "    \\toprule",
        "    method & " + " & ".join(HEADERS) + " \\\\",
    ]
    for dimension, entry in statistics.items():
        lines += [
            "    \\midrule",
            f"    \\multicolumn{{5}}{{l}}{{$n = {dimension}$}} \\\\",
        ]
        for method in _methods(entry):
            cells = []
            for problem in PROBLEMS:
                gap, cost, reached = _medians(entry["runs"], method, problem)
                cells.append(f"{_gap(gap)} $\\cdot$ {cost} $\\cdot$ {reached}")
            lines.append(f"    {METHODS[method]} & " + " & ".join(cells) + " \\\\")
    lines += ["    \\bottomrule", "  \\end{tabular}", "\\end{table}"]
    return "\n".join(lines) + "\n"


def tests(statistics: dict) -> str:
    """Return the table of the paired tests of the success."""
    lines = [
        "\\begin{table}[t]",
        "  \\centering",
        "  \\caption{Paired comparison of the success, twenty starting points:",
        "    number of starting points from which only the method reaches the",
        "    optimum $-$ number from which only the baseline does, with the",
        "    $p$-value of the exact McNemar test after Holm correction over the",
        "    four problems and the baselines of each dimension. Bold: significant",
        "    at $0.05$. ---: no discordant starting point. $^\\ast$ The same run",
        "    from every starting point, so that the test compares the runs of the",
        "    method with a single result; it is given for information and not",
        "    marked as significant.}",
        "  \\label{tab:tests}",
        "  \\scriptsize",
        "  \\setlength{\\tabcolsep}{3pt}",
        "  \\begin{tabular}{l" + "l" * len(PROBLEMS) + "}",
        "    \\toprule",
        "    baseline & " + " & ".join(HEADERS) + " \\\\",
    ]
    for dimension, entry in statistics.items():
        lines += [
            "    \\midrule",
            f"    \\multicolumn{{5}}{{l}}{{$n = {dimension}$}} \\\\",
        ]
        by_key = {(t["baseline"], t["problem"]): t for t in entry["tests"]}
        for method in _methods(entry)[1:]:
            cells = []
            for problem in PROBLEMS:
                test = by_key[method, problem]
                a, b = test["only_method"], test["only_baseline"]
                if a == b == 0:
                    cells.append("---")
                    continue
                p = test["p_success_holm"]
                value = "$<$0.001" if p < 1e-3 else f"{p:.3f}"  # noqa: PLR2004
                cell = f"{a}$-${b}, {value}"
                if method in DETERMINISTIC:
                    cell += "$^\\ast$"
                elif p < SIGNIFICANCE:
                    cell = f"\\textbf{{{a}$-${b}}}, {value}"
                cells.append(cell)
            label = METHODS[method].replace("$\\ddagger$", "")
            lines.append(f"    {label} & " + " & ".join(cells) + " \\\\")
    lines += ["    \\bottomrule", "  \\end{tabular}", "\\end{table}"]
    return "\n".join(lines) + "\n"


def _at(points: list[list[float]], evaluation: float) -> float | None:
    """Return the value of a profile at a number of evaluations."""
    if evaluation > points[-1][0] + 1e-9:
        return None
    value = 0.0
    for x, y in points:
        if x <= evaluation:
            value = y
    return value


def profiles(statistics: dict, published: dict) -> str:
    """Return the table of the areas and of the fractions of targets reached."""
    sys.path.insert(0, str(ROOT / "docs"))
    from figures import _profiles_of_the_runs  # noqa: PLC0415

    lines = [
        "\\begin{table}[t]",
        "  \\centering",
        "  \\caption{Area under the data profile and fraction of the targets",
        "    reached at a tenth, a quarter and a half of the budget and at the end",
        "    of the budget, twenty starting points, and difference of the area of",
        "    the method with that of each baseline, with its $95\\%$ bootstrap",
        "    confidence interval. $\\ddagger$ Value at the end of the budget of EGO,",
        "    i.e. $500$ evaluations, which in five dimensions is less than a",
        "    quarter of the budget of the other methods; no area is given for",
        "    EGO.}",
        "  \\label{tab:profiles}",
        "  \\scriptsize",
        "  \\setlength{\\tabcolsep}{3pt}",
        "  \\begin{tabular}{rlrrrrrl}",
        "    \\toprule",
        ("    $n$ & method & area & $\\tfrac1{10}$ & $\\tfrac14$ & $\\tfrac12$ & end"
        " & difference \\\\"),
    ]
    for dimension, entry in statistics.items():
        data = published["dimensions"][dimension]
        budget = data["budget"]
        curves = _profiles_of_the_runs(entry["runs"], data["targets"], budget)
        areas = {a["baseline"]: a for a in entry["areas"]}
        method = entry["method"]
        lines.append("    \\midrule")
        for name in _methods(entry):
            points = curves[name]
            fractions = []
            for share in (0.1, 0.25, 0.5):
                value = _at(points, share * budget)
                fractions.append("---" if value is None else f"{100 * value:.0f}\\%")
            end = f"{100 * points[-1][1]:.0f}\\%"
            if name == "egobox":
                end += "$\\ddagger$"
            if name == method:
                area = f"{next(iter(areas.values()))['area_method']:.2f}"
                difference = ""
            elif name in areas:
                test = areas[name]
                area = f"{test['area_baseline']:.2f}"
                low, high = test["ci95"]
                difference = (
                    f"${test['difference']:+.2f}$ [${low:+.2f}$, ${high:+.2f}$]"
                )
            else:
                area, difference = "---", ""
            label = METHODS[name].replace("$\\ddagger$", "")
            if name == "egobox":
                label = "EGO, 500 evaluations"
            lines.append(
                f"    {dimension} & {label} & {area} & "
                + " & ".join(fractions)
                + f" & {end} & {difference} \\\\"
            )
    lines += ["    \\bottomrule", "  \\end{tabular}", "\\end{table}"]
    return "\n".join(lines) + "\n"


def small(small_budget: dict) -> str:
    """Return the table of the comparison with a budget of 500 evaluations."""
    budget = small_budget["budget"]
    lines = [
        "\\begin{table}[t]",
        "  \\centering",
        "  \\caption{Budget of $500$ evaluations, twenty starting points: median",
        "    distance to the optimum $\\cdot$ number of starting points from which",
        "    the optimum is reached, and median cost when it is smaller than the",
        "    budget.}",
        "  \\label{tab:small}",
        "  \\scriptsize",
        "  \\setlength{\\tabcolsep}{3pt}",
        "  \\begin{tabular}{l" + "l" * len(PROBLEMS) + "}",
        "    \\toprule",
        "    method & " + " & ".join(HEADERS) + " \\\\",
    ]
    for dimension, entry in small_budget["dimensions"].items():
        lines += [
            "    \\midrule",
            f"    \\multicolumn{{5}}{{l}}{{$n = {dimension}$}} \\\\",
        ]
        summary = entry["summary"]
        names = [entry["method"]] + [
            m for m in METHODS if m in summary and m not in {"swept", "density_10"}
        ]
        for name in names:
            cells = []
            for problem in PROBLEMS:
                cell = summary[name][problem]
                text = f"{_gap(cell['median_gap'])} $\\cdot$ {cell['reached']}"
                if cell["median_cost"] < 0.95 * budget:
                    text += f" $\\cdot$ {round(cell['median_cost'])}"
                cells.append(text)
            label = METHODS[name].replace("$\\ddagger$", "")
            lines.append(f"    {label} & " + " & ".join(cells) + " \\\\")
    lines += ["    \\bottomrule", "  \\end{tabular}", "\\end{table}"]
    return "\n".join(lines) + "\n"


def main() -> None:
    """Write the four tables."""
    statistics = json.loads((STATIC / "statistics.json").read_text())["dimensions"]
    published = json.loads((STATIC / "data_profiles.json").read_text())
    small_budget = json.loads((STATIC / "small_budget.json").read_text())
    TABLES.mkdir(exist_ok=True)
    (TABLES / "baselines.tex").write_text(baselines(statistics))
    (TABLES / "tests.tex").write_text(tests(statistics))
    (TABLES / "profiles.tex").write_text(profiles(statistics, published))
    (TABLES / "small.tex").write_text(small(small_budget))
    print("paper/tables/{baselines,tests,profiles,small}.tex")  # noqa: T201


if __name__ == "__main__":
    main()
