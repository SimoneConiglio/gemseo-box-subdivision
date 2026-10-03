<!--
 Copyright 2026 Simone Coniglio

 This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
 International License. To view a copy of this license, visit
 http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
 Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

# Implementation

The package provides components for GEMSEO rather than a monolithic algorithm:
the subdivision, the two formulations confining a sub-problem to a box, the
design spaces of both levels, and a scenario adapter. Their assembly is
performed by the package, because it is subject to invariants rather than to
user choices.

## Architecture

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
mapping before the objective, builds the design space from the same subdivision,
derives the names of the master variables from the design space, selects the
`Benders` formulation and, for the constraint formulation, configures the
scenario adapter and declares the box constraint. Its `execute` method supplies
the settings of the master, so that a run requires no configuration of the
master.

The settings express the parameters of the master in the terms of the
methodology, for instance a `trust_region_radius` in number of changed components
instead of a `max_step`, and `to_master_settings` is the only method that
translates them. It enforces four invariants:

- the two convexity mechanisms are mutually exclusive: selecting one sets the
  constant of the other to zero;
- these parameters describe an outer-approximation master and are translated only
  for a master that declares them; setting one for another master raises an
  error, such a master being configured by `master_algo_settings` only;
- the master is executed by its name with these settings, not through a settings
  model: a GEMSEO settings model designates the algorithm it selects, and the
  settings of `OUTER_APPROXIMATION` designate an algorithm that no library
  provides. The sub-problem is configured the other way round, the `Benders`
  formulation taking the model built by `create_sub_problem_settings_model`;
- both names are checked against the settings declared by the algorithm when the
  settings are built, not during the run.

{py:class}`~gemseo_box_subdivision.settings.BoxSubdivisionSettings` and
{py:class}`~gemseo_box_subdivision.settings.SweptBoxSubdivisionSettings` are the
two available settings classes, sharing
{py:class}`~gemseo_box_subdivision.settings.BaseBoxSubdivisionSettings` for the
settings of the run. The swept settings designate no master, since the sweep is
implemented in it, and contain no convexity value; the ladder has one rung per
parallel point of the master, which associates each probe with a rung. The
scenario accepts both.

When the installed master does not implement the sweep,
{py:data}`~gemseo_box_subdivision.convexity_sweep.MASTER_SWEEPS_CONVEXITY` is
`False` and `drive_the_master` wraps the run in a driver that applies the ladder
around the mixed-integer solution of the master, moving a probe to the next rung
while it proposes a box already solved. This driver is temporary and will be
removed when the master implements the sweep; without it, the cuts would not be
protected, the convexity of the master defaulting to zero.

All lower-level components are public and can be used separately, as described
in [Usage](usage.md).

## Subdivision

{py:class}`~gemseo_box_subdivision.subdivisions.box.BoxSubdivision` describes the
Cartesian subdivision: for each variable, the lower and upper bounds of each
interval of each component, with shape `(size, n_subdivisions)`.

```python
subdivision = BoxSubdivision.from_design_space(design_space, {"x": 10, "y": 4})
subdivision.n_boxes      # exponential in the number of components
subdivision.n_binaries   # linear in it: this is what sizes the master
```

It also provides the helpers used by the other components: `compute_bounds` for
the box selected by a one-hot vector, `locate` for the interval containing a
value, and the naming conventions `get_one_hot_names` and `get_normalized_names`,
so that all components use the same variable names.

## One-hot layout

For a variable of size $s$ with $m$ subdivisions, the one-hot vector has length
$s \times m$ and is ordered by component:

```text
[ comp 0: k=0 .. k=m-1 | comp 1: k=0 .. k=m-1 | ... ]
```

This is the layout produced by `CatalogueDesignSpace.add_categorical_variable`
and assumed by the master, which derives
`n_members = variable_size / n_catalogues` and builds one sum-to-one constraint
per component. All components of the package must use this layout; otherwise the
master selects one box while the sub-problem enforces another, without any error.

## Formulation 1: box as a constraint

{py:class}`~gemseo_box_subdivision.disciplines.box_constraint.BoxConstraint`
computes $g_{\text{box}}$ as a single vector-valued output of dimension $2n$,
upper faces first, with an analytic Jacobian with respect to $x$ and $\alpha$.
Keeping the $2n$ components in one function gives a single cut entry per
sub-problem solution.

### Bound margin

