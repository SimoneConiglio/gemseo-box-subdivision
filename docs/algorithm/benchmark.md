<!--
 Copyright 2026 Simone Coniglio

 This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
 International License. To view a copy of this license, visit
 http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
 Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

# Results

This chapter reports the numerical experiments: the method against the
exhaustive enumeration of the boxes, the variants of the method, the effect of
the subdivision density and of the convexity settings, a comparison with
baselines at two budgets, and an application to a topology optimization
problem. The test problems are described in [annex A](problems.md), the
baselines in [annex B](baselines.md), and the tuning of the settings in
[annex C](tuning.md). The analytic experiments are reproduced with
`tox -e benchmark`.

:::{important}
All runs are given a fixed budget of equivalent evaluations. A run whose cost
equals the budget was stopped by the budget and not by its own convergence
criterion; its distance to the optimum is then an upper bound on what the same
configuration reaches with more evaluations. Comparisons between such runs
rank the progress made within the budget only. Cells whose cost is below the
budget correspond to runs that terminated on their own criterion. Results that
rest on truncated runs are marked as such.
:::

## Comparison with the enumeration of the boxes

The reference is the enumeration, which solves the sub-problem of every box.
It is exhaustive and parallel and requires no cuts; the outer approximation is
of interest only if it reaches the same optimum with fewer sub-problems. Both
methods solve the same main problem with the same `Benders` formulation, so
that the comparison isolates the exploration strategy.

