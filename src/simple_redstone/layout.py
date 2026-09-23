"""Coordinate assignment, block metadata, and ground-layer generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Any, ClassVar, Mapping

import numpy as np
from numpy.typing import NDArray

from .errors import LayoutError
from .model import CellLocation, Direction, GridShape, GroundMode, HeaderConfig, Structure, Vector, coordinates_for

DEFAULT_MINECRAFT_VERSION = "1.19.2"
Boxes = NDArray[np.float64]
_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class BlockInfo:
    """Metadata exposed by minecraft-data's blocks.json."""

    name: str
    bounding_box: str
    transparent: bool
    filter_light: int
    emit_light: int
    material: str
    default_state_id: int
    min_state_id: int
    max_state_id: int


class MinecraftBlockData:
    """Read-only block metadata backed by minecraft-data's bundled JSON files."""

    _FLOOR_ATTACHED: ClassVar[frozenset[str]] = frozenset(
        {
            "redstone_wire",
            "repeater",
            "comparator",
            "redstone_torch",
            "rail",
            "powered_rail",
            "detector_rail",
            "activator_rail",
        }
    )
    _FACE_SPECS: ClassVar[dict[str, tuple[int, bool]]] = {
        "west": (0, True),
        "east": (0, False),
        "down": (1, True),
        "up": (1, False),
        "north": (2, True),
        "south": (2, False),
    }

    def __init__(self, version: str = DEFAULT_MINECRAFT_VERSION) -> None:
        data_root = files("minecraft_data").joinpath("data", "data")
        try:
            data_paths = self._read_json(data_root.joinpath("dataPaths.json"))
            paths = data_paths["pc"][version]
        except (FileNotFoundError, KeyError) as exc:
            raise LayoutError(f"minecraft-data does not contain PC version {version!r}") from exc

        blocks_path = self._version_path(data_root, paths["blocks"], "blocks.json")
        shapes_path = self._version_path(data_root, paths["blockCollisionShapes"], "blockCollisionShapes.json")
        self.version = version
        self._block_records = {record["name"]: record for record in self._read_json(blocks_path)}
        shapes_data = self._read_json(shapes_path)
        self._collision_blocks = shapes_data["blocks"]
        self._collision_shapes = shapes_data["shapes"]

    @staticmethod
    def _version_path(root: Any, relative: str, filename: str) -> Any:
        return root.joinpath(*relative.split("/"), filename)

    @staticmethod
    def _read_json(path: Any) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    def info(self, block_state: str) -> BlockInfo:
        name = self._block_name(block_state)
        try:
            record = self._block_records[name]
        except KeyError as exc:
            raise LayoutError(f"unknown Minecraft block {name!r}") from exc
        return BlockInfo(
            name=name,
            bounding_box=record["boundingBox"],
            transparent=bool(record["transparent"]),
            filter_light=int(record["filterLight"]),
            emit_light=int(record["emitLight"]),
            material=str(record["material"]),
            default_state_id=int(record["defaultState"]),
            min_state_id=int(record["minStateId"]),
            max_state_id=int(record["maxStateId"]),
        )

    def default_collision_boxes(self, block_state: str) -> Boxes:
        """Return collision boxes for the block's default state.

        minecraft-data 3.20.0 does not ship property-to-state lookup data for
        all modern versions, so non-default properties cannot be resolved
        reliably from this dataset alone.
        """

        name = self._block_name(block_state)
        info = self.info(block_state)
        entry = self._collision_blocks.get(name)
        if entry is None:
            return np.empty((0, 6), dtype=np.float64)

        if isinstance(entry, int):
            shape_id = entry
        else:
            offset = info.default_state_id - info.min_state_id
            if not 0 <= offset < len(entry):
                return np.empty((0, 6), dtype=np.float64)
            shape_id = entry[offset]

        boxes = self._collision_shapes.get(str(shape_id), [])
        return np.asarray(boxes, dtype=np.float64).reshape(-1, 6)

    def is_full_collision_cube(self, block_state: str) -> bool:
        """Return whether the default collision shape fills the block cube."""

        boxes = self.default_collision_boxes(block_state)
        if boxes.shape[0] == 0:
            return False

        minimum = np.min(boxes[:, :3], axis=0)
        maximum = np.max(boxes[:, 3:], axis=0)
        if np.any(minimum > _EPSILON) or np.any(maximum < 1.0 - _EPSILON):
            return False

        centers = (np.indices((16, 16, 16), dtype=np.float64).transpose(1, 2, 3, 0) + 0.5) / 16.0
        covered = np.zeros(centers.shape[:-1], dtype=np.bool_)
        for box in boxes:
            inside = np.all((centers >= box[:3]) & (centers <= box[3:]), axis=-1)
            covered |= inside
        return bool(np.all(covered))

    def covers_collision_face(self, block_state: str, direction: Direction | str) -> bool:
        """Return whether collision geometry fully covers one block face.

        This describes collision coverage, not which visual texture/model face
        Minecraft renders.
        """

        face = Direction(direction).value
        axis, is_minimum = self._FACE_SPECS[face]
        boxes = self.default_collision_boxes(block_state)
        if boxes.shape[0] == 0:
            return False

        if is_minimum:
            touching = boxes[:, axis] <= _EPSILON
        else:
            touching = boxes[:, axis + 3] >= 1.0 - _EPSILON
        if not np.any(touching):
            return False

        projected_axes = [index for index in range(3) if index != axis]
        rectangles = boxes[touching][:, [projected_axes[0], projected_axes[1], projected_axes[0] + 3, projected_axes[1] + 3]]
        return self._rectangles_cover_unit_square(rectangles)

    def requires_floor_support(self, block_state: str) -> bool:
        """Return whether a block needs a supporting block below it.

        minecraft-data does not encode placement/attachment behavior. This
        rule set covers the redstone components defined by Simple Redstone and
        a small set of common floor-mounted blocks.
        """

        name, properties = self._split_block_state(block_state)
        if name not in self._block_records:
            return False
        if name in self._FLOOR_ATTACHED:
            return True
        if name == "lever":
            return properties.get("face") == "floor"
        if name.endswith("_pressure_plate"):
            return True
        if name.endswith("_button"):
            return properties.get("face") == "floor"
        return False

    @staticmethod
    def _block_name(block_state: str) -> str:
        name, _ = MinecraftBlockData._split_block_state(block_state)
        return name

    @staticmethod
    def _split_block_state(block_state: str) -> tuple[str, Mapping[str, str]]:
        value = block_state.strip()
        if "[" not in value:
            return value.removeprefix("minecraft:"), {}

        opening = value.find("[")
        if not value.endswith("]") or value.count("[") != 1 or value.count("]") != 1:
            raise LayoutError(f"invalid block state syntax: {block_state!r}")

        name = value[:opening].strip().removeprefix("minecraft:")
        properties: dict[str, str] = {}
        for raw_property in value[opening + 1 : -1].split(","):
            if raw_property.count("=") != 1:
                raise LayoutError(f"invalid block property in {block_state!r}")
            key, property_value = (part.strip() for part in raw_property.split("=", 1))
            if not key or not property_value:
                raise LayoutError(f"invalid block property in {block_state!r}")
            properties[key] = property_value
        return name, properties

    @staticmethod
    def _rectangles_cover_unit_square(rectangles: Boxes) -> bool:
        if rectangles.shape[0] == 0:
            return False

        horizontal = np.unique(np.concatenate((rectangles[:, 0], rectangles[:, 2], np.array([0.0, 1.0]))))
        for start, end in zip(horizontal[:-1], horizontal[1:]):
            if end - start <= _EPSILON:
                continue
            middle = (start + end) / 2.0
            active = rectangles[(rectangles[:, 0] <= middle + _EPSILON) & (rectangles[:, 2] >= middle - _EPSILON)]
            if active.shape[0] == 0:
                return False

            intervals = sorted((float(item[1]), float(item[3])) for item in active)
            covered_to = 0.0
            for interval_start, interval_end in intervals:
                if interval_start > covered_to + _EPSILON:
                    return False
                covered_to = max(covered_to, interval_end)
                if covered_to >= 1.0 - _EPSILON:
                    break
            if covered_to < 1.0 - _EPSILON:
                return False
        return True


