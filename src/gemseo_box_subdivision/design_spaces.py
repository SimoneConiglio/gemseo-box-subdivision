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
"""The design space of a box-subdivided problem."""

from __future__ import annotations

from copy import deepcopy
from itertools import product
from types import MappingProxyType
from typing import TYPE_CHECKING
from typing import Final

from gemseo_bilevel_outer_approximation.algos.design_space.catalogue_design_space import (  # noqa: E501
    CatalogueDesignSpace,
)
from numpy import full
from numpy import ones
from numpy import zeros

from gemseo_box_subdivision.subdivisions.box import BoxSubdivision

if TYPE_CHECKING:
    from collections.abc import Mapping

    from gemseo.space import DesignSpace
    from numpy import ndarray

DEFAULT_MAX_BOXES: Final[int] = 100_000
"""The default limit on the number of boxes that :func:`.create_box_samples` builds."""


def create_box_design_space(
    subdivision: BoxSubdivision,
    design_space: DesignSpace,
    margin: float = BoxSubdivision.DEFAULT_BOUND_MARGIN,
    one_hot_names: Mapping[str, str] = MappingProxyType({}),
    weights: Mapping[str, ndarray] = MappingProxyType({}),
) -> CatalogueDesignSpace:
    """Create the design space of a box-subdivided problem.

    The returned design space gathers the variables of both levels:

    - the variables of the original problem, whose bounds are widened by
      :meth:`.BoxSubdivision.create_relaxed_design_space`, and which are solved
      for in the sub-problem;
    - one categorical variable per subdivided variable, selecting a subdivision
      per component, which the main problem decides.

    The ``Benders`` formulation splits the two levels apart on its own, by
    keeping the categorical variables in the main problem.

    The catalogue of a subdivided variable is the range of its subdivision
    indexes, and every subdivision is weighed alike, so that the distance the
    main problem measures is the **number of components** a candidate box
    changes. Leaving the weights at the catalogue values, which is what a
    catalogue design space does on its own, would not express a proximity: the
    constraint charges the weights the *incumbent* holds on the components a
    candidate changes and never reads what it changes them to, so leaving the
    first subdivision would be free and leaving the last would cost the range,
    however near the candidate is.

    Args:
        subdivision: The Cartesian subdivision of the design space.
        design_space: The design space of the original problem.
        margin: The relative margin applied to the bounds of the subdivided
            variables, so that a box lying against a bound keeps the multiplier
            of its face.
        one_hot_names: The name of the one-hot variable of each subdivided
            variable. If empty, suffix the design variable names with
            :attr:`.BoxSubdivision.ONE_HOT_SUFFIX`.
        weights: The weights of the subdivisions of each variable, used by the
            main problem to measure the distance between two boxes.
            If empty, weigh every subdivision alike, so that the distance is the
            number of components a candidate box changes.

    Returns:
        The design space of the box-subdivided problem.

    Raises:
        ValueError: If a subdivided variable is not in the design space.
    """
    if unknown := set(subdivision.variable_names) - set(design_space.variables):
        msg = f"The following variables are not in the design space: {sorted(unknown)}."
        raise ValueError(msg)

    relaxed_design_space = subdivision.create_relaxed_design_space(
        design_space, margin=margin
    )
    box_design_space = CatalogueDesignSpace(name=design_space.name)
    box_design_space.extend(relaxed_design_space)
    _add_categorical_variables(
        box_design_space, subdivision, design_space, one_hot_names, weights
    )
    return box_design_space


def _add_categorical_variables(
    box_design_space: CatalogueDesignSpace,
    subdivision: BoxSubdivision,
    design_space: DesignSpace,
    one_hot_names: Mapping[str, str],
    weights: Mapping[str, ndarray],
) -> None:
    """Add one categorical variable per subdivided variable.

    The initial box of a variable is the one containing its initial value.

    Args:
        box_design_space: The design space to add the categorical variables to.
        subdivision: The Cartesian subdivision of the design space.
        design_space: The design space of the original problem.
        one_hot_names: The name of the one-hot variable of each subdivided
            variable.
        weights: The weights of the subdivisions of each variable.
    """
    sizes = subdivision.sizes
    n_subdivisions = subdivision.n_subdivisions
    current_value = design_space.get_current_value(as_dict=True)
    for variable_name, one_hot_name in subdivision.get_one_hot_names(
        one_hot_names
    ).items():
        value = current_value.get(variable_name)
        indexes = (
            subdivision.locate(variable_name, value)
            if value is not None
            else [0] * sizes[variable_name]
        )
        box_design_space.add_categorical_variable(
            one_hot_name,
            [int(index) for index in indexes],
            list(range(n_subdivisions[variable_name])),
            weights=weights.get(variable_name, ones(n_subdivisions[variable_name])),
        )


