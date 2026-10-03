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
"""Tests for the entry point building a box-subdivision scenario."""

from __future__ import annotations

from typing import ClassVar

import pytest
from gemseo.algos.design_space import DesignSpace
from gemseo.core.discipline import Discipline
from gemseo.settings.opt import NLOPT_COBYLA_Settings
from gemseo.settings.opt import SLSQP_Settings
from gemseo_bilevel_outer_approximation.algos.opt.bilevel_master_outer_approximation.bilevel_master_outer_approximation_settings import (  # noqa: E501
    BiLevelMasterOuterApproximation_Settings,
)
from gemseo_bilevel_outer_approximation.disciplines.scenario_adapters.mdo_scenario_adapter_benders import (  # noqa: E501
    MDOScenarioAdapterBenders,
)
from numpy import array
from numpy import cos
from numpy import ndarray
from numpy import pi
from numpy import sin
from numpy import zeros
from numpy.testing import assert_allclose

from gemseo_box_subdivision import BoxSubdivisionScenario
from gemseo_box_subdivision import BoxSubdivisionSettings
from gemseo_box_subdivision import MultiResolution
from gemseo_box_subdivision import create_box_subdivision_scenario


class Rastrigin(Discipline):
    """Rastrigin over a design variable of any name."""

    def __init__(self, name: str = "x", size: int = 2) -> None:
        super().__init__()
        self.__name = name
        self.__size = size
        self.io.input_grammar.update_from_data({name: zeros(size)})
        self.io.output_grammar.update_from_data({"f": zeros(1)})
        self.default_input_data = {name: zeros(size)}

    def _run(self, input_data):  # noqa: ANN001, ANN202
        x = input_data[self.__name]
        return {
            "f": array([10.0 * self.__size + (x**2 - 10.0 * cos(2 * pi * x)).sum()])
        }

    def _compute_jacobian(self, input_names=(), output_names=()) -> None:  # noqa: ANN001
        self._init_jacobian(input_names, output_names)
        x = self.io.data[self.__name]
        self.jac["f"][self.__name] = (2 * x + 20 * pi * sin(2 * pi * x)).reshape(1, -1)


def design_space(name: str = "x", size: int = 2) -> DesignSpace:
    """Return a design space holding one variable."""
    space = DesignSpace()
    space.add_variable(
        name, lower_bound=-4.1, upper_bound=5.9, size=size, value=zeros(size)
    )
    return space


def best(scenario) -> float:  # noqa: ANN001
    """Return the best objective value in the database of a scenario."""
    database = scenario.formulation.optimization_problem.database
    return min(float(v["f"]) for v in database.values() if "f" in v)


@pytest.mark.parametrize("name", ["x", "thickness"])
def test_the_master_variables_follow_the_design_space(name) -> None:
    """The one-hot names must be derived, never assumed to be ``x_box``."""
    scenario = create_box_subdivision_scenario(
        [Rastrigin(name)], "f", design_space(name), n_subdivisions=4
    )
    assert f"{name}_box" in scenario.formulation.design_space


def test_subdividing_some_variables_only() -> None:
    """A variable left out must stay an ordinary variable of the sub-problem."""
    space = design_space("a")
    space.add_variable("b", lower_bound=0.0, upper_bound=1.0, size=1, value=0.5)
    scenario = create_box_subdivision_scenario(
        [Rastrigin("a")], "f", space, n_subdivisions=4, variable_names=["a"]
    )
    assert scenario.subdivision.variable_names == ("a",)
    assert "b_box" not in scenario.formulation.design_space


def test_the_defaults_solve_rastrigin() -> None:
    """The entry point must solve the benchmark problem out of the box."""
    scenario = BoxSubdivisionScenario(
        [Rastrigin()], "f", design_space(), n_subdivisions=10
    )
    scenario.execute()
    assert best(scenario) == pytest.approx(0.0, abs=1e-4)


def test_the_constraint_formulation_declares_its_constraint() -> None:
    """The constraint formulation must wire its adapter and its constraint.

    Both live on the sub-problem: the box is enforced there, and the adapter is
    what places its starting point inside the box.
    """
    scenario = create_box_subdivision_scenario(
        [Rastrigin()], "f", design_space(), n_subdivisions=4, formulation="constraint"
    )
    adapter = scenario.formulation.sub_problem_scenario_adapter
    assert type(adapter).__name__ == "BoxStartScenarioAdapter"
    problem = adapter.scenario.formulation.optimization_problem
    assert problem.constraints.get_names() == ["g_box"]


