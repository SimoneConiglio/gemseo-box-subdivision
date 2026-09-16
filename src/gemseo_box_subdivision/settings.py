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
r"""The settings of a box-subdivision run, in the units the method measures.

The master of the outer approximation takes a dozen settings, several of which
are coupled: two mechanisms that must not be combined, a trust-region radius
whose unit is not obvious, and a convexity margin in the units of the objective.
This module names them in the terms the methodology uses and rejects the
combinations that measure nothing.

The convexity margin is the one with no value that transfers between problems,
and :attr:`.BoxSubdivisionSettings.convexity_sweep` is how a run avoids choosing
it; see :mod:`~gemseo_box_subdivision.convexity_sweep`.

The two levels are solved by two algorithms, and both are settings like the
rest: :attr:`.BoxSubdivisionSettings.master_algo_name` and
:attr:`.BoxSubdivisionSettings.sub_problem_algo_name` name them, and
:attr:`.BoxSubdivisionSettings.master_algo_settings` and
:attr:`.BoxSubdivisionSettings.sub_problem_algo_settings` carry whatever else
each one takes. The defaults are the pair the benchmark measures, the
outer-approximation master over SLSQP; naming another algorithm is checked
against what that algorithm declares, so a setting the chosen algorithm does not
have is refused when the settings are built rather than when the run starts.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING
from typing import Any
from typing import ClassVar
from warnings import warn

from gemseo.algos.opt.factory import OptimizationLibraryFactory

if TYPE_CHECKING:
    from collections.abc import Mapping

    from gemseo.algos.base_algorithm_settings import BaseAlgorithmSettings

    from gemseo_box_subdivision.convexity_sweep import ConvexitySweep
    from gemseo_box_subdivision.convexity_sweep import ConvexitySweepSettings

TRUST_REGION_RADIUS: int = 2
"""The default radius of the trust region, in components changed.

A radius of two is what the measurements support, and it is far from the radius
at which the region stops constraining. Letting the master change every component
at once is markedly worse, and removing the region is worse still.
"""

CONVEXITY_MARGIN: float = 100.0
"""The default convexity margin of the adaptive repair.

This is an **absolute** quantity in the units of the objective, so the default
only suits an objective of the scale of the benchmark. It has to be set to the
order of the variation of the objective over the design space.
"""

MASTER_ALGO_NAME: str = "BILEVEL_MASTER_OUTER_APPROXIMATION"
"""The default algorithm solving the master problem.

The master decides which box to look into, so it is the outer approximation
itself rather than an ordinary optimizer: it has to be one of the algorithms
taking the settings :meth:`.BoxSubdivisionSettings.to_master_settings`
translates, which the plugin ``gemseo-bilevel-outer-approximation`` provides.
"""

SUB_PROBLEM_ALGO_NAME: str = "SLSQP"
"""The default algorithm solving each sub-problem inside its box.

