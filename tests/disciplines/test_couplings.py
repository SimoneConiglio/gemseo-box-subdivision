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
"""Tests for the couplings of an MDA handed to a box-subdivision scenario."""

from __future__ import annotations

from gemseo import create_mda
from gemseo.algos.design_space import DesignSpace
from gemseo.core.chains.chain import MDOChain
from gemseo.core.discipline import Discipline
from gemseo.mda.base_mda import BaseMDA
from numpy import array
from numpy import zeros
from numpy.testing import assert_allclose

from gemseo_box_subdivision import BoxSubdivisionScenario
from gemseo_box_subdivision import BoxSubdivisionSettings
from gemseo_box_subdivision import keep_couplings_internal
from gemseo_box_subdivision import keep_every_mda_couplings_internal


class First(Discipline):
    """y1 = x + 0.2 y2."""

    def __init__(self) -> None:
        super().__init__()
        self.io.input_grammar.update_from_data({"x": zeros(1), "y2": zeros(1)})
        self.io.output_grammar.update_from_data({"y1": zeros(1)})
        self.default_input_data = {"x": zeros(1), "y2": zeros(1)}

    def _run(self, input_data):  # noqa: ANN001, ANN202
        return {"y1": input_data["x"] + 0.2 * input_data["y2"]}

    def _compute_jacobian(self, input_names=(), output_names=()) -> None:  # noqa: ANN001
        self._init_jacobian(input_names, output_names)
        self.jac["y1"]["x"] = array([[1.0]])
        self.jac["y1"]["y2"] = array([[0.2]])


class Second(Discipline):
    """y2 = 0.5 y1 + 1."""

    def __init__(self) -> None:
        super().__init__()
        self.io.input_grammar.update_from_data({"y1": zeros(1)})
        self.io.output_grammar.update_from_data({"y2": zeros(1)})
        self.default_input_data = {"y1": zeros(1)}

    def _run(self, input_data):  # noqa: ANN001, ANN202
        return {"y2": 0.5 * input_data["y1"] + 1.0}

    def _compute_jacobian(self, input_names=(), output_names=()) -> None:  # noqa: ANN001
        self._init_jacobian(input_names, output_names)
        self.jac["y2"]["y1"] = array([[0.5]])


class Objective(Discipline):
    """f = (y1 - 3)^2 + 0.1 x, and a constraint on the coupling."""

    def __init__(self) -> None:
        super().__init__()
        self.io.input_grammar.update_from_data({"y1": zeros(1), "x": zeros(1)})
        self.io.output_grammar.update_from_data({"f": zeros(1), "g": zeros(1)})
        self.default_input_data = {"y1": zeros(1), "x": zeros(1)}

    def _run(self, input_data):  # noqa: ANN001, ANN202
        y1, x = input_data["y1"], input_data["x"]
        return {"f": (y1 - 3.0) ** 2 + 0.1 * x, "g": y1 - 4.0}

    def _compute_jacobian(self, input_names=(), output_names=()) -> None:  # noqa: ANN001
        self._init_jacobian(input_names, output_names)
        self.jac["f"]["y1"] = array([[2.0 * (self.io.data["y1"][0] - 3.0)]])
        self.jac["f"]["x"] = array([[0.1]])
        self.jac["g"]["y1"] = array([[1.0]])
        self.jac["g"]["x"] = array([[0.0]])


def mda() -> BaseMDA:
    """Return the fixed point of the two coupled disciplines."""
    return create_mda("MDAGaussSeidel", [First(), Second()], tolerance=1e-12)


def design_space() -> DesignSpace:
    """Return the design space of the coupled problem."""
    space = DesignSpace()
    space.add_variable("x", lower_bound=0.0, upper_bound=6.0, value=1.0)
    return space


def test_the_couplings_are_dropped_from_the_differentiated_inputs() -> None:
    """Check that an MDA is no longer differentiated w.r.t. its own couplings."""
    block = keep_couplings_internal(mda())
    block.add_differentiated_inputs(["x", "y2"])
    assert set(block._differentiated_input_names) == {"x"}


def test_an_empty_argument_still_means_every_input() -> None:
    """Check the GEMSEO convention, an empty argument naming all the inputs."""
    block = keep_couplings_internal(mda())
    block.add_differentiated_inputs()
    assert set(block._differentiated_input_names) == {"x"}


def test_making_the_couplings_internal_twice_does_nothing() -> None:
    """Check that the transformation is idempotent, class and all."""
    block = keep_couplings_internal(mda())
    first_class = type(block)
    assert keep_couplings_internal(block) is block
    assert type(block) is first_class


def test_the_disciplines_that_are_not_mdas_are_untouched() -> None:
    """Check that only the MDAs of a discipline list are transformed."""
    objective = Objective()
    a_mda = mda()
    disciplines = keep_every_mda_couplings_internal([a_mda, objective])
    assert disciplines == (a_mda, objective)
    assert type(objective) is Objective
    assert isinstance(a_mda, BaseMDA)


def test_the_mda_still_converges_and_differentiates_correctly() -> None:
    r"""Check the value and the derivative of the chain the scenario builds.

    The fixed point of ``y1 = x + 0.2 y2`` and ``y2 = 0.5 y1 + 1`` is
    ``y1 = (x + 0.2) / 0.9``, so ``df/dx = 2 (y1 - 3) / 0.9 + 0.1``. Dropping the
    couplings from the differentiated inputs has to leave that unchanged: what
    it drops is the derivative of a converged fixed point with respect to the
    guess it started from, which is zero.
    """
    disciplines = keep_every_mda_couplings_internal([mda(), Objective()])
    chain = MDOChain(list(disciplines))
    x = 1.0
    chain.execute({"x": array([x])})
    y1 = (x + 0.2) / 0.9
    assert_allclose(chain.io.data["y1"], y1, rtol=1e-9)

    jacobian = chain.linearize({"x": array([x])}, compute_all_jacobians=True)
    assert_allclose(jacobian["f"]["x"], [[2.0 * (y1 - 3.0) / 0.9 + 0.1]], rtol=1e-6)
    assert_allclose(jacobian["g"]["x"], [[1.0 / 0.9]], rtol=1e-6)


def test_a_constrained_coupled_scenario_runs() -> None:
    """Check the case of the report, an MDA with a constraint attached.

    Without the transformation the auxiliary Jacobians of the adapter raise
    ``ValueError: Variable y2 is both a coupling and a design variable``, and
    the same scenario without the constraint runs, which is what made it
    awkward to find.
    """
    scenario = BoxSubdivisionScenario(
        [mda(), Objective()],
        "f",
        design_space(),
        n_subdivisions=3,
        settings=BoxSubdivisionSettings(
            convexity_margin=10.0, max_iter=12, sub_problem_max_iter=8
        ),
    )
    scenario.formulation.add_constraint("g", constraint_type="ineq", main_level=True)
    scenario.execute()
    database = scenario.formulation.optimization_problem.database
    assert len(database) > 1
