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

"""Run the global baselines on the SC 2D cantilever, from the trivial start.

The start is that of ``trivial_start.py``: the pose of every bar from the preset,
the length, the thickness and the density at the middle of their ranges.

    python global_baselines.py direct|cmaes|egobox|multistart [--budget N]

Every FE solve is recorded, and the best *feasible* compliance is reported, as
the box runs do. DIRECT, CMA-ES and EGO take no gradient, so a design is one
solve; the multistart runs MMA, which solves twice per design.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from contextlib import suppress
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path("benchmarks").resolve()))
import contextlib
from typing import TYPE_CHECKING

import sc2d_box_subdivision as sc2d  # noqa: E402
from gemseo.core.chains.chain import MDOChain  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Callable

TRIVIAL = {2: 0.5, 3: 0.5, 5: 0.5}
"""The normalized length, thickness and density of the trivial start."""

PENALTY = 1000.0
"""The weight of the volume violation for the methods that take no constraint."""

OUT = Path("benchmarks/box_subdivision_trivial")


def trivial_start(x_init: np.ndarray) -> np.ndarray:
    """Return the preset's poses with the trivial length, thickness and density."""
    x = x_init.copy()
    for slot, value in TRIVIAL.items():
        x[slot :: sc2d.VPC] = value
    return x


class Problem:
    """The SC 2D compliance and volume, with every solve recorded."""

    def __init__(self, guard: int):
        """
        Args:
            guard: The solves after which an evaluation stops the run.
        """  # noqa: D205, D212
        spec = sc2d.load_spec()
        self.spec = spec
        geometry, physics, x_init, _ = sc2d.build_disciplines(spec)
        self.geometry, self.physics = geometry, physics
        self.x0 = trivial_start(x_init)
        self.history = sc2d._History(geometry, physics)
        self.chain = MDOChain([geometry, physics])
        self.guard = guard
        self.budget = guard
        self.log = None

    def keep_log(self, path: Path) -> None:
        """Append every solve to a file, after reading back what it holds.

        The container these runs live in restarts every few hours, and a run
        of that length resumes from the solves already logged.
        """
        self.log = path
        if path.is_file():
            for line in path.read_text().splitlines():
                entry = json.loads(line)
                self.history.x.append(np.asarray(entry["x"]))
                self.history.compliance.append(entry["c"])
                self.history.volume.append(entry["v"])
                self.history.time.append(entry["t"])

        history = self.history
        recorded = self.physics._run

        def _run(input_data=None):
            out = recorded(input_data)
            with path.open("a") as file:
                file.write(
                    json.dumps({
                        "x": history.x[-1].tolist(),
                        "c": history.compliance[-1],
                        "v": history.volume[-1],
                        "t": history.time[-1],
                    })
                    + "\n"
                )
            return out

        self.physics._run = _run

    def truncate(self, size: int) -> None:
        """Forget the solves past a size, in the history and in its log."""
        history = self.history
        for name in ("x", "compliance", "volume", "time"):
            del getattr(history, name)[size:]
        if self.log is not None and self.log.is_file():
            lines = self.log.read_text().splitlines()[:size]
            self.log.write_text("".join(line + "\n" for line in lines))

    def evaluate(self, x: np.ndarray) -> tuple[float, float]:
        """Return the compliance and the volume constraint, feasible when <= 0."""
        if len(self.history) >= self.guard:
            raise StopIteration
        self.chain.execute({"x_vars": np.clip(np.asarray(x, float), 0.0, 1.0)})
        return self.history.compliance[-1], self.history.volume[-1]

    def penalized(self, x: np.ndarray) -> float:
        """Return the compliance plus the weighted violation of the volume."""
        compliance, volume = self.evaluate(x)
        return compliance + PENALTY * max(0.0, volume)


