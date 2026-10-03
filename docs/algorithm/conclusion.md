<!--
 Copyright 2026 Simone Coniglio

 This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
 International License. To view a copy of this license, visit
 http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
 Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

# Conclusion

The box-subdivision outer approximation separates the exploration of the design
space from local optimization. A Cartesian subdivision turns the choice of a
region into a categorical variable; a mixed-integer master selects a box from
the cuts of the boxes already solved, and a local solver solves the problem
within the selected box.

## Summary of the results

The method is suited to landscapes with a moderate number of well-separated
basins. When the subdivision separates them, it reaches the optimum with fewer
evaluations than the baselines, for instance $789$ evaluations on
Styblinski-Tang in five variables against $2340$ for the multistart and $2505$
for DIRECT, and at between a quarter and a third of the cost of the enumeration
of the boxes. When the subdivision does not separate the basins, its results are
the worst of the four methods compared, and no setting was found to compensate.

The size of the master is determined by the number of binaries rather than by
the number of boxes: the master grows as $\sum_j m_j$ whereas the number of
boxes grows as $\prod_j m_j$. One hundred thousand boxes over five variables
correspond to fifty binaries, and this density reaches the optimum of Rastrigin
in five dimensions, which none of the baselines does. The limit is the ratio
between the number of binaries and the number of sub-problems affordable within
the budget: beyond about fifty coefficients for fifty cuts the cut model is
underdetermined and the results degrade.

Two settings determined whether a run succeeded, and both fail without warning
when set incorrectly: the safeguard against non-convexity, either the adaptive
repair of the cut slopes or the convexification constant but not both, and the
trust region of the master, which must count the number of components changed by
a candidate and use a radius of about two. Weighting the subdivisions by their
indices, as the upstream design space does by default for a numeric catalogue,
does not define a distance; this default degraded the results of the method
until it was identified.