def test_the_normalized_formulation_needs_neither() -> None:
    """The normalized formulation must need no adapter and no box constraint."""
    scenario = create_box_subdivision_scenario(
        [Rastrigin()], "f", design_space(), n_subdivisions=4
    )
    adapter = scenario.formulation.sub_problem_scenario_adapter
    assert type(adapter).__name__ == "MDOScenarioAdapterBenders"
    problem = adapter.scenario.formulation.optimization_problem
    assert problem.constraints.get_names() == []


def test_levels_build_a_multi_resolution_subdivision() -> None:
    """Above one level the encoding must be the multi-resolution one."""
    scenario = create_box_subdivision_scenario(
        [Rastrigin()], "f", design_space(), n_subdivisions=4, levels=2
    )
    assert isinstance(scenario.subdivision, MultiResolution)
    assert scenario.subdivision.resolution == 16
    # One categorical variable per level per subdivided variable.
    assert "x_level_1_box" in scenario.formulation.design_space
    assert "x_level_2_box" in scenario.formulation.design_space


def test_an_unknown_formulation_is_refused() -> None:
    """Check the error raised for an unknown formulation."""
    with pytest.raises(ValueError, match="normalized"):
        create_box_subdivision_scenario(
            [Rastrigin()], "f", design_space(), formulation="other"
        )


def test_the_levels_refuse_the_constraint_formulation() -> None:
    """Check the error raised for a combination that is not supported."""
    with pytest.raises(ValueError, match="normalized formulation only"):
        create_box_subdivision_scenario(
            [Rastrigin()], "f", design_space(), levels=2, formulation="constraint"
        )


def test_the_mechanisms_cannot_be_combined() -> None:
    """Whichever mechanism is chosen, the other constant must be switched off."""
    adaptive = BoxSubdivisionSettings().to_master_settings()
    assert adaptive["adapt"] is True
    assert adaptive["convexification_constant"] == pytest.approx(0.0)
    assert adaptive["min_dfk"] > 0.0

    convex = BoxSubdivisionSettings(mechanism="convexification").to_master_settings()
    assert convex["adapt"] is False
    assert convex["min_dfk"] == pytest.approx(0.0)
    assert convex["convexification_constant"] > 0.0


def test_an_unknown_mechanism_is_refused() -> None:
    """Check the error raised for an unknown mechanism."""
    with pytest.raises(ValueError, match="mechanism must be one of"):
        BoxSubdivisionSettings(mechanism="magic")


@pytest.mark.parametrize("name", ["trust_region_radius", "n_parallel_points"])
def test_positive_counts(name) -> None:
    """Check the error raised for a non-positive count."""
    with pytest.raises(ValueError, match=name):
        BoxSubdivisionSettings(**{name: 0})


def test_the_radius_is_scaled_by_the_levels() -> None:
    """The radius must count variables, not digits, whatever the encoding."""
    settings = BoxSubdivisionSettings(trust_region_radius=2)
    assert settings.to_master_settings()["max_step"] == 2
    assert settings.to_master_settings(radius=2 * 3)["max_step"] == 6


def test_a_mapping_selects_the_variables_it_names() -> None:
    """A mapping of the subdivisions must name the variables to subdivide."""
    space = design_space("a")
    space.add_variable("b", lower_bound=0.0, upper_bound=1.0, size=1, value=0.5)
    scenario = BoxSubdivisionScenario(
        [Rastrigin("a")], "f", space, n_subdivisions={"a": 4}
    )
    assert scenario.subdivision.variable_names == ("a",)
    assert "b_box" not in scenario.formulation.design_space


def test_a_mapping_may_give_a_density_per_variable() -> None:
    """Each variable a mapping names must get the density it asks for."""
    space = design_space("a")
    space.add_variable("b", lower_bound=0.0, upper_bound=1.0, size=1, value=0.5)
    scenario = BoxSubdivisionScenario(
        [Rastrigin("a")], "f", space, n_subdivisions={"a": 4, "b": 7}
    )
    assert scenario.subdivision.n_subdivisions == {"a": 4, "b": 7}


def test_an_unknown_variable_in_the_mapping_is_refused() -> None:
    """Check the error raised when a mapping names a variable that is unknown."""
    with pytest.raises(ValueError, match="not in the design space"):
        BoxSubdivisionScenario(
            [Rastrigin()], "f", design_space(), n_subdivisions={"nope": 4}
        )


