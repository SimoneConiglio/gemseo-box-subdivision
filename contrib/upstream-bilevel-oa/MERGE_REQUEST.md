# Bring the workers' results back from a parallel evaluation

Closes the linked issue.

## What it fixes

`_execute_doe` fans the evaluation of an iteration's candidate designs over
`number_of_processes` workers. It handed `CallableParallelExecution` a callable
returning `None` and passed no `exec_callback`, and the workers are forked, so
everything a child wrote went to the child's copy of the database and nothing
reached the caller.

The caller reads those entries immediately afterwards, and the read does not
raise: `Database.get_function_value` returns `None` for a missing key and
`atleast_2d(None)` is an array of shape `(1, 1)`. An absent gradient therefore
entered the cut model as a scalar, and the run reported a converged optimum that
was wrong, with no exception and no failed status.

## The change

The worker returns the database entry it wrote, and a callback replays it in the
caller, as `BaseDOELibrary.__run_in_parallel_one_at_a_time` does for a DOE.
Returning the entry rather than the evaluation avoids rebuilding a key in the
caller and carries the gradients along with the values. The worker also clears
the database listeners in the child, as `BaseDOELibrary._worker` does, since
they are not a child's to fire.

38 lines added, 4 removed, in `_execute_doe` and one new private helper. The
serial branch is untouched and returns early as before.

## Results

`analytical_use_case`, four parallel points, four catalogues, three starting
guesses, `number_of_processes` in 1, 2, 4:

| | `f_opt` before | `f_opt` after |
| --- | --- | --- |
| 1 process | `6.2e-11` | `6.2e-11` |
| 2 or 4 processes | `1.0`, `2.0`, `3.0` in 8 of 24 | `6.2e-11` in all |

Missing entries in the caller's database over one run, sixteen batches of four:
10 values and 20 gradients before, **0 and 0** after.

## Tests

Adds `tests/algos/opt/core/test_number_of_processes.py`.

```text
without the change   16 failed, 20 passed
with the change      36 passed
```

Full suite with the change: **409 passed, 462 skipped, 1 xfailed**, no
regressions.

## Why the suite did not catch this

The fan-out is reached only when an iteration has more than one candidate, since
`_execute_doe` short circuits on `i_k.shape[0] == 1`, and the candidates are the
trust-region probes. **A run needs `number_of_parallel_points` above one for
`number_of_processes` to do anything at all.**

`test_bileveloa_optimizer_analytical` is parametrised over
`number_of_parallel_points`, which is that first setting and not the fan-out, and
nothing in the suite sets `number_of_processes`. The new test sets both, and
keeps one process as its control.

## Not included

The silent read itself. `atleast_2d(get_function_value(...))` on a missing key
yields a `(1, 1)` array rather than raising, and the existing guard covers the
value but not the gradient and logs rather than raises. Closing that would have
made this bug a crash instead of a wrong result, but it is a separate change with
its own blast radius and is left for a maintainer to judge. It is described in
the issue.

## Checklist

- [x] Linux, CPython 3.11, `gemseo` 6.3.3
- [x] New test fails before the change and passes after
- [x] Full suite green, no regressions
- [x] Uses the project's existing fixtures, adds none
- [x] Serial path unchanged
- [ ] Changelog entry — say the word and I will add one in the project's format
