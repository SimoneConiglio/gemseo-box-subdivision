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

"""Animate the box-subdivision run on the SC 2D cantilever, per theme.

Reads the designs ``record_box.py`` kept, finds where each box starts, the
first design whose subdivided poses all sit at the centres of their boxes, and
draws a few frames per box: the design being solved, the best feasible design
so far, and the best compliance against the designs spent, beside MMA from the
same start and from the preset's. Run in the GGP environment, from the GGP
repository:

    python <this repository>/benchmarks/cantilever/cantilever_gif.py \
        benchmarks/box_subdivision_trivial/box_trivial_1800_recorded_designs.npz \
        <this repository>/docs/_static/figures
"""

from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path("benchmarks").resolve()))
import sc2d_box_subdivision as sc2d  # noqa: E402

FIGURES = Path(__file__).resolve().parents[2] / "docs"
sys.path.insert(0, str(FIGURES))
import figures  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from PIL import Image  # noqa: E402

K = 10
"""The subdivisions of each pose variable."""

MMA_TRIVIAL = 4.664
"""Where plain MMA converges from the same trivial start."""

MMA_PRESET = 4.321
"""Where plain MMA converges from the preset's start."""

FRAMES_PER_BOX = 5
"""The frames drawn inside each box."""

TOLERANCE = 1e-6
"""The volume violation under which a design is feasible."""


def box_starts(x: np.ndarray, split: np.ndarray) -> list[int]:
    """Return the index of the first design of each box."""
    poses = x[:, split].astype(float)
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
    rho = np.asarray(geometry.local_data["rho_E"]).ravel()
    image = np.zeros((30, 60))
    image[np.floor(coords[:, 1]).astype(int), np.floor(coords[:, 0]).astype(int)] = rho
    return image


