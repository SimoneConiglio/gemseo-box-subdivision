# Add a failing reproduction for `number_of_processes`

Closes the linked issue.

## What this does

Adds `tests/algos/opt/core/test_number_of_processes.py`, which asserts that
`number_of_processes` changes the wall clock and not the answer.

It fails on `develop` at `1279c110`. **It is deliberately not accompanied by a
fix**, because the cause is not settled and the two obvious repairs are measured
not to work — see the issue. The test is proposed on its own so that the
behaviour is pinned, reviewable and reproducible while the cause is decided.

If the project would rather not carry a red test, mark it
`@pytest.mark.xfail(strict=True, reason="<issue url>")` on merge; it will then
turn green on its own when the behaviour is fixed, and fail loudly if it is fixed
by accident and regresses.

## Why it is needed

Nothing in the suite sets `number_of_processes`.
`test_bileveloa_optimizer_analytical` is parametrised over
`number_of_parallel_points`, which is a different setting: the trust-region
probes per iteration, not the fan-out. So the fan-out has never been covered.

That test also skips to `CatTestDisc`, which turns out to be one of the two
catalogues that cannot show the problem — they converge before the master ever
evaluates a batch of more than one design, so `_execute_doe` takes its
`i_k.shape[0] == 1` short circuit. The new test skips the other way, to the
catalogues that do reach the branch.

## What it asserts

The optimum `test_bileveloa_optimizer_analytical` already asserts serially,
`x_opt == [0, 1, 0]` and `f_opt == 0`, under `number_of_processes` of 2 and 4.

On `develop` that gives `x_opt == [1, 0, 0]` and `f_opt == 3.0000000000621`.

## Parametrisation and skips

| fixture | behaviour | in the test |
| --- | --- | --- |
| `CatTestDisc`, `Concave` | converge before a multi-design batch | skipped |
| `CatTestDiscConcave2`, `Concave3` | reach the parallel branch | run |
| guess `Blue` | starts at the answer | skipped, with reason |
| guess `Red`, `Yellow` | explores | run |
| Windows | parallel cache unsupported, as the existing test notes | skipped |

Every case that runs fails, and every skip carries its reason, so the file
documents which configurations exercise the branch at all.

```text
8 failed, 16 skipped
```

## Checklist

- [x] Runs on Linux, CPython 3.11, `gemseo` 6.3.3
- [x] Uses the project's existing fixtures, adds none
- [x] Skips are explicit and explained, none silent
- [x] Licence header matches the project's
- [ ] Changelog entry — happy to add one once the issue's resolution is chosen,
      since the wording depends on whether the setting is fixed or rejected
