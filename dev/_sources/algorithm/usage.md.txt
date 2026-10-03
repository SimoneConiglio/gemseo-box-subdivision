<!--
 Copyright 2026 Simone Coniglio

 This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
 International License. To view a copy of this license, visit
 http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
 Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

# Usage in GEMSEO scenarios

Both formulations produce an ordinary GEMSEO scenario with the `Benders`
formulation, solved by default by the `BiLevelMasterOuterApproximation` algorithm
with SLSQP for the sub-problems. Both algorithms can be changed through the
settings, see [Algorithms of the two levels](#algorithms-of-the-two-levels).

## Scenario

The scenario is built and executed as follows:

```python
from gemseo.algos.design_space import DesignSpace

from gemseo_box_subdivision import BoxSubdivisionScenario

design_space = DesignSpace()
design_space.add_variable("x", lower_bound=-4.1, upper_bound=5.9, size=2, value=0.0)

scenario = BoxSubdivisionScenario(
    [objective_discipline], "f", design_space, n_subdivisions=10
)
scenario.execute()
```

The scenario performs the assembly steps that would otherwise produce incorrect
runs without warning: it chains the mapping before the objective discipline,
builds the design space from the same subdivision, names the one-hot variables of
the master after the design variables, selects the `Benders` formulation, and
expresses the trust region in number of changed components.

The result is an ordinary GEMSEO scenario; `scenario.subdivision` is the
subdivision it built.

## Main settings

Two settings have no default value that transfers between problems. The other
settings are listed in [Settings and defaults](#settings-and-defaults).

```python
from gemseo_box_subdivision import BoxSubdivisionSettings

scenario = BoxSubdivisionScenario(
    [objective_discipline],
    "f",
    design_space,
    n_subdivisions=10,
    settings=BoxSubdivisionSettings(
        convexity_margin=80.0,  # in the units of the objective
        trust_region_radius=2,  # in components changed
    ),
)
```

`convexity_margin` is subtracted from a difference of objective values, so that
it is an absolute quantity in the units of the objective. A suitable first value
is the variation of the objective over the design space; the results improve up
to a threshold and then saturate, so that an overestimate costs sub-problems
rather than quality. This was observed on unconstrained problems; on a problem
whose boxes can be infeasible, the relevant scale is the spread over all solved
boxes, and the margin cannot make admissible a box rejected by the feasibility
cut, see [Effect of the margin with constraints](#effect-of-the-margin-with-constraints).

`n_subdivisions` must separate the basins of the landscape while keeping the
number of binaries below the number of sub-problems the budget allows; refining
beyond the basins degrades the results, see
[the results](benchmark.md#density-of-the-subdivision).

`n_subdivisions` is a number of subdivisions per component. A variable of size
$s$ subdivided into $m$ intervals corresponds to $s$ independent choices among
$m$ intervals: each component is divided over its own range, the master has $s$
one-hot groups of $m$ binaries for this variable, and the variable alone defines
$m^s$ boxes. A variable of size five and five variables of size one thus give the
same master, and all components of a variable have the same density.

The other convexity mechanism is selected as follows; the two are never
combined:

```python
BoxSubdivisionSettings(mechanism="convexification", convexification_constant=50.0)
```

Selecting one mechanism sets the constant of the other to zero.

### Swept convexity

Both mechanisms require an absolute value in the units of the objective, which
is the only setting of the method that does not transfer between problems. The
alternative is not to supply a value. The master already evaluates a ladder of
trust-region radii at each iteration, one per parallel point; the same probes can
evaluate a ladder of convexity values, the low rungs proposing neighbouring boxes
and the high rungs distant boxes, and a probe that proposes no new box is moved
to the next rung. Only an upper bound, or no value at all, is then required. This
is a separate settings class rather than a setting of the class above, because a
swept run has no convexity value to calibrate and does not designate its master:
the sweep is implemented in a specific master, which this class configures.

```python
from gemseo_box_subdivision import SweptBoxSubdivisionSettings

# An upper bound, instead of a calibrated margin.
SweptBoxSubdivisionSettings(max_value=100.0)

# No value: the bound is computed from the spread of the objective over the
# boxes already solved, multiplied by a headroom factor of ten.
SweptBoxSubdivisionSettings()
```

The rungs are the parallel points, `n_parallel_points`, which the master already
uses for the trust-region radii, so that the number of probes and the number of
rungs are a single setting.

On Rastrigin and Ackley, whose objectives differ in scale by a factor of four, the
unbounded sweep reaches the optimum from all starting points on both problems,
which no single margin does, see
[annex C](tuning.md#swept-convexity).

The sweep is configured in the master by the settings `convexity_sweep_points`
and `convexity_sweep_max`, which this class derives from the parallel points and
the upper bound.

:::{warning}
A master that does not implement the sweep does not have these settings; the
package then applies the ladder itself around the mixed-integer solution of the
master, computing the bound from the objective as the master would. Without this,
the convexity of the master would default to zero and the cuts would not be
protected.
{py:data}`~gemseo_box_subdivision.convexity_sweep.MASTER_SWEEPS_CONVEXITY`
indicates which case applies.

The sweep is kept when `scenario.execute` is given a settings model or keyword
arguments for the master, since it is a requirement of the run rather than a
user setting. A run driven by the package enables the adaptive repair, through
which the master reads the margin, and a master that implements the sweep
receives the two corresponding settings whatever other settings are passed;
settings that cannot hold them are rejected. The number of parallel points, i.e.
of rungs, can be overridden: a master with a single probe receives the highest
rung, the most conservative one.
:::

## Algorithms of the two levels

A run uses two algorithms: a master that selects the box, and a solver for the
sub-problem within the selected box. Both can be specified with their settings:

```python
BoxSubdivisionSettings(
    # The master, and anything else it takes under its own name.
    master_algo_name="BILEVEL_MASTER_OUTER_APPROXIMATION",
    master_algo_settings={"upper_bound_stall": 20},
    # The solver of each sub-problem, and its own settings.
    sub_problem_algo_name="NLOPT_COBYLA",
    sub_problem_algo_settings={"ftol_rel": 1e-8},
)
```

The defaults, the outer-approximation master with SLSQP, were used for all
reported results. The pass-through settings take precedence over the translated
ones: a `max_step` in `master_algo_settings` overrides `trust_region_radius`,
and a `max_iter` in `sub_problem_algo_settings` overrides
`sub_problem_max_iter`. An algorithm name not provided by any GEMSEO library, or
a setting not declared by the algorithm, raises an error when the settings are
built.

`sub_problem_algo_name`
: any GEMSEO optimizer. A box is a continuous problem with bounds, for which
  SLSQP is suitable; a derivative-free solver such as `NLOPT_COBYLA` can be used
  for an objective whose gradient is unavailable or noisy, a case not evaluated
  here. The solver must return a local optimum of the box: the cut of a box is
  built at the returned point, so that a solver stopping early produces an
  incorrect cut, and its iteration budget is therefore a setting of the method.

`master_algo_name`
: any algorithm that handles integer variables: the master problem is a relaxable
  mixed-integer nonlinear problem, and a continuous optimizer would return its
  relaxation rather than a box, so it is rejected. Changing the master changes
  the method. The settings expressed by this class in the terms of the method
  (mechanism, convexity, trust region, parallel points) belong to the outer
  approximation and are passed only to a master that declares them; setting one
  of them with another master raises an error. Such a master is configured by
  `master_algo_settings` only, which accepts all its declared settings, including
  those listed for the outer approximation in
  [Settings of the master](#settings-of-the-master).

## Settings and defaults

There are two settings classes, given to the scenario through `settings=`. The
general class designates the master and the sub-problem solver and requires a
calibrated convexity; the swept class configures the master that implements the
sweep.

Eight settings are common to both classes:

| setting | default | description |
|---------|---------|-------------|
| `mechanism` | `"adaptive"` | safeguard against the non-convexity of the relaxed problem, `adaptive` or `convexification`; passed only to a master that declares it |
| `trust_region_radius` | $2$ | radius of the trust region of the master, in number of changed components |
| `n_parallel_points` | $4$ | number of trust-region radii probed per iteration; with the swept class also the number of rungs. The pure convexification probes a single point unless a sweep is used |
| `max_iter` | $80$ | iterations of the master, not of the sub-problems |
| `sub_problem_max_iter` | $40$ | iterations of each sub-problem |
| `tolerance` | $10^{-4}$ | tolerance on the upper bound of the master |
| `sub_problem_algo_name` | `"SLSQP"` | algorithm solving each sub-problem |
| `sub_problem_algo_settings` | `{}` | other settings of this algorithm; takes precedence over `sub_problem_max_iter` |

*Table 1. Settings common to both classes.*

`BoxSubdivisionSettings` adds the master and the calibrated convexity:

| setting | default | description |
|---------|---------|-------------|
| `convexity_margin` | $100.0$ | margin enforced by the adaptive repair, in the units of the objective |
| `convexification_constant` | $100.0$ | constant of the pure convexification, in the units of the objective |
| `master_algo_name` | `"BILEVEL_MASTER_OUTER_APPROXIMATION"` | algorithm selecting the next box; any master handling integer variables |
| `master_algo_settings` | `{}` | other settings of the master, under its own names; the whole configuration of a master that is not an outer approximation |
| `options` | `{}` | deprecated, replaced by `master_algo_settings`, which takes precedence when both are given |

*Table 2. Settings of `BoxSubdivisionSettings`.*

`SweptBoxSubdivisionSettings` adds one setting:

| setting | default | description |
|---------|---------|-------------|
| `max_value` | $0.0$ | upper bound of the ladder, or zero to derive it from the objective during the run, with a headroom factor of ten |

*Table 3. Setting of `SweptBoxSubdivisionSettings`.*

The swept class designates no master, since the sweep is implemented in a
specific master, and has neither `master_algo_settings`, `convexity_margin` nor
`convexification_constant`, see [Swept convexity](#swept-convexity).

`n_subdivisions` is an argument of the scenario rather than a setting of either
class, since it defines the boxes rather than their search. The settings of the
master under its own names, accessible through `master_algo_settings`, are listed
in [Settings of the master](#settings-of-the-master).

## Choice of the construction

Five constructions are available, each addressing a different reason why the flat
subdivision is not applicable:

| problem | construction | reason |
|---------|--------------|--------|
| multimodal in all variables, with few enough variables for $n m$ binaries to be affordable | flat subdivision | least expensive and most reliable |
| multimodal in a few variables and smooth in the others | subdivision of a subset of the variables | a variable that is not subdivided keeps all its basins within every box, which is harmless if it has a single basin |
| requiring a resolution whose $n m$ binaries the budget cannot identify | multi-resolution encoding | $m^L$ subdivisions per component with $n m L$ binaries |
| a single broad basin that no affordable density separates | deep hierarchy | each level is small enough to be identified with a quarter of the budget |
| already solved, but too slowly | settings | the density and the trust-region radius have a larger effect than any construction |

*Table 4. Choice of the construction.*

The underlying rule follows from the methodology: a budget allows a few dozen
sub-problem solutions, and the cut model has one coefficient per binary, so that
a subdivision is usable as long as its binaries remain below the number of
affordable cuts. Each construction reduces the number of binaries for a given
resolution.

## Subdivision of a subset of the variables

Since the number of boxes is the product of the subdivisions, subdividing all
variables becomes intractable as soon as there are several of them. The variables
to subdivide can be specified, the others remaining continuous variables of the
sub-problem:

```python
# A mapping names the variables to subdivide, and how finely each one.
BoxSubdivisionScenario([discipline], "f", design_space, n_subdivisions={"x_split": 10})

# Several of them, at densities of their own.
BoxSubdivisionScenario(
    [discipline], "f", design_space, n_subdivisions={"x_1": 10, "x_2": 4}
)

# The same density for a named few, when one number is enough.
BoxSubdivisionScenario(
    [discipline], "f", design_space, n_subdivisions=10, variable_names=["x_split"]
)
```

This is beneficial when the objective is close to unimodal in the variables that
are not subdivided, whose basins all remain within every box. In
[annex C](tuning.md#subdivision-of-a-subset-of-the-variables) it solves a
problem that a coarse subdivision of all variables does not, and degrades the
results on problems that are multimodal in all variables.

## Multi-resolution encoding

When the required density would need more binaries than the budget can identify,
a box can be selected with one categorical variable per level instead of a single
categorical variable over the whole subdivision. The levels are the digits of the
box index in base $m$, so that $L$ levels of $m$ subdivisions give $m^L$
subdivisions per component with $n m L$ binaries, within a single master.

```python
BoxSubdivisionScenario(
    [objective_discipline],
    "f",
    design_space,
    n_subdivisions=4,  # the branching of a level
    levels=2,  # a resolution of 4 ** 2 = 16 per component
)
```

The mapping is chained before the objective discipline as `BoxMapping` is, and
the objective receives `x` under its own name.

:::{important}
`max_step` must be multiplied by the number of levels. The distance counts the
one-hot groups changed by a candidate, and this encoding has $nL$ groups, so that
a radius of two, suitable for a flat subdivision, would allow the master to change
two digits rather than two variables. Setting it to
{py:attr}`~gemseo_box_subdivision.subdivisions.multi_resolution.MultiResolution.max_step`,
the radius beyond which the trust region no longer constrains the master, gives
even worse results.
:::

Two limitations apply. The cut model is linear in the one-hot variables and
therefore additive over the digits: it cannot represent the dependence of the
effect of a fine digit on the coarse digit, and this restriction becomes stronger
as levels are added. Moreover, weighting the levels by the value of their digits
instead of equally gave the worst results measured. The results are given in
[annex D](extensions.md#multi-resolution-encoding).

## Refinement of a box and hierarchies

A box of a subdivision is an ordinary design space, so that refining it amounts to
applying the method again within its bounds. The three shapes described in
[the methodology](methodology.md#hierarchies-of-subdivisions) are implemented as
loops around the method: they take a callable that solves one level and returns
the boxes it solved, which leaves the scenario and the budget accounting to the
caller.

```python
from gemseo.algos.design_space import DesignSpace

from gemseo_box_subdivision import (
    BoxSubdivisionScenario,
    read_solved_boxes,
    refine_deep,
)


def solve(lower_bound, upper_bound, n_subdivisions):
    """Run the method once over these bounds."""
    if budget_is_spent():
        # No solved box ends the search, which is how a budget ends it.
        return None, []

    space = DesignSpace()
    space.add_variable(
        "x", lower_bound=lower_bound, upper_bound=upper_bound, size=lower_bound.size
    )
    scenario = BoxSubdivisionScenario(
        [objective_discipline], "f", space, n_subdivisions=n_subdivisions
    )
    scenario.execute()
    return scenario.subdivision, read_solved_boxes(
        scenario.formulation.optimization_problem
    )


visited = refine_deep(solve, lower_bound, upper_bound, branching=2, depth=4)
```

`read_solved_boxes` reads the value and the post-optimal sensitivity of every box
solved by the master, on which the shapes base their ranking.
`refine_two_levels` and `refine_frontier` take the same callable, and each returns
the bounds of all visited regions.

The ranking rules are collected in `RANKINGS`: `"value"` ranks the boxes whose
sub-problem was solved, `"cuts"` ranks all boxes of the subdivision with the cut
model of the master, which is defined at unsolved boxes, and `"mixed"` alternates
the two.

`benchmarks/hierarchy.py` applies the hierarchies to the test problems, with a
budget shared between the levels so that hierarchies and flat runs are compared
at equal cost.

:::{warning}
None of the three shapes performs better than the flat subdivision on a problem
that a flat subdivision can resolve, and each node restarts a master and discards
the cuts of its parent. They are suited only to a basin too broad for any
affordable density, for which the deep shape reaches an optimum that the flat
method does not, see [annex D](extensions.md#hierarchies). When a higher
resolution rather than a change of region is needed, the multi-resolution
encoding keeps all levels in one master and discards no cut.
:::

## Constraints of the original problem

A box may contain no point satisfying the constraints of the original problem.
Such a constraint is declared with `main_level=True`, so that an infeasible
sub-problem produces a feasibility cut instead of stalling the master:

```python
scenario.formulation.add_constraint("g", main_level=True)
```

### Naming of the constraints

A constraint is passed to the master through the post-optimal analysis of the
sub-problem, which requires its Jacobian. The adapter obtains this Jacobian from
the discipline producing the output, under the name of the constraint, so that
both names must be identical.

Three usual ways of declaring a constraint change its name, and each is rejected
when declared:

| declaration | name | usual purpose |
|-------------|------|---------------|
| `constraint_name="g_upper"` | `g_upper` | a band $\vert r \vert \le h$, two inequalities on one output |
| `positive=True` | `-g` | a constraint of the opposite sense |
| `value=0.5` | `[g-0.5]` | a non-zero bound |

*Table 5. Declarations that rename a constraint.*

Each side must instead be a discipline output, constrained under its own name. A
`LinearCombination` per side has an exact constant Jacobian:

```python
from gemseo.disciplines.linear_combination import LinearCombination

scenario = BoxSubdivisionScenario(
    [
        discipline,
        LinearCombination(["r"], "r_upper", input_coefficients={"r": 1.0}, offset=-h),
        LinearCombination(["r"], "r_lower", input_coefficients={"r": -1.0}, offset=-h),
    ],
    "f",
    design_space,
    n_subdivisions=10,
)
for name in ("r_upper", "r_lower"):
    scenario.formulation.add_constraint(name, main_level=True)
```

A constraint with `positive=True` is written as a negated constraint, `<= 0` like
the others.

:::{note}
The limitation lies upstream, in the combination of
`MDOScenarioAdapterBenders._compute_jacobian` with
`MDOScenarioAdapter._compute_auxiliary_jacobians`, and occurs only with
`Benders`. Otherwise it appears as a `KeyError` when the master first linearizes
the adapter, several iterations into a run, from a module not called by the user.
The package rejects such constraints in `add_constraint`, with the workaround in
the error message.
:::

### Effect of the margin with constraints

`main_level=True` does not add the constraint to the master. It adds a single
equality constraint on `is_feasible`, so that a box whose sub-problem has no
feasible point is cut rather than admitted.

`convexity_margin` is passed to the master as `min_dfk`, which the adaptive repair
subtracts from differences of objective values between solved boxes:

```text
rhs = l_df_k - df_k + min_dfk
```

`df_k` covers the whole history given to the repair, which includes both feasible
and infeasible boxes. An infeasible box still has an objective value and a slope,
and therefore produces an objective cut, repaired with the same margin.

This has two consequences:

1. The scale for the margin is the spread of the objective over all solved boxes,
   not only the admitted ones. A problem whose infeasible boxes report a large
   penalty has a much larger spread than its feasible boxes.
2. The margin does not apply to the `is_feasible` cut. The master passes `min_dfk`
   to the inequality-constraint cuts but uses `0.0` for the equality ones, and the
   feasibility cut is an equality. The admissibility of a box is therefore not
   affected by `convexity_margin`: a run that finds no feasible box does not
   indicate a badly scaled margin, and increasing the margin does not admit a
   box.

The run can be inspected as follows:

```python
from gemseo_box_subdivision import read_margin_report

scenario.execute()
report = read_margin_report(scenario.formulation.optimization_problem)
print(report.describe())
# 6 boxes solved, 3 admitted and 3 cut on feasibility; the objective spreads
# over 2.3 across them, which is the scale to calibrate the convexity margin in.
```

`report.spread` is this scale. A run that admitted no box sets
`report.found_nothing_feasible` and issues a warning.

:::{tip}
The sweep avoids the calibration: [Swept convexity](#swept-convexity) computes
this scale during the run with
{py:func}`~gemseo_box_subdivision.convexity_sweep.objective_scale`, over all
solved boxes including the infeasible ones, and builds the ladder from it.
:::

:::{warning}
The feasible points must not be counted in the database of the sub-problem. With
the normalized formulation the sub-problem is solved for the normalized
coordinates of its box, so that all boxes write to the same keys (the centre of
every box is `0.5`) and a later box overwrites an earlier one. This database
therefore reflects the last box solved, and may show no feasible point while the
master has found the optimum. The database of the master has one entry per box,
with its value and its `is_feasible` flag, and is the one read by
{func}`.read_margin_report`.
:::

## Coupled problems

The disciplines given to the scenario are combined into a single chain preceded
by the mapping of the boxes. A chain evaluates each discipline once in the given
order, so that coupled disciplines are evaluated in a feed-forward manner instead
of being converged, without warning.

The formulation of the sub-problem is `DisciplinaryOpt`, so that the sub-problem
cannot be an MDF scenario. A coupled problem is therefore posed by building the
MDA explicitly and passing it with the disciplines:

```python
from gemseo import create_mda

mda = create_mda("MDAGaussSeidel", [first, second], tolerance=1e-10)

scenario = BoxSubdivisionScenario(
    [mda, objective_discipline], "f", design_space, n_subdivisions=4
)
scenario.formulation.add_constraint("g", constraint_type="ineq", main_level=True)
```

An MDA both consumes and produces its couplings, and a chain treats every input
not produced by a previous discipline as an input of the chain, so that the
couplings would become inputs of the chain. The scenario prevents this: an MDA it
receives is no longer differentiated with respect to its own couplings, which are
internal to the chain.

This derivative is correct: a coupling enters an MDA as an initial guess and
leaves it converged, and a converged fixed point does not depend on the initial
guess, so that the derivative is zero. {func}`.keep_couplings_internal` performs
this operation and can be applied to a composition built without the scenario.

:::{note}
Without it the error appears only when a constraint has to be differentiated,
since the adapter then computes its auxiliary Jacobians:
`ValueError: Variable y2 is both a coupling and a design variable`, raised during
the assembly of the Jacobian. The same scenario without a constraint runs. With
`MDF` the question does not arise, the formulation treating the couplings as
internal.
:::

## Enumeration of the boxes

The same scenario can be driven exhaustively, which gives the reference for the
comparison:

```python
from gemseo.algos.doe.factory import DOELibraryFactory

from gemseo_box_subdivision.design_spaces import create_box_samples

DOELibraryFactory().execute(
    scenario.formulation.optimization_problem,
    algo_name="CustomDOE",
    samples=create_box_samples(subdivision),
)
```

## Starting point of the sub-problems

Each box is solved by a local solver, whose starting point determines the minimum
of the box from which the cut is built. The default starting point is the centre
of the box, which is independent of the order in which the boxes are visited,
unlike a warm start from the previous sub-problem, and lies within the box, unlike
the initial value of the design space.

The model may not be defined at the centre of a box, for instance when a geometry
is not closed, a simulation does not converge, or an operating point lies outside
a table. The solver then returns the centre unchanged, and the master builds the
cut of the box on an undefined value.

`scenario_adapter_cls` allows the caller to define the starting point:

```python
from gemseo_bilevel_outer_approximation.disciplines.scenario_adapters.mdo_scenario_adapter_benders import (
    MDOScenarioAdapterBenders,
)


class RestoringAdapter(MDOScenarioAdapterBenders):
    def _pre_run(self) -> None:
        super()._pre_run()
        problem = self.scenario.formulation.optimization_problem
        problem.design_space.set_current_value(a_startable_point_in(self.io.data))


BoxSubdivisionScenario(
    [discipline], "f", space, n_subdivisions=4, scenario_adapter_cls=RestoringAdapter
)
```

`self.io.data` contains the one-hot variables selected by the master, so that
{meth}`~.BoxSubdivision.compute_bounds` gives the box being solved and the adapter
can search for a valid point within it. {func}`.create_box_start_adapter_class` is
the default adapter, written in the same way.

This was required to apply the method to the
[EX-link engine](https://simoneconiglio.github.io/Atkinson-cycle-engine-optimisation-/),
where 94% of the design space corresponds to geometries the model cannot analyse
and which return a constant penalty with a zero gradient.

## Application to a new problem

The following procedure is supported by the experiments:

1. Start with a coarse flat subdivision, `n_subdivisions=2` or `4`, with all other
   settings at their defaults, to determine at low cost whether the landscape is
   suited to the method.
2. Scale the convexity margin to the objective. `convexity_margin` is an absolute
   quantity in the units of the objective, so that a value tuned on another
   problem is not meaningful. The range of the objective over the design space is
   a suitable first value; the results improve up to a threshold and then
   saturate, so that an overestimate costs sub-problems rather than quality.

   This was observed on unconstrained problems. When boxes can be infeasible, the
   relevant range is that over all solved boxes, including the infeasible ones,
   which penalties can make much larger than the variation over the design space;
   no value admits a box rejected by the feasibility cut. See
   [Effect of the margin with constraints](#effect-of-the-margin-with-constraints)
   and inspect the run with {func}`.read_margin_report`.
3. Study the density first. It has the largest effect of all settings and is
   bounded below by the separation of the basins and above by the number of
   sub-problems the budget allows. Refining beyond the basins degrades the
   ranking of the boxes.
4. Then test `trust_region_radius` around two, the second most influential
   setting, which is inexpensive to test.
5. Only then consider a construction, using Table 4.

Both convexity mechanisms are swept separately in
`benchmarks/tune_convexification.py`. The budget should also be checked: a run
whose cost equals its budget was stopped, so that the budget should be increased
until the cost no longer changes before comparing configurations, see
[annex D](extensions.md#effect-of-the-budget).

## Manual composition

The underlying classes are public and are described in
[the implementation](implementation.md). They can be used for compositions not
covered by :class:`.BoxSubdivisionScenario`; otherwise the scenario, used by the
tests and the benchmarks, is preferable.

The table below gives the settings of the master under their own names, which are
needed for a manual composition. :class:`.BoxSubdivisionSettings` performs the
translation: `convexity_margin` corresponds to `min_dfk`, `trust_region_radius` to
`max_step`, and `mechanism` selects which of `adapt` and
`convexification_constant` is active and disables the other.

### Settings of the master

:::{warning}
With their default values, both safeguards of the master are disabled: the cuts
are then invalid for a multimodal problem, and the master converges after two or
three sub-problems and reports success at a point far from the optimum. One of
them must be set, see [Convexification](methodology.md#convexification).
:::

The master provides two mechanisms against the non-convexity of the relaxed
problem, which are not intended to be combined:

`adaptive`
: `adapt=True` with a convexity margin `min_dfk`, the constant being zero. The
  master corrects the slopes of its cuts using the boxes already solved. This is
  the recommended configuration.

`convexification`
: `adapt=False` with `convexification_constant` $\kappa > 0$, the margin being
  zero. The master adds $\kappa\, C(\alpha)$ to the relaxed problem, which provides
  the convergence guarantee at the cost of a lower bound degraded by $\kappa$, see
  [annex C](tuning.md#the-two-convexity-mechanisms).

| setting | recommended value | justification |
|---------|-------------------|---------------|
| `adapt` | `True` | corrects the cut slopes using the boxes already solved |
| `min_dfk` | approximately the range of the objective over the design space, or over all solved boxes when some are infeasible | convexity margin enforced by the repair, an absolute quantity in the units of the objective. It applies to the objective cuts, including those of infeasible boxes, but not to the `is_feasible` cut, which is repaired with a zero margin, see [Effect of the margin with constraints](#effect-of-the-margin-with-constraints) |
| `convexification_constant` | $0$ with `adapt=True`; otherwise of the order of the variation of the objective | the other mechanism, used instead of the adaptive repair. Larger values do not improve and eventually degrade the results, see [annex C](tuning.md#pure-convexification) |
| `number_of_parallel_points` | $4$ | one radius per point, so that a feasible master remains available. A single point reaches the optimum from six starting points of eight against eight; eight points are as reliable as four and nearly twice as expensive |
| `max_step` | $2$ | radius of the trust region in number of changed components, all intervals having unit weight. A radius equal to {py:attr}`~gemseo_box_subdivision.subdivisions.box.BoxSubdivision.max_step`, beyond which the region no longer constrains the master, fails on Rastrigin in five variables, and no trust region gives worse results, see [annex C](tuning.md#radius-of-the-trust-region) |
| `ub_tol` | $10^{-4}$ | convergence tolerance on the upper bound |
| `max_iter` | $\ge 80$ | master iterations, not sub-problem iterations |

*Table 6. Settings of the master.*

The first two settings have no transferable value, and
[the sweep](#swept-convexity) avoids choosing them. A master that implements the
sweep has two additional settings, `convexity_sweep_points` and
`convexity_sweep_max`, which `SweptBoxSubdivisionSettings` derives from the
parallel points and the upper bound;
{py:data}`~gemseo_box_subdivision.convexity_sweep.MASTER_SWEEPS_CONVEXITY`
indicates whether the installed master declares them.

One further choice concerns the subdivision rather than the algorithm:

| choice | recommended value | justification |
|--------|-------------------|---------------|
| `n_subdivisions` | fine enough to separate the basins, over the variables in which the objective is multimodal | a box containing several basins defeats the local solution; the number of boxes costs evaluations rather than master size, since the binaries grow linearly. See [the results](benchmark.md#density-of-the-subdivision) |

*Table 7. Choice of the subdivision.*