def test_an_empty_mapping_is_refused() -> None:
    """Check the error raised for a mapping that names nothing."""
    with pytest.raises(ValueError, match="is empty"):
        BoxSubdivisionScenario([Rastrigin()], "f", design_space(), n_subdivisions={})


def test_the_factory_and_the_class_agree() -> None:
    """The ``create_`` factory must build the very same scenario."""
    scenario = create_box_subdivision_scenario(
        [Rastrigin()], "f", design_space(), n_subdivisions=4
    )
    assert isinstance(scenario, BoxSubdivisionScenario)


def test_explicit_settings_override_the_defaults() -> None:
    """Executing with settings of its own must use those, not the scenario's."""
    scenario = BoxSubdivisionScenario(
        [Rastrigin()], "f", design_space(), n_subdivisions=4
    )
    scenario.execute(
        BiLevelMasterOuterApproximation_Settings(
            max_iter=2, ub_tol=1e-4, adapt=True, min_dfk=100.0, max_step=1
        )
    )
    assert scenario.formulation.optimization_problem.database


def sub_problem_settings(scenario):  # noqa: ANN001, ANN201
    """Return the settings the sub-problems of a scenario are solved with.

    GEMSEO exposes no public accessor for the algorithm of a scenario, hence the
    private attribute: what is being tested is that the settings of the
    sub-problem reach the scenario the ``Benders`` formulation builds.
    """
    sub_scenario = scenario.formulation.sub_problem_scenario_adapter.scenario
    return sub_scenario._settings.algo_settings["settings_model"]  # noqa: SLF001


@pytest.mark.parametrize("formulation", ["normalized", "constraint"])
def test_the_sub_problem_algorithm_reaches_the_sub_problem(formulation) -> None:
    """Whichever formulation confines the box, the solver named must solve it."""
    settings = BoxSubdivisionSettings(
        sub_problem_algo_name="NLOPT_COBYLA",
        sub_problem_algo_settings={"ftol_rel": 1e-6},
    )
    scenario = BoxSubdivisionScenario(
        [Rastrigin()],
        "f",
        design_space(),
        n_subdivisions=4,
        formulation=formulation,
        settings=settings,
    )

    model = sub_problem_settings(scenario)
    assert isinstance(model, NLOPT_COBYLA_Settings)
    assert model.max_iter == settings.sub_problem_max_iter
    assert model.ftol_rel == pytest.approx(1e-6)


def test_the_sub_problem_algorithm_reaches_a_multi_resolution_sub_problem() -> None:
    """The multi-resolution encoding builds its own scenario, and must too."""
    scenario = BoxSubdivisionScenario(
        [Rastrigin()],
        "f",
        design_space(),
        n_subdivisions=2,
        levels=2,
        settings=BoxSubdivisionSettings(sub_problem_algo_name="NLOPT_COBYLA"),
    )
    assert isinstance(sub_problem_settings(scenario), NLOPT_COBYLA_Settings)


def test_the_master_algorithm_is_a_setting() -> None:
    """The master executed must be the algorithm named, with its own settings."""
    settings = BoxSubdivisionSettings(
        master_algo_name="OUTER_APPROXIMATION",
        master_algo_settings={"upper_bound_stall": 3},
        max_iter=10,
    )
    master_settings = settings.to_master_settings()
    assert master_settings["upper_bound_stall"] == 3
    assert master_settings["max_step"] == settings.trust_region_radius
    assert master_settings["min_dfk"] == pytest.approx(settings.convexity_margin)

    scenario = BoxSubdivisionScenario(
        [Rastrigin()], "f", design_space(), n_subdivisions=4, settings=settings
    )
    scenario.execute()
    # A settings model would carry the name of the algorithm it selects, which
    # for this one is not the name it is registered under.
    assert scenario.optimization_result.optimizer_name == "OUTER_APPROXIMATION"


def test_the_master_of_the_defaults_is_the_one_executed() -> None:
    """The default master must be the one the scenario executes."""
    scenario = BoxSubdivisionScenario(
        [Rastrigin()],
        "f",
        design_space(),
        n_subdivisions=4,
        settings=BoxSubdivisionSettings(max_iter=10),
    )
    scenario.execute()
    assert (
        scenario.optimization_result.optimizer_name
        == "BILEVEL_MASTER_OUTER_APPROXIMATION"
    )


