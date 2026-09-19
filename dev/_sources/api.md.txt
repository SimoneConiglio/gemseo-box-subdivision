<!--
 Copyright 2026 Simone Coniglio

 This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
 International License. To view a copy of this license, visit
 http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
 Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

# API reference

Everything below is re-exported from the top-level `gemseo_box_subdivision`
namespace, which is what user code should import from.

## The entry point

```{eval-rst}
.. autosummary::
   :toctree: _autosummary
   :recursive:

   gemseo_box_subdivision.scenario
   gemseo_box_subdivision.settings
   gemseo_box_subdivision.convexity_sweep
```

## Subdivisions

```{eval-rst}
.. autosummary::
   :toctree: _autosummary
   :recursive:

   gemseo_box_subdivision.subdivisions.box
   gemseo_box_subdivision.subdivisions.multi_resolution
   gemseo_box_subdivision.design_spaces
```

## Hierarchies

```{eval-rst}
.. autosummary::
   :toctree: _autosummary
   :recursive:

   gemseo_box_subdivision.hierarchy
```

## Disciplines

```{eval-rst}
.. autosummary::
   :toctree: _autosummary
   :recursive:

   gemseo_box_subdivision.disciplines.box_constraint
   gemseo_box_subdivision.disciplines.box_mapping
   gemseo_box_subdivision.disciplines.multi_resolution_mapping
   gemseo_box_subdivision.disciplines.scenario_adapters.box_start
```
