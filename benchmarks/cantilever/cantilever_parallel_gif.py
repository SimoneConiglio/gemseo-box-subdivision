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

"""Animate a box-subdivision run whose probes are solved in parallel.

Reads the solves ``trivial_start.py --record`` kept, one file per process,
cuts each process's stream into boxes where the subdivided poses restart at the
centres of their boxes, and groups the boxes into the master's rounds by when
they start. Each frame shows the probes of a round as they are being solved,
the best feasible design so far, and the best compliance against the designs
analysed in all, beside MMA from the same start. Run in the GGP environment,
from the GGP repository, with the preset the run used:

    python <this repository>/benchmarks/cantilever/cantilever_parallel_gif.py \
        <record prefix> benchmarks/box_subdivision_mna/mma_mna.json \
        <this repository>/docs/_static/figures --preset short_cantilever_mna
"""

from __future__ import annotations

import json
import sys
from io import BytesIO
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path("benchmarks").resolve()))
import sc2d_box_subdivision as sc2d  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "docs"))
import operator

import figures  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from PIL import Image  # noqa: E402

K = 10
"""The subdivisions of each pose variable."""

PROBES = 9
"""The probes of each round of the master, the most a round can hold."""


ROUND_GAP = 60.0
"""The seconds between the starts of boxes beyond which they are two rounds."""

FRAMES_PER_ROUND = 6
"""The frames drawn inside each round."""

TOLERANCE = 1e-6
"""The volume violation under which a design is feasible."""


