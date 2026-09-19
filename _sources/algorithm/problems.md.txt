<!--
 Copyright 2026 Simone Coniglio

 This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
 International License. To view a copy of this license, visit
 http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
 Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

# Annex A: the benchmark problems

Four classical multimodal test functions, plus one built for this package. They
are defined in `benchmarks/problems.py`, with their gradients, each checked
against central differences.

```{image} ../_static/figures/problems.png
:class: only-light
:alt: The five benchmark problems in two dimensions
```

```{image} ../_static/figures/problems-dark.png
:class: only-dark
:alt: The five benchmark problems in two dimensions
```

The bounds are deliberately **asymmetric**, so that the global minimizer is
neither at the centre of a box nor on its border, which would flatter a method
subdividing the space.

| problem | definition | bounds | global minimum |
|---------|------------|--------|----------------|
| Rastrigin | $10n + \sum_i \left(x_i^2 - 10\cos 2\pi x_i\right)$ | $[-4.1, 5.9]^n$ | $0$ at the origin |
| Ackley | $-20 e^{-0.2\sqrt{\frac1n \sum_i x_i^2}} - e^{\frac1n \sum_i \cos 2\pi x_i} + 20 + e$ | $[-28.7, 34.9]^n$ | $0$ at the origin |
| Styblinski-Tang | $\frac12 \sum_i \left(x_i^4 - 16 x_i^2 + 5 x_i\right)$ | $[-4.9, 5.1]^n$ | $-39.166 \, n$ at $x_i = -2.904$ |
| Griewank | $1 + \frac{1}{4000}\sum_i x_i^2 - \prod_i \cos \frac{x_i}{\sqrt i}$ | $[-58.1, 61.9]^n$ | $0$ at the origin |
| Partly multimodal | $\sum_{i \le 2} \left(10 + x_i^2 - 10 \cos 2\pi x_i\right) + \sum_{i > 2} x_i^2$ | $[-4.1, 5.9]^n$ | $0$ at the origin |

## What each one tests

**Rastrigin** (Rastrigin, 1974; Törn and Žilinskas, 1989) is the hard case for a subdivision: its local
minima are about **one unit apart** over a range of ten, so there are about
$10^n$ of them, and a box only holds one when the subdivision is fine.

**Ackley** (Ackley, 1987) has a single broad basin over a range of sixty,
covered with a fine ripple. A coarse box is multimodal and a fine one is almost
flat, which makes the ranking of the boxes hard for either reason.

**Styblinski-Tang** (Styblinski and Tang, 1990) has **two basins per variable**, so
$2^n$ of them, deep and well separated. This is the landscape the method is
built for, and the one it solves at the lowest cost.

**Griewank** (Griewank, 1981) is a paraboloid of range about two covered with
a product of cosines: its minima are dense but almost equal, so nothing short of
a very fine subdivision separates them, and no method of the comparison reaches
its optimum.

**Partly multimodal** is not a classical function. It is Rastrigin in the first
two variables and a paraboloid in the others, and it exists to test a subdivision
that refines **only some** of the variables, which every classical function above
makes pointless by being multimodal in all of them.

## How far apart the basins are

```{image} ../_static/figures/landscape_slice.svg
:class: only-light
:alt: A slice of three problems, normalized to a common scale
```

```{image} ../_static/figures/landscape_slice-dark.svg
:class: only-dark
:alt: A slice of three problems, normalized to a common scale
```

Rescaled to a common range, the three differ in the **spacing of their basins**
rather than in their depth, and that spacing is what the subdivision has to
resolve, see [the benchmark](benchmark.md).

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
