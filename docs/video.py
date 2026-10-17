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
"""Render a video explaining the method and its variants.

The video is drawn with `Manim <https://www.manim.community>`_ in the style of
3Blue1Brown, one scene per section, the run of the sixth scene being the one of
the animation of the methodology, recorded when the scene is rendered. Manim
and the package are installed in the same environment, and LaTeX is required
for the formulas:

```shell
pip install -e . manim "pillow<11"
manim -qh docs/video.py S1Problem S2Subdivision S3Bilevel S4Cuts \\
    S5TrustRegion S6Run S7Variants S7aFormulations S7bPartial S7cDensity \\
    S7dHierarchies S7eMultiResolution S8Conclusion
```

The scenes are written to ``media/videos/video/``, in the order of ``SCENES``,
and are joined with ``ffmpeg -f concat``. Pillow is pinned because Manim 0.22
fails to draw images with Pillow 13.
"""

# The text on screen is mathematical, with Greek letters and signs.
# ruff: noqa: RUF001

from __future__ import annotations

import sys
from itertools import starmap
from pathlib import Path

import numpy as np
from manim import BLACK
from manim import BLUE
from manim import BLUE_B
from manim import BLUE_C
from manim import DL
from manim import DOWN
from manim import DR
from manim import GREY_A
from manim import GREY_B
from manim import GREY_C
from manim import GREY_D
from manim import LEFT
from manim import ORIGIN
from manim import PI
from manim import RIGHT
from manim import UL
from manim import UP
from manim import UR
from manim import WHITE
from manim import YELLOW
from manim import Arrow
from manim import Axes
from manim import Brace
from manim import Code
from manim import Create
from manim import Cross
from manim import CurvedArrow
from manim import DashedLine
from manim import Dot
from manim import FadeIn
from manim import FadeOut
from manim import Flash
from manim import GrowArrow
from manim import ImageMobject
from manim import Indicate
from manim import LaggedStart
from manim import Line
from manim import ManimColor
from manim import MathTex
from manim import MoveAlongPath
from manim import Rectangle
from manim import RoundedRectangle
from manim import Scene
from manim import Square
from manim import Star
from manim import Text
from manim import Transform
from manim import Triangle
from manim import ValueTracker
from manim import VGroup
from manim import VMobject
from manim import Write
from manim import always_redraw
from manim import config
from manim import interpolate_color
from manim import rate_functions
from manim import smooth
from matplotlib import colormaps
from scipy.signal import find_peaks

config.background_color = "#0e1116"

FONT = "Latin Modern Roman"
ACCENT = "#ff9a3c"  # the box being solved
SOLVED = BLUE_C  # the boxes already solved
GOOD = "#5fd38d"  # the incumbent, a valid cut
BAD = "#ff5c5c"
LO, HI = -4.1, 5.9


def text(string, size=32, color=WHITE, **kwargs):
    return Text(string, font=FONT, font_size=size, color=color, **kwargs)


def rastrigin(x, y):
    return 20 + x**2 - 10 * np.cos(2 * np.pi * x) + y**2 - 10 * np.cos(2 * np.pi * y)


def rastrigin_1d(x):
    return 10 + x**2 - 10 * np.cos(2 * np.pi * x)


def partly_multimodal(x, y):
    return 10 + x**2 - 10 * np.cos(2 * np.pi * x) + y**2


class Captioned(Scene):
    """A scene with a caption at the bottom, replaced as the story goes."""

    caption = None

    def say(self, message, wait=2.5, size=28, run_time=0.8):
        # Long enough to be read, at about fifteen characters per second.
        wait = max(wait, 0.065 * len(message))
        words, lines = message.split(), [""]
        for w in words:
            if len(lines[-1]) + len(w) > 72:
                lines.append("")
            lines[-1] = (lines[-1] + " " + w).strip()
        new = text("\n".join(lines), size, color=GREY_A, line_spacing=0.8)
        if new.width > 13:
            new.scale_to_fit_width(13)
        new.to_edge(DOWN, buff=0.35)
        if self.caption is None:
            self.play(FadeIn(new, shift=0.15 * UP), run_time=run_time)
        else:
            self.play(
                FadeOut(self.caption, shift=0.15 * UP),
                FadeIn(new, shift=0.15 * UP),
                run_time=run_time,
            )
        self.caption = new
        self.wait(wait)

    def unsay(self):
        if self.caption is not None:
            self.play(FadeOut(self.caption), run_time=0.5)
            self.caption = None

    def clear_all(self, run_time=0.8):
        self.play(*[FadeOut(m) for m in self.mobjects], run_time=run_time)
        self.caption = None


class Landscape:
    """A heat map of a function of two variables, drawn in its own coordinates."""

    def __init__(
        self,
        f,
        side=6.0,
        center=ORIGIN,
        lo=LO,
        hi=HI,
        res=500,
        cmap="magma",
        gamma=0.55,
    ):
        xs = np.linspace(lo, hi, res)
        grid_x, grid_y = np.meshgrid(xs, xs[::-1])
        values = f(grid_x, grid_y)
        norm = ((values - values.min()) / (values.max() - values.min())) ** gamma
        rgba = colormaps[cmap](norm)
        rgba[:, :, :3] *= 0.85
        rgb = (rgba * 255).astype(np.uint8)
        self.image = ImageMobject(rgb)
        self.image.height = side
        self.image.move_to(center)
        self.side, self.lo, self.hi = side, lo, hi
        self.frame = Square(side, color=GREY_B, stroke_width=2).move_to(center)

    @property
    def center(self):
        return self.frame.get_center()

    def p(self, x, y):
        s = self.side / (self.hi - self.lo)
        return (
            self.center
            + ((x - self.lo) * s - self.side / 2) * RIGHT
            + ((y - self.lo) * s - self.side / 2) * UP
        )

    def grid(self, mx, my=None, color=WHITE, opacity=0.85, width=1.6):
        my = mx if my is None else my
        lines = VGroup()
        for k in range(1, mx):
            x = self.lo + k * (self.hi - self.lo) / mx
            lines.add(
                Line(
                    self.p(x, self.lo),
                    self.p(x, self.hi),
                    stroke_width=width,
                    stroke_opacity=opacity,
                    color=color,
                )
            )
        for k in range(1, my):
            y = self.lo + k * (self.hi - self.lo) / my
            lines.add(
                Line(
                    self.p(self.lo, y),
                    self.p(self.hi, y),
                    stroke_width=width,
                    stroke_opacity=opacity,
                    color=color,
                )
            )
        return lines

    def box(self, i, j, m=10, **kwargs):
        w = (self.hi - self.lo) / m
        a, b = (
            self.p(self.lo + i * w, self.lo + j * w),
            self.p(self.lo + (i + 1) * w, self.lo + (j + 1) * w),
        )
        r = Rectangle(width=b[0] - a[0], height=b[1] - a[1], **kwargs)
        r.move_to((a + b) / 2)
        return r


def record_run():
    """Return the run of the animation of the methodology, box by box."""
    sys.path.insert(0, str(Path(__file__).parent))
    from figures import _trace_solve

    return _trace_solve()


def descent(f_prime, x0, step=0.003, n=250):
    xs = [x0]
    for _ in range(n):
        xs.append(xs[-1] - step * f_prime(xs[-1]))
    return np.array(xs)


def rastrigin_1d_prime(x):
    return 2 * x + 20 * np.pi * np.sin(2 * np.pi * x)


