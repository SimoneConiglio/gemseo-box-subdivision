<!--
 Copyright 2026 Simone Coniglio

 This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
 International License. To view a copy of this license, visit
 http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
 Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

# Annex B: the baselines

The enumeration of the boxes measures the exploration performed by the master but
is not an alternative a practitioner would use. The comparison therefore includes
methods that address bound-constrained multimodal nonlinear problems, one for
each of the main families of the class: a restarted local solver, a stochastic
search and a deterministic partitioning method, complemented by Bayesian
optimization and by tunneling, a sequence of local solutions each started below
the level of the last minimum. They are run by `benchmarks/baselines.py`.

```{image} ../_static/figures/sampling.png
:class: only-light
:alt: Points at which each method evaluates the objective on Rastrigin
```

```{image} ../_static/figures/sampling-dark.png
:class: only-dark
:alt: Points at which each method evaluates the objective on Rastrigin
```

*Figure B.1. Points evaluated on the Rastrigin function by the box subdivision,
the multistart, CMA-ES and DIRECT.*

The sampling patterns of Figure B.1 reflect the methods: the box subdivision
concentrates its evaluations in the boxes selected by the master, the multistart
distributes local solutions over the whole space, CMA-ES contracts a search
distribution onto one basin, and DIRECT refines a lattice in the promising
regions.

## Multistart of a local solver

**Principle.** $N$ starting points are drawn in the design space, a local solver
is run from each of them, and the best result is retained. The method is the
reference of the class and the basis of the multi-level single-linkage methods
(Rinnooy Kan and Timmer, 1987), which select the starting points worth a local
solution. It converges to the global optimum with probability one as the number
of starts tends to infinity, which gives no indication for a finite budget.

**Information used.** The starting points are independent, so that a local
solution does not use the results of the previous ones. In the box subdivision,
by contrast, the master selects the next box from the cuts of all boxes already
solved.

**Implementation.** GEMSEO's `MultiStart` with $50$ starting points from its
default design of experiments and SLSQP (Kraft, 1988) as local solver. SLSQP is
also the default solver of the box-subdivision sub-problems and was used for
them in the comparison, so that the comparison concerns the choice of the
starting regions rather than their exploitation.

```python
OptimizationLibraryFactory().execute(
    problem,
    algo_name="MultiStart",
    n_start=50,
    opt_algo_settings={},        # MultiStart apportions its own budget
    doe_algo_settings={"seed": seed},
    max_iter=10000,              # the counter stops the run, not this
)
```

:::{warning}
`opt_algo_settings` must not contain `max_iter`: `MultiStart` distributes its
budget over the starts, and a `max_iter` in these settings makes it return `inf`
after zero evaluations while reporting success. The benchmark checks that every
method performs at least one evaluation and returns a finite value.
:::

## CMA-ES

**Principle.** The covariance matrix adaptation evolution strategy (Hansen and
Ostermeier, 2001) samples a population from a multivariate normal distribution
$\mathcal{N}(m, \sigma^2 C)$, ranks it, and updates the distribution towards the
better half: the mean $m$ becomes a weighted average of the selected points, the
covariance $C$ accumulates the successful search directions, and the step size
$\sigma$ is adapted from the length of the evolution path of the mean. After a
few generations the distribution is aligned with the local valley structure, as
shown in the third panel of Figure B.1.

**Information used.** Second-order information learned from the ranks only, without
gradient, which makes the method invariant to increasing transformations of the
objective. It is the best baseline on a landscape whose ripple covers a single
broad basin: on Ackley in five dimensions it reaches the optimum from all
starting points, unlike the box subdivision.

**Implementation.** The `cma` package, from the same starting point as the other
methods, with an initial standard deviation of a quarter of the range,
$\sigma_0 = (u - l)/4$, the bounds as box constraints, and the budget enforced
exactly by its `maxfevals` option.

## DIRECT

**Principle.** DIRECT, for *DIviding RECTangles* (Jones, Perttunen and Stuckey,
1993), evaluates the centre of the design space and then repeatedly divides
hyperrectangles. A rectangle $j$ with centre value $f_j$ and size $d_j$ is
potentially optimal if there exists a Lipschitz constant $\tilde K > 0$ such
that

