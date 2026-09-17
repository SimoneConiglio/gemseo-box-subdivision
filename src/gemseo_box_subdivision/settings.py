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
from dataclasses import fields
from typing import TYPE_CHECKING
from typing import Any
from typing import ClassVar
from warnings import warn

from gemseo.algos.opt.factory import OptimizationLibraryFactory

from gemseo_box_subdivision.convexity_sweep import HEADROOM
from gemseo_box_subdivision.convexity_sweep import MASTER_SWEEPS_CONVEXITY
from gemseo_box_subdivision.convexity_sweep import ConvexitySweep
from gemseo_box_subdivision.convexity_sweep import convexity_ladder

if TYPE_CHECKING:
    from collections.abc import Mapping

    from gemseo.algos.base_algorithm_settings import BaseAlgorithmSettings

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
itself rather than an ordinary optimizer, and this is the one the plugin
``gemseo-bilevel-outer-approximation`` provides. Another master is allowed, any
that handles integer variables, but only this one takes the settings
:meth:`.BoxSubdivisionSettings.to_master_settings` translates; the rest are
driven by :attr:`.BoxSubdivisionSettings.master_algo_settings`.
"""

N_PARALLEL_POINTS: int = 4
"""The default number of points the master probes per iteration.

One trust-region radius per point, and under
:class:`.SweptBoxSubdivisionSettings` one rung of the convexity ladder per point
as well: a probe per rung is what makes an iteration span the ladder, so the two
counts are this one number rather than two that can disagree.
"""

SUB_PROBLEM_ALGO_NAME: str = "SLSQP"
"""The default algorithm solving each sub-problem inside its box.

A box is a continuous problem with bounds, and every result reported was measured
with SLSQP over it. A derivative-free solver is a legitimate choice for an
objective whose gradient is unavailable or noisy, but nothing here measures one.
"""


@dataclass
class BaseBoxSubdivisionSettings:
    r"""What every box-subdivision run needs, whichever master drives it.

    A run is two algorithms: a master deciding which box to look into, and a
    solver running inside the box it chose. This class holds what belongs to the
    run rather than to either of them, and what the sub-problem level takes;
    :class:`.BoxSubdivisionSettings` and :class:`.SweptBoxSubdivisionSettings`
    add the master.
    """

    MECHANISMS: ClassVar[tuple[str, ...]] = ("adaptive", "convexification")
    """The two mechanisms keeping the cuts usable on a non-convex problem."""

    MASTER_TERMS: ClassVar[dict[str, str]] = {
        "mechanism": "adapt",
        "convexity_margin": "min_dfk",
        "convexification_constant": "convexification_constant",
        "trust_region_radius": "max_step",
        "n_parallel_points": "number_of_parallel_points",
        "max_iter": "max_iter",
        "tolerance": "ub_tol",
    }
    """What each setting of the method is called by the master it is meant for.

    The method names a quantity; the master names a setting. A master declaring
    the name on the right takes the setting on the left, and one that does not
    takes nothing of it, which is what makes a setting of the outer approximation
    inapplicable to another master.
    """

    mechanism: str = "adaptive"
    r"""How the master keeps its cuts usable, ``"adaptive"`` or
    ``"convexification"``.

    They rest on different arguments and are **not** combined: the adaptive
    repair fixes the slope of each cut against the boxes already solved, while
    the convexification adds a convex term whose constant, once it dominates the
    concavity of the relaxation, makes the outer approximation convergent.
    Measuring the two together measures neither.

    This describes an outer approximation and nothing else, so it reaches a
    master only where that master declares the settings it drives; see
    :meth:`.BoxSubdivisionSettings.to_master_settings`.
    """

    trust_region_radius: int = TRUST_REGION_RADIUS
    """The radius of the trust region of the master, in components changed."""

    n_parallel_points: int = N_PARALLEL_POINTS
    """The number of trust-region radii the master probes per iteration."""

    max_iter: int = 80
    """The number of iterations of the master, not of the sub-problems."""

    sub_problem_max_iter: int = 40
    """The number of iterations of each sub-problem."""

    tolerance: float = 1e-4
    """The tolerance on the upper bound of the master."""

    sub_problem_algo_name: str = SUB_PROBLEM_ALGO_NAME
    """The name of the algorithm solving each sub-problem inside its box.

    Any GEMSEO optimizer, its name as the library factory knows it. The
    sub-problem is continuous and bounded, which is what
    :data:`.SUB_PROBLEM_ALGO_NAME` suits; a solver returning a point far from a
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
                positive, when the sub-problem solver is unknown or does not take
                a setting it is given, or when its settings select another
                algorithm.
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
    def convexity_value(self) -> float | None:
        """The value the mechanism calibrates, or ``None`` when it is not known.

        A sweep reading its bound off the objective has none to give before the
        run has solved anything: only the master, which observes the objective,
        can compute one. ``None`` then leaves the master its own value rather
        than overwriting it, an unknown guard being no reason to impose a guard
        of zero.
        """
        raise NotImplementedError

    def _to_outer_approximation_settings(
        self, radius: int | None = None, swept: bool = False
    ) -> dict[str, Any]:
        """Return the settings of the outer approximation, in its own terms.

        The mechanism decides which of the two constants is passed and which is
        switched off, so that the two can never be active at once.

        Args:
            radius: The radius of the trust region, overriding
                :attr:`.trust_region_radius`. Used by the encodings whose
                distance counts something other than design variables.
            swept: Whether the convexity is swept, which keeps the parallel
                points under the pure convexification: a probe per rung is what
                makes an iteration span the ladder, so a sweep of a single probe
                is not one.

        Returns:
            The settings of the master, under the names it declares.
        """
        adaptive = self.mechanism == "adaptive"
        settings = {
            "max_iter": self.max_iter,
            "ub_tol": self.tolerance,
            "adapt": adaptive,
            # Choosing one mechanism switches the other off, whatever the value
            # of the chosen one turns out to be.
            "convexification_constant" if adaptive else "min_dfk": 0.0,
            "number_of_parallel_points": (
                self.n_parallel_points if adaptive or swept else 1
            ),
            "max_step": self.trust_region_radius if radius is None else radius,
        }

        value = self.convexity_value
        if value is not None:
            settings["min_dfk" if adaptive else "convexification_constant"] = value

        return settings

    def to_master_settings(self, radius: int | None = None) -> dict[str, Any]:
        """Return the settings of the master problem.

        Args:
            radius: The radius of the trust region, overriding
                :attr:`.trust_region_radius`.

        Returns:
            The settings of the master problem.
        """
        raise NotImplementedError

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