def test_the_defaults_are_the_measured_pair() -> None:
    """The defaults must stay the pair every reported result was measured with."""
    settings = BoxSubdivisionSettings()
    assert settings.master_algo_name == "BILEVEL_MASTER_OUTER_APPROXIMATION"
    assert settings.sub_problem_algo_name == "SLSQP"
    assert isinstance(settings.create_sub_problem_settings_model(), SLSQP_Settings)
    assert set(settings.to_master_settings()).issubset(
        BiLevelMasterOuterApproximation_Settings.model_fields
    )


def test_the_sub_problem_settings_carry_the_iterations() -> None:
    """``sub_problem_max_iter`` is the ``max_iter`` of the sub-problem solver."""
    settings = BoxSubdivisionSettings(sub_problem_max_iter=7)
    assert settings.to_sub_problem_settings() == {"max_iter": 7}
    assert settings.create_sub_problem_settings_model().max_iter == 7


@pytest.mark.parametrize(
    ("settings", "name"),
    [
        ({"sub_problem_algo_settings": {"max_iter": 3}}, "sub_problem_algo_settings"),
        ({"master_algo_settings": {"max_step": 5}}, "master_algo_settings"),
    ],
)
def test_the_pass_through_wins(settings, name) -> None:
    """A setting given by name must override the one the class translates."""
    del name
    box_settings = BoxSubdivisionSettings(
        sub_problem_max_iter=40, trust_region_radius=2, **settings
    )
    if "sub_problem_algo_settings" in settings:
        assert box_settings.create_sub_problem_settings_model().max_iter == 3
    else:
        assert box_settings.to_master_settings()["max_step"] == 5


@pytest.mark.parametrize(
    "settings",
    [
        {"master_algo_name": "magic"},
        {"sub_problem_algo_name": "magic"},
    ],
)
def test_an_unknown_algorithm_is_refused(settings) -> None:
    """Check the error raised for an algorithm no GEMSEO library provides."""
    with pytest.raises(ValueError, match="'magic' is not available"):
        BoxSubdivisionSettings(**settings)


def test_an_ordinary_optimizer_cannot_be_the_master() -> None:
    """An optimizer without integers returns the relaxation rather than a box.

    The master problem is a relaxable mixed-integer non-linear one: its
    relaxation is what the outer approximation solves, and the integers are what
    it recovers a box from. A solver that holds none of them has nothing to
    recover.
    """
    with pytest.raises(
        ValueError, match="'SLSQP' of the master problem does not handle integer"
    ):
        BoxSubdivisionSettings(master_algo_name="SLSQP")


def test_a_master_solving_linear_problems_only_cannot_solve_it() -> None:
    """Check that a linear solver is refused, the master problem being non-linear.

    Its relaxation is what the outer approximation solves, and the cuts and the
    convexification are what make it non-linear, so a solver for linear problems
    would be refused by GEMSEO in the middle of the run instead.
    """
    with pytest.raises(
        ValueError, match=r"'ORTOOLS_MILP' of the master problem solves linear"
    ):
        BoxSubdivisionSettings(master_algo_name="ORTOOLS_MILP")


def test_a_master_that_is_not_an_outer_approximation_takes_none_of_its_settings() -> (
    None
):
    """A setting of the outer approximation is refused for a master without it.

    The mechanism, the convexity and the trust region describe an outer
    approximation. Another master is driven by ``master_algo_settings`` under its
    own names, and naming it while setting one of those is a contradiction.
    """
    with pytest.raises(
        ValueError,
        match=r"'DIFFERENTIAL_EVOLUTION' of the master problem does not take",
    ):
        BoxSubdivisionSettings(
            master_algo_name="DIFFERENTIAL_EVOLUTION", mechanism="convexification"
        )

    # Left at their defaults, they reach no master that cannot take them.
    settings = BoxSubdivisionSettings(master_algo_name="DIFFERENTIAL_EVOLUTION")
    assert "min_dfk" not in settings.to_master_settings()


def test_a_setting_the_sub_problem_solver_does_not_have_is_refused() -> None:
    """A setting of another solver must be refused where it is written."""
    with pytest.raises(
        ValueError, match="'NLOPT_COBYLA' of the sub-problems does not take"
    ):
        BoxSubdivisionSettings(
            sub_problem_algo_name="NLOPT_COBYLA",
            sub_problem_algo_settings={"kkt_tol_abs": 1e-3},
        )


