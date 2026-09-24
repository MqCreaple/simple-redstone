from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import BlockExpansionError
from .model import HeaderConfig

_COLORS = frozenset(
    {
        "white",
        "orange",
        "magenta",
        "light_blue",
        "yellow",
        "lime",
        "pink",
        "gray",
        "light_gray",
        "cyan",
        "purple",
        "blue",
        "brown",
        "green",
        "red",
        "black",
    }
)

_VARIABLE_PATTERN = re.compile(
    r"\$(?P<negative>-?)(?P<field>dim[123]|solid_block|slab|colored_solid_block|transparent_block|colored_transparent_block)\b"
)


@dataclass(frozen=True, slots=True)
class _Expansion:
    base: str
    properties: tuple[tuple[str, str], ...] = ()


_SHORTHANDS: dict[str, _Expansion] = {
    "#": _Expansion("$solid_block"),
    "=": _Expansion("$slab"),
    "+": _Expansion("$transparent_block"),
    ".": _Expansion("redstone_wire"),
    "|-": _Expansion("repeater", (("facing", "$-dim1"),)),
    "-|": _Expansion("repeater", (("facing", "$dim1"),)),
    "^|^": _Expansion("repeater", (("facing", "$-dim2"),)),
    "_|_": _Expansion("repeater", (("facing", "$dim2"),)),
    ":-": _Expansion("comparator", (("facing", "$-dim1"),)),
    "-:": _Expansion("comparator", (("facing", "$dim1"),)),
    "*|*": _Expansion("comparator", (("facing", "$-dim2"),)),
    ".|.": _Expansion("comparator", (("facing", "$dim2"),)),
    "o": _Expansion("redstone_torch"),
    "o-": _Expansion("redstone_wall_torch", (("facing", "$-dim1"),)),
    "-o": _Expansion("redstone_wall_torch", (("facing", "$dim1"),)),
    "_o": _Expansion("redstone_wall_torch", (("facing", "$-dim2"),)),
    "^o": _Expansion("redstone_wall_torch", (("facing", "$dim2"),)),
    "/": _Expansion("lever", (("face", "floor"),)),
    "\\": _Expansion("lever", (("face", "ceiling"),)),
    "/-": _Expansion("lever", (("face", "wall"), ("facing", "$-dim1"))),
    "\\-": _Expansion("lever", (("face", "wall"), ("facing", "$-dim1"))),
    "-/": _Expansion("lever", (("face", "wall"), ("facing", "$dim1"))),
    "-\\": _Expansion("lever", (("face", "wall"), ("facing", "$dim1"))),
    "_/": _Expansion("lever", (("face", "wall"), ("facing", "$-dim2"))),
    "_\\": _Expansion("lever", (("face", "wall"), ("facing", "$-dim2"))),
    "^/": _Expansion("lever", (("face", "wall"), ("facing", "$dim2"))),
    "^\\": _Expansion("lever", (("face", "wall"), ("facing", "$dim2"))),
}


def expand_block(expression: str, header: HeaderConfig) -> str:
    """Expand a full block state or Simple Redstone shorthand."""

    base, explicit_properties = _split_expression(expression)
    expansion = _resolve_shorthand(base, header)

    properties: dict[str, str] = {}
    for key, value in expansion.properties:
        properties[_resolve_variables(key, header)] = _resolve_variables(value, header)
    for key, value in explicit_properties:
        properties[_resolve_variables(key, header)] = _resolve_variables(value, header)

    resolved_base = _resolve_variables(expansion.base, header)
    if not properties:
        return resolved_base
    rendered = ",".join(f"{key}={value}" for key, value in properties.items())
    return f"{resolved_base}[{rendered}]"

def _split_expression(expression: str) -> tuple[str, tuple[tuple[str, str], ...]]:
    value = expression.strip()
    if not value:
        raise BlockExpansionError("empty block expression")

    if not value.count("["):
        return value, ()

    opening = value.find("[")
    if opening <= 0 or not value.endswith("]") or value.count("[") != 1 or value.count("]") != 1:
        raise BlockExpansionError(f"invalid block state syntax: {expression!r}")

    base = value[:opening].strip()
    property_text = value[opening + 1 : -1]
    if not base:
        raise BlockExpansionError("block name cannot be empty")
    return base, _parse_properties(property_text, expression)


def _parse_properties(property_text: str, expression: str) -> tuple[tuple[str, str], ...]:
    if not property_text:
        raise BlockExpansionError(f"empty block properties: {expression!r}")

    properties: list[tuple[str, str]] = []
    for raw_property in property_text.split(","):
        raw_property = raw_property.strip()
        if raw_property.startswith("!"):
            key, value = raw_property[1:].strip(), "false"
            if not key or "=" in key:
                raise BlockExpansionError(f"invalid block property {raw_property!r} in {expression!r}")
        elif "=" in raw_property:
            if raw_property.count("=") != 1:
                raise BlockExpansionError(f"invalid block property {raw_property!r} in {expression!r}")
            key, value = (part.strip() for part in raw_property.split("=", 1))
        else:
            key, value = raw_property, "true"
        if not key or not value:
            raise BlockExpansionError(f"invalid block property {raw_property!r} in {expression!r}")
        properties.append((key, value))
    return tuple(properties)


def _resolve_shorthand(base: str, header: HeaderConfig) -> _Expansion:
    if base in _COLORS:
        return _Expansion(f"{base}_$colored_solid_block")
    if base.startswith("+") and base[1:] in _COLORS:
        return _Expansion(f"{base[1:]}_$colored_transparent_block")
    if base in _SHORTHANDS:
        return _SHORTHANDS[base]
    return _Expansion(_resolve_variables(base, header))


def _resolve_variables(value: str, header: HeaderConfig) -> str:
    def replace(match: re.Match[str]) -> str:
        field_name = match.group("field")
        if field_name.startswith("dim"):
            direction = getattr(header, field_name)
            if match.group("negative"):
                direction = direction.opposite()
            return direction.value
        if match.group("negative"):
            raise BlockExpansionError(f"cannot negate non-direction variable {field_name!r}")
        return getattr(header, field_name)

    return _VARIABLE_PATTERN.sub(replace, value)
