<!--
 Copyright 2026 Simone Coniglio

 This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
 International License. To view a copy of this license, visit
 http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
 Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

# Implementation

The package contributes building blocks to GEMSEO rather than a monolithic
algorithm: the subdivision, the two ways of confining a sub-problem to a box, the
design spaces of both levels, and a scenario adapter. Assembling them is not left
to the caller, because the assembly is a set of invariants rather than a set of
choices.

## The layers

```text
BoxSubdivisionScenario        a GEMSEO scenario; owns the assembly
   └── BoxSubdivisionSettings the settings, in the units the method measures
          └── subdivisions/   how a design space is cut into boxes
              design_spaces   the design spaces a subdivision builds
              disciplines/    the mapping, the constraint, the adapter
              hierarchy       refining a box rather than subdividing finely
```

{py:class}`~gemseo_box_subdivision.scenario.BoxSubdivisionScenario` derives from
`MDOScenario` and builds the composition in its constructor: it chains the
mapping in front of the objective, builds the design space from the **same**
subdivision, derives the names the master optimizes over from the design space
rather than from a literal, selects the `Benders` formulation, and for the
constraint formulation wires the scenario adapter and declares the box
constraint. Its `execute` supplies the settings of the master, so a run needs no
configuration of the master at all.

The settings name the master's in the terms of the methodology, a
`trust_region_radius` in components changed rather than a `max_step` in
unexplained units, and `to_master_settings` is the only place that translates
them. Four invariants live in that one place:

- **the two mechanisms are kept apart**: choosing one zeroes the other's
  constant, so a run can never measure an average of the two;
- **those terms describe an outer-approximation master**, so they are translated
  only for a master declaring them; setting one for a master that has none of
  them is refused rather than sent, such a master being driven by
  `master_algo_settings` alone;
- **the master is executed by its name** with those settings, not through a
  settings model: a GEMSEO settings model names the algorithm it selects, and the
  settings of `OUTER_APPROXIMATION` name one no library provides, so a model
  would run something other than the algorithm asked for. The sub-problem is the
  other way round, the `Benders` formulation taking the model that
  `create_sub_problem_settings_model` builds;
- **both names are checked against what the algorithm declares**, when the
  settings are built rather than in the middle of a run.

{py:class}`~gemseo_box_subdivision.settings.BoxSubdivisionSettings` and
{py:class}`~gemseo_box_subdivision.settings.SweptBoxSubdivisionSettings` are the
two constructions, sharing
{py:class}`~gemseo_box_subdivision.settings.BaseBoxSubdivisionSettings` for what
belongs to the run rather than to either level. The swept one names no master —
the sweep is implemented in one — and carries no convexity value; its ladder has
one rung per parallel point of the master, which is what pairs a probe with a
rung. The scenario takes either.

Where the installed master predates the sweep,
{py:data}`~gemseo_box_subdivision.convexity_sweep.MASTER_SWEEPS_CONVEXITY` is
`False` and `drive_the_master` wraps the run in a driver that applies the ladder
around the master's mixed-integer solve, deploying a probe one rung higher while
it proposes a box already solved. That driver is temporary — it goes when the
master ships the sweep — and it exists because the alternative is not a run
without a sweep but a run whose cuts are unguarded, the master's own convexity
defaulting to zero.

Everything below those two is public and usable on its own, which is what
[Usage](usage.md) calls composing by hand.

## The subdivision

{py:class}`~gemseo_box_subdivision.subdivisions.box.BoxSubdivision`
describes the Cartesian subdivision: per variable, the lower and upper bounds of
each subdivision of each component, shaped `(size, n_subdivisions)`.

```python
subdivision = BoxSubdivision.from_design_space(design_space, {"x": 10, "y": 4})
subdivision.n_boxes      # exponential in the number of components
subdivision.n_binaries   # linear in it: this is what sizes the master
```

It also carries the helpers the rest of the package shares: `compute_bounds` for
the box selected by a one-hot vector, `locate` for the subdivision containing a
value, and the naming conventions `get_one_hot_names` and `get_normalized_names`
so that every component agrees on the variable names.

## One-hot layout

For a variable of size $s$ with $m$ subdivisions, the one-hot vector has length
$s \times m$ and is **component-major**:

```text
[ comp 0: k=0 .. k=m-1 | comp 1: k=0 .. k=m-1 | ... ]
```

This is the layout that `CatalogueDesignSpace.add_categorical_variable` produces,
and the one the master assumes when it derives
`n_members = variable_size / n_catalogues` and emits one sum-to-one row per
component. Every part of the package must agree with it, otherwise the master
selects one box while the sub-problem enforces another, silently.

## Formulation 1: the box as a constraint