A box adjacent to the boundary of the design space has a face that coincides with
a bound of the design space. When the optimum of the sub-problem lies on this
face, both are active and GEMSEO assigns the multiplier to the bound. The
multiplier of the box constraint is then zero and the sensitivity of the box is
computed as zero, for the first and last interval of every variable, without any
warning.

`BoxSubdivision.create_relaxed_design_space` widens the bounds by a small relative
margin so that they remain inactive. Table 1 gives the multiplier of the box
constraint for a one-dimensional problem whose exact multiplier is $5.76$.

| relative margin | multiplier of the box constraint |
|-----------------|----------------------------------|
| $0$ to $10^{-6}$ | $0$, assigned to the bound |
| $10^{-5}$ and above | $5.76$ |

*Table 1. Effect of the bound margin on the multiplier of the box constraint.*

The threshold corresponds to the tolerance below which a bound is considered
active, hence the default value of $10^{-4}$. The box is still enforced by the
constraint, so that the design variables remain within the original bounds up to
the constraint tolerance.

### Starting point

The sub-problem is solved by a local algorithm, whose starting point determines
the local minimum reached within the box. None of the policies provided by GEMSEO
is suitable for a subdivision:

- `reset_x0_before_opt` restarts every sub-problem from the initial value of the
  design space, which lies outside all boxes but one;
- warm-starting from the previous sub-problem makes the result depend on the
  order in which the boxes are visited;
- `set_x0_before_opt` is not applicable, since the box is decided by the main
  problem and not by the design variables.

With the default policy, even the enumeration of the $100$ boxes of the benchmark
missed the global optimum, returning $1.92$ instead of $0$, because most
sub-problems started outside their box and the local solver stopped on a face.

{py:func}`~gemseo_box_subdivision.disciplines.scenario_adapters.box_start.create_box_start_adapter_class`
returns a `Benders` scenario adapter that starts each sub-problem at the centre of
the selected box, which is feasible by construction and independent of the order
of the boxes.

## Formulation 2: box as normalized variables

{py:class}`~gemseo_box_subdivision.disciplines.box_mapping.BoxMapping` maps
$(\xi, \alpha)$ to $x$, with an analytic Jacobian. Since the bounds of the
sub-problem no longer depend on the box, this formulation requires neither the
margin nor the scenario adapter: $\xi = 0.5$ is the centre of every box.

The discipline is chained before the objective, so that the sub-problem is solved
for $\xi$ while the disciplines receive $x$.

## Design spaces

Both levels are defined in one `CatalogueDesignSpace`, which the `Benders`
formulation splits by keeping the categorical variables in the main problem:

{py:func}`~gemseo_box_subdivision.design_spaces.create_box_design_space`
: the original variables with widened bounds and one categorical variable per
  subdivided variable, for the constraint formulation.

{py:func}`~gemseo_box_subdivision.design_spaces.create_normalized_box_design_space`
: the normalized variables bounded by $0$ and $1$ and the same categorical
  variables, for the normalized formulation.

In both cases the catalogue of a subdivided variable is the range of its interval
indices, and the initial box is the one containing the initial value of the
design space.

## Enumeration of the boxes

{py:func}`~gemseo_box_subdivision.design_spaces.create_box_samples` returns the
one-hot vector of every box. Passing these vectors to the `CustomDOE` driver of
the main problem solves the sub-problem of every box, which is the reference used
in the results. Since it is a driver of the same problem, the comparison isolates
the exploration strategy.

## Extensions

Four extensions of the method are implemented in the package, so that they can be
applied to other problems by import.

### Subdivision of a subset of the variables

{py:meth}`~gemseo_box_subdivision.subdivisions.box.BoxSubdivision.from_design_space`
accepts the names of the variables to subdivide, and the design spaces keep the
other variables unchanged, so that they remain continuous variables of the
sub-problem:

```python
subdivision = BoxSubdivision.from_design_space(design_space, 10, ["x_split"])
```

{class}`.BoxMapping` maps only the subdivided variables, and the master has
binaries for them only.

### Multi-resolution encoding

{py:class}`~gemseo_box_subdivision.subdivisions.multi_resolution.MultiResolution`
and
{py:class}`~gemseo_box_subdivision.disciplines.multi_resolution_mapping.MultiResolutionMapping`
are the counterparts of `BoxSubdivision` and `BoxMapping` for a box selected by
one categorical variable per level, and are used in the same way:

