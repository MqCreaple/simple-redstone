from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


import yaml
from nucleation import NucleationError, Schematic

from .blocks import expand_block
from .errors import BlockExpansionError, ParseError
from .layout import apply_ground
from .model import (
    Cell,
    CellLocation,
    Direction,
    GridShape,
    GroundMode,
    HeaderConfig,
    Structure,
    coordinates_for,
)

_HEADER_DELIMITER = "---"
_HEADER_FIELDS = frozenset(HeaderConfig.__dataclass_fields__)
_ENUM_FIELDS = {
    "dim1": Direction,
    "dim2": Direction,
    "dim3": Direction,
    "ground": GroundMode,
}
_AIR_BLOCKS = frozenset({"air", "minecraft:air"})


@dataclass(frozen=True, slots=True)
class _SplitInput:
    header: str | None
    body: str
    header_start_line: int
    body_start_line: int


def parse(text: str, *, source: str = "<string>") -> Structure:
    """Parse Simple Redstone text and emit directly into a Nucleation schematic."""

    if not isinstance(text, str):
        raise TypeError("text must be a string")

    split = _split_input(text, source=source)
    header = _parse_header(split.header, source=source, start_line=split.header_start_line) if split.header is not None else HeaderConfig()
    schematic = Schematic.create("simple-redstone")
    shape, labels = _parse_body(
        split.body,
        schematic=schematic,
        header=header,
        source=source,
        start_line=split.body_start_line,
    )
    structure = Structure(header=header, schematic=schematic, shape=shape, labels=labels, source=source)
    apply_ground(structure)
    return structure


def parse_file(path: str | Path) -> Structure:
    """Read and parse a UTF-8 Simple Redstone file."""

    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ParseError(str(exc), source=str(file_path)) from exc
    return parse(text, source=str(file_path))

def _split_input(text: str, *, source: str) -> _SplitInput:
    normalized = text.removeprefix("\ufeff")
    lines = normalized.splitlines(keepends=True)
    if not lines or _delimiter_content(lines[0]) != _HEADER_DELIMITER:
        return _SplitInput(None, normalized, 1, 1)

    closing_index: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if _delimiter_content(line) == _HEADER_DELIMITER:
            closing_index = index
            break

    if closing_index is None:
        raise ParseError("header is missing its closing '---' delimiter", source=source, line=1, column=1)

    header = "".join(lines[1:closing_index])
    body = "".join(lines[closing_index + 1 :])
    return _SplitInput(header=header, body=body, header_start_line=2, body_start_line=closing_index + 2)


def _delimiter_content(line: str) -> str:
    return line.rstrip("\r\n").strip()


def _parse_header(header: str, *, source: str, start_line: int) -> HeaderConfig:
    try:
        data = yaml.safe_load(header)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = start_line + mark.line if mark is not None else start_line
        column = mark.column + 1 if mark is not None else 1
        message = getattr(exc, "problem", None) or str(exc)
        raise ParseError(f"invalid YAML header: {message}", source=source, line=line, column=column) from exc

    if data is None:
        return HeaderConfig()
    if not isinstance(data, Mapping):
        raise ParseError("header must be a YAML mapping", source=source, line=start_line, column=1)

    values: dict[str, Any] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            raise ParseError("header keys must be strings", source=source, line=start_line, column=1)
        if key not in _HEADER_FIELDS:
            raise ParseError(f"unknown header attribute {key!r}", source=source, line=_field_line(header, start_line, key))
        if not isinstance(value, str):
            raise ParseError(f"header attribute {key!r} must be a string", source=source, line=_field_line(header, start_line, key))
        values[key] = value

    converted: dict[str, Any] = dict(values)
    for field_name, enum_type in _ENUM_FIELDS.items():
        if field_name not in values:
            continue
        try:
            converted[field_name] = enum_type(values[field_name])
        except ValueError as exc:
            choices = ", ".join(member.value for member in enum_type)
            raise ParseError(
                f"invalid value {values[field_name]!r} for {field_name!r}; expected one of: {choices}",
                source=source,
                line=_field_line(header, start_line, field_name),
            ) from exc

        value = converted[field_name]
        if field_name in ("dim1", "dim2") and value.axis == "y":
            raise ParseError(
                f"invalid value {values[field_name]!r} for {field_name!r}; expected one of: north, south, east, west",
                source=source,
                line=_field_line(header, start_line, field_name),
            )
        if field_name == "dim3" and value.axis != "y":
            raise ParseError(
                f"invalid value {values[field_name]!r} for {field_name!r}; expected one of: up, down",
                source=source,
                line=_field_line(header, start_line, field_name),
            )

    try:
        return HeaderConfig(**converted)
    except ValueError as exc:
        field_name = "dim2" if "dim1 and dim2" in str(exc) else None
        raise ParseError(
            f"invalid header configuration: {exc}",
            source=source,
            line=_field_line(header, start_line, field_name) if field_name else start_line,
        ) from exc


