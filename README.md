<!--
Copyright 2026 Simone Coniglio

This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
International License. To view a copy of this license, visit
http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

# gemseo-box-subdivision

[![PyPI](https://img.shields.io/pypi/v/gemseo-box-subdivision)](https://pypi.org/project/gemseo-box-subdivision/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/gemseo-box-subdivision)](https://pypi.org/project/gemseo-box-subdivision/)
[![PyPI - License](https://img.shields.io/pypi/l/gemseo-box-subdivision)](https://www.gnu.org/licenses/lgpl-3.0.en.html)
[![CI](https://github.com/SimoneConiglio/gemseo-box-subdivision/actions/workflows/ci.yml/badge.svg)](https://github.com/SimoneConiglio/gemseo-box-subdivision/actions/workflows/ci.yml)
[![Documentation](https://github.com/SimoneConiglio/gemseo-box-subdivision/actions/workflows/docs.yml/badge.svg)](https://simoneconiglio.github.io/gemseo-box-subdivision/)

A laboratory for exploring optimization algorithms built on
[GEMSEO](https://gemseo.org).

## Installation

```shell
pip install gemseo-box-subdivision
```

Python 3.10 to 3.13. This also installs GEMSEO and
[gemseo-bilevel-outer-approximation](https://pypi.org/project/gemseo-bilevel-outer-approximation/).

## Documentation

**<https://simoneconiglio.github.io/gemseo-box-subdivision/>**

| Page | Contents |
|------|----------|
| [Methodology](https://simoneconiglio.github.io/gemseo-box-subdivision/algorithm/methodology.html) | the bi-level problem, the cuts, the trust region, the constructions |
| [Implementation](https://simoneconiglio.github.io/gemseo-box-subdivision/algorithm/implementation.html) | the layers, the building blocks and their pitfalls |
| [Usage](https://simoneconiglio.github.io/gemseo-box-subdivision/algorithm/usage.html) | setting up each construction, and applying them to a new problem |
| [Results](https://simoneconiglio.github.io/gemseo-box-subdivision/algorithm/benchmark.html) | what is measured, against enumeration and four baselines |
| [Conclusion](https://simoneconiglio.github.io/gemseo-box-subdivision/algorithm/conclusion.html) | what is established, what is not, and where it can go |

## What it does

The package is a **GEMSEO plugin** implementing the **box-subdivision outer
approximation**, a bi-level method for multimodal non-linear problems. The design
space is cut into a Cartesian grid of boxes, which turns the choice of a region
into a categorical variable: a mixed-integer master decides which box to look
into from the cuts of the boxes already solved, and a local solver does the rest
inside it. Exploration and local exploitation stay in two distinct levels.

```python
from gemseo_box_subdivision import BoxSubdivisionScenario

scenario = BoxSubdivisionScenario(
    [objective_discipline], "f", design_space, n_subdivisions=10
)
scenario.execute()
```

The scenario owns the assembly, which is a set of invariants rather than a set of
choices: chaining the mapping before the objective, building the design space
from the same subdivision, naming the variables the master optimizes over,
selecting the formulation, and sizing the trust region. What it leaves to you is
what the measurements say decides a run.

## What is measured

On Rastrigin in two dimensions over $100$ boxes it reaches the optimum after
solving twenty to thirty-six of them, about three times cheaper than solving all
of them. In five dimensions, with ten subdivisions per variable, it reaches the
optimum from **every starting point** for $1920$ evaluations, which no
baseline here does at any budget tried.

The subdivision has to **resolve the basins** of the landscape, and it can afford
to: the master grows with the one-hot binaries, not with the boxes, so five
variables subdivided ten times each is a hundred thousand boxes and only fifty
binaries. That is the ceiling; the floor is the spacing of the basins, and
refining past them degrades the result rather than merely costing more.

Where the subdivision does not resolve the basins, other methods do better. At a
small budget, the regime this method targets, **Bayesian optimization explores
the hard multimodal cases better than it does**, at a hundred times its cost in
its own time. The
[results](https://simoneconiglio.github.io/gemseo-box-subdivision/algorithm/benchmark.html) report both sides.

## Two settings decide a run

Neither has a default that transfers between problems.

```python
from gemseo_box_subdivision import BoxSubdivisionSettings

BoxSubdivisionSettings(
    convexity_margin=80.0,  # absolute, in the units of *your* objective
    trust_region_radius=2,  # in components changed, and small
)
```

`convexity_margin` guards the outer-approximation cuts against the non-convexity
of a multimodal problem. Left unguarded, as GEMSEO's master is by default, the
cuts are invalid: the master converges after two or three sub-problems and
reports success far from the optimum. The settings pick **one** of the two
mechanisms and switch the other off, since measuring both at once measures
neither.

`trust_region_radius` counts the components a candidate box may change, every
subdivision being weighed alike. Keep it small: widening it to the diameter of
the design space loses Rastrigin at five variables, and removing the region is
worse still.

### Or let the margin sweep itself

The margin is absolute, so calibrating it is the standing criticism of the
method. The master already probes a ladder of trust-region radii per iteration,
one per parallel point; the same probes can sweep a ladder of **convexity**
values, the low rungs proposing the box next door and the high rungs the box
across the design space, with every probe that proposes nothing new redeployed a
rung higher. The user then supplies an upper bound and a number of points, or
nothing at all:

```python
from gemseo_box_subdivision import ConvexitySweepSettings

BoxSubdivisionSettings(convexity_sweep=ConvexitySweepSettings())
```

On Rastrigin and Ackley, whose objectives differ by a factor of four in scale,
that reaches the optimum from every starting point on both, which no single
margin does. The sweep itself belongs to the master, under its settings
`convexity_sweep_points` and `convexity_sweep_max`; against a master predating
them the settings fall back to the conservative end of the ladder, and the
benchmarks drive it from outside instead. See
[annex C](https://simoneconiglio.github.io/gemseo-box-subdivision/algorithm/tuning.html#sweeping-the-convexity-instead-of-calibrating-it).

## Beyond a flat subdivision

The same entry point covers the constructions, each answering one reason for a
flat subdivision to be out of reach:

```python
# Subdivide the variables the objective is multimodal in, at a density each.
BoxSubdivisionScenario([d], "f", space, n_subdivisions={"x_1": 10, "x_2": 4})

# A resolution of 4 ** 2 per component, on 4 * 2 binaries per variable.
BoxSubdivisionScenario([d], "f", space, n_subdivisions=4, levels=2)
```

and `refine_deep`, `refine_two_levels` and `refine_frontier` build hierarchies
that refine a box rather than subdividing finely.

## Development

```shell
git clone https://github.com/SimoneConiglio/gemseo-box-subdivision.git
cd gemseo-box-subdivision
python -m pip install tox tox-uv
tox -e py3.12       # tests
tox -e check        # pre-commit hooks
tox -e doc          # documentation, into docs/_build/html
tox -e benchmark    # algorithm benchmarks
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Bugs and questions

Please use the
[GitHub issue tracker](https://github.com/SimoneConiglio/gemseo-box-subdivision/issues).

## Contributors

- Simone Coniglio
