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
processes. The master forks, and what a child computes stays in the child's copy
of the database: ``_execute_doe`` hands :class:`.CallableParallelExecution` a
worker that returns ``None``, and passes no ``exec_callback``, which is the
channel that would bring the outputs back. Compare
``BaseDOELibrary.__run_in_parallel_one_at_a_time``, where the worker returns
``(data, jacobian_data)`` and a callback stores it in the parent.

The parent then reads entries that were never stored, and the read does not
raise: ``Database.get_function_value`` returns ``None`` for a missing key and
``atleast_2d(None)`` has shape ``(1, 1)``, so an absent gradient enters the cut
model as a scalar. The run reports a converged optimum that is wrong.

``CatTestDisc`` and ``CatTestDiscConcave`` do not show it, which is why the
parametrisation of ``test_bileveloa_optimizer_analytical`` over
``number_of_parallel_points`` never caught it: they reach the optimum before the
master evaluates a batch of more than one design. The concave catalogues do,
from any starting guess that is not already the answer.
"""

from __future__ import annotations

import sys

import pytest
from numpy.testing import assert_allclose

from tests.algos.conftest import CatTestDisc
from tests.algos.conftest import CatTestDiscConcave

EXPECTED_X_OPT = [0, 1, 0]
"""The design ``test_bileveloa_optimizer_analytical`` asserts, serially."""

EXPECTED_F_OPT = 0.0
"""The objective ``test_bileveloa_optimizer_analytical`` asserts, serially."""


@pytest.mark.parametrize("number_of_processes", [2, 4])
def test_number_of_processes_does_not_change_the_optimum(
    analytical_use_case,
    mdo_discipline_catalog,
    initial_guess,
    number_of_processes,
):
    """A run over several processes returns what a serial run returns."""
    if sys.platform.startswith("win"):
        pytest.skip("Parallel use of the cache is not supported on windows.")

    if mdo_discipline_catalog in (CatTestDisc, CatTestDiscConcave):
        pytest.skip("Converges before a batch of more than one design is evaluated.")

    if initial_guess == "Blue":
        pytest.skip("Starts at the answer, so nothing is explored in parallel.")

    scenario = analytical_use_case[0]
    scenario.execute(
        algo_name="BILEVEL_MASTER_OUTER_APPROXIMATION",
        max_iter=1000,
        normalize_design_space=True,
        posa=1.0,
        adapt=False,
        min_dfk=0.0,
        number_of_processes=number_of_processes,
    )
    result = scenario.optimization_result

    assert_allclose(result.x_opt, EXPECTED_X_OPT, atol=0.0)
    assert result.f_opt == pytest.approx(EXPECTED_F_OPT, abs=1e-10)