def test_the_deprecated_options_still_configure_the_master() -> None:
    """``options`` must keep working, and warn, until it is removed."""
    with pytest.warns(FutureWarning, match="use 'master_algo_settings'"):
        settings = BoxSubdivisionSettings(options={"upper_bound_stall": 3})

    assert settings.to_master_settings()["upper_bound_stall"] == 3


def test_master_algo_settings_win_over_the_deprecated_options() -> None:
    """Given both, the setting under its own name must be the one used."""
    with pytest.warns(FutureWarning):
        settings = BoxSubdivisionSettings(
            options={"upper_bound_stall": 3},
            master_algo_settings={"upper_bound_stall": 5},
        )

    assert settings.to_master_settings()["upper_bound_stall"] == 5


def test_a_gradient_free_sub_problem_solver_solves_rastrigin() -> None:
    """A whole run must work with another sub-problem solver, not merely build."""
    scenario = BoxSubdivisionScenario(
        [Rastrigin()],
        "f",
        design_space(),
        n_subdivisions=4,
        settings=BoxSubdivisionSettings(
            sub_problem_algo_name="NLOPT_COBYLA",
            sub_problem_algo_settings={"ftol_rel": 1e-8},
            max_iter=20,
        ),
    )
    scenario.execute()
    assert best(scenario) < 5.0


def test_an_algorithm_whose_settings_select_another_one_is_refused() -> None:
    """The name the settings select is the one executed, so it must be the one asked."""
    with pytest.raises(ValueError, match="select 'OrtoolsMILP' instead"):
        BoxSubdivisionSettings(sub_problem_algo_name="ORTOOLS_MILP")


def test_the_settings_are_given_by_name() -> None:
    """Check that a positional value is refused rather than bound by position.

    Which class holds which setting follows what applies to what, so the order
    of the fields is not an interface: a value given positionally would bind to
    whatever sits in that position, and a margin arriving as a trust-region
    radius is a run that measures something else in silence.
    """
    with pytest.raises(TypeError, match="positional argument"):
        BoxSubdivisionSettings("adaptive", 50.0)

    assert BoxSubdivisionSettings(
        mechanism="adaptive", convexity_margin=50.0
    ).convexity_value == pytest.approx(50.0)


class Quadratic(Discipline):
    """A quadratic whose optimum needs a different box per component."""

    def __init__(self, target: ndarray) -> None:
        super().__init__()
        self.__target = target
        self.io.input_grammar.update_from_data({"x": zeros(target.size)})
        self.io.output_grammar.update_from_data({"f": zeros(1)})
        self.default_input_data = {"x": zeros(target.size)}

    def _run(self, input_data):  # noqa: ANN001, ANN202
        return {"f": array([float(((input_data["x"] - self.__target) ** 2).sum())])}

    def _compute_jacobian(self, input_names=(), output_names=()) -> None:  # noqa: ANN001
        self._init_jacobian(input_names, output_names)
        self.jac["f"]["x"] = (2 * (self.io.data["x"] - self.__target)).reshape(1, -1)


@pytest.mark.parametrize("formulation", ["normalized", "constraint"])
def test_a_variable_of_several_components_chooses_a_box_per_component(
    formulation,
) -> None:
    """Check that each component of an array variable selects its own box.

    A variable of size $s$ subdivided into $m$ is $s$ independent choices of
    one subdivision out of $m$, not one choice shared by the components, so the
    master carries one sum-to-one group per component. The sizes are taken apart,
    two components and four subdivisions, because a square case cannot tell a
    grouping by component from a grouping by subdivision.
    """
    target = array([0.9, -0.9])
    space = DesignSpace()
    space.add_variable("x", lower_bound=-1.0, upper_bound=1.0, size=2, value=zeros(2))
    scenario = BoxSubdivisionScenario(
        [Quadratic(target)],
        "f",
        space,
        n_subdivisions=4,
        formulation=formulation,
        settings=BoxSubdivisionSettings(max_iter=30),
    )
    scenario.execute()

    one_hot = scenario.optimization_result.x_opt
    assert one_hot.size == 8, "two components of four subdivisions is eight binaries"

    # The optimum is at the top of the first component's range and at the bottom
    # of the second's, so the two components take opposite ends of the ladder: a
    # master choosing one subdivision for the whole variable cannot express it.
    assert_allclose(one_hot[:4], [0.0, 0.0, 0.0, 1.0], atol=1e-6)
    assert_allclose(one_hot[4:], [1.0, 0.0, 0.0, 0.0], atol=1e-6)
    assert scenario.optimization_result.f_opt < 1e-8