A box is a continuous problem with bounds, and every result reported was measured
with SLSQP over it. A derivative-free solver is a legitimate choice for an
objective whose gradient is unavailable or noisy, but nothing here measures one.
"""


@dataclass
class BoxSubdivisionSettings:
    r"""The settings of a box-subdivision run.

    The defaults are the configuration the benchmark supports: the adaptive
    repair of the cut slopes, four probe points, a trust region of two
    components, and the outer-approximation master over SLSQP.

    Two of these settings decide whether a run works at all, and neither has a
    default that transfers between problems:

    ``convexity_margin``
        subtracted from an objective difference, so it is absolute and in the
        units of *your* objective. Start from the variation of the objective
        over the design space. It crosses a threshold and then saturates, so
        erring high costs sub-problems rather than quality.

    ``trust_region_radius``
        the number of components a candidate box may change. Keep it small.

    The algorithm of each level, and any setting of it this class does not name,
    are settings of their own: see ``master_algo_name``,
    ``master_algo_settings``, ``sub_problem_algo_name`` and
    ``sub_problem_algo_settings``.
    """

    MECHANISMS: ClassVar[tuple[str, ...]] = ("adaptive", "convexification")
    """The two mechanisms keeping the cuts usable on a non-convex problem."""

    mechanism: str = "adaptive"
    r"""How the master keeps its cuts usable, ``"adaptive"`` or
    ``"convexification"``.

    They rest on different arguments and are **not** combined: the adaptive
    repair fixes the slope of each cut against the boxes already solved, while
    the convexification adds a convex term whose constant, once it dominates the
    concavity of the relaxation, makes the outer approximation convergent.
    Measuring the two together measures neither.
    """

    convexity_margin: float = CONVEXITY_MARGIN
    """The convexity margin of the adaptive repair, in the units of the objective."""

    convexification_constant: float = CONVEXITY_MARGIN
    """The constant of the convexification, in the units of the objective."""

    convexity_sweep: ConvexitySweepSettings | None = None
    """How to sweep the convexity setting, instead of calibrating one value.

    The two settings above are the ones that do not transfer between problems.
    Rather than choosing either, the master can probe a **ladder** of values per
    iteration, the way it already probes a ladder of trust-region radii, and
    redeploy at a higher rung every probe that proposes no new box. The user then
    supplies an upper bound and a number of points, or nothing at all: see
    :class:`.ConvexitySweepSettings`.

    Setting this asks for the sweep where the master supports it, which today is
    the stub of ``benchmarks/convexity_sweep.py`` rather than the released
    master. Where it does not, :meth:`.to_master_settings` falls back to the
    **top rung**, which is the conservative end of the ladder and the one the
    tuning says errs safely for the adaptive repair.
    """

    trust_region_radius: int = TRUST_REGION_RADIUS
    """The radius of the trust region of the master, in components changed."""

    n_parallel_points: int = 4
    """The number of trust-region radii the master probes per iteration."""

    max_iter: int = 80
    """The number of iterations of the master, not of the sub-problems."""

    sub_problem_max_iter: int = 40
    """The number of iterations of each sub-problem."""

    tolerance: float = 1e-4
    """The tolerance on the upper bound of the master."""

    options: Mapping[str, Any] = field(default_factory=dict)
    """Any other setting of the master, passed through unchanged.

    .. deprecated:: 0.2.0
        Use :attr:`.master_algo_settings`, which says which of the two levels it
        configures. Both may be given, in which case
        :attr:`.master_algo_settings` wins.
    """

    master_algo_name: str = MASTER_ALGO_NAME
    """The name of the algorithm solving the master problem.

    It has to take the settings :meth:`.to_master_settings` translates, which the
    two outer-approximation algorithms of ``gemseo-bilevel-outer-approximation``
    do; an algorithm missing any of them is refused here rather than at
    execution. Changing it changes the method, not merely its tuning.
    """

    master_algo_settings: Mapping[str, Any] = field(default_factory=dict)
    """Any other setting of the master, passed through unchanged.

    These win over the settings this class translates, so a setting named both
    here and by the class takes the value given here.
    """

    sub_problem_algo_name: str = SUB_PROBLEM_ALGO_NAME
    """The name of the algorithm solving each sub-problem inside its box.

    Any GEMSEO optimizer, its name as the library factory knows it. The
    sub-problem is continuous and bounded, which is what
    :attr:`.SUB_PROBLEM_ALGO_NAME` suits; a solver returning a point far from a
    local optimum of its box leaves the cut of that box wrong, rather than merely
    loose.
    """

    sub_problem_algo_settings: Mapping[str, Any] = field(default_factory=dict)
    """Any other setting of the sub-problem solver, passed through unchanged.

    These win over ``sub_problem_max_iter``, which is the ``max_iter`` of the
    solver under its own name.
    """

    def __post_init__(self) -> None:
        """Check the settings.

        Raises:
            ValueError: When the mechanism is unknown, when a count is not
                positive, when either algorithm is unknown, when an algorithm does
                not take a setting it is given, or when the settings of the
                sub-problem solver select another algorithm.
        """
        if self.mechanism not in self.MECHANISMS:
            msg = (
                f"The mechanism must be one of {list(self.MECHANISMS)}; "
                f"got {self.mechanism!r}."
            )
            raise ValueError(msg)

        for name in ("trust_region_radius", "n_parallel_points", "max_iter"):
            if getattr(self, name) < 1:
                msg = f"{name} must be positive; got {getattr(self, name)}."
                raise ValueError(msg)

        if self.options:
            warn(
                "The setting 'options' is deprecated; "
                "use 'master_algo_settings' instead.",
                FutureWarning,
                stacklevel=2,
            )
            self.master_algo_settings = {**self.options, **self.master_algo_settings}

        _check_settings_names(
            self.master_algo_name, self.to_master_settings(), "master problem"
        )
        _check_settings_names(
            self.sub_problem_algo_name, self.to_sub_problem_settings(), "sub-problems"
        )
        _check_sub_problem_settings_model(self.sub_problem_algo_name)

    @property
    def convexity_setting_name(self) -> str:
        """The name of the master setting the mechanism calibrates.

        The adaptive repair reads the convexity margin under ``"min_dfk"``, the
        pure convexification its constant under ``"convexification_constant"``.
        This is what a sweep of the convexity varies, and naming it here keeps
        the sweep from having to know which mechanism is active.
        """
        if self.mechanism == "adaptive":
            return "min_dfk"

        return "convexification_constant"

    @property
    def convexity_value(self) -> float:
        """The value of the convexity setting the mechanism calibrates."""
        if self.mechanism == "adaptive":
            return self.convexity_margin

        return self.convexification_constant

    def create_convexity_sweep(
        self, observed_scale: float = 0.0
    ) -> ConvexitySweep | None:
        """Return the sweep of the convexity setting, if one is asked for.

        Args:
            observed_scale: The variation of the objective over the boxes
                already solved, which is the upper bound of a sweep that was
                given none. See :func:`.objective_scale`.

        Returns:
            The sweep, or ``None`` when none is asked for, or when its upper
            bound is neither given nor observed yet.
        """
        if self.convexity_sweep is None:
            return None

        return self.convexity_sweep.create_sweep(observed_scale)

    def to_master_settings(self, radius: int | None = None) -> dict[str, Any]:
        """Return the settings of the master problem.

        The mechanism decides which of the two constants is passed and which is
        switched off, so that the two can never be active at once.

        A sweep of the convexity is the master's own, under the settings
        ``convexity_sweep_points`` and ``convexity_sweep_max``, and
        :attr:`.convexity_sweep` is turned into those here. The value passed to
        the mechanism is then the **top rung**, which is what the master uses in
        the first iterations, before it has solved enough boxes to have a ladder
        at all; for a sweep whose bound is read off the objective, and which
        therefore has no ladder offline, it is the value of the mechanism.

        Against a master that predates the sweep, see
        :data:`.MASTER_SWEEPS_CONVEXITY`, those two settings would be rejected
        and are not passed. What is left is the top rung, the conservative end:
        the tuning says an over-large margin costs sub-problems rather than
        quality, so a run that loses the sweep loses the cheap rungs rather than
        the result. Driving such a master is what the stub of
        ``benchmarks/convexity_sweep.py`` is for.

        Asking for a sweep also keeps :attr:`.n_parallel_points` under the pure
        convexification, which otherwise probes a single point. A probe per rung
        is what makes an iteration span the ladder, so a sweep of a single probe
        is not one.

        Args:
            radius: The radius of the trust region, overriding
                :attr:`.trust_region_radius`. Used by the encodings whose
                distance counts something other than design variables.

        Returns:
            The settings of the master problem.
        """
        adaptive = self.mechanism == "adaptive"
        swept = self.convexity_sweep is not None
        value = self.convexity_value
        ladder = self.create_convexity_sweep()
        if ladder is not None:
            value = ladder.max_value

        settings = {
            "max_iter": self.max_iter,
            "ub_tol": self.tolerance,
            "adapt": adaptive,
            "min_dfk": value if adaptive else 0.0,
            "convexification_constant": 0.0 if adaptive else value,
            "number_of_parallel_points": (
                self.n_parallel_points if adaptive or swept else 1
            ),
            "max_step": self.trust_region_radius if radius is None else radius,
        }
        if swept:
            settings.update(self.convexity_sweep.to_master_settings())

        settings.update(self.master_algo_settings)
        return settings

    def to_sub_problem_settings(self) -> dict[str, Any]:
        """Return the settings of a sub-problem.

        Returns:
            The settings of the algorithm solving a sub-problem inside its box.
        """
        settings = {"max_iter": self.sub_problem_max_iter}
        settings.update(self.sub_problem_algo_settings)
        return settings

    def create_sub_problem_settings_model(self) -> BaseAlgorithmSettings:
        """Return the settings of a sub-problem, as a Pydantic model.

        This is what the ``Benders`` formulation takes as its
        ``sub_problem_algo_settings``, the model carrying the name of the
        algorithm it selects.

        Returns:
            The settings of a sub-problem, for :attr:`.sub_problem_algo_name`.
        """
        settings_class = _get_settings_class(self.sub_problem_algo_name)
        return settings_class(**self.to_sub_problem_settings())


def _get_settings_class(algo_name: str) -> type[BaseAlgorithmSettings]:
    """Return the class of the settings of an optimization algorithm.

    Args:
        algo_name: The name of the algorithm, as the GEMSEO factory knows it.

    Returns:
        The class of its settings.

    Raises:
        ValueError: When no optimization algorithm goes by that name.
    """
    factory = OptimizationLibraryFactory()
    if not factory.is_available(algo_name):
        msg = (
            f"The optimization algorithm {algo_name!r} is not available; "
            f"the available ones are {sorted(factory.algorithms)}."
        )
        raise ValueError(msg)

    library = factory.get_class(factory.algo_names_to_libraries[algo_name])
    return library.ALGORITHM_INFOS[algo_name].Settings


def _check_settings_names(
    algo_name: str, settings: Mapping[str, Any], level: str
) -> None:
    """Check that an algorithm takes every setting it is given.

    The names are checked here so that a setting of one algorithm passed to
    another is refused where it is written, rather than in the middle of a run.

    Args:
        algo_name: The name of the algorithm.
        settings: The settings it is to be given.
        level: The level of the method it solves, for the error message.

    Raises:
        ValueError: When the algorithm does not take one of the settings.
    """
    unknown = set(settings) - set(_get_settings_class(algo_name).model_fields)
    if unknown:
        msg = (
            f"The algorithm {algo_name!r} of the {level} does not take "
            f"the following settings: {sorted(unknown)}."
        )
        raise ValueError(msg)


def _check_sub_problem_settings_model(algo_name: str) -> None:
    """Check that the settings of an algorithm select that very algorithm.

    A settings model carries the name of the algorithm it selects, and it is that
    name, not the one asked for here, that the ``Benders`` formulation executes.
    The two differ for an algorithm whose plugin declares them inconsistently, in
    which case naming it would silently run something else.

    Args:
        algo_name: The name of the algorithm.

    Raises:
        ValueError: When the settings of the algorithm select another one.
    """
    selected = _get_settings_class(algo_name)._TARGET_CLASS_NAME
    if selected != algo_name:
        msg = (
            f"The settings of the algorithm {algo_name!r} select {selected!r} "
            "instead, so the sub-problems would be solved by another algorithm "
            "than the one named; this is a defect of the plugin providing it."
        )
        raise ValueError(msg)
