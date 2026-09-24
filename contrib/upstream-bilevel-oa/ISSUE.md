# `number_of_processes` silently returns a wrong optimum

**Project** `gemseo/dev/gemseo-bilevel-outer-approximation`
**Reproduced on** `develop` at `1279c11076e136a1991057c7fb1970e9d7d74d41` (2026-02-02),
and on the released `0.1.1`, with `gemseo` 6.3.3 on Linux / CPython 3.11.
**Severity** wrong results, no error raised.

## Summary

`BILEVEL_MASTER_OUTER_APPROXIMATION` accepts `number_of_processes`. With any
value above one the master returns a **converged optimum that is wrong**, with no
exception, no warning and no failed status. A run that reaches the global optimum
serially reports a point far from it in a fraction of the time, so the failure
looks like a speed-up.

This is not only a counting or reporting problem: the returned design and
objective both change, so the search itself is different.

## Reproduction

`tests/algos/opt/core/test_number_of_processes.py` (attached, and in the merge
request) drives the project's own `analytical_use_case` fixture and asserts the
optimum that `test_bileveloa_optimizer_analytical` already asserts serially.

```text
8 failed, 16 skipped
```

Every case that exercises the parallel branch fails. Example, `CatTestDiscConcave2`
from the `Red` guess with `number_of_processes=2`:

| | `x_opt` | `f_opt` |
| --- | --- | --- |
| serial (asserted by the existing test) | `[0, 1, 0]` | `0.0` |
| `number_of_processes=2` | `[1, 0, 0]` | `3.0000000000621` |

The same is visible from a downstream package. On Rastrigin in five variables
over a 10-per-variable subdivision, one starting point, a budget of 8000
equivalent evaluations:

| `number_of_processes` | objective | evaluations | wall |
| --- | --- | --- | --- |
| 1 | **0.0000** | 2115 | 13.4 s |
| 2 | 33.4089 | 35 | 0.2 s |
| 4 | 33.4089 | 35 | 0.2 s |

`33.4089` is the value of the first box evaluated: the master stops having
learned nothing, and reports success.

## Why the existing tests do not catch it

`test_bileveloa_optimizer_analytical` is parametrised over
`number_of_parallel_points`, which is the number of trust-region probes per
iteration, **not** over `number_of_processes`, which is the fan-out. Nothing in
the suite sets `number_of_processes`.

The parametrisation also skips to `CatTestDisc`, which is one of the two
catalogues that never exercise the branch: they reach the optimum before the
master evaluates a batch of more than one design, so `_execute_doe` takes its
`i_k.shape[0] == 1` short circuit. `CatTestDiscConcave2` and
`CatTestDiscConcave3` do exercise it, from any starting guess that is not already
the answer.

## Mechanism, as far as it is established

`OuterApproximationOptimizer._execute_doe` fans out like this:

```python
CallableParallelExecution(
    [self.__evaluate_functions], self.n_processes
).execute(i_k)
```

Three things are true of that call.

1. **The worker returns `None`.** `__evaluate_functions` calls
   `self.problem.evaluate_functions(...)` and discards its `(data, jacobian_data)`.
2. **No `exec_callback` is passed.** That is the channel `CallableParallelExecution`
   provides for a parent to collect what a worker produced. Compare
   `gemseo.algos.doe.base_doe_library.BaseDOELibrary.__run_in_parallel_one_at_a_time`,
   where `_worker` returns the evaluation and
   `__store_in_database_and_finalize_iteration` stores it in the parent.
3. **`use_threading` is left at its default**, so this forks. Whatever a child
   writes to `self.problem.database` reaches the child's copy only.

The caller, immediately after `_execute_doe`, reads what was never stored:

```python
out_jac = {
    func_name: atleast_2d(database.get_function_value("@" + func_name, alpha))
    for func_name in self.function_names
}
```

`Database.get_function_value` returns `None` for a missing key, and
`numpy.atleast_2d(None)` is an **object array of shape `(1, 1)`** rather than an
error. The absent gradient therefore enters the cut model as a scalar. That is
the silent part: nothing raises, and the run converges on a model built from
absent data.

The `(1, 1)` is observable. Restoring the values but not the gradients makes it
surface as

```text
ValueError: shapes (1,1) and (50,4) not aligned: 1 (dim 1) != 50 (dim 0)
  _update_sensitivities_wt_secant_method
```

## What was tried and did **not** fix it

These are recorded so the next person does not repeat them.

- **Marshalling the results back**, modelled on `BaseDOELibrary`: the worker
  returns the database entry it wrote, and an `exec_callback` replays it in the
  parent. Instrumented, this works as intended — the callback fires for every
  design, the entries are non-empty, every one stores without error, and the
  values a child computes are **identical** to the parent's (`f`, `x_opt` and a
  `@f` of the right shape `(50,)`). The optimum is unchanged: still wrong.
- **Threading instead of forking**, so the database is shared: fails differently,
  with `AttributeError: 'NoneType' object has no attribute 'evaluation_counter'`
  from `BaseDriverLibrary._finalize_previous_iteration_using_database`. GEMSEO's
  driver library is stateful and is not re-entrant under concurrent drives of the
  sub-problem scenario.
- **A shared HDF5 cache** on `formulation.sub_problem_scenario_adapter`, which
  `test_bileveloa_optimizer_analytical` sets for its parallel points: no effect,
  the test fails with it and without it.

With the database correctly repopulated the run completes **without any
exception** and still returns the wrong optimum, which says the state the master
depends on between iterations is not carried by the database alone.

## Hypothesis for the remaining cause

The iterations are sequentially dependent. Each sub-problem is solved from the
state the previous solve left, and forked children all start from one snapshot of
the parent, so the warm start is lost. That is consistent with the size of the
effect: a sub-problem started elsewhere returns a different local optimum, and
the cut built from it describes a different box.

If that is right, `number_of_processes` is not a plumbing bug but a change of
algorithm, and the question for a maintainer is what the setting is meant to
mean.

## Suggested resolution

Whichever way the question above is settled, the present behaviour should not
survive, because it is silent:

1. **Short term** — reject `number_of_processes > 1` with an explicit error, or
   warn loudly, rather than returning a wrong optimum. A user cannot currently
   tell the difference between a speed-up and a failure.
2. **Guard the silent read** — `atleast_2d(get_function_value(...))` on a missing
   key should raise rather than produce a `(1, 1)` array. This one line is what
   turns missing data into a plausible-looking answer, and it would have made
   this report a crash instead of a wrong result.
3. **Then decide the semantics** of parallel evaluation for a sequentially
   dependent master, and if it is to be supported, marshal both the database
   entries and whatever state the warm start needs.

## Attachments

- `test_number_of_processes.py` — the reproduction, in the project's idiom,
  using its own fixtures. It fails on `develop` and is written to pass once the
  behaviour is correct.
