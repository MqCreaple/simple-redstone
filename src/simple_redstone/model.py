from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum, nonmember
from functools import lru_cache
from types import MappingProxyType
from typing import ClassVar, Mapping

import numpy as np
from nucleation import NucleationError, Schematic
from numpy.typing import NDArray


Vector = NDArray[np.int64]
Matrix = NDArray[np.int64]


class Direction(StrEnum):

    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"
    UP = "up"
    DOWN = "down"

    _VECTORS: ClassVar[dict[str, Vector]] = nonmember({
        "north": np.array([0, 0, -1], dtype=np.int64),
        "south": np.array([0, 0, 1], dtype=np.int64),
        "east": np.array([1, 0, 0], dtype=np.int64),
        "west": np.array([-1, 0, 0], dtype=np.int64),
        "up": np.array([0, 1, 0], dtype=np.int64),
        "down": np.array([0, -1, 0], dtype=np.int64),
    })
    _OPPOSITES: ClassVar[dict[str, str]] = nonmember({
        "north": "south",
        "south": "north",
        "east": "west",
        "west": "east",
        "up": "down",
        "down": "up",
    })

    @property
    def axis(self) -> str:
        if self in (Direction.EAST, Direction.WEST):
            return "x"
        if self in (Direction.NORTH, Direction.SOUTH):
            return "z"
        return "y"

    @property
    def vector(self) -> Vector:
        """Return this direction as a NumPy basis vector."""

        return self._VECTORS[self.value]

    def opposite(self) -> Direction:
        """Return the direction on the same axis with the opposite sign."""

        return Direction(self._OPPOSITES[self.value])

    @staticmethod
    @lru_cache(maxsize=64)
    def coordinate_transform(dim1: Direction, dim2: Direction, dim3: Direction) -> Matrix:
        """Return the row-vector basis for three configured dimensions."""

        return np.vstack([dim1.vector, dim2.vector, dim3.vector])


class GroundMode(StrEnum):
    NONE = "none"
    MINIMAL = "minimal"
    FULL = "full"


@dataclass(frozen=True, slots=True)
class HeaderConfig:
    dim1: Direction = Direction.EAST
    dim2: Direction = Direction.SOUTH
    dim3: Direction = Direction.DOWN
    solid_block: str = "stone"
    colored_solid_block: str = "concrete"
    transparent_block: str = "glass"
    colored_transparent_block: str = "stained_glass"
    ground: GroundMode = GroundMode.MINIMAL

    def __post_init__(self) -> None:
        try:
            dim1 = Direction(self.dim1)
            dim2 = Direction(self.dim2)
            dim3 = Direction(self.dim3)
            ground = GroundMode(self.ground)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

        if dim1.axis not in ("x", "z"):
            raise ValueError("dim1 must be north, south, east, or west")
        if dim2.axis not in ("x", "z"):
            raise ValueError("dim2 must be north, south, east, or west")
        if dim1.axis == dim2.axis:
            raise ValueError("dim1 and dim2 must use different axes")
        if dim3.axis != "y":
            raise ValueError("dim3 must be up or down")

        object.__setattr__(self, "dim1", dim1)
        object.__setattr__(self, "dim2", dim2)
        object.__setattr__(self, "dim3", dim3)
        object.__setattr__(self, "ground", ground)

        for field_name in ("solid_block", "colored_solid_block", "transparent_block", "colored_transparent_block"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
            object.__setattr__(self, field_name, value.strip())


@dataclass(frozen=True, slots=True)
class Cell:
    """A resolved block state and its optional annotation."""

    expression: str = ""
    label: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "expression", self.expression.strip())
        if self.label is not None:
            object.__setattr__(self, "label", self.label.strip())

    @property
    def is_air(self) -> bool:
        return self.expression in ("", "air", "minecraft:air")


@dataclass(frozen=True, slots=True)
class GridShape:
    layers: int
    rows: int
    columns: int

    def __post_init__(self) -> None:
        if min(self.layers, self.rows, self.columns) < 0:
            raise ValueError("grid dimensions cannot be negative")

    @property
    def volume(self) -> int:
        return self.layers * self.rows * self.columns


@dataclass(frozen=True, slots=True)
class CellLocation:
    layer: int
    row: int
    column: int

    def as_vector(self) -> Vector:
        return np.array([self.column, self.row, self.layer], dtype=np.int64)


def coordinates_for(header: HeaderConfig, indices: Vector) -> Vector:
    """Project zero-based grid indices into schematic coordinates."""

    indices = np.asarray(indices, dtype=np.int64)
    if indices.shape != (3,):
        raise ValueError("grid indices must be a three-element vector")
    if np.any(indices < 0):
        raise IndexError("grid coordinates must be non-negative")

    transform = Direction.coordinate_transform(header.dim1, header.dim2, header.dim3)
    return indices @ transform


@dataclass(slots=True)
class Structure:
    """A parsed structure whose block storage is owned by Nucleation."""

    header: HeaderConfig
    schematic: Schematic
    shape: GridShape
    labels: Mapping[str, tuple[CellLocation, ...]] = field(default_factory=dict)
    source: str = "<string>"
    _label_by_location: dict[CellLocation, str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.labels = MappingProxyType(dict(self.labels))
        self._label_by_location = {
            location: label
            for label, locations in self.labels.items()
            for location in locations
        }

    def coordinates(self, layer: int, row: int, column: int) -> Vector:
        if not (0 <= layer < self.shape.layers and 0 <= row < self.shape.rows and 0 <= column < self.shape.columns):
            raise IndexError("cell location is outside the structure")
        return coordinates_for(self.header, CellLocation(layer, row, column).as_vector())

    def cell(self, layer: int, row: int, column: int) -> Cell:
        coordinates = self.coordinates(layer, row, column)
        try:
            expression = self.schematic.get_block_string(*coordinates)
        except NucleationError:
            expression = "air"
        location = CellLocation(layer, row, column)
        return Cell(
            expression=expression,
            label=self._label_by_location.get(location),
        )

    def label_locations(self, label: str) -> tuple[CellLocation, ...]:
        return self.labels.get(label, ())
