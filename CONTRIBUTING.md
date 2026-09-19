<!--
Copyright 2026 Simone Coniglio

This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
International License. To view a copy of this license, visit
http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

# Contributing

## Setting up

```shell
python -m pip install tox tox-uv
tox -e check           # installs and runs the pre-commit hooks
tox -e py3.12          # runs the test suite
```

The pre-commit hooks format the code with [ruff](https://docs.astral.sh/ruff/),
insert the license headers and check the commit messages with
[commitizen](https://commitizen-tools.github.io/commitizen/), which expects
[conventional commits](https://www.conventionalcommits.org).

## Layout

```text
src/gemseo_box_subdivision/
├── __init__.py         # the public namespace, re-exporting everything below
├── scenario.py         # the entry point building a run
├── settings.py         # the settings, in the units the methodology measures
├── subdivisions/       # how a design space is cut into boxes
├── design_spaces.py    # the design spaces a subdivision builds
├── hierarchy.py        # refining a box rather than subdividing finely
└── disciplines/        # the disciplines the formulations are built from
tests/                  # mirrors the layout of src
docs/                   # the Sphinx documentation
benchmarks/             # the algorithm benchmarks
```

Everything a user needs is re-exported from the top-level namespace, so user
code imports from `gemseo_box_subdivision` and never from a submodule.

## Adding an optimization algorithm

This package contributes no optimization library of its own: the method is a
composition over the `Benders` formulation and the master of
`gemseo-bilevel-outer-approximation`. Should one be added, create
`src/gemseo_box_subdivision/algos/opt/<algo_name>/` containing:

1. `<algo_name>_settings.py`, with a settings model deriving from
   `BaseOptimizerSettings` (or a more specific base such as `BaseMILPSettings`)
   and whose `_TARGET_CLASS_NAME` class variable is the name of the library
   class;
2. `<algo_name>.py`, with a class deriving from `BaseOptimizationLibrary`,
   declaring its algorithms in `ALGORITHM_INFOS` and implementing `_run`;
3. an `__init__.py` in each new directory.

Then add the settings class to the `runtime-evaluated-base-classes` list of
`.ruff.toml` if other settings models derive from it, and add the tests under
`tests/algos/opt/`.

GEMSEO discovers these classes by importing every module of the package, so a
module that raises at import time silently removes its algorithms from the
factories. The test `tests/test_plugin.py::test_all_modules_are_importable`
guards against this.

## Dependency pinning

Unlike the upstream GEMSEO copier template, this project does not pin the test
dependencies in `requirements/test-python*.txt`; the `dev` dependency group of
`pyproject.toml` is used directly, so a fresh clone can run `tox` without a
locking step. Only `requirements/check.in` remains, for the pre-commit tooling.

## The published documentation

Two builds are published to one GitHub Pages site, from the `gh-pages` branch:

| build | where | what it documents |
|-------|-------|-------------------|
| `main` | <https://simoneconiglio.github.io/gemseo-box-subdivision/> | the released code |
| `develop` | <https://simoneconiglio.github.io/gemseo-box-subdivision/dev/> | what the next release will carry |

The development build says so on every page, in a banner linking back to the
released one, and its *edit this page* buttons point at `develop`.

A **pull request** publishes nothing. It builds the documentation and uploads it
as an artifact of its run, `documentation-<number>`: download it from the run's
summary and open `index.html` to read a change before it is merged. The build
fails on a warning, so a broken cross-reference stops the pull request rather
than reaching the site.

**The site is served from the `gh-pages` branch**, which the workflow writes and
nothing else should. Under *Settings → Pages*, the source is **Deploy from a
branch**, `gh-pages`, `/ (root)`. Setting it back to *GitHub Actions* would serve
whatever that path last deployed and ignore the branch.

## Releasing

The version is **derived from the git tag** by
[setuptools_scm](https://setuptools-scm.readthedocs.io), so the tag is the only
place a version number is written. An untagged build is a development version,
such as `0.1.dev12+g7084de4`, which no index accepts.

### Once, to set up trusted publishing

Trusted publishing lets the workflow upload without any token or secret. On
[PyPI](https://pypi.org/manage/account/publishing/), add a **pending publisher**
for a project that does not exist yet:

| Field | Value |
|-------|-------|
| PyPI project name | `gemseo-box-subdivision` |
| Owner | `SimoneConiglio` |
| Repository name | `gemseo-box-subdivision` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

Then create the `pypi` environment in the repository, under
Settings, Environments. Repeat both on
[TestPyPI](https://test.pypi.org/manage/account/publishing/) with the
environment `testpypi` to be able to rehearse a release.

The repository name and the environment name must match exactly, since they are
what PyPI checks in the token the workflow presents.

### For each release

1. Move the `Unreleased` section of `CHANGELOG.md` under the version being
   released, with its date, and open a new empty `Unreleased` section.
2. Check the release locally:

   ```shell
   tox -e py3.12 -e check -e dist
   ```

3. Commit the changelog, then tag and push:

   ```shell
   git tag 0.1.0
   git push origin main --follow-tags
   ```

4. The `Release` workflow runs the tests, builds the distribution, checks the
   metadata that the index will render, and publishes.

### Rehearsing

An upload cannot be undone, and a version number cannot be reused even after
the file is deleted, so a mistake costs a version number. Before the first
release, publish to TestPyPI from the Actions tab, with **Run workflow** on the
`Release` workflow and the index `testpypi`, and check the result with

```shell
pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ gemseo-box-subdivision
```

The extra index is needed because the dependencies live on PyPI, not on
TestPyPI.

### Tag format

Only version tags publish, `1.2.3` or `v1.2.3`, with an optional `a`, `b` or
`.postN` suffix for a pre-release. Any other tag is ignored by the workflow.
