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
r"""A scenario solving a problem by subdividing its design space.

Composing a run by hand means chaining the mapping before the objective, building
the design space from the *same* subdivision, naming the one-hot variables of the
master, choosing the formulation and sizing the trust region. None of those is a
decision: they are invariants, and every one of them is a way to get a silently
wrong run.

:class:`.BoxSubdivisionScenario` owns them. What it leaves to the caller is what
the measurements say actually matters: **which variables to subdivide and how
finely**, and the **convexity margin**, which is in the units of the objective
and transfers between problems no better than a length does.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING
from typing import Any

from gemseo.core.chains.chain import MDOChain
from gemseo.scenarios.mdo_scenario import MDOScenario
from gemseo.settings.formulations import DisciplinaryOpt_Settings

from gemseo_box_subdivision.design_spaces import create_box_design_space
from gemseo_box_subdivision.design_spaces import create_normalized_box_design_space
from gemseo_box_subdivision.disciplines.box_constraint import BoxConstraint
from gemseo_box_subdivision.disciplines.box_mapping import BoxMapping
from gemseo_box_subdivision.disciplines.multi_resolution_mapping import (
    MultiResolutionMapping,
)
from gemseo_box_subdivision.disciplines.scenario_adapters.box_start import (
    create_box_start_adapter_class,
)
from gemseo_box_subdivision.settings import BaseBoxSubdivisionSettings
from gemseo_box_subdivision.settings import BoxSubdivisionSettings
from gemseo_box_subdivision.subdivisions.box import BoxSubdivision
from gemseo_box_subdivision.subdivisions.multi_resolution import MultiResolution

if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Mapping
    from collections.abc import Sequence

    from gemseo.algos.design_space import DesignSpace
    from gemseo.core.discipline import Discipline
    from numpy import ndarray

FORMULATIONS: tuple[str, ...] = ("normalized", "constraint")
"""The two ways of confining a sub-problem to its box."""


class BoxSubdivisionScenario(MDOScenario):
    r"""A scenario exploring a design space by subdividing it into boxes.

    It is an ordinary GEMSEO scenario, executed the same way:

    .. code-block:: python

        scenario = BoxSubdivisionScenario(
            [objective_discipline], "f", design_space, n_subdivisions=10
        )
        scenario.execute()

    Executing it without arguments uses the settings it was built with, so the
    master of the outer approximation never has to be configured by hand. Passing
    settings explicitly overrides them, as for any scenario.

    The algorithm of each of the two levels, and its settings, come from
    :class:`.BoxSubdivisionSettings`: the master from
    :attr:`~.BoxSubdivisionSettings.master_algo_name` and
    :attr:`~.BoxSubdivisionSettings.master_algo_settings`, each sub-problem from
    :attr:`~.BoxSubdivisionSettings.sub_problem_algo_name` and
    :attr:`~.BoxSubdivisionSettings.sub_problem_algo_settings`.

    The four constructions share this one entry point:

    - a **flat** subdivision, the default;
    - **subdividing some variables only**, by passing a mapping of
      ``n_subdivisions`` whose keys are the variables to subdivide, or by naming
      them in ``variable_names``;
    - the **multi-resolution encoding**, by asking for more than one ``level``;
    - the box as a **constraint** of the sub-problem rather than its bounds, by
      asking for the ``"constraint"`` formulation.
    """

    subdivision: BoxSubdivision | MultiResolution
    """The subdivision of the design space the scenario explores."""

    box_settings: BaseBoxSubdivisionSettings
    """The settings of the run."""

    def __init__(
        self,
        disciplines: Sequence[Discipline],
        objective_name: str,
        design_space: DesignSpace,
        n_subdivisions: int | Mapping[str, int] = 10,
        variable_names: Iterable[str] = (),
        levels: int = 1,
        formulation: str = "normalized",
        weights: Mapping[str, ndarray] = MappingProxyType({}),
        settings: BaseBoxSubdivisionSettings | None = None,
        name: str = "",
    ) -> None:
        """
        Args:
            disciplines: The disciplines computing the objective, and the
                constraints if any. The mapping of the boxes is chained in front
                of them, so they keep receiving the design variables under their
                own names.
            objective_name: The name of the objective output.
            design_space: The design space of the original problem.
            n_subdivisions: The number of subdivisions of every subdivided
                variable, or a mapping of the number of subdivisions of each.
                **A mapping also selects the variables to subdivide**, its keys
                being those variables, so that subdividing two variables of five
                finely is one argument rather than two. With ``levels`` above
                one this is the branching of a level.
            variable_names: The variables to subdivide, when
                ``n_subdivisions`` is a single number. If empty, subdivide every
                variable of the design space. Ignored when ``n_subdivisions``
                is a mapping, which names them itself.
            levels: The number of levels of the multi-resolution encoding. One,
                the default, is the flat subdivision. Above one, a box is chosen
                by one categorical variable per level, which reaches a
                resolution of ``n_subdivisions ** levels`` for ``levels`` times
                the binaries of a single level.
            formulation: ``"normalized"``, the recommended one, in which the
                sub-problem is written in the normalized variables of its box,
                or ``"constraint"``, in which the box is a constraint of the
                sub-problem.
            weights: The weights of the subdivisions of each variable, which set
                the distance the trust region of the master measures. If empty,
                weigh every subdivision alike, so that the distance is the
                number of components a candidate changes. This is the metric the
                measurements support; the alternative exists to be swept.
            settings: The settings of the run, either
                :class:`.BoxSubdivisionSettings`, which names the master and the
                sub-problem solver and calibrates the convexity, or
                :class:`.SweptBoxSubdivisionSettings`, which sweeps the convexity
                instead of asking for a value and drives the master implementing
                it. If ``None``, use the defaults of
                :class:`.BoxSubdivisionSettings`, whose convexity margin only
                suits an objective of the scale of the benchmark.
            name: The name of the scenario.

        Raises:
            ValueError: When the formulation is unknown, or when the
                multi-resolution encoding is asked for together with the
                constraint formulation, which it does not support.
        """  # noqa: D205, D212
        self.box_settings = settings or BoxSubdivisionSettings()
        if formulation not in FORMULATIONS:
            msg = (
                f"The formulation must be one of {list(FORMULATIONS)}; "
                f"got {formulation!r}."
            )
            raise ValueError(msg)

        names = _subdivided_names(design_space, n_subdivisions, variable_names)
        if levels > 1:
            if formulation == "constraint":
                msg = (
                    "The multi-resolution encoding supports the normalized "
                    "formulation only."
                )
                raise ValueError(msg)

            self.__init_multi_resolution(
                disciplines,
                objective_name,
                design_space,
                n_subdivisions,
                names,
                levels,
                name,
            )
            return

        self.subdivision = BoxSubdivision.from_design_space(
            design_space, n_subdivisions, names
        )
        # The names the master optimizes over are the one-hot variables of the
        # subdivision, never a literal: they follow the design space.
        settings_of_formulation = {
            "formulation_name": "Benders",
            "main_problem_design_variables": list(
                self.subdivision.get_one_hot_names({}).values()
            ),
            "sub_problem_algo_settings": (
                self.box_settings.create_sub_problem_settings_model()
            ),
            "sub_problem_formulation_settings": DisciplinaryOpt_Settings(),
        }
        if formulation == "normalized":
            # The mapping is chained *before* the objective, so the sub-problem
            # solves for the normalized variables while the disciplines keep
            # receiving the design variables.
            super().__init__(
                [MDOChain([BoxMapping(self.subdivision), *disciplines])],
                objective_name,
                create_normalized_box_design_space(
                    self.subdivision, design_space, weights=weights
                ),
                name=name,
                **settings_of_formulation,
            )
        else:
            super().__init__(
                [*disciplines, BoxConstraint(self.subdivision)],
                objective_name,
                create_box_design_space(
                    self.subdivision, design_space, weights=weights
                ),
                name=name,
                scenario_adapter_cls=create_box_start_adapter_class(self.subdivision),
                **settings_of_formulation,
            )
            # The box is enforced by a constraint of the sub-problem, which the
            # formulation only knows about once it is declared.
            self.formulation.add_constraint(BoxConstraint.DEFAULT_OUTPUT_NAME)

    def __init_multi_resolution(
        self,
        disciplines: Sequence[Discipline],
        objective_name: str,
        design_space: DesignSpace,
        branching: int | Mapping[str, int],
        names: tuple[str, ...],
        levels: int,
        name: str,
    ) -> None:
        """Build the scenario of a multi-resolution encoding.

        Args:
            disciplines: The disciplines computing the objective.
            objective_name: The name of the objective output.
            design_space: The design space of the original problem.
            branching: The number of subdivisions of a component at each level.
            names: The variables to subdivide.
            levels: The number of levels.
            name: The name of the scenario.

        Raises:
            ValueError: When the branching differs between variables, which this
                encoding does not support.
        """
        if not isinstance(branching, int):
            values = {branching[variable_name] for variable_name in names}
            if len(values) > 1:
                msg = (
                    "The multi-resolution encoding needs the same branching for "
                    f"every variable; got {sorted(values)}."
                )
                raise ValueError(msg)

            branching = values.pop()

        self.subdivision = MultiResolution(
            {n: design_space.get_lower_bounds([n]) for n in names},
            {n: design_space.get_upper_bounds([n]) for n in names},
            branching,
            levels,
        )
        super().__init__(
            [MDOChain([MultiResolutionMapping(self.subdivision), *disciplines])],
            objective_name,
            self.subdivision.create_design_space(),
            name=name,
            formulation_name="Benders",
            main_problem_design_variables=[
                self.subdivision.get_one_hot_name(variable_name, level)
                for variable_name in names
                for level in range(1, levels + 1)
            ],
            sub_problem_algo_settings=(
                self.box_settings.create_sub_problem_settings_model()
            ),
            sub_problem_formulation_settings=DisciplinaryOpt_Settings(),
        )

    def execute(self, algo_settings_model: Any = None, **algo_settings: Any) -> None:
        """Execute the scenario.

        Without arguments, run the master named by the settings the scenario was
        built with, with those settings, the radius of the trust region scaled
        where the distance counts something other than design variables: the
        multi-resolution encoding has one one-hot group per level per variable,
        so two whole variables is twice the number of levels.

        Args:
            algo_settings_model: The settings of the master, overriding those of
                the scenario, the model naming the algorithm to execute.
            **algo_settings: The settings of the master, as keyword arguments.

        Returns:
            Whatever a GEMSEO scenario returns.
        """
        # Whatever the run supplies its master applies to every execution, not
        # only to the one this class configures: settings given here override
        # what the master is told, never what the run needs of it.
        with self.box_settings.drive_the_master():
            if algo_settings_model is None and not algo_settings:
                radius = None
                if isinstance(self.subdivision, MultiResolution):
                    radius = (
                        self.box_settings.trust_region_radius * self.subdivision.levels
                    )

                # The master is selected by its name rather than by a settings
                # model: a model names the algorithm to execute itself, and the
                # settings of ``OUTER_APPROXIMATION`` name one no library
                # provides, so a model would not run ``master_algo_name``.
                return super().execute(
                    algo_name=self.box_settings.master_algo_name,
                    **self.box_settings.to_master_settings(radius),
                )

            return super().execute(algo_settings_model, **algo_settings)


def _subdivided_names(
    design_space: DesignSpace,
    n_subdivisions: int | Mapping[str, int],
    variable_names: Iterable[str],
) -> tuple[str, ...]:
    """Return the variables to subdivide.

    A mapping of the number of subdivisions names the variables by its keys,
    which is the natural way of asking for a few of them to be subdivided
    finely; a single number leaves that to ``variable_names``.

    Args:
        design_space: The design space of the original problem.
        n_subdivisions: The number of subdivisions, or of each variable.
        variable_names: The variables to subdivide, for a single number.

    Returns:
        The names of the variables to subdivide.

    Raises:
        ValueError: When a mapping is empty, or names a variable that is not in
            the design space.
    """
    if isinstance(n_subdivisions, int):
        return tuple(variable_names) or tuple(design_space.variable_names)

    names = tuple(n_subdivisions)
    if not names:
        msg = "The mapping of the numbers of subdivisions is empty."
        raise ValueError(msg)

    if unknown := set(names) - set(design_space.variable_names):
        msg = f"The following variables are not in the design space: {sorted(unknown)}."
        raise ValueError(msg)

    return names


def create_box_subdivision_scenario(
    disciplines: Sequence[Discipline],
    objective_name: str,
    design_space: DesignSpace,
    **settings: Any,
) -> BoxSubdivisionScenario:
    """Return a scenario solving a problem by subdividing its design space.

    The factory of :class:`.BoxSubdivisionScenario`, for the ``create_`` idiom of
    GEMSEO. The two are interchangeable.

    Args:
        disciplines: The disciplines computing the objective.
        objective_name: The name of the objective output.
        design_space: The design space of the original problem.
        **settings: The settings of :class:`.BoxSubdivisionScenario`.

    Returns:
        The scenario, ready to execute.
    """
    return BoxSubdivisionScenario(disciplines, objective_name, design_space, **settings)
