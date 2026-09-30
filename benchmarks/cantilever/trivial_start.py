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

import sys
from pathlib import Path

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
sc2d.main()
