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
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING
from typing import Any
from typing import ClassVar

if TYPE_CHECKING:
    from collections.abc import Mapping

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


@dataclass
class BoxSubdivisionSettings:
    r"""The settings of a box-subdivision run.

    The defaults are the configuration the benchmark supports: the adaptive
    repair of the cut slopes, four probe points, and a trust region of two
    components.

    Two of these settings decide whether a run works at all, and neither has a
    default that transfers between problems:

    ``convexity_margin``
        subtracted from an objective difference, so it is absolute and in the
        units of *your* objective. Start from the variation of the objective
        over the design space. It crosses a threshold and then saturates, so
        erring high costs sub-problems rather than quality.

    ``trust_region_radius``
        the number of components a candidate box may change. Keep it small.
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
    """Any other setting of the master, passed through unchanged."""

    def __post_init__(self) -> None:
        """Check the settings.

        Raises:
            ValueError: When the mechanism is unknown, or a count is not
                positive.
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

        A sweep of the convexity is **not** a setting of the released master,
        which takes one value. It degrades here to the top rung of the ladder,
        the conservative end: the tuning says an over-large margin costs
        sub-problems rather than quality, so a run that loses the sweep loses
        the cheap rungs rather than the result. Where the master does support
        the sweep, it reads :attr:`.convexity_sweep` instead of this value. A
        sweep whose upper bound is read off the objective has no ladder until a
        run is under way, so it degrades to the value of the mechanism.

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
        value = self.convexity_value
        sweep = self.create_convexity_sweep()
        if sweep is not None:
            value = sweep.max_value

        settings = {
            "max_iter": self.max_iter,
            "ub_tol": self.tolerance,
            "adapt": adaptive,
            "min_dfk": value if adaptive else 0.0,
            "convexification_constant": 0.0 if adaptive else value,
            "number_of_parallel_points": (
                self.n_parallel_points if adaptive or sweep is not None else 1
            ),
            "max_step": self.trust_region_radius if radius is None else radius,
        }
        settings.update(self.options)
        return settings
