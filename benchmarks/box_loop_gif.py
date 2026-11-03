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

"""Schematic animation of the box-subdivision outer approximation on Rastrigin 2D.

A simplified re-enactment of the loop, not a run of the package. Usage:

    python benchmarks/box_loop_gif.py docs/_static/figures/box-loop.gif 20

10 x 10 boxes; each iteration the master picks the box whose cut-based lower
bound is smallest, a projected-gradient local solver optimizes inside it, and the
solution adds a cut that raises the lower bound of the other boxes.
"""

from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle
from PIL import Image

OUT = Path(sys.argv[1])
KAPPA = float(sys.argv[2]) if len(sys.argv) > 2 else 12.0

LO, HI, M = -4.62, 5.62, 10
W = (HI - LO) / M
EDGES = LO + W * np.arange(M + 1)
CENTRES = EDGES[:-1] + W / 2

BG, INK, SOFT = "#F6F5F0", "#14213D", "#5A6474"
ORANGE, BLUE, GREY = "#E07A2F", "#2F6FB0", "#C9CCD3"


def f(x):
    return 20 + np.sum(x**2 - 10 * np.cos(2 * np.pi * x), axis=-1)


def grad(x):
    return 2 * x + 20 * np.pi * np.sin(2 * np.pi * x)


def local_solve(box):
    lo = EDGES[list(box)]
    hi = lo + W
    x = np.array([CENTRES[box[0]], CENTRES[box[1]]]) + np.array([0.33, -0.3]) * W
    path = [x.copy()]
    step = 0.004
    for _ in range(400):
        x_new = np.clip(x - step * grad(x), lo, hi)
        if np.linalg.norm(x_new - x) < 1e-7:
            break
        x = x_new
        path.append(x.copy())
    return x, np.array(path)


def lower_bounds(cuts):
    """Max over cuts of f_k + sum_j [b_j != k_j] (g_kj (c_bj - x_kj) - kappa)."""
    lb = np.full((M, M), -np.inf)
    for box, x, fx, g in cuts:
        dj = [
            np.where(np.arange(M) == box[j], 0.0, g[j] * (CENTRES - x[j]) - KAPPA)
            for j in range(2)
        ]
        lb = np.maximum(lb, fx + dj[0][:, None] + dj[1][None, :])
    return lb


def run(start=(1, 7)):
    cuts, solved, history = [], {}, []
    box = start
    while True:
        x, path = local_solve(box)
        fx = float(f(x))
        g = grad(x)
        cuts.append((box, x, fx, g))
        solved[box] = (x, fx)
        lb = lower_bounds(cuts)
        for b in solved:
            lb[b] = np.inf
        best = min(v[1] for v in solved.values())
        history.append((box, path, x, fx, lb.copy(), best))
        nxt = np.unravel_index(np.argmin(lb), lb.shape)
        if lb[nxt] >= best - 1e-6 or len(solved) == M * M:
            break
        box = (int(nxt[0]), int(nxt[1]))
    return history


GX = np.linspace(LO, HI, 400)
XX, YY = np.meshgrid(GX, GX, indexing="ij")
FF = f(np.stack([XX, YY], axis=-1))


