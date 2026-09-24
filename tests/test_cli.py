import io
from pathlib import Path

import pytest
from nucleation import Schematic

from simple_redstone.cli import main


@pytest.mark.parametrize("extension", [".schem", ".litematic"])
def test_cli_converts_file_to_supported_format(tmp_path: Path, capsys: pytest.CaptureFixture[str], extension: str) -> None:
    source = tmp_path / "demo.smprd"
    source.write_text("#,#;#,#", encoding="utf-8")
    output = tmp_path / "nested" / f"demo{extension}"

    exit_code = main(["convert", "-i", str(source), "-o", str(output)])

    assert exit_code == 0
    assert output.is_file()
    assert f"Wrote {output}" in capsys.readouterr().out
    assert Schematic.load_from_file(str(output)).block_count() == 4


def test_cli_rejects_inline_input(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "demo.schem"

    exit_code = main(["convert", "-i", "#,#", "-o", str(output)])

    assert exit_code == 1
    assert "input file does not exist: #,#" in capsys.readouterr().err
    assert not output.exists()


def test_cli_rejects_dash_as_input_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "stdin.litematic"

    exit_code = main(["convert", "-i", "-", "-o", str(output)])

    assert exit_code == 1
    assert "input file does not exist: -" in capsys.readouterr().err
    assert not output.exists()


def test_cli_defaults_to_stdin_when_input_is_omitted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "stdin.schem"
    monkeypatch.setattr("sys.stdin", io.StringIO("#,#"))

    exit_code = main(["convert", "-o", str(output)])

    assert exit_code == 0
    assert Schematic.load_from_file(str(output)).block_count() == 2


def test_cli_reports_unsupported_nbt(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "demo.nbt"
    source = tmp_path / "demo.smprd"
    source.write_text("#", encoding="utf-8")

    exit_code = main(["convert", "-i", str(source), "-o", str(output)])

    assert exit_code == 1
    assert "does not support Java .nbt" in capsys.readouterr().err
    assert not output.exists()


def test_cli_reports_missing_input_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "demo.schem"

    exit_code = main(["convert", "-i", str(tmp_path / "missing.smprd"), "-o", str(output)])

    assert exit_code == 1
    assert "input file does not exist" in capsys.readouterr().err
