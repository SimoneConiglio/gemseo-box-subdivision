<!--
 Copyright 2026 Simone Coniglio

 This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
 International License. To view a copy of this license, visit
 http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
 Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

# Results

What the method achieves, against the exhaustive enumeration of the boxes and
against the three baselines of the problem class. The problems are described in
[one appendix](problems.md) and the baselines in [the other](baselines.md); how
the settings were arrived at is [annex C](tuning.md).

Reproduce with `tox -e benchmark`.

:::{important}
**Every selection on this page holds within its budget, and not beyond it.**
The runs are given a fixed number of equivalent evaluations, and a cell whose
cost equals that budget was **stopped by the budget rather than by its own
criterion**: its distance to the optimum is an upper bound on what the same
configuration would reach with more evaluations, not a result. Ranking two such
cells says which got further within the budget, which is a weaker statement than
which solves the problem. Cells reporting a cost below the budget did end on
their own, and those comparisons are between finished runs.

Where a conclusion here rests on a truncated run it is marked. The honest
summary is that if the goal were to solve a problem from every starting point
whatever the cost, the first thing to spend is budget, and the choices compared
here would have to be re-ranked at that larger budget.
:::


## Against the enumeration of the boxes

The reference is the **enumeration**: solving the sub-problem of every box. It is
exhaustive, embarrassingly parallel and needs no cuts, so the outer approximation
is only worth its complexity if it reaches the same optimum after substantially
fewer sub-problems. Both drive the same main problem through the same `Benders`
formulation, so the comparison isolates the exploration strategy.

Rastrigin in two dimensions, $10 \times 10 = 100$ boxes, eight starting points,
counted in **executions of the objective discipline**:

| formulation | method | objective | boxes solved | executions |
|-------------|--------|-----------|--------------|------------|
| constraint | enumeration | $0.0$ | 100 | 1427 |
| constraint | outer approximation | $0.0$ | 24 to 36 | 341 to 521 |
| normalized | enumeration | $0.0$ | 100 | 1267 |
| normalized | outer approximation | $0.0$ | 20 to 36 | 255 to 458 |

About **three times cheaper for the same optimum**, solving a quarter to a third
of the boxes. Both formulations reach the optimum from seven starting points out
of eight, so reliability no longer separates them; what does is cost. The
normalized formulation enumerates for about 11% less, its sub-problems being
bounded by their box instead of having to restore the feasibility of a box
constraint, and its cheapest outer-approximation runs are cheaper still, $255$
executions against $341$. It is therefore the one to prefer, by a small margin.

## Against the baselines

Four problems, two dimensions, three starting points, a budget of $500$
equivalent evaluations per design variable under the adjoint convention. Each
cell is the **median distance to the optimum**, the **median cost**, and the
number of starting points from which the optimum was **reached**.

| problem | $n$ | box subdivision | multistart | CMA-ES | DIRECT |
|---------|-----|-----------------|------------|--------|--------|
| Rastrigin | 2 | $0.00$ · 543 · 3/3 | $0.00$ · 1000 · 2/3 | $1.00$ · 631 · 0/3 | $0.00$ · 649 · 3/3 |
| Rastrigin | 5 | $4.98$ · 823 · 0/3 | $3.98$ · 2500 · 0/3 | $8.96$ · 1945 · 0/3 | $4.98$ · 461 · 0/3 |
| Ackley | 2 | $0.00$ · 347 · 2/3 | $0.00$ · 1000 · 3/3 | $0.00$ · 745 · 3/3 | $0.00$ · 417 · 3/3 |
| Ackley | 5 | $14.43$ · 892 · 0/3 | $9.55$ · 2500 · 0/3 | $0.00$ · 2009 · 3/3 | $0.11$ · 353 · 0/3 |
| Styblinski-Tang | 2 | $0.00$ · 218 · 3/3 | $0.00$ · 1000 · 3/3 | $0.00$ · 535 · 2/3 | $0.00$ · 1011 · 3/3 |
| Styblinski-Tang | 5 | $0.00$ · 458 · 2/3 | $0.00$ · 2340 · 3/3 | $0.00$ · 1457 · 2/3 | $0.00$ · 2505 · 3/3 |
| Griewank | 2 | $0.01$ · 607 · 0/3 | $0.01$ · 1000 · 0/3 | $0.05$ · 643 · 0/3 | $0.01$ · 1011 · 0/3 |
| Griewank | 5 | $0.06$ · 1016 · 0/3 | $0.05$ · 2500 · 0/3 | $0.03$ · 1769 · 0/3 | $0.01$ · 397 · 0/3 |