$$
f_j - \tilde K d_j \le f_i - \tilde K d_i \quad \forall i,
\qquad
f_j - \tilde K d_j \le f_{\min} - \varepsilon \left| f_{\min} \right|,
$$

i.e. if it lies on the lower-right convex hull of the points $(d_i, f_i)$. All
potentially optimal rectangles are divided along their longest side, which
balances a global search (large rectangles) and a local search (rectangles of low
value) without choosing a Lipschitz constant. The method converges to the global
optimum of a continuous objective in the limit, by density of the samples.

**Information used.** The geometry of the design space rather than the shape of
the objective. The partition is regular and the number of rectangles grows
rapidly with the dimension, which explains its good performance in two
dimensions and its weaker performance in five.

**Implementation.** `scipy.optimize.direct`, which is deterministic and does not
use the starting point, with `maxfun` and `maxiter` set to the budget.

## EGO

Efficient global optimization (Jones, Schonlau and Welch, 1998) is used through
`egobox` (Lafage, 2022), a Rust implementation. A Gaussian process is fitted to
all evaluated points, and the next point maximizes the expected improvement,
which balances the refinement of known basins and the exploration of new
regions; the surrogate model retains the whole history of the run.

Bayesian optimization targets the same situation as the box subdivision: an
expensive objective, for which the cost of fitting a surrogate is negligible and
a few hundred evaluations make up the whole budget. A comparison at equal
numbers of evaluations on analytic problems does not account for the cost of the
method itself, which dominates on these problems: a run of $500$ evaluations
takes about two and a half minutes, against three seconds for the box
subdivision. For an expensive objective this ratio is reversed; the benchmark
does not measure this case.

The budget is enforced exactly by the number of calls, `n_doe + max_iters` with
batches of one. It is not enforced by the counter because an exception raised in
the objective of the Rust extension results in an opaque panic instead of being
propagated, as for the C extension of DIRECT. The initial design of experiments
has five points per variable and is kept below half the budget, so that the
surrogate model is used for the search.

EGO has its own stopping criterion, which is reached in practice: on
Styblinski-Tang the expected improvement vanishes once the Gaussian process
models the landscape, and the run terminates after $29$ of the $500$ allowed
evaluations, at a distance of $0.286$ from the optimum. A cost below the budget
therefore indicates termination on this criterion.

## Tunneling

**Principle.** The tunneling method (Levy and Montalvo, 1985; Levy and Gómez,
1985) alternates two phases. A *minimization* phase runs a local solver from the
current point and gives a local minimizer $x^*$ of value $f^*$. A *tunneling*
phase then looks for a point $x \neq x^*$ of the design space at the same level
or below, $f(x) \le f^*$, as a non-positive value of the tunneling function

$$
T(x) = \frac{f(x) - f^*}
{\left[(x - x^*)^T (x - x^*)\right]^{\lambda^*}
\prod_i \left[(x - x_m^i)^T (x - x_m^i)\right]^{\lambda_m}},
$$

minimized by a gradient-based solver from points perturbed around $x^*$. The
pole at $x^*$ cancels the zero of the numerator there, so that the search does
not return to the minimizer it starts from. When the search converges to a
stationary point $x_m$ of $T$ with $T(x_m) > 0$, a *mobile* pole is placed at
$x_m$ and the search starts again next to it. A point with $T \le 0$ starts the
next minimization phase, so that the sequence of minima is non-increasing,
which Levy and Montalvo call the generalized descent property.

**Information used.** The value of the best minimum found, which sets the
level the tunneling phase must reach, and the positions of that minimizer and of
the stationary points of the current tunneling search, which the poles exclude.
The minima found before are not used. Unlike the multistart, the method is
sequential and deterministic for a given set of perturbation directions.

**Implementation.** `benchmarks/tunneling.py`, with GEMSEO's SLSQP, under its
default settings, in both phases, as for the multistart and the sub-problems of
the box subdivision. The design variables are bounded, and the bounds are
handled by SLSQP in both phases. The gradient of $T$ is analytic,

$$
\nabla T = \frac{\nabla f - (f - f^*)\, \nabla \ln D}{D},
\qquad
\nabla \ln D = \sum_j 2 \lambda_j \frac{x - x_j}{\|x - x_j\|^2},
$$

