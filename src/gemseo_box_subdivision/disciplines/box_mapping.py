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
"""The mapping from the normalized variables of a box to the design variables."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING
from typing import ClassVar

from gemseo.core.discipline import Discipline
from numpy import diag
from numpy import zeros

if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Mapping

    from gemseo.util.typing import StrKeyMapping

    from gemseo_box_subdivision.subdivisions.box import BoxSubdivision


class BoxMapping(Discipline):
    r"""The mapping from the normalized variables of a box to the design variables.

    The sub-problem is written in the normalized variables :math:`\xi \in [0, 1]^n`
    of the box selected by the one-hot vector :math:`\alpha`, through

    .. math::

        x(\xi, \alpha) = \ell(\alpha) + \xi \odot (u(\alpha) - \ell(\alpha)).

    This is an alternative to :class:`.BoxConstraint`, in which the box is not a
    constraint of the sub-problem but the bounds of its design space. Those
    bounds are :math:`[0, 1]` whatever the box, hence:

    - the sub-problem always starts at the same point of its own box, the center
      for :math:`\xi = 0.5`, so no scenario adapter is needed to place the
      starting point inside the box;
    - the design space of the sub-problem does not depend on :math:`\alpha`,
      which is what the ``Benders`` formulation of GEMSEO requires, instead of
      being worked around;
    - the bounds are genuinely independent of :math:`\alpha`, so the assumption
      made by the post-optimal analysis of GEMSEO holds, and no margin is needed
      to keep a border box from losing the multiplier of its face.

    The sensitivity of the sub-problem optimum then comes from the partial
    derivative of the objective rather than from constraint multipliers:

    .. math::

        \frac{\mathrm{d}u}{\mathrm{d}\alpha_{j,k}}
        = \nabla_x f \cdot \frac{\partial x}{\partial \alpha_{j,k}},
        \qquad
        \frac{\partial x_j}{\partial \alpha_{j,k}}
        = (1 - \xi_j)\, l_{j,k} + \xi_j\, u_{j,k},

    which is correct both at an interior optimum, where :math:`\nabla_x f`
    vanishes, and on a face, where :math:`\xi_j` is pinned to a bound so that the
    partial derivative is the total one.

    The counterpart is that :math:`x` is bilinear in :math:`(\xi, \alpha)`: the
    choice of the box enters the non-linearity of the objective, instead of
    staying in a jointly convex constraint as it does with
    :class:`.BoxConstraint`.
    """

    default_grammar_type: ClassVar[Discipline.GrammarType] = (
        Discipline.GrammarType.SIMPLER
    )

    __subdivision: BoxSubdivision
    """The Cartesian subdivision of the design space."""

    __one_hot_names: dict[str, str]
    """The name of the one-hot variable of each design variable."""

    __normalized_names: dict[str, str]
    """The name of the normalized variable of each design variable."""

    def __init__(
        self,
        subdivision: BoxSubdivision,
        one_hot_names: Mapping[str, str] = MappingProxyType({}),
        normalized_names: Mapping[str, str] = MappingProxyType({}),
        name: str = "",
    ) -> None:
        """
        Args:
            subdivision: The Cartesian subdivision of the design space.
            one_hot_names: The name of the one-hot variable of each design
                variable. If empty, suffix the design variable names with
                :attr:`.BoxSubdivision.ONE_HOT_SUFFIX`.
            normalized_names: The name of the normalized variable of each design
                variable. If empty, suffix the design variable names with
                :attr:`.BoxSubdivision.NORMALIZED_SUFFIX`.
        """  # noqa: D205, D212
        super().__init__(name=name)
        self.__subdivision = subdivision
        self.__one_hot_names = subdivision.get_one_hot_names(one_hot_names)
        self.__normalized_names = subdivision.get_normalized_names(normalized_names)

        input_data = {}
        output_data = {}
        for variable_name in subdivision.variable_names:
            size = subdivision.sizes[variable_name]
            n_subdivisions = subdivision.n_subdivisions[variable_name]
            # The center of a box, whichever box is selected.
            input_data[self.__normalized_names[variable_name]] = zeros(size) + 0.5
            one_hot = zeros((size, n_subdivisions))
            one_hot[:, 0] = 1.0
            input_data[self.__one_hot_names[variable_name]] = one_hot.ravel()
            output_data[variable_name] = zeros(size)

        self.io.input_grammar.update_from_data(input_data)
        self.io.output_grammar.update_from_data(output_data)
        self.default_input_data = input_data

    @property
    def one_hot_names(self) -> dict[str, str]:
        """The name of the one-hot variable of each design variable."""
        return dict(self.__one_hot_names)

    @property
    def normalized_names(self) -> dict[str, str]:
        """The name of the normalized variable of each design variable."""
        return dict(self.__normalized_names)

    def _run(self, input_data: StrKeyMapping) -> StrKeyMapping:
        output_data = {}
        for variable_name in self.__subdivision.variable_names:
            lower_bound, upper_bound = self.__subdivision.compute_bounds(
                variable_name, input_data[self.__one_hot_names[variable_name]]
            )
            normalized = input_data[self.__normalized_names[variable_name]]
            output_data[variable_name] = lower_bound + normalized * (
                upper_bound - lower_bound
            )

        return output_data

    def _compute_jacobian(
        self,
        input_names: Iterable[str] = (),
        output_names: Iterable[str] = (),
    ) -> None:
        self._init_jacobian(input_names, output_names)
        subdivision = self.__subdivision
        data = self.io.data
        for variable_name in subdivision.variable_names:
            one_hot_name = self.__one_hot_names[variable_name]
            normalized = data[self.__normalized_names[variable_name]]
            lower_bound, upper_bound = subdivision.compute_bounds(
                variable_name, data[one_hot_name]
            )
            jacobian = self.jac[variable_name]
            # The width of the selected box scales the normalized variable.
            jacobian[self.__normalized_names[variable_name]] = diag(
                upper_bound - lower_bound
            )

            size = subdivision.sizes[variable_name]
            n_subdivisions = subdivision.n_subdivisions[variable_name]
            lower_bounds = subdivision.get_lower_bounds(variable_name)
            upper_bounds = subdivision.get_upper_bounds(variable_name)
            derivatives = zeros((size, size * n_subdivisions))
            for component in range(size):
                columns = slice(
                    component * n_subdivisions, (component + 1) * n_subdivisions
                )
                derivatives[component, columns] = (
                    1.0 - normalized[component]
                ) * lower_bounds[component] + normalized[component] * upper_bounds[
                    component
                ]

            jacobian[one_hot_name] = derivatives