@dataclass
class BoxSubdivisionSettings(BaseBoxSubdivisionSettings):
    r"""The settings of a box-subdivision run, with the master you name.

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

    Not choosing either is what :class:`.SweptBoxSubdivisionSettings` is for.

    **The mechanism belongs to the outer approximation, not to every master.**
    :attr:`.mechanism`, the two convexity values, the trust region and the
    parallel points are settings of an outer-approximation master, and a master
    that does not declare them is driven by :attr:`.master_algo_settings` alone,
    under its own names. Naming such a master *and* setting one of those is
    refused where it is written rather than silently ignored at execution.
    """

    convexity_margin: float = CONVEXITY_MARGIN
    """The convexity margin of the adaptive repair, in the units of the objective."""

    convexification_constant: float = CONVEXITY_MARGIN
    """The constant of the convexification, in the units of the objective."""

    options: Mapping[str, Any] = field(default_factory=dict)
    """Any other setting of the master, passed through unchanged.

    .. deprecated:: 0.2.0
        Use :attr:`.master_algo_settings`, which says which of the two levels it
        configures. Both may be given, in which case
        :attr:`.master_algo_settings` wins.
    """

    master_algo_name: str = MASTER_ALGO_NAME
    """The name of the algorithm solving the master problem.

    Any GEMSEO algorithm deciding the next box. The default is the outer
    approximation the method is built on, whose settings this class translates;
    another master is configured through :attr:`.master_algo_settings`, under the
    names it declares. Changing it changes the method, not merely its tuning.
    """

    master_algo_settings: Mapping[str, Any] = field(default_factory=dict)
    """Any other setting of the master, passed through unchanged.

    These win over the settings this class translates, so a setting named both
    here and by the class takes the value given here. For a master that is not an
    outer approximation, this is the whole of its configuration.
    """

    def __post_init__(self) -> None:
        """Check the settings.

        Raises:
            ValueError: When a setting of the outer approximation is given to a
                master that does not declare it, on top of what
                :meth:`.BaseBoxSubdivisionSettings.__post_init__` refuses.
        """
        super().__post_init__()

        if self.options:
            warn(
                "The setting 'options' is deprecated; "
                "use 'master_algo_settings' instead.",
                FutureWarning,
                stacklevel=2,
            )
            self.master_algo_settings = {**self.options, **self.master_algo_settings}

        _check_the_master_can_solve_it(self.master_algo_name)
        self._check_the_master_takes_the_method_s_terms()
        _check_settings_names(
            self.master_algo_name, self.to_master_settings(), "master problem"
        )

    @property
    def convexity_value(self) -> float:
        """The value of the convexity setting the mechanism calibrates."""
        if self.mechanism == "adaptive":
            return self.convexity_margin

        return self.convexification_constant

    def _check_the_master_takes_the_method_s_terms(self) -> None:
        """Refuse a setting of the method the master cannot take.

        A master that is not an outer approximation has no mechanism, no
        convexity and no trust region, so a value given for one of them would go
        nowhere. Leaving them at their defaults is how such a master is named;
        setting one is a contradiction, and it is refused here rather than
        dropped silently on the way to a master that never sees it.

        Raises:
            ValueError: When the master does not declare a setting that was set.
        """
        declared = set(_get_settings_class(self.master_algo_name).model_fields)
        defaults = {field.name: field.default for field in fields(self)}
        refused = {
            name: term
            for name, term in self.MASTER_TERMS.items()
            if term not in declared and getattr(self, name) != defaults[name]
        }
        if refused:
            named = ", ".join(
                f"{name!r} ({term!r})" for name, term in sorted(refused.items())
            )
            msg = (
                f"The algorithm {self.master_algo_name!r} of the master problem does "
                f"not take {named}; a master that is not an outer approximation is "
                "configured by 'master_algo_settings', under the names it declares."
            )
            raise ValueError(msg)

    def to_master_settings(self, radius: int | None = None) -> dict[str, Any]:
        """Return the settings of the master problem.

        For an outer approximation, the settings this class names are translated
        into the master's own terms, the mechanism deciding which of the two
        constants is passed and which is switched off, so that the two can never
        be active at once. For any other master, none of them is: it is driven by
        :attr:`.master_algo_settings` alone, and the iteration count and the
        tolerance, which an ordinary optimizer takes too, follow the names it
        declares.

        Args:
            radius: The radius of the trust region, overriding
                :attr:`.trust_region_radius`. Used by the encodings whose
                distance counts something other than design variables.

        Returns:
            The settings of the master problem.
        """
        settings = self._to_outer_approximation_settings(radius)
        declared = set(_get_settings_class(self.master_algo_name).model_fields)
        settings = {name: value for name, value in settings.items() if name in declared}
        settings.update(self.master_algo_settings)
        return settings


