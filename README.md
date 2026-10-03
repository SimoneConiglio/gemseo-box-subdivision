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

gemseo-box-subdivision is a [GEMSEO](https://gemseo.org) plugin for the study of
optimization algorithms.

## Installation

```shell
pip install gemseo-box-subdivision
```

Python versions 3.10 to 3.13 are supported. GEMSEO and
[gemseo-bilevel-outer-approximation](https://pypi.org/project/gemseo-bilevel-outer-approximation/)
are installed as dependencies.

## Documentation

**<https://simoneconiglio.github.io/gemseo-box-subdivision/>**

| page | contents |
|------|----------|
| [Methodology](https://simoneconiglio.github.io/gemseo-box-subdivision/algorithm/methodology.html) | bi-level problem, cuts, trust region, extensions |
| [Implementation](https://simoneconiglio.github.io/gemseo-box-subdivision/algorithm/implementation.html) | architecture, components and their verification |
| [Usage](https://simoneconiglio.github.io/gemseo-box-subdivision/algorithm/usage.html) | configuration of each construction and application to a new problem |
| [Results](https://simoneconiglio.github.io/gemseo-box-subdivision/algorithm/benchmark.html) | comparison with the enumeration of the boxes and with baselines, application to topology optimization |
| [Conclusion](https://simoneconiglio.github.io/gemseo-box-subdivision/algorithm/conclusion.html) | summary, limitations and further work |

## Method

The package implements the box-subdivision outer approximation, a bi-level
method for multimodal nonlinear problems. The design space is divided into a
Cartesian grid of boxes, which turns the choice of a region into a categorical
variable: a mixed-integer master selects a box from the cuts of the boxes already
solved, and a local solver solves the problem within it.

```python
from gemseo_box_subdivision import BoxSubdivisionScenario

scenario = BoxSubdivisionScenario(
    [objective_discipline], "f", design_space, n_subdivisions=10
)
scenario.execute()
```

The scenario performs the assembly: it chains the mapping before the objective,
builds the design space from the same subdivision, names the variables of the
master, selects the formulation and sets the trust region.

## Results

On the Rastrigin function in two dimensions with $100$ boxes, the method reaches
the optimum after solving 20 to 36 boxes, at about one third of the cost of
solving all of them. In five dimensions, with ten subdivisions per variable, it
reaches the optimum from all starting points for $1920$ evaluations; none of the
baselines reaches it at the budgets tested.

The subdivision must separate the basins of the landscape. The master grows with
the number of one-hot binaries and not with the number of boxes, so that five
variables with ten subdivisions each give one hundred thousand boxes and fifty
binaries. The number of binaries the budget can identify limits the density from
above, the spacing of the basins from below, and refining beyond the basins
degrades the results.

When the subdivision does not separate the basins, other methods perform better.
At small budgets, Bayesian optimization gives better results on the hardest
multimodal problems, at about a hundred times the computation time of the method.
On the short cantilever of the GGP package, a constrained problem with $108$
variables and adjoint gradients, the method reaches a compliance of $82.1$,
against $84.0$ for MMA from the reference initial design and $83.0$ for a
multistart of MMA with the same number of local solutions. See the [results].

[results]: https://simoneconiglio.github.io/gemseo-box-subdivision/algorithm/benchmark.html

## Main settings

Two settings have no default value that transfers between problems:

```python
from gemseo_box_subdivision import BoxSubdivisionSettings

BoxSubdivisionSettings(
    convexity_margin=80.0,  # absolute, in the units of the objective
    trust_region_radius=2,  # in number of changed components
)
```

`convexity_margin` protects the outer-approximation cuts against the
non-convexity of a multimodal problem. Without protection, which is the default
of the GEMSEO master, the cuts are invalid: the master converges after two or
three sub-problems and reports success far from the optimum. The settings select
one of the two available mechanisms and disable the other.

`trust_region_radius` is the number of components a candidate box may change,
all intervals having the same weight. It should be small: a radius equal to the
diameter of the design space fails on Rastrigin in five variables, and no trust
region gives worse results.

### Swept convexity

Since the margin is absolute, it has to be calibrated for each problem. The
master already probes a ladder of trust-region radii at each iteration, one per
parallel point; the same probes can evaluate a ladder of convexity values, the
low rungs proposing neighbouring boxes and the high rungs distant boxes, and a
probe that proposes no new box is moved to the next rung. This is configured by a
separate settings class, which requires an upper bound or no value at all:

```python
from gemseo_box_subdivision import SweptBoxSubdivisionSettings

SweptBoxSubdivisionSettings()
```

Without a value, the bound is computed during the run from the spread of the
objective over the boxes already solved, multiplied by a headroom factor of ten.

On Rastrigin and Ackley, whose objectives differ in scale by a factor of four,
this reaches the optimum from all starting points on both problems, which no
single margin does. The sweep is implemented in the master through the settings
`convexity_sweep_points` and `convexity_sweep_max`; for master versions that do
not implement it, the package performs it from outside. See
[annex C](https://simoneconiglio.github.io/gemseo-box-subdivision/algorithm/tuning.html#swept-convexity).

## Extensions

The same scenario supports the extensions of the method, each addressing a case
where a flat subdivision is not applicable:

```python
# Subdivide the variables the objective is multimodal in, at a density each.
BoxSubdivisionScenario([d], "f", space, n_subdivisions={"x_1": 10, "x_2": 4})

# A resolution of 4 ** 2 per component, on 4 * 2 binaries per variable.
BoxSubdivisionScenario([d], "f", space, n_subdivisions=4, levels=2)
```

`refine_deep`, `refine_two_levels` and `refine_frontier` build hierarchies that
refine a box instead of subdividing the whole space finely.

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
