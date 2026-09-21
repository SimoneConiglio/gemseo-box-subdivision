<!--
Copyright 2026 Simone Coniglio

This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
International License. To view a copy of this license, visit
http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

<!--
Changelog titles are:
- Added: for new features.
- Changed: for changes in existing functionality.
- Deprecated: for soon-to-be removed features.
- Removed: for now removed features.
- Fixed: for any bug fixes.
- Security: in case of vulnerabilities.
-->

# Changelog

All notable changes of this project will be documented here.

The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.0.0)
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Fixed

- The constraint formulation no longer fails when only some of the variables
  are subdivided: the adapter starting a sub-problem inside its box sets the
  starting point of the subdivided variables one at a time, instead of handing
  the design space a current value covering part of its variables, which it
  rejects. The variables that are not subdivided keep the value they have.

- An MDA can now be a discipline of a `BoxSubdivisionScenario` once a
  constraint is attached. The disciplines are collapsed into one chain, which
  treats the couplings of an MDA as inputs of the chain, so the adapter asked
  the MDA for derivatives with respect to its own couplings as soon as there
  was a constraint to differentiate, and the Jacobian assembly refused with
  `Variable y2 is both a coupling and a design variable`. Inside a chain those
  couplings are internal, and the derivative that is no longer asked for is
  zero: a coupling enters an MDA as an initial guess and leaves it converged,
  and a converged fixed point does not depend on where the iteration started.

### Added

- `keep_couplings_internal` and `keep_every_mda_couplings_internal`, which do
  that to an MDA, for a composition built without the scenario.

### Documentation

- *Coupled problems: the disciplines are chained*, saying that the disciplines
  are chained and that a coupled problem therefore needs its MDA built
  explicitly — a reader handing the scenario five coupled disciplines otherwise
  gets a feed-forward evaluation and no warning.

## 0.2.0 (2026-09-19)

The settings, in two entry points: the general construction, which names the
master and the solver running inside a box, and the swept one, which asks the
master to sweep the convexity rather than asking its user for a margin in the
units of an objective they have not measured. What each entry point holds is
what applies to it, every setting is given by name, and a setting of an outer
approximation no longer reaches a master that has none.

Measured against the baselines, the swept construction — nothing tuned, no
convexity value supplied — reaches the same distance to the optimum as the
calibrated one on every problem of the benchmark, and reaches it from more
starting points on two of them. The numbers this release reports are therefore
the ones a user gets without first tuning the method to the problem they are
about to solve.

### Added

- The algorithm of each of the two levels is a setting, with its own settings:
  `BoxSubdivisionSettings.master_algo_name` and `master_algo_settings` for the
  master, `sub_problem_algo_name` and `sub_problem_algo_settings` for the solver
  running inside a box. The defaults are the pair every reported result was
  measured with, the outer-approximation master over SLSQP, so a sub-problem is
  no longer solved by SLSQP with nothing but its iteration count to configure it.
  A derivative-free solver of the sub-problem is now a setting rather than a fork
  of the scenario; nothing here measures one, and what the method needs of a
  sub-problem solver is a local optimum of its box, the cut of that box being
  built at the point it returns.
- Both names are checked against what the algorithm declares when the settings
  are built: a name no GEMSEO library provides, a setting the algorithm named does
  not have, and an ordinary optimizer named as the master, which cannot hold the
  integers a box is made of, are all refused where they are written rather than in
  the middle of a run.
- Settings asking the master to **sweep the convexity**, so that a run no longer
  needs a margin calibrated in the units of its objective, which is the standing
  criticism of the method. The master probes one trust-region radius per
  parallel point; the same probes can carry a ladder of convexity values, the
  low rungs proposing the box next door and the high rungs the box across the
  design space, with every probe that proposes nothing new redeployed a rung
  higher until it proposes a new box or the ladder is exhausted.

  `SweptBoxSubdivisionSettings` asks for it, with an upper bound,
  `SweptBoxSubdivisionSettings(max_value=100.0)`, or with nothing at all,
  `SweptBoxSubdivisionSettings()`, the bound then following the spread of the
  objective over the boxes already solved, with a decade of headroom. It is an
  entry point of its own rather than a setting of `BoxSubdivisionSettings`: a run
  that sweeps has no convexity to calibrate and no master to name, and the rungs
  of its ladder are the parallel points of the master, a probe per rung, rather
  than a count of their own that could disagree with them.

  On Rastrigin and Ackley in two dimensions, whose objectives differ by a factor
  of four in scale, the unbounded sweep reaches the optimum from every starting
  point on both, which no fixed margin among those tried does, and a bound ten
  times too large costs two starting points where a margin ten times too small
  costs the run. See `benchmarks/convexity_sweep.py` and annex C.

  **The sweep belongs to the master**, and it is implemented in
  `gemseo-bilevel-outer-approximation`, under `convexity_sweep_points` and
  `convexity_sweep_max`; this package turns its two settings into those. Against
  a master predating them, `MASTER_SWEEPS_CONVEXITY` is `False` and the package
  drives the ladder itself, around the master's mixed-integer solve, computing
  the bound from the objective as the master would. That is what makes the
  unbounded form work against any master: the master's own convexity defaults to
  zero, so leaving it there would be a run with its cuts unguarded rather than a
  run without a sweep. Both `_convexity_sweep_driver` and
  `_convexity_sweep_fallback` are temporary and go once the master ships the
  sweep.

