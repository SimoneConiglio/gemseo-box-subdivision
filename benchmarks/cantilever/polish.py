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
"""Polish the best design of a box-subdivision run without the box bounds.

The best feasible design of a run of ``port_box_subdivision.py``, up to a number
of designs, is the solution of a sub-problem restricted to its box, and may lie
on a face of the box. It is used as the starting point of MMA over the whole
design space, with the settings of the sub-problems, and the compliance before
and after is printed, with the number of design variables of the subdivided
poses lying on a face of their box:

    python benchmarks/cantilever/polish.py --backend ggp_mna_port.py \
        --out runs/probes_9 --budget 55995
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classic_tunneling import MMA_OPTIONS  # noqa: E402
from classic_tunneling import TOLERANCE  # noqa: E402
from classic_tunneling import mma  # noqa: E402
from port_box_subdivision import POSE  # noqa: E402
from port_box_subdivision import VPC  # noqa: E402
from port_box_subdivision import load_problem  # noqa: E402
from port_box_subdivision import summarize  # noqa: E402


def main() -> None:
    """Polish the best design of a run and print the compliances."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--budget", type=int)
    parser.add_argument("--n-subdivisions", type=int, default=10)
    parser.add_argument("--max-iter", type=int, default=1800)
    args = parser.parse_args()
    problem = load_problem(args.backend)
    size = problem.x_init.size
    summary = summarize(args.out, size, args.budget)
    start = np.array(summary["x_best"])
    split = np.array([c * VPC + s for c in range(size // VPC) for s in POSE])
    scaled = start[split] * args.n_subdivisions
    on_face = int(np.sum(np.abs(scaled - np.round(scaled)) < 1e-6))

    def evaluate(x: np.ndarray) -> dict:
        return problem.physics(np.clip(np.asarray(x, float), 0.0, 1.0))

    visited = mma(evaluate, start, dict(MMA_OPTIONS), args.max_iter)
    # The objective is log(C + 1), so that the compliance follows from it.
    feasible = [float(np.expm1(f)) for _, f, g in visited if g <= TOLERANCE]
    best = (min(feasible) if feasible else float("nan"), len(visited))
    print(  # noqa: T201
        json.dumps({
            "compliance_before": summary["best_compliance"],
            "compliance_after": best[0],
            "poses_on_a_face": on_face,
            "subdivided_variables": int(split.size),
            "designs": len(visited),
        })
    )


if __name__ == "__main__":
    main()