def create_normalized_box_design_space(
    subdivision: BoxSubdivision,
    design_space: DesignSpace,
    one_hot_names: Mapping[str, str] = MappingProxyType({}),
    normalized_names: Mapping[str, str] = MappingProxyType({}),
    weights: Mapping[str, ndarray] = MappingProxyType({}),
) -> CatalogueDesignSpace:
    """Create the design space of a box-subdivided problem in normalized variables.

    This is the counterpart of :func:`.create_box_design_space` for the
    formulation based on :class:`.BoxMapping`: a subdivided variable is replaced
    by its normalized variable, bounded by 0 and 1 whatever the box, and starting
    at the center of the box. A variable that is not subdivided is kept as is.

    Since the bounds of the sub-problem no longer depend on the box, this design
    space needs neither the margin of :func:`.create_box_design_space` nor a
    scenario adapter placing the starting point inside the box.

    Args:
        subdivision: The Cartesian subdivision of the design space.
        design_space: The design space of the original problem.
        one_hot_names: The name of the one-hot variable of each subdivided
            variable. If empty, suffix the design variable names with
            :attr:`.BoxSubdivision.ONE_HOT_SUFFIX`.
        normalized_names: The name of the normalized variable of each subdivided
            variable. If empty, suffix the design variable names with
            :attr:`.BoxSubdivision.NORMALIZED_SUFFIX`.
        weights: The weights of the subdivisions of each variable, used by the
            main problem to measure the distance between two boxes.
            If empty, weigh every subdivision alike, so that the distance is the
            number of components a candidate box changes.

    Returns:
        The design space of the box-subdivided problem in normalized variables.

    Raises:
        ValueError: If a subdivided variable is not in the design space.
    """
    if unknown := set(subdivision.variable_names) - set(design_space.variables):
        msg = f"The following variables are not in the design space: {sorted(unknown)}."
        raise ValueError(msg)

    box_design_space = CatalogueDesignSpace(name=design_space.name)
    kept_names = [
        name
        for name in design_space.variables
        if name not in subdivision.variable_names
    ]
    if kept_names:
        box_design_space.extend(deepcopy(design_space).filter(kept_names))

    sizes = subdivision.sizes
    for variable_name, normalized_name in subdivision.get_normalized_names(
        normalized_names
    ).items():
        size = sizes[variable_name]
        box_design_space.add_variable(
            normalized_name,
            lower_bound=zeros(size),
            upper_bound=ones(size),
            value=full(size, 0.5),
            size=size,
        )

    _add_categorical_variables(
        box_design_space, subdivision, design_space, one_hot_names, weights
    )
    return box_design_space


def create_box_samples(
    subdivision: BoxSubdivision,
    one_hot_names: Mapping[str, str] = MappingProxyType({}),
    max_boxes: int = DEFAULT_MAX_BOXES,
) -> ndarray:
    """Return the one-hot vectors of every box of a subdivision.

    Passing these samples to the ``CustomDOE`` driver of the main problem solves
    the sub-problem of every box. This is the reference against which the outer
    approximation has to be compared: it is exhaustive over the boxes, and it is
    embarrassingly parallel, so the outer approximation is only worth its
    complexity if it solves substantially fewer sub-problems.

    Args:
        subdivision: The Cartesian subdivision of the design space.
        one_hot_names: The name of the one-hot variable of each subdivided
            variable, used to order the columns as in the design space.
        max_boxes: The maximum number of boxes to enumerate.

    Returns:
        The one-hot vectors, shaped ``(n_boxes, n_binaries)``.

    Raises:
        ValueError: If the subdivision has more boxes than ``max_boxes``.
    """
    n_boxes = subdivision.n_boxes
    if n_boxes > max_boxes:
        msg = (
            f"The subdivision has {n_boxes} boxes, more than the maximum of "
            f"{max_boxes}; enumerating them is not tractable."
        )
        raise ValueError(msg)

    names = list(subdivision.get_one_hot_names(one_hot_names))
    sizes = subdivision.sizes
    n_subdivisions = subdivision.n_subdivisions
    # One choice per component, ordered as the one-hot blocks of the design space.
    components = [
        (name, component) for name in names for component in range(sizes[name])
    ]
    offsets = {}
    offset = 0
    for name in names:
        offsets[name] = offset
        offset += sizes[name] * n_subdivisions[name]

    samples = zeros((n_boxes, offset))
    ranges = [range(n_subdivisions[name]) for name, _ in components]
    for row, indexes in enumerate(product(*ranges)):
        for (name, component), index in zip(components, indexes, strict=True):
            column = offsets[name] + component * n_subdivisions[name] + index
            samples[row, column] = 1.0

    return samples
