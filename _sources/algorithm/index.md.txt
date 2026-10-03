<!--
 Copyright 2026 Simone Coniglio

 This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
 International License. To view a copy of this license, visit
 http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
 Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

# The algorithm

The box-subdivision outer approximation is a bi-level method for multimodal
nonlinear problems. A Cartesian subdivision of the design space defines a finite
set of boxes; a mixed-integer master problem selects a box, and a local nonlinear
solver solves the original problem within it. Exploration and local optimization
are thus carried out at two distinct levels.

::::{grid} 1 2 2 2
:gutter: 3

:::{grid-item-card} Methodology
:link: methodology
:link-type: doc

Motivation, bi-level formulation, the two formulations of the sub-problem,
convexification, trust region and hierarchies.
:::

:::{grid-item-card} Implementation
:link: implementation
:link-type: doc

Components added to GEMSEO, their common one-hot layout, extensions, and two
errors that produce no warning.
:::

:::{grid-item-card} Usage
:link: usage
:link-type: doc

Construction of a GEMSEO scenario with either formulation, main settings, and
refinement of a box.
:::

:::{grid-item-card} Results
:link: benchmark
:link-type: doc

Comparison with the enumeration of the boxes and with baselines, effect of the
subdivision density and of the convexity settings, extensions, and an
application to topology optimization.
:::

:::{grid-item-card} Conclusion
:link: conclusion
:link-type: doc

Summary of the results, their limitations, and directions for further work.
:::

:::{grid-item-card} Annexes
:link: problems
:link-type: doc

Test problems, baselines, tuning of the master settings, and detailed results
of the extensions.
:::

::::

```{toctree}
:hidden:
:caption: The method

methodology
implementation
usage
benchmark
conclusion
```

```{toctree}
:hidden:
:caption: Annexes

problems
baselines
tuning
extensions
```
