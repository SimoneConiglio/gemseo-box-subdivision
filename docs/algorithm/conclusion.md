<!--
 Copyright 2026 Simone Coniglio

 This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
 International License. To view a copy of this license, visit
 http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
 Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

# Conclusion

The box-subdivision outer approximation separates the exploration of a design
space from its local exploitation: a Cartesian subdivision turns the choice of a
region into a categorical variable, a mixed-integer master decides which box to
look into from the cuts of the boxes already solved, and a local solver does the
rest inside it.

## What the method is, once measured

**It is a method for a landscape of few, well-separated basins.** Where the
subdivision resolves them, it reaches the optimum for three to five times fewer
evaluations than multistart, CMA-ES or DIRECT, and for about a quarter of the
cost of enumerating the boxes it replaces. Where it does not, it is the worst of
the four, and no setting recovers it.

**Its size is set by the binaries, not by the boxes.** The master grows as
$\sum_j m_j$ while the boxes grow as $\prod_j m_j$, so a hundred thousand boxes
over five variables is a master of fifty binaries, and that density solves
Rastrigin in five dimensions, which none of the baselines does. The limit is the
ratio between those binaries and the sub-problems a budget can pay for: past
some fifty coefficients for fifty cuts, the cut model is underdetermined and the
quality collapses.

**Two settings decide whether a run works at all**, and both fail silently when
wrong: the guard against non-convexity, the adaptive repair of the cut slopes or
the convexification constant, never both; and the trust region of the master,
which has to measure the **number of components a candidate changes** and to keep
a radius of about two. Weighing the subdivisions by their own indexes, which the
upstream design space does by default for a numeric catalogue, is not a distance
at all, and it cost this method its best result until it was found.

