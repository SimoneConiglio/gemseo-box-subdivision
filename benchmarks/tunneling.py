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
r"""The classic tunneling method, a deterministic sequential global baseline.

The method of Levy and Montalvo (1985) alternates two phases:

- a **minimization** phase, a local solution from the current point, giving a
  local minimizer :math:`x^*` and its value :math:`f^*`;
- a **tunneling** phase, which looks for a point :math:`x \neq x^*` of the
  design space with :math:`f(x) \le f^*`, as a non-positive value of the
  tunneling function

  .. math::

     T(x) = \frac{f(x) - f^*}{\left[(x - x^*)^T (x - x^*)\right]^{\lambda^*}
            \prod_i \left[(x - x_m^i)^T (x - x_m^i)\right]^{\lambda_m}},

  minimized by the same gradient-based solver from points perturbed around
  :math:`x^*`. The pole at :math:`x^*` removes the zero of the numerator there;
  when the search converges to a stationary point :math:`x_m` with
  :math:`T > 0`, a *mobile* pole is placed at it and the search starts again.

A point with :math:`T \le 0` starts the next minimization phase. The sequence
of local minima is therefore non-increasing, the *generalized descent* property
of the method. The run stops when its budget is spent or when every tunneling
attempt from the current minimizer has failed, which is the method's own
stopping rule.

Every setting is fixed across problems; see :data:`.SETTINGS` for each value
and where it comes from.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from gemseo.algos.design_space import DesignSpace
from gemseo.algos.opt.factory import OptimizationLibraryFactory
from gemseo.algos.optimization_problem import OptimizationProblem
from gemseo.core.mdo_functions.mdo_function import MDOFunction
from numpy import array_equal
from numpy import clip
from numpy import full
from numpy import ndarray
from numpy import zeros
from numpy.linalg import norm
from numpy.random import default_rng

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Sequence

    from benchmarks.problems import Counter


@dataclass(frozen=True)
class TunnelingSettings:
    """The settings of the tunneling method, the same on every problem."""

    initial_strength: float = 1.0
    r"""The initial strength :math:`\lambda^*` of the pole at the minimizer.

    One is the smallest strength removing the zero of :math:`f - f^*` at a
    non-degenerate minimizer, where it vanishes quadratically, which is the
    reason given by Levy and Montalvo (1985) for a pole of that order.
    """

    strength_increment: float = 0.1
    r"""The increment of :math:`\lambda^*` until the tunneling function descends
    away from the minimizer at the starting point of a tunneling search.

    The adaptive increase of the strength in steps of a tenth follows Levy and
    Montalvo (1985); it costs no evaluation, since the objective and its
    gradient at the starting point do not depend on the strength.
    """

    max_strength: float = 10.0
    """The strength at which the increase stops, a safeguard chosen here."""

    mobile_strength: float = 1.0
    r"""The strength :math:`\lambda_m` of a mobile pole, of order one like the
    pole at the minimizer (Levy and Montalvo, 1985)."""

    perturbation: float = 0.01
    """The distance of a tunneling starting point from the minimizer (or from a
    mobile pole), as a fraction of the range of each variable.

    The method only needs a small perturbation, the pole doing the rest; this
    relative value, one tenth of the Rastrigin basin width on its benchmark, is
    chosen here and was not tuned.
    """

    attempts_per_variable: int = 2
    """The number of tunneling searches, along random directions, from one
    minimizer before declaring it global, per variable; chosen here."""

    mobile_poles_per_variable: int = 1
    """The number of mobile poles placed in one tunneling search before it is
    abandoned, per variable; chosen here."""

    max_iter: int = 1000
    """The iteration limit of each local solution, SLSQP's default in GEMSEO."""


SETTINGS = TunnelingSettings()
"""The settings of every run."""

MIN_SQUARED_DISTANCE = 1e-24
"""The squared distance to a pole below which it is taken as this distance."""


