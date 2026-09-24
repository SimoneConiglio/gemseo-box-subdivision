# The master rebuilds its MILP in Python, at every iteration

**Project** `gemseo/dev/gemseo-bilevel-outer-approximation`
**Measured on** `develop` at `1279c11076e136a1991057c7fb1970e9d7d74d41`, with
`gemseo` 6.3.3, `ortools` via `pywraplp`, Linux, CPython 3.11.
**Severity** performance only. No result changes.
**Fix** proposed, see the merge request. Suite: 387 passed, 462 skipped, 1 xfailed.

## Summary

`OrtoolsMILP._run` builds the master's model from scratch on every iteration of
the outer approximation, and builds each constraint row by accumulating a Python
expression:

```python
constraint = sum(c * x for c, x in zip(cc, variables, strict=False))
```

That allocates a temporary product and a temporary sum per coefficient. The
coefficients arrive as **NumPy scalars**, so each `c * x` dispatches through
NumPy's operator machinery before reaching `pywraplp`'s. The rows are dense and
the cut set grows as the run proceeds, so the cost is paid again and again over
a matrix that keeps getting bigger.

On a five-variable box-subdivision master, 51 variables:

| rebuild | inequality block | density | Python terms |
| --------- | ------------------ | --------- | -------------- |
| first | $5 \times 51$ | 82% | 510 |
| 38th | $43 \times 51$ | 94% | 2448 |
| last (76th) | $80 \times 51$ | 82% | 4335 |

**184,110 terms over one run of 76 rebuilds.** The profiler counts the
generator on line 134 alone 167,960 times.

## What it costs

Timed in situ, where the measurement covers `build_constraints_matrices`, the
variable creation and the solver setup as well as the rows:

| problem | wall | MILP | of which CBC | of which the Python build |
| --------- | ------ | ------ | -------------- | --------------------------- |
| Rastrigin | $12.94$ | 78.5% | 65.8% | **12.7%** |
| Ackley | $16.85$ | 72.6% | 58.2% | **14.3%** |
| Griewank | $12.97$ | 78.3% | 66.1% | **12.3%** |
| `partly_multimodal` | $1.48$ | 45.3% | 25.7% | **19.3%** |

So roughly an eighth of a run, and a fifth of a short one, is spent building the
model rather than solving it.

## The measurement that isolates it

Building an $80 \times 51$ block of rows, twenty repetitions:

| how | per build | |
| ----- | ----------- | --- |
| `sum(c * x ...)` over NumPy scalars, as now | $27.7$ms | — |
| the same over `tolist()` | $8.7$ms | $3.2\times$ |
| `solver.Sum` over `tolist()` | $7.9$ms | $3.5\times$ |
| `RowConstraint` + `SetCoefficient` | **$2.5$ms** | **$11\times$** |

Two separate costs, then. About two thirds of it is NumPy scalar dispatch,
which `tolist()` alone removes; the rest is the expression tree, which only
setting the coefficients directly removes.

Note what is *not* the problem: the rows are 82–94% dense, so this is not a
sparsity question and skipping zeros is not where the gain is.

## Fix

Set the coefficients on the solver's own objective and on a `RowConstraint` per
row. One row is still added per finite bound, in the same order, so an equality
still becomes the same two rows it did before. See the merge request.

## Not included: rebuilding at all

The deeper cost is that the model is rebuilt from scratch every iteration when
the master mostly *appends* a cut. Caching the solver across iterations would
remove the rest, but the existing rows are not obviously append-only — the
convexification repair rewrites coefficients — so it needs a maintainer's
judgement about when a cached model may be reused. Left alone here.

## Two unrelated faults, found while testing

Neither is touched by the merge request; both are reachable on `develop`.

1. **An all-integer design space cannot be solved.** `get_value_and_bounds`
   returns integer-typed bounds, and `Solver.IntVar(xl, xu, name)` rejects a
   NumPy integer for its `double` arguments:
   `TypeError: in method 'Solver_IntVar', argument 2 of type 'double'`.
   A `float()` at the call site would close it. The master never hits this, its
   design space carrying a continuous epigraph variable.
2. **A problem with only one kind of constraint raises before any row is
   built.** `build_constraints_matrices` returns `None` for the absent kind,
   and `_run` then evaluates `eq_rhs - self._settings.eq_tolerance`:
   `TypeError: unsupported operand type(s) for -: 'NoneType' and 'float'`.
   The existing `test_milp.py` fixture carries both kinds, so the suite does
   not reach it.
