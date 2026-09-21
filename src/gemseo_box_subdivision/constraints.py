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
"""The constraints of the original problem, and the one shape that cannot be used.

A constraint reaches the master through the post-optimal analysis of the
sub-problem, which needs the Jacobian of the constraint with respect to the
variables of the main problem. The adapter builds it by asking each *discipline*
for the derivative of the function, and it asks under the **name of the
constraint**::

    func_jacobian = disciplines[func_name].jac[func_name]

``disciplines`` maps an output name to the discipline producing it, so this holds
exactly while a constraint is named after the output it is built from. A
constraint named anything else is the output of no discipline, and the lookup
raises :class:`KeyError`.

Three ordinary ways of writing a constraint rename it, and every one of them is
a way to write a band or a lower bound:

=========================== ==================
written as                  named
=========================== ==================
``constraint_name="g_up"``  ``g_up``
``positive=True``           ``-g``
``value=0.5``               ``[g-0.5]``
=========================== ==================

The lookup is reached only when the master first linearizes the adapter, which a
run of one or two iterations never does, so the ``KeyError`` arrives long after
the line that caused it and from a module the caller never named. What this
module does is move the refusal to where the constraint is written.
"""

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gemseo.algos.optimization_problem import OptimizationProblem

RENAMING_SHAPES: tuple[str, ...] = (
    "constraint_name=",
    "positive=True, which GEMSEO names '-g'",
    "a non-zero value, which GEMSEO names '[g-0.5]'",
)
"""The ways of writing a constraint that rename it, hence that cannot be used."""


def find_renamed_constraints(
    problem: OptimizationProblem,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return the constraints of a problem that are named after no output.

    Args:
        problem: The optimization problem of a sub-problem.

    Returns:
        The name of every constraint named after none of the outputs it is built
        from, with those outputs.
    """
    return tuple(
        (constraint.name, tuple(constraint.output_names))
        for constraint in problem.constraints
        if constraint.name not in constraint.output_names
    )


def _describe(renamed: Sequence[tuple[str, tuple[str, ...]]]) -> str:
    """Return the message refusing renamed constraints.

    Args:
        renamed: The name of every renamed constraint, with its outputs.

    Returns:
        The message, naming the limitation and the way around it.
    """
    listed = ", ".join(
        f"{name!r}, built from {list(output_names)}" for name, output_names in renamed
    )
    shapes = "".join(f"\n  - {shape}" for shape in RENAMING_SHAPES)
    # The first output of the first renamed constraint, so that the way around
    # the limitation is written in the names of the problem at hand.
    output_name = renamed[0][1][0]
    return (
        f"The following constraints are named after no output of a discipline: "
        f"{listed}. The sub-problem adapter looks a constraint up by its name "
        "among the outputs of the disciplines to build its Jacobian, so such a "
        "constraint raises a KeyError the first time the master linearizes the "
        "adapter, which is several iterations into a run rather than here."
        f"\n\nA constraint is renamed by:{shapes}"
        "\n\nGive each side its own discipline output instead, and constrain "
        "that output under its own name. A LinearCombination per side has an "
        f"exact constant Jacobian:\n\n    LinearCombination([{output_name!r}], "
        f"'{output_name}_upper', "
        f"input_coefficients={{{output_name!r}: 1.0}}, offset=-0.5)"
    )


def check_constraint_names(problem: OptimizationProblem) -> None:
    """Refuse the constraints of a problem that are named after no output.

    Args:
        problem: The optimization problem of a sub-problem.

    Raises:
        ValueError: When a constraint is named after none of the outputs it is
            built from, which the sub-problem adapter cannot linearize.
    """
    renamed = find_renamed_constraints(problem)
    if renamed:
        raise ValueError(_describe(renamed))


def guard_renamed_constraints(formulation: Any) -> None:
    """Make a ``Benders`` formulation refuse a constraint it cannot linearize.

    The constraint is added first and removed again on refusal, since what makes
    a constraint unusable is the name GEMSEO gives it, which is worth reporting
    and is not worth predicting: ``value`` and ``positive`` name a constraint
    between them, and the naming belongs to GEMSEO rather than here.

    Args:
        formulation: The ``Benders`` formulation of the scenario.
    """
    add_constraint = formulation.add_constraint
    problem = formulation.sub_problem_scenario_adapter.scenario.formulation.optimization_problem  # noqa: E501

    @wraps(add_constraint)
    def guarded(*args: Any, **kwargs: Any) -> None:
        n_constraints = len(problem.constraints)
        add_constraint(*args, **kwargs)
        try:
            check_constraint_names(problem)
        except ValueError:
            # A refused constraint is a constraint that was never added, so
            # that the message is the whole of what this call did.
            while len(problem.constraints) > n_constraints:
                problem.constraints.pop()

            raise

    formulation.add_constraint = guarded
