<!--
Copyright 2026 Simone Coniglio

This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
International License. To view a copy of this license, visit
http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

# An upstream report, prepared here

This directory holds what belongs to
[`gemseo-bilevel-outer-approximation`][upstream]
rather than to this package: the master's `number_of_processes` setting returned
a wrong optimum without raising. Reported, and fixed.

| file | what it is |
| --- | --- |
| `ISSUE.md` | the report: reproduction, mechanism, measurements |
| `MERGE_REQUEST.md` | the merge request description |
| `0001-fix-number-of-processes.patch` | the fix and its test, as a commit |
| `test_number_of_processes.py` | the test alone, for reference |

## Why it matters here

`benchmarks/basin_spacing.py` exposes `n_processes`, and this is why its
docstring tells the reader what it does. The way the upstream fault failed — a
plausible answer, arrived at sooner — is the kind that corrupts a benchmark
quietly rather than stopping it.

A second reason to leave it at one here is local and is **not** an upstream bug:
`BudgetedCounter` counts, and tracks the best value, in the parent process. A
forked child's evaluations never reach it, so this benchmark cannot measure the
cost of a multi-process run even against a fixed master. With the fix applied the
scenario's own `optimization_result.f_opt` is 0.0000 at one process and at four,
while the counter reports 0.0000 and 33.4089: the optimisation agrees, the
counter does not.

## Reproducing

```shell
git clone https://gitlab.com/gemseo/dev/gemseo-bilevel-outer-approximation.git
cd gemseo-bilevel-outer-approximation
pip install -e .
cp <this directory>/test_number_of_processes.py tests/algos/opt/core/
pytest tests/algos/opt/core/test_number_of_processes.py   # fails
git am <this directory>/0001-fix-number-of-processes.patch
pytest tests/algos/opt/core/test_number_of_processes.py   # passes
```

Reproduced at `1279c110` on `develop` and on the released `0.1.1`, with
`gemseo` 6.3.3 on Linux and CPython 3.11: **16 failed, 20 passed** without the
fix, **36 passed** with it. The whole upstream suite stays green.

Reaching the fault needs **both** `number_of_parallel_points > 1` and
`number_of_processes > 1`: `_execute_doe` short circuits on a single candidate,
so the fan-out is unreachable at the default of one probe.

## Status

**Fixed.** The branch `fix/number-of-processes-loses-worker-results` carries the
change and the test; `0001-fix-number-of-processes.patch` is that commit, ready
to apply to a clone or a fork:

```shell
git am 0001-fix-number-of-processes.patch
```

The fix needs pushing to a fork and opening as a merge request, which is not
something this session could do: it had no GitLab credentials.
