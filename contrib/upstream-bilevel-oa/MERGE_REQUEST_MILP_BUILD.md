# Build the MILP rows on the solver instead of in Python

Closes the linked issue.

## What it changes

`OrtoolsMILP._run` built every constraint row by accumulating a Python
expression, `sum(c * x for c, x in zip(cc, variables))`, which allocates a
temporary product and a temporary sum per coefficient and dispatches each
multiplication through NumPy before reaching `pywraplp`. The master rebuilds
this model at every iteration of the outer approximation and its cut set grows
as it goes, so the cost is paid again and again over a matrix that keeps
getting bigger — 184,110 terms over one 76-iteration run.

The coefficients are now set on the solver's own objective and on a
`RowConstraint` per row. **This is a change of how the model is built, not of
what it is**: one row is still added per finite bound, in the same order, so an
equality still becomes the same two rows it did before.

49 lines added, 8 removed, in `_run` and one new private static helper.

## Results

Building an $80 \times 51$ block of rows, twenty repetitions: **$27.7$ms
before, $2.5$ms after, $11\times$.**

In situ, where the measurement also covers `build_constraints_matrices`, the
variables and the solver setup:

| problem | build before | build after | | share of wall |
| --------- | -------------- | ------------- | --- | --------------- |
| Rastrigin | $1.65$s | $0.33$s | $4.9\times$ | 12.7% → 3.1% |
| Ackley | $2.41$s | $0.52$s | $4.6\times$ | 14.3% → 3.6% |
| Griewank | $1.59$s | $0.35$s | $4.5\times$ | 12.3% → 3.0% |
| Styblinski-Tang | $0.06$s | $0.02$s | $\approx 3\times$ | 12.9% → 6.3% |
| `partly_multimodal` | $0.29$s | $0.09$s | $\approx 3\times$ | 19.3% → 7.6% |

Branch and bound is untouched and remains the bulk of a run, so the saving on
the wall clock is the build itself — about a tenth of these runs. Wall times
move by more than that between repetitions, CBC's own time varying by some 13%
on this machine, so the build column is the honest measurement of the change
and the wall column is not quoted here.

## Equivalence

Checked end to end rather than argued. Over five box-subdivision problems, the
optimum, the evaluation count, the box count and the **number of MILP solves**
are identical before and after:

| problem | best | evaluations | boxes | MILP solves |
| --------- | ------ | ------------- | ------- | ------------- |
| Rastrigin | $0.000000$ | 1337 | 64 | 76 |
| Ackley | $7.075571$ | 2552 | 84 | 95 |
| Griewank | $0.027101$ | 1661 | 64 | 75 |
| Styblinski-Tang | $-181.694109$ | 163 | 8 | 15 |
| `partly_multimodal` | $0.000000$ | 516 | 24 | 41 |

Identical solve counts matter more than identical optima: the master took the
same path, iteration for iteration, not merely the same destination.

## Tests

Adds `tests/algos/opt/test_milp_model_construction.py` — 14 tests pinning that
a coefficient reaches the variable it belongs to, that a zero coefficient means
the variable is absent rather than displaced, that an all-zero row constrains
nothing, and that an equality still binds on both sides; each cross-checked
against `Scipy_MILP`, plus a dense eight-seed agreement check.

These **pass before and after**. They are an equivalence guard, not a
reproduction, which is what a performance change warrants. To show they have
teeth, replacing the row builder with one that compacts a row instead of
skipping its zeros — shifting every coefficient after the first zero onto the
wrong variable — fails 8 of the 14.

```text
full suite   387 passed, 462 skipped, 1 xfailed
```

## Not included

Caching the model across iterations, which is the larger prize: the master
mostly appends a cut, and rebuilding from scratch throws that away. But the
existing rows are not obviously append-only, the convexification repair
rewriting coefficients, so when a cached model may be reused is a maintainer's
call. Described in the issue.

The issue also records two pre-existing faults found while writing the tests —
an all-integer design space that `Solver.IntVar` rejects, and a problem with
only one kind of constraint that raises on `eq_rhs - eq_tolerance`. Both are
untouched here; the tests are shaped around them rather than through them.

## Checklist

- [x] Linux, CPython 3.11, `gemseo` 6.3.3
- [x] Full suite green, no regressions
- [x] Results identical on five problems, solve counts included
- [x] New tests fail against a deliberately misaligned row builder
- [x] No change to the solver, its settings, or the model's meaning
- [ ] Changelog entry — say the word and I will add one in the project's format
