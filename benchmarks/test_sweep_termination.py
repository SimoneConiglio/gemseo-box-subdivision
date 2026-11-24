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
"""Tests for the diagnosis of the swept runs that stop early, and for its fix."""

from __future__ import annotations

from itertools import product
from types import SimpleNamespace

import pytest
from gemseo_bilevel_outer_approximation.algos.opt.core import (
    outer_approximation_optimizer as core,
)
from numpy import array
from numpy import atleast_2d
from numpy import zeros
from numpy.random import default_rng

from benchmarks.sweep_termination import convexification_sensitivity
from benchmarks.sweep_termination import margin_sensitivity
from benchmarks.sweep_termination import nonnegative_repair
from benchmarks.sweep_termination import recording
from benchmarks.sweep_termination import repair_nonnegatively

SOLVED = ((0, 0, 1), (0, 1, 0), (1, 0, 1), (1, 1, 1))
"""Four boxes of three components of two subdivisions each, already solved."""

UNSOLVED = (1, 0, 0)
"""A box none of them is, which the cut of the third one is raised at."""


def encode(box: tuple[int, ...], n_subdivisions: int = 2) -> array:
    """Return the one-hot encoding of a box.

    Args:
        box: The index of the subdivision of each component.
        n_subdivisions: The subdivisions per component.

    Returns:
        The encoding.
    """
    alpha = zeros(len(box) * n_subdivisions)
    for component, index in enumerate(box):
        alpha[component * n_subdivisions + index] = 1.0
    return alpha


def predict(slope, alpha, value: float, target) -> float:  # noqa: ANN001
    """Return what one cut predicts at a box.

    Args:
        slope: The slope of the cut.
        alpha: The box of the cut.
        value: The value there.
        target: The box to predict.

    Returns:
        The prediction.
    """
    return float(value + atleast_2d(slope).ravel() @ (target - alpha))


def released_repair(alphas, slopes, values, margin):  # noqa: ANN001, ANN201
    """Return the slopes as the released master repairs them.

    Args:
        alphas: The boxes solved.
        slopes: Their slopes.
        values: Their values.
        margin: The convexity margin.

    Returns:
        The repaired slopes.
    """
    master = SimpleNamespace(use_bilateral_adaptation=False)
    return core.OuterApproximationOptimizer._update_sensitivities_wt_secant_method(
        master, alphas, slopes, values, margin
    )


def test_the_margin_is_minus_one_at_a_box_solved() -> None:
    """Check that the margin lowers every cut by itself at the boxes solved."""
    alphas = [encode(box) for box in SOLVED]
    for alpha in alphas:
        assert margin_sensitivity(alphas, alpha) == pytest.approx([
            -1.0 if (other != alpha).any() else 0.0 for other in alphas
        ])


def test_the_margin_raises_a_cut_at_a_box_not_solved() -> None:
    """Check that the minimum-norm repair can raise a cut where nothing is solved.

    This is the released master's own repair, not a model of it: on a flat
    objective every right-hand side is the margin, and the cut of the third box
    rises by exactly the margin at the box nobody solved.
    """
    alphas = [encode(box) for box in SOLVED]
    target = encode(UNSOLVED)
    assert margin_sensitivity(alphas, target)[2] == pytest.approx(1.0)

    slopes = [zeros((1, alphas[0].size)) for _ in alphas]
    values = [0.0] * len(alphas)
    for margin in (1.0, 10.0, 100.0):
        repaired = released_repair(alphas, slopes, values, margin)
        assert predict(repaired[2], alphas[2], 0.0, target) == pytest.approx(margin)


def test_the_nonnegative_repair_never_raises_a_cut() -> None:
    """Check that no cut is raised anywhere, solved or not, whatever the margin."""
    generator = default_rng(3)
    boxes = list(product(range(3), repeat=3))
    solved = [boxes[index] for index in generator.choice(len(boxes), 9, False)]
    alphas = [encode(box, 3) for box in solved]
    slopes = [generator.normal(size=(1, 9)) * 5 for _ in alphas]
    values = list(generator.normal(size=len(alphas)) * 5)
    for margin in (0.0, 1.0, 10.0, 100.0):
        repaired = repair_nonnegatively(alphas, slopes, values, margin)
        for box in boxes:
            target = encode(box, 3)
            for raw, fixed, alpha, value in zip(
                slopes, repaired, alphas, values, strict=True
            ):
                assert (
                    predict(fixed, alpha, value, target)
                    <= predict(raw, alpha, value, target) + 1e-9
                )


def test_what_the_nonnegative_repair_gives_up() -> None:
    """Check what the fix costs: the exact margin at every box solved.

    The released repair lowers every cut by exactly the margin at the other boxes
    solved, and pays for it by raising the third cut at the box nobody solved.
    The fix refuses the raise, so it cannot lower every cut by the whole margin
    at every box solved: it lowers them by most of it, and by nothing negative.
    """
    alphas = [encode(box) for box in SOLVED]
    slopes = [zeros((1, alphas[0].size)) for _ in alphas]
    values = [0.0] * len(alphas)
    released = released_repair(alphas, slopes, values, 10.0)
    fixed = repair_nonnegatively(alphas, slopes, values, 10.0)
    lowered = []
    for cut, exact, alpha in zip(fixed, released, alphas, strict=True):
        for other in alphas:
            if (other != alpha).any():
                assert predict(exact, alpha, 0.0, other) == pytest.approx(-10.0)
                lowered.append(predict(cut, alpha, 0.0, other))

    assert max(lowered) < 0.0
    assert min(lowered) <= -10.0 + 1e-6
    assert predict(released[2], alphas[2], 0.0, encode(UNSOLVED)) == pytest.approx(10.0)
    assert predict(fixed[2], alphas[2], 0.0, encode(UNSOLVED)) <= 1e-9


def test_the_convexification_never_raises_a_cut() -> None:
    """Check that the constant lowers a cut by two per component changed."""
    alphas = [encode(box, 3) for box in product(range(3), repeat=2)]
    for alpha, target in product(alphas, repeat=2):
        changed = int(((alpha - target) != 0).sum()) // 2
        assert convexification_sensitivity([alpha], target, 2)[0] == pytest.approx(
            -2.0 * changed / 2
        )


def test_the_repair_is_put_back() -> None:
    """Check that the fix is installed for the context only."""
    original = core.OuterApproximationOptimizer._update_sensitivities_wt_secant_method
    with nonnegative_repair():
        assert (
            core.OuterApproximationOptimizer._update_sensitivities_wt_secant_method
            is not original
        )

    assert (
        core.OuterApproximationOptimizer._update_sensitivities_wt_secant_method
        is original
    )


def test_the_recording_is_put_back() -> None:
    """Check that recording leaves the solve of the master as it found it."""
    original = core.OuterApproximationOptimizer._solve_milp
    with recording(10) as record:
        assert core.OuterApproximationOptimizer._solve_milp is not original

    assert core.OuterApproximationOptimizer._solve_milp is original
    assert record.termination == "no new candidate, or the budget"
