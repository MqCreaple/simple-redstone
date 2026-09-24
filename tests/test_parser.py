from pathlib import Path

import numpy as np

import pytest
from nucleation import Schematic

from simple_redstone.errors import ParseError
from simple_redstone.model import Cell, CellLocation, Direction, GroundMode
from simple_redstone.parser import parse, parse_file


def test_parses_default_header_and_single_cell() -> None:
    structure = parse(".@Q")

    assert isinstance(structure.schematic, Schematic)
    assert structure.header.dim1 is Direction.EAST
    assert structure.header.dim2 is Direction.SOUTH
    assert structure.header.dim3 is Direction.DOWN
    assert structure.header.solid_block == "stone"
    assert structure.header.slab == "stone_slab"
    assert structure.header.ground is GroundMode.MINIMAL
    assert structure.shape.layers == 1
    assert structure.shape.rows == 1
    assert structure.shape.columns == 1
    assert structure.cell(0, 0, 0) == Cell(expression="redstone_wire", label="Q")
    assert structure.label_locations("Q") == (CellLocation(0, 0, 0),)


def test_parses_all_header_values() -> None:
    structure = parse(
        """---
dim1: west
dim2: north
dim3: up
solid_block: iron_block
slab: oak_slab
colored_solid_block: wool
transparent_block: tinted_glass
colored_transparent_block: stained_glass
ground: full
---
#
"""
    )

    assert structure.header.dim1 is Direction.WEST
    assert structure.header.dim2 is Direction.NORTH
    assert structure.header.dim3 is Direction.UP
    assert structure.header.solid_block == "iron_block"
    assert structure.header.slab == "oak_slab"
    assert structure.header.colored_solid_block == "wool"
    assert structure.header.transparent_block == "tinted_glass"
    assert structure.header.colored_transparent_block == "stained_glass"
    assert structure.header.ground is GroundMode.FULL
    assert structure.cell(0, 0, 0).expression == "iron_block"


def test_empty_header_uses_defaults() -> None:
    structure = parse("---\n---\n#")

    assert structure.header.dim1 is Direction.EAST
    assert structure.cell(0, 0, 0).expression == "stone"


def test_parses_layers_rows_and_pads_short_layers() -> None:
    structure = parse("#,y,z;\n,\n")

    assert (structure.shape.layers, structure.shape.rows, structure.shape.columns) == (2, 2, 3)
    assert [structure.cell(0, 0, column).expression for column in range(3)] == ["stone", "y", "z"]
    assert all(structure.cell(0, 1, column).is_air for column in range(3))
    assert all(structure.cell(1, 0, column).is_air for column in range(3))
    assert all(structure.cell(1, 1, column).is_air for column in range(3))


def test_preserves_blank_layers() -> None:
    structure = parse("\n\n#")

    assert structure.shape.layers == 3
    assert structure.cell(0, 0, 0).is_air
    assert structure.cell(1, 0, 0).is_air
    assert structure.cell(2, 0, 0).expression == "stone"


def test_parses_readme_annotation_example() -> None:
    structure = parse(".@Q;_|_,-|,.@C;.@D")

    assert structure.shape == structure.shape.__class__(layers=1, rows=3, columns=3)
    assert structure.cell(0, 0, 0) == Cell("redstone_wire", "Q")
    assert structure.cell(0, 1, 0).expression == "repeater[facing=south]"
    assert structure.cell(0, 1, 1).expression == "repeater[facing=east]"
    assert structure.label_locations("C") == (CellLocation(0, 1, 2),)
    assert structure.label_locations("D") == (CellLocation(0, 2, 0),)


def test_labels_can_be_attached_to_air_cells() -> None:
    structure = parse("/,|-,@QC\n#,#,piston")

    assert structure.cell(0, 0, 0).expression == "lever[face=floor]"
    assert structure.shape.layers == 2
    assert structure.shape.rows == 1
    assert structure.shape.columns == 3
    assert structure.cell(0, 0, 2).is_air
    assert structure.cell(0, 0, 2).label == "QC"
    assert structure.label_locations("QC") == (CellLocation(0, 0, 2),)

    padded_air = parse("#,@A")
    assert padded_air.cell(0, 0, 1).is_air
    assert padded_air.label_locations("A") == (CellLocation(0, 0, 1),)


def test_repeated_labels_keep_all_locations() -> None:
    structure = parse("#@A,#@A")

    assert structure.label_locations("A") == (
        CellLocation(0, 0, 0),
        CellLocation(0, 0, 1),
    )


def test_parse_file_reads_utf8(tmp_path: Path) -> None:
    path = tmp_path / "demo.smprd"
    path.write_text("---\nground: none\n---\n#@A", encoding="utf-8")

    structure = parse_file(path)

    assert structure.source == str(path)
    assert structure.header.ground is GroundMode.NONE
    assert structure.label_locations("A") == (CellLocation(0, 0, 0),)


def test_parses_readme_body_example() -> None:
    structure = parse(" , ,.,.,.,|-,.,.,redstone_lamp\n#,#,#,#,#,# ,#,#,")

    assert structure.shape.layers == 2
    assert structure.shape.rows == 1
    assert structure.shape.columns == 9
    assert structure.cell(0, 0, 0).is_air
    assert structure.cell(0, 0, 1).is_air
    assert [structure.cell(0, 0, column).expression for column in range(2, 9)] == [
        "redstone_wire",
        "redstone_wire",
        "redstone_wire",
        "repeater[facing=west]",
        "redstone_wire",
        "redstone_wire",
        "redstone_lamp",
    ]
    assert [structure.cell(1, 0, column).expression for column in range(8)] == ["stone"] * 8
    assert structure.cell(1, 0, 8).is_air


