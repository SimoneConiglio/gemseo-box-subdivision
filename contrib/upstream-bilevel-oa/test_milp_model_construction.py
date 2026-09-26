# Copyright 2021 IRT Saint Exupéry, https://www.irt-saintexupery.com
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
"""The model `OrtoolsMILP` hands to the solver, row by row.

The rows are built by setting each coefficient on the solver's own constraint
rather than by accumulating a Python expression, which is a change of how the
model is built and not of what it is. What these tests pin is the "not of what
it is" half: that a coefficient still reaches the variable it belongs to, that a
zero still means the variable is absent from the row, and that the equality
tolerance still widens the row on both sides.

A coefficient landing one variable off is the failure mode a faster row builder
invites, and it is invisible in a problem whose rows are all alike, so the
problems here are asymmetric on purpose: every coefficient is distinct and the
optimum moves if any of them is misplaced.

Every problem carries an inequality *and* an equality, the pinning of ``t``
being there for no other reason. That is not a property of the change either:
`_run` reads ``eq_rhs - eq_tolerance`` and ``ineq_rhs`` without guarding
either, and `build_constraints_matrices` returns ``None`` for a kind of
constraint the problem does not have, so a problem carrying only one kind
raises a `TypeError` before any row is built. Older than this change, and
untouched by it.
"""

from __future__ import annotations

import pytest
from gemseo.algos.design_space import DesignSpace
from gemseo.algos.opt.factory import OptimizationLibraryFactory
from gemseo.algos.optimization_problem import OptimizationProblem
from gemseo.core.mdo_functions.mdo_function import MDOFunction
from gemseo.core.mdo_functions.mdo_linear_function import MDOLinearFunction
from numpy import array
from numpy import zeros
from numpy.random import default_rng
from numpy.testing import assert_allclose

ALGORITHMS = ["ORTOOLS_MILP", "Scipy_MILP"]


def _binary_space(size: int) -> DesignSpace:
    """Return a design space of binary variables, plus a continuous one.

    The continuous ``t`` is not decoration. The master's own design space mixes
    the one-hot binaries with a continuous epigraph variable, so this matches
    it; and an all-integer design space does not reach the solver at all today,
    ``get_value_and_bounds`` returning integer-typed bounds that
    ``Solver.IntVar`` rejects as its ``double`` arguments. That is a fault of
    its own, older than this change and untouched by it.

    ``t`` carries a coefficient of zero in every row and a positive one in every
    objective, so it is driven to zero and moves no optimum here.

    Args:
        size: The number of binary variables.

    Returns:
        The design space.
    """
    design_space = DesignSpace()
    for index in range(size):
        design_space.add_variable(
            f"x{index}",
            lower_bound=0.0,
            upper_bound=1.0,
            value=0,
            type_=design_space.DesignVariableType.INTEGER,
        )
    design_space.add_variable("t", lower_bound=0.0, upper_bound=1.0, value=0.0)
    return design_space


@pytest.mark.parametrize("algo_name", ALGORITHMS)
def test_a_zero_coefficient_leaves_its_variable_out_of_the_row(algo_name):
    """A zero coefficient frees its variable without displacing the others.

    Minimising $-3x_0 - 2x_1 - x_2$ over binaries under
    $x_0 + 0x_1 + x_2 \\le 1$ leaves $x_1$ unconstrained and makes the row pick
    the better of $x_0$ and $x_2$, so the optimum is $[1, 1, 0]$ at $-5$.

    Were the zero dropped rather than skipped, the row would read
    $x_0 + x_2 \\le 1$ against the *first two* variables, giving $[1, 0, 1]$ at
    $-4$: the same number of coefficients, shifted by one variable.
    """
    names = ["x0", "x1", "x2", "t"]
    problem = OptimizationProblem(_binary_space(3), is_linear=True)
    problem.objective = MDOLinearFunction(
        array([-3.0, -2.0, -1.0, 1.0]), "f", MDOFunction.FunctionType.OBJ, names
    )
    problem.add_constraint(
        MDOLinearFunction(array([1.0, 0.0, 1.0, 0.0]), "g", input_names=names),
        1.0,
        MDOFunction.ConstraintType.INEQ,
    )
    problem.add_constraint(
        MDOLinearFunction(array([0.0, 0.0, 0.0, 1.0]), "pin", input_names=names),
        0.0,
        MDOFunction.ConstraintType.EQ,
    )
    result = OptimizationLibraryFactory().execute(problem, algo_name=algo_name)
    assert_allclose(result.x_opt, array([1.0, 1.0, 0.0, 0.0]))
    assert result.f_opt == pytest.approx(-5.0)


