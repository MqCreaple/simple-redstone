from pathlib import Path

import pytest

from simple_redstone.cli import main
from simple_redstone.errors import RenderError
from simple_redstone.parser import parse
from simple_redstone.render import RenderOptions, StructureRenderer, render_to_png


def test_render_png_writes_valid_image(tmp_path: Path) -> None:
    structure = parse("---\nground: none\n---\nx,x;x,x")
    output = tmp_path / "nested" / "demo.png"

    rendered = render_to_png(structure, output, width=256, height=192)

    assert rendered == output
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert output.stat().st_size > 500


def test_render_png_bytes_uses_fallback_pack() -> None:
    structure = parse("---\nground: none\n---\nx,.")
    rendered = StructureRenderer(structure).render_png_bytes(RenderOptions(width=160, height=120))

    assert rendered.startswith(b"\x89PNG\r\n\x1a\n")


def test_render_rejects_non_png_output(tmp_path: Path) -> None:
    structure = parse("x")

    with pytest.raises(RenderError, match="must use the .png extension"):
        render_to_png(structure, tmp_path / "demo.bmp")


def test_cli_renders_png(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "demo.smprd"
    source.write_text("x,x", encoding="utf-8")
    output = tmp_path / "demo.png"

    exit_code = main(["render", "-i", str(source), "-o", str(output), "--width", "200", "--height", "150"])

    assert exit_code == 0
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert f"Wrote {output}" in capsys.readouterr().out
