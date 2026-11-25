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

r"""Run the classic constrained tunneling method on the SC 2D cantilever.

The method of Levy and Montalvo (1985), with the constraint kept in the
tunneling phase as in Levy and Gómez (1985), alternates two phases, both solved
by MMA with the preset's settings and at most 1800 iterations, the cap of a box
of the box subdivision:

- **minimization**, of :math:`f = \log(C + 1)` under the volume constraint, from
  the initial design of ``GGP_main.m`` and then from each point the tunneling
  phase finds; its best feasible design is the minimizer :math:`x^*` and its
  value the level :math:`f^*`;
- **tunneling**, the minimization under the same constraint and bounds of

  .. math::

     T(x) = \frac{f(x) - f^*}{\|x - x^*\|^{2\lambda^*}
            \prod_j \|x - x_j\|^{2\lambda_0}},

  in the normalized variables, the :math:`x_j` being the minimizers found before
  :math:`x^*` and the mobile poles of the current search, from a point at a
  distance :math:`\varepsilon` of :math:`x^*` in a random direction. The phase
  stops at the first evaluated design that is feasible with :math:`T \le 0`,
  i.e. :math:`f \le f^*`, from which the next minimization starts.

:math:`\lambda^*` starts at one and is raised by a tenth until :math:`T`
decreases away from :math:`x^*` at the starting point, and again whenever a
search ends within :math:`\varepsilon` of :math:`x^*`. A search that ends elsewhere
without reaching the level, at a stationary point of :math:`T` or at the
iteration cap, places a mobile pole there and starts again next to it, up to
:data:`SETTINGS` ``.mobile_poles`` times, after which a new direction is drawn
from :math:`x^*`. See :class:`Settings` for each value and its source.

Four searches from the same minimizer run in parallel, along different random
directions; a search that fails is replaced at once by one along a new
direction, and the first to reach the level stops the others. The budget counts
the distinct designs analysed by all processes, as for the multistart and the
box subdivision, a design being one FE solve for the value and the gradient.

Run in the GGP environment, from the GGP repository, as the other scripts:

    python <this repository>/benchmarks/cantilever/classic_tunneling.py \
        --preset short_cantilever_mna --budget 56000 --processes 4 \
        --out benchmarks/box_subdivision_mna

``--backend <file.py>`` replaces the GGP disciplines by a module defining a
class ``Cantilever`` with an ``x_init``, ``centroids`` and a method
``physics(x)`` returning ``f``, ``df``, ``g``, ``dg``, ``compliance`` and
``rho``, as a NumPy port of ``GGP_main.m`` does. ``--plot <summary.json>
<directory>`` draws the figure of a finished run.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import multiprocessing
import operator
import sys
import time
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

TOLERANCE = 1e-6
"""The volume violation under which a design is feasible, as in the other
scripts."""

MMA_OPTIONS = {
    "max_optimization_step": 0.01,
    "initial_asymptotes_distance": 0.01,
    "max_asymptote_distance": 0.01,
    "min_asymptote_distance": 0.0001,
    "asymptotes_distance_amplification_coefficient": 1.2,
    "asymptotes_distance_reduction_coefficient": 0.4,
    "ftol_rel": 1e-20,
    "ftol_abs": 1e-20,
    "xtol_rel": 1e-20,
    "xtol_abs": 1e-20,
}
"""The MMA settings of the ``short_cantilever_mna`` preset (those of
``mmasub.m``), used when the backend is not the GGP preset itself."""


@dataclass(frozen=True)
class Settings:
    """The settings of the method; none was tuned on this problem."""

    max_iter: int = 1800
    """The MMA iterations of each minimization and of each tunneling search, the
    cap of a box of the box subdivision."""

    initial_strength: float = 1.0
    r"""The initial :math:`\lambda^*`, the order of the zero of :math:`f - f^*`
    at a non-degenerate unconstrained minimizer (Levy and Montalvo, 1985)."""

    strength_increment: float = 0.1
    r"""The increase of :math:`\lambda^*` when the pole does not repel the
    search, as recalled from Levy and Montalvo (1985), not checked against the
    text."""

    max_strength: float = 10.0
    r"""The cap on :math:`\lambda^*`, a safeguard chosen here."""

    pole_strength: float = 1.0
    r"""The strength :math:`\lambda_0` of the poles at the earlier minimizers and
    of the mobile poles, of order one like the initial :math:`\lambda^*`."""

    perturbation: float = 0.1
    r"""The distance :math:`\varepsilon` of a starting point from :math:`x^*` or
    from a mobile pole, in the normalized variables, chosen here: about one MMA
    move limit per variable in 108 dimensions."""

    stationary_step: float = 1e-4
    """The norm of an MMA step under which a tunneling search is taken to be at
    a stationary point of :math:`T`, chosen here, a thousandth of a step at the
    move limit of every variable; MMA's KKT test, absolute, is not used in the
    tunneling phase, :math:`T` varying by orders of magnitude along a search."""

    mobile_poles: int = 2
    """The mobile poles of one search before a new direction is drawn, chosen
    here so that a search costs at most three MMA solutions."""

    processes: int = 4
    """The searches run in parallel from the same minimizer."""

    budget: int = 56000
    """The distinct designs analysed by all processes, that of the box
    subdivision, after which the run stops; there is no other stopping rule."""


SETTINGS = Settings()


class BudgetExhaustedError(Exception):
    """Raised when the budget of the run is spent."""


class AbortedError(Exception):
    """Raised in a search when another one has reached the level."""


class LevelReachedError(Exception):
    """Raised by a search at a feasible design at or below the level."""

    def __init__(self, x: np.ndarray, f: float) -> None:  # noqa: D107
        super().__init__()
        self.x = x
        self.f = f


# --------------------------------------------------------------------------- #
# The problem
# --------------------------------------------------------------------------- #
class GGPBackend:
    """The GGP disciplines of a preset, value and gradients by one linearization."""

    def __init__(self, preset: str) -> None:  # noqa: D107
        sys.path.insert(0, str(Path("benchmarks").resolve()))
        import sc2d_box_subdivision as sc2d
        from gemseo.core.chains.chain import MDOChain

        sc2d.select_preset(preset)
        spec = sc2d.load_spec()
        self.options = dict(spec.solver.options)
        self.options.pop("max_iter", None)
        geometry, physics, x_init, _ = sc2d.build_disciplines(spec)
        self.geometry = geometry
        self.x_init = np.asarray(x_init, float)
        self.centroids = np.asarray(geometry.eval_coords)[:, :2]
        self.chain = MDOChain([geometry, physics])
        self.chain.add_differentiated_inputs(["x_vars"])
        self.chain.add_differentiated_outputs(["compliance", "volume"])

    def physics(self, x: np.ndarray) -> dict:
        """Return the objective, the constraint, their gradients and the density."""
        jacobian = self.chain.linearize({"x_vars": x}, execute=True)
        data = self.chain.io.data

        def dense(block) -> np.ndarray:  # noqa: ANN001
            return np.asarray(
                block.toarray() if hasattr(block, "toarray") else block
            ).ravel()

        f = float(np.ravel(data["compliance"])[0])
        return {
            "f": f,
            "df": dense(jacobian["compliance"]["x_vars"]),
            "g": float(np.ravel(data["volume"])[0]),
            "dg": dense(jacobian["volume"]["x_vars"]),
            "compliance": float(np.expm1(f)),
            "rho": np.asarray(data["rho_V"]).ravel(),
        }


def load_backend(backend: str, preset: str):  # noqa: ANN201
    """Return the problem, the GGP preset or a module defining ``Cantilever``."""
    if backend == "ggp":
        return GGPBackend(preset)

    spec = importlib.util.spec_from_file_location("cantilever_backend", backend)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(Path(backend).resolve().parent))
    spec.loader.exec_module(module)
    problem = module.Cantilever()
    problem.options = dict(MMA_OPTIONS)
    return problem


# --------------------------------------------------------------------------- #
# The evaluations, counted across processes
# --------------------------------------------------------------------------- #
class Evaluator:
    """The counted evaluations of one process, each written to its log.

    A design is evaluated once for its value and its gradient, kept until the
    next design; the count is shared by all processes and stops the run at the
    budget. A row of the log is the time, the objective, the constraint and the
    design, in float64.
    """

    def __init__(self, problem, log: Path, total, stop, budget: int) -> None:  # noqa: ANN001, D107
        self.problem = problem
        self.log = log
        self.total = total
        self.stop = stop
        self.budget = budget
        self.level: float | None = None
        self.start = 0.0
        self.__last: tuple[bytes, dict] | None = None

    def __call__(self, x: np.ndarray) -> dict:
        """Return the outputs at a design, evaluated if new."""
        x = np.clip(np.asarray(x, float), 0.0, 1.0)
        key = x.tobytes()
        if self.__last is not None and self.__last[0] == key:
            return self.__last[1]

        if self.stop is not None and self.stop.is_set():
            raise AbortedError
        with self.total.get_lock():
            if self.total.value >= self.budget:
                raise BudgetExhaustedError
            self.total.value += 1

        outputs = self.problem.physics(x)
        self.__last = (key, outputs)
        row = np.concatenate([
            [time.time() - self.start, outputs["f"], outputs["g"]],
            x,
        ])
        with self.log.open("ab") as file:
            row.astype(np.float64).tofile(file)
        if (
            self.level is not None
            and outputs["g"] <= TOLERANCE
            and outputs["f"] <= self.level
        ):
            if self.stop is not None:
                self.stop.set()
            raise LevelReachedError(x, outputs["f"])
        return outputs


def mma(
    evaluate: Evaluator,
    start: np.ndarray,
    options: dict,
    max_iter: int,
    objective=None,  # noqa: ANN001
) -> list[tuple[np.ndarray, float, float]]:
    """Run MMA under the volume constraint from a point.

    Args:
        evaluate: The counted evaluations.
        start: The starting point.
        options: The MMA settings.
        max_iter: The iteration cap.
        objective: The objective and its gradient as a function of the design
            and of the outputs there, or ``None`` for ``f``.

    Returns:
        The designs evaluated, with ``f`` and the constraint.
    """
    from gemseo.algos.design_space import DesignSpace
    from gemseo.algos.opt.factory import OptimizationLibraryFactory
    from gemseo.algos.optimization_problem import OptimizationProblem
    from gemseo.core.mdo_functions.mdo_function import MDOFunction

    visited = []

    def outputs(x: np.ndarray) -> dict:
        result = evaluate(x)
        if not visited or not np.array_equal(visited[-1][0], x):
            visited.append((np.array(x), result["f"], result["g"]))
        return result

    if objective is None:

        def value(x: np.ndarray) -> float:
            return outputs(x)["f"]

        def gradient(x: np.ndarray) -> np.ndarray:
            return outputs(x)["df"]

    else:

        def value(x: np.ndarray) -> float:
            return objective(x, outputs(x))[0]

        def gradient(x: np.ndarray) -> np.ndarray:
            return objective(x, outputs(x))[1]

    design_space = DesignSpace()
    design_space.add_variable(
        "x", size=start.size, lower_bound=0.0, upper_bound=1.0, value=start
    )
    problem = OptimizationProblem(design_space)
    problem.objective = MDOFunction(value, "f", jac=gradient)
    problem.add_constraint(
        MDOFunction(
            lambda x: np.array([outputs(x)["g"]]),
            "g",
            jac=lambda x: outputs(x)["dg"][None, :],
        ),
        constraint_type="ineq",
    )
    OptimizationLibraryFactory().execute(
        problem, algo_name="MMA", max_iter=max_iter, **options
    )
    return visited


def tunneling_function(
    x: np.ndarray,
    f: float,
    df: np.ndarray,
    level: float,
    poles: list[tuple[np.ndarray, float]],
) -> tuple[float, np.ndarray]:
    r"""Return :math:`T` and its gradient, computed through :math:`\ln D`."""
    log_d = 0.0
    gradient_log_d = np.zeros(x.size)
    for position, strength in poles:
        difference = x - position
        squared = max(float(difference @ difference), 1e-24)
        log_d += strength * np.log(squared)
        gradient_log_d += 2.0 * strength * difference / squared
    scale = np.exp(-log_d)
    excess = f - level
    return excess * scale, (df - excess * gradient_log_d) * scale


# --------------------------------------------------------------------------- #
# A tunneling search, in a worker process
# --------------------------------------------------------------------------- #
WORKER: dict = {}


def _init_worker(backend: str, preset: str, out: Path, total, stop, budget, start):  # noqa: ANN001
    """Build the problem and the counted evaluations of a worker."""
    logging.disable(logging.CRITICAL)
    problem = load_backend(backend, preset)
    name = multiprocessing.current_process().name.replace(":", "_")
    evaluate = Evaluator(problem, out / f"tunneling_{name}.bin", total, stop, budget)
    evaluate.start = start
    WORKER.update(problem=problem, evaluate=evaluate)


def search(task: tuple) -> dict:
    """Run one tunneling search from a minimizer, along one random direction."""
    x_star, level, earlier, seed, settings = task
    settings = Settings(**settings)
    evaluate: Evaluator = WORKER["evaluate"]
    # MMA's KKT test is absolute and T varies by orders of magnitude along a
    # search: a run ends instead when its step falls below a fixed length.
    options = {
        **WORKER["problem"].options,
        "tol": 0.0,
        "xtol_abs": settings.stationary_step,
    }
    evaluate.level = level
    rng = np.random.default_rng(seed)
    epsilon = settings.perturbation
    strength = settings.initial_strength
    mobile: list[np.ndarray] = []
    record = {"seed": seed, "runs": [], "status": "failed"}

    def perturbed(center: np.ndarray) -> np.ndarray:
        direction = rng.standard_normal(center.size)
        step = epsilon * direction / np.linalg.norm(direction)
        point = center + step
        outside = (point < 0.0) | (point > 1.0)
        point[outside] = center[outside] - step[outside]
        return np.clip(point, 0.0, 1.0)

    def poles() -> list[tuple[np.ndarray, float]]:
        return [
            (x_star, strength),
            *((x, settings.pole_strength) for x in earlier),
            *((x, settings.pole_strength) for x in mobile),
        ]

    scale = [1.0]

    def objective(x: np.ndarray, outputs: dict) -> tuple[float, np.ndarray]:
        value, gradient = tunneling_function(
            x, outputs["f"], outputs["df"], level, poles()
        )
        return value * scale[0], gradient * scale[0]

    try:
        start = perturbed(x_star)
        from_minimizer = True
        for _ in range(settings.mobile_poles + 1):
            # The pole at x* must repel the search from a start next to it; the
            # test means nothing below the level, at an infeasible start.
            outputs = evaluate(start)
            scale[0] = 1.0
            while (
                from_minimizer
                and outputs["f"] > level
                and strength < settings.max_strength
            ):
                _, slope = objective(start, outputs)
                if slope @ (start - x_star) < 0.0:
                    break
                strength += settings.strength_increment

            # T is divided by its magnitude at the start, which changes neither
            # its sign nor its stationary points, so that the absolute KKT
            # tolerance of MMA is relative to it.
            value = abs(objective(start, outputs)[0])
            scale[0] = 1.0 / value if value > 0.0 else 1.0
            visited = mma(evaluate, start, options, settings.max_iter, objective)
            x_end = visited[-1][0]
            distance = float(np.linalg.norm(x_end - x_star))
            record["runs"].append({
                "designs": len(visited),
                "strength": strength,
                "distance_to_minimizer": distance,
            })
            if distance < epsilon:
                # Back within the perturbation of x*: the pole is too weak.
                strength = min(
                    strength + settings.strength_increment, settings.max_strength
                )
                start = perturbed(x_star)
                from_minimizer = True
            else:
                # A stationary point of T above the level: a mobile pole.
                mobile.append(x_end)
                start = perturbed(x_end)
                from_minimizer = False
    except LevelReachedError as reached:
        record.update(
            status="reached",
            x=reached.x.tolist(),
            f=reached.f,
            distance_to_minimizer=float(np.linalg.norm(reached.x - x_star)),
        )
    except AbortedError:
        record["status"] = "aborted"
    except BudgetExhaustedError:
        record["status"] = "budget"
    record["strength"] = strength
    record["mobile_poles"] = len(mobile)
    return record


# --------------------------------------------------------------------------- #
# The run
# --------------------------------------------------------------------------- #
def minimize(evaluate: Evaluator, start: np.ndarray, options: dict, max_iter: int):  # noqa: ANN201
    """Run a minimization phase; return its best feasible design and value."""
    evaluate.level = None
    visited = mma(evaluate, start, options, max_iter)
    feasible = [(f, x) for x, f, g in visited if g <= TOLERANCE]
    if feasible:
        f, x = min(feasible, key=operator.itemgetter(0))
        return x, f, True, len(visited)
    return visited[-1][0], visited[-1][1], False, len(visited)


def run(args: argparse.Namespace) -> dict:
    """Run the method to the budget and return its summary."""
    logging.disable(logging.CRITICAL)
    settings = Settings(
        budget=args.budget, processes=args.processes, max_iter=args.max_iter
    )
    args.out.mkdir(parents=True, exist_ok=True)
    for path in args.out.glob("tunneling_*.bin"):
        path.unlink()
    events = args.out / "tunneling_events.jsonl"
    events.write_text("")

    def note(entry: dict) -> None:
        entry["time_s"] = time.time() - start_time
        entry["designs"] = total.value
        with events.open("a") as file:
            file.write(json.dumps(entry) + "\n")
        print(json.dumps({k: v for k, v in entry.items() if k != "x"}), flush=True)

    context = multiprocessing.get_context("fork")
    total = context.Value("q", 0)
    stop = context.Event()
    start_time = time.time()
    problem = load_backend(args.backend, args.preset)
    evaluate = Evaluator(
        problem, args.out / "tunneling_main.bin", total, None, settings.budget
    )
    evaluate.start = start_time
    pool = context.Pool(
        settings.processes,
        _init_worker,
        (
            args.backend,
            args.preset,
            args.out,
            total,
            stop,
            settings.budget,
            start_time,
        ),
    )
    rng = np.random.default_rng(args.seed)
    minima: list[np.ndarray] = []
    x = problem.x_init.copy()
    successes = 0
    searches = 0
    try:
        while True:
            try:
                x_star, f_star, feasible, designs = minimize(
                    evaluate, x, problem.options, settings.max_iter
                )
            except BudgetExhaustedError:
                break
            note({
                "event": "minimum",
                "index": len(minima),
                "f": f_star,
                "compliance": float(np.expm1(f_star)),
                "feasible": feasible,
                "phase_designs": designs,
                "distance_to_previous": (
                    float(np.linalg.norm(x_star - minima[-1])) if minima else None
                ),
                "x": np.asarray(x_star).tolist(),
            })
            earlier = list(minima)
            minima.append(np.asarray(x_star))
            found = None
            stop.clear()
            pending = []
            reached = []
            # Searches along new directions replace those that fail, until one
            # reaches the level and the others abort, or the budget is spent.
            while True:
                while (
                    len(pending) < settings.processes
                    and not stop.is_set()
                    and total.value < settings.budget
                ):
                    seed = int(rng.integers(2**31))
                    task = (x_star, f_star, earlier, seed, asdict(settings))
                    pending.append(pool.apply_async(search, (task,)))
                if not pending:
                    break
                time.sleep(0.2)
                for result in [r for r in pending if r.ready()]:
                    pending.remove(result)
                    record = result.get()
                    searches += 1
                    note({
                        "event": "search",
                        "search": searches,
                        "minimum": len(minima) - 1,
                        **{k: v for k, v in record.items() if k != "x"},
                    })
                    if record["status"] == "reached":
                        reached.append(record)
            if reached:
                found = min(reached, key=operator.itemgetter("f"))
            if found is None:
                break
            successes += 1
            x = np.asarray(found["x"])
            note({
                "event": "tunneled",
                "success": successes,
                "f": found["f"],
                "distance_to_minimizer": found["distance_to_minimizer"],
            })
    finally:
        pool.close()
        pool.join()

    elapsed = time.time() - start_time
    return summarize(args.out, settings, elapsed, problem, successes, searches)


def summarize(out: Path, settings: Settings, elapsed, problem, successes, searches):  # noqa: ANN001, ANN201
    """Merge the logs of all processes by time and summarize the run."""
    width = 3 + problem.x_init.size
    rows = []
    for path in sorted(out.glob("tunneling_*.bin")):
        data = np.fromfile(path, dtype=np.float64)
        rows.append(data[: data.size // width * width].reshape(-1, width))
    rows = np.vstack(rows)
    rows = rows[np.argsort(rows[:, 0], kind="stable")]
    f, g = rows[:, 1], rows[:, 2]
    compliance = np.where(g <= TOLERANCE, np.expm1(f), np.inf)
    best = np.minimum.accumulate(compliance)
    index = int(np.argmin(compliance))
    changes = np.flatnonzero(np.diff(np.concatenate([[np.inf], best])) != 0)
    minima = [
        json.loads(line)
        for line in (out / "tunneling_events.jsonl").read_text().splitlines()
    ]
    found = [entry for entry in minima if entry["event"] == "minimum"]
    x_best = rows[index, 3:]
    outputs = problem.physics(x_best)
    image = np.zeros((30, 60))
    centroids = np.asarray(problem.centroids)
    image[
        np.floor(centroids[:, 1]).astype(int), np.floor(centroids[:, 0]).astype(int)
    ] = outputs["rho"]
    return {
        "settings": asdict(settings),
        "compliance": float(compliance[index]),
        "log_compliance": float(f[index]),
        "designs_to_best": index + 1,
        "designs": len(rows),
        "minima": len(found),
        "minima_compliance": [entry["compliance"] for entry in found],
        "successful_tunnelings": successes,
        "tunneling_searches": searches,
        "time_s": elapsed,
        "best_history": [[int(i) + 1, float(best[i])] for i in changes],
        "x_best": x_best.tolist(),
        "density": image.round(4).tolist(),
    }


# --------------------------------------------------------------------------- #
# The figure
# --------------------------------------------------------------------------- #
PUBLISHED = (
    ("MMA from the initial design", 84.0, 680),
    ("multistart of MMA, 63 starts", 83.0, 9967),
    ("box subdivision, 9 probes", 82.1, 31070),
)
"""The published results of Table 9: best compliance and designs to it."""


def plot(summary_path: Path, directory: Path) -> None:
    """Draw the best layout and the best compliance against the designs."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "docs"))
    import figures
    import matplotlib.pyplot as plt

    summary = json.loads(summary_path.read_text())
    history = np.asarray(summary["best_history"], float)
    designs = np.append(history[:, 0], summary["designs"])
    best = np.append(history[:, 1], history[-1, 1])
    finite = np.isfinite(best)
    for suffix, foreground in (("", figures.LIGHT), ("-dark", figures.DARK)):
        colours = figures.series(foreground)
        with plt.rc_context(figures._style(foreground)):
            figure, (layout, curve) = plt.subplots(
                1, 2, figsize=(10.0, 3.2), width_ratios=(1.0, 1.4)
            )
            layout.imshow(
                np.asarray(summary["density"]),
                origin="lower",
                cmap="Greys" if foreground == figures.LIGHT else "Greys_r",
                vmin=0.0,
                vmax=1.0,
                extent=(0, 60, 0, 30),
            )
            layout.set_xticks([])
            layout.set_yticks([])
            layout.set_title(
                f"tunneling, best design found: C = {summary['compliance']:.1f}",
                fontsize=9,
            )
            curve.step(
                designs[finite],
                best[finite],
                where="post",
                color=figures.ACCENT,
                linewidth=1.8,
                label="classic tunneling",
            )
            for (label, value, at), colour in zip(PUBLISHED, colours, strict=False):
                curve.axhline(value, color=colour, linestyle=":", linewidth=1.0)
                curve.plot(at, value, "o", color=colour, markersize=4, label=label)
            curve.set_xscale("log")
            curve.set_xlim(50, max(summary["designs"], 56000) * 1.05)
            curve.set_ylim(81.5, 90.0)
            curve.set_xlabel("designs analysed, all processes", fontsize=8)
            curve.set_ylabel("best feasible C", fontsize=8)
            curve.tick_params(labelsize=7)
            curve.legend(fontsize=7, loc="upper right")
            curve.grid(alpha=0.25)
            figure.tight_layout()
            figure.savefig(directory / f"cantilever-tunneling{suffix}.svg")
            plt.close(figure)


def main() -> None:
    """Run the method, or draw the figure of a finished run."""
    if "--plot" in sys.argv:
        index = sys.argv.index("--plot")
        plot(Path(sys.argv[index + 1]), Path(sys.argv[index + 2]))
        return

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", default="short_cantilever_mna")
    parser.add_argument("--backend", default="ggp")
    parser.add_argument("--budget", type=int, default=SETTINGS.budget)
    parser.add_argument("--processes", type=int, default=SETTINGS.processes)
    parser.add_argument("--max-iter", type=int, default=SETTINGS.max_iter)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, default=Path("benchmarks/box_subdivision"))
    args = parser.parse_args()
    summary = run(args)
    (args.out / "tunneling_summary.json").write_text(json.dumps(summary))
    print(
        f"best C = {summary['compliance']:.2f} (log {summary['log_compliance']:.4f}),"
        f" {summary['designs_to_best']} designs to the best of {summary['designs']},"
        f" {summary['minima']} minima, {summary['successful_tunnelings']}"
        f" tunnelings, {summary['time_s'] / 3600:.2f} h"
    )


if __name__ == "__main__":
    main()