@pytest.mark.parametrize("algo_name", ALGORITHMS)
def test_an_all_zero_row_constrains_nothing(algo_name):
    """A row of zeros is a row the solver may be told nothing about.

    Skipping every coefficient of a row leaves an empty constraint, and an empty
    constraint with a finite bound must still be satisfiable rather than render
    the problem infeasible.
    """
    names = ["x0", "x1", "x2", "t"]
    problem = OptimizationProblem(_binary_space(3), is_linear=True)
    problem.objective = MDOLinearFunction(
        array([-1.0, -1.0, -1.0, 1.0]), "f", MDOFunction.FunctionType.OBJ, names
    )
    problem.add_constraint(
        MDOLinearFunction(zeros(4), "g", input_names=names),
        1.0,
        MDOFunction.ConstraintType.INEQ,
    )
    problem.add_constraint(
        MDOLinearFunction(array([0.0, 0.0, 0.0, 1.0]), "pin", input_names=names),
        0.0,
        MDOFunction.ConstraintType.EQ,
    )
    result = OptimizationLibraryFactory().execute(problem, algo_name=algo_name)
    assert result.f_opt == pytest.approx(-3.0)


@pytest.mark.parametrize("algo_name", ALGORITHMS)
def test_the_equality_row_binds_on_both_sides(algo_name):
    """An equality is two bounds, and dropping either one loses the constraint.

    $x_0 + x_1 + x_2 = 2$ over binaries, minimising $-3x_0 - 2x_1 - x_2$, gives
    $[1, 1, 0]$ at $-5$. Keeping only the lower bound would let all three rise
    to $-6$; keeping only the upper would let all three fall to $0$.
    """
    names = ["x0", "x1", "x2", "t"]
    problem = OptimizationProblem(_binary_space(3), is_linear=True)
    problem.objective = MDOLinearFunction(
        array([-3.0, -2.0, -1.0, 1.0]), "f", MDOFunction.FunctionType.OBJ, names
    )
    problem.add_constraint(
        MDOLinearFunction(array([1.0, 1.0, 1.0, 0.0]), "h", input_names=names),
        2.0,
        MDOFunction.ConstraintType.EQ,
    )
    problem.add_constraint(
        MDOLinearFunction(array([1.0, 1.0, 1.0, 0.0]), "slack", input_names=names),
        3.0,
        MDOFunction.ConstraintType.INEQ,
    )
    result = OptimizationLibraryFactory().execute(problem, algo_name=algo_name)
    assert_allclose(result.x_opt, array([1.0, 1.0, 0.0, 0.0]))
    assert result.f_opt == pytest.approx(-5.0)


@pytest.mark.parametrize("seed", range(8))
def test_ortools_agrees_with_scipy_on_a_dense_model(seed):
    """The two libraries return the same optimum on a model with no structure.

    The master's own rows are dense and its coefficients are all different, so
    the check that matters is a dense model with distinct coefficients rather
    than a tidy one. Only the objective value is compared: a tie between two
    designs is the solvers' to break as they please.
    """
    rng = default_rng(seed)
    size, n_rows = 6, 5
    names = [f"x{index}" for index in range(size)]
    names.append("t")
    matrix = zeros((n_rows, size + 1))
    matrix[:, :size] = rng.normal(size=(n_rows, size))
    # A row that is entirely absent from the model, and one that is half absent.
    matrix[0] = 0.0
    matrix[1, :size:2] = 0.0
    coefficients = zeros(size + 1)
    coefficients[:size] = rng.normal(size=size)
    coefficients[size] = 1.0
    optima = []
    for algo_name in ALGORITHMS:
        problem = OptimizationProblem(_binary_space(size), is_linear=True)
        problem.objective = MDOLinearFunction(
            coefficients, "f", MDOFunction.FunctionType.OBJ, names
        )
        for row in range(n_rows):
            problem.add_constraint(
                MDOLinearFunction(matrix[row], f"g{row}", input_names=names),
                1.0,
                MDOFunction.ConstraintType.INEQ,
            )
        pinned = zeros(size + 1)
        pinned[size] = 1.0
        problem.add_constraint(
            MDOLinearFunction(pinned, "pin", input_names=names),
            0.0,
            MDOFunction.ConstraintType.EQ,
        )
        optima.append(
            OptimizationLibraryFactory().execute(problem, algo_name=algo_name).f_opt
        )
    assert optima[0] == pytest.approx(optima[1])