def test_expands_colored_and_transparent_shorthands() -> None:
    structure = parse("white,+white,#,+")

    assert [structure.cell(0, 0, column).expression for column in range(4)] == [
        "white_concrete",
        "white_stained_glass",
        "stone",
        "glass",
    ]


def test_expands_slab_shorthand() -> None:
    structure = parse("---\nslab: oak_slab\n---\n#,=")

    assert [structure.cell(0, 0, column).expression for column in range(2)] == [
        "stone",
        "oak_slab",
    ]


def test_expands_orientation_shorthands() -> None:
    structure = parse(
        """---
dim1: west
dim2: north
---
|-,-:,o-,/-
"""
    )

    assert [structure.cell(0, 0, column).expression for column in range(4)] == [
        "repeater[facing=east]",
        "comparator[facing=west]",
        "redstone_wall_torch[facing=east]",
        "lever[face=wall,facing=east]",
    ]


def test_expands_attributes_and_variables() -> None:
    structure = parse("-o[lit=false],stone_stairs[facing=$dim1]")

    assert structure.cell(0, 0, 0).expression == "redstone_wall_torch[facing=east,lit=false]"
    assert structure.cell(0, 0, 1).expression == "stone_stairs[facing=east]"


def test_expands_boolean_attributes() -> None:
    structure = parse("redstone_lamp[lit],redstone_lamp[!lit],o[!lit]")

    assert structure.cell(0, 0, 0).expression == "redstone_lamp[lit=true]"
    assert structure.cell(0, 0, 1).expression == "redstone_lamp[lit=false]"
    assert structure.cell(0, 0, 2).expression == "redstone_torch[lit=false]"


def test_multiple_attributes_remain_in_one_cell() -> None:
    structure = parse("oak_stairs[facing=north,half=top,shape=inner_left],stone")

    assert structure.shape.columns == 2
    assert structure.cell(0, 0, 0).expression == "oak_stairs[facing=north,half=top,shape=inner_left]"
    assert structure.cell(0, 0, 1).expression == "stone"


def test_explicit_attributes_override_shorthand_defaults() -> None:
    structure = parse("|-[facing=north]")

    assert structure.cell(0, 0, 0).expression == "repeater[facing=north]"


def test_direction_vectors_are_numpy_and_owned_by_direction() -> None:
    east = Direction.EAST.vector
    west = Direction.WEST.vector

    assert isinstance(east, np.ndarray)
    assert isinstance(west, np.ndarray)
    np.testing.assert_array_equal(east, np.array([1, 0, 0], dtype=np.int64))
    np.testing.assert_array_equal(west, np.array([-1, 0, 0], dtype=np.int64))
    assert Direction.EAST.opposite() is Direction.WEST
    assert isinstance(Direction.coordinate_transform(Direction.EAST, Direction.NORTH, Direction.DOWN), np.ndarray)


def test_negative_direction_coordinates_and_bounds() -> None:
    structure = parse("---\ndim1: west\ndim2: north\ndim3: down\n---\n#;\n\n")

    assert structure.shape.layers == 2
    assert structure.shape.rows == 2
    np.testing.assert_array_equal(structure.coordinates(0, 0, 0), np.array([0, 0, 0], dtype=np.int64))
    np.testing.assert_array_equal(structure.coordinates(0, 1, 0), np.array([0, 0, -1], dtype=np.int64))
    np.testing.assert_array_equal(structure.coordinates(1, 0, 0), np.array([0, -1, 0], dtype=np.int64))



def test_large_structure_is_stored_in_nucleation() -> None:
    row = ",".join(["#"] * 64)
    source = ";".join([row] * 64)
    structure = parse(source)

    assert structure.shape == structure.shape.__class__(layers=1, rows=64, columns=64)
    assert structure.schematic.block_count() == 64 * 64
    assert structure.cell(0, 63, 0).expression == "stone"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("---\nunknown: value\n---\n#", "unknown header attribute"),
        ("---\ndim1: up\n---\n#", "invalid value 'up' for 'dim1'"),
        ("---\ndim3: north\n---\n#", "invalid value 'north' for 'dim3'"),
        ("---\ndim1: north\ndim2: south\n---\n#", "different axes"),
        ("---\ndim1: [\n---\n#", "invalid YAML header"),
        ("---\ndim1: 1\n---\n#", "must be a string"),
        ("---\ndim1: east\n#", "missing its closing"),
    ],
)
def test_header_errors_are_reported(text: str, message: str) -> None:
    with pytest.raises(ParseError, match=message):
        parse(text, source="demo.smprd")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (".@", "label must be non-empty"),
        ("#@a@b", "at most one"),
        ("#@Q label", "contain no whitespace"),
        ("repeater[facing=north", "invalid block state syntax"),
        ("repeater[]", "empty block properties"),
        ("redstone_lamp[!]", "invalid block property"),
    ],
)
def test_cell_errors_are_reported(text: str, message: str) -> None:
    with pytest.raises(ParseError, match=message):
        parse(text)


def test_parse_error_has_source_and_location() -> None:
    with pytest.raises(ParseError) as caught:
        parse("#\n@", source="example.smprd")

    error = caught.value
    assert error.source == "example.smprd"
    assert error.line == 2
    assert str(error).startswith("example.smprd:2:")
