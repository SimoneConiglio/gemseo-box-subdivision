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
"""Tests that the documentation keeps saying what the code does.

Every check here was first run by hand, and each one caught something: a table
claiming to be exhaustive that had stopped being so, a mechanism labelled by a
name the setting refuses, an example whose keyword no longer existed, a
cross-reference to a class that had been deleted. A check run by hand is a check
that runs once, so they run here instead, over the chapters, the README and the
docstrings alike.
"""

from __future__ import annotations

import ast
import builtins
import re
from dataclasses import fields
from dataclasses import is_dataclass
from pathlib import Path

import pytest

import gemseo_box_subdivision
from gemseo_box_subdivision import BoxSubdivisionSettings
from gemseo_box_subdivision import SweptBoxSubdivisionSettings

USAGE = Path(__file__).parent.parent / "docs" / "algorithm" / "usage.md"
"""The usage chapter, which carries the table of every setting."""

SECTION = "## Every setting, and what it defaults to"
"""The heading of that table, whose rows are checked against the class."""

MECHANISM_LABEL = r"^`([a-z_]*(?:convexification|adaptive)[a-z_]*)`$"
"""A definition-list term naming a mechanism, whatever it names it."""

ROOT = Path(__file__).parent.parent
"""The repository, whose chapters and sources are read together."""

CHAPTERS = (*sorted((ROOT / "docs").rglob("*.md")), ROOT / "README.md")
"""Everything written for a reader, the README included."""

SOURCES = (
    *sorted((ROOT / "src").rglob("*.py")),
    *sorted((ROOT / "benchmarks").rglob("*.py")),
)
"""The modules, whose docstrings are documentation too.

The benchmarks are read as well although the suite does not run them: their
docstrings are what the method chapters cite for their numbers, and a name the
package withdrew survives there just as visibly as in a chapter."""

WITHDRAWN = (
    "ConvexitySweepSettings",
    "N_CONVEXITY_POINTS",
    "create_convexity_sweep",
    "convexity_sweep=",
    "BoxSubdivisionSettings.convexity_sweep",
)
"""Names this package has removed, which nothing may still promise a reader.

They are listed rather than derived because the point is what is *absent* from
the code: an audit of the chapters alone missed the ones left in the docstrings.
"""


def _code_blocks(text: str) -> list[str]:
    """Return the Python examples of a chapter.

    Args:
        text: The text of the chapter.

    Returns:
        The body of each fenced ``python`` block.
    """
    return re.findall(r"```python\n(.*?)```", text, re.DOTALL)


def _headings(page: Path) -> set[str]:
    """Return the anchors a chapter offers, as a Markdown renderer slugs them.

    Args:
        page: The chapter to read.

    Returns:
        One slug per heading.
    """
    anchors = set()
    for line in page.read_text(encoding="utf-8").splitlines():
        heading = re.match(r"^#{1,6}\s+(.*?)\s*$", line)
        if heading:
            slug = re.sub(r"[`*_]", "", heading.group(1)).lower()
            anchors.add(re.sub(r"\s+", "-", re.sub(r"[^\w\s-]", "", slug).strip()))

    return anchors


def _documented_settings() -> list[str]:
    """Return the settings the usage chapter enumerates, in the order it does.

    Returns:
        The name in the first column of each row of the table.
    """
    text = USAGE.read_text(encoding="utf-8")
    section = text.split(SECTION, 1)[1].split("\n## ", 1)[0]
    return re.findall(r"^\| `([a-z_]+)` \|", section, re.MULTILINE)


@pytest.mark.skipif(not USAGE.exists(), reason="the documentation is not installed")
def test_every_setting_is_documented() -> None:
    """Check that the tables list every setting of both entry points, and no other.

    The section holds one table of what the two share and one of what each adds,
    so between them they name every field of either class exactly once.
    """
    assert set(_documented_settings()) == {
        field.name
        for settings in (BoxSubdivisionSettings, SweptBoxSubdivisionSettings)
        for field in fields(settings)
    }


@pytest.mark.skipif(not USAGE.exists(), reason="the documentation is not installed")
def test_the_documented_mechanisms_are_the_ones_accepted() -> None:
    """Check that every mechanism a chapter labels is a value of the setting.

    The two are labelled by their value rather than by their prose name, so a
    reader copying one into ``mechanism`` has to get a run rather than an error.
    The prose names, the adaptive repair and the pure convexification, are not
    written as literals and are not matched here.
    """
    labelled = {}
    for chapter in USAGE.parent.glob("*.md"):
        text = chapter.read_text(encoding="utf-8")
        labelled[chapter.name] = set(re.findall(MECHANISM_LABEL, text, re.MULTILINE))
    accepted = set(BoxSubdivisionSettings.MECHANISMS)

    for name, labels in labelled.items():
        assert labels <= accepted, f"{name} labels a mechanism the setting refuses"

    assert set().union(*labelled.values()) == accepted


