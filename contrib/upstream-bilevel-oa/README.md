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
rather than to this package: the master's `number_of_processes` setting returns a
wrong optimum without raising, and nothing in this repository can fix it.

| file | what it is |
| ------ | ------------ |
| `ISSUE.md` | the report, with the reproduction, the mechanism, and what was ruled out |
| `MERGE_REQUEST.md` | the description of the merge request adding the test |
| `test_number_of_processes.py` | the reproduction, to drop into `tests/algos/opt/core/` |

## Why it matters here

`benchmarks/basin_spacing.py` exposes `n_processes` and its docstring says to
leave it at one. This is the evidence behind that instruction. The machine this
benchmark runs on has cores to spare and the setting looks like free speed; it is
not, and the way it fails — a plausible answer, arrived at sooner — is the kind
that quietly corrupts a benchmark rather than stopping it.

## Reproducing

```shell
git clone https://gitlab.com/gemseo/dev/gemseo-bilevel-outer-approximation.git
cd gemseo-bilevel-outer-approximation
pip install -e .
cp <this directory>/test_number_of_processes.py tests/algos/opt/core/
pytest tests/algos/opt/core/test_number_of_processes.py
```

Reproduced at `1279c110` on `develop` and on the released `0.1.1`, with
`gemseo` 6.3.3 on Linux and CPython 3.11: **8 failed, 16 skipped**, no case that
reaches the parallel branch passing.

## Status

Reported, not fixed. Two repairs were implemented and measured not to work, and
both are written up in `ISSUE.md` so they are not tried again: marshalling the
results back through an `exec_callback`, which restores the database exactly and
changes nothing; and threading rather than forking, which fails on a driver
library that is not re-entrant. What remains is most likely the warm start of the
sub-problems, which a fork cannot carry, and that is a question about intended
semantics rather than a defect to patch.

[upstream]: https://gitlab.com/gemseo/dev/gemseo-bilevel-outer-approximation
