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
"""A Cartesian subdivision of a design space."""

from __future__ import annotations

from copy import deepcopy
from types import MappingProxyType
from typing import TYPE_CHECKING
from typing import Final

from numpy import array
from numpy import atleast_1d
from numpy import clip
from numpy import isfinite
from numpy import linspace
from numpy import ndarray
from numpy import searchsorted

from gemseo_box_subdivision.subdivisions.base import BaseSubdivision

if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Mapping

    from gemseo.algos.design_space import DesignSpace


class BoxSubdivision(BaseSubdivision):
    r"""A Cartesian subdivision of a design space.

    Each scalar component of each design variable is split into contiguous
    subdivisions. The Cartesian product of these subdivisions defines the boxes
    in which a sub-problem can be solved.

    The subdivision of a component is described by its bounds,
    so that the box selected by a one-hot vector :math:`\alpha` has bounds

    .. math::

        \ell_j(\alpha) = \sum_k l_{j,k} \alpha_{j,k},
        \qquad
        u_j(\alpha) = \sum_k u_{j,k} \alpha_{j,k},

    which are affine in :math:`\alpha`.
    """

    DEFAULT_BOUND_MARGIN: Final[float] = 1e-4
    """The default relative margin of :meth:`.create_relaxed_design_space`."""

    ONE_HOT_SUFFIX: Final[str] = "_box"
    """The default suffix of the one-hot variable selecting a subdivision."""

    NORMALIZED_SUFFIX: Final[str] = "_normalized"
    """The default suffix of the normalized variable of a box."""

    __lower_bounds: dict[str, ndarray]
    """The lower bounds of the subdivisions, shaped ``(size, n_subdivisions)``."""

    __upper_bounds: dict[str, ndarray]
    """The upper bounds of the subdivisions, shaped ``(size, n_subdivisions)``."""

    def __init__(
        self,
        lower_bounds: Mapping[str, ndarray],
        upper_bounds: Mapping[str, ndarray],
    ) -> None:
        """
        Args:
            lower_bounds: The lower bounds of the subdivisions of each variable,
                shaped ``(size, n_subdivisions)``.
            upper_bounds: The upper bounds of the subdivisions of each variable,
                shaped ``(size, n_subdivisions)``.

        Raises:
            ValueError: If the bounds do not describe a consistent subdivision.
        """  # noqa: D205, D212
        if set(lower_bounds) != set(upper_bounds):
            msg = (
                "The lower and upper bounds must be defined "
                "for the same variables; got "
                f"{sorted(lower_bounds)} and {sorted(upper_bounds)}."
            )
            raise ValueError(msg)

        if not lower_bounds:
            msg = "The subdivision must include at least one variable."
            raise ValueError(msg)

        self.__lower_bounds = {}
        self.__upper_bounds = {}
        for name, lower_bound in lower_bounds.items():
            lower_bound = self.__as_matrix(lower_bound, name, "lower")
            upper_bound = self.__as_matrix(upper_bounds[name], name, "upper")
            if lower_bound.shape != upper_bound.shape:
                msg = (
                    f"The bounds of the subdivisions of {name} must have the same "
                    f"shape; got {lower_bound.shape} and {upper_bound.shape}."
                )
                raise ValueError(msg)

            if (lower_bound >= upper_bound).any():
                msg = (
                    f"The subdivisions of {name} must have a lower bound "
                    "strictly smaller than their upper bound."
                )
                raise ValueError(msg)

            self.__lower_bounds[name] = lower_bound
            self.__upper_bounds[name] = upper_bound

    @staticmethod
    def __as_matrix(bound: ndarray, name: str, kind: str) -> ndarray:
        """Return the bounds of the subdivisions of a variable as a matrix.

        Args:
            bound: The bounds of the subdivisions of the variable.
            name: The name of the variable.
            kind: The kind of bound, either ``"lower"`` or ``"upper"``.

        Returns:
            The bounds, shaped ``(size, n_subdivisions)``.

        Raises:
            ValueError: If the bounds are not a finite matrix.
        """
        matrix = atleast_1d(bound).astype(float)
        if matrix.ndim != 2:
            msg = (
                f"The {kind} bounds of the subdivisions of {name} must be a matrix "
                f"shaped (size, n_subdivisions); got {matrix.ndim} dimension(s)."
            )
            raise ValueError(msg)

        if not isfinite(matrix).all():
            msg = f"The {kind} bounds of the subdivisions of {name} must be finite."
            raise ValueError(msg)

        return matrix

    @classmethod
    def from_design_space(
        cls,
        design_space: DesignSpace,
        n_subdivisions: int | Mapping[str, int],
        variable_names: Iterable[str] = (),
    ) -> BoxSubdivision:
        """Create a uniform subdivision of a design space.

        Args:
            design_space: The design space to subdivide.
            n_subdivisions: The number of subdivisions of every variable,
                or of each variable.
            variable_names: The variables to subdivide.
                If empty, subdivide all the variables of the design space.

        Returns:
            The uniform subdivision of the design space.

        Raises:
            ValueError: If a variable is unknown, has a non-finite bound,
                or has a non-positive number of subdivisions.
        """
        names = tuple(variable_names) or tuple(design_space.variable_names)
        if unknown := set(names) - set(design_space.variable_names):
            msg = (
                "The following variables are not in the design space: "
                f"{sorted(unknown)}."
            )
            raise ValueError(msg)

        lower_bounds = {}
        upper_bounds = {}
        for name in names:
            n = (
                n_subdivisions
                if isinstance(n_subdivisions, int)
                else n_subdivisions[name]
            )
            if n < 1:
                msg = f"The number of subdivisions of {name} must be positive; got {n}."
                raise ValueError(msg)

            lower_bound = design_space.get_lower_bounds([name])
            upper_bound = design_space.get_upper_bounds([name])
            if not (isfinite(lower_bound).all() and isfinite(upper_bound).all()):
                msg = f"The variable {name} must have finite bounds to be subdivided."
                raise ValueError(msg)

            # linspace over the last axis gives the n + 1 breakpoints of each
            # component, from which the n subdivisions are read as consecutive pairs.
            breakpoints = linspace(lower_bound, upper_bound, n + 1, axis=-1)
            lower_bounds[name] = breakpoints[..., :-1]
            upper_bounds[name] = breakpoints[..., 1:]

        return cls(lower_bounds, upper_bounds)

    @property
    def variable_names(self) -> tuple[str, ...]:
        """The names of the subdivided variables."""
        return tuple(self.__lower_bounds)

    @property
    def sizes(self) -> dict[str, int]:
        """The size of each subdivided variable."""
        return {name: bound.shape[0] for name, bound in self.__lower_bounds.items()}

    @property
    def n_subdivisions(self) -> dict[str, int]:
        """The number of subdivisions of each variable."""
        return {name: bound.shape[1] for name, bound in self.__lower_bounds.items()}

    @property
    def n_boxes(self) -> int:
        """The number of boxes of the Cartesian subdivision."""
        n_boxes = 1
        for name, n in self.n_subdivisions.items():
            n_boxes *= n ** self.sizes[name]
        return n_boxes

    @property
    def n_binaries(self) -> int:
        """The number of binary variables encoding the choice of a box.

        This is the size of the master problem, linear in the number of design
        variable components, whereas :attr:`.n_boxes` is exponential in it.
        """
        return sum(self.sizes[name] * n for name, n in self.n_subdivisions.items())

    @property
    def max_step(self) -> int:
        r"""The largest trust-region step of the master, with the default weights.

        The master restricts each of its iterations to a neighbourhood of the
        incumbent box: writing $w_j$ for the weights of the catalogue of a
        component and $\alpha$ for the incumbent, a candidate $\alpha'$ must
        satisfy

        $$
        \sum_{j \,:\, \alpha'_j = \alpha_j} w_j(\alpha)
        \ \ge\ \sum_j w_j(\alpha) - \texttt{max\_step},
        $$

        so the cost of a move is the sum of the weights the **incumbent** holds
        over the components the candidate changes. The constraint never reads
        what those components change *to*, so no weighting of an ordered
        catalogue makes it a proximity; with the weights this package sets, all
        equal, it is the **number of components changed**, which is a distance.

        This property is the largest such distance, the number of components of
        the subdivision, at which the trust region is inactive.

        Note:
            A radius that large is not what works: the master explores better
            when it may change only a couple of components per iteration, see
            [the results](../../algorithm/benchmark.md). This property says where
            the region stops constraining, not what to set.
        """
        return sum(self.sizes.values())

    def get_lower_bounds(self, name: str) -> ndarray:
        """Return the lower bounds of the subdivisions of a variable.

        Args:
            name: The name of the variable.

        Returns:
            The lower bounds, shaped ``(size, n_subdivisions)``.
        """
        return self.__lower_bounds[name]

    def get_upper_bounds(self, name: str) -> ndarray:
        """Return the upper bounds of the subdivisions of a variable.

        Args:
            name: The name of the variable.

        Returns:
            The upper bounds, shaped ``(size, n_subdivisions)``.
        """
        return self.__upper_bounds[name]

    def create_relaxed_design_space(
        self,
        design_space: DesignSpace,
        margin: float = DEFAULT_BOUND_MARGIN,
    ) -> DesignSpace:
        """Return a copy of a design space whose bounds are slightly widened.

        When a box lies against the border of the design space, the face of the
        box and the bound of the design space coincide. Both are then active at
        a sub-problem optimum lying on that face, and the Lagrange multiplier is
        attributed to the bound rather than to the box constraint. The
        sensitivity of the sub-problem optimum with respect to the box selection
        would then be computed as zero for every border box.

        Widening the bounds by a small margin keeps them inactive, so that the
        multiplier is carried by the box constraint. The box itself is still
        enforced, by the constraint, hence the design variables remain in the
        original bounds up to the constraint tolerance.

        Args:
            design_space: The design space to relax.
            margin: The margin, relative to the range of each variable.

        Returns:
            A copy of the design space with widened bounds.

        Raises:
            ValueError: If the margin is negative.
        """
        if margin < 0.0:
            msg = f"The margin must be non-negative; got {margin}."
            raise ValueError(msg)

        relaxed_design_space = deepcopy(design_space)
        for name in self.variable_names:
            lower_bound = relaxed_design_space.get_lower_bounds([name])
            upper_bound = relaxed_design_space.get_upper_bounds([name])
            offset = margin * (upper_bound - lower_bound)
            relaxed_design_space.set_lower_bound(name, lower_bound - offset)
            relaxed_design_space.set_upper_bound(name, upper_bound + offset)

        return relaxed_design_space

    def get_one_hot_names(
        self, overrides: Mapping[str, str] = MappingProxyType({})
    ) -> dict[str, str]:
        """Return the name of the one-hot variable of each subdivided variable.

        Args:
            overrides: The names to use instead of the default ones.

        Returns:
            The name of the one-hot variable of each subdivided variable.
        """
        return {
            name: overrides.get(name, f"{name}{self.ONE_HOT_SUFFIX}")
            for name in self.variable_names
        }

    def locate(self, name: str, value: ndarray) -> ndarray:
        """Return the index of the subdivision containing each component of a value.

        A value lying on the border between two subdivisions is assigned to the
        first of them, and a value outside the original bounds is assigned to the
        closest subdivision.

        Args:
            name: The name of the variable.
            value: The value of the variable.

        Returns:
            The index of the subdivision of each component.
        """
        upper_bounds = self.__upper_bounds[name]
        n_subdivisions = upper_bounds.shape[1]
        indexes = [
            searchsorted(upper_bounds[component], component_value)
            for component, component_value in enumerate(atleast_1d(value))
        ]
        return clip(array(indexes), 0, n_subdivisions - 1)

    def get_normalized_names(
        self, overrides: Mapping[str, str] = MappingProxyType({})
    ) -> dict[str, str]:
        """Return the name of the normalized variable of each subdivided variable.

        Args:
            overrides: The names to use instead of the default ones.

        Returns:
            The name of the normalized variable of each subdivided variable.
        """
        return {
            name: overrides.get(name, f"{name}{self.NORMALIZED_SUFFIX}")
            for name in self.variable_names
        }

    def compute_bounds(self, name: str, one_hot: ndarray) -> tuple[ndarray, ndarray]:
        """Compute the bounds of the box selected by a one-hot vector.

        Args:
            name: The name of the variable.
            one_hot: The flat one-hot vector selecting a subdivision per component.

        Returns:
            The lower and upper bounds of the selected box.
        """
        weights = one_hot.reshape(self.sizes[name], self.n_subdivisions[name])
        return (
            (self.__lower_bounds[name] * weights).sum(axis=1),
            (self.__upper_bounds[name] * weights).sum(axis=1),
        )
