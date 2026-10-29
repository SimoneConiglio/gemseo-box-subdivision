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
"""The interface shared by the subdivisions of a design space."""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:
    from numpy import ndarray


class BaseSubdivision(ABC):
    """A subdivision of a design space into boxes chosen by binary variables.

    A subdivision tells the master problem how many binaries it chooses a box
    with, and the sub-problem the bounds of the box those binaries select. How
    the binaries encode a box is left to the concrete subdivisions: one one-hot
    vector per component for a :class:`.BoxSubdivision`, one per level and per
    component for a :class:`.MultiResolution`.
    """

    @property
    @abstractmethod
    def variable_names(self) -> tuple[str, ...]:
        """The names of the subdivided variables."""

    @property
    @abstractmethod
    def sizes(self) -> dict[str, int]:
        """The size of each subdivided variable."""

    @property
    @abstractmethod
    def n_boxes(self) -> int:
        """The number of boxes the binaries can select."""

    @property
    @abstractmethod
    def n_binaries(self) -> int:
        """The number of binary variables encoding the choice of a box."""

    @property
    @abstractmethod
    def max_step(self) -> int:
        """The radius at which the trust region stops constraining the master."""

    @abstractmethod
    def compute_bounds(self, name: str, one_hot: Any) -> tuple[ndarray, ndarray]:
        """Compute the bounds of the box selected by the binaries of a variable.

        Args:
            name: The name of the variable.
            one_hot: The binaries of the variable, in the encoding of the
                subdivision.

        Returns:
            The lower and upper bounds of the selected box.
        """

    @abstractmethod
    def locate(self, name: str, value: ndarray) -> Any:
        """Return the box holding a value of a variable.

        Args:
            name: The name of the variable.
            value: The value of the variable.

        Returns:
            The box holding the value, in the encoding of the subdivision.
        """