def test_the_components_of_a_variable_are_independent_under_the_levels() -> None:
    """Check the same of the multi-resolution encoding, level by level."""
    target = array([0.9, -0.9])
    space = DesignSpace()
    space.add_variable("x", lower_bound=-1.0, upper_bound=1.0, size=2, value=zeros(2))
    scenario = BoxSubdivisionScenario(
        [Quadratic(target)],
        "f",
        space,
        n_subdivisions=2,
        levels=2,
        settings=BoxSubdivisionSettings(max_iter=40),
    )
    scenario.execute()

    one_hot = scenario.optimization_result.x_opt
    assert one_hot.size == 8, "two components, two levels, two branches"

    # One group per component per level, the coarse level first: the upper half
    # then its upper quarter for the first component, the lower half then its
    # lower quarter for the second.
    assert_allclose(one_hot, [0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0], atol=1e-6)
    assert scenario.optimization_result.f_opt < 1e-8


class RecordingAdapter(MDOScenarioAdapterBenders):
    """An adapter recording that it ran, to show which class the run used."""

    boxes: ClassVar[list[str]] = []

    def _pre_run(self) -> None:
        super()._pre_run()
        RecordingAdapter.boxes.append(type(self).__name__)


@pytest.mark.parametrize("formulation", ["normalized", "constraint"])
def test_the_starting_point_of_a_sub_problem_is_the_callers_to_own(
    formulation,
) -> None:
    """An adapter given by the caller must be the one the sub-problems run under.

    The center of a box is a starting point, not a law: a problem whose
    disciplines reject that point needs its own policy, and the normalized
    formulation used to offer no way to supply one.
    """
    scenario = create_box_subdivision_scenario(
        [Rastrigin()],
        "f",
        design_space(),
        n_subdivisions=2,
        formulation=formulation,
        scenario_adapter_cls=RecordingAdapter,
    )
    adapter = scenario.formulation.sub_problem_scenario_adapter
    assert isinstance(adapter, RecordingAdapter)


def test_the_caller_adapter_wins_over_the_box_start_one() -> None:
    """The constraint formulation hard-coded its adapter; the caller now wins."""
    scenario = create_box_subdivision_scenario(
        [Rastrigin()],
        "f",
        design_space(),
        n_subdivisions=2,
        formulation="constraint",
        scenario_adapter_cls=RecordingAdapter,
    )
    adapter = scenario.formulation.sub_problem_scenario_adapter
    assert type(adapter).__name__ == "RecordingAdapter"
    # The box is still enforced by the constraint the formulation declares.
    problem = adapter.scenario.formulation.optimization_problem
    assert problem.constraints.get_names() == ["g_box"]


def test_the_multi_resolution_encoding_takes_the_adapter_too() -> None:
    """Every construction goes through one adapter, so all three must take one."""
    scenario = create_box_subdivision_scenario(
        [Rastrigin()],
        "f",
        design_space(),
        n_subdivisions=2,
        levels=2,
        scenario_adapter_cls=RecordingAdapter,
    )
    adapter = scenario.formulation.sub_problem_scenario_adapter
    assert isinstance(adapter, RecordingAdapter)


def test_the_default_adapter_is_unchanged() -> None:
    """Supplying nothing must leave each construction on the policy it had."""
    normalized = create_box_subdivision_scenario(
        [Rastrigin()], "f", design_space(), n_subdivisions=2
    )
    constrained = create_box_subdivision_scenario(
        [Rastrigin()], "f", design_space(), n_subdivisions=2, formulation="constraint"
    )
    assert (
        type(normalized.formulation.sub_problem_scenario_adapter).__name__
        == "MDOScenarioAdapterBenders"
    )
    assert (
        type(constrained.formulation.sub_problem_scenario_adapter).__name__
        == "BoxStartScenarioAdapter"
    )


def test_a_caller_adapter_runs_the_sub_problems() -> None:
    """The adapter must be reached by an execution, not merely be stored."""
    RecordingAdapter.boxes.clear()
    scenario = create_box_subdivision_scenario(
        [Rastrigin()],
        "f",
        design_space(),
        n_subdivisions=2,
        settings=BoxSubdivisionSettings(max_iter=2, sub_problem_max_iter=5),
        scenario_adapter_cls=RecordingAdapter,
    )
    scenario.execute()
    assert RecordingAdapter.boxes
