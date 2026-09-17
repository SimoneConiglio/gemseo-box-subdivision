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

The usage chapter enumerates every setting of the class, and a table claiming to
be exhaustive is worth only what keeps it so: a setting added, renamed or
dropped has to reach that table in the same commit.
"""

from __future__ import annotations

import re
from dataclasses import fields
from pathlib import Path

import pytest

from gemseo_box_subdivision import BoxSubdivisionSettings

USAGE = Path(__file__).parent.parent / "docs" / "algorithm" / "usage.md"
"""The usage chapter, which carries the table of every setting."""

SECTION = "## Every setting, and what it defaults to"
"""The heading of that table, whose rows are checked against the class."""

MECHANISM_LABEL = r"^`([a-z_]*(?:convexification|adaptive)[a-z_]*)`$"
"""A definition-list term naming a mechanism, whatever it names it."""


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
    """Check that the table lists every setting of the class, and only those."""
    assert set(_documented_settings()) == {
        f.name for f in fields(BoxSubdivisionSettings)
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