@lru_cache(maxsize=8)
def get_block_data(version: str = DEFAULT_MINECRAFT_VERSION) -> MinecraftBlockData:
    return MinecraftBlockData(version)


class StructureLayout:
    """Apply layout-time operations to a parsed structure."""

    def __init__(self, structure: Structure, block_data: MinecraftBlockData | None = None) -> None:
        self.structure = structure
        self.block_data = block_data or get_block_data()

    def apply_ground(self) -> None:
        if self.structure.header.ground is GroundMode.NONE:
            return

        shape = self.structure.shape
        if not shape.volume:
            return

        if self.structure.header.ground is GroundMode.FULL:
            self._fill_ground(shape)
        else:
            self._fill_minimal_ground(shape)

    def _fill_ground(self, shape: GridShape) -> None:
        header = self.structure.header
        bottom_layer = 0 if header.dim3 is Direction.UP else shape.layers - 1
        first = coordinates_for(header, CellLocation(bottom_layer, 0, 0).as_vector())
        last = coordinates_for(header, CellLocation(bottom_layer, shape.rows - 1, shape.columns - 1).as_vector())
        minimum = np.minimum(first, last)
        maximum = np.maximum(first, last)
        ground_y = int(minimum[1] - 1)
        self.structure.schematic.fill_cuboid(
            int(minimum[0]),
            ground_y,
            int(minimum[2]),
            int(maximum[0]),
            ground_y,
            int(maximum[2]),
            header.solid_block,
        )

    def _fill_minimal_ground(self, shape: GridShape) -> None:
        header = self.structure.header
        bottom_layer = 0 if header.dim3 is Direction.UP else shape.layers - 1
        for row in range(shape.rows):
            for column in range(shape.columns):
                cell = self.structure.cell(bottom_layer, row, column)
                if not self.block_data.requires_floor_support(cell.expression):
                    continue
                coordinates = coordinates_for(header, CellLocation(bottom_layer, row, column).as_vector())
                coordinates[1] -= 1
                self.structure.schematic.set_block_from_string(*coordinates, header.solid_block)


def apply_ground(structure: Structure, block_data: MinecraftBlockData | None = None) -> None:
    StructureLayout(structure, block_data).apply_ground()
