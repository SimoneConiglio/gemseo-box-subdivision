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
"""Tests for what a run says about the guard the convexity margin provides.

The reader is exercised against master databases built here, which is what it
reads and costs no run. One scenario is executed, to pin that a real master
records what the reader looks for and that a run reports on itself.
"""

from __future__ import annotations

import logging

import pytest
from gemseo.algos.design_space import DesignSpace
from gemseo.algos.optimization_problem import OptimizationProblem
from gemseo.core.discipline import Discipline
from gemseo.core.mdo_functions.mdo_function import MDOFunction
from numpy import array
from numpy import cos
from numpy import pi
from numpy import sin
from numpy import zeros

from gemseo_box_subdivision import BoxSubdivisionScenario
from gemseo_box_subdivision import BoxSubdivisionSettings
from gemseo_box_subdivision import MarginReport
from gemseo_box_subdivision import log_margin_report
from gemseo_box_subdivision import objective_scale
from gemseo_box_subdivision import read_margin_report

LOGGER_NAME = "gemseo_box_subdivision.diagnostics"


def master_problem(*boxes: tuple[float, float | None]) -> OptimizationProblem:
    """Return a master problem whose database holds the given solved boxes.

    This is what the reader reads: one entry per box, carrying the value of the
    box and, when a main-level constraint was declared, whether the box held a
    feasible point.

    Args:
        *boxes: The value of each box, with its feasibility flag or ``None``
            when the master recorded none.

    Returns:
        The problem.
    """
    space = DesignSpace()
    space.add_variable("alpha", lower_bound=0.0, upper_bound=1.0, value=0.0)
    problem = OptimizationProblem(space)
    problem.objective = MDOFunction(lambda x: x, "f")
    for index, (value, flag) in enumerate(boxes):
        entry = {"f": array([value])}
        if flag is not None:
            entry["is_feasible"] = flag

        # One key per box, as a master has one entry per box it solved.
        problem.database.store(array([float(index)]), entry)

    return problem


def test_the_report_counts_the_boxes_of_each_kind() -> None:
    """Check the split between boxes cut on value and boxes cut on feasibility."""
    report = read_margin_report(
        master_problem((-1.9, 1), (0.4, 0), (-1.1, 1), (0.8, 0))
    )
    assert report.n_solved == 4
    assert report.n_feasible == 2
    assert report.n_infeasible == 2
    assert report.best_feasible == pytest.approx(-1.9)
    # Over every box solved: an infeasible box produces an objective cut like
    # any other, and the repair is given both histories together.
    assert report.spread == pytest.approx(0.8 - -1.9)
    assert report.margin_governs


def test_a_run_without_a_main_level_constraint_has_no_feasibility_cut() -> None:
    """Check that every box counts as feasible when the master records no flag.

    Without a main-level constraint the master cuts every box on its objective
    value, which is the case the tuning guidance was measured on.
    """
    report = read_margin_report(master_problem((-1.9, None), (0.4, None)))
    assert report.n_infeasible == 0
    assert report.n_feasible == report.n_solved == 2
    assert report.margin_governs


def test_a_run_that_admitted_no_box_says_the_margin_is_not_the_knob() -> None:
    """Check the case the report exists for, every box cut on feasibility.

    The margin still guarded the objective cuts those boxes produced; what
    rejected every one of them is the ``is_feasible`` gate, which the master
    repairs with a margin of zero whatever the convexity margin says.
    """
    report = read_margin_report(master_problem((0.4, 0), (0.8, 0), (1.2, 0)))
    assert report.n_feasible == 0
    assert report.best_feasible is None
    assert report.found_nothing_feasible
    # The margin did enter the master: three boxes, hence objective cuts.
    assert report.margin_governs
    assert report.spread == pytest.approx(0.8)
    assert "is_feasible gate" in report.describe()


def test_the_margin_enters_the_master_from_two_boxes_of_either_kind() -> None:
    """Check that an infeasible box counts towards the margin having an effect.

    The repair subtracts the margin from differences of objective value over
    the whole history it is given, which is both kinds of box together.
    """
    report = read_margin_report(master_problem((-1.9, 1), (0.4, 0)))
    assert report.n_feasible == 1
    assert report.best_feasible == pytest.approx(-1.9)
    assert report.margin_governs
    assert report.spread == pytest.approx(2.3)


def test_one_box_leaves_the_margin_nothing_to_subtract_from() -> None:
    """Check the boundary: one cut has no other to be compared against."""
    report = read_margin_report(master_problem((-1.9, 1)))
    assert report.n_solved == 1
    assert not report.margin_governs
    assert report.spread == pytest.approx(0.0)
    assert "never entered the master" in report.describe()