def one_hot(n, k, size=0.32, color=ACCENT):
    cells = VGroup(*[
        Square(size, stroke_width=1.5, color=GREY_B) for _ in range(n)
    ]).arrange(RIGHT, buff=0.05)
    labels = VGroup(*[text("0", 18, GREY_B).move_to(c) for c in cells])
    cells[k].set_fill(color, 0.9)
    labels[k].become(text("1", 18, BLACK).move_to(cells[k]))
    return VGroup(cells, labels)


# ---------------------------------------------------------------------------
# 1. The problem
# ---------------------------------------------------------------------------


class S1Problem(Captioned):
    def construct(self):
        title = text("Box subdivision", 64)
        sub = text(
            "exploring a multimodal landscape with a mixed-integer master", 30, GREY_B
        )
        VGroup(title, sub).arrange(DOWN, buff=0.4)
        self.play(Write(title), run_time=1.5)
        self.play(FadeIn(sub, shift=0.2 * UP))
        self.wait(2)
        self.play(FadeOut(title), FadeOut(sub))

        problem = (
            MathTex(r"\min_{x \in [L, U]} f(x) \quad \text{s.t.} \quad g(x) \le 0")
            .scale(1.1)
            .to_edge(UP)
        )
        self.play(Write(problem))
        ax = Axes(
            x_range=[LO, HI, 1],
            y_range=[0, 50, 10],
            x_length=11.5,
            y_length=4.2,
            axis_config={"include_tip": False, "color": GREY_B},
            x_axis_config={"include_ticks": False},
        ).shift(0.3 * DOWN)
        graph = ax.plot(
            rastrigin_1d, x_range=[LO, HI, 0.005], color=BLUE, stroke_width=4
        )
        label = (
            MathTex(r"f(x) = 10 + x^2 - 10\cos(2\pi x)", font_size=34)
            .next_to(ax, UP, buff=0.05)
            .to_edge(RIGHT)
        )
        self.play(Create(ax), Create(graph), FadeIn(label), run_time=2)
        self.say("f is non-convex: it has many local minima.", 1.5)

        def roll(x0, color=YELLOW, run_time=2.0):
            xs = descent(rastrigin_1d_prime, x0)
            path = VMobject().set_points_smoothly([
                ax.c2p(x, rastrigin_1d(x)) for x in xs[::5]
            ])
            dot = Dot(ax.c2p(x0, rastrigin_1d(x0)), color=color, radius=0.1)
            self.play(FadeIn(dot, scale=0.5), run_time=0.4)
            self.play(
                MoveAlongPath(dot, path),
                run_time=run_time,
                rate_func=rate_functions.ease_out_cubic,
            )
            return dot, xs[-1]

        dot, xend = roll(3.35)
        val = MathTex(
            rf"f = {rastrigin_1d(xend):.2f}", font_size=30, color=YELLOW
        ).next_to(dot, UP)
        self.play(FadeIn(val))
        self.say("A local solver returns the minimum of the basin it starts in.", 2)
        dots = [dot]
        for x0, c in ((-2.6, GREY_A), (1.65, GREY_A), (4.4, GREY_A)):
            d, _ = roll(x0, c, 1.0)
            dots.append(d)
        star = Star(color=GOOD, fill_opacity=1, outer_radius=0.18).move_to(ax.c2p(0, 0))
        self.play(FadeIn(star, scale=2))
        self.say("The global minimum is reached only from the right basin.", 2)
        idea = VGroup(
            text("Idea: separate two tasks", 36),
            text("exploration — which region to search?", 30, BLUE_B),
            text("exploitation — local descent within that region", 30, ACCENT),
        ).arrange(DOWN, buff=0.3)
        self.clear_all()
        self.play(FadeIn(idea[0]))
        self.play(FadeIn(idea[1], shift=0.2 * RIGHT))
        self.play(FadeIn(idea[2], shift=0.2 * RIGHT))
        self.wait(3)
        self.clear_all()


# ---------------------------------------------------------------------------
# 2. The subdivision and its encoding
# ---------------------------------------------------------------------------


class S2Subdivision(Captioned):
    def construct(self):
        ax = Axes(
            x_range=[LO, HI, 1],
            y_range=[0, 50, 10],
            x_length=11.5,
            y_length=4.2,
            axis_config={"include_tip": False, "color": GREY_B},
            x_axis_config={"include_ticks": False},
        ).shift(0.5 * UP)
        graph = ax.plot(
            rastrigin_1d, x_range=[LO, HI, 0.005], color=BLUE, stroke_width=4
        )
        self.add(ax, graph)
        cuts = VGroup(*[
            DashedLine(
                ax.c2p(LO + k, 0), ax.c2p(LO + k, 50), color=ACCENT, stroke_width=2
            )
            for k in range(1, 10)
        ])
        self.play(LaggedStart(*[Create(c) for c in cuts], lag_ratio=0.1), run_time=2)
        braces = VGroup(*[
            Brace(
                Line(ax.c2p(LO + k, 0), ax.c2p(LO + k + 1, 0)),
                DOWN,
                buff=0.05,
                color=GREY_B,
            )
            for k in range(10)
        ])
        ks = VGroup(*[
            MathTex(str(k + 1), font_size=26).next_to(b, DOWN, buff=0.08)
            for k, b in enumerate(braces)
        ])
        self.play(FadeIn(braces), FadeIn(ks))
        self.say(
            "Each variable is divided into m contiguous intervals — here m = 10.", 2
        )
        mins = VGroup(*[
            Dot(ax.c2p(k, rastrigin_1d(k)), color=YELLOW, radius=0.07)
            for k in range(-4, 6)
        ])
        self.play(LaggedStart(*[FadeIn(d, scale=2) for d in mins], lag_ratio=0.1))
        self.say("Well chosen, each interval contains a single basin.", 2)
        self.clear_all()

        land = Landscape(rastrigin, side=6.2, center=3.1 * LEFT + 0.35 * UP)
        grid = land.grid(10)
        x1 = MathTex("x_1", font_size=30).next_to(land.frame, DOWN, buff=0.1)
        x2 = MathTex("x_2", font_size=30).next_to(land.frame, LEFT, buff=0.1)
        self.play(FadeIn(land.image), Create(land.frame), FadeIn(x1), FadeIn(x2))
        self.play(
            LaggedStart(*[Create(line) for line in grid], lag_ratio=0.05), run_time=1.5
        )
        self.say(
            "In two dimensions, the Cartesian product gives 10 × 10 = 100 boxes.", 1.5
        )

        def selection(i, j):
            box = land.box(i, j, stroke_color=ACCENT, stroke_width=5)
            a1 = one_hot(10, i).move_to(3.6 * RIGHT + 1.6 * UP)
            a2 = one_hot(10, j).move_to(3.6 * RIGHT + 0.2 * UP)
            l1 = MathTex(r"\alpha_1", font_size=34).next_to(a1, LEFT)
            l2 = MathTex(r"\alpha_2", font_size=34).next_to(a2, LEFT)
            return VGroup(box, a1, a2, l1, l2)

        heading = text(
            "Choosing a box = one categorical\nvariable per component", 30
        ).move_to(3.6 * RIGHT + 2.9 * UP)
        sel = selection(6, 3)
        self.play(FadeIn(heading), Create(sel[0]), FadeIn(sel[1:]))
        self.say(
            "Each choice is one-hot encoded: α ∈ {0, 1}, a single cell set to 1.",
            1.5,
        )
        for i, j in ((2, 7), (8, 1), (4, 4)):
            new = selection(i, j)
            self.play(Transform(sel, new), run_time=0.9)
            self.wait(0.4)
        bounds = (
            MathTex(
                r"\ell_j(\alpha) = \sum_k l_{j,k}\,\alpha_{j,k}",
                r"\qquad",
                r"u_j(\alpha) = \sum_k u_{j,k}\,\alpha_{j,k}",
                font_size=34,
            )
            .move_to(3.6 * RIGHT + 1.3 * DOWN)
            .scale(0.9)
        )
        self.play(Write(bounds))
        self.say("The bounds of the selected box are affine functions of α.", 2.5)
        self.clear_all()

        # What grows with the dimension.
        head = VGroup(MathTex("n"), text("boxes  ∏ mⱼ", 30), text("binaries  Σ mⱼ", 30))
        rows = [head]
        for n in range(1, 6):
            rows.append(
                VGroup(
                    MathTex(str(n)),
                    MathTex(f"{10**n:,}".replace(",", r"\,")),
                    MathTex(str(10 * n)),
                )
            )
        table = VGroup()
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                cell.move_to(np.array([[-3.5, 0, 3.5][c], 2.4 - 0.85 * r, 0]))
            table.add(row)
        line = Line(5 * LEFT, 5 * RIGHT, color=GREY_B).move_to(2.0 * UP)
        self.play(FadeIn(head), Create(line))
        for row in rows[1:]:
            row[1].set_color(BAD)
            row[2].set_color(GOOD)
            self.play(FadeIn(row, shift=0.2 * UP), run_time=0.6)
        self.play(Indicate(rows[-1][1], color=BAD), Indicate(rows[-1][2], color=GOOD))
        self.say(
            "The master handles Σ mⱼ binaries, linear in n. The Cartesian product is never enumerated.",
            3.5,
        )
        self.say(
            "Five variables, ten intervals each: 100 000 boxes, but only 50 binaries.",
            3,
        )
        self.clear_all()


