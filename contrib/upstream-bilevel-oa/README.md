<!--
Copyright 2026 Simone Coniglio

This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
International License. To view a copy of this license, visit
http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

# Two upstream contributions, prepared here

This directory holds what belongs to
[`gemseo-bilevel-outer-approximation`][upstream] rather than to this package.
There are **two independent changes**, each on its own branch off `develop` at
`1279c110`, each with its own issue, merge request and patch. Neither depends on
the other.

| | what it is |
| --- | --- |
| **1. A wrong optimum, silently** | `number_of_processes` lost its workers' results |
| `ISSUE.md` | the report: reproduction, mechanism, measurements |
| `MERGE_REQUEST.md` | the merge request description |
| `0001-fix-number-of-processes.patch` | the fix and its test, as a commit |
| `test_number_of_processes.py` | the test alone, for reference |
| **2. A MILP rebuilt in Python** | the master's model construction, $11\times$ |
| `ISSUE_MILP_BUILD.md` | the report: measurements and what is not the cause |
| `MERGE_REQUEST_MILP_BUILD.md` | the merge request description |
| `0002-perf-milp-model-construction.patch` | the change and its tests, as a commit |
| `test_milp_model_construction.py` | the tests alone, for reference |

The numbering is only for ordering this directory. The two patches touch
different files and apply to `develop` independently, in either order.

## 1. `number_of_processes` returned a wrong optimum

The master fanned out over forked workers with a callable returning nothing and
no `exec_callback`, so what a child computed never reached the caller; the
caller's read of the missing gradient returned `None`, which `atleast_2d` makes
into a `(1, 1)` array rather than raising. A converged, wrong answer, arrived at
sooner — the kind of failure that corrupts a benchmark quietly rather than
stopping it. Reaching it needs **both** `number_of_parallel_points > 1` and
`number_of_processes > 1`, `_execute_doe` short circuiting on a single
candidate, which is why the suite never caught it.

```shell
cp <this directory>/test_number_of_processes.py tests/algos/opt/core/
pytest tests/algos/opt/core/test_number_of_processes.py   # 16 failed, 20 passed
git am <this directory>/0001-fix-number-of-processes.patch
pytest tests/algos/opt/core/test_number_of_processes.py   # 36 passed
```

### The counting fault that was ours, not theirs

`BudgetedCounter` counted, and kept the best value, in the parent process, and a
forked child's evaluations never reached it. With the upstream fix applied the
master reached the same optimum at one process and at four while the counter
reported 0.0000 and 33.4089 on Rastrigin: the optimisation agreed and the
measurement did not.

Fixed here rather than upstream, by reading the run from the master's database —
the best value, the sub-problem evaluations and the boxes are now identical to
the digit at one process and at four. What could not move is the cost in the
counter's unit, the adapter exporting a count of points where the cost counts an
objective call plus a gradient call, and the budget guard, which a child
inherits as a copy. See `RunOutcome` and annex D.

## 2. The master rebuilt its MILP in Python

Having re-timed the parallel runs honestly, the fan-out turned out to cover
about a tenth of a run and the master's MILP the rest. Within that, an eighth of
the whole run went on *building* the model rather than solving it:
`OrtoolsMILP._run` accumulated each row as `sum(c * x for c, x in zip(...))`,
over NumPy scalars, rebuilt from scratch at every master iteration against a cut
set that grows — 184,110 Python terms over one 76-iteration run.

Setting the coefficients directly on the solver builds an $80 \times 51$ block
in $2.5$ms against $27.7$ms, $11\times$; in situ the model build falls $4.5$ to
$4.7\times$ and from 12–19% of a run to 3–8%. Over five problems the optimum,
the evaluation count, the box count **and the number of MILP solves** are
identical before and after, so the master takes the same path and not merely the
same destination.

```shell
cp <this directory>/test_milp_model_construction.py tests/algos/opt/
git am <this directory>/0002-perf-milp-model-construction.patch
pytest tests/algos/opt/test_milp_model_construction.py   # 14 passed
```

Those tests pass before the change as well — they are an equivalence guard, not
a reproduction, which is what a performance change warrants. Given a row builder
that compacts a row instead of skipping its zeros, 8 of the 14 fail.

The larger prize is left alone: not rebuilding the model at all between
iterations. The master mostly appends a cut, but the existing rows are not
obviously append-only, the convexification repair rewriting coefficients, so
when a cached model may be reused is a maintainer's call.

### A correctness fault in the same function, reported not fixed