@dataclass
class SweptBoxSubdivisionSettings(BaseBoxSubdivisionSettings):
    r"""The settings of a run that **sweeps** the convexity instead of choosing it.

    The convexity is the one quantity of this method with no value that
    transfers between problems, and this is the entry point that does not ask
    for one. The master probes a ladder of convexity values across the parallel
    points it already spends on trust-region radii, the low rungs proposing the
    box next door and the high rungs the box across the design space, and
    redeploys a rung higher every probe that proposes nothing new.

    **The sweep is the master's**, so this names no master: it drives the one
    that implements it, under its own settings ``convexity_sweep_points`` and
    ``convexity_sweep_max``. There is nothing to pass through either, since the
    parameters of the master are chosen here rather than supplied:

    :attr:`.n_parallel_points`
        the probes *and* the rungs. A probe per rung is the whole construction,
        so the two are one number rather than two that can disagree; a single
        probe is given the top rung, the conservative end, since there is no
        ladder to span.

    :attr:`.max_value`
        the top of the ladder, or zero to read it off the objective as the run
        observes it, lifted by a decade of headroom.

    What is **not** here is as much of the point as what is: no convexity
    margin, no convexification constant, and no master to name. Those live on
    :class:`.BoxSubdivisionSettings`, which is the general construction, and
    supplying one alongside a sweep is the contradiction this split removes.
    """

    max_value: float = 0.0
    """The upper bound of the ladder, or zero to read it off the objective.

    Zero asks the master for the bound the run observes, the spread of the
    objective over the boxes already solved, lifted by :data:`.HEADROOM`. That
    spread is a lower estimate of the spread over the design space, and reading
    it literally is circular, which is what the headroom answers.
    """

    def __post_init__(self) -> None:
        """Check the settings.

        Raises:
            ValueError: When the upper bound is negative, on top of what
                :meth:`.BaseBoxSubdivisionSettings.__post_init__` refuses.
        """
        super().__post_init__()

        if self.max_value < 0.0:
            msg = (
                "The upper bound of the sweep must be positive, or zero to read "
                f"it off the objective; got {self.max_value}."
            )
            raise ValueError(msg)

        _check_the_master_can_solve_it(self.master_algo_name)
        _check_settings_names(
            self.master_algo_name, self.to_master_settings(), "master problem"
        )

    @property
    def master_algo_name(self) -> str:
        """The name of the algorithm solving the master problem.

        The sweep is implemented in the master, so this entry point drives that
        master rather than one of the caller's choosing. A master to name, and
        settings to pass it, are what :class:`.BoxSubdivisionSettings` is for.
        """
        return MASTER_ALGO_NAME

    @property
    def convexity_value(self) -> float | None:
        """The value the mechanism takes before the ladder is there.

        The **top rung** of a bounded sweep, which is what the master uses in the
        first iterations, before it has solved enough boxes to have a ladder at
        all, and what a master predating the sweep uses throughout. The tuning
        says an over-large margin costs sub-problems rather than quality, so the
        conservative end is where a lone value belongs.

        An unbounded sweep has no such value: its bound is the spread of the
        objective, which the run has not measured yet, so the master keeps
        whatever it uses by default until :meth:`.create_sweep` can compute one.
        """
        return self.max_value or None

    def create_sweep(self, observed_scale: float = 0.0) -> ConvexitySweep | None:
        """Return the ladder this run asks for.

        Args:
            observed_scale: The variation of the objective over the boxes already
                solved, which is the upper bound of a sweep given none. See
                :func:`.objective_scale`.

        Returns:
            The ladder, or ``None`` when its upper bound is neither given nor
            observed yet.
        """
        max_value = self.max_value or observed_scale * HEADROOM
        if max_value <= 0.0:
            return None

        return ConvexitySweep(convexity_ladder(max_value, self.n_parallel_points))

    def to_master_settings(self, radius: int | None = None) -> dict[str, Any]:
        """Return the settings of the master problem.

        The sweep is asked for under the master's own two settings, the rungs
        being the parallel points. Against a master predating the sweep, see
        :data:`.MASTER_SWEEPS_CONVEXITY`, those two are not declared and are not
        passed; what is left is the top rung, the conservative end, so a run that
        loses the sweep loses the cheap rungs rather than the result.

        Args:
            radius: The radius of the trust region, overriding
                :attr:`.trust_region_radius`. Used by the encodings whose
                distance counts something other than design variables.

        Returns:
            The settings of the master problem.
        """
        settings = self._to_outer_approximation_settings(radius, swept=True)
        if MASTER_SWEEPS_CONVEXITY:
            settings["convexity_sweep_points"] = self.n_parallel_points
            settings["convexity_sweep_max"] = self.max_value

        return settings