# ---------------------------------------------------------------------------
# 3. The bi-level problem
# ---------------------------------------------------------------------------


class S3Bilevel(Captioned):
    def construct(self):
        eq = MathTex(
            r"\min_\alpha\ u(\alpha)",
            r"\quad\text{where}\quad",
            r"u(\alpha) = \min_x \{\, f(x) : g(x) \le 0,\ \ell(\alpha) \le x \le u(\alpha) \,\}",
            font_size=38,
        ).to_edge(UP, buff=0.6)
        self.play(Write(eq), run_time=2)
        master = VGroup(
            RoundedRectangle(
                corner_radius=0.3, width=4.6, height=2.4, color=BLUE, fill_opacity=0.12
            ),
            text("Master", 40, BLUE_B),
            text("mixed-integer · exploration", 24, GREY_A),
        )
        master[1].move_to(master[0]).shift(0.35 * UP)
        master[2].next_to(master[1], DOWN, buff=0.25)
        master.move_to(3.6 * LEFT + 0.4 * DOWN)
        sub = VGroup(
            RoundedRectangle(
                corner_radius=0.3,
                width=4.6,
                height=2.4,
                color=ACCENT,
                fill_opacity=0.12,
            ),
            text("Sub-problem", 40, ACCENT),
            text("local solver · exploitation", 24, GREY_A),
        )
        sub[1].move_to(sub[0]).shift(0.35 * UP)
        sub[2].next_to(sub[1], DOWN, buff=0.25)
        sub.move_to(3.6 * RIGHT + 0.4 * DOWN)
        self.play(FadeIn(master, shift=RIGHT), FadeIn(sub, shift=LEFT))
        top = CurvedArrow(
            master.get_top() + 0.6 * RIGHT,
            sub.get_top() + 0.6 * LEFT,
            angle=-PI / 3,
            color=GREY_A,
        )
        bot = CurvedArrow(
            sub.get_bottom() + 0.6 * LEFT,
            master.get_bottom() + 0.6 * RIGHT,
            angle=-PI / 3,
            color=GREY_A,
        )
        tl = text("box α", 28).next_to(top, UP, buff=0.1)
        bl = MathTex(
            r"u(\alpha^{(i)}),\ \ s^{(i)} = \frac{\mathrm{d}u}{\mathrm{d}\alpha}",
            font_size=34,
        ).next_to(bot, DOWN, buff=0.1)
        self.play(Create(top), FadeIn(tl))
        self.play(Create(bot), FadeIn(bl))
        for _ in range(2):
            d = Dot(color=YELLOW)
            self.play(MoveAlongPath(d, top), run_time=1)
            self.play(Flash(sub[0].get_center(), color=ACCENT), run_time=0.5)
            self.play(MoveAlongPath(d, bot), run_time=1)
            self.remove(d)
        self.say(
            "The master proposes a box; the local solver solves the problem within it and returns its value and slope.",
            3,
        )
        self.say(
            "The slope comes for free from the post-optimal analysis (Lagrange multipliers).",
            3,
        )
        self.say(
            "This is the Benders formulation of gemseo-bilevel-outer-approximation.",
            2.5,
        )
        self.clear_all()


# ---------------------------------------------------------------------------
# 4. The cuts and the convexification
# ---------------------------------------------------------------------------