with $D$ the denominator of $T$ and $x_j$ its poles, and each evaluation of $T$
or $\nabla T$ charges the evaluations of $f$ or $\nabla f$ it needs, at most one
of each per point, to the same budgeted counter as the other methods. The
settings are the same on every problem and were not tuned:

| setting | value | source |
|---------|-------|--------|
| form of $T$, pole at $x^*$, mobile poles | as above | Levy and Montalvo (1985) |
| initial strength $\lambda^*$ | $1$, the order of the zero of $f - f^*$ at a non-degenerate minimizer | recalled from Levy and Montalvo (1985), not verified |
| increase of $\lambda^*$ | by $0.1$ until $\nabla T \cdot (x_0 - x^*) < 0$ at the starting point $x_0$, at most $10$ | recalled from Levy and Montalvo (1985), not verified; the cap is chosen here |
| strength $\lambda_m$ of a mobile pole | $1$ | recalled from Levy and Montalvo (1985), not verified |
| perturbation of $x^*$ or $x_m$ | $1\%$ of the range of each variable, in a random direction, reflected into the bounds | chosen here |
| mobile poles per tunneling search | $n$, after which a new direction is drawn | chosen here |
| tunneling searches per minimizer | no limit, the run stopping at the budget | chosen here, see below |
| acceptance of a tunneling point | $f(x) < f^*$, as soon as it is evaluated | $T \le 0$ of Levy and Montalvo, made strict |

The rows marked *recalled* were taken from the descriptions of the method as
remembered when it was implemented: neither the original articles nor a
secondary source giving these values could be consulted from the environments
in which the baseline was written and reviewed, so that they are to be checked
against the text. Only the form of $T$, its poles and the alternation of the
two phases are certain. The method's
own stopping rule ends a run when every tunneling search from a minimizer has
failed, after a fixed number of searches. The benchmark sets no such number, so
that the run stops at its budget like the other methods. With two searches per
variable, run apart as a check of sensitivity, the distances of Tables 6 and 8
are unchanged except on Griewank in five variables, $0.160$ instead of
$0.123$, while the median costs of the two-dimensional runs of Table 6 fall to
between $477$ and $603$ evaluations of their $1000$.