### Changed

- **Every setting is given by name.** The three settings classes are keyword-only,
  since which one holds which setting follows what applies to what rather than an
  order a reader could rely on: a value given positionally would bind to whatever
  sits in that position, and a convexity margin arriving as a trust-region radius
  is a run that measures something else in silence.
- **The two constructions are two entry points.** `BoxSubdivisionSettings` is the
  general one, naming any master that can choose a box and any sub-problem
  solver; `SweptBoxSubdivisionSettings` is the swept one, driving the master that
  implements the sweep with the parameters of that master chosen rather than
  supplied. What each holds is what applies to it: the swept entry point has no
  `master_algo_name`, no `master_algo_settings`, no `convexity_margin` and no
  `convexification_constant`, since a value to calibrate is what a sweep exists
  not to ask for.
- **A setting of the outer approximation no longer reaches a master that has
  none.** `mechanism`, the two convexity values, `trust_region_radius`,
  `n_parallel_points`, `max_iter` and `tolerance` are the method's names for
  settings of an outer-approximation master. They are translated only for a
  master declaring them, and setting one for a master that does not is refused
  where it is written, naming both the setting and what the master calls it,
  rather than sent blindly and rejected at execution. A master that is not an
  outer approximation is configured by `master_algo_settings` alone.
- **The master must be able to choose a box.** The master problem is a relaxable
  mixed-integer non-linear one, whose relaxation the outer approximation solves
  before recovering the integers from it, so an algorithm that cannot hold an
  integer variable returns the relaxation rather than a box, and is refused when
  the settings are built.
- The master is executed by its name with the settings `to_master_settings`
  returns, rather than through a `BiLevelMasterOuterApproximation_Settings` model.
  A GEMSEO settings model names the algorithm it selects, and the settings of
  `OUTER_APPROXIMATION` name one no library provides, so a model would have run an
  algorithm other than the one `master_algo_name` asks for. That mismatch is a
  defect of the plugin declaring those settings, not of the algorithm.
- **The documentation reports the method as a user gets it.** The comparison
  against the baselines carried a convexity margin chosen on the problems it
  reports; it now carries the swept configuration beside it, and the landing
  page sends a reader to the sweep rather than to a chapter on calibrating a
  constant. The methodology derives the sweep where the mechanisms it replaces
  are derived, the results carry what it reaches, the extensions move to an
  annex of their own, and the notes recording what an earlier version of a page
  reported are gone: a withdrawn measurement is not a finding.
- The published documentation has **two builds**: the released one at the root
  of the site and the integration branch under `/dev/`, which says on every page
  that it documents code in no release. Both are written to the `gh-pages`
  branch, which the site is served from, and every build — a pull request's
  included — uploads a browsable archive, so a change can be read before it is
  published. See `CONTRIBUTING.md`.

### Deprecated

- `BoxSubdivisionSettings.options`, the pass-through to the master, is
  `master_algo_settings`, which says which of the two levels it configures. The
  old name still works, and warns; given both, `master_algo_settings` wins.

### Fixed

- A variable of size $s$ subdivided into $m$ was always $s$ independent choices
  of one subdivision out of $m$, one one-hot group per component, and it still
  is; what was missing was a test that could tell. Every array-variable test
  used two components and two subdivisions, and a square case cannot distinguish
  a grouping by component from a grouping by subdivision. The cases added take
  the two sizes apart, and the usage chapter states the rule: the density is per
  component, so one variable of size five and five variables of size one give
  the same master.

## 0.1.0 (2026-09-15)

First public release.

The method, its four constructions and the benchmark that measures them. The
results are measurements on the problems reported, not a claim of generalization:
the settings were tuned on those very problems, and the convexity margin is in
the units of the objective, so it does not transfer between them unchanged.

### Added