class S4Cuts(Captioned):
    def construct(self):
        cut_eq = MathTex(
            r"\eta \ \ge\ u(\alpha^{(i)}) + s^{(i)\top}(\alpha - \alpha^{(i)})",
            font_size=40,
        ).to_edge(UP, buff=0.4)
        self.play(Write(cut_eq))
        self.say(
            "The master builds a piecewise-linear underestimator: one cut per solved box.",
            2.5,
        )

        ax = Axes(
            x_range=[0, 1, 0.5],
            y_range=[-5, 6, 2],
            x_length=6.6,
            y_length=4.2,
            axis_config={"include_tip": False, "color": GREY_B},
        ).shift(2.5 * LEFT + 0.15 * UP)
        xl = text("α, relaxed between two boxes", 24, GREY_A).next_to(
            ax, DOWN, buff=0.15
        )

        def u(a):
            return 3 - 6 * a + 8 * a * (1 - a)

        graph = ax.plot(u, x_range=[0, 1, 0.01], color=BLUE, stroke_width=4)
        ul = MathTex("u(\\alpha)", color=BLUE, font_size=32).next_to(
            ax.c2p(0.5, u(0.5)), UP
        )
        b0 = Dot(ax.c2p(0, 3), color=WHITE, radius=0.09)
        b1 = Dot(ax.c2p(1, -3), color=GOOD, radius=0.11)
        l0 = text("box A", 24).next_to(b0, UP + RIGHT, buff=0.1)
        l1 = text("box B (optimum)", 24, GOOD).next_to(b1, DOWN + LEFT, buff=0.1)
        self.play(Create(ax), FadeIn(xl), Create(graph), FadeIn(ul))
        self.play(FadeIn(b0), FadeIn(b1), FadeIn(l0), FadeIn(l1))

        kappa = ValueTracker(0)

        def slope():
            return 2 - kappa.get_value()

        cut = always_redraw(
            lambda: Line(
                ax.c2p(0, 3),
                ax.c2p(1, 3 + slope()),
                color=interpolate_color(
                    ManimColor(BAD),
                    ManimColor(GOOD),
                    float(np.clip(kappa.get_value() / 8, 0, 1)) ** 4,
                ),
                stroke_width=4,
            )
        )
        self.play(Create(cut))
        tip = always_redraw(
            lambda: Dot(ax.c2p(1, 3 + slope()), color=cut.get_color(), radius=0.08)
        )
        gap = always_redraw(
            lambda: DashedLine(ax.c2p(1, 3 + slope()), ax.c2p(1, -3), color=GREY_B)
        )
        self.play(FadeIn(tip), Create(gap))
        self.say("The cut at A claims u(B) ≥ 5. Wrong — the true value is −3.", 2)
        cross = Cross(scale_factor=0.25, stroke_color=BAD).move_to(b1)
        self.play(Create(cross))
        self.say(
            "u is not convex: the cut excludes the optimum, and the master converges… without reporting an error.",
            3,
        )
        self.play(FadeOut(cross))

        # The convexification term.
        cax = Axes(
            x_range=[0, 1, 0.5],
            y_range=[-0.3, 0.05, 0.1],
            x_length=4,
            y_length=2.2,
            axis_config={"include_tip": False, "color": GREY_B},
            y_axis_config={"include_ticks": False},
        ).move_to(4.4 * RIGHT + 1.4 * UP)
        cg = cax.plot(
            lambda a: a * (a - 1), x_range=[0, 1, 0.01], color=ACCENT, stroke_width=4
        )
        cl = MathTex(r"\alpha(\alpha - 1)", color=ACCENT, font_size=30).next_to(
            cax, UP, buff=0.05
        )
        zeros = VGroup(Dot(cax.c2p(0, 0), radius=0.07), Dot(cax.c2p(1, 0), radius=0.07))
        self.play(Create(cax), Create(cg), FadeIn(cl), FadeIn(zeros))
        conv = MathTex(
            r"\tilde u(\alpha) = u(\alpha) + \kappa\, C(\alpha)", font_size=34
        ).move_to(4.4 * RIGHT + 0.7 * DOWN)
        corr = MathTex(
            r"s^{(i)} \leftarrow s^{(i)} + \tfrac{\kappa}{n}\,(2\alpha^{(i)} - 1)",
            font_size=34,
        ).next_to(conv, DOWN)
        self.play(Write(conv))
        self.say(
            "A convex term, zero at every box: the discrete problem is unchanged.",
            2.5,
        )
        self.play(Write(corr))
        kl = always_redraw(
            lambda: MathTex(rf"\kappa = {kappa.get_value():.1f}", font_size=34).next_to(
                corr, DOWN
            )
        )
        self.play(FadeIn(kl))
        self.play(kappa.animate.set_value(9), run_time=4, rate_func=smooth)
        check = text("✓ valid", 28, GOOD).next_to(tip, RIGHT, buff=0.15)
        self.play(FadeIn(check))
        self.say(
            "The term is never evaluated: the slope is tilted, and the cut falls back below the value at B.",
            3,
        )
        self.clear_all()

        # The three safeguards.
        warn = text(
            "The most important setting — disabled by default", 34, ACCENT
        ).to_edge(UP, buff=0.5)
        self.play(FadeIn(warn))
        cards = VGroup()
        specs = [
            (
                "Fixed κ",
                BLUE,
                "valid by construction\nconvergence guarantee\nbut lowers the lower bound",
            ),
            (
                "Adaptive repair δ",
                GOOD,
                "least-squares correction of\nthe slopes over the history\nno guarantee, very effective",
            ),
            (
                "Swept convexity",
                ACCENT,
                "a ladder κ₁ < … < κₘₐₓ\none rung per parallel probe\nno value to supply",
            ),
        ]
        for name, color, body in specs:
            card = VGroup(
                RoundedRectangle(
                    corner_radius=0.2,
                    width=4.1,
                    height=3.4,
                    color=color,
                    fill_opacity=0.08,
                ),
                text(name, 28, color),
                text(body, 20, GREY_A, line_spacing=1.0),
            )
            for part in card[1:]:
                if part.width > 3.7:
                    part.scale_to_fit_width(3.7)
            card[1].move_to(card[0].get_top() + 0.5 * DOWN)
            card[2].next_to(card[1], DOWN, buff=0.4)
            cards.add(card)
        cards.arrange(RIGHT, buff=0.3).shift(0.2 * UP)
        self.play(
            LaggedStart(*[FadeIn(c, shift=0.3 * UP) for c in cards], lag_ratio=0.3),
            run_time=2,
        )
        adapt = MathTex(
            r"u(\alpha^{(i)}) + s^{(i)\top}(\alpha^{(j)} - \alpha^{(i)}) \le u(\alpha^{(j)}) - \delta",
            font_size=30,
        )
        adapt.next_to(cards, DOWN, buff=0.3)
        self.play(Write(adapt))
        self.say("Two mechanisms not to combine: κ or δ, the other set to zero.", 3)
        self.say(
            "κ and δ are in the units of f: δ = 100 succeeds on Rastrigin… and fails on Ackley.",
            3.5,
        )
        self.play(
            FadeOut(adapt),
            FadeOut(warn),
            cards[0].animate.set_opacity(0.25),
            cards[1].animate.set_opacity(0.25),
        )
        self.play(cards.animate.shift(2.5 * UP).scale(0.6))

        # The ladder of the swept convexity.
        ladder = VGroup()
        values = [r"\kappa_1", r"\kappa_2", r"\kappa_3", r"\kappa_4", r"\kappa_{\max}"]
        for k, v in enumerate(values):
            rung = Line(0.9 * LEFT, 0.9 * RIGHT, color=ACCENT).shift(
                (k * 0.6 - 2.2) * UP
            )
            ladder.add(VGroup(rung, MathTex(v, font_size=28).next_to(rung, LEFT)))
        rails = VGroup(
            Line(ladder[0][0].get_left(), ladder[-1][0].get_left()),
            Line(ladder[0][0].get_right(), ladder[-1][0].get_right()),
        ).set_color(GREY_B)
        VGroup(rails, ladder).shift(3 * LEFT)
        self.play(
            Create(rails), LaggedStart(*[FadeIn(r) for r in ladder], lag_ratio=0.15)
        )
        probes = VGroup(*[
            Dot(ladder[k][0].get_center(), color=YELLOW) for k in range(4)
        ])
        self.play(FadeIn(probes))
        expl = (
            VGroup(
                text("probe k ↔ rung k: small κ = neighbouring box,", 24),
                text("large κ = distant box", 24),
                text("box already solved → the probe climbs a rung", 24, GREY_A),
                text("bound: spread of the observed values × 10", 24, GREY_A),
            )
            .arrange(DOWN, aligned_edge=LEFT, buff=0.25)
            .move_to(1.8 * RIGHT + 1.2 * DOWN)
        )
        self.play(FadeIn(expl[:2]))
        self.play(
            probes[1].animate.move_to(ladder[2][0].get_center()),
            Flash(ladder[1][0], color=YELLOW),
        )
        self.play(FadeIn(expl[2]))
        self.play(probes[2].animate.move_to(ladder[4][0].get_center()))
        self.play(FadeIn(expl[3]))
        self.say(
            "Without any tuning, the sweep reaches the optimum on both Rastrigin and Ackley — no fixed margin does.",
            4,
        )
        self.clear_all()


