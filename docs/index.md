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

Four times cheaper than enumerating the boxes, and measured against multistart,
CMA-ES and DIRECT.
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
times cheaper than solving all of them.

$$
\min_\alpha\ u(\alpha)
\quad \text{where} \quad
u(\alpha) = \min_x \left\{ f(x) : g(x) \le 0,\ \ell(\alpha) \le x \le u(\alpha) \right\}
$$

A MINLP master decides the box through the one-hot vector $\alpha$, and a local
NLP solves the original problem inside it.

```{note}
The method suits a landscape with a **moderate number of basins**: the
subdivision has to resolve them. On a densely multimodal problem, such as
Rastrigin beyond two dimensions, no tractable subdivision does, and an evolution
strategy does better. See [the benchmark](algorithm/benchmark.md).
```

```{warning}
The convexification constant defaults to `0.0` in GEMSEO, which makes the
outer-approximation cuts invalid on a multimodal problem: the master converges
after two or three sub-problems and reports success far from the optimum. Read
[Convexification](algorithm/methodology.md#convexification) before using the
method.
```

```{toctree}
:hidden:

installation
algorithm/index
api
changelog
```