```{image} ../_static/figures/results.svg
:class: only-light
:alt: Cost of each method on each problem, with the optima reached
```

```{image} ../_static/figures/results-dark.svg
:class: only-dark
:alt: Cost of each method on each problem, with the optima reached
```

**Where it works, it is the cheapest.** Styblinski-Tang in five dimensions is
solved for $458$ evaluations, against $2340$ for multistart, $1457$ for CMA-ES
and $2505$ for DIRECT: the same answer, three to five times cheaper. In two
dimensions it is the cheapest column on three problems out of four, $543$, $347$
and $218$ evaluations, roughly half of what the next method spends.

**It is not the most reliable.** On Ackley in five dimensions CMA-ES reaches the
optimum every time and the method does not; on Griewank, DIRECT is closer at a
fraction of the cost. DIRECT is a serious baseline at low dimension, cheap and
reliable, so any claim for the method has to be made against it rather than
against multistart alone.

**The five-variable rows are the method at its default density**, two
subdivisions per variable, which bounds the enumeration and is not the best
choice for three of these four problems. At ten subdivisions per variable
Rastrigin in five dimensions is solved from every starting point for about $2100$
evaluations, which **no baseline here achieves at any budget tried**, and Ackley
and Griewank both improve as well. The next section is that sweep, and it is
where the method's case actually rests.