def load(prefix: str) -> list[np.ndarray]:
    """Return the solves of each process, a row per solve."""
    streams = []
    for path in sorted(Path(prefix).parent.glob(Path(prefix).name + ".*.bin")):
        rows = np.fromfile(path, dtype=np.float64)
        width = 3 + 18 * sc2d.VPC
        streams.append(rows[: rows.size // width * width].reshape(-1, width))
    return streams


def box_starts(x: np.ndarray, split: np.ndarray) -> list[int]:
    """Return the index of the first design of each box of one process."""
    poses = x[:, split]
    at_centre = np.all(
        np.isclose(poses * K - np.floor(poses * K), 0.5, atol=1e-4), axis=1
    )
    starts = [0]
    for index in np.flatnonzero(at_centre):
        # A box restarts at its centre once; the next centre starts a new box.
        if index > starts[-1] + 5:
            starts.append(int(index))
    return starts


def density_image(geometry, design: np.ndarray, coords: np.ndarray) -> np.ndarray:
    """Return the density of a design on the 60 by 30 grid of the mesh."""
    geometry.execute({"x_vars": design.astype(float)})
    rho = np.asarray(geometry.local_data["rho_V"]).ravel()
    image = np.zeros((30, 60))
    image[np.floor(coords[:, 1]).astype(int), np.floor(coords[:, 0]).astype(int)] = rho
    return image


def best_feasible(compliance: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """Return the best feasible compliance after each solve, in compliance."""
    feasible = np.where(volume <= TOLERANCE, np.expm1(compliance), np.inf)
    return np.minimum.accumulate(feasible)


def main() -> None:  # noqa: C901, PLR0915
    """Draw the animation of the recorded run, in both themes."""
    preset = "short_cantilever"
    if "--preset" in sys.argv:
        index = sys.argv.index("--preset")
        preset = sys.argv[index + 1]
        del sys.argv[index : index + 2]
    prefix, mma_path, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    sc2d.select_preset(preset)
    spec = sc2d.load_spec()
    geometry, _, _, _ = sc2d.build_disciplines(spec)
    coords = np.asarray(geometry.eval_coords)
    split = sc2d.split_indices("layout", 18, spec.formulation.num_components)

    # Every solve of every process, in the order they happened, with its box.
    boxes = []
    for stream in load(prefix):
        starts = box_starts(stream[:, 3:], split)
        for start, end in zip(starts, [*starts[1:], len(stream)], strict=True):
            boxes.append(stream[start:end])
    boxes.sort(key=operator.itemgetter((0, 0)))
    rows = np.vstack([
        np.column_stack((box, np.full(len(box), number)))
        for number, box in enumerate(boxes)
    ])
    rows = rows[np.argsort(rows[:, 0], kind="stable")]
    _when, log_c, volume, x = rows[:, 0], rows[:, 1], rows[:, 2], rows[:, 3:-1]
    box_of = rows[:, -1].astype(int)
    compliance = np.expm1(log_c)
    feasible = volume <= TOLERANCE
    best = best_feasible(log_c, volume)
    best_index = np.zeros(len(rows), dtype=int)
    current = -1
    for i in range(len(rows)):
        if feasible[i] and (current < 0 or compliance[i] < compliance[current]):
            current = i
        best_index[i] = current

    # The boxes of a round start together, those of the next once all are
    # solved; the first box is the master's start, a round of its own.
    rounds = [[0]]
    for number in range(1, len(boxes)):
        if boxes[number][0, 0] - boxes[rounds[-1][0]][0, 0] > ROUND_GAP:
            rounds.append([])
        rounds[-1].append(number)

    # The last solve of each box, to frame a round from its first start to it.
    last = {
        number: int(np.flatnonzero(box_of == number)[-1])
        for number in range(len(boxes))
    }
    first = {
        number: int(np.flatnonzero(box_of == number)[0]) for number in range(len(boxes))
    }
    frames = []
    for number, members in enumerate(rounds):
        begin = min(first[m] for m in members)
        end = max(last[m] for m in members)
        steps = np.linspace(begin, end, FRAMES_PER_ROUND + 1)[1:].astype(int)
        frames.extend((number, members, int(step)) for step in steps)

    mma = json.loads(mma_path.read_text())
    mma_best = best_feasible(
        np.asarray(mma["history"])[1::2], np.asarray(mma["volume_history"])[1::2]
    )
    designs = np.arange(1, len(rows) + 1)

    images = {}

    def image_of(index: int) -> np.ndarray:
        if index not in images:
            images[index] = density_image(geometry, x[index], coords)
        return images[index]

    for suffix, foreground in (("", figures.LIGHT), ("-dark", figures.DARK)):
        rendered = []
        style = {
            **figures._style(foreground),
            "savefig.transparent": False,
            "savefig.facecolor": figures.BACKGROUNDS[foreground],
        }
        cmap = "Greys" if foreground == figures.LIGHT else "Greys_r"
        with plt.rc_context(style):
            for number, members, step in frames:
                figure = plt.figure(figsize=(11.0, 4.6))
                figure.set_facecolor(figures.BACKGROUNDS[foreground])
                grid = figure.add_gridspec(
                    3,
                    5,
                    width_ratios=(1.0, 1.0, 1.0, 0.25, 2.9),
                    wspace=0.08,
                    hspace=0.35,
                    left=0.01,
                    right=0.99,
                    top=0.88,
                    bottom=0.11,
                )
                for slot in range(PROBES):
                    axes = figure.add_subplot(grid[slot // 3, slot % 3])
                    axes.set_xticks([])
                    axes.set_yticks([])
                    if slot < len(members):
                        box = members[slot]
                        solved = np.flatnonzero((box_of == box) & (designs <= step + 1))
                        if solved.size:
                            index = int(solved[-1])
                            axes.imshow(
                                image_of(index),
                                origin="lower",
                                cmap=cmap,
                                vmin=0.0,
                                vmax=max(image_of(index).max(), 1e-9),
                                extent=(0, 60, 0, 30),
                            )
                            done = index == last[box]
                            # A finished box reads its optimum; the best is
                            # drawn in the accent, an infeasible design starred.
                            axes.set_title(
                                f"box {box + 1}: C = {compliance[index]:.1f}"
                                + ("" if feasible[index] else "*")
                                + (", done" if done else ""),
                                fontsize=7.5,
                                **(
                                    {"color": figures.ACCENT}
                                    if index == best_index[step]
                                    else {}
                                ),
                            )
                    for spine in axes.spines.values():
                        spine.set_visible(slot < len(members))
                round_name = (
                    "the first box, at the start"
                    if number == 0
                    else f"round {number} of {len(rounds) - 1}: "
                    f"boxes {members[0] + 1} to {members[-1] + 1} in parallel"
                )
                figure.text(0.25, 0.97, round_name, ha="center", va="top", fontsize=9)

                right = grid[:, 4].subgridspec(
                    2, 1, height_ratios=(1.0, 1.3), hspace=0.4
                )
                best_axes = figure.add_subplot(right[0])
                if best_index[step] >= 0:
                    best_axes.imshow(
                        image_of(int(best_index[step])),
                        origin="lower",
                        cmap=cmap,
                        vmin=0.0,
                        vmax=1.0,
                        extent=(0, 60, 0, 30),
                    )
                    best_axes.set_title(
                        f"best feasible so far: C = {best[step]:.1f}, "
                        f"box {box_of[best_index[step]] + 1}",
                        fontsize=9,
                    )
                best_axes.set_xticks([])
                best_axes.set_yticks([])

                curve = figure.add_subplot(right[1])
                finite = np.isfinite(best)
                curve.plot(
                    designs[finite],
                    best[finite],
                    color=foreground,
                    alpha=0.15,
                    linewidth=1.2,
                )
                shown = finite & (designs <= step + 1)
                curve.plot(
                    designs[shown],
                    best[shown],
                    color=figures.ACCENT,
                    linewidth=1.8,
                    label="nine probes in parallel",
                )
                steps = np.arange(1, len(mma_best) + 1)
                finite_mma = np.isfinite(mma_best)
                curve.plot(
                    steps[finite_mma],
                    mma_best[finite_mma],
                    color=figures.SECOND,
                    linestyle="--",
                    linewidth=1.2,
                    label=f"MMA, same start: {mma_best[-1]:.1f}",
                )
                curve.axhline(
                    mma_best[-1],
                    color=figures.SECOND,
                    alpha=0.35,
                    linestyle=":",
                    linewidth=1.0,
                )
                # The descent is in the first designs, the search in the rest.
                curve.set_xscale("log")
                curve.set_xlim(50, len(rows))
                curve.set_ylim(np.floor(best[-1]) - 1, np.ceil(mma_best[-1]) + 8)
                curve.set_xlabel("designs analysed, all processes", fontsize=8)
                curve.set_ylabel("best feasible C", fontsize=8)
                curve.tick_params(labelsize=7)
                curve.legend(fontsize=7, loc="upper right")
                curve.grid(alpha=0.25)

                buffer = BytesIO()
                figure.savefig(buffer, format="png", dpi=80)
                plt.close(figure)
                buffer.seek(0)
                rendered.append(Image.open(buffer).convert("RGB"))

        palette = rendered[-1].quantize(colors=128, method=Image.Quantize.MEDIANCUT)
        quantized = [
            frame.quantize(palette=palette, dither=Image.Dither.NONE)
            for frame in rendered
        ]
        durations = [600] * (len(quantized) - 1) + [4000]
        quantized[0].save(
            out / f"cantilever{suffix}.gif",
            save_all=True,
            append_images=quantized[1:],
            duration=durations,
            loop=0,
            optimize=True,
        )
        print(
            f"cantilever{suffix}.gif: {len(quantized)} frames, {len(boxes)} boxes, "
            f"{len(rounds) - 1} rounds, best {best[-1]:.2f}"
        )


if __name__ == "__main__":
    main()
