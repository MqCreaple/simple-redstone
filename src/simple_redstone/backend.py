from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from nucleation import StoreIo

from .errors import BackendError
from .model import Structure


class SchematicFormat(StrEnum):
    """Formats supported by the installed Nucleation backend."""

    SCHEM = "schematic"
    LITEMATIC = "litematic"

    @property
    def extension(self) -> str:
        return {
            SchematicFormat.SCHEM: ".schem",
            SchematicFormat.LITEMATIC: ".litematic",
        }[self]

    @classmethod
    def from_path(cls, path: str | Path) -> SchematicFormat:
        suffix = Path(path).suffix.lower()
        if suffix == ".nbt":
            raise BackendError(
                "Nucleation does not support Java .nbt exports; use .schem or .litematic"
            )
        for schematic_format in cls:
            if suffix == schematic_format.extension:
                return schematic_format
        supported = ", ".join(schematic_format.extension for schematic_format in cls)
        raise BackendError(f"unsupported output format {suffix or '<none>'!r}; expected one of: {supported}")


class SchematicExporter:
    """Write parsed structures through Nucleation's format-aware exporter."""

    SUPPORTED_EXTENSIONS: ClassVar[tuple[str, ...]] = tuple(
        schematic_format.extension for schematic_format in SchematicFormat
    )

    @classmethod
    def export(cls, structure: Structure, output: str | Path) -> Path:
        output_path = Path(output)
        schematic_format = SchematicFormat.from_path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        version = StoreIo.default_format_version(schematic_format.value)
        structure.schematic.save_to_file_with_format(
            str(output_path),
            schematic_format.value,
            version,
        )
        return output_path


def convert_structure(structure: Structure, output: str | Path) -> Path:
    return SchematicExporter.export(structure, output)
