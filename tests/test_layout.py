import pytest
from nucleation import NucleationError, Schematic

from simple_redstone.layout import MinecraftBlockData
from simple_redstone.model import Direction
from simple_redstone.parser import parse


def _block_at(schematic: Schematic, x: int, y: int, z: int) -> str:
    try:
        return schematic.get_block_string(x, y, z)
    except NucleationError:
        return "minecraft:air"


def test_minecraft_data_exposes_collision_metadata() -> None:
    data = MinecraftBlockData()

    assert data.info("stone").bounding_box == "block"
    assert not data.info("stone").transparent
    assert data.is_full_collision_cube("stone")
    assert data.is_full_collision_cube("glass")
    assert data.info("glass").transparent
    assert all(data.covers_collision_face("stone", direction) for direction in Direction)
    assert data.default_collision_boxes("redstone_wire").shape == (0, 6)


def test_attachment_requirements_are_explicit_behavior_rules() -> None:
    data = MinecraftBlockData()

    assert data.requires_floor_support("redstone_wire")
    assert data.requires_floor_support("repeater[facing=east]")
    assert data.requires_floor_support("comparator[facing=east]")
    assert data.requires_floor_support("redstone_torch")
    assert data.requires_floor_support("lever[face=floor]")
    assert data.requires_floor_support("stone_pressure_plate")
    assert not data.requires_floor_support("redstone_wall_torch[facing=east]")
    assert not data.requires_floor_support("lever[face=wall,facing=east]")
    assert not data.requires_floor_support("stone")


def test_full_ground_fills_the_complete_bottom_layer() -> None:
    structure = parse("---\nground: full\n---\n#,#")

    assert _block_at(structure.schematic, 0, -1, 0) == "stone"
    assert _block_at(structure.schematic, 1, -1, 0) == "stone"
    assert structure.schematic.block_count() == 4


def test_minimal_ground_only_supports_attached_bottom_blocks() -> None:
    structure = parse("---\nground: minimal\n---\n.,#")

    assert _block_at(structure.schematic, 0, -1, 0) == "stone"
    assert _block_at(structure.schematic, 1, -1, 0) == "minecraft:air"


def test_minimal_ground_does_not_add_floor_for_wall_torch() -> None:
    structure = parse("---\nground: minimal\n---\no-")

    assert _block_at(structure.schematic, 0, -1, 0) == "minecraft:air"


def test_none_ground_adds_no_blocks() -> None:
    structure = parse("---\nground: none\n---\n.")

    assert _block_at(structure.schematic, 0, -1, 0) == "minecraft:air"


@pytest.mark.parametrize(
    ("dim3", "body", "ground_y"),
    [
        ("up", ".\n#", -1),
        ("down", "#\n.", -2),
    ],
)
def test_minimal_ground_checks_world_bottom_layer(dim3: str, body: str, ground_y: int) -> None:
    structure = parse(f"---\ndim3: {dim3}\nground: minimal\n---\n{body}")

    assert _block_at(structure.schematic, 0, ground_y, 0) == "stone"
    assert structure.schematic.block_count() == 3


@pytest.mark.parametrize(
    ("dim3", "ground_y"),
    [
        ("up", -1),
        ("down", -2),
    ],
)
def test_full_ground_uses_world_bottom_layer(dim3: str, ground_y: int) -> None:
    structure = parse(f"---\ndim3: {dim3}\nground: full\n---\n#\n#")

    assert _block_at(structure.schematic, 0, ground_y, 0) == "stone"
    assert structure.schematic.block_count() == 3