{py:class}`~gemseo_box_subdivision.disciplines.box_constraint.BoxConstraint` computes
$g_{\text{box}}$ as a single vector-valued output of dimension $2n$, upper faces
first, with an analytic Jacobian with respect to both $x$ and $\alpha$.

Keeping the $2n$ components in **one** function keeps the cut bookkeeping to a
single entry per sub-problem solve.

### The bound margin

A box lying against the border of the design space has a face that *coincides*
with a bound of the design space. When the sub-problem optimum lies on that face,
both are active, and GEMSEO attributes the multiplier to the bound. The box
constraint is then left with a multiplier of zero, and the sensitivity of that
box is silently computed as zero — for the first and the last subdivision of
*every* variable.

`BoxSubdivision.create_relaxed_design_space` widens the bounds by a small
relative margin so they stay inactive. On a one-dimensional problem whose exact
multiplier is $5.76$:

| relative margin | multiplier of the box constraint |
|-----------------|----------------------------------|
| $0$ to $10^{-6}$ | $0$, attributed to the bound |
| $10^{-5}$ and above | $5.76$ |

The threshold is the tolerance under which a bound counts as active, hence the
default of $10^{-4}$. The box itself is still enforced by the constraint, so the
design variables stay in the original bounds up to the constraint tolerance.

### The starting point

The sub-problem is solved by a local algorithm, so its starting point decides
which local minimum of the box it reaches. Neither policy offered by GEMSEO
suits a subdivision:

- `reset_x0_before_opt` restarts every sub-problem from the initial value of the
  design space, which lies outside of all the boxes but one;
- warm-starting from the previous sub-problem makes the result depend on the
  order in which the boxes are visited;
- `set_x0_before_opt` cannot help, since the main problem decides the box, not
  the design variables.

This is not a detail: with the default policy, **even the exhaustive enumeration
of the 100 boxes of the benchmark missed the global optimum**, returning $1.92$
instead of $0$, because most sub-problems started outside their own box and the
local solver stalled on a face.

{py:func}`~gemseo_box_subdivision.disciplines.scenario_adapters.box_start.create_box_start_adapter_class`
returns a `Benders` scenario adapter that starts each sub-problem at the center
of the selected box, which is feasible by construction and independent of the
order of the boxes.

## Formulation 2: the box as normalized variables

{py:class}`~gemseo_box_subdivision.disciplines.box_mapping.BoxMapping` maps
$(\xi, \alpha)$ to $x$, again with an analytic Jacobian. Because the bounds of
the sub-problem no longer depend on the box, this formulation needs **neither**
the margin **nor** the scenario adapter: $\xi = 0.5$ is the center of whichever
box.

The discipline is chained before the objective, so the sub-problem solves for
$\xi$ while the disciplines keep receiving $x$.

## The design spaces

Both levels live in one `CatalogueDesignSpace`, which the `Benders` formulation
splits on its own by keeping the categorical variables in the main problem:

{py:func}`~gemseo_box_subdivision.design_spaces.create_box_design_space`
: the original variables with widened bounds, plus one categorical variable per
  subdivided variable. For the constraint formulation.

{py:func}`~gemseo_box_subdivision.design_spaces.create_normalized_box_design_space`
: the normalized variables bounded by $0$ and $1$, plus the same categorical
  variables. For the normalized formulation.

In both cases the catalogue of a subdivided variable is the range of its
subdivision indexes, so the default weights make two consecutive subdivisions
neighbours in the distance used by the master, and the initial box is the one
containing the initial value of the design space.

## Enumerating the boxes

{py:func}`~gemseo_box_subdivision.design_spaces.create_box_samples`
returns the one-hot vector of every box. Passing them to the `CustomDOE` driver
of the main problem solves the sub-problem of every box, which is the reference
the method has to beat — and, being a driver of the same problem, makes the
comparison isolate the exploration strategy.

## The extensions

Four extensions of the method are implemented, all of them in the package, so
that each can be applied to another problem by importing it rather than by
copying a benchmark.

### Subdividing some of the variables only

{py:meth}`~gemseo_box_subdivision.subdivisions.box.BoxSubdivision.from_design_space`
takes the variables to subdivide, and the design spaces keep the others as they
are, so a variable left out stays an ordinary variable of the sub-problem:

```python
subdivision = BoxSubdivision.from_design_space(design_space, 10, ["x_split"])
```

Nothing else changes: {class}`.BoxMapping` maps the subdivided variables alone,
and the master carries binaries for them alone.

### The multi-resolution encoding