def main() -> None:
    """Draw the frames of each theme and write the two animations."""
    data = np.load(sys.argv[1])
    out = Path(sys.argv[2])
    x, compliance, volume = data["x"], data["compliance"], data["volume"]
    # MMA from the same start: two solves per design, the value then the gradient.
    import json

    mma = json.loads((Path(sys.argv[1]).parent / "mma_trivial.json").read_text())
    mma_c = np.asarray(mma["history"])[1::2]
    mma_v = np.asarray(mma["volume_history"])[1::2]
    mma_best = np.minimum.accumulate(np.where(mma_v <= TOLERANCE, mma_c, np.inf))
    spec = sc2d.load_spec()
    geometry, _, _, _ = sc2d.build_disciplines(spec)
    coords = np.asarray(geometry.eval_coords)
    split = sc2d.split_indices("layout", 18, spec.formulation.num_components)
    starts = box_starts(x, split)
    ends = [*starts[1:], len(x)]

    feasible = volume <= TOLERANCE
    best = np.minimum.accumulate(np.where(feasible, compliance, np.inf))
    best_index = np.zeros(len(x), dtype=int)
    current = -1
    for i in range(len(x)):
        if feasible[i] and (current < 0 or compliance[i] < compliance[current]):
            current = i
        best_index[i] = current

    frames = []
    for box, (start, end) in enumerate(zip(starts, ends, strict=True), 1):
        steps = np.linspace(start, end - 1, FRAMES_PER_BOX).astype(int)
        frames.extend((box, int(step)) for step in steps)

    images = {}
    for suffix, foreground in (("", figures.LIGHT), ("-dark", figures.DARK)):
        rendered = []
        style = {
            **figures._style(foreground),
            "savefig.transparent": False,
            "savefig.facecolor": figures.BACKGROUNDS[foreground],
        }
        with plt.rc_context(style):
            for box, step in frames:
                key = ("current", step)
                if key not in images:
                    images[key] = density_image(geometry, x[step], coords)
                if best_index[step] >= 0 and ("best", best_index[step]) not in images:
                    images["best", best_index[step]] = density_image(
                        geometry, x[best_index[step]], coords
                    )

                figure = plt.figure(figsize=(10.4, 3.9))
                figure.set_facecolor(figures.BACKGROUNDS[foreground])
                grid = figure.add_gridspec(2, 2, width_ratios=(1.0, 1.1))
                current_axes = figure.add_subplot(grid[0, 0])
                best_axes = figure.add_subplot(grid[1, 0])
                curve = figure.add_subplot(grid[:, 1])
                cmap = "Greys" if foreground == figures.LIGHT else "Greys_r"
                for axes, image, title in (
                    (
                        current_axes,
                        images[key],
                        f"box {box} of {len(starts)}: design "
                        f"{step + 1 - starts[box - 1]}"
                        f", C = {compliance[step]:.3f}"
                        + ("" if feasible[step] else ", infeasible"),
                    ),
                    (
                        best_axes,
                        images.get(("best", best_index[step])),
                        f"best feasible so far: C = {best[step]:.3f}"
                        if np.isfinite(best[step])
                        else "no feasible design yet",
                    ),
                ):
                    if image is not None:
                        axes.imshow(
                            image,
                            origin="lower",
                            cmap=cmap,
                            vmin=0.0,
                            vmax=max(image.max(), 1e-9),
                            extent=(0, 60, 0, 30),
                        )
                    axes.set_title(title, fontsize=8.5)
                    axes.set_xticks([])
                    axes.set_yticks([])
                    axes.set_aspect("equal")
                    for spine in axes.spines.values():
                        spine.set_visible(True)

                designs = np.arange(1, len(x) + 1)
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
                    label="box subdivision, trivial start",
                )
                for boundary in starts[1:box]:
                    curve.axvline(boundary, color=foreground, alpha=0.2, linewidth=0.6)
                steps = np.arange(1, len(mma_best) + 1)
                shown_mma = np.isfinite(mma_best) & (steps <= step + 1)
                curve.plot(
                    steps[shown_mma],
                    mma_best[shown_mma],
                    color=figures.SECOND,
                    linestyle="--",
                    linewidth=1.4,
                    label=f"MMA, trivial start: converges at {MMA_TRIVIAL}",
                )
                if step + 1 >= len(mma_best):
                    curve.plot(
                        len(mma_best),
                        mma_best[-1],
                        marker="o",
                        color=figures.SECOND,
                        markersize=4,
                    )
                    curve.axhline(
                        MMA_TRIVIAL,
                        color=figures.SECOND,
                        alpha=0.35,
                        linestyle=":",
                        linewidth=1.0,
                    )
                curve.axhline(
                    MMA_PRESET,
                    color=figures.THIRD,
                    linestyle=":",
                    linewidth=1.4,
                    label=f"MMA, preset start: {MMA_PRESET}",
                )
                curve.set_xlim(0, len(x))
                curve.set_ylim(4.2, 6.2)
                curve.set_xlabel("designs analysed")
                curve.set_ylabel("best feasible compliance")
                curve.legend(fontsize=7.5, loc="upper right")
                curve.grid(alpha=0.25)
                figure.tight_layout()

                buffer = BytesIO()
                figure.savefig(buffer, format="png", dpi=90)
                plt.close(figure)
                buffer.seek(0)
                rendered.append(Image.open(buffer).convert("RGB"))

        palette = rendered[-1].quantize(colors=128, method=Image.Quantize.MEDIANCUT)
        quantized = [
            frame.quantize(palette=palette, dither=Image.Dither.NONE)
            for frame in rendered
        ]
        durations = [700] * (len(quantized) - 1) + [4000]
        quantized[0].save(
            out / f"cantilever{suffix}.gif",
            save_all=True,
            append_images=quantized[1:],
            duration=durations,
            loop=0,
            optimize=True,
        )
        print(f"cantilever{suffix}.gif: {len(quantized)} frames, {len(starts)} boxes")


if __name__ == "__main__":
    main()
