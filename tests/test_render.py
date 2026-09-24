from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from simple_redstone.cli import main
from simple_redstone.errors import RenderError
from simple_redstone.parser import parse
from simple_redstone.render import (
    RenderOptions,
    StructureRenderer,
    _build_viewer_scene,
    _close_on_escape,
    _load_viewer_model,
    render_to_png,
)


def test_render_png_writes_valid_image(tmp_path: Path) -> None:
    structure = parse("---\nground: none\n---\n#,#;#,#")
    output = tmp_path / "nested" / "demo.png"

    rendered = render_to_png(structure, output, width=256, height=192)

    assert rendered == output
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert output.stat().st_size > 500


def test_render_png_bytes_uses_fallback_pack() -> None:
    structure = parse("---\nground: none\n---\n#,.")
    rendered = StructureRenderer(structure).render_png_bytes(RenderOptions(width=160, height=120))

    assert rendered.startswith(b"\x89PNG\r\n\x1a\n")


def test_viewer_model_exports_glb_and_bounds() -> None:
    structure = parse("---\nground: none\n---\n#,#")
    model = StructureRenderer(structure).viewer_model()

    assert model.glb.startswith(b"glTF")
    assert model.bounds_min.shape == (3,)
    assert model.bounds_max.shape == (3,)
    assert np.all(model.bounds_max > model.bounds_min)


def test_viewer_scene_uses_atlas_correct_uvs() -> None:
    import pygfx as gfx

    structure = parse("---\nground: none\n---\n#,#")
    model_data = StructureRenderer(structure).viewer_model()
    model = _load_viewer_model(gfx, model_data.glb)
    scene, camera, target, floor_height = _build_viewer_scene(
        gfx,
        model,
        model_data.bounds_min,
        model_data.bounds_max,
    )

    mesh = next(scene.iter(lambda item: isinstance(item, gfx.Mesh)))
    assert mesh.geometry.texcoords is not None
    assert mesh.material.map is not None
    assert mesh.material.map.mag_filter == "nearest"
    assert camera.width > 0
    assert target.shape == (3,)
    assert floor_height < 0


def test_escape_closes_viewer_window() -> None:
    class FakeCanvas:
        closed = False

        def close(self) -> None:
            self.closed = True

    canvas = FakeCanvas()

    _close_on_escape(canvas, SimpleNamespace(key="a"))
    assert not canvas.closed

    _close_on_escape(canvas, SimpleNamespace(key="Escape"))
    assert canvas.closed


def test_render_rejects_non_png_output(tmp_path: Path) -> None:
    structure = parse("#")

    with pytest.raises(RenderError, match="must use the .png extension"):
        render_to_png(structure, tmp_path / "demo.bmp")


def test_cli_renders_png(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "demo.smprd"
    source.write_text("#,#", encoding="utf-8")
    output = tmp_path / "demo.png"

    exit_code = main(["render", "-i", str(source), "-o", str(output), "--width", "200", "--height", "150"])

    assert exit_code == 0
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert f"Wrote {output}" in capsys.readouterr().out


def test_cli_interactive_dispatches_to_gpu_viewer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "demo.smprd"
    source.write_text("#,#", encoding="utf-8")
    calls: list[tuple[int, int, str | None]] = []

    def fake_render_interactive(
        structure: object,
        *,
        width: int,
        height: int,
        resource_pack: str | None,
    ) -> None:
        calls.append((width, height, resource_pack))

    monkeypatch.setattr("simple_redstone.cli.render_interactive", fake_render_interactive)

    exit_code = main(["render", "-i", str(source), "--width", "640", "--height", "480"])

    assert exit_code == 0
    assert calls == [(640, 480, None)]