def _check_the_master_can_solve_it(algo_name: str) -> None:
    """Check that an algorithm can solve the master problem at all.

    The master chooses a box, and a box is a one-hot assignment of binaries, so
    the master problem is a **relaxable mixed-integer non-linear** one whatever
    the algorithm solving it: the cuts and the convexification make it non-linear,
    and its continuous relaxation is what the outer approximation solves before
    recovering the integers from it. Relaxing is therefore the method working, not
    a solver falling short — but an algorithm that cannot hold an integer variable
    has no integers to recover and returns the relaxation itself, which is not a
    box. That is refused where the master is named rather than at the first
    iteration.

    Args:
        algo_name: The name of the algorithm.

    Raises:
        ValueError: When the algorithm does not handle integer variables.
    """
    factory = OptimizationLibraryFactory()
    if not factory.is_available(algo_name):
        msg = (
            f"The optimization algorithm {algo_name!r} is not available; "
            f"the available ones are {sorted(factory.algorithms)}."
        )
        raise ValueError(msg)

    library = factory.get_class(factory.algo_names_to_libraries[algo_name])
    if not library.ALGORITHM_INFOS[algo_name].handle_integer_variables:
        msg = (
            f"The algorithm {algo_name!r} of the master problem does not handle "
            "integer variables, so it returns the relaxation rather than a box; "
            "the master problem is a relaxable mixed-integer non-linear one "
            "whatever solves it."
        )
        raise ValueError(msg)


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
