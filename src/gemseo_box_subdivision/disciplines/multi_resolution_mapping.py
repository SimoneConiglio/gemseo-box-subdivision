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
"""The mapping from the levels of a multi-resolution subdivision to the variables."""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import ClassVar

from gemseo.core.discipline import Discipline
from numpy import diag
from numpy import zeros

if TYPE_CHECKING:
    from collections.abc import Iterable

    from gemseo.util.typing import StrKeyMapping

    from gemseo_box_subdivision.subdivisions.multi_resolution import MultiResolution


class MultiResolutionMapping(Discipline):
    r"""The mapping from the digits of a box and a normalized point to a design value.

    The counterpart of :class:`.BoxMapping` for a
    :class:`.MultiResolution` subdivision, in which a box is chosen by one
    categorical variable per level rather than by one over the whole
    subdivision:

    .. math::

        x_j(\xi, \alpha)
        = L_j + \Delta_j \sum_{k=1}^{L} m^{-k} \, d_k(\alpha_j)
        + \xi_j \, \Delta_j \, m^{-L}.

    It is chained **before** the objective discipline, which keeps receiving the
    design variables under their own names, exactly as :class:`.BoxMapping` is.

    The width :math:`\Delta_j m^{-L}` does not depend on the levels at all, so
    every Jacobian block is constant: the derivative with respect to a level is
    the value that digit contributes, and the derivative with respect to the
    normalized point is the width of the smallest box. The bilinearity is the
    same as the one-level mapping's, so the post-optimal sensitivity of the
    ``Benders`` formulation applies unchanged.
    """

    default_grammar_type: ClassVar[Discipline.GrammarType] = (
        Discipline.GrammarType.SIMPLER
    )

    __subdivision: MultiResolution
    """The multi-resolution subdivision of the design space."""

    def __init__(self, subdivision: MultiResolution, name: str = "") -> None:
        """
        Args:
            subdivision: The multi-resolution subdivision of the design space.
        """  # noqa: D205, D212
        super().__init__(name=name)
        self.__subdivision = subdivision

        input_data = {}
        output_data = {}
        for variable_name in subdivision.variable_names:
            size = subdivision.sizes[variable_name]
            # The center of the smallest box, whichever box is selected.
            input_data[subdivision.get_normalized_name(variable_name)] = (
                zeros(size) + 0.5
            )
            for level in range(1, subdivision.levels + 1):
                one_hot = zeros((size, subdivision.branching))
                one_hot[:, 0] = 1.0
                input_data[subdivision.get_one_hot_name(variable_name, level)] = (
                    one_hot.ravel()
                )

            output_data[variable_name] = zeros(size)

        self.io.input_grammar.update_from_data(input_data)
        self.io.output_grammar.update_from_data(output_data)
        self.default_input_data = input_data

    def __one_hots(
        self, data: StrKeyMapping, variable_name: str
    ) -> list[StrKeyMapping]:
        """Return the one-hot vector of every level of a design variable.

        Args:
            data: The input data.
            variable_name: The name of the design variable.

        Returns:
            The one-hot vector of each level, coarsest first.
        """
        return [
            data[self.__subdivision.get_one_hot_name(variable_name, level)]
            for level in range(1, self.__subdivision.levels + 1)
        ]

    def _run(self, input_data: StrKeyMapping) -> StrKeyMapping:
        subdivision = self.__subdivision
        output_data = {}
        for variable_name in subdivision.variable_names:
            lower_bound, upper_bound = subdivision.compute_bounds(
                variable_name, self.__one_hots(input_data, variable_name)
            )
            normalized = input_data[subdivision.get_normalized_name(variable_name)]
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
        smallest = 1.0 / subdivision.resolution
        for variable_name in subdivision.variable_names:
            size = subdivision.sizes[variable_name]
            lower_bound, upper_bound = subdivision.compute_bounds(
                variable_name, self.__one_hots(data, variable_name)
            )
            # The width of the smallest box, which no level changes.
            width = (upper_bound - lower_bound) / smallest
            jacobian = self.jac[variable_name]
            jacobian[subdivision.get_normalized_name(variable_name)] = diag(
                upper_bound - lower_bound
            )
            for level in range(1, subdivision.levels + 1):
                # One block per level: a component moves by what its digit is
                # worth, scaled by the range of that component.
                values = subdivision.get_digit_values(level)
                derivatives = zeros((size, size * subdivision.branching))
                for component in range(size):
                    columns = slice(
                        component * subdivision.branching,
                        (component + 1) * subdivision.branching,
                    )
                    derivatives[component, columns] = width[component] * values

                jacobian[subdivision.get_one_hot_name(variable_name, level)] = (
                    derivatives
                )
