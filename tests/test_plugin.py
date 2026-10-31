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
"""Tests for the registration of the package as a GEMSEO plugin."""

from __future__ import annotations

import importlib
import pkgutil
from importlib.metadata import entry_points

import pytest
from gemseo.core.base_factory import BaseFactory
from gemseo.optimization.factory import OptimizationLibraryFactory

import gemseo_box_subdivision
from gemseo_box_subdivision import disciplines
from gemseo_box_subdivision import subdivisions

PACKAGE_NAME = "gemseo_box_subdivision"


def _iter_module_names() -> list[str]:
    """Return the names of all the modules of the package.

    These are the modules that the GEMSEO factories import when they look for the
    classes contributed by the plugin.
    """
    return [
        module_info.name
        for module_info in pkgutil.walk_packages(
            gemseo_box_subdivision.__path__, prefix=f"{PACKAGE_NAME}."
        )
    ]


def test_entry_point_is_declared() -> None:
    """Check that the package declares itself as a GEMSEO plugin."""
    values = {
        entry_point.value
        for entry_point in entry_points(group=BaseFactory.PLUGIN_ENTRY_POINT)
    }
    assert PACKAGE_NAME in values


@pytest.mark.parametrize("package", [gemseo_box_subdivision, subdivisions, disciplines])
def test_packages_are_importable(package) -> None:
    """Check that the packages scanned by the GEMSEO factories are importable."""
    assert package.__name__.startswith(PACKAGE_NAME)


def test_all_modules_are_importable() -> None:
    """Check that every module of the package can be imported.

    A module raising at import time would be silently discarded by the GEMSEO
    factories, and the algorithms it defines would not be available.
    """
    for module_name in _iter_module_names():
        importlib.import_module(module_name)


def test_optimization_library_factory_discovery() -> None:
    """Check that the plugin does not break the discovery of the optimizers."""
    # Accessing the algorithms triggers the lazy discovery,
    # which imports all the packages declared through the plugin entry points.
    assert OptimizationLibraryFactory().algorithms