```python
subdivision = MultiResolution(lower_bounds, upper_bounds, branching=4, levels=2)
space = subdivision.create_design_space()
```

Three properties define the implementation. `locate` performs a base conversion,
writing a position in base $m$ and reading $L$ digits, one one-hot vector per
level, and `compute_bounds` is its inverse. The Jacobian blocks are constant,
since the width $\Delta_j m^{-L}$ does not depend on the levels, which keeps the
post-optimal sensitivity of the `Benders` formulation valid. The catalogue
weights are set explicitly to one, so that the trust region counts the digits
changed by a candidate.

### Trust-region radius

{py:attr}`~gemseo_box_subdivision.subdivisions.box.BoxSubdivision.max_step`
returns the radius beyond which the trust region no longer constrains the master,
which with unit catalogue weights equals the number of subdivided components. It
is a property of the subdivision and not the radius to be used; the radius is set
by `BoxSubdivisionSettings.trust_region_radius`.

The multi-resolution encoding has one one-hot group per level and component, so
that its `max_step` is $L$ times larger; the scenario multiplies the radius by the
number of levels before execution. Without this scaling the encoding would be
evaluated with a much smaller trust region than the flat encoding it is compared
with.

### Hierarchies

{py:mod}`~gemseo_box_subdivision.hierarchy` contains the scoring rules and the
three shapes. A shape is a loop around the method rather than a modification of
it, and is driven by a callable that solves one level and returns the boxes it
solved:

```python
def solve(lower_bound, upper_bound, n_subdivisions):
    ...  # build and execute a scenario over these bounds
    return subdivision, read_solved_boxes(problem)


refine_deep(solve, lower_bound, upper_bound, branching=2, depth=4)
```

Returning no solved box ends the search, which allows the caller to report an
exhausted budget or an infeasible master. Each shape returns the bounds of all
visited regions.

{py:func}`~gemseo_box_subdivision.hierarchy.read_solved_boxes`
: reads the value and the post-optimal sensitivity of every box solved by a
  master from the database of its problem, as
  {py:class}`~gemseo_box_subdivision.hierarchy.SolvedBox` records.

{py:func}`~gemseo_box_subdivision.hierarchy.compute_cut_model`
: evaluates the cuts of a master over all boxes of its subdivision, including the
  unsolved ones, so that a ranking can select an unvisited box.

`rank_by_value`, `rank_by_cuts`, `rank_mixed`
: the three ranking rules, collected in
  {py:data}`~gemseo_box_subdivision.hierarchy.RANKINGS`.

`refine_deep`, `refine_two_levels`, `refine_frontier`
: the three shapes, collected in
  {py:data}`~gemseo_box_subdivision.hierarchy.SHAPES`. Only the frontier can
  return to a box previously passed over, using a priority queue of open boxes
  from all levels.

`benchmarks/hierarchy.py` contains the GEMSEO configuration and the budget
accounting: `Level` is a counter that spends a share of the budget of a run and
raises an exception when this share is exhausted, so that a hierarchy and a flat
run are compared at equal cost.

## Verification

- The Jacobians of `BoxConstraint` and `BoxMapping` are verified against finite
  differences and the complex step at relaxed one-hot values, since the master
  relaxes them.
- The sensitivity is verified end to end: the multiplier of an active face of a
  sub-problem is compared with the exact slope of the objective.
- The one-hot layouts of the design space and of the disciplines are compared,
  so that a mismatch is detected.
- The Jacobian of `MultiResolutionMapping` is verified against finite differences
  at relaxed one-hot values, and `locate` against `compute_bounds`: every
  returned box contains the value that selected it, and all boxes have the same
  width.
- The hierarchies are tested with a stub solver instead of a scenario: a
  descending shape produces nested and narrowing regions, the frontier does not,
  the cut model is defined at unsolved boxes, and a level returning no solved box
  ends the search.
- The degeneracy at the boundary boxes is covered by a regression test that
  checks both the incorrect behaviour without margin and the correct behaviour
  with it.
- The scenario is checked to derive the master variables from the design space,
  using a variable not named `x`, and to select the adapter and constraint of each
  formulation. The settings are checked to keep the two convexity mechanisms
  mutually exclusive in both directions.
- The scenario is checked to reproduce a manually composed run exactly, and the
  benchmarks are run through it, so that a change in the assembly appears as a
  change in the published results.
