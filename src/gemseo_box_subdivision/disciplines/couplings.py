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
"""Keeping the couplings of an MDA internal to the chain it sits in.

The disciplines of a :class:`.BoxSubdivisionScenario` are collapsed into a single
:class:`~gemseo.core.chains.chain.MDOChain`, so a **coupled** problem is posed by
building the MDA explicitly and handing it over among the disciplines. That is
the only route: the sub-problem's formulation is
:class:`~gemseo.formulations.disciplinary_opt.DisciplinaryOpt`, so the
sub-problem cannot itself be an MDF scenario, and chaining the disciplines
instead is a different problem — it evaluates each once in order and calls the
result converged.

An MDA both consumes and produces its couplings, and a chain treats every input
that no earlier discipline produces as an input of the chain, so the couplings
become inputs of the chain. When the adapter computes its auxiliary Jacobians —
which it only does once there is a constraint to differentiate — the chain asks
the MDA for derivatives with respect to them, and the Jacobian assembly refuses::

    ValueError: Variable y2 is both a coupling and a design variable

Under MDF the formulation knows the couplings are internal and never asks.
Inside a chain nothing does, which is what this module supplies.

The derivative it declines to compute is the right one rather than a way round
the error: a coupling enters an MDA as an **initial guess** and leaves it
converged, and a converged fixed point does not depend on where the iteration
started, so that derivative is zero.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Final

from gemseo.mda.base_mda import BaseMDA

if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Sequence

    from gemseo.core.discipline import Discipline

_INTERNAL_COUPLINGS: Final[str] = "_gemseo_box_subdivision_internal_couplings"
"""The mark of an MDA whose couplings were already made internal."""


def keep_couplings_internal(discipline: BaseMDA) -> BaseMDA:
    """Stop an MDA being differentiated with respect to its own couplings.

    The MDA is given a subclass of its own class overriding
    :meth:`~gemseo.core.discipline.discipline.Discipline.add_differentiated_inputs`,
    so that a chain asking for every input of the MDA gets the derivatives with
    respect to the inputs that are not couplings. Calling this twice on the same
    MDA does nothing the second time.

    Args:
        discipline: The MDA, which is modified in place.

    Returns:
        The same MDA, for chaining.
    """
    if getattr(discipline, _INTERNAL_COUPLINGS, False):
        return discipline

    couplings = frozenset(discipline.coupling_structure.all_couplings)

    class CoupledBlock(type(discipline)):  # type: ignore[misc,valid-type]
        """An MDA that is a block of a chain rather than a formulation of its own."""

        def add_differentiated_inputs(self, input_names: Iterable[str] = ()) -> None:
            # An empty argument means every input of the discipline, so the
            # filtering has to name them rather than pass the emptiness on.
            names = list(input_names) or list(self.io.input_grammar)
            super().add_differentiated_inputs([
                name for name in names if name not in couplings
            ])

    CoupledBlock.__name__ = f"{type(discipline).__name__}AsABlock"
    CoupledBlock.__qualname__ = CoupledBlock.__name__
    discipline.__class__ = CoupledBlock
    setattr(discipline, _INTERNAL_COUPLINGS, True)
    return discipline


def keep_every_mda_couplings_internal(
    disciplines: Sequence[Discipline],
) -> tuple[Discipline, ...]:
    """Make the couplings of every MDA among some disciplines internal.

    The disciplines that are not MDAs are returned untouched.

    Args:
        disciplines: The disciplines handed to a scenario. The MDAs among them
            are modified in place.

    Returns:
        The disciplines, in the order they were given.
    """
    return tuple(
        keep_couplings_internal(discipline)
        if isinstance(discipline, BaseMDA)
        else discipline
        for discipline in disciplines
    )