def run_direct(problem: Problem, seed: int) -> str:  # noqa: ARG001
    """Run DIRECT from the center of the design space, which it always does."""
    from scipy.optimize import direct

    bounds = [(0.0, 1.0)] * problem.x0.size
    # Its own budget is exact, and raising from an objective called from its C
    # extension does not stop it; its work arrays are sized by maxiter.
    problem.guard = 10**7
    # In 108 dimensions a few splits per axis take a box below the default volume
    # tolerance, which stops the run at half its budget: both tolerances are off.
    direct(
        problem.penalized,
        bounds,
        maxfun=problem.budget,
        maxiter=problem.budget,
        vol_tol=0.0,
        len_tol=0.0,
    )
    return f"DIRECT, {problem.budget} evaluations"


def run_cmaes(problem: Problem, seed: int) -> str:
    """Run CMA-ES from the trivial start, a quarter of the range wide."""
    import cma

    with contextlib.suppress(StopIteration):
        cma.fmin(
            problem.penalized,
            problem.x0,
            0.25,
            options={
                "bounds": [0.0, 1.0],
                "maxfevals": problem.budget,
                "seed": seed,
                "verbose": -9,
            },
        )
    return f"CMA-ES, {problem.budget} evaluations"


def initial_design(x0: np.ndarray, seed: int) -> np.ndarray:
    """Return the trivial start and a Latin hypercube, dimension + 1 points."""
    from scipy.stats.qmc import LatinHypercube

    sample = LatinHypercube(d=x0.size, seed=seed).random(x0.size)
    return np.vstack([x0, sample])


def run_egobox(problem: Problem, seed: int) -> str:
    """Run EGO with a KPLS surrogate, the volume as a modeled constraint."""
    max_iters = problem.budget
    import egobox as egx

    def fun(x: np.ndarray) -> np.ndarray:
        return np.array([problem.evaluate(row) for row in x])

    specs = [egx.XSpec(egx.XType.FLOAT, [0.0, 1.0])] * problem.x0.size
    problem.keep_log(OUT / "egobox_evals.jsonl")
    with suppress(StopIteration):
        # Its own checkpoint, one per iteration, resumes a run cut short; a
        # solve after the last checkpoint is solved again, and logged twice.
        egx.Egor(
            specs,
            n_cstr=1,
            gp_config=egx.GpConfig(kpls_dim=3),
            doe=initial_design(problem.x0, seed),
        ).minimize(
            fun,
            max_iters=max_iters,
            seed=seed,
            outdir=str(OUT / "egobox_checkpoint"),
            hot_start=0,
        )
    return f"EGO (KPLS 3), {max_iters} iterations"


def run_multistart(problem: Problem, seed: int, max_iter: int = 1800) -> str:
    """Run MMA from the trivial start, then from random poses, to the budget."""
    from gemseo import create_design_space
    from gemseo import create_scenario

    rng = np.random.default_rng(seed)
    options = dict(problem.spec.solver.options)
    options["algo_name"] = problem.spec.solver.algorithm
    # The solves at the end of each finished start: a run cut short resumes
    # after the last of them, the start it was in being solved again.
    ends_path = OUT / "multistart_ends.json"
    ends = json.loads(ends_path.read_text()) if ends_path.is_file() else []
    problem.keep_log(OUT / "multistart_evals.jsonl")
    problem.truncate(ends[-1] if ends else 0)
    starts = len(ends)
    x = problem.x0
    for _ in range(starts):
        x = trivial_start(rng.uniform(0.0, 1.0, problem.x0.size))
    # A design is two solves under MMA, the gradient re-solving the system.
    while len(problem.history) < 2 * problem.budget:
        remaining = (2 * problem.budget - len(problem.history)) // 2
        design_space = create_design_space()
        design_space.add_variable(
            "x_vars", size=x.size, lower_bound=0.0, upper_bound=1.0, value=x
        )
        scenario = create_scenario(
            [problem.geometry, problem.physics],
            objective_name="compliance",
            design_space=design_space,
            formulation_name="MDF",
        )
        scenario.add_constraint(
            "volume", constraint_type="ineq", positive=False, value=0.0
        )
        scenario.execute(**{**options, "max_iter": min(max_iter, remaining)})
        starts += 1
        ends.append(len(problem.history))
        ends_path.write_text(json.dumps(ends))
        # The next start: random poses, the trivial length, thickness, density.
        x = trivial_start(rng.uniform(0.0, 1.0, problem.x0.size))
    return f"multistart MMA, {starts} starts"


