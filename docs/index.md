<!--
 Copyright 2026 Simone Coniglio

 This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
 International License. To view a copy of this license, visit
 http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
 Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

# gemseo-box-subdivision

gemseo-box-subdivision is a [GEMSEO](https://gemseo.org) plugin for the study of
optimization algorithms. Its algorithms are registered in the GEMSEO factories
and can be used wherever a GEMSEO algorithm name is expected, without importing
the package explicitly.

The package implements the box-subdivision outer approximation, a bi-level
method for multimodal nonlinear problems in which the exploration of the design
space and the local optimization within a region are carried out at two
distinct levels.

```{code-block} shell
pip install gemseo-box-subdivision
```

::::{grid} 1 2 2 2
:gutter: 3

:::{grid-item-card} {octicon}`beaker;1.5em;sd-mr-1` Methodology
:link: algorithm/methodology
:link-type: doc

The separation of exploration and exploitation, the bi-level formulation and
the role of the convexification.
:::

:::{grid-item-card} {octicon}`tools;1.5em;sd-mr-1` Implementation
:link: algorithm/implementation
:link-type: doc

The components, their common one-hot layout, and two errors that produce no
warning.
:::

:::{grid-item-card} {octicon}`rocket;1.5em;sd-mr-1` Usage
:link: algorithm/usage
:link-type: doc

Construction of a GEMSEO scenario with either formulation, and the main
settings.
:::

:::{grid-item-card} {octicon}`graph;1.5em;sd-mr-1` Results
:link: algorithm/benchmark
:link-type: doc

Comparison with the enumeration of the boxes, with multistart, CMA-ES, DIRECT
and EGO, and an application to topology optimization.
:::

:::{grid-item-card} {octicon}`check-circle;1.5em;sd-mr-1` Conclusion
:link: algorithm/conclusion
:link-type: doc

Summary of the results and directions for further work.
:::

::::

## Overview

The method solves

$$
\min_\alpha\ u(\alpha)
\quad \text{where} \quad
u(\alpha) = \min_x \left\{ f(x) : g(x) \le 0,\ \ell(\alpha) \le x \le u(\alpha) \right\},
$$

where a mixed-integer master problem selects a box through the one-hot vector
$\alpha$ and a local nonlinear solver solves the original problem within it.

```{image} _static/figures/solve.gif
:class: only-light
:alt: The master selecting boxes of the Rastrigin function, with the path of the local solver in each
```

```{image} _static/figures/solve-dark.gif
:class: only-dark
:alt: The master selecting boxes of the Rastrigin function, with the path of the local solver in each
```

*Figure 1. Rastrigin function in two dimensions, subdivided into $100$ boxes,
solved with the default settings. Each frame adds one box: the box selected by
the master (orange) with the path of the local solver, the boxes already solved
(blue) and the incumbent (green circle).*

In the run of Figure 1, the global optimum is found in the seventh box, after
$154$ evaluations; the run terminates on its stopping criterion after twenty
boxes and $438$ evaluations.

```{note}
The method applies to problems whose basins can be separated by a subdivision of
the design space. The subdivision must be fine enough to place the basins in
different boxes, and coarse enough for the number of binaries to remain below the
number of sub-problems the budget allows, about fifty in the experiments of this
documentation. With ten subdivisions per variable, the Rastrigin function in five
dimensions satisfies both conditions and its optimum is reached from all starting
points; with the same density, each basin of Styblinski-Tang is divided into five
boxes and the results degrade. See
[the density of the subdivision](algorithm/benchmark.md#density-of-the-subdivision).
```

```{tip}
The cuts of the outer approximation are valid only for a convex value function.
The corresponding safeguards of the master are disabled by default, in which case
a run typically terminates after two or three sub-problems far from the optimum.
Both safeguards are expressed in the units of the objective, which are generally
unknown before the run. `SweptBoxSubdivisionSettings()` requires no such value: it
assigns a ladder of convexity values to the probes of the master. In the
experiments it performs as well as the calibrated configuration on all problems
and is more reliable on two of them. See
[Usage](algorithm/usage.md#swept-convexity) and
[the results](algorithm/benchmark.md#swept-convexity).
```

```{toctree}
:hidden:

installation
algorithm/index
api
changelog
```
