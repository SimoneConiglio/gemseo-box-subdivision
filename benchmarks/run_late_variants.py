# Copyright 2026 Simone Coniglio
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""Run the variants added after the targets were published, and profile them.

The variants of :data:`benchmarks.data_profiles.LATE_VARIANTS`, the Euclidean
trust regions, are run under the protocol of the data profiles, four problems,
five starting points and $500$ equivalent evaluations per variable, and profiled
against the **published** targets of ``docs/_static/data_profiles.json``, read
rather than regenerated, as :mod:`benchmarks.run_tunneling` does for tunneling.
As a check, the variant each of them is compared with, ``swept`` in two
variables and ``density_10`` in five, is run again and its area compared with
the published one.

```shell
python -m benchmarks.run_late_variants
```
"""

from __future__ import annotations

import json
import logging
import warnings

from benchmarks import data_profiles
from benchmarks import variants

REFERENCES = {2: "swept", 5: "density_10"}
"""The published variant each dimension's late variants are compared with."""


def main() -> None:
    """Run the late variants, profile them and add them to the published file."""
    logging.disable(logging.CRITICAL)
    warnings.simplefilter("ignore")
    published = json.loads(data_profiles.OUTPUT.read_text(encoding="utf-8"))
    for dimension, names in data_profiles.LATE_VARIANTS.items():
        data = published["dimensions"][str(dimension)]
        budget = data["budget"]
        reference = REFERENCES[dimension]
        results = data_profiles.collect(dimension, (*names, reference))
        profiles = data_profiles.compute_profiles(results, data["targets"])
        summary = data_profiles.summarize(results)
        for name in names:
            published["labels"][name] = variants.VARIANTS[name][0]
            data["areas"][name] = round(data_profiles.area(profiles[name], budget), 4)
            data["summary"][name] = summary[name]
            data["profiles"][name] = data_profiles.change_points(profiles[name])

        checkpoints = [budget // 10, budget // 4, budget // 2, budget]
        print(  # noqa: T201
            f"\n{dimension} variables, published targets\n"
            f"{'':>32} {'area':>5} " + " ".join(f"{c:>5}" for c in checkpoints)
        )
        for name in (reference, *names):
            profile = data_profiles._padded(profiles[name], budget)
            cells = " ".join(f"{profile[c - 1]:>5.0%}" for c in checkpoints)
            print(  # noqa: T201
                f"{name:>32} {data_profiles.area(profile, budget):>5.2f} {cells}"
            )
        print(f"{reference + ', published':>32} {data['areas'][reference]:>5.2f}")  # noqa: T201

    data_profiles.OUTPUT.write_text(
        json.dumps(published, indent=2) + "\n", encoding="utf-8"
    )
    logging.disable(logging.NOTSET)


if __name__ == "__main__":
    main()