def _field_line(header: str, start_line: int, field_name: str) -> int:
    prefix = f"{field_name}:"
    for offset, line in enumerate(header.splitlines()):
        if line.lstrip().startswith(prefix):
            return start_line + offset
    return start_line

def _parse_body(
    body: str,
    *,
    schematic: Schematic,
    header: HeaderConfig,
    source: str,
    start_line: int,
) -> tuple[GridShape, dict[str, tuple[CellLocation, ...]]]:
    if body == "":
        return GridShape(0, 0, 0), {}

    raw_layers = body.splitlines()
    max_rows = max((len(layer.split(";")) for layer in raw_layers), default=0)
    max_columns = 0
    labels: dict[str, list[CellLocation]] = {}

    for layer_index, layer_text in enumerate(raw_layers):
        raw_rows = layer_text.split(";")
        for row_index, row_text in enumerate(raw_rows):
            raw_cells = _split_cells(row_text)
            max_columns = max(max_columns, len(raw_cells))
            column_offset = 1
            for column_index, raw_cell in enumerate(raw_cells):
                cell = _parse_cell(
                    raw_cell,
                    source=source,
                    line=start_line + layer_index,
                    column=column_offset,
                )
                if cell.label is not None:
                    labels.setdefault(cell.label, []).append(CellLocation(layer_index, row_index, column_index))
                if not cell.is_air:
                    _emit_cell(
                        cell,
                        schematic=schematic,
                        header=header,
                        layer=layer_index,
                        row=row_index,
                        column=column_index,
                        source=source,
                        line=start_line + layer_index,
                        source_column=column_offset,
                    )
                column_offset += len(raw_cell) + 1

    shape = GridShape(len(raw_layers), max_rows, max_columns)
    _anchor_bounds(schematic, header, shape)
    frozen_labels = {label: tuple(locations) for label, locations in labels.items()}
    return shape, frozen_labels


def _emit_cell(
    cell: Cell,
    *,
    schematic: Schematic,
    header: HeaderConfig,
    layer: int,
    row: int,
    column: int,
    source: str,
    line: int,
    source_column: int,
) -> None:
    try:
        block = expand_block(cell.expression, header)
    except BlockExpansionError as exc:
        raise ParseError(str(exc), source=source, line=line, column=source_column) from exc

    coordinates = coordinates_for(header, CellLocation(layer, row, column).as_vector())
    try:
        schematic.set_block_from_string(*coordinates, block)
    except Exception as exc:
        raise ParseError(
            f"invalid Minecraft block state {block!r}: {exc}",
            source=source,
            line=line,
            column=source_column,
        ) from exc


def _anchor_bounds(schematic: Schematic, header: HeaderConfig, shape: GridShape) -> None:
    if not shape.volume:
        return

    locations = (
        CellLocation(0, 0, 0),
        CellLocation(shape.layers - 1, shape.rows - 1, shape.columns - 1),
    )
    for location in locations:
        coordinates = coordinates_for(header, location.as_vector())
        try:
            current = schematic.get_block_string(*coordinates)
        except NucleationError:
            current = "air"
        if current in _AIR_BLOCKS:
            schematic.set_block_from_string(*coordinates, "air")

def _split_cells(row: str) -> list[str]:
    """Split a row on commas outside block-state property brackets."""

    cells: list[str] = []
    start = 0
    bracket_depth = 0
    for index, character in enumerate(row):
        if character == "[":
            bracket_depth += 1
        elif character == "]" and bracket_depth:
            bracket_depth -= 1
        elif character == "," and bracket_depth == 0:
            cells.append(row[start:index])
            start = index + 1
    cells.append(row[start:])
    return cells


def _parse_cell(raw: str, *, source: str, line: int, column: int) -> Cell:
    value = raw.strip()
    if not value:
        return Cell()

    if value.count("@") > 1:
        raise ParseError("cell may contain at most one '@' annotation", source=source, line=line, column=column)

    if "@" in value:
        expression, label = value.rsplit("@", 1)
        expression = expression.strip()
        label = label.strip()
        if not label or any(character.isspace() for character in label):
            raise ParseError("annotation label must be non-empty and contain no whitespace", source=source, line=line, column=column)
        return Cell(expression=expression, label=label)

    return Cell(expression=value)
