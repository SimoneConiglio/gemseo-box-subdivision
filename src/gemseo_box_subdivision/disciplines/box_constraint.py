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
"""The box of a Cartesian subdivision, expressed as a constraint."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING
from typing import ClassVar
from typing import Final

from gemseo.core.discipline import Discipline
from numpy import concatenate
from numpy import eye
from numpy import zeros

if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Mapping

    from gemseo.util.typing import StrKeyMapping

    from gemseo_box_subdivision.subdivisions.box import BoxSubdivision


class BoxConstraint(Discipline):
    r"""The box selected by a one-hot vector, expressed as a constraint.

    Given a :class:`.BoxSubdivision` and the one-hot vectors :math:`\alpha`
    selecting a subdivision per design variable component, this discipline
    computes

    .. math::

        g(x, \alpha) =
        \begin{bmatrix} x - u(\alpha) \\ \ell(\alpha) - x \end{bmatrix} \le 0,

    a single vector-valued function of dimension :math:`2n`,
    whose first :math:`n` components are the upper faces of the box
    and the last :math:`n` components its lower faces.

    Expressing the box as a constraint rather than as bounds of the sub-problem
    design space is what makes the sensitivity of the sub-problem optimum with
    respect to :math:`\alpha` available: the post-optimal analysis of GEMSEO
    propagates the dependency on a parameter through the constraint multipliers
    only, and assumes the bounds to be constant.

    Both :math:`\ell` and :math:`u` are affine in :math:`\alpha`, and :math:`g`
    is linear in :math:`x`, so :math:`g` is jointly convex: the whole
    non-convexity of the problem remains in its original functions.
    """

    DEFAULT_OUTPUT_NAME: Final[str] = "g_box"
    """The default name of the constraint."""

    default_grammar_type: ClassVar[Discipline.GrammarType] = (
        Discipline.GrammarType.SIMPLER
    )

    __subdivision: BoxSubdivision
    """The Cartesian subdivision of the design space."""

    __one_hot_names: dict[str, str]
    """The name of the one-hot variable of each design variable."""

    __output_name: str
    """The name of the constraint."""

    __offsets: dict[str, int]
    """The index of the first component of each design variable."""

    __size: int
    """The total number of design variable components."""

    def __init__(
        self,
        subdivision: BoxSubdivision,
        one_hot_names: Mapping[str, str] = MappingProxyType({}),
        output_name: str = DEFAULT_OUTPUT_NAME,
        name: str = "",
    ) -> None:
        """
        Args:
            subdivision: The Cartesian subdivision of the design space.
            one_hot_names: The name of the one-hot variable of each design
                variable. If empty, suffix the design variable names with
                :attr:`.BoxSubdivision.ONE_HOT_SUFFIX`.
            output_name: The name of the constraint.
        """  # noqa: D205, D212
        super().__init__(name=name)
        self.__subdivision = subdivision
        self.__output_name = output_name
        self.__one_hot_names = subdivision.get_one_hot_names(one_hot_names)

        sizes = subdivision.sizes
        n_subdivisions = subdivision.n_subdivisions
        offset = 0
        self.__offsets = {}
        for variable_name in subdivision.variable_names:
            self.__offsets[variable_name] = offset
            offset += sizes[variable_name]

        self.__size = offset

        input_data = {}
        for variable_name in subdivision.variable_names:
            # The design variable starts at the center of its first subdivision,
            # which is the box selected by the default one-hot value.
            lower_bound = subdivision.get_lower_bounds(variable_name)
            upper_bound = subdivision.get_upper_bounds(variable_name)
            input_data[variable_name] = (lower_bound[:, 0] + upper_bound[:, 0]) / 2.0
            one_hot = zeros((sizes[variable_name], n_subdivisions[variable_name]))
            one_hot[:, 0] = 1.0
            input_data[self.__one_hot_names[variable_name]] = one_hot.ravel()

        self.io.input_grammar.update_from_data(input_data)
        self.io.output_grammar.update_from_data({output_name: zeros(2 * self.__size)})
        self.default_input_data = input_data

    @property
    def one_hot_names(self) -> dict[str, str]:
        """The name of the one-hot variable of each design variable."""
        return dict(self.__one_hot_names)

    @property
    def output_name(self) -> str:
        """The name of the constraint."""
        return self.__output_name

    def _run(self, input_data: StrKeyMapping) -> StrKeyMapping:
        upper_violations = []
        lower_violations = []
        for variable_name in self.__subdivision.variable_names:
            value = input_data[variable_name]
            lower_bound, upper_bound = self.__subdivision.compute_bounds(
                variable_name, input_data[self.__one_hot_names[variable_name]]
            )
            upper_violations.append(value - upper_bound)
            lower_violations.append(lower_bound - value)

        return {self.__output_name: concatenate(upper_violations + lower_violations)}

    def _compute_jacobian(
        self,
        input_names: Iterable[str] = (),
        output_names: Iterable[str] = (),
    ) -> None:
        self._init_jacobian(input_names, output_names)
        subdivision = self.__subdivision
        size = self.__size
        jacobian = self.jac[self.__output_name]
        for variable_name in subdivision.variable_names:
            variable_size = subdivision.sizes[variable_name]
            offset = self.__offsets[variable_name]
            rows = slice(offset, offset + variable_size)
            shifted_rows = slice(size + offset, size + offset + variable_size)

            # The constraint is linear in the design variable:
            # +1 on the upper faces and -1 on the lower ones.
            identity = eye(variable_size)
            derivatives = zeros((2 * size, variable_size))
            derivatives[rows] = identity
            derivatives[shifted_rows] = -identity
            jacobian[variable_name] = derivatives

            # The bounds are affine in the one-hot vector, and the subdivision of
            # a component only depends on that component's block of the one-hot.
            n_subdivisions = subdivision.n_subdivisions[variable_name]
            derivatives = zeros((2 * size, variable_size * n_subdivisions))
            lower_bounds = subdivision.get_lower_bounds(variable_name)
            upper_bounds = subdivision.get_upper_bounds(variable_name)
            for component in range(variable_size):
                columns = slice(
                    component * n_subdivisions, (component + 1) * n_subdivisions
                )
                derivatives[offset + component, columns] = -upper_bounds[component]
                derivatives[size + offset + component, columns] = lower_bounds[
                    component
                ]

            jacobian[self.__one_hot_names[variable_name]] = derivatives