Of those two, the guard is the one the method should stop asking for, and a
prototype says it can: sweeping a ladder of convexity values across the parallel
probes the master already runs reaches the optimum on Rastrigin and on Ackley
from every starting point, with no value supplied at all, where no single margin
serves both. It is measured on two problems in two dimensions and it runs through
a stub, so it is a direction rather than a result, see
[annex C](tuning.md#sweeping-the-convexity-instead-of-calibrating-it).

## What is established, and what is not

Established:

- against the exhaustive enumeration of the boxes, the outer approximation
  reaches the same optimum solving about a quarter of them, at about a quarter of
  the cost;
- the sub-problem starting point and the guard against non-convexity are both
  decisive, and both fail silently when wrong;
- where the subdivision resolves the basins, the method reaches the optimum for
  three to five times fewer evaluations than multistart, CMA-ES or DIRECT;
- a subdivision fine enough to resolve them stays tractable, the master growing
  with the binaries and not with the boxes: Rastrigin in five dimensions, out of
  reach of every baseline here, is solved over $100\,000$ boxes;
- subdividing only the variables the objective is multimodal in solves a problem
  that subdividing every variable coarsely does not, and loses when the
  multimodality is spread over all of them;
- the trust region has to be **tight** and measured in components changed: a
  radius of two solves Rastrigin at five variables from every starting point,
  where the diameter of the design space reaches it from two out of six and no
  region at all from one;
- the ordinal proximity between neighbouring boxes, which the constraint appears
  to promise, is worth nothing here: measured through a stub it is as reliable
  as counting components and half again as expensive, multimodality behaving
  like a categorical choice rather than a discrete one;
- the multi-resolution encoding reaches a resolution on **fewer binaries**, two
  levels of four reaching sixteen subdivisions per component on forty binaries
  against eighty, and it is not worse at that resolution: on Styblinski-Tang,
  the problem the best flat density breaks on, it gets within $0.27$ of the
  optimum for fewer evaluations than the flat encoding that matches it. Its cost
  is a cut model additive over the digits, so fewer and wider levels beat more
  and narrower ones;
- a hierarchy of subdivisions loses to the flat method wherever a flat
  subdivision can resolve the basins, and wins on the one case it cannot, a
  basin too broad for any affordable density: on Ackley at five variables the
  deep hierarchy reaches the optimum from four starting points out of six
  against two for the flat method, both having stopped on their own criteria.

Not established:

- **anything beyond the budget each comparison was run at.** A run whose cost
  equals its budget was stopped rather than finished, and ranking two of them
  says which got further, not which is better. Where it was checked, on Ackley
  at five variables, a larger budget did change the answer, from no starting
  point reaching the optimum to two out of six, and then stopped changing it:
  both configurations end at the same evaluation whether they are allowed
  $5000$ or $10\,000$, because what binds them is their own stopping rule and
  not the budget. Every other truncated cell carries the same caveat until it is
  re-run.
- **generalization.** The constants and the number of subdivisions were tuned on
  the problems then reported. A claim about the method needs a held-out set or a
  protocol fixed in advance.
- **a rule for the number of subdivisions.** It has to follow the spacing of the
  basins rather than the dimension, and that spacing is not known a priori. The
  sweep gives a ceiling, the binaries a budget can identify, and a floor, the
  basins, but no single value serves the four problems: ten subdivisions per
  variable is the best density for three of them and the worst for the fourth.
  Estimating the spacing, from the curvature or from a first sampling, is the
  most valuable next step, and the same estimate would say which variables to
  subdivide at all.
- **the convergence guarantee of the convexification.** A run ends on the trust
  region or on the stall counter, never on the optimality test, so the guarantee
  is out of reach whatever the constant, and lifting both caps to recover it
  costs the sub-problems the method exists to save.
- **behaviour with constraints.** Every problem here is bound-constrained only.
- **the industrial case.** The method earns its complexity when a sub-problem
  costs minutes, which is the regime none of these analytic problems is in, and
  the one where the baselines that need an algebraic form cannot compete. The
  comparison with Bayesian optimization now exists, at a budget of five hundred
  evaluations, and it is the one that should worry a claim made for this method:
  EGO explores the hard multimodal cases better at that budget, returning $1.99$
  on Rastrigin at five variables where this method returns $8.57$. What is not
  counted there is EGO's own cost, a hundred times this method's on the same
  cell, which an expensive objective would invert. Establishing the method
  against it needs a case where that inversion is real, not an analytic problem
  where it is argued.

## Where this can go

Five directions follow from the measurements above, in the order in which they
would pay.

**A subdivision that follows the basins.** Everything on this page turns on the
subdivision resolving the basins of the landscape, and the method has no way of
knowing their spacing. Estimating it, from the curvature at a first sampling or
from the failures of the local solves themselves, would replace the one setting
that is tuned by hand and would say, at the same time, which variables deserve
subdividing at all.

**A convexity nobody has to calibrate.** The margin and the constant are
absolute quantities in the units of the objective, and that is the criticism this
method has not answered. Sweeping them instead of choosing them costs nothing the
master is not already paying: its parallel points are a sweep of the
trust-region radius, and the same probes can carry a ladder of convexity values,
one iteration then returning the box next door and the box across the design
space at once, with every probe that proposes nothing new redeployed a rung
higher. The prototype of `benchmarks/convexity_sweep.py` solves both
two-dimensional problems from every starting point without being given a value,
which no fixed margin does. What it needs to become a result is the iteration
loop of the master, which lives upstream, and a held-out problem: the decade of
headroom its unbounded form needs was itself chosen on the two problems it is
reported on.

**A master that keeps its cuts while the boxes change.** The hierarchies all
restart a master per node, which is what makes them lose. A master over a
**growing set of leaves**, adding binaries as a box is split and keeping every
cut, would be the genuine lazy branch-and-bound: the frontier without its cost.
It cannot be built on a catalogue design space fixed at construction, so it means
writing the master problem rather than calling it.

**A bound worth the name.** A run ends on its trust region or on its stall
counter, never on its optimality test, because the convexification degrades the
lower bound by its own constant. Reporting the bound net of a term that vanishes
at every integer point would make the gap meaningful, and a meaningful gap is
what turns the method into one that can stop on a proof rather than on a budget.

**The regime the method is for.** Every problem here is analytic and
bound-constrained, where a sub-problem costs microseconds. The method is built
for a sub-problem that costs minutes and comes with an adjoint, and for
constraints that make a box infeasible rather than merely expensive. Bayesian
optimization is now in the comparison, and at a small budget it is the method to
beat on the hardest landscapes; what the benchmark cannot show is the one thing
that would decide between them, an objective expensive enough that the cost of
fitting a surrogate stops being free. A case of that kind is what would establish
either.