# ---------------------------------------------------------------------------
# 5. The trust region
# ---------------------------------------------------------------------------


class S5TrustRegion(Captioned):
    def construct(self):
        title = text("Trust region of the master", 40).to_edge(UP, buff=0.4)
        self.play(FadeIn(title))
        s = 0.42

        def grid(center):
            g = VGroup(*[
                Square(s, stroke_width=1, color=GREY_D) for _ in range(100)
            ]).arrange_in_grid(10, 10, buff=0)
            return g.move_to(center)

        def cell(g, i, j):  # Column i and row j from the bottom, from one.
            return g[(10 - j) * 10 + (i - 1)]

        left, right = grid(3.3 * LEFT + 0.2 * DOWN), grid(3.3 * RIGHT + 0.2 * DOWN)
        lt = text("unit weights (Hamming distance)", 26, GOOD).next_to(left, UP)
        rt = text("index weights", 26, BAD).next_to(right, UP)
        self.play(FadeIn(left), FadeIn(right), FadeIn(lt), FadeIn(rt))
        eq = MathTex(
            r"\textstyle\sum_{j:\,\alpha'_j = \alpha_j} w_j(\alpha) \ \ge\ \sum_j w_j(\alpha) - \texttt{max\_step}",
            font_size=32,
        )
        eq.next_to(title, DOWN, buff=0.1)
        self.play(Write(eq))

        for inc in ((1, 1), (7, 6)):
            hl = VGroup()
            for i in range(1, 11):
                for j in range(1, 11):
                    changed = (i != inc[0]) + (j != inc[1])
                    if changed <= 1:
                        hl.add(cell(left, i, j).copy().set_fill(GOOD, 0.5))
                    cost = (inc[0] if i != inc[0] else 0) + (
                        inc[1] if j != inc[1] else 0
                    )
                    if cost <= 2:
                        hl.add(cell(right, i, j).copy().set_fill(BAD, 0.5))
            mark = VGroup(
                cell(left, *inc).copy().set_fill(YELLOW, 1),
                cell(right, *inc).copy().set_fill(YELLOW, 1),
            )
            lab = MathTex(
                rf"\text{{incumbent}}\ ({inc[0]},{inc[1]})", font_size=30
            ).next_to(VGroup(left, right), DOWN, buff=0.15)
            self.play(FadeIn(hl), FadeIn(mark), FadeIn(lab))
            if inc == (1, 1):
                self.say("From (1,1), index weights open the whole space…", 2.5)
            else:
                self.say(
                    "… from (7,6), only the incumbent. Unit weights: 19 boxes in both cases.",
                    3,
                )
            self.play(FadeOut(hl), FadeOut(mark), FadeOut(lab))
        self.say(
            "So the distance counts the components changed, with a small radius: about 2.",
            3,
        )
        self.say(
            "Rastrigin 5D: radius 2 → optimum from every start; no trust region → failure.",
            3.5,
        )
        self.clear_all()


# ---------------------------------------------------------------------------
# 6. A run
# ---------------------------------------------------------------------------


class S6Run(Captioned):
    def construct(self):
        land = Landscape(rastrigin, side=5.9, center=3.4 * LEFT + 0.65 * UP)
        grid = land.grid(10)
        self.play(FadeIn(land.image), Create(land.frame), Create(grid))
        title = text("A real run: Rastrigin 2D, 100 boxes", 28).move_to(
            3.4 * RIGHT + 3.2 * UP
        )
        self.play(FadeIn(title))
        legend = (
            VGroup(
                VGroup(
                    Square(0.3, color=ACCENT, stroke_width=4),
                    text("chosen by the master", 24),
                ).arrange(RIGHT),
                VGroup(
                    Square(0.3, color=SOLVED, fill_opacity=0.5, stroke_width=0),
                    text("already solved (cut)", 24),
                ).arrange(RIGHT),
                VGroup(
                    Star(color=GOOD, fill_opacity=1, outer_radius=0.15),
                    text("best solution", 24),
                ).arrange(RIGHT),
            )
            .arrange(DOWN, aligned_edge=LEFT)
            .move_to(3.4 * RIGHT + 2.0 * UP)
        )
        self.play(FadeIn(legend))

        n_box, n_eval, best = ValueTracker(0), ValueTracker(0), ValueTracker(np.nan)

        def counters():
            b = best.get_value()
            g = (
                VGroup(
                    text(f"boxes solved: {int(n_box.get_value())} / 100", 28),
                    text(f"evaluations: {int(n_eval.get_value())}", 28),
                    text(
                        "best value: " + ("—" if np.isnan(b) else f"{b:.2f}"),
                        28,
                        GOOD,
                    ),
                )
                .arrange(DOWN, aligned_edge=LEFT)
                .move_to(3.4 * RIGHT + 0.4 * DOWN)
            )
            return g

        cnt = always_redraw(counters)
        self.add(cnt)
        star = None
        prev = None
        best_value = np.inf
        for k, s in enumerate(record_run()):
            i, j = s["box"]
            fast = k >= 8
            rt = 0.35 if fast else 1.0
            outline = land.box(i, j, stroke_color=ACCENT, stroke_width=5)
            pts = list(starmap(land.p, s["points"]))
            path = VMobject(
                stroke_color=ACCENT, stroke_width=2.5
            ).set_points_as_corners(pts)
            anims = [Create(outline)]
            if prev is not None:
                anims.extend((
                    prev[0].animate.set_stroke(width=0).set_fill(SOLVED, 0.45),
                    FadeOut(prev[1]),
                ))
            self.play(*anims, run_time=rt)
            self.play(
                Create(path), n_eval.animate.set_value(s["cost"]), run_time=rt * 1.3
            )
            local = s["points"][int(np.argmin(s["values"]))]
            dot = Dot(land.p(*local), radius=0.05, color=SOLVED)
            self.add(dot)
            n_box.set_value(k + 1)
            if s["best"] < best_value - 1e-9:
                best_value = s["best"]
                best.set_value(best_value)
                new_star = Star(color=GOOD, fill_opacity=1, outer_radius=0.17).move_to(
                    land.p(*local)
                )
                if star is None:
                    self.play(FadeIn(new_star, scale=2), run_time=0.5)
                else:
                    self.play(
                        Transform(star, new_star),
                        Flash(new_star, color=GOOD),
                        run_time=0.8,
                    )
                    new_star = star
                star = new_star
            prev = (outline, path)
            if k == 0:
                self.say(
                    "First box: the local solver finds a local minimum, f = 8.95.",
                    2,
                )
            if k == 2:
                self.say(
                    "The master chooses each next box from the cuts of the boxes already solved.",
                    2,
                )
            if k == 6:
                self.say("7th box: the global minimum f = 0, after 154 evaluations.", 3)
            if k == 8:
                self.say(
                    "The following boxes only confirm it… until the stopping criterion.",
                    0.5,
                )
        self.play(
            prev[0].animate.set_stroke(width=0).set_fill(SOLVED, 0.45), FadeOut(prev[1])
        )
        self.say(
            "20 boxes solved out of 100: the exploration is informed, not exhaustive.",
            3,
        )
        self.clear_all()


# ---------------------------------------------------------------------------
# 7. The variants
# ---------------------------------------------------------------------------