`_run` decides which variables are integers by looking at their **current
value** rather than at the design space that declares them, so a continuous
variable whose value lands on a whole number, or on an infinity, becomes an
`IntVar` for that solve. The master's epigraph variable `eta` is continuous and
carries the lower bound the convergence test reads: **28 of 76 MILP builds,
37%, made it an integer** over one Rastrigin run.

Reported rather than fixed, because both repairs were tried and both are worse.
Reading the declared types breaks the library outright (`191 failed`) — the
one-hot components are declared continuous on purpose and their whole values
are what make them binaries. Requiring finite bounds as well is clean, neutral
on the five box-subdivision problems, and loses the published optimum of
`test_kocis_grossman` (8.47643 against 7.66752). Something in the outer
approximation is relying on that epigraph variable being rounded, and
establishing what is a maintainer's call.

Related, and the reason it surfaced: `pywraplp`'s CP-SAT backend does not
reject a continuous variable either, it rounds it and reports `OPTIMAL`. It is
four to ten times faster than CBC on the master's models and returns a
different problem's answer.

### Two more pre-existing faults, reported but not fixed

Found while writing the tests, untouched by either patch, both reachable on
`develop`:

- a design space of **integer variables only** cannot be solved at all,
  `get_value_and_bounds` returning integer-typed bounds that `Solver.IntVar`
  rejects as its `double` arguments;
- a problem carrying **only one kind of constraint** raises before any row is
  built, `build_constraints_matrices` returning `None` for the absent kind and
  `_run` reading `eq_rhs - eq_tolerance` unguarded.

The master hits neither, its design space mixing binaries with a continuous
epigraph variable and its problem carrying both kinds of constraint.

## Reproducing either

```shell
git clone https://gitlab.com/gemseo/dev/gemseo-bilevel-outer-approximation.git
cd gemseo-bilevel-outer-approximation
git checkout 1279c110
pip install -e .
```

Verified with `gemseo` 6.3.3 on Linux and CPython 3.11. The full upstream suite
is green with each change: **409 passed** with the first, **387 passed** with the
second, 462 skipped and 1 xfailed in both cases.

## Status

**Both fixed, neither submitted.** The branches
`fix/number-of-processes-loses-worker-results` and
`perf/milp-model-construction` carry the changes and their tests, and the two
patch files are those commits, ready for `git am` against a clone or a fork.

Pushing them to a fork and opening the merge requests is not something this
session could do: it had no GitLab credentials, no `glab`, and anonymous read
access only. The patches are the whole deliverable, and they are faithful:
applied to a pristine `1279c110` they reproduce the tree these measurements were
taken on, byte for byte.

### To submit them

Two independent merge requests, from your own fork:

```shell
git clone https://gitlab.com/<you>/gemseo-bilevel-outer-approximation.git
cd gemseo-bilevel-outer-approximation
git remote add upstream https://gitlab.com/gemseo/dev/gemseo-bilevel-outer-approximation.git
git fetch upstream

git checkout -b fix/number-of-processes-loses-worker-results 1279c110
git am <this directory>/0001-fix-number-of-processes.patch
git push -u origin fix/number-of-processes-loses-worker-results

git checkout -b perf/milp-model-construction 1279c110
git am <this directory>/0002-perf-milp-model-construction.patch
git push -u origin perf/milp-model-construction
```

Each branch starts from `1279c110` rather than from the other, because the two
changes are independent and should be reviewed that way. `ISSUE.md` and
`ISSUE_MILP_BUILD.md` are the issue bodies; `MERGE_REQUEST.md` and
`MERGE_REQUEST_MILP_BUILD.md` are the merge request descriptions. Rebase onto a
newer `develop` if `1279c110` has moved on — neither patch touches a file that
is likely to have been rewritten, but say so in the MR if you do.

The third finding, the integrality guess, has **no branch**: both repairs for it
were measured and both are worse, so it is an issue body only. See the section
above.

To run this package against both at once, apply both patches to one branch —
they touch different files and do not conflict:

```shell
git checkout -b local/both-fixes 1279c110
git am <this directory>/0001-fix-number-of-processes.patch
git am <this directory>/0002-perf-milp-model-construction.patch
pytest                       # 423 passed, 462 skipped, 1 xfailed
```

Worth knowing why that matters here rather than being a convenience.
`benchmarks/test_basin_spacing.py` asserts that a run's outcome is identical at
one process and at four, which is false without the *first* patch however the
second is built: installed against a tree carrying only the MILP change, that
test fails with one box against twenty-four. It is the check that says which
upstream tree is installed, and it is worth reading that way when it fails.

[upstream]: https://gitlab.com/gemseo/dev/gemseo-bilevel-outer-approximation