def test_the_spread_is_the_scale_the_sweep_reads() -> None:
    """Check the report against the sweep, which must read the same scale.

    `objective_scale` is what the swept entry point computes its ladder from,
    over every box solved; a report disagreeing with it would send a caller
    calibrating by hand to a different number than the sweep uses.
    """
    values = (-1.9, 0.4, -1.1, 0.8)
    report = read_margin_report(
        master_problem(*((value, index % 2) for index, value in enumerate(values)))
    )
    assert report.spread == pytest.approx(objective_scale(values))


def test_an_entry_carrying_no_value_is_not_a_solved_box() -> None:
    """Check that the reader counts boxes, not database entries.

    A master's database also holds entries a box never produced, such as the
    bounds it records as it goes; they carry no objective value.
    """
    problem = master_problem((-1.9, 1), (0.4, 0))
    problem.database.store(array([7.0]), {"lower bound": array([-2.0])})
    report = read_margin_report(problem)
    assert report.n_solved == 2
    assert report.n_feasible == 1


def test_a_run_that_admitted_no_box_warns(caplog) -> None:  # noqa: ANN001
    """Check that such a run says so, rather than looking like any other."""
    with caplog.at_level(logging.WARNING, LOGGER_NAME):
        log_margin_report(master_problem((0.4, 0), (0.8, 0)))

    assert [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING and "is_feasible gate" in record.message
    ]


def test_a_run_the_margin_governs_does_not_warn(caplog) -> None:  # noqa: ANN001
    """Check that the warning is about the case it names, not about every run."""
    with caplog.at_level(logging.WARNING, LOGGER_NAME):
        log_margin_report(master_problem((-1.9, 1), (-1.1, 1), (0.4, 0)))

    assert not [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING and record.name == LOGGER_NAME
    ]


def test_an_empty_run_reports_nothing() -> None:
    """Check that a master that solved no box is not described."""
    report = log_margin_report(master_problem())
    assert report.n_solved == 0


@pytest.mark.parametrize(
    ("n_solved", "governs"),
    [(0, False), (1, False), (2, True)],
)
def test_two_solved_boxes_are_what_the_margin_acts_on(n_solved, governs) -> None:  # noqa: ANN001
    """Check the rule: the margin is subtracted from a difference of values."""
    report = MarginReport(
        n_solved=n_solved, n_feasible=0, best_feasible=None, spread=1.0
    )
    assert report.margin_governs is governs


def test_the_report_names_the_scale() -> None:
    """Check that the report names the scale, which is what transfers badly."""
    report = MarginReport(n_solved=4, n_feasible=3, best_feasible=-1.9, spread=0.801)
    assert "0.801" in report.describe()


class Landscape(Discipline):
    """f = cos(pi x) - x/10 on [0, 10]; g <= 0 near x = 1 and x = 9 only.

    Most boxes of a subdivision therefore hold no feasible point, which is the
    shape of problem the report is about.
    """

    def __init__(self) -> None:
        super().__init__()
        self.io.input_grammar.update_from_data({"x": zeros(1)})
        self.io.output_grammar.update_from_data({"f": zeros(1), "g": zeros(1)})
        self.default_input_data = {"x": array([1.0])}

    def _run(self, input_data):  # noqa: ANN001, ANN202
        x = input_data["x"]
        return {
            "f": cos(pi * x) - x / 10.0,
            "g": (x - 1.0) ** 2 * (x - 9.0) ** 2 - 0.5,
        }

    def _compute_jacobian(self, input_names=(), output_names=()) -> None:  # noqa: ANN001
        self._init_jacobian(input_names, output_names)
        x = float(self.io.data["x"][0])
        self.jac["f"]["x"] = array([[-pi * sin(pi * x) - 0.1]])
        self.jac["g"]["x"] = array([
            [2.0 * (x - 1.0) * (x - 9.0) ** 2 + 2.0 * (x - 1.0) ** 2 * (x - 9.0)]
        ])


def test_a_real_run_reports_on_itself(caplog) -> None:  # noqa: ANN001
    """Check the reader against a master database, and the run reporting on it.

    The one executed scenario here: it pins that a real master records the
    objective and the feasibility flag under the names the reader looks for,
    and that `execute` reports once the run is over.
    """
    space = DesignSpace()
    space.add_variable("x", lower_bound=0.0, upper_bound=10.0, value=1.0)
    scenario = BoxSubdivisionScenario(
        [Landscape()],
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
    scenario.formulation.add_constraint("g", constraint_type="ineq", main_level=True)
    with caplog.at_level(logging.INFO, LOGGER_NAME):
        scenario.execute()

    report = read_margin_report(scenario.formulation.optimization_problem)
    assert report.n_solved > 0
    assert report.n_solved == report.n_feasible + report.n_infeasible
    # The landscape is feasible near two points only, so a subdivision of six
    # holds boxes of both kinds.
    assert report.n_feasible > 0
    assert report.n_infeasible > 0
    assert report.best_feasible is not None
    # The run described itself without being asked.
    assert [record for record in caplog.records if record.name == LOGGER_NAME]