class S7Variants(Captioned):
    def construct(self):
        title = text("The variants", 56).to_edge(UP, buff=0.5)
        items = (
            VGroup(*[
                text(t, 32)
                for t in (
                    "1.  Two formulations of the sub-problem",
                    "2.  Three safeguards against non-convexity  (seen)",
                    "3.  Subdividing some of the variables",
                    "4.  Estimating the density of the subdivision",
                    "5.  Hierarchies of subdivisions",
                    "6.  Multi-resolution encoding",
                )
            ])
            .arrange(DOWN, aligned_edge=LEFT, buff=0.35)
            .next_to(title, DOWN, buff=0.6)
        )
        items[1].set_color(GREY_C)
        self.play(Write(title))
        self.play(
            LaggedStart(*[FadeIn(i, shift=0.2 * RIGHT) for i in items], lag_ratio=0.2),
            run_time=2.5,
        )
        self.wait(3)
        self.clear_all()


class S7aFormulations(Captioned):
    def construct(self):
        title = text("1 · Two formulations of the sub-problem", 38).to_edge(
            UP, buff=0.4
        )
        self.play(FadeIn(title))
        lt = text("Box as a constraint", 30, BLUE_B).move_to(3.5 * LEFT + 2.4 * UP)
        rt = text("Box as normalized variables", 30, ACCENT).move_to(
            3.5 * RIGHT + 2.4 * UP
        )
        l1 = MathTex(
            r"g_{\text{box}}(x,\alpha) = \begin{bmatrix} x - u(\alpha) \\ \ell(\alpha) - x \end{bmatrix} \le 0",
            font_size=34,
        )
        l2 = MathTex(
            r"\frac{\mathrm{d}u}{\mathrm{d}\alpha_{j,k}} = -\lambda^u_j\,u_{j,k} + \lambda^\ell_j\,l_{j,k}",
            font_size=34,
        )
        l3 = text("linear in x, affine in α:\njointly convex", 22, GREY_A)
        VGroup(l1, l2, l3).arrange(DOWN, buff=0.45).next_to(lt, DOWN, buff=0.4)
        r1 = MathTex(
            r"x(\xi,\alpha) = \ell(\alpha) + \xi \odot (u(\alpha) - \ell(\alpha))",
            font_size=32,
        )
        r2 = MathTex(r"\xi \in [0,1]^n", font_size=32)
        VGroup(r1, r2).arrange(DOWN, buff=0.3).next_to(rt, DOWN, buff=0.4)
        sep = Line(2.9 * UP, 2.6 * DOWN, color=GREY_D)
        self.play(FadeIn(lt), FadeIn(rt), Create(sep))
        self.play(Write(l1))
        self.play(Write(l2))
        self.play(FadeIn(l3))
        self.say(
            "The slope is exact, given by the multipliers of the faces of the box.",
            2.5,
        )
        self.play(Write(r1), Write(r2))

        unit = Square(1.4, color=ACCENT).move_to(1.5 * RIGHT + 1.3 * DOWN)
        ul = MathTex(r"[0,1]^2", font_size=26).next_to(unit, DOWN, buff=0.1)
        g = (
            VGroup(*[Square(0.3, stroke_width=1, color=GREY_D) for _ in range(36)])
            .arrange_in_grid(6, 6, buff=0)
            .move_to(5.0 * RIGHT + 1.3 * DOWN)
        )
        xi = ValueTracker(0.3)
        cellk = ValueTracker(8)
        pt = always_redraw(
            lambda: Dot(
                unit.get_corner(DL) + 1.4 * np.array([xi.get_value(), 0.7, 0]),
                color=YELLOW,
                radius=0.07,
            )
        )
        hl = always_redraw(
            lambda: g[int(cellk.get_value())].copy().set_stroke(ACCENT, 4)
        )
        img = always_redraw(
            lambda: Dot(
                g[int(cellk.get_value())].get_corner(DL)
                + 0.3 * np.array([xi.get_value(), 0.7, 0]),
                color=YELLOW,
                radius=0.05,
            )
        )
        arr = Arrow(unit.get_right(), g.get_left(), buff=0.2, color=GREY_B)
        self.play(
            Create(unit),
            FadeIn(ul),
            FadeIn(g),
            FadeIn(pt),
            FadeIn(hl),
            FadeIn(img),
            GrowArrow(arr),
        )
        self.play(xi.animate.set_value(0.85), run_time=1.2)
        for k in (21, 33, 4):
            cellk.set_value(k)
            self.wait(0.5)
        self.say(
            "The sub-problem always lives in [0,1]ⁿ; the slope is ∇f · ∂x/∂α.", 2.5
        )
        self.say(
            "In practice: normalized → optimum from every start; constraint → from all but one.",
            3.5,
        )
        self.clear_all()


class S7bPartial(Captioned):
    def construct(self):
        title = text("3 · Subdividing only the multimodal variables", 38).to_edge(
            UP, buff=0.4
        )
        self.play(FadeIn(title))
        land = Landscape(partly_multimodal, side=5.0, center=3.6 * LEFT + 0.1 * DOWN)
        self.play(FadeIn(land.image), Create(land.frame))
        lines = VGroup(*[
            Line(
                land.p(LO + k, LO),
                land.p(LO + k, HI),
                color=WHITE,
                stroke_width=2.5,
                stroke_opacity=0.9,
            )
            for k in range(1, 10)
        ])
        self.play(LaggedStart(*[Create(line) for line in lines], lag_ratio=0.08))
        x1 = text("x₁: subdivided (multimodal)", 22).next_to(land.frame, DOWN, buff=0.1)
        x2 = (
            text("x₂: left to the local solver", 22)
            .rotate(PI / 2)
            .next_to(land.frame, LEFT, buff=0.1)
        )
        self.play(FadeIn(x1), FadeIn(x2))
        code = (
            Code(
                code_string='BoxSubdivision.from_design_space(\n    design_space, 10, ["x_1"]\n)',
                language="python",
                background="rectangle",
                add_line_numbers=False,
            )
            .scale(0.8)
            .move_to(2.9 * RIGHT + 0.8 * UP)
        )
        self.play(FadeIn(code))
        f = MathTex(r"f = 10 + x_1^2 - 10\cos(2\pi x_1) + x_2^2", font_size=32).next_to(
            code, DOWN, buff=0.5
        )
        self.play(Write(f))
        self.say(
            "10 boxes instead of 100: the unimodal variable stays continuous within each box.",
            3,
        )
        self.say(
            "Useful only when the multimodality is concentrated in a few variables.",
            3,
        )
        self.clear_all()


