<!--
 Copyright 2026 Simone Coniglio

 This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
 International License. To view a copy of this license, visit
 http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
 Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

# Annex A: the benchmark problems

The analytic experiments use four classical multimodal test functions and one
function defined for this package. They are implemented in
`benchmarks/problems.py` together with their gradients, which were verified
against central finite differences.

```{image} ../_static/figures/problems.png
:class: only-light
:alt: The five benchmark problems in two dimensions
```

```{image} ../_static/figures/problems-dark.png
:class: only-dark
:alt: The five benchmark problems in two dimensions
```

*Figure A.1. The five test problems in two dimensions.*

The bounds are asymmetric, so that the global minimizer lies neither at the
centre nor on the boundary of a box, which would favour a method based on a
subdivision of the design space.

| problem | definition | bounds | global minimum |
|---------|------------|--------|----------------|
| Rastrigin | $10n + \sum_i \left(x_i^2 - 10\cos 2\pi x_i\right)$ | $[-4.1, 5.9]^n$ | $0$ at the origin |
| Ackley | $-20 e^{-0.2\sqrt{\frac1n \sum_i x_i^2}} - e^{\frac1n \sum_i \cos 2\pi x_i} + 20 + e$ | $[-28.7, 34.9]^n$ | $0$ at the origin |
| Styblinski-Tang | $\frac12 \sum_i \left(x_i^4 - 16 x_i^2 + 5 x_i\right)$ | $[-4.9, 5.1]^n$ | $-39.166 \, n$ at $x_i = -2.904$ |
| Griewank | $1 + \frac{1}{4000}\sum_i x_i^2 - \prod_i \cos \frac{x_i}{\sqrt i}$ | $[-58.1, 61.9]^n$ | $0$ at the origin |
| Partly multimodal | $\sum_{i \le 2} \left(10 + x_i^2 - 10 \cos 2\pi x_i\right) + \sum_{i > 2} x_i^2$ | $[-4.1, 5.9]^n$ | $0$ at the origin |

*Table A.1. Definitions, bounds and global minima.*

## Characteristics of the problems

The Rastrigin function (Rastrigin, 1974; Törn and Žilinskas, 1989) has local
minima about one unit apart over a range of ten, i.e. about $10^n$ minima; a box
contains a single minimum only when the subdivision is fine.

The Ackley function (Ackley, 1987) has a single broad basin over a range of
sixty, with a fine ripple superimposed. A coarse box is multimodal and a fine box
is almost flat, so that the ranking of the boxes is difficult in both cases.

The Styblinski-Tang function (Styblinski and Tang, 1990) has two deep and well
separated basins per variable, i.e. $2^n$ basins. This is the type of landscape
for which the method is designed, and the problem it solves at the lowest cost.

The Griewank function (Griewank, 1981) is a paraboloid of range about two with a
product of cosines superimposed. Its minima are dense and of almost equal value,
so that only a very fine subdivision separates them; no method of the comparison
reaches its optimum.

The partly multimodal function is the Rastrigin function in the first two
variables and a paraboloid in the others. It is used to evaluate a subdivision of
a subset of the variables, which is of no use for the classical functions, all
multimodal in every variable.

## Spacing of the basins

```{image} ../_static/figures/landscape_slice.svg
:class: only-light
:alt: A slice of three problems, normalized to a common scale
```

```{image} ../_static/figures/landscape_slice-dark.svg
:class: only-dark
:alt: A slice of three problems, normalized to a common scale
```

*Figure A.2. One-dimensional slices of three problems, normalized to a common
range.*

After normalization to a common range, the three problems of Figure A.2 differ in
the spacing of their basins rather than in their depth. This spacing determines
the subdivision required, see [the results](benchmark.md).

## References

- Rastrigin, L. A. (1974). *Systems of Extremal Control.* Nauka, Moscow.
- Törn, A., & Žilinskas, A. (1989). *Global Optimization.* Lecture Notes in
  Computer Science 350, Springer.
- Ackley, D. H. (1987). *A Connectionist Machine for Genetic Hillclimbing.*
  Kluwer Academic Publishers.
- Styblinski, M. A., & Tang, T.-S. (1990). *Experiments in nonconvex optimization:
  stochastic approximation with function smoothing and simulated annealing.*
  Neural Networks, 3(4), 467-483.
- Griewank, A. O. (1981). *Generalized descent for global optimization.* Journal
  of Optimization Theory and Applications, 34(1), 11-39.
- Jamil, M., & Yang, X.-S. (2013). *A literature survey of benchmark functions
  for global optimization problems.* International Journal of Mathematical
  Modelling and Numerical Optimisation, 4(2), 150-194.