NO_STALL = "--no-stall" in sys.argv
"""Whether to switch GE-SBO's stalling test off, so its budget is what ends it."""
if NO_STALL:
    sys.argv.remove("--no-stall")

GESBO = Path("/home/user/simoneconiglio/ggp_gesbo")
"""A checkout of the GGP branch ``claude/gradient-enhanced-sbo-s6yfyr``,
whose ``scp_uno`` package holds GE-SBO."""


def run_gesbo(problem: Problem, seed: int) -> str:
    """Run GE-SBO from the trivial start, its adjoint gradients as observations.

    Its engine is called directly, the GEMSEO wrapper only adapting a problem to
    it: the value and the gradient of the compliance and of the volume come from
    one linearization of the chain. Its settings are its defaults but for the
    budget, and for the cap on its outer iterations, raised so that the budget
    or its own stalling test ends the run rather than the cap.
    """
    sys.path.insert(0, str(GESBO))
    from scp_uno.gesbo_core import GESBOConfig
    from scp_uno.gesbo_core import gesbo_minimize

    chain = problem.chain
    chain.add_differentiated_inputs(["x_vars"])
    chain.add_differentiated_outputs(["compliance", "volume"])

    def evaluate(x: np.ndarray):  # noqa: ANN202
        jacobian = chain.linearize(
            {"x_vars": np.clip(np.asarray(x, float), 0.0, 1.0)}, execute=True
        )
        data = chain.io.data
        return (
            float(np.ravel(data["compliance"])[0]),
            np.asarray(jacobian["compliance"]["x_vars"]).ravel(),
            np.ravel(data["volume"]).astype(float),
            np.asarray(jacobian["volume"]["x_vars"]).reshape(1, -1),
        )

    size = problem.x0.size
    result = gesbo_minimize(
        evaluate,
        problem.x0,
        np.zeros(size),
        np.ones(size),
        GESBOConfig(
            max_evals=problem.budget,
            max_outer_iter=problem.budget,
            seed=seed,
            **({"stall_limit": problem.budget} if NO_STALL else {}),
        ),
    )
    return (
        f"GE-SBO, {problem.budget} evaluations: {result.status} after "
        f"{result.n_evals} evaluations, {result.n_iter} iterations"
    )


