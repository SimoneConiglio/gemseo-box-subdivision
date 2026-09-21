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
"""Tests for what a run says about the guard the convexity margin provides."""

from __future__ import annotations

import logging

import pytest
from gemseo.algos.design_space import DesignSpace
from gemseo.core.discipline import Discipline
from numpy import array
from numpy import cos
from numpy import pi
from numpy import sin
from numpy import zeros

from gemseo_box_subdivision import BoxSubdivisionScenario
from gemseo_box_subdivision import BoxSubdivisionSettings
from gemseo_box_subdivision import MarginReport
from gemseo_box_subdivision import log_margin_report
from gemseo_box_subdivision import read_margin_report


class Landscape(Discipline):
    """f = cos(pi x) - x/10 on [0, 10], with a constraint of a given offset.

    With the default offset, ``g <= 0`` holds near ``x = 1`` and ``x = 9`` only,
    so most boxes of a subdivision hold no feasible point. A negative offset
    makes every box infeasible.
    """

    def __init__(self, offset: float = -0.5) -> None:
        super().__init__()
        self.__offset = offset
        self.io.input_grammar.update_from_data({"x": zeros(1)})
        self.io.output_grammar.update_from_data({"f": zeros(1), "g": zeros(1)})
        self.default_input_data = {"x": array([1.0])}

    def _run(self, input_data):  # noqa: ANN001, ANN202
        x = input_data["x"]
        return {
            "f": cos(pi * x) - x / 10.0,
            "g": (x - 1.0) ** 2 * (x - 9.0) ** 2 + self.__offset,
        }

    def _compute_jacobian(self, input_names=(), output_names=()) -> None:  # noqa: ANN001
        self._init_jacobian(input_names, output_names)
        x = float(self.io.data["x"][0])
        self.jac["f"]["x"] = array([[-pi * sin(pi * x) - 0.1]])
        self.jac["g"]["x"] = array([
            [2.0 * (x - 1.0) * (x - 9.0) ** 2 + 2.0 * (x - 1.0) ** 2 * (x - 9.0)]
        ])


def run(offset: float = -0.5, constrained: bool = True) -> BoxSubdivisionScenario:
    """Return an executed scenario over the landscape."""
    space = DesignSpace()
    space.add_variable("x", lower_bound=0.0, upper_bound=10.0, value=1.0)
    scenario = BoxSubdivisionScenario(
        [Landscape(offset)],
        "f",
        space,
        n_subdivisions=6,
        settings=BoxSubdivisionSettings(
            convexity_margin=1.0,
            trust_region_radius=1,
            max_iter=12,
            sub_problem_max_iter=15,
        ),
    )
    if constrained:
        scenario.formulation.add_constraint(
            "g", constraint_type="ineq", main_level=True
        )

    scenario.execute()
    return scenario


def test_the_report_counts_the_boxes_of_each_kind() -> None:
    """Check the split the master's database carries, on a constrained run."""
    scenario = run()
    report = read_margin_report(scenario.formulation.optimization_problem)
    assert report.n_solved > 0
    assert report.n_solved == report.n_feasible + report.n_infeasible
    assert report.n_infeasible > 0
    assert report.best_feasible is not None


def test_a_run_without_a_main_level_constraint_has_no_feasibility_cut() -> None:
    """Check that every box counts as feasible when the master records no flag.

    Without a main-level constraint the master cuts every box on its objective
    value, which is the case the tuning guidance was measured on.
    """
    scenario = run(constrained=False)
    report = read_margin_report(scenario.formulation.optimization_problem)
    assert report.n_infeasible == 0
    assert report.n_feasible == report.n_solved
    assert report.margin_governs


def test_the_margin_cannot_govern_a_run_with_no_feasible_box() -> None:
    """Check the case the report exists for, every box cut on feasibility.

    The margin relaxes the objective cuts, so a run producing fewer than two of
    them was steered by cuts no margin reaches.
    """
    scenario = run(offset=0.5)
    report = read_margin_report(scenario.formulation.optimization_problem)
    assert report.n_feasible == 0
    assert report.best_feasible is None
    assert not report.margin_governs
    assert "no margin relaxes" in report.describe()


def test_a_run_the_margin_cannot_govern_warns(caplog) -> None:  # noqa: ANN001
    """Check that such a run says so, rather than looking like any other."""
    with caplog.at_level(logging.WARNING, "gemseo_box_subdivision.diagnostics"):
        run(offset=0.5)

    assert any(
        "feasibility cuts" in record.message
        for record in caplog.records
        if record.levelno == logging.WARNING
    )


def test_a_run_the_margin_governs_does_not_warn(caplog) -> None:  # noqa: ANN001
    """Check that the warning is about the case it names, not about every run."""
    with caplog.at_level(logging.WARNING, "gemseo_box_subdivision.diagnostics"):
        run()

    assert not [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING
        and record.name == "gemseo_box_subdivision.diagnostics"
    ]


@pytest.mark.parametrize(
    ("n_feasible", "governs"),
    [(0, False), (1, False), (2, True)],
)
def test_two_feasible_boxes_are_what_the_margin_acts_on(n_feasible, governs) -> None:  # noqa: ANN001
    """Check the rule: a margin relaxes one objective cut against another."""
    report = MarginReport(
        n_solved=5, n_feasible=n_feasible, best_feasible=0.0, spread=1.0
    )
    assert report.margin_governs is governs
    assert report.n_infeasible == 5 - n_feasible


def test_the_spread_is_the_scale_the_margin_is_calibrated_in() -> None:
    """Check that the report names the scale, which is what transfers badly."""
    report = MarginReport(n_solved=4, n_feasible=3, best_feasible=-1.9, spread=0.801)
    assert "0.801" in report.describe()


def test_an_empty_run_reports_nothing() -> None:
    """Check that a master that solved no box is not described."""
    scenario = run(constrained=False)
    problem = scenario.formulation.optimization_problem
    problem.database.clear()
    report = log_margin_report(problem)
    assert report.n_solved == 0