Table 1 reports the results on the Rastrigin function in two dimensions with
$10 \times 10 = 100$ boxes. The cost is counted in executions of the objective
discipline. The normalized formulation was run from the twenty starting points
of the [comparison with the baselines](#comparison-with-the-baselines), the
constraint formulation from eight starting points of an earlier study.

| formulation | method | objective | boxes solved | executions | reached |
|-------------|--------|-----------|--------------|------------|---------|
| constraint | enumeration | $0.0$ | 100 | 1427 | |
| constraint | outer approximation | $0.0$ | 24 to 36 | 341 to 521 | 7/8 |
| normalized | enumeration | $0.0$ | 100 | 1267 | 20/20 |
| normalized | outer approximation | $0.0$ | 12 to 32 | 158 to 412 | 19/20 |

*Table 1. Enumeration and outer approximation on Rastrigin, $n = 2$: median
objective, and range over the starting points of the boxes solved and of the
executions.*

With the normalized formulation, the outer approximation reaches the optimum
from nineteen of the twenty starting points after solving 12 to 32% of the
boxes, at a median cost of $312$ executions, a quarter of that of the
enumeration. The normalized formulation is about 11% cheaper in enumeration,
since its sub-problems are bounded by the box instead of restoring feasibility
with respect to a box constraint. It is retained in the following.

## Variants of the method

The master explores the design space through two mechanisms, and the
subdivision adds a third setting:

- the number of probes, i.e. of boxes proposed per master iteration, which in
  a swept run are also the rungs of the convexity ladder;
- the upper bound of the convexity ladder, a low value keeping the master near
  the boxes favoured by its cuts and a high value moving it across the design
  space;
- the subdivision density, either fixed, proposed by counting basins, or
  obtained through the multi-resolution encoding or the deep hierarchy.

Each variant changes one of these settings with respect to the swept
configuration `SweptBoxSubdivisionSettings()`: four probes, a ladder bounded by
the spread of the objective, and ten subdivisions per variable in two
dimensions and two in five. The calibrated configuration, with a convexity
margin of $100$, is included as the reference that the sweep replaces.

The variants are compared through data profiles. For each problem a sequence of
twenty target values is defined, from a value reached early by every method down
to the global optimum. The profile of a configuration is the fraction of the
targets, over the four problems and the starting points, reached after a given
number of evaluations; the targets were generated from the five starting points
of the first study. The targets and profiles are computed with
[gemseo-benchmark](https://gitlab.com/gemseo/dev/gemseo-benchmark): the
`TargetsGenerator` uses the pooled histories of all runs of a given dimension,
variants and baselines together, so that the profiles of this section and of
the [comparison with the baselines](#comparison-with-the-baselines) share the
same targets; the `DataProfile` uses the history of each run. The budget is
$500$ equivalent evaluations per variable, a gradient counting as one
evaluation. The area under the profile, i.e. the mean fraction of targets
reached over the budget, is used to rank the variants.

```{image} ../_static/figures/variant_profiles.svg
:class: only-light
:alt: Fraction of the targets reached by each variant of the method against the evaluations spent
```

```{image} ../_static/figures/variant_profiles-dark.svg
:class: only-dark
:alt: Fraction of the targets reached by each variant of the method against the evaluations spent
```

*Figure 1. Data profiles of the variants of the method, twenty starting points.*

### Twenty starting points

Every variant is run from the twenty starting points of the
[comparison with the baselines](#comparison-with-the-baselines) and paired by
starting point with the configuration compared with them, swept with four probes
and ten subdivisions per variable. The tests are those of the
[paired tests](#paired-tests), the Holm correction running over the problems and
the variants of each dimension. The configuration was fixed beforehand, from the
[first study](#first-study-five-starting-points) below, and is kept unless a
variant is clearly better: it succeeds significantly more often on some problem,
or has a larger area with an interval excluding zero, and succeeds significantly
less often on none (`benchmarks.statistics.clearly_better`). In five variables
the variants without a mark use two subdivisions per variable, as in the first
study, and so differ from the configuration also by the density.

| variant | 2 variables: area | difference [95% CI] | success | 5 variables: area | difference [95% CI] | success |
|---|---|---|---|---|---|---|
| swept, 4 probes, 10 per variable (configuration) | $0.85$ | reference | | $0.61$ | reference | |
| swept, 4 probes, 2 per variable | — | | | $0.51$ | $-0.10$ [$-0.14$, $-0.07$] | −R −A |
| calibrated, margin 100 | $0.79$ | $-0.06$ [$-0.09$, $-0.04$] |  | $0.49$ | $-0.12$ [$-0.16$, $-0.08$] | −R −A |
| swept, 8 probes | $0.86$ | $+0.00$ [$-0.01$, $+0.01$] |  | $0.53$ | $-0.09$ [$-0.12$, $-0.05$] | −R −A |
| swept, 16 probes | $0.89$ | $+0.04$ [$+0.01$, $+0.05$] |  | $0.49$ | $-0.12$ [$-0.16$, $-0.09$] | −R −A |
| swept, 16 probes, 10 per variable¹ | — | | | $0.41$ | $-0.20$ [$-0.23$, $-0.17$] | −A |
| swept, ladder up to 30 | $0.83$ | $-0.02$ [$-0.05$, $+0.01$] |  | $0.48$ | $-0.13$ [$-0.18$, $-0.09$] | −R −A |
| swept, ladder up to 10 | $0.71$ | $-0.15$ [$-0.21$, $-0.09$] | −A | $0.46$ | $-0.15$ [$-0.19$, $-0.11$] | −R −A |
| swept, ladder up to 10, 10 per variable¹ | — | | | $0.58$ | $-0.03$ [$-0.07$, $+0.00$] | −S |
| swept, proposed density | $0.53$ | $-0.33$ [$-0.36$, $-0.29$] | −R −A | $0.18$ | $-0.43$ [$-0.46$, $-0.40$] | −R −A |
| swept, proposed density, scans free | $0.69$ | $-0.16$ [$-0.19$, $-0.13$] | −A | $0.56$ | $-0.05$ [$-0.09$, $-0.02$] | −A |
| swept, 2 levels of 4 | $0.77$ | $-0.08$ [$-0.10$, $-0.07$] | −A | $0.43$ | $-0.19$ [$-0.22$, $-0.15$] | −R −A −S |
| swept, deep hierarchy | $0.67$ | $-0.18$ [$-0.20$, $-0.17$] | −R −A | $0.57$ | $-0.04$ [$-0.07$, $-0.01$] | −R |
| swept, Euclidean, diameter¹ | $0.84$ | $-0.01$ [$-0.03$, $+0.01$] |  | $0.62$ | $+0.01$ [$-0.02$, $+0.05$] |  |
| swept, Euclidean, nearest box¹ | $0.78$ | $-0.07$ [$-0.10$, $-0.04$] |  | $0.43$ | $-0.19$ [$-0.22$, $-0.15$] | −S |

*Table 2. Area under the data profile, difference with the configuration and
its paired bootstrap interval, and the problems on which the success differs
significantly (R Rastrigin, A Ackley, S Styblinski-Tang, G Griewank; + more
often, − less often than the configuration). ¹ Ten subdivisions per variable in
both dimensions.*

No variant is clearly better in five variables: the Euclidean trust region with
the diameter schedule is the only one whose interval contains a positive
difference, $+0.01$ [$-0.02$, $+0.05$]; every variant with two subdivisions per
variable reaches the optimum of Rastrigin and Ackley significantly less often.
In two variables sixteen probes are, on the area only ($+0.04$ [$+0.01$,
$+0.05$]), with the same success on every problem. Selected among eleven on the
same starting points, this variant was run again with the configuration from
twenty new ones (`python -m benchmarks.confirm_challenger 2 probes_16`): the
difference is $+0.045$ [$+0.032$, $+0.059$], both reaching the optimum of
Rastrigin, Ackley and Styblinski-Tang from all twenty and that of Griewank from
none. Sixteen probes reach the targets sooner, not more often. In five
variables with ten subdivisions per variable, they lower the area by $0.20$
[$0.17$, $0.23$] and reach the optimum of Ackley from one starting point against
thirteen, a significant difference, so the configuration with four probes is
kept in both dimensions.

The variants take about an hour and a half on four processes, after the runs of
the comparison with the baselines:

```shell
OMP_NUM_THREADS=1 python -m benchmarks.run_statistics --variants
python -m benchmarks.statistics
python -m benchmarks.confirm_challenger 2 probes_16
python docs/figures.py variant_profiles
```

### First study, five starting points

The configuration was chosen from the following study, with the five first
starting points, on which the targets were generated.

| variant | 2 variables: area | at 250 | at 1000 | 5 variables: area | at 625 | at 2500 |
|---------|------|-----|------|------|-----|------|
| swept, 4 probes | $0.87$ | 90% | 99% | $0.51$ | 56% | 56% |
| calibrated, margin 100 | $0.83$ | 85% | 94% | $0.50$ | 54% | 54% |
| swept, 8 probes | $0.88$ | 85% | 99% | $0.52$ | 55% | 57% |
| swept, 16 probes | $0.92$ | 99% | 99% | $0.49$ | 38% | 56% |
| swept, ladder up to 30 | $0.88$ | 92% | 96% | $0.47$ | 50% | 50% |
| swept, ladder up to 10 | $0.73$ | 78% | 78% | $0.46$ | 49% | 50% |
| swept, 10 per variable | — | — | — | $0.64$ | 62% | 84% |
| swept, 10 per variable, ladder up to 10 | — | — | — | $0.63$ | 59% | 74% |
| swept, proposed density | $0.51$ | 44% | 64% | $0.19$ | 8% | 31% |
| swept, proposed density, scans free | $0.75$ | 75% | 83% | $0.58$ | 49% | 70% |
| swept, 2 levels of 4 | $0.77$ | 75% | 85% | $0.43$ | 44% | 44% |
| swept, deep hierarchy | $0.67$ | 68% | 75% | $0.60$ | 56% | 77% |
| swept, Euclidean, diameter¹ | $0.88$ | 88% | 99% | $0.61$ | 51% | 84% |
| swept, Euclidean, nearest box¹ | $0.85$ | 70% | 99% | $0.49$ | 30% | 72% |
| swept, 16 probes, 10 per variable² | — | — | — | $0.45$ | 36% | 64% |

*Table 2b. Area under the data profile and fraction of targets reached at a
quarter and at the whole budget. In two variables ten subdivisions per variable
is the default, so the corresponding rows are omitted. ¹ The Euclidean trust
region of the [usage](usage.md#euclidean-trust-region), with ten subdivisions per
variable in both dimensions, to be compared in five variables with the row
"swept, 10 per variable"; added after the others and profiled against the same
targets, rerun by `python -m benchmarks.run_late_variants`. ² Added in the same
way, in five variables only.*

**Probes.** In two variables, sixteen probes reach $99\%$ of the targets after
$250$ evaluations, against $90\%$ for four probes, and reach the optimum of
Rastrigin, Ackley and Styblinski-Tang from all starting points; this is the
highest area of Table 2b. Eight probes lie in between. In five variables with two
subdivisions per variable, the area is between $0.49$ and $0.52$ whatever the
number of probes: with two subdivisions per variable no box separates the basins
of Rastrigin or Ackley, so that the choice among boxes does not matter. The
values four, eight and sixteen avoid the degradation observed with six probes in
[annex D](extensions.md#number-of-probes).

The cost of the master is not counted in the budget. Sixteen probes with ten
subdivisions per variable in five dimensions (fifty binaries) were first
excluded from this study for their cost: with an earlier version of the master,
half of the runs had not spent their $2500$ evaluations after five hours of wall
time. With the current version a run takes from a quarter of a minute to four
minutes, and the variant was added afterwards, to Table 2 from twenty starting
points and to Table 2b against the published targets.

**Upper bound of the ladder.** A ladder bounded by $10$ gives the fastest start
in two variables, $63\%$ of the targets after $100$ evaluations against $43\%$,
but ends at $78\%$, the optimum of Ackley being missed from all starting
points. With ten subdivisions per variable in five dimensions the same bound
gives $37\%$ against $30\%$ after $250$ evaluations and ends at $74\%$ against
$84\%$. A bound of $30$ gives $92\%$ against $90\%$ after $250$ evaluations in
two variables and ends at $96\%$ against $99\%$. The low rungs propose the
neighbouring boxes, so that a ladder restricted to them converges within the
region of the starting point: speed is obtained at the expense of reliability.

**Calibrated margin.** The margin of $100$ gives a lower area than the sweep in
both dimensions, $0.83$ against $0.87$ and $0.50$ against $0.51$, and reaches
the optimum of Ackley in two variables from three starting points of five
against five.

**Density.** In five variables, ten subdivisions per variable is the best
variant, with an area of $0.64$ and a final fraction of $84\%$, the highest of
all configurations at this budget, baselines included. It reaches the optimum
of Styblinski-Tang from five starting points of five, of Ackley from three and
of Rastrigin from two; the density study of the
[next section](#density-of-the-subdivision) reached Rastrigin from all three of
its starting points, a difference that three and five starting points cannot
resolve. The deep hierarchy follows with $0.60$ and reaches the optimum of
Ackley from four starting points of five.

**Proposed density.** Counting the basins costs between $500$ evaluations
(Styblinski-Tang) and more than ten thousand (Ackley) in two variables, and
between $1250$ and about twenty-five thousand in five, which exceeds the budget
on most problems; a run charged with its scans is therefore last in both
dimensions. With the scans free of charge, the proposed density still ranks
below the fixed densities, $0.75$ against $0.87$ in two variables and $0.58$
against $0.64$ in five, the unresolved ladder of Ackley proposing more than
sixty subdivisions per variable (see [Proposed density](#proposed-density)).

**Multi-resolution encoding.** Two levels of four subdivisions give the fastest
start in both dimensions, $69\%$ of the targets after $100$ evaluations in two
variables and $42\%$ after $250$ in five, and the flattest profile afterwards,
ending at $85\%$ and $44\%$. With the convexity swept it misses the optimum of
Styblinski-Tang in five variables from all starting points, whereas the
calibrated encoding of [annex D](extensions.md#multi-resolution-encoding)
reaches it from two of twenty.

## Density of the subdivision

The number of boxes is the product of the subdivisions and grows exponentially
with the dimension, whereas the master works with the one-hot binaries, whose
number $\sum_j m_j$ grows linearly. Five variables with ten subdivisions each
give $100\,000$ boxes and $50$ binaries.

Table 3 reports the results in five variables with the `adaptive`
configuration, a budget of $2500$ and the twenty starting points of the
[comparison with the baselines](#comparison-with-the-baselines): the median
distance to the optimum, the median cost, and the number of starting points from
which the optimum is reached, when non-zero.

| $m$ | binaries | boxes | Rastrigin | Ackley | Styblinski-Tang | Griewank |
|-----|----------|-------|-----------|--------|-----------------|----------|
| 2 | 10 | $32$ | $4.98$ · 866 | $14.43$ · 674 | $0.00$ · 481 · 16/20 | $0.06$ · 1015 |
| 4 | 20 | $10^3$ | $6.70$ · 801 | $12.63$ · 1270 | $0.00$ · 749 · 19/20 | $0.22$ · 1349 |
| 10 | 50 | $10^5$ | $0.00$ · 1757 · 15/20 | $6.30$ · 2500† · 1/20 | $0.00$ · 582 · 15/20 | $0.05$ · 2500† |
| 16 | 80 | $10^6$ | $1.99$ · 1780 · 1/20 | $5.53$ · 2500† · 3/20 | $0.13$ · 864 · 10/20 | $0.06$ · 2500† |
| 24 | 120 | $8 \cdot 10^6$ | $2.86$ · 1834 · 1/20 | $8.90$ · 2500† | $0.13$ · 1122 · 8/20 | $0.08$ · 2500† |

*Table 3. Effect of the number $m$ of subdivisions per variable, $n = 5$.
† median run stopped by the budget; the distance is an upper bound.*

```{image} ../_static/figures/density.svg
:class: only-light
:alt: Effect of the subdivision density at five variables
```

```{image} ../_static/figures/density-dark.svg
:class: only-dark
:alt: Effect of the subdivision density at five variables
```

*Figure 2. Effect of the subdivision density, $n = 5$.*

With ten subdivisions per variable, the optimum of Rastrigin in five dimensions
is reached from fifteen of the twenty starting points for a median of about
$1750$ evaluations; none of the baselines reached it at the budgets tested. With
two or four subdivisions it is not reached.

The Rastrigin and Styblinski-Tang columns compare terminated runs. In the Ackley
and Griewank columns, most runs from ten subdivisions upwards were stopped by
the budget; these columns therefore rank the progress made within $2500$
evaluations and do not show which density would perform best with a larger
budget.

Beyond ten subdivisions the optimum of Rastrigin is reached from one starting
point, at sixteen and at twenty-four subdivisions, although the runs terminate
on their own criterion at a cost similar to that with ten. The cut model has $\sum_j m_j$ coefficients, and a budget
allows a few dozen cuts to identify them. A density is therefore usable as long
as the number of binaries remains below the number of sub-problems the budget
can pay for: fifty binaries are at this limit for a budget of about fifty
sub-problems, eighty are beyond it. The number of boxes does not provide this
criterion.

The density must also be sufficient to separate the minima: the basins of
Rastrigin are about one unit apart over a range of ten, which requires ten
subdivisions.

Conversely, refining well beyond the basins degrades the results.
Styblinski-Tang has two basins per variable and its optimum is reached from
fifteen to nineteen starting points with two to ten subdivisions, and from ten
and eight with sixteen and twenty-four, the latter significantly less often than
with two (exact McNemar test, $p = 0.008$).

The useful density thus lies between the one separating the basins and the one
limited by the binaries. Ten subdivisions suit Rastrigin and Styblinski-Tang,
whereas no density reaches the optimum of Ackley from more than three starting
points, nor that of Griewank from any, within this budget. The default of
`benchmarks/baselines.py` bounds the enumeration accordingly.

### Proposed density

The density can be proposed by counting the basins along jittered axial scans of
each component, as described in [the
methodology](methodology.md#estimation-of-the-subdivision-density). Each problem
of Table 4 is given four times the budget implied by its proposed density, so
that every run terminates on its own criterion; twenty starting points, median
distance and median cost.

| problem | proposed $m$ | binaries | distance | cost | reached |
| --------- | -------------- | ---------- | ----- | ------ | --------- |
| Rastrigin | 10 ×5 | 50 | $0.00$ | 1757 | 15/20 |
| Styblinski-Tang | 2 ×5 | 10 | $0.00$ | 481 | 16/20 |
| `partly_multimodal` | 10 10 1 1 1 | 20 | $0.00$ | 990 | 20/20 |
| Griewank | 19 13 11 7 9 | 59 | $0.034$ | 3631 | 0/20 |
| Ackley | 62–63 each, *unresolved* | ≈ 314 | $14.72$ | 3170 | 0/20 |

*Table 4. Proposed density, $n = 5$.*

:::{note}
The costs of Table 4 exclude the scans that determine the density, which also
evaluate the objective: about $12\,500$ evaluations on Rastrigin in five
variables, against a median of $1757$ for the run itself, $12\,525$ on Griewank and
$25\,350$ on Ackley. Charged to the budget of the [variants](#variants-of-the-method), the
proposed density ranks last in both dimensions. Table 4 measures the value of
the proposed density, not the cost of proposing it.
:::

The proposal selects ten subdivisions for Rastrigin and two for
Styblinski-Tang, which reach the optimum from fifteen and sixteen starting
points. On `partly_multimodal` the three unimodal components are left undivided,
and the optimum is reached from all starting points for a median of $990$
evaluations, against none with two subdivisions of every variable
([annex D](extensions.md#subdivision-of-a-subset-of-the-variables)).

The budget implied by the proposal, $\sum_j m_j$ sub-problems, is of the order
of the measured cost: $2000$ against a median of $1757$ on Rastrigin, $400$
against $481$ on Styblinski-Tang and $920$ against $990$ on
`partly_multimodal`.

On Ackley the basin count does not converge, and the proposed density of
sixty-three reaches the optimum from no starting point. Its ripples are one unit apart over a range
of sixty-four, so that the count is correct but the corresponding subdivision is
not useful: the global funnel, not the ripples, has to be resolved. The estimate
reports itself as unresolved before the run, which identifies the proposals to
be discarded; the same indicator directs such a problem to a hierarchy.

The estimate is based on the objective only. For a problem whose basins are
separated by non-convex constraints it returns one subdivision per component and
reports itself as converged, the objective having a single basin;
[annex D](extensions.md#constraint-aware-count) describes the
constraint-aware count and its limitations.

## Swept convexity

The results of the density study were obtained with a convexity margin chosen
for each problem, in the units of its objective. The alternative is to
[sweep the value](methodology.md#swept-convexity): the
parallel probes of the master carry a ladder of convexity values, a probe
proposing a box already solved moves to the next rung, and the upper bound of
the ladder is derived from the spread of the objective over the boxes already
solved.

Table 5 compares fixed and swept convexity on Rastrigin and Ackley in two
dimensions, whose objectives differ in scale by a factor of four, with ten
subdivisions, a budget of $1000$ and twenty starting points: median distance,
median cost and number of starting points from which the optimum is reached.

| convexity | Rastrigin, range $\approx 80$ | Ackley, range $\approx 22$ |
|-----------|-------------------------------|----------------------------|
| fixed, margin $10$ | $0.497$ · 183 · 10/20 | $3.814$ · 270 · 10/20 |
| fixed, margin $100$ | $0.000$ · 541 · 19/20 | $0.000$ · 528 · 17/20 |
| sweep, $\kappa_{\max} = 100$ | $0.000$ · 539 · 20/20 | $0.000$ · 517 · 19/20 |
| sweep, unbounded | $0.000$ · 540 · 20/20 | $0.000$ · 491 · 20/20 |

*Table 5. Fixed and swept convexity, $n = 2$.*

A margin ten times too small reaches the optimum of both problems from half of
the starting points, significantly less often than either swept configuration
(exact McNemar test, $p \le 0.004$). The margin of $100$ retained by the tuning
reaches Rastrigin and Ackley from nineteen and seventeen starting points, and
the swept configurations from all or all but one, including the unbounded one,
which is given no convexity value; these differences are not significant.

The additional rungs cost mixed-integer solves rather than evaluations, so the
swept configurations cost about as much as the calibrated one. Table 5 covers
two problems in two dimensions, on which the headroom of the unbounded form was
chosen; it does not establish a general factor. A broader comparison is given by
the [variants](#variants-of-the-method), on four problems in two and five
dimensions from twenty starting points, for the adaptive repair only. The full
table and the derivation of the bound are in
[annex C](tuning.md#swept-convexity).

## Extensions

Four extensions were evaluated at equal budget in five variables with $2500$
equivalent evaluations: the subdivision of a subset of the variables, the
multi-resolution encoding, the hierarchies of subdivisions, and the scores that
rank a box. None of them was adopted as a default. The tables are given in
[annex D](extensions.md); the findings are the following.

- Subdividing a subset of the variables improves the results when the
  multimodality is concentrated in that subset and degrades them otherwise. The
  configurations that do not subdivide exactly the multimodal variables can
  also reach the optimum, at a cost governed by the number of binaries.
- The multi-resolution encoding reduces the number of binaries for a given
  resolution, sixteen subdivisions per variable for forty binaries instead of
  eighty, but reaches the optimum less often than the flat encodings of the
  same resolution on Ackley and Styblinski-Tang. Fewer and coarser levels
  perform better than more and finer ones.
- The hierarchies address basins too broad for any affordable density: the deep
  hierarchy reaches the optimum of Ackley in five variables from twelve
  starting points of twenty, against at most four for the other configurations
  of these tables. The frontier hierarchy, the only one able to revise a
  choice, performs worst, because each node restarts a master and discards its
  cuts.
- The positional weighting of the subdivisions performs worse than the
  unweighted metric, as for the trust region.

Several of these comparisons involve runs stopped by the budget, so
[annex D](extensions.md#effect-of-the-budget) repeats the most
sensitive one at two and four times the budget. The flat subdivision then
reaches Ackley from four starting points of twenty instead of one, and the deep
hierarchy from twelve in both cases, a difference which remains significant;
beyond that, a larger budget does not change the results, both configurations
terminating on their own criteria.

## Comparison with the baselines

The method is used in the same configuration in both dimensions: swept
convexity, four probes and ten subdivisions per variable. It uses no convexity
value chosen for these problems; its density was selected on them. Every method
is run on the four problems from twenty starting points, the same for all
methods (the five of the data profiles and fifteen more), with $500$ equivalent
evaluations per variable and adjoint gradients; EGO gets the $500$ evaluations
its surrogate model can afford. Each cell of Table 6 gives the median distance
to the optimum, the median cost, and the number of starting points out of twenty
from which the optimum is reached.

| problem | $n$ | box subdivision | multistart | CMA-ES | DIRECT | tunneling | EGO‡ |
|---------|-----|-----------------|------------|--------|--------|-----------|------|
| Rastrigin | 2 | $0.00$ · 538 · 20 | $1.00$ · 1000 · 9 | $1.00$ · 625 · 4 | $0.00$ · 649 · 20 | $1.99$ · 1000 · 0 | $0.00$ · 500 · 12 |
| Ackley | 2 | $0.00$ · 575 · 20 | $0.00$ · 1000 · 12 | $0.00$ · 751 · 20 | $0.00$ · 417 · 20 | $0.00$ · 1000 · 19 | $0.32$ · 500 · 0 |
| Styblinski-Tang | 2 | $0.00$ · 348 · 20 | $0.00$ · 1000 · 20 | $0.00$ · 532 · 12 | $0.00$ · 1011 · 20 | $0.00$ · 1000 · 20 | $0.00$ · 500 · 20 |
| Griewank | 2 | $0.007$ · 628 · 0 | $0.027$ · 1000 · 1 | $0.047$ · 766 · 1 | $0.007$ · 1011 · 0 | $0.027$ · 1000 · 1 | $0.024$ · 500 · 2 |
| Rastrigin | 5 | $0.00$ · 1756 · 11 | $5.97$ · 2500 · 0 | $4.97$ · 1749 · 0 | $4.98$ · 461 · 0 | $4.97$ · 2500 · 0 | $3.99$ · 500 · 0 |
| Ackley | 5 | $0.00$ · 2500 · 13 | $9.28$ · 2500 · 0 | $0.00$ · 1921 · 19 | $0.11$ · 353 · 0 | $2.32$ · 2500 · 4 | $1.40$ · 500 · 0 |
| Styblinski-Tang | 5 | $0.00$ · 842 · 18 | $0.00$ · 2326 · 20 | $14.14$ · 1409 · 8 | $0.00$ · 2505 · 20 | $0.00$ · 2500 · 15 | $0.00$ · 500 · 20 |
| Griewank | 5 | $0.027$ · 2200 · 0 | $0.046$ · 2500 · 0 | $0.028$ · 1681 · 0 | $0.011$ · 397 · 0 | $0.070$ · 2500 · 0 | $0.064$ · 500 · 0 |

*Table 6. Box subdivision, swept with ten subdivisions per variable, and
baselines, $500$ equivalent evaluations per variable, twenty starting points.
‡ $500$ evaluations.*

```{image} ../_static/figures/results.svg
:class: only-light
:alt: Cost of the method and of each baseline on each problem, with the optima reached
```

```{image} ../_static/figures/results-dark.svg
:class: only-dark
:alt: Cost of the method and of each baseline on each problem, with the optima reached
```

*Figure 3. Cost and number of optima reached for each method and problem, from
the five starting points of the data profiles of the variants.*

### Paired tests

The runs of two methods from the same starting point are paired. The success is
compared by the exact McNemar test, a binomial test on the starting points from
which exactly one of the two reaches the optimum, and the final distance by the
Wilcoxon signed-rank test. The $p$-values of each dimension are corrected by the
Holm procedure over its four problems and five baselines. Both measures, the
final distance and the area under the data profile, were fixed before the runs.
DIRECT uses no starting point and gives the same run twenty times: against it,
the tests compare the method with a single result.

| problem | $n$ | multistart | CMA-ES | DIRECT | tunneling | EGO |
|---------|-----|------------|--------|--------|-----------|-----|
| Rastrigin | 2 | **11–0**, 0.017 | **16–0**, 0.001 | — | **20–0**, <0.001 | 8–0, 0.125 |
| Ackley | 2 | 8–0, 0.125 | — | — | 1–0, 1.000 | **20–0**, <0.001 |
| Styblinski-Tang | 2 | — | 8–0, 0.125 | — | — | — |
| Griewank | 2 | 0–1, 1.000 | 0–1, 1.000 | — | 0–1, 1.000 | 0–2, 1.000 |
| Rastrigin | 5 | **11–0**, 0.017 | **11–0**, 0.017 | **11–0**, 0.017 | **11–0**, 0.017 | **11–0**, 0.017 |
| Ackley | 5 | **13–0**, 0.005 | 0–6, 0.312 | **13–0**, 0.005 | 11–2, 0.247 | **13–0**, 0.005 |
| Styblinski-Tang | 5 | 0–2, 1.000 | 11–1, 0.076 | 0–2, 1.000 | 4–1, 1.000 | 0–2, 1.000 |
| Griewank | 5 | — | — | — | — | — |

*Table 7. Starting points from which only the method reaches the optimum – those
from which only the baseline does, and the McNemar $p$-value after Holm
correction; bold below $0.05$, — when no starting point differs.*

In five variables, the method is the only one that reaches the optimum of
Rastrigin, from eleven starting points of twenty, a significant difference with
every baseline. On Ackley it reaches it from thirteen, against none for the
multistart, DIRECT and EGO (significant), four for tunneling and nineteen for
CMA-ES (not significant). On Styblinski-Tang no difference is significant. In
two variables, the method and DIRECT reach the optimum of Rastrigin, Ackley and
Styblinski-Tang from all starting points; the method is significantly better on
Rastrigin than the multistart, CMA-ES and tunneling, and on Ackley than EGO. No
method reaches the optimum of Griewank from more than two starting points; the
final distance is significantly smaller with the method than with the multistart,
CMA-ES, tunneling and EGO in two variables, and larger than with DIRECT in five
($0.027$ against $0.011$). On Ackley in five variables, CMA-ES ends significantly
closer to the optimum. The other significant differences of final distance agree
with those of the success, or are below $10^{-4}$ between runs that both reach
the optimum.

### Data profiles

```{image} ../_static/figures/data_profiles.svg
:class: only-light
:alt: Fraction of the targets reached by the method and each baseline against the evaluations spent
```

```{image} ../_static/figures/data_profiles-dark.svg
:class: only-dark
:alt: Fraction of the targets reached by the method and each baseline against the evaluations spent
```

*Figure 4. Data profiles of the method, swept with ten subdivisions per
variable, and of the baselines, twenty starting points, against the targets of
the variants; the end of the budget of EGO is marked on its curve, tunneling is
dashed.*

| $n$ | method | area | at a tenth | at a quarter | at a half | at the budget | area difference [95% CI] |
|-----|--------|------|------------|--------------|-----------|---------------|--------------------------|
| 2 | box subdivision | $0.85$ | 32% | 86% | 98% | 99% | |
| 2 | multistart | $0.73$ | 46% | 67% | 79% | 90% | $+0.12$ [$+0.09$, $+0.15$] |
| 2 | CMA-ES | $0.72$ | 52% | 69% | 79% | 80% | $+0.13$ [$+0.08$, $+0.19$] |
| 2 | DIRECT | $0.90$ | 69% | 84% | 99% | 99% | $-0.04$ [$-0.06$, $-0.03$] |
| 2 | tunneling | $0.74$ | 55% | 68% | 79% | 87% | $+0.11$ [$+0.07$, $+0.15$] |
| 2 | EGO, 500 evaluations | — | 73% | 82% | 85% | 85%‡ | |
| 5 | box subdivision | $0.61$ | 25% | 51% | 70% | 85% | |
| 5 | multistart | $0.52$ | 40% | 50% | 56% | 61% | $+0.09$ [$+0.05$, $+0.13$] |
| 5 | CMA-ES | $0.64$ | 42% | 61% | 72% | 74% | $-0.02$ [$-0.06$, $+0.02$] |
| 5 | DIRECT | $0.76$ | 75% | 79% | 79% | 79% | $-0.15$ [$-0.18$, $-0.11$] |
| 5 | tunneling | $0.65$ | 40% | 61% | 71% | 76% | $-0.03$ [$-0.07$, $+0.01$] |
| 5 | EGO, 500 evaluations | — | 61% | — | — | 69%‡ | |

*Table 8. Area under the data profile, fraction of targets reached at a tenth, a
quarter, a half and the whole budget, and difference of the area of the method
with that of each baseline, with a bootstrap interval over the starting points,
paired across methods. ‡ At the EGO budget of $500$, which in five variables is
less than a quarter of the budget of the other methods; no area is given for
EGO.*

The area of the method is larger than those of the multistart, CMA-ES and
tunneling in two variables, and than that of the multistart in five. It is
smaller than that of DIRECT in both, which reaches the targets earlier; in five
variables the intervals against CMA-ES and tunneling contain zero. The method
has the lowest fraction of targets at a tenth of the budget in both dimensions,
and the highest at the end of the budget in five variables, $85\%$.

The last target is the global optimum on all problems in two variables and on
three of the four in five. On Griewank in five variables no run reaches the
optimum, so the last target is the best value found by any run; it compares the
methods with one another rather than with the optimum.

:::{warning}
The configuration is the same in both dimensions, but its density was selected
on the same problems, among variants measured from five starting points, which
biases the comparison in its favour. The sweep removes the convexity margin from
the settings to be tuned, but not the density. A claim on the general
performance of the method requires a separate set of test problems and a
protocol fixed in advance.
:::

The runs take a few hours with one process per core, mostly for EGO and for the
method in five variables, and resume from their cache when interrupted:

```shell
OMP_NUM_THREADS=1 python -m benchmarks.run_statistics  # runs, cached in benchmarks/.statistics
python -m benchmarks.statistics                        # writes docs/_static/statistics.json
python docs/figures.py data_profiles
```

## Comparison at a budget of 500 evaluations

The comparison above gives each method $500$ equivalent evaluations per
variable, which is large for industrial applications, and excludes Bayesian
optimization, whose cost per iteration is cubic in the number of points: an EGO
run of $500$ evaluations takes about two and a half minutes on the test machine,
against three seconds for the box subdivision. At larger budgets the comparison
would measure the overhead of the surrogate rather than the quality of the
method.

The same methods are therefore compared at a budget of $500$ evaluations, which
all of them can afford and which corresponds to an expensive objective, where a
few hundred evaluations make up the whole budget. Table 9 gives, for the four
problems in two and five dimensions and the twenty starting points of the
[comparison with the baselines](#comparison-with-the-baselines), the median
distance to the optimum and the number of starting points from which it is
reached. The box subdivision uses the configuration of that comparison, swept
with ten subdivisions per variable in both dimensions, and is compared with each
baseline by the same [paired tests](#paired-tests).

| problem | $n$ | box subdivision, swept, 10 per variable | multistart | CMA-ES | DIRECT | EGO | tunneling |
|---------|-----|-----------------------------------------|------------|--------|--------|-----|-----------|
| Rastrigin | 2 | $0.00$ · 20 | $1.00$ · 6 | $1.00$ · 4 | $0.00$ · 20 | $0.00$ · 12 | $1.99$ · 0 |
| Ackley | 2 | $0.00$ · 19 | $3.57$ · 2 | $0.00$ · 20 | $0.00$ · 20 · 417 | $0.32$ · 0 | $0.00$ · 13 |
| Styblinski-Tang | 2 | $0.00$ · 20 · 348 | $0.00$ · 20 | $0.00$ · 12 | $0.00$ · 20 | $0.00$ · 20 | $0.00$ · 20 |
| Griewank | 2 | $0.007$ · 0 | $0.053$ · 1 | $0.052$ · 1 | $0.009$ · 0 | $0.024$ · 2 | $0.027$ · 0 |
| Rastrigin | 5 | $6.47$ · 0 | $9.95$ · 0 | $11.20$ · 0 | $4.98$ · 0 · 461 | $3.99$ · 0 | $4.97$ · 0 |
| Ackley | 5 | $16.70$ · 0 | $16.30$ · 0 | $0.05$ · 0 | $0.11$ · 0 · 353 | $1.40$ · 0 | $6.09$ · 2 |
| Styblinski-Tang | 5 | $6.03$ · 10 | $7.15$ · 9 | $14.14$ · 6 | $0.00$ · 20 | $0.00$ · 20 | $14.14$ · 7 |
| Griewank | 5 | $0.440$ · 0 | $0.097$ · 0 | $0.276$ · 0 | $0.011$ · 0 · 397 | $0.064$ · 0 | $0.221$ · 0 |

*Table 9. Median distance to the optimum and number of starting points out of
twenty reaching it at a budget of $500$ evaluations; a third number is the
median cost when it is below the budget. Rerun by
`OMP_NUM_THREADS=1 python -m benchmarks.small_budget_statistics`, which writes
the runs and the tests to `docs/_static/small_budget.json`.*

In two dimensions, the box subdivision reaches the optimum of Rastrigin, Ackley
and Styblinski-Tang from twenty, nineteen and twenty starting points,
significantly more often than the multistart on Rastrigin and Ackley, than
CMA-ES and tunneling on Rastrigin, and than EGO on Ackley. In five dimensions no
method reaches the optimum of Rastrigin; the median distance is $3.99$ for EGO,
$4.97$ for tunneling, $4.98$ for DIRECT and $6.47$ for the box subdivision, and
no difference between the box subdivision and a baseline is significant. The
fifty binary variables of ten subdivisions per variable cannot be identified
with the cuts of $500$ evaluations: every run is stopped by the budget, the
optimum of Styblinski-Tang is reached from ten starting points, significantly
fewer than the twenty of DIRECT and EGO, and the final distances on Ackley are
significantly larger than with CMA-ES, DIRECT, EGO and tunneling, and on
Griewank than with the multistart, DIRECT and EGO. Rastrigin in five variables
requires the $2103$ evaluations of Table 3.

```{image} ../_static/figures/small_budget.svg
:class: only-light
:alt: Distance reached by each method at 500 evaluations, and its run time
```

```{image} ../_static/figures/small_budget-dark.svg
:class: only-dark
:alt: Distance reached by each method at 500 evaluations, and its run time
```

*Figure 5. Distance reached at $500$ evaluations (top) and run time (bottom),
from the three starting points of an earlier study. The figure shows the calibrated configuration of the box subdivision with the
default density, two subdivisions per variable in five dimensions; its run time
depends on the machine, so that a configuration timed elsewhere cannot be
added.*

The run time of EGO is about a hundred times that of the box subdivision, $444$
seconds against $3$ on Rastrigin in five dimensions in the runs of Figure 5,
and is not counted in Table 9; it becomes negligible only for an objective that
is expensive to evaluate.

Tunneling reaches the optimum of Styblinski-Tang and Ackley in two variables
from all or all but one of the twenty starting points, but not that of
Rastrigin, where it stays at a local minimum, $1.99$ from the optimum in both
Table 6 and Table 9. In five variables it reaches the optimum from four and
fifteen of the twenty starting points on Ackley and Styblinski-Tang in Table 6,
and from seven of the twenty on Styblinski-Tang in Table 9. Its area under the data
profile is $0.74$ in two variables, below the box subdivision by $0.11$, and
$0.65$ in five, where the interval of the difference with the box subdivision
contains zero (Table 8). Having no stopping rule in this setting, its runs spend the whole budget. Its
settings are fixed choices, some recalled from the literature without the
original articles at hand (see [annex B](baselines.md#tunneling)), none of them
tuned on these problems. A
run of $500$ evaluations takes about $0.2$ seconds and one of $2500$ about one
second. Both protocols are rerun by `python -m benchmarks.run_tunneling`.

Tables 6 and 9 address different situations: Table 9 the case of scarce
evaluations, typical of industrial problems, and Table 6 the case of a budget
large enough to afford the densities the box subdivision requires.

## Application to the GGP short cantilever

The analytic problems above are inexpensive, of low dimension and without
constraints. The short cantilever of
[generalized geometry projection](https://github.com/SimoneConiglio/generalized_geometry_projection)
(GGP) is a constrained problem with adjoint gradients: $18$ bars, each defined
by the position of its centre, its angle, its length, its thickness and its
density, i.e. $108$ variables, whose compliance $C$ is minimized under a volume
fraction constraint of $0.4$. As in the MATLAB implementation of the GGP paper,
the objective of the disciplines is $\log(C + 1)$; the results are given in
terms of $C$.

### Setting

The problem is solved with the preset `short_cantilever_mna` of the GGP package,
which reproduces the script `GGP_main.m` of the MATLAB implementation with the
Moving Node Approach (MNA): a cubic characteristic function of width $1$, the
volume and the stiffness weighted by $M_c$ and $M_c^3$ respectively, where
$M_c$ is the density of a bar, a lower-bound Kreisselmeier-Steinhauser
aggregation with $k_a = 10$ followed by a smooth saturation, a penalization
exponent $p = 3$ on the aggregated density with $E_{\min} = 10^{-6}$, and
bounds of $[-2\pi, 2\pi]$ on the angles. The finite element mesh has
$60 \times 30$ elements. MMA is used with the settings of `mmasub.m`: a move
limit of $0.01$ and asymptotes within $0.01$ of the current design. The initial
design is that of `GGP_main.m`, pairs of crossed bars at the nodes of a
$3 \times 3$ grid, of length $44.7$, thickness $2$ and density $0.5$.

The Python implementation was verified against a direct port of the MATLAB code:
for the same design the densities agree to $3 \cdot 10^{-8}$ and the
compliances to all reported digits, provided the bounds of the variables are
derived from the mesh nodes, as in `GGP_main.m`.

The box subdivision subdivides the pose of every bar, i.e. the coordinates of
its centre and its angle, into ten intervals, which gives $54$ subdivided
variables and $540$ binaries. The length, thickness and density are continuous
variables of each sub-problem, initialized at the values of the initial design.
The convexity is swept, the master proposes nine boxes per iteration, which are
solved in parallel, and each sub-problem is solved by MMA with at most $1800$
iterations. Parallel evaluation of the probes requires the correction of merge
request 139 of gemseo-bilevel-outer-approximation.

The multistart solves the same problem with MMA from 63 initial designs,
one per box solved by the box subdivision: the initial design of `GGP_main.m`
and 62 designs whose bar poses are drawn uniformly within the bounds,
the length, thickness and density being those of the initial design, as in the
sub-problems. Each run uses the settings above and at most $1800$ iterations,
and the runs are distributed over four processes.

The classic tunneling method of [annex B](baselines.md#tunneling) (Levy and
Montalvo, 1985), with the volume constraint kept in the tunneling phase as in
Levy and Gómez (1985), alternates
MMA minimizations of $\log(C + 1)$ under the volume constraint, the first from
the initial design of `GGP_main.m`, and MMA minimizations under the same
constraint of the tunneling function
$T(x) = (f(x) - f^*) / \left(\|x - x^*\|^{2\lambda^*}
\prod_j \|x - x_j\|^{2\lambda_0}\right)$ in the normalized variables, where
$x^*$ is the best feasible design of the last minimization, $f^*$ its value
and the $x_j$ the earlier minimizers and the mobile poles of the search. A
search starts at a distance $\varepsilon = 0.1$ of $x^*$ in a random direction
and stops at the first feasible design with $T \le 0$, from which the next
minimization starts; when its MMA run stalls above the level, a mobile pole of
strength $\lambda_0 = 1$ is placed there and the search starts again next to
it, twice at most, after which a new direction is drawn. $\lambda^*$ starts at
$1$ and is raised by $0.1$ until $T$ decreases away from $x^*$ at the starting
point, and whenever a search ends within $\varepsilon$ of $x^*$. Every MMA run
uses the settings above and at most $1800$ iterations; in the tunneling phase,
whose objective varies by orders of magnitude along a search, the KKT test of
MMA is replaced by a step shorter than $10^{-4}$, and $T$ is divided by its
magnitude at the start of each run. Four searches from the same minimizer run
in parallel, each failed one being replaced at once by a new direction, and the
first to reach the level stops the others; the minimizations run on one
process. The run stops at $56\,000$ designs, the budget of the box subdivision,
counted over all processes, the method having no other stopping rule here. The
initial strength, its increments and the strength of the mobile poles are
recalled from the literature, not verified against the original articles; the
perturbation, the number of mobile poles, the stalling step and the scaling of
$T$ are chosen here. The stalling test replaced the KKT test after trial
searches from the first minimizer, in which the KKT test ended the runs while
the compliance was still decreasing; no value was tuned on the result of the
run. The driver is `benchmarks/cantilever/classic_tunneling.py`.

### Results

| method | $C$ | $\log(C + 1)$ | designs to the best | designs evaluated |
|--------|-----|---------------|---------------------|-------------------|
| MMA from the initial design of `GGP_main.m` | $84.0$ | $4.443$ | 680 | 680 |
| multistart of MMA, 63 initial designs | $83.0$ | $4.431$ | 9967¹ | 59322 |
| box subdivision, 9 probes, 63 boxes | $82.1$ | $4.420$ | 31070 | 55995 |
| classic tunneling, 4 searches in parallel² | $82.8$ | $4.429$ | 44072 | 56000 |

*Table 10. Short cantilever: best feasible compliance, number of designs
evaluated until the best one was found, and total number of designs evaluated.
¹ Designs of the runs from initial designs 0 to 8, the best being found by
run 8; the runs are executed in parallel. ² Added after the other rows, on a
NumPy port of `GGP_main.m` rather than on the GGP preset, see below; designs
of all processes, in the order they were analysed.*

```{image} ../_static/figures/cantilever.gif
:class: only-light
:alt: Box subdivision with nine probes on the cantilever, compared with MMA from the same initial design
```

```{image} ../_static/figures/cantilever-dark.gif
:class: only-dark
:alt: Box subdivision with nine probes on the cantilever, compared with MMA from the same initial design
```

*Figure 6. Box subdivision on the short cantilever, by round of the master.
Left: the boxes of the current round during their local solutions, infeasible
designs marked with an asterisk. Right: the best feasible design so far, and the
best compliance against the number of designs evaluated by all processes,
compared with MMA from the same initial design.*

MMA from the initial design of `GGP_main.m` converges to the symmetric design
reported in the GGP paper, with $C = 84.0$. The multistart reaches $C = 83.0$
from three of its $63$ initial designs (runs 8, 62 and 34); seven runs end below
the MMA solution from the initial design of `GGP_main.m`, which is run 0, the
median run ends at $95.6$, and eight runs are stopped at $1800$ iterations. It
took $3.9$ hours of wall time on four processes, against $2.0$ hours for the box
subdivision on the same four cores. The box subdivision improves on the MMA
solution in its first box, after $349$ designs, and reaches $C = 82.1$ in its
$32$nd box, after $31\,070$ designs and about seventy minutes on four cores. The
corresponding layout is not symmetric: the lower diagonal bars meet the bottom
chord at a single node instead of crossing. The ten best of the 63 boxes have a
compliance between $82.1$ and $82.4$ and the median box $83.8$, so that the best
value is not attained by an isolated box.

Classic tunneling, run afterwards with the budget of the box subdivision,
reaches $C = 82.8$ after $44\,072$ of its $56\,000$ designs, between the
multistart ($83.0$) and the box subdivision ($82.1$). Its first minimization
reproduces the MMA run from the initial design of `GGP_main.m`, $C = 84.04$
after $671$ designs, against $680$ in the first row. It then finds nine minima,
of compliance $84.0$, $83.8$, $83.7$, $83.6$, $83.2$, $83.1$, $83.1$, $82.9$
and $82.8$, through eight successful tunnelings out of $51$ searches, $15$ of
which failed after their three MMA solutions, $24$ being stopped by a search
that reached the level and $4$ by the budget. Every successful search ends at a
design whose compliance is below the level by less than $0.01$, at a distance
between $1.2$ and $4.3$ of the minimizer in the normalized variables, from
which the next minimization descends: the tunneling phase crosses the region of
designs of nearly equal compliance rather than jumping to a lower basin, and
the descent is made by the minimizations. The $108$ variables admit equivalent
designs, the bars being interchangeable and an angle being defined up to $\pi$
on a range of $4\pi$, which the poles at the minimizers do not exclude. The
fourth tunneling took $20\,700$ designs, nearly half of the budget.

The run was made on a NumPy port of `GGP_main.m` with the settings of the
preset `short_cantilever_mna` and GEMSEO's MMA, the GGP environment with legacy
FEniCS being unavailable; this port reproduces the first row, as said above,
but is not the code of the other rows. Its wall time was $3.6$ hours, excluding
a restart of the machine after which the run resumed from its logs (the four
searches in progress were lost, their designs counted), and its
processes used about $4.7$ hours of CPU; the machine was shared with other
jobs, a
load average of $20$ on four cores at the median of its samples, so that
the wall time is not comparable with those above. The minimizations, on one
process, took $5980$ of the designs.

```{image} ../_static/figures/cantilever-tunneling.svg
:class: only-light
:alt: Best layout found by classic tunneling on the cantilever, and its best compliance against the designs analysed
```

```{image} ../_static/figures/cantilever-tunneling-dark.svg
:class: only-dark
:alt: Best layout found by classic tunneling on the cantilever, and its best compliance against the designs analysed
```

*Figure 7. Classic tunneling on the short cantilever. Left: the best design
found. Right: the best feasible compliance against the designs analysed by all
processes, with the final values of Table 10 at the designs where they were
reached. The data is in `docs/_static/cantilever_tunneling.json`.*

The result depends on the MMA settings. With a move limit of $0.1$ and
asymptotes allowed to widen, the direct port of the MATLAB code converged to
compliances between $84$ and $128$ from initial designs differing by $10^{-12}$
to $10^{-9}$; with the settings of `mmasub.m`, all these runs converged to
$84.4$. The latter settings are therefore used throughout.

:::{warning}
Each row of Tables 1 to 9 corresponds to the stated number of runs only, and
the box subdivision was configured on the problems it is evaluated on: the
density, the number of probes and, for the cantilever, the number of MMA
iterations per box. The cantilever drivers are in `benchmarks/cantilever/`; they
are run from the GGP repository, in its environment with the legacy FEniCS
version, and are not part of the test suite.
:::

The conclusions drawn from these results are discussed in
[the conclusion](conclusion.md).
