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
"""Multimodal problems used by the benchmarks.

Each problem is a scalar objective with an analytic gradient, over a box whose
bounds are deliberately **asymmetric**: with symmetric bounds the global
minimizer of these classical functions falls on the border or at the center of a
box of a uniform subdivision, which flatters or penalises the box-subdivision
method for a reason that has nothing to do with the method.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Final

from gemseo.core.discipline import Discipline
from numpy import arange
from numpy import array
from numpy import atleast_2d
from numpy import cos
from numpy import e
from numpy import exp
from numpy import ndarray
from numpy import pi
from numpy import prod
from numpy import sin
from numpy import sqrt
from numpy import sum as np_sum
from numpy import zeros

if TYPE_CHECKING:
    from collections.abc import Callable

RASTRIGIN_LOWER_BOUND = -4.1
"""The lower bound of the Rastrigin benchmark."""

RASTRIGIN_UPPER_BOUND = 5.9
"""The upper bound of the Rastrigin benchmark."""


def rastrigin(x: ndarray) -> float:
    """Rastrigin, whose local minima are about one unit apart.

    Args:
        x: The design value.

    Returns:
        The objective value.
    """
    return 10.0 * x.size + float(np_sum(x**2 - 10.0 * cos(2.0 * pi * x)))


def rastrigin_gradient(x: ndarray) -> ndarray:
    """The gradient of :func:`.rastrigin`.

    Args:
        x: The design value.

    Returns:
        The gradient.
    """
    return 2.0 * x + 20.0 * pi * sin(2.0 * pi * x)


def ackley(x: ndarray) -> float:
    """Ackley, a nearly flat landscape with a deep narrow global basin.

    Args:
        x: The design value.

    Returns:
        The objective value.
    """
    n = x.size
    return float(
        -20.0 * exp(-0.2 * sqrt(np_sum(x**2) / n))
        - exp(np_sum(cos(2.0 * pi * x)) / n)
        + 20.0
        + e
    )


def ackley_gradient(x: ndarray) -> ndarray:
    """The gradient of :func:`.ackley`.

    Args:
        x: The design value.

    Returns:
        The gradient.
    """
    n = x.size
    norm = sqrt(np_sum(x**2) / n)
    # The first term is not differentiable at the origin, which is the optimum.
    first = 4.0 * exp(-0.2 * norm) * x / (n * norm) if norm > 1e-12 else zeros(n)
    second = 2.0 * pi * exp(np_sum(cos(2.0 * pi * x)) / n) * sin(2.0 * pi * x) / n
    return first + second


def styblinski_tang(x: ndarray) -> float:
    """Styblinski-Tang, whose optimum is at no remarkable coordinate.

    Args:
        x: The design value.

    Returns:
        The objective value.
    """
    return float(np_sum(x**4 - 16.0 * x**2 + 5.0 * x) / 2.0)


def styblinski_tang_gradient(x: ndarray) -> ndarray:
    """The gradient of :func:`.styblinski_tang`.

    Args:
        x: The design value.

    Returns:
        The gradient.
    """
    return (4.0 * x**3 - 32.0 * x + 5.0) / 2.0


def griewank(x: ndarray) -> float:
    """Griewank, whose many local minima sit on a wide quadratic bowl.

    Args:
        x: The design value.

    Returns:
        The objective value.
    """
    indexes = arange(1, x.size + 1)
    return float(1.0 + np_sum(x**2) / 4000.0 - prod(cos(x / sqrt(indexes))))


def griewank_gradient(x: ndarray) -> ndarray:
    """The gradient of :func:`.griewank`.

    Args:
        x: The design value.

    Returns:
        The gradient.
    """
    indexes = arange(1, x.size + 1)
    cosines = cos(x / sqrt(indexes))
    gradient = zeros(x.size)
    for i in range(x.size):
        others = prod(cosines[arange(x.size) != i])
        gradient[i] = x[i] / 2000.0 + others * sin(x[i] / sqrt(indexes[i])) / sqrt(
            indexes[i]
        )
    return gradient


@dataclass(frozen=True)
class Problem:
    """A multimodal benchmark problem."""

    name: str
    """The name of the problem."""

    objective: Callable[[ndarray], float]
    """The objective."""

    gradient: Callable[[ndarray], ndarray]
    """The gradient of the objective."""

    lower_bound: float
    """The lower bound of every component."""

    upper_bound: float
    """The upper bound of every component."""

    optimum: Callable[[int], float]
    """The global minimum, as a function of the dimension."""


N_MULTIMODAL: Final[int] = 2
"""The number of multimodal variables of :func:`.partly_multimodal`."""


def partly_multimodal(x: ndarray) -> float:
    """Rastrigin on the first variables, a paraboloid on the others.

    The other problems are multimodal in every variable, which is the worst case
    for a subdivision refining only some of them: whatever is left unsubdivided
    keeps several basins inside each box, and the local solve returns the one it
    starts in. This one concentrates the multimodality in
    :data:`.N_MULTIMODAL` variables, which is the case a partial refinement is
    for, and the shape of an industrial problem whose difficulty lies in a few
    parameters.

    Args:
        x: The design value.

    Returns:
        The objective value.
    """
    head, tail = x[:N_MULTIMODAL], x[N_MULTIMODAL:]
    return float(np_sum(10.0 + head**2 - 10.0 * cos(2.0 * pi * head)) + np_sum(tail**2))


def partly_multimodal_gradient(x: ndarray) -> ndarray:
    """The gradient of :func:`.partly_multimodal`.

    Args:
        x: The design value.

    Returns:
        The gradient.
    """
    gradient = 2.0 * x
    head = x[:N_MULTIMODAL]
    gradient[:N_MULTIMODAL] += 20.0 * pi * sin(2.0 * pi * head)
    return gradient


PROBLEMS: dict[str, Problem] = {
    problem.name: problem
    for problem in (
        Problem(
            "rastrigin",
            rastrigin,
            rastrigin_gradient,
            RASTRIGIN_LOWER_BOUND,
            RASTRIGIN_UPPER_BOUND,
            lambda n: 0.0,  # noqa: ARG005
        ),
        Problem(
            "ackley",
            ackley,
            ackley_gradient,
            -28.7,
            34.9,
            lambda n: 0.0,  # noqa: ARG005
        ),
        Problem(
            "styblinski_tang",
            styblinski_tang,
            styblinski_tang_gradient,
            -4.9,
            5.1,
            lambda n: -39.16616570377142 * n,
        ),
        Problem(
            "griewank",
            griewank,
            griewank_gradient,
            -58.1,
            61.9,
            lambda n: 0.0,  # noqa: ARG005
        ),
        Problem(
            "partly_multimodal",
            partly_multimodal,
            partly_multimodal_gradient,
            RASTRIGIN_LOWER_BOUND,
            RASTRIGIN_UPPER_BOUND,
            lambda n: 0.0,  # noqa: ARG005
        ),
    )
}
"""The benchmark problems, by name."""


class Counter:
    """A counter of the calls to an objective and to its gradient.

    The two are counted apart, because a method using the gradient and one that
    does not cannot be compared on the number of objective evaluations alone.
    """

    def __init__(self, problem: Problem) -> None:
        """
        Args:
            problem: The problem to count the calls to.
        """  # noqa: D205, D212
        self.problem = problem
        self.n_objective = 0
        self.n_gradient = 0
        self.best = float("inf")
        self.calls: list[tuple[bool, float]] = []
        """Whether each call was to the gradient, and the best value after it."""

    def objective(self, x: ndarray) -> float:
        """Return the objective value and count the call.

        Args:
            x: The design value.

        Returns:
            The objective value.
        """
        self.n_objective += 1
        value = self.problem.objective(x)
        self.best = min(self.best, value)
        self.calls.append((False, self.best))
        return value

    def gradient(self, x: ndarray) -> ndarray:
        """Return the gradient and count the call.

        Args:
            x: The design value.

        Returns:
            The gradient.
        """
        self.n_gradient += 1
        self.calls.append((True, self.best))
        return self.problem.gradient(x)

    def cost(self, dimension: int, adjoint: bool) -> int:
        """Return the equivalent number of objective evaluations.

        Args:
            dimension: The number of design variables.
            adjoint: Whether the gradient costs one objective evaluation, as an
                adjoint does, rather than ``dimension`` of them, as finite
                differences do.

        Returns:
            The equivalent number of objective evaluations.
        """
        weight = 1 if adjoint else dimension
        return self.n_objective + weight * self.n_gradient

    def history(self, dimension: int, adjoint: bool) -> tuple[float, ...]:
        """Return the best value after each equivalent objective evaluation.

        This is the history a data profile reads, whose value at index ``i`` is
        taken as obtained with ``i + 1`` evaluations, so a gradient spans as
        many entries as it costs.

        Args:
            dimension: The number of design variables.
            adjoint: Whether the gradient costs one objective evaluation.

        Returns:
            The best value after each equivalent evaluation, infinite before the
            first objective evaluation.
        """
        weight = 1 if adjoint else dimension
        history = []
        for is_gradient, best in self.calls:
            history.extend([best] * (weight if is_gradient else 1))

        return tuple(history)


class Objective(Discipline):
    """A GEMSEO discipline wrapping a counted objective."""

    def __init__(self, counter: Counter, dimension: int) -> None:
        """
        Args:
            counter: The counter of the calls.
            dimension: The number of design variables.
        """  # noqa: D205, D212
        super().__init__()
        self._counter = counter
        self.io.input_grammar.update_from_data({"x": zeros(dimension)})
        self.io.output_grammar.update_from_data({"f": zeros(1)})
        self.default_input_data = {"x": zeros(dimension)}

    def _run(self, input_data):  # noqa: ANN001, ANN202
        return {"f": array([self._counter.objective(input_data["x"])])}

    def _compute_jacobian(self, input_names=(), output_names=()) -> None:  # noqa: ANN001
        self._init_jacobian(input_names, output_names)
        self.jac["f"]["x"] = atleast_2d(self._counter.gradient(self.io.data["x"]))


class Rastrigin(Objective):
    """The Rastrigin function, kept for the enumeration benchmark."""

    def __init__(self, size: int = 2) -> None:
        """
        Args:
            size: The number of design variables.
        """  # noqa: D205, D212
        super().__init__(Counter(PROBLEMS["rastrigin"]), size)
        self.size = size

    @property
    def n_executions(self) -> int:
        """The number of evaluations of the objective."""
        return self._counter.n_objective
