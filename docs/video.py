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
3Blue1Brown, one scene per section, the run of ``S12Run`` being the one of
the animation of the methodology, recorded when the scene is rendered. Manim
and the package are installed in the same environment, and LaTeX is required
for the formulas:

```shell
pip install -e . manim "pillow<11" cma egobox
manim -qh docs/video.py $(python -c "import sys; sys.path.insert(0, 'docs'); \\
    import video; print(' '.join(video.SCENES))")
```

The scenes are written to ``media/videos/video/``, in the order of ``SCENES``,
and are joined with ``ffmpeg -f concat``. Pillow is pinned because Manim 0.22
fails to draw images with Pillow 13.

The captions are read aloud when ``VIDEO_VOICE_DIR`` names a directory holding
the ``kokoro.onnx`` and ``voices.bin`` files of
`Kokoro <https://github.com/thewh1teagle/kokoro-onnx/releases>`_, the voice
being ``VIDEO_VOICE``, ``am_michael`` by default; each scene then waits for its
sentences to end, and the captions are hidden unless ``VIDEO_CAPTIONS=1``.
Without it, the video is silent and captioned:

```shell
pip install kokoro-onnx soundfile
VIDEO_VOICE_DIR=path/to/kokoro manim -qh docs/video.py S1Problem
```
"""

# The text on screen is mathematical, with Greek letters and signs.
# ruff: noqa: RUF001

from __future__ import annotations

import hashlib
import os
import re
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
from manim import Circle
from manim import Code
from manim import Create
from manim import Cross
from manim import DashedLine
from manim import Dot
from manim import FadeIn
from manim import FadeOut
from manim import Flash
from manim import Group
from manim import GrowArrow
from manim import ImageMobject
from manim import Indicate
from manim import LaggedStart
from manim import Line
from manim import MathTex
from manim import MoveAlongPath
from manim import Polygon
from manim import Rectangle
from manim import Scene
from manim import Square
from manim import Star
from manim import SurroundingRectangle
from manim import Text
from manim import Transform
from manim import Triangle
from manim import ValueTracker
from manim import VGroup
from manim import VMobject
from manim import Write
from manim import always_redraw
from manim import config
from manim import rate_functions
from matplotlib import colormaps
from scipy.signal import find_peaks

config.background_color = "#0e1116"

FONT = "Latin Modern Roman"
ACCENT = "#ff9a3c"  # the box being solved
SOLVED = BLUE_C  # the boxes already solved
GOOD = "#5fd38d"  # the incumbent, a valid cut
BAD = "#ff5c5c"
LO, HI = -4.1, 5.9


VOICE = os.environ.get("VIDEO_VOICE", "am_michael")
"""The Kokoro voice of the narration."""

SPOKEN = (
    (
        r"radius 2 → optimum from every start; no trust region → failure",
        (
            "a radius of 2 reaches the optimum from every start, and without a trust "
            "region the method fails"
        ),
    ),
    (
        r"normalized → optimum from every start; constraint → from all but one",
        (
            "the normalized formulation reaches the optimum from every start, the "
            "constraint formulation from all but one"
        ),
    ),
    (r"not appropriate → hierarchies", "not appropriate, and hierarchies are needed"),
    (r"\b2L\b", "2 L"),
    (r"\bu\(B\)", "u of B"),
    (
        r"∇f · ∂x/∂α",
        "the gradient of f times the derivative of x with respect to alpha",
    ),
    (r"\[0,1\]ⁿ", "the unit hypercube"),
    (r"10 × 10 = 100", "ten by ten, so one hundred"),
    (r"100 000", "one hundred thousand"),
    (r"\((\d),(\d)\)", r"box \1 \2"),
    (r"Σ mⱼ", "the sum of the m j"),
    (r"(\d)D\b", r"\1 D"),
    (r"∈ \{0, 1\}", "is zero or one"),
    (r"\bf = ", "f equals "),
    (r" = ", " equals "),
    (r"7th", "seventh"),
    (r"−", "minus "),
    (r"≥", "at least"),
    (r"→", ","),
    (r"[—…;]", ","),
    (r"κ", "kappa"),
    (r"δ", "delta"),
    (r"α", "alpha"),
    (r"gemseo-bilevel-outer-approximation", "gemseo bilevel outer approximation"),
    (r"\s+,", ","),
    (r",+", ","),
    (r"^\s*,\s*", ""),
)
"""The rewritings of the captions that a speech synthesizer would misread."""


CAPTIONS = os.environ.get(
    "VIDEO_CAPTIONS", "0" if os.environ.get("VIDEO_VOICE_DIR") else "1"
) not in {"0", ""}
"""Whether the narration is shown as captions, by default only without a voice."""


def spoken(message):
    """Return a caption as it is to be read aloud."""
    for pattern, replacement in SPOKEN:
        message = re.sub(pattern, replacement, message)
    return message


def speech(message):
    """Return the audio file of a sentence read aloud, if a voice is configured.

    The narration is synthesized by
    `Kokoro <https://github.com/thewh1teagle/kokoro-onnx>`_ when
    ``VIDEO_VOICE_DIR`` names the directory of its ``kokoro.onnx`` and
    ``voices.bin``, and each sentence is cached there.

    Returns:
        The path of the audio file and its duration in seconds, or ``None``.
    """
    directory = os.environ.get("VIDEO_VOICE_DIR")
    if not directory:
        return None

    import soundfile

    directory = Path(directory)
    key = hashlib.sha1(f"{VOICE}:{message}".encode()).hexdigest()[:16]
    path = directory / "cache" / f"{key}.wav"
    if not path.exists():
        from kokoro_onnx import Kokoro

        if not hasattr(speech, "model"):
            speech.model = Kokoro(
                str(directory / "kokoro.onnx"), str(directory / "voices.bin")
            )
        samples, rate = speech.model.create(message, voice=VOICE, lang="en-us")
        path.parent.mkdir(parents=True, exist_ok=True)
        soundfile.write(path, samples, rate)

    return path, soundfile.info(path).duration


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
    voice_end = 0.0

    def hush(self):
        """Wait for the sentence being read to end."""
        remaining = self.voice_end - self.renderer.time
        if remaining > 0:
            self.wait(remaining + 0.2)

    def narrate(self, message):
        """Read a sentence aloud, without a caption, once the previous one ends.

        Returns:
            The duration of the sentence, zero without a voice.
        """
        audio = speech(spoken(message))
        if audio is None:
            return 0.0

        self.hush()
        self.add_sound(str(audio[0]))
        self.voice_end = self.renderer.time + audio[1]
        return audio[1]

    def say(self, message, wait=2.5, size=28, run_time=0.8, voice=None):
        duration = self.narrate(voice or message)
        if not CAPTIONS:
            self.wait(max(wait, duration + 0.4))
            return

        # Long enough to be read, at about fifteen characters per second, or
        # to be heard to the end.
        wait = max(wait, 0.065 * len(message), duration - run_time + 0.6)
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
        self.hush()
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


def ackley(x, y):
    return (
        -20 * np.exp(-0.2 * np.sqrt(0.5 * (x**2 + y**2)))
        - np.exp(0.5 * (np.cos(2 * np.pi * x) + np.cos(2 * np.pi * y)))
        + np.e
        + 20
    )


def styblinski_1d(x):
    return 0.5 * (x**4 - 16 * x**2 + 5 * x)


def styblinski_1d_prime(x):
    return 0.5 * (4 * x**3 - 32 * x + 5)


def styblinski_tang(x, y):
    return styblinski_1d(x) + styblinski_1d(y)


def griewank(x, y):
    return 1 + (x**2 + y**2) / 4000 - np.cos(x) * np.cos(y / np.sqrt(2))


def record_samples(budget=400):
    """Return the points each baseline evaluates on Rastrigin in two dimensions."""
    sys.path.insert(0, str(Path(__file__).parent))
    from figures import _sample

    return {method: _sample(method, budget) for method in BASELINES}


BASELINES = ("multistart", "cmaes", "direct", "egobox")
"""The baselines whose evaluations are shown, by their name in the benchmarks."""


class Toy:
    """Styblinski-Tang in one variable, cut into ten boxes, each solved from its centre.

    The value and the multipliers of each box are those of a projected gradient
    descent, and the cut of a box is exact: with one variable and the box as a
    constraint, the prediction of a cut is affine in the bounds of the other box.
    """

    LO = -4.9
    WIDTH = 1.0
    M = 10

    def __init__(self):
        self.lb = self.LO + self.WIDTH * np.arange(self.M)
        self.ub = self.lb + self.WIDTH
        self.paths, self.x, self.u, self.lam_u, self.lam_l = [], [], [], [], []
        for k in range(self.M):
            x = (self.lb[k] + self.ub[k]) / 2
            path = [x]
            for _ in range(4000):
                x = float(
                    np.clip(x - 0.002 * styblinski_1d_prime(x), self.lb[k], self.ub[k])
                )
                path.append(x)
            gradient = styblinski_1d_prime(x)
            self.paths.append(np.array(path))
            self.x.append(x)
            self.u.append(styblinski_1d(x))
            self.lam_u.append(-gradient if np.isclose(x, self.ub[k]) else 0.0)
            self.lam_l.append(gradient if np.isclose(x, self.lb[k]) else 0.0)

    def predict(self, i, k, kappa=0.0):
        """Return the value the cut of box i predicts at box k."""
        value = (
            self.u[i]
            - self.lam_u[i] * (self.ub[k] - self.ub[i])
            + self.lam_l[i] * (self.lb[k] - self.lb[i])
        )
        return value if k == i else value - kappa

    def bound(self, solved, k, kappa=0.0):
        """Return the lower bound of the master at box k."""
        return max(self.predict(i, k, kappa) for i in solved)

    def next_box(self, solved, kappa=0.0):
        """Return the box the master solves next, or None once it stops."""
        bounds = {
            k: self.bound(solved, k, kappa) for k in range(self.M) if k not in solved
        }
        if not bounds:
            return None
        k = min(bounds, key=bounds.get)
        return k if bounds[k] < min(self.u[i] for i in solved) - 1e-6 else None


class CutChart:
    """The boxes of the toy along an axis, their values, cuts and bounds."""

    Y = (-100, 60)

    def __init__(self, toy, center=0.4 * DOWN):
        self.toy = toy
        self.ax = Axes(
            x_range=[0.5, 10.5, 1],
            y_range=[*self.Y, 20],
            y_axis_config={
                "include_ticks": True,
                "include_numbers": True,
                "font_size": 22,
            },
            x_length=11.5,
            y_length=5.4,
            axis_config={"include_tip": False, "color": GREY_B},
            x_axis_config={"include_ticks": False},
        ).move_to(center)
        self.labels = VGroup(*[
            text(str(k + 1), 22, GREY_B).next_to(self.ax.c2p(k + 1, self.Y[0]), DOWN)
            for k in range(toy.M)
        ])
        self.titles = VGroup(
            text("box", 24, GREY_B).next_to(self.ax.c2p(10.5, self.Y[0]), RIGHT),
            text("value", 24, GREY_B).next_to(self.ax.c2p(0.5, self.Y[1]), UP),
        )
        self.zero = DashedLine(
            self.ax.c2p(0.5, 0), self.ax.c2p(10.5, 0), color=GREY_D, stroke_width=1
        )

    def value(self, k, color=WHITE, opacity=1.0, width=6):
        u = self.toy.u[k]
        return Line(
            self.ax.c2p(k + 0.65, u),
            self.ax.c2p(k + 1.35, u),
            color=color,
            stroke_width=width,
            stroke_opacity=opacity,
        )

    def cut(self, i, kappa=0.0, color=BLUE_B):
        # The predictions are affine in the box index, so the cut is a line,
        # lowered by kappa away from its own box and clipped to the axes.
        a = self.toy.predict(i, i)
        b = (self.toy.lam_l[i] - self.toy.lam_u[i]) * self.toy.WIDTH
        lo, hi = self.Y
        group = VGroup()
        for x0, x1 in ((0.5, i + 0.65), (i + 1.35, 10.5)):
            if b == 0:
                inside = lo <= a - kappa <= hi
                xa, xb = x0, x1
            else:
                bounds = sorted(((i + 1) + (y + kappa - a) / b) for y in (lo, hi))
                xa, xb = max(x0, bounds[0]), min(x1, bounds[1])
                inside = xb > xa
            if inside:
                group.add(
                    Line(
                        self.ax.c2p(xa, a + b * (xa - (i + 1)) - kappa),
                        self.ax.c2p(xb, a + b * (xb - (i + 1)) - kappa),
                        color=color,
                        stroke_width=2.5,
                    )
                )
        group.add(Dot(self.ax.c2p(i + 1, a), radius=0.06, color=color))
        return group

    def bounds(self, solved, kappa=0.0):
        markers = VGroup()
        for k in range(self.toy.M):
            if k in solved:
                continue
            y = float(np.clip(self.toy.bound(solved, k, kappa), *self.Y))
            markers.add(
                Triangle(color=YELLOW, fill_opacity=1)
                .scale(0.09)
                .move_to(self.ax.c2p(k + 1, y))
            )
        return markers


def gaussian_process(xs, ys, grid, length=1.1):
    """Return the mean and standard deviation of a Gaussian process over a grid."""

    def kernel(a, b):
        return np.exp(-((a[:, None] - b[None, :]) ** 2) / (2 * length**2))

    mean0, scale = ys.mean(), ys.std()
    gram = kernel(xs, xs) + 1e-8 * np.eye(len(xs))
    cross = kernel(grid, xs)
    weights = np.linalg.solve(gram, (ys - mean0) / scale)
    mean = cross @ weights * scale + mean0
    variance = 1 - np.sum(cross * np.linalg.solve(gram, cross.T).T, axis=1)
    return mean, np.sqrt(np.clip(variance, 0, None)) * scale


def expected_improvement(mean, std, best):
    from scipy.stats import norm

    std = np.maximum(std, 1e-9)
    z = (best - mean) / std
    return (best - mean) * norm.cdf(z) + std * norm.pdf(z)


def curve(ax, xs, ys, **kwargs):
    return VMobject(**kwargs).set_points_as_corners(
        list(starmap(ax.c2p, zip(xs, ys, strict=True)))
    )


def cantilever_frames():
    """Return the frames of the animation of the cantilever run."""
    from PIL import Image
    from PIL import ImageSequence

    gif = Path(__file__).parent / "_static" / "figures" / "cantilever-dark.gif"
    with Image.open(gif) as animation:
        return [frame.convert("RGBA") for frame in ImageSequence.Iterator(animation)]


# ---------------------------------------------------------------------------
# 1. The hook
# ---------------------------------------------------------------------------


class S01Hook(Captioned):
    def construct(self):
        last = cantilever_frames()[-1]
        crop = ImageMobject(np.asarray(last.crop((440, 20, 880, 368))))
        crop.scale_to_fit_height(6.6).move_to(0.2 * DOWN)
        self.narrate(
            "This is a bracket, designed by a computer. Eighteen bars, arranged to make "
            "the structure as stiff as possible with a fixed amount of material."
        )
        self.play(FadeIn(crop), run_time=1.5)
        self.hush()
        scale = 6.6 / 348

        def at(x, y):
            # A pixel of the cropped frame, in the coordinates of the scene.
            return np.array([(x - 220) * scale, -0.2 + (174 - y) * scale, 0])

        frame = Rectangle(width=208 * scale, height=108 * scale, color=YELLOW)
        frame.move_to((at(137, 23) + at(345, 131)) / 2)
        self.play(Create(frame))
        self.hush()
        blue = Arrow(at(150, 330) + 0.3 * LEFT, at(150, 276), buff=0.05, color=BLUE_B)
        blue_label = text("84.0", 30, BLUE_B).next_to(blue.get_start(), DOWN, buff=0.1)
        orange = Arrow(at(415, 250), at(415, 292), buff=0.05, color=ACCENT)
        orange_label = text("82.1", 30, ACCENT).next_to(
            orange.get_start(), UP, buff=0.1
        )
        self.narrate(
            "The dashed blue curve is a standard gradient-based optimizer, started from "
            "a sensible initial design. It improves quickly, then stops at a compliance "
            "of eighty-four."
        )
        self.play(FadeOut(frame), GrowArrow(blue), FadeIn(blue_label))
        self.hush()
        self.narrate(
            "The orange curve is the method of this video. It keeps going, down to "
            "eighty-two point one, the design shown above."
        )
        self.play(GrowArrow(orange), FadeIn(orange_label))
        self.hush()
        self.narrate(
            "The blue run didn't make a mistake. It did exactly what it is built to do: "
            "walk downhill until nothing nearby is lower. The trouble is that this "
            "landscape has many valleys, and walking downhill only ever finds the one "
            "you started in."
        )
        self.hush()
        self.play(
            FadeOut(crop), FadeOut(VGroup(blue, blue_label, orange, orange_label))
        )
        title = text("Box subdivision", 64)
        sub = text("choosing where to look, one local solve at a time", 30, GREY_B)
        VGroup(title, sub).arrange(DOWN, buff=0.4)
        self.narrate(
            "This video is about one way to decide where to look: box subdivision."
        )
        self.play(Write(title), run_time=1.5)
        self.play(FadeIn(sub, shift=0.2 * UP))
        self.wait(1)
        self.clear_all()


# ---------------------------------------------------------------------------
# 2. A ball on a curve
# ---------------------------------------------------------------------------


class S02LocalSolver(Captioned):
    def construct(self):
        ax = Axes(
            x_range=[LO, HI, 1],
            y_range=[0, 50, 10],
            x_length=11.5,
            y_length=4.6,
            axis_config={"include_tip": False, "color": GREY_B},
            x_axis_config={"include_ticks": False},
        ).shift(0.2 * DOWN)
        graph = ax.plot(
            rastrigin_1d, x_range=[LO, HI, 0.005], color=BLUE, stroke_width=4
        )
        self.narrate(
            "To see what's going on, shrink the problem to a single variable. Here's a "
            "function with lots of dips."
        )
        self.play(Create(ax), Create(graph), run_time=2)
        self.hush()

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

        self.narrate(
            "A gradient-based local solver behaves like a ball released on this curve. "
            "It rolls to the bottom of whatever valley it's in, and it does that very "
            "efficiently."
        )
        dot, xend = roll(3.35)
        value = MathTex(
            rf"{rastrigin_1d(xend):.2f}", font_size=34, color=YELLOW
        ).next_to(dot, UP)
        self.play(FadeIn(value))
        self.hush()
        self.narrate("Release it somewhere else, and it settles somewhere else.")
        for x0 in (-2.6, 1.65, 4.4):
            roll(x0, GREY_A, 1.0)
        self.hush()
        star = Star(color=GOOD, fill_opacity=1, outer_radius=0.18).move_to(ax.c2p(0, 0))
        self.narrate(
            "Only if you happen to drop it in the middle valley does it find the true "
            "minimum, zero."
        )
        self.play(FadeIn(star, scale=2))
        self.hush()
        question = text("going downhill is easy.\nchoosing where to start is not.", 40)
        question.to_edge(UP, buff=0.3)
        self.narrate(
            "So the hard part isn't going downhill. The hard part is choosing where to "
            "start."
        )
        self.play(FadeIn(question))
        self.clear_all()


# ---------------------------------------------------------------------------
# 3. The zoo
# ---------------------------------------------------------------------------


ZOO = (
    (
        "Rastrigin",
        rastrigin,
        (-4.1, 5.9),
        0.0,
        "an egg crate: about 10ⁿ valleys",
        (
            "Rastrigin is an egg crate: a bowl with a regular grid of dimples, about one "
            "unit apart. In two dimensions that's around a hundred local minima; in five "
            "dimensions, around a hundred thousand. Only one of them, at the centre, is "
            "the global minimum."
        ),
    ),
    (
        "Ackley",
        ackley,
        (-28.7, 34.9),
        0.0,
        "one huge funnel, covered in ripples",
        (
            "Ackley is almost the opposite. There's really just one valley, an enormous "
            "funnel sixty units wide, but its whole surface is covered in fine ripples. "
            "Up close it looks like Rastrigin; from far away it's a single bowl."
        ),
    ),
    (
        "Styblinski-Tang",
        styblinski_tang,
        (-4.9, 5.1),
        -2.904,
        "two deep valleys per variable: 2ⁿ",
        (
            "Styblinski-Tang has just two deep, well-separated valleys per variable, one "
            "slightly deeper than the other. In five dimensions, that's thirty-two "
            "basins, and you have to find the deepest corner."
        ),
    ),
    (
        "Griewank",
        griewank,
        (-58.1, 61.9),
        0.0,
        "a shallow bowl, dense near-identical dips",
        (
            "And Griewank: a very shallow bowl under a dense pattern of dips that are "
            "almost exactly the same depth. Finding the very best one is so hard that, "
            "spoiler, none of the methods in this video manage it."
        ),
    ),
)
"""The test functions: name, function, bounds, optimum coordinate, tag, narration."""


class S03Zoo(Captioned):
    def construct(self):
        self.narrate(
            "To test ideas like this, people use a small zoo of functions, each designed "
            "to be nasty in its own way. Let's meet four of them, because we'll come "
            "back to all of them."
        )
        corners = (
            3.3 * LEFT + 1.75 * UP,
            3.3 * RIGHT + 1.75 * UP,
            3.3 * LEFT + 1.95 * DOWN,
            3.3 * RIGHT + 1.95 * DOWN,
        )
        self.wait(1)
        for name, f, (lo, hi), opt, tag, narration in ZOO:
            land = Landscape(f, side=4.6, center=3.6 * LEFT + 0.1 * DOWN, lo=lo, hi=hi)
            title = text(name, 40).move_to(3.0 * RIGHT + 2.8 * UP)
            subtitle = text(tag, 26, GREY_A).next_to(title, DOWN, buff=0.2)
            xs = np.linspace(lo, hi, 1200)
            ys = f(xs, np.full_like(xs, opt))
            pad = 0.08 * (ys.max() - ys.min())
            ax = Axes(
                x_range=[lo, hi, (hi - lo) / 4],
                y_range=[ys.min() - pad, ys.max() + pad, (ys.max() - ys.min()) / 4],
                x_length=6.2,
                y_length=3.4,
                axis_config={"include_tip": False, "color": GREY_B},
                x_axis_config={"include_ticks": False},
                y_axis_config={"include_ticks": False},
            ).move_to(3.0 * RIGHT + 0.6 * DOWN)
            slice_line = Line(land.p(lo, opt), land.p(hi, opt), color=YELLOW)
            profile = curve(ax, xs, ys, color=YELLOW, stroke_width=2.5)
            star = Star(color=GOOD, fill_opacity=1, outer_radius=0.13).move_to(
                land.p(opt, opt)
            )
            self.hush()
            self.narrate(narration)
            self.play(
                FadeIn(land.image), Create(land.frame), FadeIn(title), FadeIn(subtitle)
            )
            self.play(Create(slice_line), Create(ax), run_time=1)
            self.play(Create(profile), FadeIn(star, scale=2), run_time=2)
            self.hush()
            self.play(
                FadeOut(VGroup(title, subtitle, slice_line, ax, profile, star)),
                FadeOut(land.image),
                FadeOut(land.frame),
            )
        thumbnails = Group()
        for (name, f, (lo, hi), opt, *_), corner in zip(ZOO, corners, strict=True):
            land = Landscape(f, side=2.9, center=corner + 0.15 * DOWN, lo=lo, hi=hi)
            label = text(name, 26).next_to(land.frame, UP, buff=0.08)
            star = Star(color=GOOD, fill_opacity=1, outer_radius=0.09).move_to(
                land.p(opt, opt)
            )
            thumbnails.add(Group(land.image, land.frame, star, label))
        self.narrate(
            "One more detail: the bounds of every problem are shifted off-centre, so the "
            "true minimum doesn't sit conveniently in the middle of anything, including "
            "a box."
        )
        self.play(
            LaggedStart(*[FadeIn(t) for t in thumbnails], lag_ratio=0.3), run_time=2
        )
        self.wait(1)
        self.clear_all()


# ---------------------------------------------------------------------------
# 4. How people usually search
# ---------------------------------------------------------------------------


BASELINE_STORY = {
    "multistart": (
        "Multistart",
        BLUE_B,
        ("random starting points,", "a local solve from each,", "keep the best"),
        (
            "The simplest: multistart. Throw starting points at random, run the local "
            "solver from each one, keep the best result. It's robust, and with infinitely "
            "many starts it's guaranteed to find the answer. But every start is "
            "independent: the fiftieth run has learned nothing from the first forty-nine."
        ),
    ),
    "cmaes": (
        "CMA-ES",
        GOOD,
        (
            "a Gaussian cloud of samples,",
            "moved and reshaped",
            "toward the better half",
        ),
        (
            "CMA-ES is an evolution strategy. It samples a cloud of points from a "
            "Gaussian, keeps the better half, and moves and reshapes the Gaussian toward "
            "them. It uses no gradients, only the ranking of the points. Watch the cloud "
            "shrink onto one region: it commits."
        ),
    ),
    "direct": (
        "DIRECT",
        ACCENT,
        ("keep splitting the rectangles", "that could hold the minimum", ""),
        (
            "DIRECT, for dividing rectangles, is deterministic. It evaluates the centre of "
            "the space, then keeps splitting every rectangle that could still contain the "
            "minimum, either because it is large or because its centre is low. Very "
            "thorough in two dimensions; but the number of rectangles explodes as the "
            "dimension grows."
        ),
    ),
}


class S04Baselines(Captioned):
    def construct(self):
        samples = record_samples()
        land = Landscape(rastrigin, side=5.8, center=3.4 * LEFT + 0.1 * DOWN)
        self.narrate(
            "So how do people usually search a landscape like this? There are a few "
            "classic families, and it's revealing to watch where each one spends its "
            "evaluations. Same function, two-dimensional Rastrigin, same budget for all."
        )
        self.play(FadeIn(land.image), Create(land.frame))
        self.hush()
        for key, (name, color, lines, narration) in BASELINE_STORY.items():
            title = text(name, 44, color).move_to(3.4 * RIGHT + 2.3 * UP)
            body = VGroup(*[text(line, 28, GREY_A) for line in lines if line])
            body.arrange(DOWN, buff=0.2).next_to(title, DOWN, buff=0.5)
            dots = VGroup(*[
                Dot(land.p(*p), radius=0.04, color=color) for p in samples[key]
            ])
            self.narrate(narration)
            self.play(FadeIn(title), FadeIn(body))
            self.play(
                LaggedStart(*[FadeIn(d, scale=2) for d in dots], lag_ratio=0.02),
                run_time=8,
            )
            self.hush()
            self.play(FadeOut(dots), FadeOut(title), FadeOut(body))
        self.play(FadeOut(land.image), FadeOut(land.frame))

        # Bayesian optimization, shown on one variable first.
        title = text("Bayesian optimization (EGO)", 40, YELLOW).to_edge(UP, buff=0.3)
        ax = Axes(
            x_range=[-4.9, 5.1, 1],
            y_range=[-60, 100, 20],
            x_length=11,
            y_length=3.8,
            axis_config={"include_tip": False, "color": GREY_B},
            x_axis_config={"include_ticks": False},
            y_axis_config={"include_ticks": False},
        ).move_to(0.6 * UP)
        ei_ax = Axes(
            x_range=[-4.9, 5.1, 1],
            y_range=[0, 1, 0.5],
            x_length=11,
            y_length=1.3,
            axis_config={"include_tip": False, "color": GREY_B},
            x_axis_config={"include_ticks": False},
            y_axis_config={"include_ticks": False},
        ).move_to(2.6 * DOWN)
        ei_label = text("expected improvement", 22, ACCENT).next_to(
            ei_ax, UP, buff=0.05
        )
        grid = np.linspace(-4.9, 5.1, 400)
        visible = grid[styblinski_1d(grid) <= 100]
        truth = curve(ax, visible, styblinski_1d(visible), color=GREY_D, stroke_width=2)
        xs = np.array([-4.2, -0.5, 1.4, 3.9])
        self.narrate(
            "And Bayesian optimization, here the classic EGO algorithm. It's easiest to "
            "see in one variable. After a few evaluations, it fits a statistical model, "
            "a Gaussian process, through every point seen so far: a best guess, and a "
            "band of uncertainty that widens away from the data."
        )
        self.play(FadeIn(title), Create(ax), Create(truth))

        def model(points):
            mean, std = gaussian_process(points, styblinski_1d(points), grid)
            band = Polygon(
                *list(
                    starmap(
                        ax.c2p,
                        zip(grid, np.clip(mean + 2 * std, -60, 100), strict=True),
                    )
                ),
                *list(
                    starmap(
                        ax.c2p,
                        zip(
                            grid[::-1],
                            np.clip(mean - 2 * std, -60, 100)[::-1],
                            strict=True,
                        ),
                    )
                ),
                stroke_width=0,
                fill_color=BLUE,
                fill_opacity=0.25,
            )
            line = curve(
                ax, grid, np.clip(mean, -60, 100), color=BLUE_B, stroke_width=3
            )
            ei = expected_improvement(mean, std, styblinski_1d(points).min())
            ei_curve = curve(ei_ax, grid, ei / ei.max(), color=ACCENT, stroke_width=3)
            pick = grid[int(np.argmax(ei))]
            data = VGroup(*[
                Dot(ax.c2p(x, styblinski_1d(x)), radius=0.07, color=WHITE)
                for x in points
            ])
            return VGroup(band, line, data), ei_curve, pick

        fit, ei_curve, pick = model(xs)
        self.play(FadeIn(fit))
        self.hush()
        self.narrate(
            "The next point goes where the model expects the biggest improvement: either "
            "a low prediction, or a large uncertainty that might hide one."
        )
        self.play(Create(ei_ax), FadeIn(ei_label), Create(ei_curve))
        arrow = Arrow(ei_ax.c2p(pick, 1.3), ei_ax.c2p(pick, 0.9), buff=0, color=ACCENT)
        self.play(GrowArrow(arrow))
        for _ in range(2):
            xs = np.append(xs, pick)
            new_fit, new_ei, pick = model(xs)
            self.play(
                Transform(fit, new_fit), Transform(ei_curve, new_ei), FadeOut(arrow)
            )
            arrow = Arrow(
                ei_ax.c2p(pick, 1.3), ei_ax.c2p(pick, 0.9), buff=0, color=ACCENT
            )
            self.play(GrowArrow(arrow))
        self.hush()
        self.narrate(
            "It remembers everything, which makes it very economical with evaluations. "
            "The price is the model itself, which gets more expensive with every point "
            "added."
        )
        self.wait(1)
        self.clear_all()
        land = Landscape(rastrigin, side=5.8, center=3.4 * LEFT + 0.1 * DOWN)
        dots = VGroup(*[
            Dot(land.p(*p), radius=0.04, color=YELLOW) for p in samples["egobox"]
        ])
        title = text("EGO", 44, YELLOW).move_to(3.4 * RIGHT + 2.3 * UP)
        self.play(FadeIn(land.image), Create(land.frame), FadeIn(title))
        self.play(
            LaggedStart(*[FadeIn(d, scale=2) for d in dots], lag_ratio=0.02), run_time=6
        )
        question = text(
            "a local solve is rich information.\ncan it tell us where to solve next?",
            30,
        ).move_to(3.4 * RIGHT + 0.4 * DOWN)
        self.narrate(
            "Here's the question that drives the rest of this video. A local solve with "
            "gradients is a rich piece of information. Multistart throws it away. Could "
            "each local solve instead tell us where the next one should go?"
        )
        self.play(FadeIn(question))
        self.clear_all()


# ---------------------------------------------------------------------------
# 5. Turning "where" into "which"
# ---------------------------------------------------------------------------


class S05Boxes(Captioned):
    def construct(self):
        toy = Toy()
        ax = Axes(
            x_range=[toy.LO, toy.LO + toy.M * toy.WIDTH, 1],
            y_range=[-45, 90, 15],
            x_length=11.5,
            y_length=5.2,
            axis_config={"include_tip": False, "color": GREY_B},
            x_axis_config={"include_ticks": False},
            y_axis_config={"include_ticks": False},
        ).shift(0.1 * DOWN)
        graph = ax.plot(
            styblinski_1d, x_range=[-4.9, 4.78, 0.01], color=BLUE, stroke_width=4
        )
        self.narrate(
            "Here's the key move. Take a landscape, this time one variable of "
            "Styblinski-Tang, with its two valleys."
        )
        self.play(Create(ax), Create(graph), run_time=2)
        walls = VGroup(*[
            DashedLine(ax.c2p(x, -45), ax.c2p(x, 90), color=ACCENT, stroke_width=2)
            for x in toy.lb[1:]
        ])
        numbers = VGroup(*[
            text(str(k + 1), 22, GREY_B).move_to(ax.c2p(toy.lb[k] + 0.5, 84))
            for k in range(toy.M)
        ])
        self.hush()
        self.narrate(
            "Chop the range into ten intervals; call them boxes. From now on, the local "
            "solver is only ever allowed to run inside one box at a time."
        )
        self.play(
            LaggedStart(*[Create(w) for w in walls], lag_ratio=0.1), FadeIn(numbers)
        )
        self.hush()
        values = VGroup()
        self.narrate(
            "Start it at the centre of a box and let it roll, but it can't leave the box. "
            "Whatever it ends on is the best it found in that box. Call that number u of "
            "the box."
        )
        for k in range(toy.M):
            path = toy.paths[k][::40]
            ys = styblinski_1d(path)
            dot = Dot(ax.c2p(path[0], ys[0]), radius=0.08, color=YELLOW)
            mover = VMobject().set_points_as_corners(
                list(starmap(ax.c2p, zip(path, np.minimum(ys, 89), strict=True)))
            )
            segment = Line(
                ax.c2p(toy.lb[k] + 0.08, toy.u[k]),
                ax.c2p(toy.ub[k] - 0.08, toy.u[k]),
                color=YELLOW,
                stroke_width=6,
            )
            run_time = 1.2 if k < 3 else 0.5
            self.add(dot)
            self.play(MoveAlongPath(dot, mover), run_time=run_time)
            self.play(FadeIn(segment), FadeOut(dot), run_time=run_time / 2)
            values.add(segment)
        self.hush()
        self.narrate(
            "Look at what just happened. If we only ever see the landscape through the "
            "boxes, a continuous curve has become a list of ten numbers."
        )
        self.play(graph.animate.set_stroke(opacity=0.2), walls.animate.set_opacity(0.3))
        self.hush()
        best = values[1].copy().set_color(GOOD)
        self.narrate(
            "The question 'where should I start?' has become 'which box?': find the "
            "smallest number in a list where reading each entry costs one local solve. "
            "And if each box holds at most one valley, the smallest number is the global "
            "minimum."
        )
        self.play(Transform(values[1], best), Indicate(values[1], color=GOOD))
        self.clear_all()

        # The same in two dimensions.
        land = Landscape(rastrigin, side=6.0, center=3.3 * LEFT + 0.2 * DOWN)
        grid = land.grid(10)
        self.narrate(
            "In two dimensions the same chop gives a grid: ten intervals along each axis, "
            "a hundred boxes."
        )
        self.play(FadeIn(land.image), Create(land.frame))
        self.play(
            LaggedStart(*[Create(line) for line in grid], lag_ratio=0.05), run_time=1.5
        )
        self.hush()

        def selection(i, j):
            box = land.box(i, j, stroke_color=ACCENT, stroke_width=5)
            a1 = one_hot(10, i).move_to(3.6 * RIGHT + 1.0 * UP)
            a2 = one_hot(10, j).move_to(3.6 * RIGHT + 0.4 * DOWN)
            l1 = MathTex(r"x_1", font_size=34).next_to(a1, LEFT)
            l2 = MathTex(r"x_2", font_size=34).next_to(a2, LEFT)
            return VGroup(box, a1, a2, l1, l2)

        heading = text("which interval, on each axis?", 30).move_to(
            3.6 * RIGHT + 2.3 * UP
        )
        sel = selection(6, 3)
        self.narrate(
            "To name a box, answer one question per axis: which interval? Write each "
            "answer as a row of switches, with exactly one switch on. Two rows of ten "
            "switches pick one box out of a hundred."
        )
        self.play(FadeIn(heading), Create(sel[0]), FadeIn(sel[1:]))
        for i, j in ((2, 7), (8, 1), (4, 4)):
            self.play(Transform(sel, selection(i, j)), run_time=0.9)
            self.wait(0.4)
        self.clear_all()

        # What grows with the dimension.
        head = VGroup(MathTex("n"), text("boxes", 30), text("switches", 30))
        rows = [head]
        for n in range(1, 6):
            rows.append(
                VGroup(
                    MathTex(str(n)),
                    MathTex(f"{10**n:,}".replace(",", r"\,")),
                    MathTex(str(10 * n)),
                )
            )
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                cell.move_to(np.array([[-3.5, 0, 3.5][c], 2.4 - 0.85 * r, 0]))
        line = Line(5 * LEFT, 5 * RIGHT, color=GREY_B).move_to(2.0 * UP)
        self.narrate(
            "Now here's why the switches matter. Add dimensions, still ten intervals per "
            "axis. The number of boxes multiplies: ten, a hundred, a thousand..."
        )
        self.play(FadeIn(head), Create(line))
        for row in rows[1:]:
            row[1].set_color(BAD)
            row[2].set_color(GOOD)
            self.play(FadeIn(row, shift=0.2 * UP), run_time=0.6)
        self.hush()
        self.narrate(
            "...a hundred thousand in five dimensions. But the number of switches only "
            "adds up: fifty. The method never lists the boxes. Everything it does, it "
            "does with the switches."
        )
        self.play(Indicate(rows[-1][1], color=BAD), Indicate(rows[-1][2], color=GOOD))
        self.clear_all()


# ---------------------------------------------------------------------------
# 6. What a solve says beyond its value
# ---------------------------------------------------------------------------


class S06Multipliers(Captioned):
    def construct(self):
        toy = Toy()
        ax = Axes(
            x_range=[-0.3, 3.7, 1],
            y_range=[-30, 5, 5],
            x_length=11,
            y_length=5.2,
            axis_config={"include_tip": False, "color": GREY_B},
            x_axis_config={"include_ticks": False},
            y_axis_config={"include_ticks": False},
        ).shift(0.3 * DOWN)
        graph = ax.plot(
            styblinski_1d, x_range=[-0.3, 3.7, 0.01], color=BLUE, stroke_width=4
        )
        self.narrate(
            "Here's the ingredient that makes this work. When the solver finishes inside "
            "a box, it hands back more than a number. Zoom in on boxes six and eight."
        )
        self.play(Create(ax), Create(graph))
        wall_x = ValueTracker(toy.ub[5])
        left6 = DashedLine(ax.c2p(toy.lb[5], -30), ax.c2p(toy.lb[5], 5), color=ACCENT)
        right6 = always_redraw(
            lambda: DashedLine(
                ax.c2p(wall_x.get_value(), -30),
                ax.c2p(wall_x.get_value(), 5),
                color=ACCENT,
            )
        )
        ball6 = always_redraw(
            lambda: Dot(
                ax.c2p(wall_x.get_value(), styblinski_1d(wall_x.get_value())),
                radius=0.11,
                color=YELLOW,
            )
        )
        walls8 = VGroup(*[
            DashedLine(ax.c2p(x, -30), ax.c2p(x, 5), color=ACCENT)
            for x in (toy.lb[7], toy.ub[7])
        ])
        ball8 = Dot(ax.c2p(toy.x[7], toy.u[7]), radius=0.11, color=YELLOW)
        labels = VGroup(
            text("box 6", 26).move_to(ax.c2p(0.6, 3)),
            text("box 8", 26).move_to(ax.c2p(2.6, 3)),
        )
        self.play(Create(left6), Create(right6), Create(walls8), FadeIn(labels))
        self.play(FadeIn(ball6), FadeIn(ball8))
        self.hush()
        push = always_redraw(
            lambda: Arrow(
                ax.c2p(wall_x.get_value() - 0.45, styblinski_1d(wall_x.get_value())),
                ax.c2p(wall_x.get_value() - 0.02, styblinski_1d(wall_x.get_value())),
                buff=0,
                color=BAD,
            )
        )
        lam = MathTex(r"\lambda = 12.4", font_size=34, color=BAD).move_to(
            ax.c2p(0.4, -12)
        )
        self.narrate(
            "In box six, the lowest point the solver can reach is pressed against the "
            "right wall. That's a strong hint: the ground keeps going down beyond that "
            "wall. And the solver can say how strongly. The force with which the "
            "solution pushes on the wall, its Lagrange multiplier, is exactly how fast "
            "the value would drop if the wall moved."
        )
        self.play(GrowArrow(push), FadeIn(lam))
        self.hush()
        self.narrate(
            "Let's check: slide the wall to the right, and the value goes down, at that rate."
        )
        self.play(wall_x.animate.set_value(1.45), run_time=2.5)
        self.play(wall_x.animate.set_value(toy.ub[5]), run_time=1.2)
        self.hush()
        zero = MathTex(r"\lambda = 0", font_size=34, color=GOOD).move_to(
            ax.c2p(2.6, -27)
        )
        self.narrate(
            "In box eight, the solution sits at the bottom of a valley, away from both "
            "walls. Moving a wall changes nothing, and the multiplier is zero."
        )
        self.play(FadeIn(zero), Indicate(ball8, color=GOOD))
        self.hush()
        formula = MathTex(
            r"\frac{\mathrm{d}u}{\mathrm{d}\,\text{wall}} = -\lambda", font_size=40
        ).to_edge(UP, buff=0.3)
        self.narrate(
            "So every local solve gives two things: a value, and a slope, a sense of "
            "which direction is downhill in the space of boxes. And it comes for free: "
            "the multipliers are a by-product of solving the box."
        )
        self.play(Write(formula))
        self.clear_all()


# ---------------------------------------------------------------------------
# 7. Cuts and the master
# ---------------------------------------------------------------------------


class S07Cuts(Captioned):
    def construct(self):
        toy = Toy()
        chart = CutChart(toy)
        self.narrate(
            "Now put the boxes side by side, numbered one to ten, with value going up. "
            "A value and a slope are enough to draw a line through the other boxes: a "
            "guess at what each of them is worth. This line is called a cut."
        )
        self.play(
            Create(chart.ax),
            FadeIn(chart.labels),
            FadeIn(chart.titles),
            Create(chart.zero),
        )
        solved = [5]
        self.play(Create(chart.value(5, YELLOW)))
        cuts = VGroup(chart.cut(5))
        self.play(Create(cuts[0]), run_time=1.5)
        self.hush()
        self.narrate(
            "Box six was pressed against its right wall, so its cut slopes down to the "
            "right: things should get better that way, and worse to the left."
        )
        self.wait(1)
        self.hush()
        markers = chart.bounds(solved)
        self.narrate(
            "The cut is meant as a lower bound: no box should be better than the line "
            "says. The master problem reads off, for each unsolved box, its bound, here "
            "the yellow markers, and picks the box whose bound is lowest: the most "
            "promising box that hasn't been ruled out."
        )
        self.play(FadeIn(markers))
        self.hush()
        lines = (
            (
                "So it solves box ten. Surprise: seventeen, much worse than predicted. But "
                "box ten was pressed against its left wall, steeply, so its cut says "
                "the left is far better."
            ),
            (
                "With two cuts, the bound at each box is the highest of the two lines: the "
                "tightest claim wins. The lowest bound is now box nine."
            ),
            (
                "Box nine gives minus twenty-three, and a cut sloping down to the left. "
                "Then box eight: the bottom of a valley, minus twenty-five point oh three, "
                "and a perfectly flat cut."
            ),
        )
        for step in range(3):
            k = toy.next_box(solved)
            chosen = markers[[m for m in range(toy.M) if m not in solved].index(k)]
            self.play(Indicate(chosen, color=ACCENT, scale_factor=2))
            solved.append(k)
            new_cut = chart.cut(k)
            new_markers = chart.bounds(solved)
            self.narrate(lines[step])
            self.play(Create(chart.value(k, YELLOW)), Create(new_cut), run_time=1.5)
            cuts.add(new_cut)
            self.play(Transform(markers, new_markers))
            self.hush()
        k = toy.next_box(solved)
        best = DashedLine(
            chart.ax.c2p(0.5, toy.u[7]), chart.ax.c2p(10.5, toy.u[7]), color=GOOD
        )
        verdict = text("no bound below −25.03: stop", 30, GOOD).move_to(
            chart.ax.c2p(6.5, 45)
        )
        self.narrate(
            "And now the master looks at the remaining boxes, and every bound is above "
            "minus twenty-five. Nothing can beat what we already have. The master stops, "
            "and reports minus twenty-five point oh three as the optimum."
        )
        self.play(Create(best), FadeIn(verdict))
        self.hush()
        self.narrate(
            "This scheme is called outer approximation, and it goes back to Duran and "
            "Grossmann in 1986. For a convex problem it's beautiful: a cut can never "
            "overestimate, so a box the cuts rule out really is worse."
        )
        self.wait(1)
        self.clear_all()


# ---------------------------------------------------------------------------
# 8. When cuts lie, and the first fix
# ---------------------------------------------------------------------------


class S08Lies(Captioned):
    def construct(self):
        toy = Toy()
        chart = CutChart(toy)
        solved = [5, 9, 8, 7]
        values = VGroup(*[chart.value(k, YELLOW) for k in solved])
        kappa = ValueTracker(0.0)
        cuts = always_redraw(
            lambda: VGroup(*[chart.cut(i, kappa.get_value()) for i in solved])
        )
        markers = always_redraw(lambda: chart.bounds(solved, kappa.get_value()))
        self.add(
            chart.ax, chart.labels, chart.titles, chart.zero, values, cuts, markers
        )
        self.narrate(
            "But our landscape is about as far from convex as it gets. Let's reveal what "
            "the master never looked at."
        )
        truth = VGroup(*[
            chart.value(k, GREY_B, opacity=0.6, width=4)
            for k in range(toy.M)
            if k not in solved
        ])
        self.play(FadeIn(truth))
        self.hush()
        global_box = chart.value(1, BAD, width=7)
        self.narrate(
            "Box two holds minus thirty-nine point one seven: the global minimum. The "
            "master ruled it out because the cut from box six, extrapolated to the left, "
            "claimed it was worth at least forty-three. And box eight's flat cut said "
            "nothing anywhere could beat minus twenty-five."
        )
        self.play(Transform(truth[1], global_box), Indicate(truth[1], color=BAD))
        self.hush()
        self.narrate(
            "The master is confidently wrong. It reports convergence, and no error. "
            "This isn't a contrived example: with the default settings, not one run of "
            "the benchmark found the optimum, and every single one reported success."
        )
        self.wait(1)
        self.hush()
        title = text("Fix 1: lower every cut by κ", 34, BLUE_B).to_edge(UP, buff=0.3)
        self.narrate(
            "The first fix: make every cut more modest. Lower each cut by an amount "
            "kappa, everywhere except at the box it came from."
        )
        self.play(FadeIn(title))
        self.play(kappa.animate.set_value(60), run_time=4)
        self.hush()
        inset_ax = Axes(
            x_range=[0, 1, 0.5],
            y_range=[-0.3, 0.05, 0.1],
            x_length=2.6,
            y_length=1.4,
            axis_config={"include_tip": False, "color": GREY_B},
            y_axis_config={"include_ticks": False},
        ).move_to(4.6 * RIGHT + 2.3 * UP)
        parabola = inset_ax.plot(
            lambda a: a * (a - 1), x_range=[0, 1, 0.01], color=ACCENT
        )
        inset_label = MathTex(r"\kappa\,\alpha(\alpha - 1)", font_size=26, color=ACCENT)
        inset_label.next_to(inset_ax, DOWN, buff=0.05)
        self.narrate(
            "Mathematically this is a convex term added to the objective, kappa times "
            "alpha times alpha minus one for each switch. It's zero when a switch is "
            "fully on or fully off, so on every real box the problem is untouched. "
            "Only the cuts change."
        )
        self.play(
            FadeOut(title), Create(inset_ax), Create(parabola), FadeIn(inset_label)
        )
        self.hush()
        self.narrate(
            "With kappa at sixty, the bounds of the unsolved boxes fall below minus "
            "twenty-five, and the master keeps going."
        )
        for _ in range(4):
            k = toy.next_box(solved, 60)
            if k is None:
                break
            solved.append(k)
            self.play(Create(chart.value(k, YELLOW)), run_time=1)
        self.hush()
        found = text("found: −39.17", 32, GOOD).move_to(chart.ax.c2p(6.5, 45))
        self.narrate(
            "Box seven, box five, box four, and box three: minus thirty-nine point one "
            "seven, right next to the global minimum."
        )
        self.play(FadeIn(found))
        self.hush()
        self.clear_all()

        # How many boxes the master solves, as kappa grows.
        self.narrate(
            "So is a bigger kappa always safer? Count the boxes the master solves before "
            "it stops."
        )
        rows = VGroup()
        for row, (value, verdict, color) in enumerate((
            (0, "stops early: wrong answer", BAD),
            (60, "finds −39.17", GOOD),
            (100, "visits every box", ACCENT),
        )):
            cells = VGroup(*[
                Square(0.5, stroke_width=2, color=GREY_B) for _ in range(toy.M)
            ]).arrange(RIGHT, buff=0.08)
            cells.move_to(0.9 * LEFT + (1.6 - 1.6 * row) * UP)
            numbers = VGroup(*[
                text(str(k + 1), 18, GREY_B).move_to(c) for k, c in enumerate(cells)
            ])
            label = MathTex(rf"\kappa = {value}", font_size=36).next_to(
                cells, LEFT, buff=0.5
            )
            note = text(verdict, 26, color).next_to(cells, RIGHT, buff=0.5)
            group = VGroup(label, cells, numbers, note)
            rows.add(group)
        stories = (
            "With kappa at zero: four boxes, and the wrong answer.",
            "At sixty: eight boxes, and the right one.",
            "At a hundred: all ten.",
        )
        for (value, *_), group, story in zip(
            ((0,), (60,), (100,)), rows, stories, strict=True
        ):
            label, cells, numbers, note = group
            solved = [5]
            while (k := toy.next_box(solved, value)) is not None:
                solved.append(k)
            self.narrate(story)
            self.play(FadeIn(label), Create(cells), FadeIn(numbers), run_time=0.8)
            self.play(
                LaggedStart(
                    *[cells[k].animate.set_fill(YELLOW, 0.8) for k in solved],
                    lag_ratio=0.4,
                ),
                run_time=0.4 * len(solved),
            )
            self.play(FadeIn(note))
            self.hush()
        self.narrate(
            "A large kappa makes every box nobody has visited look promising, so the "
            "master keeps visiting them, until it has visited every single one. That's "
            "not a search any more. It's enumeration."
        )
        self.play(Indicate(rows[2], color=ACCENT))
        self.hush()
        scale = (
            VGroup(
                text("1 variable, 10 boxes: 10 local solves", 30),
                text("5 variables, 100 000 boxes: a budget of about 50", 30, BAD),
            )
            .arrange(DOWN, buff=0.3)
            .to_edge(DOWN, buff=0.5)
        )
        self.narrate(
            "Here, that costs ten local solves. With five variables and ten intervals "
            "each, it would mean a hundred thousand, against a budget of about fifty. "
            "The exploration never gets anywhere near finishing: the run is cut short, "
            "or breaks down, long before."
        )
        self.play(FadeIn(scale[0]))
        self.play(FadeIn(scale[1]))
        self.hush()
        self.narrate(
            "Too small, and the cuts lie. Too large, and they stop saying anything. And "
            "where the useful range lies depends on the problem."
        )
        self.wait(1)
        self.clear_all()


class S09Adaptive(Captioned):
    def construct(self):
        title = text("Adaptive convexification", 38, GOOD).to_edge(UP, buff=0.4)
        self.narrate(
            "Lowering every cut by the same amount is a blunt instrument. The second fix is more surgical: it only corrects a cut when the data prove it wrong."
        )
        self.play(FadeIn(title))
        ax = Axes(
            x_range=[0, 6.5, 1],
            y_range=[-2, 7, 1],
            x_length=8.0,
            y_length=5.4,
            axis_config={"include_tip": False, "color": GREY_B},
            x_axis_config={"include_ticks": False},
            y_axis_config={"include_ticks": False},
        ).shift(2.4 * LEFT + 0.5 * DOWN)
        xl = text("the boxes, in one dimension for the illustration", 22, GREY_A)
        xl.next_to(ax, DOWN, buff=0.1)
        names = ("A", "B", "C")
        xs = np.array([1.0, 3.0, 5.0])
        us = np.array([3.5, 1.2, 0.5])
        slopes = [ValueTracker(1.2), ValueTracker(-0.3), ValueTracker(0.2)]
        delta = 0.5

        def cut_at(i, x):
            return us[i] + slopes[i].get_value() * (x - xs[i])

        def valid(i):
            return all(
                cut_at(i, xs[j]) <= us[j] - delta + 1e-9 for j in range(3) if j != i
            )

        def cut(i):
            # The cut, clipped to the axes.
            s = slopes[i].get_value()
            ends = []
            for x in (0.0, 6.5):
                y = cut_at(i, x)
                if y > 7 or y < -2:
                    y = 7 if y > 7 else -2
                    x = xs[i] + (y - us[i]) / s
                ends.append(ax.c2p(x, y))
            return Line(*ends, color=GOOD if valid(i) else BAD, stroke_width=4)

        dots = VGroup(*[
            Dot(ax.c2p(x, u), radius=0.09) for x, u in zip(xs, us, strict=True)
        ])
        labels = VGroup(*[
            MathTex(f"u({n})", font_size=30).next_to(d, UP + RIGHT, buff=0.05)
            for n, d in zip(names, dots, strict=True)
        ])
        self.play(Create(ax), FadeIn(xl))
        self.narrate(
            "Here's a simpler picture. Three boxes have been solved, A, B and C, each with its value and its slope, so each gives a cut."
        )
        self.play(LaggedStart(*[FadeIn(d, scale=2) for d in dots], lag_ratio=0.3))
        self.play(FadeIn(labels))
        cuts = VGroup(*[always_redraw(lambda i=i: cut(i)) for i in range(3)])
        self.play(LaggedStart(*[Create(c) for c in cuts], lag_ratio=0.4), run_time=2)
        rule = MathTex(
            r"u(\alpha^{(i)}) + s^{(i)\top}(\alpha^{(j)} - \alpha^{(i)})",
            r"\le u(\alpha^{(j)}) - \delta",
            font_size=30,
        ).arrange(DOWN, aligned_edge=LEFT)
        rule.move_to(4.3 * RIGHT + 1.6 * UP)
        rule_text = text("for every pair of\nvisited boxes i, j", 24, GREY_A)
        rule_text.next_to(rule, DOWN, buff=0.3)
        self.narrate(
            "Here's the test. A cut is supposed to be a lower bound. So if the cut from A predicts more than what we actually measured at B, the cut from A is provably wrong. The repair demands that every cut pass at least a small margin, delta, below every value actually observed."
        )
        self.play(Write(rule), FadeIn(rule_text))
        margins = VGroup(*[
            DashedLine(
                ax.c2p(x - 0.35, u - delta), ax.c2p(x + 0.35, u - delta), color=GREY_B
            )
            for x, u in zip(xs, us, strict=True)
        ])
        delta_label = MathTex(r"\delta", font_size=28, color=GREY_B).next_to(
            margins[2], RIGHT, buff=0.1
        )
        self.play(Create(margins), FadeIn(delta_label))

        def overshoot(i):
            # The violations of the cut at i, from the margin up to the cut.
            return VGroup(*[
                Line(
                    ax.c2p(xs[j], us[j] - delta),
                    ax.c2p(xs[j], min(cut_at(i, xs[j]), 7)),
                    color=BAD,
                    stroke_width=6,
                )
                for j in range(3)
                if j != i and cut_at(i, xs[j]) > us[j] - delta
            ])

        for i, target, message in (
            (
                0,
                -1.5,
                (
                    "The cut from A fails twice: it overshoots both B and C. So its slope is pulled back, by a least-squares fit over all its violations, just far enough to clear them."
                ),
            ),
            (
                1,
                -0.75,
                "The cut from B overshoots C. Same treatment.",
            ),
        ):
            gaps = always_redraw(lambda i=i: overshoot(i))
            self.add(gaps)
            self.play(Indicate(dots[i], color=YELLOW))
            self.narrate(message)
            self.wait(2)
            self.play(slopes[i].animate.set_value(target), run_time=2.5)
            self.remove(gaps)
        self.play(Indicate(dots[2], color=GOOD))
        self.say(
            "And the cut from C contradicts nothing, so it's left exactly as it was. That's the point: cuts the data agree with keep their full sharpness.",
            1.5,
        )
        hidden = Circle(radius=0.11, color=YELLOW).move_to(ax.c2p(6, -1.2))
        hidden_label = MathTex("u(D)", font_size=30, color=YELLOW).next_to(
            hidden, DOWN, buff=0.1
        )
        self.narrate(
            "But notice what the test can't see. It only checks cuts against boxes we have visited. A box nobody has visited yet, like D down here, can still sit under a cut and be ruled out. That's exactly our toy run: no observation contradicted the cut that ruled out the left side, so this repair would have changed nothing there."
        )
        self.play(FadeIn(hidden, scale=2), FadeIn(hidden_label))
        self.play(Create(Cross(scale_factor=0.2, stroke_color=BAD).move_to(hidden)))
        self.hush()
        comparison = (
            VGroup(
                text("fixed κ: every cut, by the same amount", 24, BLUE_B),
                text("too small: lies; too large: enumeration", 22, GREY_A),
                text("adaptive δ: only the contradicted cuts", 24, GOOD),
                text("useful lower bound, no guarantee", 22, GREY_A),
            )
            .arrange(DOWN, aligned_edge=LEFT, buff=0.2)
            .move_to(4.3 * RIGHT + 1.6 * DOWN)
        )
        self.narrate(
            "So, the trade-off. A fixed kappa is blunt: too small and the cuts lie, too large and the master enumerates. The adaptive repair lowers only the cuts the data contradict, so the others keep their full sharpness, without a guarantee. In the benchmarks, together with a trust region, it reached the optimum from every starting point."
        )
        self.play(
            LaggedStart(*[FadeIn(c) for c in comparison], lag_ratio=0.5), run_time=3
        )
        self.clear_all()


class S10Sweep(Captioned):
    def construct(self):
        title = text("Swept convexity", 38, ACCENT).to_edge(UP, buff=0.4)
        self.play(FadeIn(title))
        units = VGroup(
            text("κ and δ are in the units of f", 32),
            text("Rastrigin, range ≈ 80:  δ = 100  ✓", 30, GOOD),
            text("Ackley, range ≈ 22:  δ = 100  ✗", 30, BAD),
            text("no single value suits both", 30, GREY_A),
        ).arrange(DOWN, buff=0.4)
        self.play(FadeIn(units[0]))
        self.narrate(
            "Both fixes share an annoying problem: kappa and delta are measured in the units of the objective. Rastrigin's values span about eighty; Ackley's, about twenty-two. A margin of a hundred works on Rastrigin, and is the worst value tested on Ackley. You'd have to tune it for each problem, before knowing anything about it."
        )
        self.play(
            LaggedStart(*[FadeIn(u) for u in units[1:]], lag_ratio=0.8), run_time=4
        )
        self.hush()
        self.play(FadeOut(units))

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
        VGroup(rails, ladder).shift(3 * LEFT + 1.3 * UP)
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
            .move_to(1.8 * RIGHT + 0.1 * UP)
        )
        self.narrate(
            "The third fix avoids choosing. Think of kappa as a skepticism dial. Turned down, the master trusts its cuts and proposes boxes near what already looks good. Turned up, it distrusts them and reaches for boxes far away; turned all the way up, as we saw, it would visit everything. The master already proposes several boxes per iteration, to be solved in parallel. So give each proposal a different setting of the dial: a ladder, from trusting to skeptical. A setting that proposes a box already solved climbs a rung. The top of the ladder comes from the data, ten times the spread of the values seen so far, so the dial never reaches enumeration. And when every rung proposes only boxes already solved, the search stops."
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
            "With no tuning at all, this reached the optimum from every starting point on both Rastrigin and Ackley, which no single fixed value managed.",
            4,
        )
        self.clear_all()


class S11TrustRegion(Captioned):
    def construct(self):
        title = text("Trust region of the master", 40).to_edge(UP, buff=0.4)
        self.narrate(
            "One more safety rail. With a fine grid, the master has an enormous number of options, and only a handful of cuts to judge them by. So each step is restricted to a neighbourhood of the best box so far: a candidate may only change a couple of its interval choices. But how should we count a change?"
        )
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
                self.say(
                    "One natural idea is to weight each interval by its index. From box one-one, that lets the master go anywhere...",
                    2.5,
                )
            else:
                self.say(
                    "...and from box seven-six, nowhere at all. The region depends on where you stand, not on how far you move. Counting the axes that change gives the same cross everywhere.",
                    3,
                )
            self.play(FadeOut(hl), FadeOut(mark), FadeOut(lab))
        self.say(
            "So the rule is: count the axes that change, and allow about two.",
            3,
        )
        self.say(
            "On five-dimensional Rastrigin, a radius of two reaches the optimum from every start; without a trust region, it doesn't.",
            3.5,
        )
        self.clear_all()


class S12Run(Captioned):
    def construct(self):
        land = Landscape(rastrigin, side=5.9, center=3.4 * LEFT + 0.65 * UP)
        grid = land.grid(10)
        self.play(FadeIn(land.image), Create(land.frame), Create(grid))
        title = text("A real run: Rastrigin 2D, 100 boxes", 28).move_to(
            3.4 * RIGHT + 3.2 * UP
        )
        self.narrate(
            "Let's put it all together, and watch the real method on two-dimensional Rastrigin. Orange is the box the master just picked, with the path of the local solver inside it. Blue boxes are solved, and each contributes a cut. The green star is the best point so far."
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
                    "The first box lands in a local valley: eight point nine five.",
                    2,
                )
            if k == 2:
                self.say(
                    "None of the next five boxes does better.",
                    2,
                )
            if k == 6:
                self.say(
                    "Then, on the seventh box: the global minimum, zero, after a hundred and fifty-four evaluations.",
                    3,
                )
            if k == 8:
                self.say(
                    "From here on, the master is checking the remaining candidates before it's willing to stop.",
                    0.5,
                )
        self.play(
            prev[0].animate.set_stroke(width=0).set_fill(SOLVED, 0.45), FadeOut(prev[1])
        )
        self.say(
            "Twenty boxes out of a hundred. Solving all hundred would have cost three to four times as much.",
            3,
        )
        self.clear_all()


class S14aPartial(Captioned):
    def construct(self):
        title = text("3 · Subdividing only the multimodal variables", 38).to_edge(
            UP, buff=0.4
        )
        self.narrate(
            "So the method works when the grid fits the landscape. What if it doesn't? A few situations, and what to do about each. First: only some variables are bumpy."
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
            "Here the function wiggles along x one, and is a smooth bowl along x two. Cutting x two buys nothing: the local solver handles it. So only x one is cut, ten boxes instead of a hundred.",
            3,
        )
        self.say(
            "That pays off only when the bumpiness really is concentrated in a few variables.",
            3,
        )
        self.clear_all()


class S14bDensity(Captioned):
    def construct(self):
        title = text("4 · Estimating the density: counting the basins", 38).to_edge(
            UP, buff=0.4
        )
        self.narrate(
            "Second: how fine should the grid be? Too coarse, and one box holds several valleys. Too fine, and there are more switches than the budget can ever learn about: in five dimensions, ten intervals per axis gave the best results, and sixteen were markedly worse. The sweet spot is one interval per valley, so let's count valleys."
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
                    "Pick a random line through the space, sample along it, and count the dips deep enough to matter. Repeat for many lines, and average.",
                    3,
                )
            elif scan == 1:
                self.say(
                    "One subtlety: sample at random positions along the line. Evenly spaced samples can fall in step with a regular landscape, and miss its dips entirely.",
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
            "And the count can only be too low, never too high: a scan only sees the dips it resolves.",
            3,
        )
        self.say(
            "If the count keeps growing as you sample more finely, one interval per valley is the wrong idea for this problem, which brings us to the third case.",
            3,
        )
        self.clear_all()


class S14cHierarchies(Captioned):
    def construct(self):
        title = text("5 · Hierarchies of subdivisions", 38).to_edge(UP, buff=0.4)
        self.narrate(
            "Third: a single valley so wide that no affordable grid separates anything. That's Ackley. The answer is to zoom."
        )
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
            "Solve a coarse grid, then give the most promising boxes a grid of their own.",
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
            "Or go all the way: split each axis in two, keep the best half, and repeat. Four levels give sixteen intervals per axis, while each level only ever chooses between two per axis.",
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
            "Or keep every open box in a priority queue, so the search can come back to an earlier branch: a spatial branch-and-bound.",
            3,
        )
        self.say(
            "The catch: each zoom starts a fresh master, and the cuts learned at the coarser level are thrown away.",
            3,
        )
        self.say(
            "Still, on Ackley, the deep hierarchy found the optimum from four starts out of six, against two for the best flat grid.",
            3.5,
        )
        self.clear_all()


class S14dMultiResolution(Captioned):
    def construct(self):
        title = text("6 · Multi-resolution encoding", 38).to_edge(UP, buff=0.4)
        self.narrate(
            "Fourth: can we zoom without forgetting? Put every zoom level into one master."
        )
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
            "Write the box index in base m. The first digit picks the coarse region, the second the region inside it. Each digit gets its own row of switches.",
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
        self.narrate(
            "The flat encoding needs n times m to the L binaries; the levels need only n "
            "times m times L. A resolution of a thousand per variable costs one hundred "
            "binaries instead of five thousand."
        )
        self.play(Write(bin_eq))
        self.say(
            "Since one master holds all the digits, it keeps every cut, and can change a coarse and a fine digit in the same step.",
            3,
        )
        self.say(
            "The catch: a cut adds up the effect of each digit separately. In a bumpy landscape, the effect of the fine digit depends on which coarse region you're in, and the cuts can't express that.",
            3.5,
        )
        self.clear_all()


class S15Cantilever(Captioned):
    def construct(self):
        title = text("Application: topology optimization", 40).to_edge(UP, buff=0.4)
        self.narrate("Back to the bracket we started with.")
        self.play(FadeIn(title))
        facts = (
            VGroup(
                text("18 bars, each with a centre, an angle, a length,", 28),
                text("a thickness and a density: 108 variables", 28),
                text(
                    "compliance C minimized, volume fraction ≤ 0.4, adjoint gradients",
                    28,
                ),
                text("the pose of each bar subdivided in 10: 540 binaries", 28, ACCENT),
                text("9 boxes per round, each solved by MMA, in parallel", 28, ACCENT),
            )
            .arrange(DOWN, aligned_edge=LEFT, buff=0.35)
            .next_to(title, DOWN, buff=0.8)
        )
        self.narrate(
            "It's built from eighteen bars. Each bar has a position, an angle, a length, a thickness and a density: a hundred and eight variables, with a gradient that costs about one extra simulation, thanks to an adjoint."
        )
        self.play(FadeIn(facts[:2], shift=0.2 * RIGHT))
        self.play(FadeIn(facts[2], shift=0.2 * RIGHT))
        self.narrate(
            "The method subdivides only where each bar sits and how it's turned, ten intervals each: five hundred and forty switches. Length, thickness and density stay continuous, and inside each box they're optimized by MMA, the workhorse of topology optimization. The master proposes nine boxes per round, solved in parallel."
        )
        self.play(FadeIn(facts[3], shift=0.2 * RIGHT))
        self.play(FadeIn(facts[4], shift=0.2 * RIGHT))
        self.clear_all()

        from PIL import Image
        from PIL import ImageSequence

        gif = Path(__file__).parent / "_static" / "figures" / "cantilever-dark.gif"
        with Image.open(gif) as animation:
            frames = [
                ImageMobject(np.asarray(frame.convert("RGBA")))
                for frame in ImageSequence.Iterator(animation)
            ]
        for frame in frames:
            frame.scale_to_fit_width(13.6).move_to(0.2 * DOWN)
        border = SurroundingRectangle(frames[0], color=GREY_D, buff=0.05)
        self.narrate(
            "Here is the run, round by round. On the left, the boxes of the current "
            "round during their local solutions. On the right, the best feasible design "
            "so far, and its compliance against the designs evaluated, compared with "
            "MMA from the same initial design."
        )
        self.play(FadeIn(frames[0]), Create(border))
        shown = frames[0]
        for k, frame in enumerate(frames[1:], 1):
            if k == 30:
                self.narrate(
                    "MMA from the initial design converges to the symmetric design of "
                    "the paper, at eighty-four. The box subdivision improves on it in its "
                    "first box, and reaches eighty-two point one in its thirty-second box."
                )
            self.remove(shown)
            self.add(frame)
            shown = frame
            self.wait(0.6)
        self.hush()
        self.wait(1)
        self.clear_all()
        rows = VGroup(
            text("MMA from the initial design", 30),
            text("C = 84.0", 30),
            text("multistart of MMA, 63 initial designs", 30),
            text("C = 83.0", 30),
            text("box subdivision, 9 probes, 63 boxes", 30, ACCENT),
            text("C = 82.1", 30, ACCENT),
        ).arrange_in_grid(3, 2, buff=(1.2, 0.6), col_alignments="lr")
        self.narrate(
            "Against MMA at eighty-four, and a multistart of MMA at eighty-three, the box "
            "subdivision reaches eighty-two point one, for a comparable number of "
            "designs, in about half the wall time of the multistart."
        )
        self.play(LaggedStart(*[FadeIn(r) for r in rows], lag_ratio=0.3), run_time=3)
        self.clear_all()


# ---------------------------------------------------------------------------
# 13. The scorecard
# ---------------------------------------------------------------------------


SCORECARD = (
    ("Styblinski-Tang", ("5/5 · 789", "5/5 · 2340", "3/5 · 1401", "5/5 · 2505")),
    ("Rastrigin", ("all*", "0/5", "0/5", "0/5")),
    ("Ackley", ("3/5", "0/5", "5/5 · 2001", "0/5")),
    ("Griewank", ("0/5", "0/5", "0/5", "0/5")),
)
"""The runs reaching the optimum in five dimensions, and the evaluations they took."""


class S13Scorecard(Captioned):
    def construct(self):
        title = text("five variables, 2500 evaluations", 36).to_edge(UP, buff=0.4)
        self.narrate(
            "So how does it stack up against the methods from earlier? Five variables, "
            "a budget of two thousand five hundred evaluations, a gradient counted as one "
            "evaluation, which is what an adjoint gives you, and five starting points per "
            "problem. Each cell says how many runs reached the optimum, and how many "
            "evaluations it took."
        )
        self.play(FadeIn(title))
        header = ["", "box subdivision", "multistart", "CMA-ES", "DIRECT"]
        colors = [WHITE, ACCENT, BLUE_B, GOOD, ACCENT]
        cells = [text(h, 26, c) for h, c in zip(header, colors, strict=True)]
        for name, row in SCORECARD:
            cells.append(text(name, 26))
            for value in row:
                good = not value.startswith("0/")
                cells.append(text(value, 26, GOOD if good else GREY_C))
        table = VGroup(*cells).arrange_in_grid(
            len(SCORECARD) + 1, 5, buff=(0.55, 0.55), col_alignments="lcccc"
        )
        table.next_to(title, DOWN, buff=0.6)
        self.play(FadeIn(table[:5]))
        self.hush()
        rows = [table[5 * (r + 1) : 5 * (r + 2)] for r in range(len(SCORECARD))]
        stories = (
            (
                "Styblinski-Tang, with its well-separated valleys, is home turf: every run "
                "finds the optimum, in seven hundred and eighty-nine evaluations, about three "
                "times fewer than multistart or DIRECT."
            ),
            (
                "On Rastrigin in five dimensions, none of the baselines reaches the optimum. "
                "The box subdivision does, from every start, with ten intervals per axis: "
                "the hundred-thousand-box grid that costs only fifty switches."
            ),
            (
                "Ackley turns the tables. Its one valley is wider than any box, so the grid "
                "doesn't separate anything, and CMA-ES, which follows the overall shape and "
                "ignores the ripples, wins."
            ),
            "And Griewank defeats everyone.",
        )
        for row, story in zip(rows, stories, strict=True):
            self.narrate(story)
            self.play(FadeIn(row, shift=0.2 * RIGHT))
            self.hush()
        note = text(
            "* with ten intervals per axis; the variant of the comparison table: 2/5",
            20,
            GREY_B,
        ).next_to(table, DOWN, buff=0.4)
        self.play(FadeIn(note))
        self.narrate(
            "One more honest data point: with only five hundred evaluations in total, "
            "Bayesian optimization does better on the hardest problems, at about a "
            "hundred times the computing time of the method. Worth it if your function "
            "is expensive, not if it's cheap."
        )
        self.hush()
        lesson = text("it wins when the grid separates the valleys", 34, ACCENT)
        lesson.next_to(note, DOWN, buff=0.4)
        self.narrate(
            "The pattern is clear. The method shines when the grid separates the "
            "valleys, and loses when it doesn't."
        )
        self.play(FadeIn(lesson))
        self.clear_all()


# ---------------------------------------------------------------------------
# 16. Closing
# ---------------------------------------------------------------------------


class S16Closing(Captioned):
    def construct(self):
        ideas = VGroup(
            text("turn “where should I look?” into a discrete choice", 32),
            text("let each local solve vote, through its multipliers", 32),
            text("protect the votes from the non-convexity that makes them lie", 32),
        ).arrange(DOWN, buff=0.5)
        self.narrate(
            "So that's the idea. Turn the question 'where should I look?' into a "
            "discrete choice."
        )
        self.play(FadeIn(ideas[0], shift=0.2 * UP))
        self.narrate(
            "Let each local solve vote, through its multipliers, on where to look next."
        )
        self.play(FadeIn(ideas[1], shift=0.2 * UP))
        self.narrate(
            "And protect those votes from the non-convexity that would make them lie."
        )
        self.play(FadeIn(ideas[2], shift=0.2 * UP))
        self.hush()
        self.narrate(
            "When the grid matches the valleys of your problem, that beats starting at "
            "random. When it doesn't, you now know which tool to reach for instead."
        )
        self.wait(1)
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
        url = text("simoneconiglio.github.io/gemseo-box-subdivision", 28, BLUE_B)
        url.next_to(code, DOWN, buff=0.5)
        self.narrate("The method is available as a GEMSEO plugin. Thanks for watching.")
        self.play(FadeIn(name), FadeIn(code, shift=0.2 * UP))
        self.play(FadeIn(url))
        self.wait(3)
        self.clear_all(1.5)


SCENES = [
    "S01Hook",
    "S02LocalSolver",
    "S03Zoo",
    "S04Baselines",
    "S05Boxes",
    "S06Multipliers",
    "S07Cuts",
    "S08Lies",
    "S09Adaptive",
    "S10Sweep",
    "S11TrustRegion",
    "S12Run",
    "S13Scorecard",
    "S14aPartial",
    "S14bDensity",
    "S14cHierarchies",
    "S14dMultiResolution",
    "S15Cantilever",
    "S16Closing",
]
