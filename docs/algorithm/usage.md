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

Two, and neither has a default that transfers between problems. The class holds
more, and [every one of them is listed below](#every-setting-and-what-it-defaults-to);
these are the two that a new problem actually asks of you:

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
sub-problems rather than quality. That is measured on **unconstrained**
benchmarks; on a problem whose boxes can be infeasible the scale is the spread
over every box solved, and the margin cannot admit a box the feasibility gate
rejects, see
[what the margin reaches](#what-the-margin-reaches-and-what-it-does-not).

`n_subdivisions` has to resolve the basins of the landscape and keep the binaries
below the sub-problems a budget can pay for, and refining past the basins makes
things worse rather than merely slower, see
[the benchmark](benchmark.md#the-density-of-the-subdivision-decides).

It counts subdivisions **per component**, not per variable. A variable of size
$s$ subdivided into $m$ is $s$ independent choices of one subdivision out of $m$:
each component is cut over its own range, the master carries $s$ one-hot groups
of $m$ binaries for it, and the boxes of that variable alone number $m^s$. So one
variable of size five and five variables of size one give the same master, and
`n_subdivisions` is the density of a variable rather than of one of its
components — a size-five variable cannot be given five different densities.

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
upper bound, or nothing at all. It is a **separate entry point** rather than a
setting of the one above, because a run that sweeps has no convexity to calibrate
and does not name its master: the sweep lives in one particular master, and this
drives it.

```python
from gemseo_box_subdivision import SweptBoxSubdivisionSettings

# An upper bound, instead of a calibrated margin.
SweptBoxSubdivisionSettings(max_value=100.0)

# Or nothing at all: the bound is computed from the objective as the run
# observes it, the spread over the boxes already solved with a decade of
# headroom, so the run asks for no number in the units of the objective.
SweptBoxSubdivisionSettings()
```

The rungs are the **parallel points**, `n_parallel_points`, which are the probes
the master already spends on trust-region radii: a probe per rung is the whole
construction, so the two are one number rather than two that can disagree.

On Rastrigin and Ackley, whose objectives differ by a factor of four in scale,
the unbounded sweep reaches the optimum from every starting point on both, which
no single margin does, see
[annex C](tuning.md#sweeping-the-convexity-instead-of-calibrating-it).

The sweep is the **master's**, under its settings `convexity_sweep_points` and
`convexity_sweep_max`, which this entry point fills from the parallel points and
the upper bound.

:::{warning}
A master predating the sweep does not have those settings, so the package
**drives the ladder itself**, around the master's mixed-integer solve, computing
the bound from the objective exactly as the master would. That is what makes the
unbounded form work against any master: the master's own convexity defaults to
zero, and leaving it there would be a run with its cuts unguarded rather than a
run without a sweep.
{py:data}`~gemseo_box_subdivision.convexity_sweep.MASTER_SWEEPS_CONVEXITY` says
which master is installed, and the driving stops the day it says the master
sweeps.

The sweep holds over a run that configures its own master, `scenario.execute`
being given a settings model or keyword arguments: it is what the run needs of
its master rather than one of the settings the caller is overriding. A driven run
switches the adaptive repair on, because the master reads the margin only behind
it, and a master that sweeps on its own is given the two settings carrying the
sweep, whatever else the caller passes; settings with no room for them are
refused where they are given, rather than run unswept. What such a run does
override is the number of parallel points, which is the number of rungs: a master
left with one probe is given the top rung, the conservative end, rather than a
ladder.
:::

## The algorithm of each of the two levels

A run is two algorithms: a master deciding which box to look into, and a solver
running inside the box it chose. The general construction names both, with
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
: any algorithm that can **choose a box**, which means one handling integer
  variables: the master problem is a relaxable mixed-integer non-linear one, and
  an ordinary optimizer would return its relaxation rather than a box, so it is
  refused outright. Changing it changes the method rather than its tuning. The
  settings this class names in the method's terms — the mechanism, the convexity,
  the trust region, the parallel points — belong to the **outer approximation**,
  and they reach only a master declaring them; naming another master while
  setting one of them is refused where it is written. Such a master is driven by
  `master_algo_settings` alone, which reaches every setting it declares, among
  them those
  [the table below](#the-settings-of-the-master-in-their-own-terms) names for the
  outer approximation.

## Every setting, and what it defaults to

There are **two entry points**, and the settings below are split the way they
are. The general construction names its master and its sub-problem solver and
calibrates the convexity; the swept one drives the master that sweeps, with the
parameters of that master chosen rather than supplied. Both are given to the same
scenario, under `settings=`.

Eight settings are common to both:

| setting | default | what it is |
|---------|---------|------------|
| `mechanism` | `"adaptive"` | which guard against the non-convexity of the relaxed problem, `adaptive` or `convexification`, never both. It describes an outer approximation, so it reaches only a master declaring it |
| `trust_region_radius` | $2$ | the radius of the trust region of the master, counted in **components changed** |
| `n_parallel_points` | $4$ | the trust-region radii the master probes per iteration. Under the swept entry point this is also the number of rungs, a probe per rung. The **pure convexification probes a single point** whatever this says, unless a sweep spreads them |
| `max_iter` | $80$ | iterations of the **master**, not of the sub-problems |
| `sub_problem_max_iter` | $40$ | iterations of each sub-problem |
| `tolerance` | $10^{-4}$ | the tolerance on the upper bound of the master |
| `sub_problem_algo_name` | `"SLSQP"` | the algorithm solving each sub-problem inside its box, free under either entry point |
| `sub_problem_algo_settings` | `{}` | anything else that solver takes, passed through; it wins over `sub_problem_max_iter` |

`BoxSubdivisionSettings`, the general construction, adds the master and the
convexity you calibrate:

| setting | default | what it is |
|---------|---------|------------|
| `convexity_margin` | $100.0$ | the margin the adaptive repair enforces, **in the units of the objective** |
| `convexification_constant` | $100.0$ | the constant the pure convexification adds, **in the units of the objective** |
| `master_algo_name` | `"BILEVEL_MASTER_OUTER_APPROXIMATION"` | the algorithm deciding the next box. Any master that handles integer variables; the default is the outer approximation whose settings this class translates |
| `master_algo_settings` | `{}` | anything else the master takes, passed through under **its own** names. For a master that is not an outer approximation, this is the whole of its configuration |
| `options` | `{}` | **deprecated**, use `master_algo_settings`. It still works and warns, and `master_algo_settings` wins when both are given |

`SweptBoxSubdivisionSettings`, the swept construction, adds one number and takes
away four:

| setting | default | what it is |
|---------|---------|------------|
| `max_value` | $0.0$ | the top of the ladder, or zero to have the master read it off the objective as the run observes it, lifted by a decade of headroom |

It names **no master**, since the sweep is implemented in one particular master
and this entry point drives it, and it has no `master_algo_settings` to pass it,
no `convexity_margin` and no `convexification_constant`: a value to calibrate is
the thing a sweep exists not to ask for. See
[the sweep](#not-choosing-the-convexity-at-all).

Two things a reader looks for here and does not find. `n_subdivisions` is an
argument of the scenario rather than a setting of either class, since it defines
the boxes rather than how they are searched. And the settings of the master under
**its own** names, which `master_algo_settings` reaches, are
[a table of their own](#the-settings-of-the-master-in-their-own-terms).

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
[annex D](extensions.md#the-multi-resolution-encoding).

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
[annex D](extensions.md#the-hierarchies). If what you
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

### A constraint must be named after its output

A constraint reaches the master through the post-optimal analysis of the
sub-problem, which needs its Jacobian. The adapter builds that Jacobian by
asking the **discipline producing the output** for it, and it asks under the
*name of the constraint*, so the two have to be the same name. A constraint
named anything else is the output of no discipline.

Three ordinary ways of writing a constraint rename it, and each is refused where
it is written:

| written as | named | why one writes it |
|------------|-------|-------------------|
| `constraint_name="g_upper"` | `g_upper` | a band $|r| \le h$, as two inequalities on one output |
| `positive=True` | `-g` | a constraint of the other sense |
| `value=0.5` | `[g-0.5]` | a bound that is not zero |

Give each side its own **discipline output** instead, and constrain that output
under its own name. A `LinearCombination` per side has an exact constant
Jacobian, and costs one discipline:

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

A `positive=True` constraint becomes a negated one, `<= 0` like the others.

:::{note}
The limitation is upstream, in the pairing of
`MDOScenarioAdapterBenders._compute_jacobian` with
`MDOScenarioAdapter._compute_auxiliary_jacobians`, and it is reached only
through `Benders`. Left alone it surfaces as a `KeyError` the first time the
master linearizes the adapter — several iterations into a run, which a one- or
two-iteration smoke test never reaches, and from a module the caller never
named. What this package does is refuse it at `add_constraint`, with the way
around it in the message.

### What the margin reaches, and what it does not

`main_level=True` does not add the constraint to the master. It adds, once, an
*equality* constraint on `is_feasible`, so a box whose sub-problem has no
feasible point is cut on that rather than admitted.

`convexity_margin` reaches the master as `min_dfk`, and the adaptive repair
subtracts it from **differences of objective value between solved boxes**:

```text
rhs = l_df_k - df_k + min_dfk
```

`df_k` runs over the whole history the repair is given, and that history is the
feasible and the infeasible boxes **together**. An infeasible box still carries
an objective value and a slope, so it still produces an objective cut, and that
cut is repaired with the same margin.

Two consequences, and they pull in opposite directions from what you might
expect:

1. **The scale to calibrate against is the spread of the objective over every
   box solved**, not over the boxes that were admitted. A problem whose
   infeasible boxes report a large penalty has a much wider spread than its
   feasible ones do, and that wider spread is the one the margin is compared
   against.
2. **The margin does not reach the `is_feasible` gate.** The master passes
   `min_dfk` to its inequality-constraint cuts but hard-codes `0.0` for the
   equality ones, and the feasibility cut is an equality. So what decides
   *admissibility* is a mechanism no value of `convexity_margin` relaxes: a run
   that returns nothing feasible is not a run whose margin was mis-scaled, and
   raising the margin will not admit a box.

A run does not look any different from the outside, so read it back:

```python
from gemseo_box_subdivision import read_margin_report

scenario.execute()
report = read_margin_report(scenario.formulation.optimization_problem)
print(report.describe())
# 6 boxes solved, 3 admitted and 3 cut on feasibility; the objective spreads
# over 2.3 across them, which is the scale to calibrate the convexity margin in.
```

`report.spread` is that scale. A run that admitted no box at all sets
`report.found_nothing_feasible`, and says so with a warning of its own accord,
since it is otherwise indistinguishable from a run the margin governed well.

:::{tip}
The clean way out is not to calibrate at all.
[The sweep](#not-choosing-the-convexity-at-all) reads this very scale off the
run — {py:func}`~gemseo_box_subdivision.convexity_sweep.objective_scale`, over
every box solved, infeasible ones included — and sweeps a ladder around it, so
a constrained problem needs no number in the units of an objective whose spread
its penalties decide.
:::

:::{warning}
Do not count feasible points in the database of the **sub-problem**. Under the
normalized formulation the sub-problem solves for the normalized coordinate of
its box, so every box writes to the same keys — the centre of every box is
`0.5` — and a later box overwrites an earlier one. That database reports the
last box solved rather than the run, and reading it can show a run finding
nothing feasible when the master's own record shows it found the optimum. The
master's database carries one entry per box, with its value and its
`is_feasible` flag, and is what {func}`.read_margin_report` reads.

## Coupled problems: the disciplines are chained

The disciplines handed to the scenario are collapsed into a **single chain**,
with the mapping of the boxes in front of them. A chain evaluates each
discipline once, in the order given, so handing it a set of coupled disciplines
gives a feed-forward evaluation rather than a converged one — and no warning.

The sub-problem's formulation is `DisciplinaryOpt`, so the sub-problem cannot
itself be an MDF scenario. A coupled problem is therefore posed by **building
the MDA explicitly** and handing it over among the disciplines:

```python
from gemseo import create_mda

mda = create_mda("MDAGaussSeidel", [first, second], tolerance=1e-10)

scenario = BoxSubdivisionScenario(
    [mda, objective_discipline], "f", design_space, n_subdivisions=4
)
scenario.formulation.add_constraint("g", constraint_type="ineq", main_level=True)
```

An MDA both consumes and produces its couplings, and a chain treats every input
that no earlier discipline produces as an input of the chain, so the couplings
would become inputs of the chain. The scenario stops that: an MDA it is handed
is no longer differentiated with respect to its **own** couplings, which inside
a chain are internal.

That is the right derivative rather than a way round an error. A coupling enters
an MDA as an *initial guess* and leaves it converged, and a converged fixed point
does not depend on where the iteration started, so the derivative is zero.
{func}`.keep_couplings_internal` does it, and can be applied by hand to a
composition built without the scenario.

:::{note}
Without it the failure appears only once there is a **constraint** to
differentiate, since that is when the adapter computes its auxiliary Jacobians:
`ValueError: Variable y2 is both a coupling and a design variable`, from the
Jacobian assembly. The same scenario without a constraint runs, which is what
made it awkward to find. Under `MDF` the question never arises, the formulation
knowing the couplings are internal.
:::

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

## Where a sub-problem starts

Each box is handed to a local solver, so its **starting point** decides which of
the box's minima the cut is built from. The default is the center of the box:
independent of the order the boxes are visited, which warm-starting from the
previous sub-problem is not, and inside the box, which the initial value of the
design space is not.

The center is a point, and a problem may have no value there. Where the
disciplines reject it — a geometry that does not close, a simulation that does
not converge, an operating point outside a table — the solver returns the center
unchanged, and the master builds the cut of that box on a value nothing
computed. The whole run is then a tour of starting points.

`scenario_adapter_cls` hands that policy to the caller, under every
construction:

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

`self.io.data` carries the one-hot variables the master chose, so
{meth}`~.BoxSubdivision.compute_bounds` gives the box being solved and the policy
can search inside it. {func}`.create_box_start_adapter_class` is the default
one, written the same way.

This is what applying the method to the
[EX-link engine](https://simoneconiglio.github.io/Atkinson-cycle-engine-optimisation-/)
needed: 94 % of that design box is a geometry the model cannot analyse, and
reports a flat penalty with a zero gradient, so a box centered there is not a
place a solver can start.

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

   That sentence is measured on the **unconstrained** benchmarks. On a problem
   whose boxes can be infeasible, the range to take is the range over **every
   box solved**, infeasible ones included, which a penalised branch can make far
   wider than the design space suggests — and no value of it will admit a box
   the feasibility gate rejects. See
   [what the margin reaches](#what-the-margin-reaches-and-what-it-does-not), and
   read the run back with {func}`.read_margin_report` rather than assuming.
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
[the results](extensions.md#does-more-budget-change-the-answer).

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

`convexification`
: `adapt=False` with `convexification_constant` $\kappa > 0$, the margin left at
  zero. The master adds $\kappa\, C(\alpha)$ to the relaxed problem, which is the
  configuration carrying the convergence guarantee, at the price of a lower bound
  degraded by $\kappa$, see [annex C](tuning.md#the-master-has-two-mechanisms-and-they-must-not-be-combined).

| Setting | Recommended | Why |
|---------|-------------|-----|
| `adapt` | `True` | repairs the cut slopes against the boxes already solved |
| `min_dfk` | the range of the objective over the design space, roughly, or over **every box solved** where some are infeasible | the convexity margin the repair enforces; it is an **absolute** quantity in the units of the objective and has to be scaled to the problem. It guards the objective cuts, an infeasible box's included, but not the `is_feasible` gate, which is repaired with a margin of zero, see [what the margin reaches](#what-the-margin-reaches-and-what-it-does-not) |
| `convexification_constant` | $0$ with `adapt=True`; otherwise the order of the variation of the objective | the other mechanism; use it *instead of*, not with, the adaptive repair. Raising it beyond that order buys nothing and decays the result, see [annex C](tuning.md#the-pure-convexification-and-the-range-where-it-is-worth-using) |
| `number_of_parallel_points` | $4$ | the master probes one radius per point, so that a feasible master stays available. A single point still works, from six starting points out of eight against eight; eight points are as reliable as four and nearly twice as expensive |
| `max_step` | $2$ | the radius of the trust region of the master, counted in **components changed**, the design spaces of this package weighing every subdivision alike. Keep it small: widening it to {py:attr}`~gemseo_box_subdivision.subdivisions.box.BoxSubdivision.max_step`, where the region stops constraining, loses Rastrigin at five variables, and removing the region is worse still, see [annex C](tuning.md#how-wide-the-radius-should-be) |
| `ub_tol` | $10^{-4}$ | convergence tolerance on the upper bound |
| `max_iter` | $\ge 80$ | master iterations, not sub-problem iterations |

The first two rows are the ones with no transferable value, and
[the sweep](#not-choosing-the-convexity-at-all) is how a run avoids choosing
either. A master that sweeps takes two settings more, `convexity_sweep_points`
and `convexity_sweep_max`, which `SweptBoxSubdivisionSettings` fills from the
parallel points and the upper bound;
{py:data}`~gemseo_box_subdivision.convexity_sweep.MASTER_SWEEPS_CONVEXITY` says
whether the installed master declares them.

And one choice that is not a setting of the algorithm but of the subdivision:

| Choice | Recommended | Why |
|--------|-------------|-----|
| `n_subdivisions` | fine enough to resolve the basins, over the variables the objective is multimodal in | a box that still holds several basins defeats the local solve, and the number of boxes costs evaluations rather than master size, the binaries growing linearly. See [the benchmark](benchmark.md#the-density-of-the-subdivision-decides) |