{py:class}`~gemseo_box_subdivision.subdivisions.multi_resolution.MultiResolution`
and
{py:class}`~gemseo_box_subdivision.disciplines.multi_resolution_mapping.MultiResolutionMapping`
are the counterparts of `BoxSubdivision` and `BoxMapping` for a box chosen by one
categorical variable per level, used exactly as the flat pair is:

```python
subdivision = MultiResolution(lower_bounds, upper_bounds, branching=4, levels=2)
space = subdivision.create_design_space()
```

Three contracts carry the construction. **`locate` is a base conversion**,
writing a position in base $m$ and reading off $L$ digits, one one-hot vector per
level, with `compute_bounds` its inverse. **The Jacobian blocks are constant**,
the width $\Delta_j m^{-L}$ not depending on the levels, which is what keeps the
post-optimal sensitivity of the `Benders` formulation valid. **The catalogue
weights are ones**, set explicitly, so the trust region counts the digits a
candidate changes rather than what those digits are worth.

### The radius of the trust region

{py:attr}`~gemseo_box_subdivision.subdivisions.box.BoxSubdivision.max_step`
returns the radius at which the region stops constraining the master, which with
unit catalogue weights is the number of subdivided components. It is a property
of the subdivision rather than a setting, and its docstring records that it is
**not** the radius to use; `BoxSubdivisionSettings.trust_region_radius` is.

The multi-resolution encoding has one one-hot group per level per component, so
its `max_step` is $L$ times larger and the scenario scales the radius by the
number of levels before executing. Leaving it unscaled measures the encoding with
a region far tighter than the one it is compared against.

### The hierarchies

{py:mod}`~gemseo_box_subdivision.hierarchy` holds the scoring rules and the three
shapes. A shape is a **loop around the method** rather than a change to it, so it
is driven by a callable solving one level and reporting the boxes it solved:

```python
def solve(lower_bound, upper_bound, n_subdivisions):
    ...  # build and execute a scenario over these bounds
    return subdivision, read_solved_boxes(problem)


refine_deep(solve, lower_bound, upper_bound, branching=2, depth=4)
```

Returning **no solved box** ends the search, which is how a caller reports that
its budget is spent or that its master became infeasible. Each shape returns the
bounds of every region it visited.

{py:func}`~gemseo_box_subdivision.hierarchy.read_solved_boxes`
: reads back the value and the post-optimal sensitivity of every box a master
  solved, from the database of its problem, as
  {py:class}`~gemseo_box_subdivision.hierarchy.SolvedBox` records.

{py:func}`~gemseo_box_subdivision.hierarchy.compute_cut_model`
: evaluates the cuts of a master over **every** box of its subdivision, including
  those it never solved, which is what lets a ranking propose an unvisited box.

`rank_by_value`, `rank_by_cuts`, `rank_mixed`
: the three rules, collected in
  {py:data}`~gemseo_box_subdivision.hierarchy.RANKINGS`.

`refine_deep`, `refine_two_levels`, `refine_frontier`
: the three shapes, collected in
  {py:data}`~gemseo_box_subdivision.hierarchy.SHAPES`. Only the
  frontier can return to a box it passed over, holding a priority queue of open
  boxes from every level.

`benchmarks/hierarchy.py` is then only the GEMSEO wiring and the budget
accounting: `Level`, a counter spending a share of the budget of a run and
raising when that share is gone, so that a hierarchy and a flat run are compared
at equal cost.

## What is checked

- The Jacobians of `BoxConstraint` and `BoxMapping` are verified against finite
  differences and complex step, at **relaxed** one-hot values, since the master
  relaxes them.
- The sensitivity is verified end to end: the multiplier of an active face of a
  sub-problem is compared with the exact slope of the objective.
- The one-hot layout of the design space and of the disciplines are
  cross-checked, so a disagreement cannot pass silently.
- The Jacobian of `MultiResolutionMapping` is verified against finite
  differences at **relaxed** one-hot values too, and `locate` against
  `compute_bounds`: every box returned must contain the value that selected it,
  and every box has the same width whichever it is.
- The hierarchies are tested against a stub solver rather than a scenario, so
  their contract is checked on its own: a descending shape nests and narrows,
  the frontier does not nest, the cut model is defined at boxes never solved, and
  a level returning no solved box ends the search.
- The border-box degeneracy is pinned by a regression test that asserts both the
  broken behaviour without a margin and the correct one with it.
- The scenario is checked to derive the master's variables from the design space,
  by building the same problem for a variable that is not called `x`, and to
  select the right adapter and constraint for each formulation. The settings are
  checked to keep the two mechanisms apart in both directions, one constant on
  and the other off.
- The entry point is checked to reproduce a hand-composed run to the digit, and
  the benchmarks are run through it, so that a change to the assembly shows up as
  a change to the published numbers rather than passing unnoticed.
