<!--
 Copyright 2026 Simone Coniglio

 This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
 International License. To view a copy of this license, visit
 http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
 Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

# The algorithm

The **box-subdivision outer approximation** is a bi-level method for multimodal
non-linear problems. A Cartesian subdivision of the design space defines a
finite set of boxes; a MINLP master decides which box to look into, and a local
NLP solves the original problem inside it. Exploration and exploitation stay in
two distinct levels.

::::{grid} 1 2 2 2
:gutter: 3

:::{grid-item-card} Methodology
:link: methodology
:link-type: doc

The motivation, the bi-level formulation and its equations, the two
formulations, the convexification, the trust region and the hierarchies.
:::

:::{grid-item-card} Implementation
:link: implementation
:link-type: doc

The building blocks contributed to GEMSEO, the one-hot layout they share, the
extensions, and the two pitfalls that fail silently.
:::

:::{grid-item-card} Usage
:link: usage
:link-type: doc

Building a GEMSEO scenario with either formulation, the settings that matter,
and how a box is refined.
:::

:::{grid-item-card} Results
:link: benchmark
:link-type: doc

Against the enumeration of the boxes, against multistart, CMA-ES and DIRECT,
what the density decides, and what the extensions are worth.
:::

:::{grid-item-card} Conclusion
:link: conclusion
:link-type: doc

What the method is once measured, what is established and what is not, and the
directions that follow.
:::

:::{grid-item-card} Annexes
:link: problems
:link-type: doc

The benchmark problems, the baselines and how each is run, the sweeps that set
the settings of the master, and the extensions table by table.
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
