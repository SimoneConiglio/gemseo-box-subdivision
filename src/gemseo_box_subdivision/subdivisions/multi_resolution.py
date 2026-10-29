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
r"""A subdivision described by one categorical variable per level of refinement.

A :class:`.BoxSubdivision` spends :math:`n m` binaries to reach :math:`m`
subdivisions per component. This one spends :math:`n m L` to reach
:math:`m^L`, by choosing a box with **one categorical variable per level**
instead of one over the whole subdivision: the levels are the digits of the box
index in base :math:`m`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gemseo_bilevel_outer_approximation.algos.design_space.catalogue_design_space import (  # noqa: E501
    CatalogueDesignSpace,
)
from numpy import arange
from numpy import asarray
from numpy import atleast_1d
from numpy import float64
from numpy import ones
from numpy import zeros

from gemseo_box_subdivision.subdivisions.base import BaseSubdivision

if TYPE_CHECKING:
    from collections.abc import Iterable

    from gemseo.algos.design_space import DesignSpace
    from numpy import ndarray


class MultiResolution(BaseSubdivision):
    r"""A subdivision of a design space into :math:`m^L` boxes per component.

    The lower bound of a component is the sum of the fractions of the design
    space that its levels select,

    .. math::

        \ell_j(\alpha) = L_j + \Delta_j \sum_{k=1}^{L} m^{-k} \, d_k(\alpha_j),
        \qquad
        u_j(\alpha) = \ell_j(\alpha) + \Delta_j \, m^{-L},

    with :math:`\Delta_j = U_j - L_j` and :math:`d_k \in \{0, \dots, m-1\}` the
    subdivision selected at level :math:`k`, one-hot encoded.

    Two consequences make this usable where a flat subdivision is not.

    - The **resolution grows as a power while the binaries grow as a product**,
      so a resolution of :math:`1024` over five variables costs :math:`100`
      binaries instead of :math:`5120`. Since the density a budget can support is
      bounded by the binaries of the master and not by the boxes, this is what
      moves that bound.
    - The bounds stay **affine** in the one-hot variables and the width does not
      depend on them at all, so the mapping is bilinear in
      :math:`(\xi, \alpha)` exactly as the one-level mapping is, and the
      post-optimal sensitivity of the ``Benders`` formulation applies unchanged.

    The counterpart is the **model class**: the cuts of the master are linear in
    the one-hot variables, so over the digits they are additive. They can
    represent what a level contributes on its own, and not that the contribution
    of a fine digit depends on the coarse digit it sits inside.
    """

    LEVEL_TEMPLATE: str = "{name}_level_{level}"
    """The template naming the categorical variable of a level."""

    NORMALIZED_SUFFIX: str = "_normalized"
    """The suffix naming the normalized variable of a design variable."""

    ONE_HOT_SUFFIX: str = "_box"
    """The suffix naming the one-hot variable of a categorical variable."""

    def __init__(
        self,
        lower_bounds: dict[str, ndarray],
        upper_bounds: dict[str, ndarray],
        branching: int,
        levels: int,
    ) -> None:
        """
        Args:
            lower_bounds: The lower bound of each design variable.
            upper_bounds: The upper bound of each design variable.
            branching: The number of subdivisions of a component at each level.
            levels: The number of levels.

        Raises:
            ValueError: When the branching or the number of levels is below one,
                or when the bounds do not describe the same variables.
        """  # noqa: D205, D212
        if branching < 2:  # noqa: PLR2004
            msg = f"The branching must be at least two, got {branching}."
            raise ValueError(msg)

        if levels < 1:
            msg = f"The number of levels must be at least one, got {levels}."
            raise ValueError(msg)

        if set(lower_bounds) != set(upper_bounds):
            msg = "The lower and upper bounds must describe the same variables."
            raise ValueError(msg)

        self.__lower_bounds = {
            name: atleast_1d(asarray(bound, dtype=float64))
            for name, bound in lower_bounds.items()
        }
        self.__upper_bounds = {
            name: atleast_1d(asarray(bound, dtype=float64))
            for name, bound in upper_bounds.items()
        }
        self.__branching = branching
        self.__levels = levels
        # What a digit of each level is worth, as a fraction of the range.
        self.__fractions = asarray([
            branching ** -(level + 1) * arange(branching) for level in range(levels)
        ])

    @property
    def variable_names(self) -> tuple[str, ...]:
        """The names of the design variables."""
        return tuple(self.__lower_bounds)

    @property
    def sizes(self) -> dict[str, int]:
        """The size of each design variable."""
        return {name: bound.size for name, bound in self.__lower_bounds.items()}

    @property
    def branching(self) -> int:
        """The number of subdivisions of a component at each level."""
        return self.__branching

    @property
    def levels(self) -> int:
        """The number of levels."""
        return self.__levels

    @property
    def resolution(self) -> int:
        """The number of subdivisions of a component the levels reach."""
        return self.__branching**self.__levels

    @property
    def n_binaries(self) -> int:
        """The number of binaries of the master problem.

        This is :math:`n m L`, against the :math:`n m^L` a
        :class:`.BoxSubdivision` of the same resolution would need.
        """
        return sum(self.sizes.values()) * self.__branching * self.__levels

    @property
    def n_boxes(self) -> int:
        """The number of boxes the levels can select."""
        return self.resolution ** sum(self.sizes.values())

    @property
    def max_step(self) -> int:
        """The radius at which the trust region stops constraining the master.

        The distance of the master counts the one-hot groups a candidate
        changes, and this subdivision has one group per level per component,
        against the one per component of a :class:`.BoxSubdivision`.

        Note:
            As for a flat subdivision, this is **not** the radius to use: it
            marks where the region stops constraining. A radius letting the
            master move a couple of whole variables, that is
            ``2 * levels``, is what the measurements support.
        """
        return sum(self.sizes.values()) * self.__levels

    def get_level_name(self, name: str, level: int) -> str:
        """Return the name of the categorical variable of a level.

        Args:
            name: The name of the design variable.
            level: The level, counted from one.

        Returns:
            The name of the categorical variable.
        """
        return self.LEVEL_TEMPLATE.format(name=name, level=level)

    def get_one_hot_name(self, name: str, level: int) -> str:
        """Return the name of the one-hot variable of a level.

        A categorical variable is registered under the name of its one-hot
        encoding, as :func:`.create_box_design_space` does, so this is the name
        the design space, the master and the mapping all use.

        Args:
            name: The name of the design variable.
            level: The level, counted from one.

        Returns:
            The name of the one-hot variable.
        """
        return f"{self.get_level_name(name, level)}{self.ONE_HOT_SUFFIX}"

    def get_normalized_name(self, name: str) -> str:
        """Return the name of the normalized variable of a design variable.

        Args:
            name: The name of the design variable.

        Returns:
            The name of the normalized variable.
        """
        return f"{name}{self.NORMALIZED_SUFFIX}"

    def get_digit_values(self, level: int) -> ndarray:
        """Return what each digit of a level is worth, as a fraction of a range.

        Args:
            level: The level, counted from one.

        Returns:
            The fraction of the range each subdivision of the level selects.
        """
        return self.__fractions[level - 1]

    def compute_bounds(
        self, name: str, one_hots: Iterable[ndarray]
    ) -> tuple[ndarray, ndarray]:
        """Return the bounds of the box the levels select.

        Args:
            name: The name of the design variable.
            one_hots: The one-hot vector of each level, coarsest first.

        Returns:
            The lower and upper bounds of the box.
        """
        lower_bound = self.__lower_bounds[name]
        width = self.__upper_bounds[name] - lower_bound
        size = lower_bound.size
        fractions = zeros(size)
        for level, one_hot in enumerate(one_hots, start=1):
            selected = asarray(one_hot).reshape(size, self.__branching)
            fractions = fractions + selected @ self.get_digit_values(level)

        lower = lower_bound + width * fractions
        return lower, lower + width / self.resolution

    def locate(self, name: str, value: ndarray) -> list[ndarray]:
        """Return the one-hot vector of each level holding a design value.

        Args:
            name: The name of the design variable.
            value: The design value.

        Returns:
            The one-hot vector of each level, coarsest first.
        """
        lower_bound = self.__lower_bounds[name]
        width = self.__upper_bounds[name] - lower_bound
        size = lower_bound.size
        # The position in the range, as a number in base `branching`.
        remainder = (asarray(value) - lower_bound) / width
        one_hots = []
        for _ in range(self.__levels):
            remainder = remainder * self.__branching
            digit = remainder.astype(int).clip(0, self.__branching - 1)
            remainder = remainder - digit
            one_hot = zeros((size, self.__branching))
            one_hot[arange(size), digit] = 1.0
            one_hots.append(one_hot.ravel())

        return one_hots

    def create_design_space(
        self, design_space: DesignSpace | None = None, value: dict | None = None
    ) -> CatalogueDesignSpace:
        """Return the design space of the master and of the sub-problem.

        The normalized variables of the sub-problem span :math:`[0, 1]`
        whichever box is selected, and each level is a categorical variable
        weighted by ones, so that the distance of the trust region counts the
        digits a candidate changes.

        Args:
            design_space: Unused, the bounds being held by this object.
            value: The design value the levels should start from, by variable
                name. If ``None``, start from the center of the design space.

        Returns:
            The design space.
        """
        del design_space
        space = CatalogueDesignSpace()
        for name in self.variable_names:
            size = self.sizes[name]
            start = (
                0.5 * (self.__lower_bounds[name] + self.__upper_bounds[name])
                if value is None or name not in value
                else asarray(value[name])
            )
            digits = self.locate(name, start)
            for level in range(1, self.__levels + 1):
                selected = digits[level - 1].reshape(size, self.__branching)
                space.add_categorical_variable(
                    self.get_one_hot_name(name, level),
                    value=selected.argmax(axis=1),
                    catalogue=arange(self.__branching),
                    weights=ones(self.__branching),
                )

            space.add_variable(
                self.get_normalized_name(name),
                lower_bound=zeros(size),
                upper_bound=ones(size),
                value=zeros(size) + 0.5,
                size=size,
            )

        return space