def run_smt(problem: Problem, seed: int, n_doe: int = 20) -> str:
    """Run EGO on SMT's gradient-enhanced surrogate, GEKPLS.

    SMT's own EGO cannot train GEKPLS as a gradient-enhanced model: version
    2.15 hands it every column of the data, the gradients included, as training
    outputs, and requires the output count to match. This loop does what it
    means to: GEKPLS is trained on the value, with the adjoint gradients as its
    derivatives, SMT's defaults otherwise (two PLS components), and the next
    point maximizes the expected improvement from several starts, its gradient
    taken by finite differences on the surrogate in one batch. There is no
    constraint, so the volume enters as the penalty of DIRECT and CMA-ES, its
    gradient added where it is violated. The initial design is the trivial start
    and a Latin hypercube, twenty points in all.
    """
    from scipy.optimize import minimize
    from scipy.stats import norm
    from smt.design_space import DesignSpace
    from smt.surrogate_models import GEKPLS

    chain = problem.chain
    chain.add_differentiated_inputs(["x_vars"])
    chain.add_differentiated_outputs(["compliance", "volume"])

    def evaluate(x: np.ndarray) -> tuple[float, np.ndarray]:
        jacobian = chain.linearize({"x_vars": np.clip(x, 0.0, 1.0)}, execute=True)
        data = chain.io.data
        volume = float(np.ravel(data["volume"])[0])
        value = float(np.ravel(data["compliance"])[0])
        gradient = np.asarray(jacobian["compliance"]["x_vars"]).ravel()
        if volume > 0.0:
            value += PENALTY * volume
            gradient = (
                gradient + PENALTY * np.asarray(jacobian["volume"]["x_vars"]).ravel()
            )
        return value, gradient

    size = problem.x0.size
    rng = np.random.default_rng(seed)
    x_data = list(initial_design(problem.x0, seed)[:n_doe])
    evaluated = [evaluate(x) for x in x_data]
    y_data = [value for value, _ in evaluated]
    g_data = [gradient for _, gradient in evaluated]
    step = 1e-5

    for _ in range(problem.budget):
        model = GEKPLS(
            design_space=DesignSpace(np.array([[0.0, 1.0]] * size)),
            print_global=False,
        )
        x_train = np.array(x_data)
        model.set_training_values(x_train, np.array(y_data)[:, None])
        gradients = np.array(g_data)
        for k in range(size):
            model.set_training_derivatives(x_train, gradients[:, k : k + 1], k)
        model.train()
        best = min(y_data)

        def negative_ei(
            points: np.ndarray, model: GEKPLS = model, best: float = best
        ) -> np.ndarray:
            mean = model.predict_values(points).ravel()
            sigma = np.sqrt(np.maximum(model.predict_variances(points).ravel(), 1e-18))
            z = (best - mean) / sigma
            return -((best - mean) * norm.cdf(z) + sigma * norm.pdf(z))

        def objective(
            x: np.ndarray, negative_ei: Callable = negative_ei
        ) -> tuple[float, np.ndarray]:
            # The point and its 108 neighbours, in one prediction.
            points = np.vstack([x, x + step * np.eye(size)])
            values = negative_ei(points)
            return float(values[0]), (values[1:] - values[0]) / step

        starts = [x_data[int(np.argmin(y_data))], problem.x0]
        starts += list(rng.uniform(0.0, 1.0, (3, size)))
        candidates = [
            minimize(
                objective,
                start,
                jac=True,
                method="L-BFGS-B",
                bounds=[(0.0, 1.0)] * size,
                options={"maxiter": 50},
            )
            for start in starts
        ]
        x_next = min(candidates, key=lambda result: result.fun).x
        value, gradient = evaluate(x_next)
        x_data.append(x_next)
        y_data.append(value)
        g_data.append(gradient)

    return f"EGO on SMT's GEKPLS, {problem.budget} iterations after {n_doe}"


RUNNERS = {
    "smt": run_smt,
    "gesbo": run_gesbo,
    "direct": run_direct,
    "cmaes": run_cmaes,
    "egobox": run_egobox,
    "multistart": run_multistart,
}


def main() -> None:
    """Run the method named on the command line and write its record."""
    parser = argparse.ArgumentParser()
    parser.add_argument("method", choices=RUNNERS)
    parser.add_argument(
        "--budget",
        type=int,
        default=12325,
        help="designs; for EGO, its iterations (600 in the study)",
    )
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    # The derivative-free methods are stopped at the budget in solves, which is
    # a design each; EGO by its iterations and MMA by its designs, so for those
    # two the cap only guards against a runaway.
    guard = args.budget if args.method in ("direct", "cmaes") else 10**7
    problem = Problem(guard)
    problem.budget = args.budget
    start = time.time()
    method = RUNNERS[args.method](problem, args.seed)
    elapsed = time.time() - start

    history = problem.history
    try:
        compliance, x_best, index = history.best()
    except RuntimeError:
        # No feasible design at all is a result, not a failure of the script.
        compliance, index = float("nan"), -1
        x_best = np.asarray(history.x[int(np.argmin(history.volume))])
    result = {
        "method": method,
        "compliance": compliance,
        "evaluations": len(history),
        "unique_designs": history.unique,
        "evaluations_to_best": index + 1,
        "time_s": elapsed,
        "x_best": x_best.tolist(),
        "history": history.compliance,
        "volume_history": history.volume,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    tag = args.method + ("_no_stall" if NO_STALL else "")
    (OUT / f"{tag}_trivial.json").write_text(json.dumps(result))
    print(
        f"{method}: best feasible {compliance:.6f}, {history.unique} designs, "
        f"{len(history)} solves, best at solve {index + 1}, {elapsed:.0f} s"
    )


if __name__ == "__main__":
    main()
