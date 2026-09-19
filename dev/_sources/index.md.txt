<!--
 Copyright 2026 Simone Coniglio

 This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
 International License. To view a copy of this license, visit
 http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
 Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

# gemseo-box-subdivision

A laboratory for exploring optimization algorithms built on
[GEMSEO](https://gemseo.org).

The package is a **GEMSEO plugin**: the algorithms it defines register
themselves in the GEMSEO factories and can be used wherever a GEMSEO algorithm
name is expected, without importing the package explicitly.

It implements the **box-subdivision outer approximation**, a bi-level method for
multimodal non-linear problems that keeps the exploration of the design space
and the local exploitation of a region in two distinct levels.

```{code-block} shell
pip install gemseo-box-subdivision
```

::::{grid} 1 2 2 2
:gutter: 3

:::{grid-item-card} {octicon}`beaker;1.5em;sd-mr-1` Methodology
:link: algorithm/methodology
:link-type: doc

Why separate exploration from exploitation, the bi-level formulation, and what
the convexification really does.
:::

:::{grid-item-card} {octicon}`tools;1.5em;sd-mr-1` Implementation
:link: algorithm/implementation
:link-type: doc

The building blocks, the one-hot layout they share, and the two pitfalls that
fail silently.
:::

:::{grid-item-card} {octicon}`rocket;1.5em;sd-mr-1` Usage
:link: algorithm/usage
:link-type: doc

Building a GEMSEO scenario with either formulation, and the settings that
matter.
:::

:::{grid-item-card} {octicon}`graph;1.5em;sd-mr-1` Results
:link: algorithm/benchmark
:link-type: doc

Four times cheaper than enumerating the boxes, measured against multistart,
CMA-ES and DIRECT, and with the convexity swept rather than supplied.
:::

:::{grid-item-card} {octicon}`check-circle;1.5em;sd-mr-1` Conclusion
:link: algorithm/conclusion
:link-type: doc

What the method is once measured, and the directions that follow from it.
:::

::::

## At a glance

On the Rastrigin function in two dimensions, subdivided into 100 boxes, the
method reaches the global optimum after solving about 20 boxes, roughly five
times cheaper than solving all of them, with nothing to tune but the
subdivision.

$$
\min_\alpha\ u(\alpha)
\quad \text{where} \quad
u(\alpha) = \min_x \left\{ f(x) : g(x) \le 0,\ \ell(\alpha) \le x \le u(\alpha) \right\}
$$

A MINLP master decides the box through the one-hot vector $\alpha$, and a local
NLP solves the original problem inside it.

```{note}
The method suits a landscape whose **basins a subdivision can separate**, and it
is the density of that subdivision that decides: it has to be fine enough to put
the basins in different boxes, and coarse enough that the binaries it costs stay
within the sub-problems a budget can pay for — around fifty in this benchmark.
Rastrigin in five dimensions sits inside that window at ten subdivisions per
variable and is solved from every starting point, which no baseline here achieves
at any budget tried; Styblinski-Tang at the same density sits outside it, its
basins cut into five boxes apiece. See
[the density of the subdivision](algorithm/benchmark.md#the-density-of-the-subdivision-decides).
```

```{tip}
**Do not calibrate the convexity: sweep it.** The cuts of the outer approximation
are valid only on a convex value function, and the master's own guards are off by
default, so a run left to them converges after two or three sub-problems and
reports success far from the optimum. Both guards are numbers in the units of
your objective, which is the one thing you do not know before the run.
`SweptBoxSubdivisionSettings()` asks for none of it and spreads a ladder of
values over the probes the master already runs: measured, it matches the
calibrated configuration on every problem of the benchmark and is more reliable
on two of them. See [Usage](algorithm/usage.md#not-choosing-the-convexity-at-all)
and [the results](algorithm/benchmark.md#sweeping-the-convexity-rather-than-supplying-it).
```

```{toctree}
:hidden:

installation
algorithm/index
api
changelog
```