**On the cantilever.** The constrained short cantilever of the
[application](benchmark.md#application-to-the-ggp-short-cantilever) is solved
by the same method with MMA in both phases, the volume constraint kept in the
tunneling phase as in Levy and Gómez (1985), poles at every minimizer found,
and four searches in parallel; its settings, and where they depart from these,
are given there.

**Variant of Zhang and Norato.** Zhang and Norato (2018) combine a
gradient-based tunneling method with the geometry projection method in topology
optimization, and a later article reports that they adapted the method of moving
asymptotes to it (Papadopoulos, Farrell and Surowiec, 2021). Their tunneling
function, the type and strength of their poles, their treatment of the
constraints and their stopping rules could not be verified from an accessible
source, and this variant is therefore not implemented.

## Summary of the methods

| | multistart | CMA-ES | DIRECT | EGO | tunneling | box subdivision |
|---|---|---|---|---|---|---|
| gradient | yes, in each local solution | no | no | no | yes, in both phases | yes, in each sub-problem |
| stochastic | starting points | yes | no | initial design | perturbation directions | no |
| use of past evaluations | none | covariance | partition | surrogate over all points | best level, current poles | cuts of all solved boxes |
| asymptotic guarantee | infinitely many starts | none | dense sampling | dense sampling | none | not attained, see [annex C](tuning.md#termination-of-the-runs) |
| parallelism | starts | population | potentially optimal rectangles | batch of the acquisition | tunneling searches | boxes of an iteration |
| own cost per iteration | negligible | negligible | negligible | cubic in the number of points | negligible | one mixed-integer solution |
| intended use | few basins, inexpensive objective | rippled landscapes, no gradient | low dimension | expensive objective, small budget | escaping a local minimum with gradients | expensive sub-problem with adjoint |

*Table B.1. Characteristics of the compared methods.*

EGO and the box subdivision are designed for the same situation, which makes
their comparison the most informative, subject to the difference in their own
computational cost.

## Budget accounting

A method using gradients cannot be compared with a derivative-free method on the
number of objective evaluations alone, since the gradient carries information at
a cost. The budget is therefore counted in equivalent evaluations, under two
conventions that bound the actual cost:

| convention | cost of a gradient | corresponding case |
|------------|--------------------|--------------------|
| adjoint | $1$ evaluation | an adjoint is available, the target case of the method |
| finite differences | $n$ evaluations | black-box objective |

*Table B.2. Conventions for the cost of a gradient.*

CMA-ES and DIRECT do not depend on the convention. The budget is $500$
equivalent evaluations per design variable, since a fixed budget would favour,
in low dimension, the method converging fastest there.

The objective and its gradient are wrapped in a counter that raises an exception
as soon as the budget is spent, which stops the run:

```python
class BudgetedCounter(Counter):
    def objective(self, x):
        if self.cost(self.__dimension, self.__adjoint) >= self.__budget:
            raise BudgetExceededError
        return super().objective(x)
```

This works for the methods driven from Python but not for those called from a C
extension, where the exception results in a `SystemError`. CMA-ES and DIRECT are
therefore limited by their own `maxfevals` and `maxfun` options. DIRECT completes
its current iteration and exceeds the budget by about one percent, $1011$
evaluations for a budget of $1000$, which the budget test tolerates.

## Methods not included

Relaxation-based global solvers such as BARON, SCIP, Couenne or Alpine build
convex relaxations from the algebraic form of the problem. The sub-problem of an
industrial application, a disciplinary optimization or a multidisciplinary
analysis, has no such form; these solvers are relevant for polynomial programs
but not for the problems considered here.

Basin hopping, particle swarm optimization and simulated annealing are variants
of the families already represented, restarted local solvers and stochastic
searches, and are not expected to change the comparison.

## References

- Rinnooy Kan, A. H. G., & Timmer, G. T. (1987). *Stochastic global optimization
  methods. Part II: Multi level methods.* Mathematical Programming, 39(1), 57-78.
- Kraft, D. (1988). *A software package for sequential quadratic programming.*
  DFVLR-FB 88-28, DLR German Aerospace Center.
- Hansen, N., & Ostermeier, A. (2001). *Completely derandomized self-adaptation in
  evolution strategies.* Evolutionary Computation, 9(2), 159-195.
- Hansen, N. (2016). *The CMA evolution strategy: a tutorial.* arXiv:1604.00772.
- Jones, D. R., Schonlau, M., & Welch, W. J. (1998). *Efficient global
  optimization of expensive black-box functions.* Journal of Global Optimization,
  13(4), 455-492.
- Lafage, R. (2022). *egobox, a Rust toolbox for efficient global optimization.*
  Journal of Open Source Software, 7(78), 4737.
- Jones, D. R., Perttunen, C. D., & Stuckey, B. E. (1993). *Lipschitzian
  optimization without the Lipschitz constant.* Journal of Optimization Theory
  and Applications, 79(1), 157-181.
- Virtanen, P., et al. (2020). *SciPy 1.0: fundamental algorithms for scientific
  computing in Python.* Nature Methods, 17, 261-272.
- Levy, A. V., & Montalvo, A. (1985). *The tunneling algorithm for the global
  minimization of functions.* SIAM Journal on Scientific and Statistical
  Computing, 6(1), 15-29.
- Levy, A. V., & Gómez, S. (1985). *The tunneling method applied to global
  optimization.* In P. T. Boggs, R. H. Byrd & R. B. Schnabel (Eds.), Numerical
  Optimization 1984 (pp. 213-244). SIAM.
- Zhang, S., & Norato, J. A. (2018). *Finding better local optima in topology
  optimization via tunneling.* ASME IDETC/CIE 2018, DETC2018-86116.
- Papadopoulos, I. P. A., Farrell, P. E., & Surowiec, T. M. (2021). *Computing
  multiple solutions of topology optimization problems.* SIAM Journal on
  Scientific Computing, 43(3), A1555-A1582; preprint 2021-03 of the
  Mathematical Institute, University of Oxford.
- Gallard, F., et al. (2018). *GEMS: a Python library for automation of
  multidisciplinary design optimization process generation.* AIAA/ASCE/AHS/ASC
  Structures, Structural Dynamics, and Materials Conference.