@pytest.mark.skipif(not USAGE.exists(), reason="the documentation is not installed")
def test_the_swept_entry_point_is_not_offered_what_it_drops() -> None:
    """Check that what the swept entry point drops is not listed under it.

    A master to name, settings to pass it and a convexity to calibrate are what
    a sweep exists not to ask for, so the chapter must not leave them where a
    swept run would look for them.
    """
    text = USAGE.read_text(encoding="utf-8")
    under_swept = text.split("`SweptBoxSubdivisionSettings`, the swept", 1)[1]
    under_swept = under_swept.split("\n## ", 1)[0]
    rows = set(re.findall(r"^\| `([a-z_]+)` \|", under_swept, re.MULTILINE))

    swept = {field.name for field in fields(SweptBoxSubdivisionSettings)}
    dropped = {field.name for field in fields(BoxSubdivisionSettings)} - swept
    assert rows <= swept
    assert not rows & dropped


@pytest.mark.parametrize("chapter", CHAPTERS, ids=lambda path: path.name)
def test_every_example_passes_settings_that_exist(chapter) -> None:
    """Check that every keyword of every example is a setting of its class.

    An example is the first thing a reader copies, and a keyword the class no
    longer takes fails at the first line they run.

    Args:
        chapter: The chapter to read.
    """
    for block in _code_blocks(chapter.read_text(encoding="utf-8")):
        for node in ast.walk(ast.parse(block)):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue

            cls = getattr(gemseo_box_subdivision, node.func.id, None)
            if cls is None or not is_dataclass(cls):
                continue

            accepted = {field.name for field in fields(cls)}
            given = {keyword.arg for keyword in node.keywords if keyword.arg}
            assert given <= accepted, (
                f"{chapter.name}: {cls.__name__} takes no {given - accepted}"
            )


@pytest.mark.parametrize("chapter", CHAPTERS, ids=lambda path: path.name)
def test_every_self_contained_example_runs(chapter) -> None:
    """Check that an example needing nothing of its own executes.

    Reading an example proves it parses. Only running it proves the behaviour it
    shows is the behaviour the package has, which is how a refusal added for
    safety was caught turning the documented form of a sweep into an error.

    Args:
        chapter: The chapter to read.
    """
    # What import * binds, which is the public API and not the submodules:
    # dir would offer 'scenario', and a snippet continuing an earlier block
    # would look self-contained.
    available = set(gemseo_box_subdivision.__all__) | set(dir(builtins))
    for block in _code_blocks(chapter.read_text(encoding="utf-8")):
        tree = ast.parse(block)
        used = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        bound = {
            target.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        } | {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        if used - bound - available:
            # It needs a design space, a discipline or an earlier block.
            continue

        exec(  # noqa: S102
            compile(
                f"from {gemseo_box_subdivision.__name__} import *\n{block}",
                str(chapter),
                "exec",
            ),
            {},
        )


@pytest.mark.parametrize("page", CHAPTERS + SOURCES, ids=lambda path: path.name)
def test_nothing_still_promises_what_was_withdrawn(page) -> None:
    """Check that no chapter or docstring names something the package removed.

    Args:
        page: The chapter or module to read.
    """
    text = page.read_text(encoding="utf-8")
    named = [name for name in WITHDRAWN if name in text]
    assert not named, f"{page.name} still names {named}"


@pytest.mark.parametrize("chapter", CHAPTERS, ids=lambda path: path.name)
def test_every_internal_link_resolves(chapter) -> None:
    """Check that every link between chapters, and every anchor, has a target.

    Args:
        chapter: The chapter to read.
    """
    for link in re.findall(r"\]\(([^)]+)\)", chapter.read_text(encoding="utf-8")):
        if link.startswith(("http", "mailto")):
            continue

        path, _, anchor = link.partition("#")
        target = (chapter.parent / path) if path else chapter
        assert target.exists(), f"{chapter.name}: {link} has no file"
        if anchor:
            assert anchor in _headings(target), f"{chapter.name}: {link} has no heading"


@pytest.mark.parametrize("chapter", CHAPTERS, ids=lambda path: path.name)
def test_the_headings_make_an_outline(chapter) -> None:
    """Check that no heading level is skipped, so the outline stays readable.

    Args:
        chapter: The chapter to read.
    """
    previous = 0
    fenced = False
    for line in chapter.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            fenced = not fenced
        if fenced:
            continue

        heading = re.match(r"^(#{1,6})\s", line)
        if heading:
            level = len(heading.group(1))
            assert not previous or level <= previous + 1, f"{chapter.name}: {line}"
            previous = level