class S7cDensity(Captioned):
    def construct(self):
        title = text("4 · Estimating the density: counting the basins", 38).to_edge(
            UP, buff=0.4
        )
        self.play(FadeIn(title))
        land = Landscape(rastrigin, side=5.0, center=4.0 * LEFT + 0.5 * DOWN)
        self.play(FadeIn(land.image), Create(land.frame))
        ax = Axes(
            x_range=[LO, HI, 1],
            y_range=[0, 80, 20],
            x_length=6.8,
            y_length=3.0,
            axis_config={"include_tip": False, "color": GREY_B},
            x_axis_config={"include_ticks": False},
            y_axis_config={"include_ticks": False},
        ).move_to(3.0 * RIGHT + 0.6 * UP)
        self.play(Create(ax))
        formula = MathTex(
            r"N_j = \mathbb{E}_{x_\perp}\big[\#\{\text{minima of } t \mapsto f(x_\perp + t\,e_j)\}\big]",
            r"\qquad m_j = N_j",
            font_size=32,
        ).move_to(2.9 * RIGHT + 1.6 * DOWN)
        formula.scale_to_fit_width(min(formula.width, 7.0))
        rng = np.random.default_rng(3)
        count_label = None
        for scan, y0 in enumerate((1.35, -2.7, 3.6)):
            line = Line(land.p(LO, y0), land.p(HI, y0), color=YELLOW, stroke_width=3)
            anchor = Dot(land.p(rng.uniform(LO, HI), y0), color=YELLOW)
            ts = np.sort(rng.uniform(LO, HI, 400))
            vs = rastrigin(ts, y0)
            curve = VMobject(color=YELLOW, stroke_width=2.5).set_points_as_corners(
                list(starmap(ax.c2p, zip(ts, vs, strict=False)))
            )
            dots = VGroup(*[
                Dot(ax.c2p(t, v), radius=0.025, color=GREY_A)
                for t, v in zip(ts[::4], vs[::4], strict=False)
            ])
            peaks, _ = find_peaks(-vs, prominence=0.03 * (vs.max() - vs.min()))
            marks = VGroup(*[
                Triangle(color=GOOD, fill_opacity=1)
                .scale(0.07)
                .rotate(PI)
                .next_to(ax.c2p(ts[p], vs[p]), UP, buff=0.05)
                for p in peaks
            ])
            self.play(FadeIn(anchor, scale=2), run_time=0.4)
            self.play(Create(line), FadeIn(dots), run_time=0.8)
            self.play(Create(curve), run_time=1)
            self.play(
                LaggedStart(
                    *[FadeIn(m, shift=0.1 * DOWN) for m in marks], lag_ratio=0.05
                )
            )
            new_label = text(f"basins kept: {len(peaks)}", 28, GOOD).next_to(
                ax, UP, buff=0.1
            )
            self.play(
                FadeIn(new_label)
                if count_label is None
                else Transform(count_label, new_label)
            )
            if count_label is None:
                count_label = new_label
            if scan == 0:
                self.play(Write(formula))
                self.say(
                    "Axial scan from a random anchor; the minima deep enough (by prominence) are counted.",
                    3,
                )
            elif scan == 1:
                self.say(
                    "Random abscissae: an even step resonates with a regular landscape.",
                    3,
                )
            self.play(
                FadeOut(line),
                FadeOut(anchor),
                FadeOut(curve),
                FadeOut(dots),
                FadeOut(marks),
                run_time=0.5,
            )
        self.say(
            "The error is one-sided: a ladder of scan rates only gives a lower bound.",
            3,
        )
        self.say(
            "If it does not converge, one box per basin is not appropriate → hierarchies.",
            3,
        )
        self.clear_all()


class S7dHierarchies(Captioned):
    def construct(self):
        title = text("5 · Hierarchies of subdivisions", 38).to_edge(UP, buff=0.4)
        self.play(FadeIn(title))
        side = 3.4
        centers = [4.5 * LEFT + 0.3 * DOWN, 0.3 * DOWN, 4.5 * RIGHT + 0.3 * DOWN]
        names = ["two levels", "deep", "frontier"]
        frames = VGroup(*[Square(side, color=GREY_B).move_to(c) for c in centers])
        labels = VGroup(*[
            text(n, 28, BLUE_B).next_to(f, UP, buff=0.15)
            for n, f in zip(names, frames, strict=False)
        ])
        self.play(Create(frames), FadeIn(labels))

        def subgrid(sq, m, color=GREY_C, width=1.5):
            g = VGroup()
            w = sq.width
            dl = sq.get_corner(DL)
            for k in range(1, m):
                g.add(
                    Line(
                        dl + k * w / m * RIGHT,
                        dl + k * w / m * RIGHT + w * UP,
                        color=color,
                        stroke_width=width,
                    )
                )
                g.add(
                    Line(
                        dl + k * w / m * UP,
                        dl + k * w / m * UP + w * RIGHT,
                        color=color,
                        stroke_width=width,
                    )
                )
            return g

        def child(sq, m, i, j):
            w = sq.width / m
            return Square(w).move_to(
                sq.get_corner(DL) + (i + 0.5) * w * RIGHT + (j + 0.5) * w * UP
            )

        # Two levels.
        f0 = frames[0]
        self.play(Create(subgrid(f0, 4)))
        best = [child(f0, 4, 1, 2), child(f0, 4, 3, 0)]
        self.play(
            *[b.animate.set_stroke(ACCENT, 4) for b in best],
            *[FadeIn(b.set_stroke(ACCENT, 4)) for b in best],
        )
        self.play(*[Create(subgrid(b, 4, ACCENT, 1)) for b in best])
        self.say(
            "Two levels: solve a coarse subdivision, then refine the k best boxes.",
            2.5,
        )

        # Deep.
        sq = frames[1]
        picks = [(0, 1), (1, 0), (1, 1), (0, 0)]
        for level, (i, j) in enumerate(picks):
            self.play(Create(subgrid(sq, 2, GREY_C, 2 - 0.3 * level)), run_time=0.5)
            nxt = child(sq, 2, i, j).set_stroke(ACCENT, 3)
            self.play(Create(nxt), run_time=0.5)
            sq = nxt
        res = MathTex(
            r"2^4 = 16 \text{ per variable,}\ 2n \text{ binaries per level}",
            font_size=26,
        ).next_to(frames[1], DOWN, buff=0.15)
        self.play(FadeIn(res))
        self.say(
            "Deep: halve each variable at each level and keep the best box.",
            2.5,
        )

        # Frontier.
        f2 = frames[2]
        self.play(Create(subgrid(f2, 2)))
        a = child(f2, 2, 0, 1).set_stroke(ACCENT, 3)
        self.play(Create(a))
        self.play(Create(subgrid(a, 2, ACCENT, 1)))
        b = child(f2, 2, 1, 0).set_stroke(GOOD, 3)
        back = text("backtracking", 22, GOOD).next_to(f2, DOWN, buff=0.15)
        self.play(Create(b), FadeIn(back))
        self.play(Create(subgrid(b, 2, GOOD, 1)))
        bb = child(b, 2, 1, 1).set_stroke(GOOD, 3)
        self.play(Create(bb), Create(subgrid(bb, 2, GOOD, 1)))
        self.say(
            "Frontier: a priority queue of open boxes — a spatial branch-and-bound.",
            3,
        )
        self.say(
            "The price: each node has its own master, and the cuts of the parent are discarded.",
            3,
        )
        self.say(
            "A win when a basin is too broad: Ackley, 4 starts out of 6 against 2 for the flat subdivision.",
            3.5,
        )
        self.clear_all()


