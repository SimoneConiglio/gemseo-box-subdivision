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
"""``number_of_processes`` must change the wall clock and not the answer.

The setting fans the evaluation of an iteration's candidate designs over several
processes. It is reached only when an iteration has more than one candidate to
evaluate, because ``_execute_doe`` short circuits on ``i_k.shape[0] == 1``, and
the candidates of an iteration are its trust-region probes. **A run therefore has
to set ``number_of_parallel_points`` above one for ``number_of_processes`` to do
anything at all**, which is why the parametrisation of
``test_bileveloa_optimizer_analytical`` over ``number_of_parallel_points`` alone
never exercised the fan-out.

Before the fix the workers were forked with a callable returning ``None`` and no
``exec_callback``, so what a child computed stayed in the child's copy of the
database. The caller then read entries that were never stored, and the read did
not raise: ``Database.get_function_value`` returns ``None`` for a missing key and
``atleast_2d(None)`` has shape ``(1, 1)``, so an absent gradient entered the cut
model as a scalar and the run reported a converged optimum that was wrong.
"""

from __future__ import annotations

import sys

import pytest
from numpy.testing import assert_allclose

X_OPT = [0.0, 1.0, 0.0]
"""The design every configuration of this fixture reaches serially."""

F_OPT = 0.0
"""The objective every configuration of this fixture reaches serially."""

N_PARALLEL_POINTS = 4
"""Candidates per iteration, so that the fan-out is reached at all."""


@pytest.mark.parametrize("number_of_processes", [1, 2, 4])
def test_number_of_processes_does_not_change_the_optimum(
    analytical_use_case, number_of_processes
):
    """The optimum is the one the serial run reaches, over any process count.

    One process is the control: it takes the serial branch and must agree with
    the others.
    """
    if sys.platform.startswith("win"):
        pytest.skip("Parallel use of the cache is not supported on windows.")

    scenario = analytical_use_case[0]
    scenario.execute(
        algo_name="BILEVEL_MASTER_OUTER_APPROXIMATION",
        max_iter=1000,
        normalize_design_space=True,
        posa=1.0,
        adapt=False,
        min_dfk=0.0,
        number_of_parallel_points=N_PARALLEL_POINTS,
        number_of_processes=number_of_processes,
    )

    result = scenario.optimization_result
    assert_allclose(result.x_opt, X_OPT, atol=0.0)
    assert result.f_opt == pytest.approx(F_OPT, abs=1e-9)
