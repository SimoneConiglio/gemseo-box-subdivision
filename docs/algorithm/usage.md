<!--
 Copyright 2026 Simone Coniglio

 This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
 International License. To view a copy of this license, visit
 http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
 Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

# Usage in GEMSEO scenarios

Both formulations build an ordinary GEMSEO scenario with the `Benders`
formulation, and are solved by default by the `BiLevelMasterOuterApproximation`
algorithm over SLSQP. Both algorithms are
[settings like the rest](#the-algorithm-of-each-of-the-two-levels).

## The entry point

One call builds the scenario, one executes it:

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

What this owns, so that you cannot get it wrong: chaining the mapping **before**
the objective discipline, building the design space from the **same**
subdivision, naming the one-hot variables the master optimizes over after your
design variables rather than after a literal, selecting the `Benders`
formulation, and sizing the trust region in components changed. None of those is
a decision; every one of them is a way to produce a silently wrong run.

The result is an ordinary GEMSEO scenario. `scenario.subdivision` is the
subdivision it built, and everything else about it works as usual.

## The settings that are yours to choose

Two, and neither has a default that transfers between problems:

```python
from gemseo_box_subdivision import BoxSubdivisionSettings

scenario = BoxSubdivisionScenario(
    [objective_discipline],
    "f",
    design_space,
    n_subdivisions=10,
    settings=BoxSubdivisionSettings(
        convexity_margin=80.0,  # in the units of *your* objective
        trust_region_radius=2,  # in components changed
    ),
)
```

`convexity_margin` is subtracted from an objective difference, so it is absolute
and in the units of the objective. Start from the variation of the objective over
the design space; it crosses a threshold and then saturates, so erring high costs
sub-problems rather than quality.

`n_subdivisions` has to resolve the basins of the landscape and keep the binaries
below the sub-problems a budget can pay for, and refining past the basins makes
things worse rather than merely slower, see
[the benchmark](benchmark.md#the-density-of-the-subdivision-decides).

The other mechanism is selected, never mixed:

```python
BoxSubdivisionSettings(mechanism="convexification", convexification_constant=50.0)
```

Choosing one switches the other's constant off, so a run always measures one
mechanism rather than an average of two.

### Not choosing the convexity at all

Both are absolute quantities in the units of the objective, which is the one
thing about this method that does not transfer between problems. The way out is
to stop supplying a value. The master already probes a **ladder** of
trust-region radii per iteration, one per parallel point; the same probes can
sweep a ladder of convexity values, the low rungs proposing the box next door
and the high rungs the box across the design space, with every probe that
proposes nothing new redeployed a rung higher. What is then asked of you is an
upper bound and a number of points, or nothing at all:

```python
from gemseo_box_subdivision import ConvexitySweepSettings

# An upper bound and a number of points, instead of a calibrated margin.
BoxSubdivisionSettings(convexity_sweep=ConvexitySweepSettings(max_value=100.0))

# Or nothing at all: the bound follows the objective as the run observes it.
BoxSubdivisionSettings(convexity_sweep=ConvexitySweepSettings())
```

On Rastrigin and Ackley, whose objectives differ by a factor of four in scale,
the unbounded sweep reaches the optimum from every starting point on both, which
no single margin does, see
[annex C](tuning.md#sweeping-the-convexity-instead-of-calibrating-it).

The sweep is the **master's**, under its settings `convexity_sweep_points` and
`convexity_sweep_max`, and the two numbers above are turned into those.

:::{warning}
A master predating the sweep does not have those settings, and a scenario given
these settings then falls back to the **top rung** of the ladder, which is the
conservative end and not the margin it was going to replace.
{py:data}`~gemseo_box_subdivision.convexity_sweep.MASTER_SWEEPS_CONVEXITY` says
which master is installed, and the stub of `benchmarks/convexity_sweep.py` drives
the older one from outside, for the measurements.
:::

## The algorithm of each of the two levels

A run is two algorithms: a master deciding which box to look into, and a solver
running inside the box it chose. Both are named by the same settings class, with
whatever else each one takes:

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

The defaults are the pair every result reported here was measured with, the
outer-approximation master over SLSQP, and the two pass-throughs win over the
settings the class translates: a `max_step` in `master_algo_settings` overrides
`trust_region_radius`, and a `max_iter` in `sub_problem_algo_settings` overrides
`sub_problem_max_iter`. A name no GEMSEO library provides, and a setting the
algorithm named does not have, are both refused when the settings are built
rather than in the middle of a run.

What each of the two is free to be is not the same thing:

`sub_problem_algo_name`
: any GEMSEO optimizer. A box is a continuous problem with bounds, which is what
  SLSQP suits; a derivative-free solver such as `NLOPT_COBYLA` is the reasonable
  choice for an objective whose gradient is unavailable or noisy, and nothing
  here measures one. What the method needs of it is a **local optimum of the
  box**: the cut of a box is built at the point it returns, so a solver stopping
  early leaves that cut wrong rather than merely loose, and its iteration budget
  is a setting of the method rather than a detail.

`master_algo_name`
: an algorithm taking the settings of the outer approximation, which means one of
  those of `gemseo-bilevel-outer-approximation`. Changing it changes the method
  rather than its tuning, and an ordinary optimizer is refused outright, taking
  none of those settings. `master_algo_settings` is the useful half of this pair:
  it reaches every setting of the master that
  [the table below](#the-settings-of-the-master-in-their-own-terms) names and
  this class does not.

## Which methodology to set up

Five constructions are available, and they are not alternatives to be tried at
random: each answers a different reason for the flat subdivision to be out of
reach. Read down the first column until one matches the problem.

| If the problem is | then use | because |
|-------------------|----------|---------|
| multimodal in every variable, few enough variables that $n m$ binaries stay affordable | the **flat subdivision**, below | it is the cheapest and the most reliable of the five |
| multimodal in a few variables and smooth in the rest | **subdividing some variables only** | a variable left out keeps all its basins inside every box, which is harmless when it has none |
| needing a resolution whose $n m$ binaries the budget cannot identify | the **multi-resolution encoding** | it reaches $m^L$ subdivisions per component for $n m L$ binaries |
| one broad basin that no affordable density separates | a **hierarchy**, deep and narrow | each level is small enough to be determined by a quarter of the budget |
| solved already, but too slowly | the **settings**, above | the density and the trust-region radius move results further than any of the constructions |

The rule behind the table is the one the methodology derives: what a budget buys
is a few dozen sub-problem solves, and the cut model has one coefficient per
binary, so a subdivision is usable while its binaries stay below the cuts that
can be afforded. Every construction here is a different way of spending fewer
binaries on the same resolution.

## Subdividing some of the variables only

The number of boxes being the Cartesian product of the subdivisions, subdividing
every variable is out of reach as soon as there are a few of them. Pass the
variables to subdivide, and the others stay ordinary variables of the
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

This is worth it when the objective is close to unimodal in the variables left
out: one of them keeps all of its basins inside every box, and the local solve
returns the one it starts in. See
[annex C](tuning.md#refining-some-variables-only-and-when-it-pays),
where it solves a problem that subdividing every variable coarsely does not, and
loses on the problems that are multimodal in every variable.

## A resolution the binaries cannot afford: the multi-resolution encoding

When the density needed would cost more binaries than the budget can identify,
choose a box with **one categorical variable per level** instead of one over the
whole subdivision. The levels are the digits of the box index in base $m$, so
$L$ levels of $m$ subdivisions reach $m^L$ subdivisions per component for
$n m L$ binaries, and the whole thing stays in a single master.

```python
BoxSubdivisionScenario(
    [objective_discipline],
    "f",
    design_space,
    n_subdivisions=4,  # the branching of a level
    levels=2,  # a resolution of 4 ** 2 = 16 per component
)
```

The mapping is chained before the objective discipline exactly as `BoxMapping`
is, and the objective keeps receiving `x` under its own name.

:::{important}
`max_step` must be scaled by the number of levels. The distance counts the
one-hot groups a candidate changes and this encoding has $nL$ of them, so the
radius of two that suits a flat subdivision would let the master move two
**digits** rather than two variables. Leaving it at
{py:attr}`~gemseo_box_subdivision.subdivisions.multi_resolution.MultiResolution.max_step`,
where the region stops constraining, is markedly worse still.
:::

Two limits are worth knowing before choosing it. The cut model is linear in the
one-hot variables, so over the digits it is **additive**: it cannot express that
what a fine digit is worth depends on the coarse digit it sits inside, and
adding levels makes that assumption bind harder. And weighting the levels by
what their digit is worth, rather than alike, is the worst configuration
measured. What it achieves is in
[the results](benchmark.md#the-extensions-and-what-they-are-worth).

## Refining a box, and hierarchies

A box of a subdivision is an ordinary design space, so refining it is running the
method again inside its bounds. The three shapes described in
[the methodology](methodology.md#hierarchies-of-subdivisions) are in the package,
and each is a loop around the method rather than a change to it: you give it a
callable that solves one level and reports the boxes it solved, which leaves you
your own scenario and your own accounting of the budget.

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

`read_solved_boxes` reads back the value and the post-optimal sensitivity of
every box the master solved, which is what the shapes rank on.
`refine_two_levels` and `refine_frontier` take the same callable, and each
returns the bounds of every region it visited.

Which box to refine is the whole question, and the rules are in `RANKINGS`:
`"value"` ranks the boxes whose sub-problem was solved, `"cuts"` ranks **every**
box of the subdivision by the cut model of the master, which is defined at boxes
it never solved, and `"mixed"` alternates the two.

`benchmarks/hierarchy.py` wires this to the benchmark problems, sharing one
budget between the levels so that a hierarchy and a flat run are compared at
equal cost.

:::{warning}
None of the three beats the flat subdivision on a problem a flat subdivision can
resolve, and each node restarts a master and discards its parent's cuts. Reach
for one only in the case they answer, a basin too broad for any affordable
density, where the deep shape reaches an optimum the flat method does not, see
[the results](benchmark.md#the-extensions-and-what-they-are-worth). If what you
need is resolution rather than a change of region, the multi-resolution encoding
above keeps every level in one master and discards nothing.
:::

## Constraints of the original problem

A box may contain no point satisfying the original constraints. Declare such a
constraint with `main_level=True` so an infeasible sub-problem produces a
feasibility cut instead of stalling the master:

```python
scenario.formulation.add_constraint("g", main_level=True)
```

## Enumerating the boxes instead

The same scenario, driven exhaustively, which is the reference to compare
against:

```python
from gemseo.algos.doe.factory import DOELibraryFactory

from gemseo_box_subdivision.design_spaces import create_box_samples

DOELibraryFactory().execute(
    scenario.formulation.optimization_problem,
    algo_name="CustomDOE",
    samples=create_box_samples(subdivision),
)
```

## Applying this to a new problem

The order below is the one the measurements support, and it is deliberately not
the order in which the constructions were built.

1. **Start flat and coarse.** `n_subdivisions=2` or `4`, everything else left at
   its default. This is cheap and tells you whether the landscape is one the
   method suits at all.
2. **Scale the convexity margin to the objective.** `convexity_margin` is
   subtracted from an objective difference, so it is absolute, in the units of
   *your* objective, and a value tuned on another problem means nothing. Take the
   range of the objective over the design space as a first value. It crosses a
   threshold and then saturates, so erring high costs sub-problems rather than
   quality.
3. **Sweep the density before anything else.** It moves results further than any
   other choice, and it has a floor and a ceiling: fine enough to separate the
   basins, coarse enough that the binaries stay below the sub-problem solves the
   budget affords. Refining past the basins actively degrades the ranking, so
   more is not safer.
4. **Then try `trust_region_radius` either side of two.** It is the second most
   decisive setting and it is cheap to test.
5. **Only then reach for a construction**, using the table above to choose
   which; each answers one specific reason for the flat subdivision to fail.

Both mechanism sweeps are in `benchmarks/tune_convexification.py`, which sweeps
each separately, and the budget question is worth settling too: a run whose cost
equals its budget was stopped rather than finished, so raise the budget until the
cost stops moving before comparing anything, see
[the results](benchmark.md#does-more-budget-change-the-answer).

## Composing it by hand

The classes underneath stay public, and
[the implementation](implementation.md) describes them. Use them when you need a
composition :class:`.BoxSubdivisionScenario` does not cover; otherwise prefer the
scenario, which is what the tests and the benchmarks use.

The table below names the settings of the master in **its** terms rather than the
package's, which is what you need when composing by hand.
:class:`.BoxSubdivisionSettings` is the translation:
`convexity_margin` is `min_dfk`, `trust_region_radius` is `max_step`, and
`mechanism` chooses which of `adapt` and `convexification_constant` is active
while switching the other off.

### The settings of the master, in their own terms

:::{warning}
Left to their defaults, the master's two safeguards are both off: the cuts are
then invalid on a multimodal problem, the master converges after two or three
sub-problems and reports success on a point far from the optimum. One of them
**must** be set, see [Convexification](methodology.md#convexification).
:::

The master offers **two different mechanisms** against the non-convexity of the
relaxed problem, and they are not meant to be combined:

`adaptive`
: `adapt=True` with a convexity margin `min_dfk`, the constant left at zero. The
  master repairs its cut slopes against the boxes it has already solved. This is
  the recommended configuration.

`pure_convexification`
: `adapt=False` with `convexification_constant` $\kappa > 0$, the margin left at
  zero. The master adds $\kappa\, C(\alpha)$ to the relaxed problem, which is the
  configuration carrying the convergence guarantee, at the price of a lower bound
  degraded by $\kappa$, see [annex C](tuning.md#the-master-has-two-mechanisms-and-they-must-not-be-combined).

| Setting | Recommended | Why |
|---------|-------------|-----|
| `adapt` | `True` | repairs the cut slopes against the boxes already solved |
| `min_dfk` | the range of the objective over the design space, roughly | the convexity margin the repair enforces; it is an **absolute** quantity in the units of the objective and has to be scaled to the problem |
| `convexification_constant` | $0$ with `adapt=True`; otherwise the order of the variation of the objective | the other mechanism; use it *instead of*, not with, the adaptive repair. Raising it beyond that order buys nothing and decays the result, see [annex C](tuning.md#the-pure-convexification-and-the-range-where-it-is-worth-using) |
| `number_of_parallel_points` | $4$ | the master probes one radius per point, so that a feasible master stays available. A single point still works, from six starting points out of eight against eight; eight points are as reliable as four and nearly twice as expensive |
| `max_step` | $2$ | the radius of the trust region of the master, counted in **components changed**, the design spaces of this package weighing every subdivision alike. Keep it small: widening it to {py:attr}`~gemseo_box_subdivision.subdivisions.box.BoxSubdivision.max_step`, where the region stops constraining, loses Rastrigin at five variables, and removing the region is worse still, see [annex C](tuning.md#how-wide-the-radius-should-be) |
| `ub_tol` | $10^{-4}$ | convergence tolerance on the upper bound |
| `max_iter` | $\ge 80$ | master iterations, not sub-problem iterations |

The first two rows are the ones with no transferable value, and
[the sweep](#not-choosing-the-convexity-at-all) is how a run avoids choosing
either.

And one choice that is not a setting of the algorithm but of the subdivision:

| Choice | Recommended | Why |
|--------|-------------|-----|
| `n_subdivisions` | fine enough to resolve the basins, over the variables the objective is multimodal in | a box that still holds several basins defeats the local solve, and the number of boxes costs evaluations rather than master size, the binaries growing linearly. See [the benchmark](benchmark.md#the-density-of-the-subdivision-decides) |
