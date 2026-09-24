# `number_of_processes` returns a wrong optimum, silently

**Project** `gemseo/dev/gemseo-bilevel-outer-approximation`
**Reproduced on** `develop` at `1279c11076e136a1991057c7fb1970e9d7d74d41` (2026-02-02)
and on the released `0.1.1`, with `gemseo` 6.3.3, Linux, CPython 3.11.
**Severity** wrong results, no exception, no failed status.
**Fix** proposed, see the merge request. The suite stays green: 409 passed,
462 skipped, 1 xfailed.

## Summary

`BILEVEL_MASTER_OUTER_APPROXIMATION` accepts `number_of_processes`. Where the
fan-out is actually reached the master returns a **converged optimum that is
wrong**. Nothing raises, nothing reaches a caller that configures logging, and
the run is faster, so the failure looks exactly like a speed-up.

On the project's own `analytical_use_case`, with four parallel points, across the
four catalogues and three starting guesses:

| | correct | wrong |
| --- | --- | --- |
| `number_of_processes=1` | 12 / 12 | — |
| `number_of_processes=2` | 4 / 12 | **8 / 12** |

The wrong ones return `f_opt` of `1.0`, `2.0` or `3.0` where the serial run
returns `6.2e-11`, and `x_opt` of `[1, 0, 0]` where it returns `[0, 1, 0]`.

## The condition to reproduce

**Both** settings are needed:

- `number_of_parallel_points > 1`, because `_execute_doe` short circuits on
  `i_k.shape[0] == 1` and the candidate designs of an iteration are its
  trust-region probes. At the default of one probe, `number_of_processes` does
  nothing at all and the branch is never entered.
- `number_of_processes > 1`, the fan-out itself.

That is why the suite never caught it: `test_bileveloa_optimizer_analytical` is
parametrised over `number_of_parallel_points`, which is not the fan-out, and
nothing anywhere sets `number_of_processes`.

## Mechanism

```python
CallableParallelExecution(
    [self.__evaluate_functions], self.n_processes
).execute(i_k)
```

Three facts about that call:

1. `__evaluate_functions` calls `self.problem.evaluate_functions(...)` and
   **discards its return**, `(data, jacobian_data)`.
2. No `exec_callback` is passed. That is the channel
   `CallableParallelExecution` provides for a caller to collect what a worker
   produced; compare
   `BaseDOELibrary.__run_in_parallel_one_at_a_time` in `gemseo`, where `_worker`
   returns the evaluation and a callback stores it.
3. `use_threading` is left at its default, so this **forks**, and what a child
   writes to `self.problem.database` reaches the child's copy only.

The caller reads those entries immediately afterwards:

```python
out_jac = {
    func_name: atleast_2d(
        database.get_function_value("@" + func_name, alpha)
    )
    for func_name in self.function_names
}
```

`Database.get_function_value` returns `None` for a missing key, and
`numpy.atleast_2d(None)` is an **object array of shape `(1, 1)`**, not an error.
The absent gradient enters the cut model as a scalar, the model is built from
data that was never computed here, and the run proceeds to a plausible wrong
answer.

Measured on one run of the fixture, sixteen parallel batches of four designs:
**10 values and 20 gradients missing** from the caller's database.

The `(1, 1)` is observable. Restoring the values but not the gradients turns the
silence into:

```text
ValueError: shapes (1,1) and (50,4) not aligned: 1 (dim 1) != 50 (dim 0)
  _update_sensitivities_wt_secant_method
```

## Fix

The worker returns the database entry it wrote and a callback replays it in the
caller. Returning the entry rather than the evaluation avoids rebuilding a
database key in the parent, and carries the gradients with the values. The diff
is 38 lines added and 4 removed, in `_execute_doe` plus one private helper.

After it, all 24 configurations return `6.2e-11` and `[0, 1, 0]`, equal to one
process, and the caller's database has **0 values and 0 gradients missing**.

## A second, independent suggestion

Whatever is done about the fan-out, the silent read deserves closing on its own.
The master guards the value,

```python
if fopt is None:
    LOGGER.error("CustomDOE execution did not run correctly.")
```

but not the gradient, and it logs rather than raises, so a caller that
configures logging away — which any benchmark harness does — sees nothing. The
`atleast_2d(None) -> (1, 1)` step is what turns absent data into a plausible
answer, and closing it would have made this a crash rather than a wrong result.

## Reproduction

`tests/algos/opt/core/test_number_of_processes.py`, in the merge request, drives
the project's own fixture and asserts the optimum for `number_of_processes` of
1, 2 and 4, with one process as the control.

```text
without the fix   16 failed, 20 passed
with the fix      36 passed
```