def tunneling_function(
    value: float,
    gradient: ndarray,
    x: ndarray,
    x_star: ndarray,
    f_star: float,
    strength: float,
    poles: Sequence[tuple[ndarray, float]] = (),
) -> tuple[float, ndarray]:
    r"""Return the tunneling function and its gradient.

    With
    :math:`D(x) = \|x - x^*\|^{2\lambda^*} \prod_i \|x - x_m^i\|^{2\lambda_i}`,
    :math:`T = (f - f^*) / D` and
    :math:`\nabla T = \left(\nabla f - (f - f^*) \nabla \ln D\right) / D`,
    where :math:`\nabla \ln D = \sum_j 2 \lambda_j (x - x_j) / \|x - x_j\|^2`.

    Args:
        value: The objective at ``x``.
        gradient: The gradient of the objective at ``x``.
        x: The design value.
        x_star: The current minimizer.
        f_star: The current minimum.
        strength: The strength of the pole at ``x_star``.
        poles: The mobile poles, as positions and strengths.

    Returns:
        The tunneling function and its gradient.
    """
    denominator = 1.0
    log_gradient = zeros(x.size)
    for position, power in ((x_star, strength), *poles):
        difference = x - position
        # A pole is never evaluated on purpose, but SLSQP may step onto one
        # held on a bound, where the function is infinite.
        squared = max(float(difference @ difference), MIN_SQUARED_DISTANCE)
        denominator *= squared**power
        log_gradient += 2.0 * power * difference / squared

    excess = value - f_star
    return excess / denominator, (gradient - excess * log_gradient) / denominator


class LowerPointFoundError(Exception):
    """Raised by a tunneling search as soon as it finds a point below the level.

    Attributes:
        x: The point found.
    """

    def __init__(self, x: ndarray) -> None:
        """
        Args:
            x: The point found.
        """  # noqa: D205, D212
        super().__init__()
        self.x = x


class _CachedObjective:
    """The counted objective and gradient, evaluated once per point.

    The tunneling function needs the objective at every point its gradient is
    asked at, and SLSQP asks both at the same points, so that the objective is
    kept to be charged once.
    """

    def __init__(self, counter: Counter) -> None:
        """
        Args:
            counter: The counter of the calls, which may stop the run.
        """  # noqa: D205, D212
        self.__counter = counter
        self.__value: tuple[ndarray, float] | None = None
        self.__gradient: tuple[ndarray, ndarray] | None = None

    def value(self, x: ndarray) -> float:
        """Return the objective, evaluated if not at the last point.

        Args:
            x: The design value.

        Returns:
            The objective value.
        """
        if self.__value is None or not array_equal(self.__value[0], x):
            self.__value = (x.copy(), self.__counter.objective(x))
        return self.__value[1]

    def gradient(self, x: ndarray) -> ndarray:
        """Return the gradient, evaluated if not at the last point.

        Args:
            x: The design value.

        Returns:
            The gradient.
        """
        if self.__gradient is None or not array_equal(self.__gradient[0], x):
            self.__gradient = (x.copy(), self.__counter.gradient(x))
        return self.__gradient[1]


def _solve(
    lower: float,
    upper: float,
    start: ndarray,
    function: Callable[[ndarray], float],
    jacobian: Callable[[ndarray], ndarray],
    max_iter: int,
) -> tuple[ndarray, float]:
    """Solve a bound-constrained problem with GEMSEO's SLSQP from a point.

    Args:
        lower: The lower bound of every component.
        upper: The upper bound of every component.
        start: The starting point.
        function: The function to minimize.
        jacobian: Its gradient.
        max_iter: The iteration limit.

    Returns:
        The solution and the value of the function there.
    """
    design_space = DesignSpace()
    design_space.add_variable(
        "x", size=start.size, lower_bound=lower, upper_bound=upper, value=start
    )
    problem = OptimizationProblem(design_space)
    problem.objective = MDOFunction(function, "f", jac=jacobian)
    result = OptimizationLibraryFactory().execute(
        problem, algo_name="SLSQP", max_iter=max_iter
    )
    return result.x_opt, float(result.f_opt)


