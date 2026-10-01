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

"""Run the SC 2D benchmark from a trivial guess of the monotone variables.

The pose of every bar (Xc, Yc, theta) is kept from the preset; the length is
uniform and the thickness and the density are at the middle of their ranges,
in the normalized variables the GGP disciplines take.
"""

from __future__ import annotations

import dataclasses
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path("benchmarks").resolve()))
import sc2d_box_subdivision as sc2d

TRIVIAL = {2: 0.5, 3: 0.5, 5: 0.5}
"""The normalized value of the length, the thickness and the density."""

original = sc2d.build_disciplines

PRESET = "--preset" in sys.argv
"""Whether to keep the preset's starting design, the reference run."""
if PRESET:
    sys.argv.remove("--preset")


def build_disciplines(spec):  # noqa: ANN001, ANN201
    """Build the disciplines, starting from the trivial design unless --preset."""
    geometry, physics, x_init, domain = original(spec)
    x_init = x_init.copy()
    if not PRESET:
        for slot, value in TRIVIAL.items():
            x_init[slot :: sc2d.VPC] = value
    return geometry, physics, x_init, domain


sc2d.build_disciplines = build_disciplines

# The preset's options are MMA's (asymptotes, move limit), and the script hands
# them to whichever sub-solver it is given: another one runs on its defaults.
if "--sub-algo" in sys.argv and sys.argv[sys.argv.index("--sub-algo") + 1] != "MMA":
    original_load_spec = sc2d.load_spec

    def load_spec(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        """Load the preset, without the options of MMA."""
        spec = original_load_spec(*args, **kwargs)
        return dataclasses.replace(
            spec, solver=dataclasses.replace(spec.solver, options={})
        )

    sc2d.load_spec = load_spec
# Spreading the probes over processes needs the fix of
# gemseo-bilevel-outer-approximation's merge request 139, which brings the
# workers' results back to the master; without it the master stops after
# its first box.
# The master solves its probes one after the other unless told how many
# processes to spread them over, and it is never told: --processes tells it.
# A forked worker's evaluations never reach the history of this process, so a
# parallel run is read off the master's database instead, which the adapter of
# each box writes its optimum and its evaluation count into.
PROCESSES = 1
if "--processes" in sys.argv:
    index = sys.argv.index("--processes")
    PROCESSES = int(sys.argv[index + 1])
    del sys.argv[index : index + 2]

    from gemseo_box_subdivision import BoxSubdivisionScenario
    from gemseo_box_subdivision import SweptBoxSubdivisionSettings

    original_settings = SweptBoxSubdivisionSettings.to_master_settings

    def to_master_settings(self, radius=None):  # noqa: ANN001, ANN202
        """Return the settings of the master, its probes spread over processes."""
        return {**original_settings(self, radius), "number_of_processes": PROCESSES}

    SweptBoxSubdivisionSettings.to_master_settings = to_master_settings
    scenarios = []
    original_execute = BoxSubdivisionScenario.execute

    def execute(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        """Execute the scenario, keeping it to read its master afterwards."""
        scenarios.append(self)
        return original_execute(self, *args, **kwargs)

    BoxSubdivisionScenario.execute = execute
    original_best = sc2d._History.best

    def best(self, tolerance=1e-6):  # noqa: ANN001, ANN202
        """Return the best feasible design this process saw, if any."""
        try:
            return original_best(self, tolerance)
        except RuntimeError:
            return float("nan"), np.asarray(self.x[-1]), -1

    sc2d._History.best = best

# --record PREFIX appends every FE solve, of this process and of each forked
# worker, to PREFIX.<pid>.bin: the time, the compliance, the volume and the
# design, which is what the animation of a parallel run draws.
if "--record" in sys.argv:
    index = sys.argv.index("--record")
    RECORD = sys.argv[index + 1]
    del sys.argv[index : index + 2]
    original_init = sc2d._History.__init__

    def __init__(self, geometry, physics):  # noqa: ANN001, D107
        original_init(self, geometry, physics)
        recorded = physics._run

        def _run(input_data=None):  # noqa: ANN001, ANN202
            out = recorded(input_data)
            row = np.concatenate((
                [time.time(), self.compliance[-1], self.volume[-1]],
                np.asarray(self.x[-1], dtype=float),
            ))
            with open(f"{RECORD}.{os.getpid()}.bin", "ab") as file:
                file.write(row.astype(np.float64).tobytes())
            return out

        physics._run = _run

    sc2d._History.__init__ = __init__

try:
    sc2d.main()
finally:
    if PROCESSES > 1 and scenarios:
        import json

        values, evaluations = [], 0
        database = scenarios[0].formulation.optimization_problem.database
        for entry in database.values():
            if entry.get("compliance") is not None:
                values.append(float(np.ravel(entry["compliance"])[0]))
            if entry.get("iterations") is not None:
                evaluations += int(np.ravel(entry["iterations"])[0])
        report = {
            "boxes": len(values),
            "box_optima": values,
            "best": min(values) if values else None,
            "sub_problem_evaluations": evaluations,
        }
        print("master database:", json.dumps(report))
