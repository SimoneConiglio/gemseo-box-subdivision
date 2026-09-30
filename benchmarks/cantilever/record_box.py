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

"""Rerun the trivial-start box run, keeping every design it analysed.

The same run as ``trivial_start.py`` with the arguments given, plus a file
``<out>/<tag>_designs.npz`` holding each design, its compliance and its volume,
in the order the FE solves happened, which is what the animation draws.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path("benchmarks").resolve()))
import sc2d_box_subdivision as sc2d

TRIVIAL = {2: 0.5, 3: 0.5, 5: 0.5}
histories = []
original_history = sc2d._History


OUT = Path(sys.argv[sys.argv.index("--out") + 1])
TAG = sys.argv[sys.argv.index("--tag") + 1]


def dump(history) -> None:
    """Write the designs analysed so far, so that a run cut short leaves them."""
    np.savez_compressed(
        OUT / f"{TAG}_designs.npz",
        x=np.asarray(history.x, dtype=np.float32),
        compliance=np.asarray(history.compliance),
        volume=np.asarray(history.volume),
    )


class Recorded(original_history):
    """The history of the run, dumping its designs every 500 solves."""

    def __init__(self, geometry, physics):  # noqa: ANN001, D107
        super().__init__(geometry, physics)
        histories.append(self)
        recorded = physics._run

        def _run(input_data=None):
            out = recorded(input_data)
            if len(self.x) % 500 == 0:
                dump(self)
            return out

        physics._run = _run


sc2d._History = Recorded
original_build = sc2d.build_disciplines


def build_disciplines(spec):  # noqa: ANN001, ANN201
    """Build the disciplines, starting from the trivial design."""
    geometry, physics, x_init, domain = original_build(spec)
    x_init = x_init.copy()
    for slot, value in TRIVIAL.items():
        x_init[slot :: sc2d.VPC] = value
    return geometry, physics, x_init, domain


sc2d.build_disciplines = build_disciplines
sc2d.main()
dump(histories[0])
print(f"designs written: {len(histories[0].x)}")