def frame(history, it, phase, path_frac=1.0):
    """phase: 'pick', 'solve', 'cut'."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 6), dpi=100, facecolor=BG)
    fig.subplots_adjust(left=0.03, right=0.97, top=0.80, bottom=0.03, wspace=0.08)
    box, path, x, fx, lb, best = history[it]
    done = history[:it] if phase != "cut" else history[: it + 1]

    ax = axes[0]
    ax.set_facecolor(BG)
    ax.contourf(XX, YY, FF, levels=18, cmap="Blues_r", alpha=0.35)
    for e in EDGES:
        ax.axhline(e, color="white", lw=0.8)
        ax.axvline(e, color="white", lw=0.8)
    for b, _, xs, fs, _, _ in done:
        ax.add_patch(Rectangle((EDGES[b[0]], EDGES[b[1]]), W, W, fc=INK, alpha=0.18, ec="none"))
        ax.plot(*xs, "o", ms=5, color=INK)
    if phase in ("pick", "solve", "cut"):
        ax.add_patch(Rectangle((EDGES[box[0]], EDGES[box[1]]), W, W, fc="none", ec=ORANGE, lw=3))
    if phase in ("solve", "cut"):
        n = max(2, int(len(path) * path_frac))
        ax.plot(path[:n, 0], path[:n, 1], "-", color=ORANGE, lw=2.2)
        ax.plot(*path[n - 1], "o", ms=8, color=ORANGE, mec="white")
    if phase == "cut":
        bi = min(range(it + 1), key=lambda k: history[k][3])
        ax.plot(*history[bi][2], "*", ms=20, color=ORANGE, mec=INK, mew=1)
    ax.set_xlim(LO, HI)
    ax.set_ylim(LO, HI)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title("Design space: 10 × 10 boxes on Rastrigin", color=INK, fontsize=15, loc="left")

    ax = axes[1]
    ax.set_facecolor(BG)
    prev = history[it - 1] if it > 0 else None
    show_lb = lb if phase == "cut" else (prev[4] if prev else None)
    cur_best = best if phase == "cut" else (prev[5] if prev else np.inf)
    img = np.ones((M, M, 3)) * np.array(matplotlib.colors.to_rgb(BG))
    if show_lb is not None:
        pruned = matplotlib.colors.to_rgb(GREY)
        cand = matplotlib.colors.to_rgb(BLUE)
        for i in range(M):
            for j in range(M):
                v = show_lb[i, j]
                if np.isinf(v):
                    img[j, i] = matplotlib.colors.to_rgb(INK)
                elif v >= cur_best - 1e-6:
                    img[j, i] = pruned
                else:
                    a = np.clip((cur_best - v) / (2 * KAPPA + 30), 0.25, 1.0)
                    img[j, i] = (1 - a) * np.array(matplotlib.colors.to_rgb(BG)) + a * np.array(cand)
    ax.imshow(img, origin="lower", extent=(LO, HI, LO, HI), interpolation="nearest")
    for e in EDGES:
        ax.axhline(e, color=BG, lw=1.5)
        ax.axvline(e, color=BG, lw=1.5)
    ax.add_patch(Rectangle((EDGES[box[0]], EDGES[box[1]]), W, W, fc="none", ec=ORANGE, lw=3))
    ax.set_xlim(LO, HI)
    ax.set_ylim(LO, HI)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title("Master: lower bound of each box from the cuts", color=INK, fontsize=15, loc="left")

    n_solved = len(done) if phase == "cut" else it
    step = {
        "pick": "1  Master selects the box with the lowest bound",
        "solve": "2  Local solver optimizes inside the box",
        "cut": "3  Its solution adds a cut: boxes that cannot beat the best are ruled out",
    }[phase]
    if phase == "cut" and it == len(history) - 1:
        step = f"Done: every other box is ruled out, optimum found after {len(history)} of 100 boxes"
    fig.text(0.03, 0.935, step, color=ORANGE if phase != "cut" else INK, fontsize=19, weight="bold")
    best_txt = "—" if not np.isfinite(cur_best) else f"{cur_best:.2f}"
    fig.text(
        0.03, 0.875,
        f"boxes solved {n_solved}/100     best f = {best_txt}",
        color=SOFT, fontsize=14,
    )
    x0 = 0.545
    for label, col in (("solved", INK), ("candidate", BLUE), ("ruled out by the cuts", GREY)):
        fig.text(x0, 0.875, "■", color=col, fontsize=16)
        fig.text(x0 + 0.018, 0.875, label, color=SOFT, fontsize=14)
        x0 += 0.035 + 0.0105 * len(label)
    buf = BytesIO()
    fig.savefig(buf, format="png", facecolor=BG)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def main():
    history = run()
    print("solved", len(history), "best", min(h[3] for h in history), file=sys.stderr)
    frames, durations = [], []
    for it in range(len(history)):
        slow = it < 3
        frames.append(frame(history, it, "pick"))
        durations.append(700 if slow else 250)
        for frac in ((0.35, 0.7, 1.0) if slow else (0.5, 1.0)):
            frames.append(frame(history, it, "solve", frac))
            durations.append(250 if slow else 120)
        frames.append(frame(history, it, "cut"))
        durations.append(1200 if slow else 350)
    durations[-1] = 4000
    pick = [frames[i] for i in (2, len(frames) // 2, len(frames) - 1)]
    mosaic = Image.new("RGB", (pick[0].width, pick[0].height * len(pick)))
    for k, fr in enumerate(pick):
        mosaic.paste(fr, (0, k * fr.height))
    pal = mosaic.quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    q = [fr.quantize(palette=pal, dither=Image.Dither.NONE) for fr in frames]
    q[0].save(OUT, save_all=True, append_images=q[1:], duration=durations, loop=0, optimize=True)
    print(OUT, OUT.stat().st_size // 1024, "KB", len(frames), "frames", file=sys.stderr)


if __name__ == "__main__":
    main()