:::{warning}
**These numbers are measurements, not a claim of generalization.** The convexity
margin and the number of subdivisions were tuned on these very problems, and the
margin is an absolute quantity in the units of the objective, so it does not even
transfer between them unchanged. A claim about the method needs a held-out set of
problems and a protocol fixed in advance. Sweeping the margin rather than
supplying it is how a run avoids choosing that value at all, measured in
[annex C](tuning.md#sweeping-the-convexity-instead-of-calibrating-it).
:::

## At a budget every method can afford

The comparison above gives every method $500$ equivalent evaluations **per
variable**, which is generous to all of them and representative of nothing
industrial. It also excludes Bayesian optimization, whose cost per iteration is
cubic in the points gathered so far: one EGO run of $500$ evaluations takes about
two and a half minutes here against three seconds for the box subdivision, and at
the budgets above it would measure wall time rather than method quality.

So here is the same set of methods at **one budget of $500$ evaluations**, which
every one of them can afford, and which is the regime both EGO and this method
are built for: an objective costing minutes, where a few hundred evaluations is
the whole budget. Four problems, two dimensions each, three starting points, the
median distance to the optimum and the number of starting points reaching it.

| problem | $n$ | box subdivision | multistart | CMA-ES | DIRECT | EGO |
|---------|-----|-----------------|------------|--------|--------|-----|
| Rastrigin | 2 | $0.00$ · **3/3** | $0.00$ · 2/3 | $1.00$ | $0.00$ · **3/3** | $0.00$ · 2/3 |
| Ackley | 2 | $0.00$ · 2/3 | $9.58$ | $0.00$ · **3/3** | $0.00$ · **3/3** | $0.32$ |
| Styblinski-Tang | 2 | $0.00$ · **3/3** · 218 | $0.00$ · **3/3** | $0.00$ · 2/3 | $0.00$ · **3/3** | $0.29$ · 29‡ |
| Griewank | 2 | $0.007$ | $0.067$ | $0.048$ | $0.009$ | **$0.008$** |
| Rastrigin | 5 | $8.57$ | $9.95$ | $11.20$ | $4.98$ | **$1.99$** |
| Ackley | 5 | $14.43$ | $17.06$ | **$0.05$** | $0.11$ | $2.90$ |
| Styblinski-Tang | 5 | $0.00$ · 2/3 · 458 | $14.14$ · 1/3 | $0.003$ | $0.00$ · **3/3** | $0.14$ · 219‡ |
| Griewank | 5 | $0.061$ | $0.096$ | $0.381$ | **$0.011$** | $0.104$ |

```{image} ../_static/figures/small_budget.svg
:class: only-light
:alt: What each method reaches at 500 evaluations, and what it costs to run
```

```{image} ../_static/figures/small_budget-dark.svg
:class: only-dark
:alt: What each method reaches at 500 evaluations, and what it costs to run
```

The lower row is the caveat the upper one cannot show: the distance to the
optimum is measured in evaluations, and EGO's own time per run is two orders of
magnitude above every other method's. On an objective costing minutes that row
vanishes; on these it decides.

‡ EGO stopped on its own criterion, after $29$ and $219$ evaluations of the
$500$ it was allowed: its expected improvement collapses once the process models
the landscape. Every other cell of the table spent its whole budget.

**EGO is the best explorer of the hard multimodal cases at this budget**, and by
a wide margin where it matters most: on Rastrigin in five dimensions it returns
$1.99$ where the next best is DIRECT at $4.98$ and the box subdivision at
$8.57$. It also gets closest on Griewank in two dimensions. That is the result
your intuition should keep: given few evaluations and a landscape of many
basins, a surrogate over the whole history beats every method here that throws
its history away.

**It is also a hundred times more expensive in its own time**, $444$ seconds
against $3$ for the box subdivision on the same cell, and that cost is not
counted anywhere in the table. On an objective costing minutes the ratio
inverts and the table stands; on these analytic problems it does not.

**The box subdivision is the cheapest route to a solved problem where the
subdivision resolves the basins**, Styblinski-Tang at $218$ evaluations in two
dimensions and $458$ in five, both ending on their own criterion rather than on
the budget. Where it does not resolve them, five hundred evaluations is simply
too few for it: Rastrigin at five variables needs the $2103$ of the density
sweep below, and no method here solves that problem at this budget.

:::{note}
This table and the one above answer different questions, and neither supersedes
the other. This one asks which method gets furthest when evaluations are scarce,
which is the industrial case. The one above asks what each method reaches when
evaluations are plentiful, which is where the box subdivision's density can be
afforded at all.
:::

## The density of the subdivision decides

The number of boxes is the Cartesian product of the subdivisions, so it explodes
with the dimension, but the master does not see it: it sees the **one-hot
binaries**, $\sum_j m_j$, which grow linearly. Five variables with ten
subdivisions each is $100\,000$ boxes and only $50$ binaries.

Five variables, the `adaptive` configuration, a budget of $2500$, three starting
points. The median distance to the optimum, the median cost, and the number of
starting points reaching it:

| $m$ | binaries | boxes | Rastrigin | Ackley | Styblinski-Tang | Griewank |
|-----|----------|-------|-----------|--------|-----------------|----------|
| 2 | 10 | $32$ | $4.98$ · 823 | $14.43$ · 892 | $0.00$ · 458 · 2/3 | $0.06$ · 1016 |
| 4 | 20 | $10^3$ | $6.70$ · 714 | $12.63$ · 1277 | **$0.00$ · 846 · 3/3** | $0.22$ · 1547 |
| **10** | **50** | $10^5$ | **$0.00$ · 2103 · 3/3** | **$6.30$** · 2500† | $14.14$ · 598 · 1/3 | **$0.03$** · 2500† |
| 16 | 80 | $10^6$ | $1.99$ · 1706 | $12.63$ · 2500† | $0.00$ · 973 · 2/3 | $0.05$ · 2500† |
| 24 | 120 | $8 \cdot 10^6$ | $3.59$ · 1628 | $8.53$ · 2500† | $14.44$ · 1098 · 1/3 | $0.08$ · 2500† |

† stopped by the budget, so the gap is an upper bound rather than a result.

```{image} ../_static/figures/density.svg
:class: only-light
:alt: What the density of the subdivision does at five variables
```

```{image} ../_static/figures/density-dark.svg
:class: only-dark
:alt: What the density of the subdivision does at five variables
```

**Rastrigin in five dimensions is solved**, from every starting point, for about
$2100$ evaluations, which no baseline achieves at any budget tried here. That is
the headline of the whole benchmark, and it needs ten subdivisions per variable:
at two or four the problem is not solved at all.

**The Rastrigin and Styblinski-Tang columns are between finished runs**, every
cell ending below the budget, so what follows about them is a comparison of
results. **The Ackley and Griewank columns are not**: from ten subdivisions
upwards every run is stopped by the budget, so those two columns rank how far
each density got in $2500$ evaluations and say nothing about which density would
win with more. Ackley's apparent improvement with refinement is that kind of
statement and no stronger.

**There is a ceiling, and it is the binaries.** Past ten subdivisions the quality
falls away on Rastrigin, $1.99$ at sixteen and $3.59$ at twenty-four, while the
cost falls too, which is the signature of a run ending early rather than
searching harder. The cut model carries $\sum_j m_j$ coefficients and a budget
buys a few dozen cuts to identify them, so a subdivision is usable while its
**binaries stay below the sub-problems a budget can pay for**. Fifty against
about fifty is the edge; eighty is past it. This is the rule the number of boxes
never gave: $10^5$ boxes are fine and $10^6$ are not, for a reason that has
nothing to do with either figure.

**There is also a floor, and it is the basins.** The subdivision has to separate
the minima, which is why Rastrigin needs ten: its basins are about one unit apart
over a range of ten.

**And refining past the basins is not free.** Styblinski-Tang has two basins per
variable and is solved at two and four subdivisions; at ten it is not, $14.14$
and one starting point out of three. Ten subdivisions cut each of its basins into
five boxes, and a box holding no minimum of its own returns a value and a
sensitivity that say nothing about where the minimum is, so the ranking degrades.
The same reversal appears under the pure convexification and under three of the
four trust-region radii, in [annex C](tuning.md#the-density-and-the-mechanism-are-not-independent),
so it belongs to the subdivision and not to the master.

So the useful density sits between the basins and the binaries, and **no single
value serves all four problems**: ten is best for three of them and worst for the
fourth. The default of `benchmarks/baselines.py` bounds the enumeration rather
than guessing, and the density is the first thing to sweep on a new problem.

:::{note}
An earlier version of this page reported this sweep as a collapse past ten
subdivisions and concluded that densely multimodal landscapes were out of reach.
That measurement was made with the trust region of the master charging the
catalogue values of the boxes, which is not a distance; see
[annex C](tuning.md#what-the-constraint-actually-measures). The ceiling survives
the correction, the collapse does not, and Rastrigin at five variables went from
a gap of $1.00$ and two starting points out of six to a solve from all six.
:::

## The extensions, and what they are worth

Four extensions were built on top of the method and measured at equal budget,
five variables, $2500$ equivalent evaluations. None of them becomes a default,
and each says something about where the method's difficulty lies: subdividing
some variables only, the multi-resolution encoding, the hierarchies, and the
scores that rank a box. They are derived in
[the methodology](methodology.md#one-master-several-levels-the-multi-resolution-encoding)
and the sweeps behind them are in [annex C](tuning.md).

**Subdividing some variables only** wins where the multimodality is concentrated
and loses where it is not, which is the requirement of the method restated: a
variable left out keeps all of its basins inside every box. On Styblinski-Tang,
multimodal in every variable, leaving three of the five out takes a run from two
starting points out of three to none.

| subdivision of `partly_multimodal` | boxes | binaries | gap | cost | reached |
|------------------------------------|-------|----------|-----|------|---------|
| all 5 variables, $m=2$ | 32 | 10 | $1.99$ | 540 | 0/3 |
| **3 variables, $m=4$** | 64 | **12** | **$0.00$** | **773** | **3/3** |
| 2 variables, $m=10$ | 100 | 20 | **$0.00$** | 858 | **3/3** |
| 2 variables, $m=5$ | 25 | 10 | $1.99$ | 620 | 0/3 |
| 1 variable, $m=10$ | 10 | 10 | $3.98$ | 419 | 0/3 |

The cheapest configuration that works is **not** the one matching the
multimodality exactly. `partly_multimodal` is Rastrigin in two variables and a
paraboloid in three, yet splitting *three* variables into four beats splitting
the two into ten, $773$ evaluations against $858$: twelve binaries against
twenty, and the extra variable costs nothing to subdivide because it is unimodal
in every box. The binaries govern here as everywhere else.

**The multi-resolution encoding**, one categorical variable per level with the
box index read off as its base-$m$ digits, is the one construction here that
changes how many binaries a resolution costs. Five variables, three starting
points, the same budget of $2500$, median distance to the optimum:

| encoding | binaries | resolution | Rastrigin | Ackley | Styblinski-Tang |
|----------|----------|------------|-----------|--------|-----------------|
| flat, $m=10$ | 50 | 10 | **$0.00$ · 3/3** | $6.30$† | $14.14$ · 1/3 |
| flat, $m=16$ | 80 | 16 | $1.99$ | $12.63$† | **$0.00$ · 2/3** |
| levels $m=2$, $L=4$ | 40 | 16 | $2.99$† | $7.08$† | $14.44$ |
| levels $m=2$, $L=5$ | 50 | 32 | $5.25$ | $14.82$† | $14.70$ |
| **levels $m=4$, $L=2$** | **40** | **16** | $1.99$ · 1/3 | $7.40$ | **$0.27$ · 1/3** |
| levels $m=4$, $L=3$ | 60 | 64 | $3.14$ · 1/3 | **$6.28$**† | $5.67$ |
| levels $m=2$, $L=4$, positional | 40 | 16 | $7.04$† | $16.81$† | $3.68$ · 1/3 |

† stopped by the budget.

```{image} ../_static/figures/encodings.svg
:class: only-light
:alt: What the multi-resolution encoding buys, and what it costs
```

```{image} ../_static/figures/encodings-dark.svg
:class: only-dark
:alt: What the multi-resolution encoding buys, and what it costs
```

**The construction does what it claims.** Two levels of four reach a resolution
of sixteen on **forty binaries** against the eighty of the flat encoding, and at
that resolution they are not worse for it: $1.99$ against $1.99$ on Rastrigin,
with one starting point reaching the optimum where flat $m=16$ reaches none, and
$0.27$ against $0.00$ on Styblinski-Tang for **fewer evaluations**, $920$ against
$973$. The saving grows with the resolution: sixty binaries buy sixty-four
subdivisions per component, which would cost $320$ flat.

**Styblinski-Tang is where it earns its place.** That problem is the one the
density sweep breaks on: ten subdivisions per variable, the best density
elsewhere, returns $14.14$ and reaches the optimum from one starting point out of
three. Sixteen subdivisions fix it, and the cheapest way to sixteen is two levels
of four, which gets within $0.27$ of the optimum on half the binaries of the flat
encoding that matches it. Where the useful density is **above** what the binaries
can afford, this is the construction that reaches it.

**It does not rescue the problems whose difficulty is elsewhere.** On Rastrigin
nothing beats plain flat $m=10$, whose resolution the encoding was never needed
for, and on Ackley every configuration is truncated by the budget and none
reaches the optimum, the difficulty there being a basin too broad for any
resolution rather than a resolution too expensive.

**Fewer, wider levels beat more, narrower ones.** At the same resolution of
sixteen and the same forty binaries, $m=4, L=2$ beats $m=2, L=4$ on all three
problems, by $1.99$ against $2.99$, $7.40$ against $7.08$ near enough, and
$0.27$ against $14.44$. Adding levels is what makes the cut model's additivity
bind: it is linear in the one-hot variables, so it can express what a level
contributes on its own but not that a fine digit's effect depends on the coarse
digit it sits inside, and each level is another dimension over which that is
wrong. The five-level row is the worst unit row on two problems out of three.

**The positional weighting stays the wrong choice**, worst on Rastrigin and
Ackley by a wide margin, which is the trust-region metric conclusion reappearing
in a second and independent setting: weighing a subdivision by its own index
expresses a proximity the problem does not have.

**A hierarchy** was built in three shapes. The deep one reaches the optimum of
Ackley from four starting points out of six, which nothing else here does; none
of them beats the flat subdivision elsewhere.

| method | Rastrigin | Ackley | Styblinski-Tang |
|--------|-----------|--------|-----------------|
| flat $m=2$ | $4.98$ | $14.43$ | $0.00$, 5/6, 486 |
| flat $m=10$ | **$0.00$, 6/6, 1920** | $6.30$, 2500† | $0.00$, 1/6, 532 |
| two levels, by value | $4.98$ | $6.30$ | $0.00$, 5/6, 872 |
| two levels, by cuts | $2.45$ | $8.11$ | $0.00$, 5/6, 987 |
| deep, 4 levels of 2 | $4.98$ | **$0.00$, 4/6, 2387** | $0.00$, 5/6, 1494 |
| frontier, best first | $6.70$, 2500† | $9.71$, 2500† | $0.00$, **6/6**, 2500† |

† stopped by the budget. The frontier is truncated by construction, its loop
expanding boxes until the budget is spent.

```{image} ../_static/figures/extensions.svg
:class: only-light
:alt: The hierarchies against the flat subdivisions
```

```{image} ../_static/figures/extensions-dark.svg
:class: only-dark
:alt: The hierarchies against the flat subdivisions
```

Two readings the medians alone hide, and one caveat that undoes part of the
first.

The deep hierarchy **solves Ackley** at five variables, from four starting
points out of six, and it ends on its own criterion at $2387$ evaluations rather
than on the budget. The flat subdivision at the same density returns $6.30$ here,
but four of its six runs were **stopped by the budget**, so this row understates
it: given twice the budget it reaches the optimum from two starting points out of
six, and no further with more. The margin is four out of six against two, which
is [measured below](#does-more-budget-change-the-answer) rather than read off
this table.

On Styblinski-Tang every configuration solves the problem, so that panel is about
cost alone, and the flat coarse subdivision wins outright, $486$ evaluations
against $872$ to $2500$ for the hierarchies. The frontier is the only shape
reaching it from all six starting points, for five times the cost of the cheapest
that reaches five.

**The frontier**, which is the only shape able to undo a choice, is the worst of
the family on Rastrigin, $6.70$ against $4.98$ for doing nothing at all, and the
reason is not the backtracking it adds but what it costs: every node restarts a
master and throws its cuts away, so the same budget that fills one model with
fifty cuts fills ten models with five each, none of them determined enough to
rank its own children. What the flat method does instead is keep one model over
the whole subdivision and localize with its trust region, which can also widen
again.

So the hierarchies are not a default and are not a failure either. They are the
answer to one specific shape of problem, a basin too broad for any affordable
density, and the flat subdivision remains the answer everywhere else.

## Does more budget change the answer?

Several comparisons above are between runs the budget stopped, so the obvious
question is whether the rankings are properties of the method or of the number
$2500$. On the one comparison where it matters most, Ackley at five variables,
the answer is measured rather than argued. Six starting points:

| budget | flat $m=10$ | deep, 4 levels of 2 |
|--------|-------------|---------------------|
| $2500$ | $6.30$ · 2500 · 0/6 · **4 of 6 at the wall** | $0.00$ · 2387 · 4/6 · none at the wall |
| $5000$ | $5.62$ · 3306 · **2/6** · none at the wall | $0.00$ · 3093 · 4/6 · none at the wall |
| $10\,000$ | $5.62$ · 3306 · 2/6 · none at the wall | $0.00$ · 3093 · 4/6 · none at the wall |

Two things follow, and the first is a correction.

**The budget was hiding part of the flat method's result.** At $2500$ it reaches
the optimum from no starting point; given twice that, it reaches it from two out
of six. The comparison that produced "only the hierarchy solves Ackley" was
between a truncated run and a finished one, and the honest margin is **four out
of six against two**, not four against none.

**Past that, more budget buys nothing at all.** The rows at $5000$ and
$10\,000$ are *identical*, to the evaluation: both configurations stop at $3306$
and $3093$ evaluations whatever they are allowed. They end on their own caps, the
trust region shrinking to infeasibility or the stall counter firing, described in
[annex C](tuning.md#the-two-caps-that-end-a-run). So on this problem the budget
is not the binding constraint and raising it is not the way; what binds is the
stopping rule.

That is the general answer to the question, and it cuts both ways. Where a cell
reports a cost below its budget, the budget was never binding and the comparison
stands as measured, which covers most of this page, including the whole Rastrigin
column: flat $m=10$ solves it from all six starting points for $1920$ evaluations
at a budget of $2500$, of $5000$ and of $10\,000$ alike. Where a cell reports a
cost equal to its budget, the number is an upper bound and the ranking is only
"within this budget" until it is re-run, as Ackley was here.

What all of this establishes, and where it can go, is [the conclusion](conclusion.md).