- EGO, the Bayesian optimization of `egobox`, is a fifth baseline, and with it a
  comparison at one budget of five hundred evaluations that every method can
  afford, `benchmarks/small_budget.py`. It is the baseline of the regime the
  method targets, and at that budget it explores the hard multimodal cases
  better than anything else here, returning $1.99$ on Rastrigin at five variables
  against $4.98$ for DIRECT and $8.57$ for this method. Its own cost, a hundred
  times this method's on the same cell, is not counted in that table and is what
  an expensive objective would invert.
- Initial packaging of the project as a GEMSEO plugin, generated from the
  [GEMSEO copier template](https://gitlab.com/gemseo/dev/copier-gemseo).
- Dependency on `gemseo-bilevel-outer-approximation`.
- `benchmark` dependency group with `gemseo-benchmark`, and the matching
  `tox -e benchmark` environment.
- Design note for the box-subdivision outer approximation algorithm.
- `BoxSubdivision`, a Cartesian subdivision of a design space.
- `BoxConstraint`, the discipline expressing the selected box as a
  vector-valued constraint, with its analytic Jacobian.
- `create_box_design_space`, building the design space of both levels.
- `BoxSubdivision.locate` and `BoxSubdivision.get_one_hot_names`.
- `create_box_start_adapter_class`, a `Benders` scenario adapter starting
  each sub-problem at the center of its box.
- `create_box_samples`, the one-hot vectors of every box, to solve them all
  with the `CustomDOE` driver.
- Benchmark comparing the outer approximation with that enumeration.
- `benchmarks/configurations.py`, the two named configurations of the master,
  `adaptive`, the default, and `pure_convexification`, whose constant is the
  order of the variation of the objective rather than an arbitrarily large
  number, and which the benchmarks now sweep over the range where it is worth
  using, reporting the cost as a fraction of the enumeration it replaces.
- `benchmarks/configurations.py` sizes the trust region of the master to the
  design space for every configuration. The master's default radius of ten is
  unrelated to that space, whose diameter is the sum over the components of the
  number of subdivisions minus one, and starting below it confines the search:
  with five variables and ten subdivisions each, that is the difference between
  solving Rastrigin, which no baseline here does, and returning a gap of
  sixteen. The benchmark page reports the comparison with the radius sized, the
  density sweep it corrects, and the constants of both mechanisms at the fine
  subdivision, where the convexity margin goes up rather than down.
- `benchmarks/refine_some_variables.py`, comparing a coarse subdivision of every
  variable with a fine subdivision of some of them, and the `partly_multimodal`
  problem it needs, multimodal in two variables and convex in the others.
- `benchmarks/hierarchy.py`, subdividing coarsely and refining the boxes that
  look promising, with the same budget as a flat run, under three rules
  deciding what to refine: the value of the sub-problem solved in a box, the cut
  model of the master, which scores every box including those never solved, and
  a mix of the two, in two levels or in a deep hierarchy splitting every
  variable in two at each level. The deep one reaches the optimum of Ackley in
  five dimensions from three starting points out of six, which no flat
  subdivision here does; none of them beats the flat subdivisions elsewhere, a
  hierarchy being unable to return to a subdomain it passed over.
- `BoxSubdivision.max_step`, the largest trust-region step of the master in the
  distance induced by the weights of the boxes, to be passed as its `max_step`
  when a run stops early: the master's own default of ten is smaller than the
  design space as soon as the subdivision is not coarse, and the run then ends
  on an infeasible master instead of on its optimality test.
- Benchmark comparing the method with the baselines of the problem class,
  multistart, CMA-ES and DIRECT, at equal budget of equivalent objective
  evaluations under both gradient-cost conventions.
- `benchmarks/run_baselines.py`, sweeping the baselines over the problems,
  the dimensions and the seeds.
- `BoxMapping` and `create_normalized_box_design_space`, an alternative
  formulation solving the sub-problem in the normalized variables of the box.
- `BoxSubdivision.compute_bounds` and `BoxSubdivision.get_normalized_names`.
- `benchmarks/tune_convexification.py`, sweeping the convexification of both
  formulations, and the convexification tuned for each of them.

### Changed

- The multi-resolution encoding, one categorical variable per level, is part of
  the package rather than of the benchmarks: `MultiResolution` and
  `MultiResolutionMapping`. It reaches $m^L$ subdivisions per component for
  $n m L$ binaries, and on Styblinski-Tang at five variables, the problem the
  best flat density breaks on, two levels of four get within $0.27$ of the
  optimum on forty binaries against the eighty of the flat encoding that matches
  it, for fewer evaluations.
- The hierarchies of subdivisions are part of the package too,
  `algos/opt/hierarchy.py`, driven by a callable that solves one level, so that
  a shape can be applied to another problem without copying a benchmark.
- The density of a subdivision is bounded above by a measurable ratio rather than
  by the number of boxes: the cut model carries as many coefficients as there are
  binaries, and a budget affords a few dozen cuts. On five variables, ten
  subdivisions per variable is the best density measured and sixteen is markedly
  worse, whatever the boxes they represent. It is bounded below by the spacing of
  the basins, and refining past them degrades the ranking rather than merely
  costing sub-problems, so no single density serves the four benchmark problems.
- The results show the hierarchies beside the flat subdivisions in a figure of
  their own, the distance to the optimum and the cost, with a tick per starting
  point reaching the optimum, and the frontier is measured over six starting
  points like the rest.
- The documentation follows the method rather than its history: methodology,
  implementation, usage, results and a conclusion, with the benchmark problems,
  the baselines and the sweeps that set the settings of the master moved to
  annexes A, B and C. The methodology derives the hierarchies of subdivisions,
  the scores that rank a box and what each shape can and cannot undo, and the
  implementation and usage pages describe the extensions and how to refine a
  box.
- The methodology describes what the method has grown since: what grows with the
  dimension, the boxes or the master, the trust region and the distance it uses,
  subdividing some variables only, and the three shapes of hierarchy, each with
  its figure. The results carry the extensions and end on the directions that
  follow from them.
- The documentation is illustrated, `docs/figures.py` drawing every figure for
  the light and the dark theme, and it is split so that the results are readable
  on their own: the benchmark page reports what the method achieves, a page of
  its own covers the tuning of the master, and two appendices describe and cite
  the benchmark problems and the baselines. The appendix on the baselines gives
  the algorithm of each, the settings it is run with, how the budget is enforced
  across methods called from Python and from a C extension, what is deliberately
  absent, and a figure of where each one evaluates the objective.
- The project is named `gemseo-box-subdivision`, since it is about the
  box-subdivision outer approximation rather than a collection of
  algorithms. The package is `gemseo_box_subdivision`.
- The GEMSEO monogram is no longer used as the logo of the documentation,
  being the registered mark of GEMSEO.
- The documentation is built with Sphinx instead of MkDocs, and published on
  GitHub Pages by a dedicated workflow.
- The documentation uses the PyData theme, with a navigation bar, a section
  navigation, a page outline and cards on the landing pages.

### Fixed

- The trust region of the master measures a distance. The design spaces of this
  package now weigh every subdivision alike, so that the distance between two
  boxes is the number of components a candidate changes. They used to inherit the
  default of `CatalogueDesignSpace`, which weighs a numeric catalogue by the
  catalogue values themselves; with the cost of a move charged on the weight the
  **incumbent** holds, leaving the first subdivision of a component was free and
  leaving the last cost $m_j - 1$, whatever the destination, so the region was
  lopsided rather than local and became infeasible at high indexes. Reported
  upstream. On Rastrigin with five variables and ten subdivisions this is the
  difference between a gap of $0.995$ from two starting points out of six and the
  optimum from all six; the settings, the density sweep, the hierarchies and the
  multi-resolution encoding were all re-measured against it.
- The radius of the trust region is small, `TRUST_REGION_RADIUS = 2` components,
  rather than the diameter of the design space that the documentation used to
  recommend. Once the distance is a distance, widening the region is markedly
  worse and removing it is worse still.
- The benchmark runner survives a budget spent inside a linearization, which
  GEMSEO reports as a missing output key rather than as the budget error raised
  underneath it; such a run used to crash instead of returning its best point.
- The multi-resolution encoding is measured with a trust region at all. Its
  radius was being taken from the diameter helper, which for unit weights returns
  the number of one-hot groups, so the region did not constrain; it is now scaled
  by the number of levels, this encoding having one group per level per variable.
- The benchmarks no longer mix the two mechanisms of the master, the adaptive
  repair of the cut slopes and the fixed convexification constant, which are
  different approaches. The configuration is now an explicit axis,
  `benchmarks/configurations.py`, and the settings and results reported by the
  documentation are measured with one mechanism at a time. The previously
  reported comparison of the two formulations, 96% against 58%, compared their
  tuning rather than the formulations, and the reported collapse of the method
  when the number of boxes grows is a property of the fixed constant rather than
  of the method: with the adaptive repair, Styblinski-Tang in five dimensions is
  solved from every starting point over a hundred thousand boxes as well as over
  thirty-two.
- The benchmarks no longer have their report stripped by the `T20` rule of
  ruff, whose unsafe fixes silently replaced the `print` calls by `pass`.
- The equations of the documentation are rendered: MathJax is served by the
  documentation itself instead of a CDN, which a network blocking third-party
  CDNs, or a local build, left unreachable.