class S7eMultiResolution(Captioned):
    def construct(self):
        title = text("6 · Multi-resolution encoding", 38).to_edge(UP, buff=0.4)
        self.play(FadeIn(title))
        bar = Rectangle(width=11, height=0.5, color=GREY_B).shift(1.6 * UP)
        lo_l = MathTex("L_j", font_size=30).next_to(bar, LEFT)
        hi_l = MathTex("U_j", font_size=30).next_to(bar, RIGHT)
        self.play(Create(bar), FadeIn(lo_l), FadeIn(hi_l))
        m = 4
        w = 11 / m
        coarse = VGroup(*[
            Line(
                bar.get_corner(DL) + k * w * RIGHT,
                bar.get_corner(UL) + k * w * RIGHT,
                color=GREY_B,
            )
            for k in range(1, m)
        ])
        digits1 = VGroup(*[
            MathTex(str(k), font_size=28).move_to(
                bar.get_left() + (k + 0.5) * w * RIGHT + 0.5 * UP
            )
            for k in range(m)
        ])
        self.play(Create(coarse), FadeIn(digits1))
        d1 = 2
        sel1 = Rectangle(
            width=w, height=0.5, color=BLUE, fill_opacity=0.4, stroke_width=3
        ).move_to(bar.get_left() + (d1 + 0.5) * w * RIGHT)
        self.play(FadeIn(sel1))
        zoom = Rectangle(width=11, height=0.5, color=BLUE).shift(0.1 * DOWN)
        l1 = DashedLine(sel1.get_corner(DL), zoom.get_corner(UL), color=GREY_C)
        l2 = DashedLine(sel1.get_corner(DR), zoom.get_corner(UR), color=GREY_C)
        fine = VGroup(*[
            Line(
                zoom.get_corner(DL) + k * w * RIGHT,
                zoom.get_corner(UL) + k * w * RIGHT,
                color=GREY_B,
            )
            for k in range(1, m)
        ])
        digits2 = VGroup(*[
            MathTex(str(k), font_size=28).move_to(
                zoom.get_left() + (k + 0.5) * w * RIGHT + 0.5 * DOWN
            )
            for k in range(m)
        ])
        self.play(Create(l1), Create(l2), Create(zoom), Create(fine), FadeIn(digits2))
        d2 = 1
        sel2 = Rectangle(
            width=w, height=0.5, color=ACCENT, fill_opacity=0.5, stroke_width=3
        ).move_to(zoom.get_left() + (d2 + 0.5) * w * RIGHT)
        self.play(FadeIn(sel2))
        idx = MathTex(
            r"\text{index} = (", "2", r"\,", "1", r")_4 = 9", font_size=36
        ).shift(1.3 * DOWN)
        idx[1].set_color(BLUE)
        idx[3].set_color(ACCENT)
        self.play(Write(idx))
        formula = MathTex(
            r"l_j(\alpha) = L_j + \Delta_j \sum_{k=1}^{L} m^{-k}\, d_k(\alpha_j)",
            font_size=36,
        ).next_to(idx, DOWN, buff=0.4)
        self.play(Write(formula))
        self.say(
            "One categorical variable per level: the levels are the digits of the box index in base m.",
            3,
        )
        self.clear_all()

        head = VGroup(
            text("resolution", 28),
            text("flat, n = 5", 28, BAD),
            text("levels, n = 5", 28, GOOD),
        )
        rows = [
            head,
            VGroup(MathTex("16"), MathTex("80"), MathTex(r"40 \ (m{=}4, L{=}2)")),
            VGroup(MathTex("64"), MathTex("320"), MathTex(r"60 \ (m{=}4, L{=}3)")),
            VGroup(MathTex("1024"), MathTex("5120"), MathTex(r"100 \ (m{=}4, L{=}5)")),
        ]
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                cell.move_to(np.array([[-4.0, -0.5, 3.5][c], 2.3 - 0.9 * r, 0]))
        rule = Line(6 * LEFT, 6 * RIGHT, color=GREY_B).move_to(1.85 * UP)
        bin_eq = MathTex(
            r"n\,m^L \quad\text{versus}\quad n\,m\,L \ \text{binaries}", font_size=36
        ).move_to(1.3 * DOWN)
        self.play(FadeIn(head), Create(rule))
        for row in rows[1:]:
            self.play(FadeIn(row, shift=0.2 * UP), run_time=0.6)
        self.play(Write(bin_eq))
        self.say(
            "A single master keeps every cut, and can change a coarse and a fine digit at once.",
            3,
        )
        self.say(
            "Limitation: the cut model is additive over the digits. The trust radius becomes 2L.",
            3.5,
        )
        self.clear_all()


# ---------------------------------------------------------------------------
# 8. Results and conclusion
# ---------------------------------------------------------------------------


class S8Conclusion(Captioned):
    def construct(self):
        title = text("What the experiments show", 44).to_edge(UP, buff=0.5)
        self.play(FadeIn(title))
        facts = (
            VGroup(
                text(
                    "Rastrigin 2D: optimum after 20 to 36 % of the boxes, ~⅓ of the cost of enumerating them",
                    26,
                ),
                text(
                    "Rastrigin 5D: 100 000 boxes, 50 binaries — optimum from every start",
                    26,
                ),
                text(
                    "     in 1920 evaluations; none of the baselines reaches it",
                    26,
                    GREY_A,
                ),
                text(
                    "Styblinski-Tang 5D: 789 evaluations, against 2340 (multistart) and 2505 (DIRECT)",
                    26,
                ),
                text(
                    "GGP short cantilever, 108 variables: 82.1 against 84.0 (MMA) and 83.0 (MMA multistart)",
                    26,
                ),
            )
            .arrange(DOWN, aligned_edge=LEFT, buff=0.35)
            .next_to(title, DOWN, buff=0.6)
        )
        facts.scale_to_fit_width(min(facts.width, 12.5)).set_x(0)
        for f in facts:
            self.play(FadeIn(f, shift=0.2 * RIGHT), run_time=0.7)
            self.wait(1.2)
        self.wait(2)
        self.play(FadeOut(facts), FadeOut(title))
        key = text("The subdivision must separate the basins.", 44, ACCENT)
        lims = VGroup(
            text("too coarse: several minima per box", 28, GREY_A),
            text(
                "too fine: more binaries than the budget can identify",
                28,
                GREY_A,
            ),
            text(
                "otherwise, other methods do better (Bayesian optimization at small budgets)",
                28,
                GREY_A,
            ),
        ).arrange(DOWN, buff=0.3)
        VGroup(key, lims).arrange(DOWN, buff=0.6)
        self.play(Write(key))
        self.play(LaggedStart(*[FadeIn(line) for line in lims], lag_ratio=0.4))
        self.wait(4)
        self.clear_all()
        code = Code(
            code_string=(
                "pip install gemseo-box-subdivision\n\n"
                "from gemseo_box_subdivision import BoxSubdivisionScenario\n\n"
                "scenario = BoxSubdivisionScenario(\n"
                '    [objective_discipline], "f", design_space, n_subdivisions=10\n'
                ")\nscenario.execute()"
            ),
            language="python",
            background="rectangle",
            add_line_numbers=False,
        ).scale(0.85)
        name = text("gemseo-box-subdivision", 48).next_to(code, UP, buff=0.6)
        url = text(
            "simoneconiglio.github.io/gemseo-box-subdivision", 28, BLUE_B
        ).next_to(code, DOWN, buff=0.5)
        self.play(FadeIn(name), FadeIn(code, shift=0.2 * UP))
        self.play(FadeIn(url))
        self.wait(4)
        self.clear_all(1.5)


SCENES = [
    "S1Problem",
    "S2Subdivision",
    "S3Bilevel",
    "S4Cuts",
    "S5TrustRegion",
    "S6Run",
    "S7Variants",
    "S7aFormulations",
    "S7bPartial",
    "S7cDensity",
    "S7dHierarchies",
    "S7eMultiResolution",
    "S8Conclusion",
]
