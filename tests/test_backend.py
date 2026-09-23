from pathlib import Path

import pytest
from nucleation import Schematic

from simple_redstone.backend import SchematicExporter, convert_structure
from simple_redstone.errors import BackendError
from simple_redstone.parser import parse


@pytest.mark.parametrize("extension", [".schem", ".litematic"])
def test_backend_writes_and_reloads_supported_formats(tmp_path: Path, extension: str) -> None:
    structure = parse("x,x;x,x")
    output = tmp_path / f"demo{extension}"

    written = convert_structure(structure, output)

    assert written == output
    assert output.is_file()
    loaded = Schematic.load_from_file(str(output))
    assert loaded.block_count() == 4
    assert loaded.get_block_string(0, 0, 0) == "stone"


def test_backend_rejects_java_nbt(tmp_path: Path) -> None:
    structure = parse("x")
    output = tmp_path / "demo.nbt"

    with pytest.raises(BackendError, match="does not support Java \\.nbt"):
        convert_structure(structure, output)


def test_backend_rejects_unknown_extension(tmp_path: Path) -> None:
    structure = parse("x")
    output = tmp_path / "demo.bin"

    with pytest.raises(BackendError, match="unsupported output format"):
        convert_structure(structure, output)


def test_schematic_exporter_advertises_only_supported_formats() -> None:
    assert SchematicExporter.SUPPORTED_EXTENSIONS == (".schem", ".litematic")