def tunnel(
    counter: Counter,
    dimension: int,
    lower: float,
    upper: float,
    start: ndarray,
    seed: int,
    settings: TunnelingSettings = SETTINGS,
) -> list[tuple[ndarray, float]]:
    """Run the tunneling method until it stops on its own or on the counter.

    Args:
        counter: The counter of the calls, which may stop the run by raising.
        dimension: The number of design variables.
        lower: The lower bound of every component.
        upper: The upper bound of every component.
        start: The starting point.
        seed: The seed of the directions of the tunneling searches.
        settings: The settings of the method.

    Returns:
        The local minimizers of the successive minimization phases, with their
        values, if the method stops on its own; the counter raising otherwise.
    """
    cached = _CachedObjective(counter)
    rng = default_rng(seed)
    radius = settings.perturbation * (upper - lower)
    lower_bounds = full(dimension, lower)
    upper_bounds = full(dimension, upper)

    def perturbed(center: ndarray) -> ndarray:
        """Return a point at the perturbation radius in a random direction.

        A component leaving the bounds is reflected into them, rather than
        clipped, so that a center on a bound is never returned unchanged.
        """
        direction = rng.standard_normal(dimension)
        step = radius * direction / norm(direction)
        point = center + step
        outside = (point < lower_bounds) | (point > upper_bounds)
        point[outside] = center[outside] - step[outside]
        return clip(point, lower_bounds, upper_bounds)

    minima = []
    x = start
    while True:
        # Minimization phase.
        x_star, f_star = _solve(
            lower, upper, x, cached.value, cached.gradient, settings.max_iter
        )
        minima.append((x_star, f_star))

        # Tunneling phase.
        try:
            for _ in range(settings.attempts_per_variable * dimension):
                _tunneling_search(
                    cached,
                    lower,
                    upper,
                    x_star,
                    f_star,
                    perturbed,
                    settings.mobile_poles_per_variable * dimension,
                    settings,
                )
        except LowerPointFoundError as found:
            x = found.x
        else:
            return minima


def _tunneling_search(
    cached: _CachedObjective,
    lower: float,
    upper: float,
    x_star: ndarray,
    f_star: float,
    perturbed: Callable[[ndarray], ndarray],
    max_poles: int,
    settings: TunnelingSettings,
) -> None:
    """Search for a point below the level of the minimizer from a perturbation.

    Args:
        cached: The counted objective and gradient.
        lower: The lower bound of every component.
        upper: The upper bound of every component.
        x_star: The current minimizer.
        f_star: The current minimum.
        perturbed: The point perturbed around a given one.
        max_poles: The number of mobile poles before the search is abandoned.
        settings: The settings of the method.

    Raises:
        LowerPointFoundError: When a point with ``f < f_star`` is evaluated.
    """
    start = perturbed(x_star)
    while array_equal(start, x_star):
        start = perturbed(x_star)

    # The strength of the pole at the minimizer is raised until the tunneling
    # function descends away from it at the starting point.
    value = cached.value(start)
    if value < f_star:
        raise LowerPointFoundError(start)

    gradient = cached.gradient(start)
    strength = settings.initial_strength
    while strength < settings.max_strength:
        _, slope = tunneling_function(value, gradient, start, x_star, f_star, strength)
        if slope @ (start - x_star) < 0.0:
            break
        strength += settings.strength_increment

    poles: list[tuple[ndarray, float]] = []

    def function(x: ndarray) -> float:
        value = cached.value(x)
        if value < f_star:
            raise LowerPointFoundError(x.copy())
        return tunneling_function(
            value, zeros(x.size), x, x_star, f_star, strength, poles
        )[0]

    def jacobian(x: ndarray) -> ndarray:
        return tunneling_function(
            cached.value(x), cached.gradient(x), x, x_star, f_star, strength, poles
        )[1]

    for _ in range(max_poles + 1):
        x_m, _ = _solve(lower, upper, start, function, jacobian, settings.max_iter)
        # A stationary point of the tunneling function above the level: a
        # mobile pole there, and the search starts again next to it.
        poles.append((x_m, settings.mobile_strength))
        start = perturbed(x_m)
