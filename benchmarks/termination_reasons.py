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
"""Count the stopping criteria that end the runs of the configuration.

The configuration compared with the baselines is run on the four problems from
the twenty starting points, and the message of the master announcing its end is
read, whatever the logging settings of the run:

- ``lower bound``: the smallest optimal value of the master problems of the
  probes exceeds the incumbent value plus the tolerance;
- ``stall``: the incumbent has not changed for ``upper_bound_stall`` iterations;
- ``no new box``: every box proposed by the probes has already been solved;
- ``infeasible``: no admissible box remains for any probe;
- ``iterations``: the iteration limit of the master;
- ``budget``: the budget of evaluations is spent first.

    python -m benchmarks.termination_reasons
"""

from __future__ import annotations

import json
import logging
import warnings
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

from benchmarks import data_profiles
from benchmarks.run_statistics import COMPARED
from benchmarks.run_statistics import SEEDS

OUTPUT = data_profiles.OUTPUT.with_name("termination_reasons.json")
"""The file of the counts."""

MESSAGES = {
    "eta*": "lower bound",
    "stopped changing": "stall",
    "Infeasible MILP": "infeasible",
    "Maximum iteration reached": "iterations",
    "stopped proposing different new candidates": "no new box",
}
"""The stopping criterion announced by each message of the master."""


class _Recorder:
    """A stand-in of the logger of the master, keeping its messages."""

    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger
        self.messages: list[str] = []

    def info(self, message, *args, **kwargs) -> None:  # noqa: ANN001, ANN002, ANN003, D102
        self.messages.append(str(message))

    def __getattr__(self, name: str):  # noqa: ANN204
        return getattr(self.logger, name)


def run_one(task: tuple[str, int, int]) -> tuple[str, int, int, str]:
    """Run the configuration once and return the criterion that ended it.

    Args:
        task: The problem, the dimension and the seed.

    Returns:
        The problem, the dimension, the seed and the criterion.
    """
    from gemseo_bilevel_outer_approximation.algos.opt.core import (  # noqa: PLC0415
        outer_approximation_optimizer as core,
    )

    from benchmarks.data_profiles import _run  # noqa: PLC0415

    problem, dimension, seed = task
    recorder = _Recorder(core.LOGGER)
    core.LOGGER = recorder
    try:
        result = _run((COMPARED[dimension], problem, dimension, seed))
    finally:
        core.LOGGER = recorder.logger
    reason = "budget" if result.cost_adjoint >= result.budget else "unknown"
    for message in recorder.messages:
        for key, name in MESSAGES.items():
            if key in message:
                reason = name
                break
        if reason != "unknown" and "End of Outer" in message:
            break
    if result.cost_adjoint >= result.budget:
        reason = "budget"
    return problem, dimension, seed, reason


def main() -> None:
    """Count the criteria of every run and write them."""
    logging.disable(logging.CRITICAL)
    warnings.simplefilter("ignore")
    tasks = [
        (problem, dimension, seed)
        for dimension in data_profiles.DIMENSIONS
        for problem in data_profiles.PROBLEM_NAMES
        for seed in SEEDS
    ]
    with ProcessPoolExecutor() as executor:
        outcomes = list(executor.map(run_one, tasks))
    output = {}
    for dimension in data_profiles.DIMENSIONS:
        output[str(dimension)] = {
            problem: dict(
                Counter(r for p, d, _, r in outcomes if p == problem and d == dimension)
            )
            for problem in data_profiles.PROBLEM_NAMES
        }
        print(dimension, output[str(dimension)])  # noqa: T201
    OUTPUT.write_text(json.dumps(output, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