The first of these settings no longer needs to be chosen. Sweeping a ladder of
convexity values over the parallel probes of the master, without any supplied
value, reaches the same median distance to the optimum as the calibrated
configuration on all problems of the
[comparison of the variants](benchmark.md#variants-of-the-method), and reaches
it from more starting points on two of them. The density of the subdivision and
the trust region remain to be set. The sweep was evaluated on four problems in
two and five dimensions with five starting points each, which are the problems of
this study and not a separate test set. See
[the results](benchmark.md#swept-convexity) and
[annex C](tuning.md#swept-convexity).

On the short cantilever of the GGP package, a constrained problem with $108$
variables and adjoint gradients, in the setting of the MATLAB implementation of
the GGP paper, MMA from the reference initial design reaches $C = 84.0$, a
multistart of MMA from $63$ initial designs $83.0$, and the box subdivision with
nine probes and $63$ boxes $82.1$, for a comparable number of designs.

## Findings and limitations

The following findings are supported by the experiments:

- compared with the exhaustive enumeration of the boxes, the outer approximation
  reaches the same optimum after solving 20 to 36% of the boxes, at between a
  quarter and a third of the cost;
- the starting point of the sub-problems and the safeguard against
  non-convexity both determine the outcome, and both fail without warning when
  set incorrectly;
- when the subdivision separates the basins, the method requires fewer
  evaluations than multistart, CMA-ES and DIRECT, without a supplied convexity
  value: the swept configuration performs as well as the calibrated one on all
  rows of that comparison and is more reliable on two;
- a subdivision fine enough to separate the basins remains tractable, the master
  growing with the binaries and not with the boxes: the optimum of Rastrigin in
  five dimensions, not reached by any baseline, is reached with $100\,000$
  boxes;
- subdividing only the variables in which the objective is multimodal solves a
  problem that a coarse subdivision of all variables does not, and degrades the
  results when the multimodality concerns all variables;
- the density can be proposed by counting the basins along jittered axial scans.
  On all problems whose count converged, the proposal coincides with the better
  of the two fixed densities tested, and improves on both for the problem with
  unimodal components. The error of the estimate is one-sided by construction, so
  that a count that does not converge indicates an unreliable proposal; on Ackley
  this indicator identifies the proposal to discard;
- the trust region must be small and measured in components changed: a radius of
  two reaches the optimum of Rastrigin in five variables from all starting
  points, a radius equal to the diameter of the design space from two of six, and
  no trust region from one;
- the ordinal proximity between neighbouring boxes brings no improvement: an
  implementation based on it is as reliable as counting components and about
  50% more expensive, the multimodality behaving as a categorical rather than an
  ordinal choice;
- the multi-resolution encoding reaches a given resolution with fewer binaries,
  sixteen subdivisions per component with forty binaries instead of eighty,
  without degrading the results at that resolution: on Styblinski-Tang, where the
  best flat density fails, it reaches a distance of $0.27$ to the optimum with
  fewer evaluations than the equivalent flat encoding. Its cut model is additive
  over the levels, so that fewer and coarser levels perform better;
- a hierarchy of subdivisions performs worse than the flat method whenever a flat
  subdivision separates the basins, and better when a basin is too broad for any
  affordable density: on Ackley in five variables the deep hierarchy reaches the
  optimum from four starting points of six against two for the flat method, both
  terminating on their own criteria.

The following points are not established:

- Results beyond the budget of each comparison. A run whose cost equals its
  budget was stopped, and the comparison of two such runs ranks the progress made
  within the budget. On Ackley in five variables, a larger budget changed the
  result from no starting point reaching the optimum to two of six, and then no
  longer: both configurations terminate at the same evaluation with budgets of
  $5000$ and $10\,000$, being limited by their own stopping rules. The other
  truncated results remain subject to the same restriction.
- Generalization. The number of subdivisions, the trust-region radius and the
  headroom of the unbounded sweep were chosen on the problems on which they are
  reported. The convexity margin is no longer among these settings, but a claim
  on the general performance of the method requires a separate set of test
  problems or a protocol fixed in advance.
- A rule for the number of subdivisions. The density must follow the spacing of
  the basins rather than the dimension, and this spacing is not known in advance.
  The experiments give an upper limit, the number of binaries the budget can
  identify, and a lower limit, the spacing of the basins, but no single value is
  suitable for the four problems: ten subdivisions per variable is the best
  density for three of them and the worst for the fourth.
- Convergence of the convexified method. Runs terminate on the trust region or on
  the stall counter, never on the optimality test, so that the theoretical
  guarantee is not attained for any constant; removing both limits to recover it
  would require the sub-problems the method is designed to avoid.
- Behaviour with constraints. The analytic problems are bound-constrained only;
  the short cantilever is the only constrained problem, with a single volume
  constraint.
- Expensive objectives. The method is intended for sub-problems costing minutes,
  whereas the analytic problems cost microseconds per evaluation. At a budget of
  $500$ evaluations, EGO obtains better results on the hardest multimodal cases,
  $1.99$ on Rastrigin in five variables against $8.57$ for this method, at about
  a hundred times the computation time of the method, a cost that becomes
  negligible only for expensive objectives. A comparison on such an objective is
  required to conclude.

## Further work

Five directions follow from the results.

**Subdivision guided by the constraints.** Counting basins along axial scans
proposes the density and indicates which variables to subdivide, but it is based
on the objective only. For an objective such as the mass under a non-convex
constraint, the count returns one subdivision per component and reports itself
as converged, the objective having a single basin. A constraint-aware count, the
minima of $f$ restricted to each maximal feasible interval, treats disconnected
feasible sets and active-set corners with a single rule. Three difficulties
remain for stress-constrained problems: a density field is neither subdivided by
this method nor affordable to scan, which calls for a reduced parameterization;
a stress-feasible region is rarely bounded by planes normal to the design
variables, so that axial scans across an oblique boundary may overcount it or
miss it; and a singular optimum lies in a degenerate part of the feasible set of
zero volume, which no sampling of feasibility reaches.

**Convexity without calibration.** The margin and the constant are absolute
quantities in the units of the objective. The sweep removes them, and on the
variants it performs as well as the calibrated margin on all problems and better
on two. Three points remain: the headroom of the unbounded form was chosen on the
two problems of annex C and requires validation on other problems; the pure
convexification has not been swept, only the adaptive repair; and the sweep is
driven from this package because the released master does not implement it, a
workaround to be removed when `MASTER_SWEEPS_CONVEXITY` indicates that it does.

**A master that keeps its cuts when the boxes change.** The hierarchies restart a
master at each node, which explains their poor performance. A master over a
growing set of leaves, adding binaries when a box is split and keeping all cuts,
would implement a lazy branch-and-bound. It cannot be built on a catalogue
design space fixed at construction, and requires a dedicated master problem.

**A meaningful lower bound.** Runs terminate on the trust region or on the stall
counter because the convexification degrades the lower bound by its constant.
Reporting the bound without a term that vanishes at every integer point would
give a meaningful gap, and allow a run to terminate on an optimality certificate
rather than on its budget.

**Expensive constrained problems.** The method is designed for sub-problems that
cost minutes and provide adjoint gradients, and for constraints that make some
boxes infeasible. The short cantilever is a first case of this kind; at small
budgets, Bayesian optimization remains the reference on the hardest analytic
landscapes, and a comparison on an objective whose cost makes the surrogate
overhead negligible is needed to decide between the two approaches.
