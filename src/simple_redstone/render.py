"""PNG and interactive rendering support."""

from __future__ import annotations

import base64
import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from nucleation import MeshConfig, MeshResult, NucleationError, RenderConfig, Renderer, ResourcePack, ResourcePackList
from numpy.typing import NDArray

from .errors import RenderError
from .model import Structure


@dataclass(frozen=True, slots=True)
class RenderOptions:
    width: int = 800
    height: int = 600
    resource_pack: Path | None = None
    yaw: float = -45.0
    pitch: float = 30.0
    zoom: float = 1.0

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise RenderError("render dimensions must be positive")
        if self.zoom <= 0:
            raise RenderError("render zoom must be positive")


@dataclass(frozen=True, slots=True)
class ViewerModel:
    """A GPU-ready GLB and its world-space bounds."""

    glb: bytes
    bounds_min: NDArray[np.float32]
    bounds_max: NDArray[np.float32]


class StructureRenderer:
    """Render a Structure through Nucleation with optional Minecraft assets."""

    def __init__(self, structure: Structure, resource_pack: Path | None = None) -> None:
        self.structure = structure
        self.resource_pack = self._load_resource_pack(resource_pack) if resource_pack else _fallback_resource_pack(structure)

    def render_options(self, options: RenderOptions) -> RenderConfig:
        config = RenderConfig.create(options.width, options.height)
        config.set_isometric()
        config.set_sphere_fit(True)
        config.set_yaw(options.yaw)
        config.set_pitch(options.pitch)
        config.set_zoom(options.zoom)
        config.set_background(0.08, 0.09, 0.11, 1.0)
        config.set_fitted_grid(4, 1, 0.0, True, 0.35, 0.38, 0.42, 0.55)
        return config

    def render_png(self, output: str | Path, options: RenderOptions | None = None) -> Path:
        render_options = options or RenderOptions()
        output_path = Path(output)
        if output_path.suffix.lower() != ".png":
            raise RenderError("render output must use the .png extension")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            Renderer.render_to_file_with_pack(
                self.structure.schematic,
                self.resource_pack,
                self.render_options(render_options),
                str(output_path),
            )
        except NucleationError as exc:
            raise RenderError(f"failed to render structure: {exc}") from exc
        return output_path

    def render_png_bytes(self, options: RenderOptions | None = None) -> bytes:
        render_options = options or RenderOptions()
        try:
            encoded = Renderer.render_png_b64_with_pack(
                self.structure.schematic,
                self.resource_pack,
                self.render_options(render_options),
            )
        except NucleationError as exc:
            raise RenderError(f"failed to render structure: {exc}") from exc
        return base64.b64decode(encoded)

    def viewer_model(self) -> ViewerModel:
        """Export a GLB with atlas-correct UVs for interactive rendering."""

        config = MeshConfig.create()
        config.set_cull_hidden_faces(True)
        config.set_cull_occluded_blocks(True)
        config.set_greedy_meshing(True)
        try:
            exported = MeshResult.create(self.structure.schematic, self.resource_pack, config)
        except NucleationError as exc:
            raise RenderError(f"failed to build interactive model: {exc}") from exc

        bounds = exported.bounds()
        return ViewerModel(
            glb=base64.b64decode(exported.glb_data_b64()),
            bounds_min=np.array([bounds.min_x, bounds.min_y, bounds.min_z], dtype=np.float32),
            bounds_max=np.array([bounds.max_x, bounds.max_y, bounds.max_z], dtype=np.float32),
        )

    @staticmethod
    def _load_resource_pack(path: Path) -> ResourcePack:
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise RenderError(f"cannot read resource pack {path}: {exc}") from exc
        try:
            return ResourcePack.from_bytes(list(data))
        except Exception as exc:
            raise RenderError(f"invalid resource pack {path}: {exc}") from exc


def render_to_png(
    structure: Structure,
    output: str | Path,
    *,
    width: int = 800,
    height: int = 600,
    resource_pack: str | Path | None = None,
) -> Path:
    pack_path = Path(resource_pack) if resource_pack is not None else None
    options = RenderOptions(width=width, height=height, resource_pack=pack_path)
    return StructureRenderer(structure, pack_path).render_png(output, options)


def render_interactive(
    structure: Structure,
    *,
    width: int = 900,
    height: int = 700,
    resource_pack: str | Path | None = None,
) -> None:
    if width <= 0 or height <= 0:
        raise RenderError("render dimensions must be positive")

    try:
        import pygfx as gfx
        from rendercanvas.auto import RenderCanvas
    except ImportError as exc:
        raise RenderError("interactive rendering requires pygfx and glfw") from exc

    pack_path = Path(resource_pack) if resource_pack is not None else None
    renderer = StructureRenderer(structure, pack_path)
    model_data = renderer.viewer_model()
    if np.any(model_data.bounds_min == model_data.bounds_max):
        raise RenderError("structure does not contain any visible blocks")

    model = _load_viewer_model(gfx, model_data.glb)
    scene, camera, target, floor_height = _build_viewer_scene(
        gfx,
        model,
        model_data.bounds_min,
        model_data.bounds_max,
    )

    try:
        canvas = RenderCanvas(size=(width, height), title="Simple Redstone Renderer", max_fps=60)
        renderer = gfx.WgpuRenderer(canvas)
        controller = gfx.OrbitController(camera, target=target, register_events=renderer)

        def close_on_escape(event: Any) -> None:
            _close_on_escape(canvas, event)

        renderer.add_event_handler(close_on_escape, "key_down")
        gfx.show(
            scene,
            canvas=canvas,
            renderer=renderer,
            controller=controller,
            camera=camera,
        )
    except Exception as exc:
        if "canvas" in locals():
            canvas.close()
        raise RenderError(f"failed to open interactive renderer: {exc}") from exc


def _close_on_escape(canvas: Any, event: Any) -> None:
    if getattr(event, "key", None) == "Escape":
        canvas.close()


def _load_viewer_model(gfx: Any, glb: bytes) -> Any:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as file:
            file.write(glb)
            temp_path = Path(file.name)
        loaded = gfx.load_gltf(str(temp_path), quiet=True)
    except Exception as exc:
        raise RenderError(f"failed to load interactive GLB: {exc}") from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    model = loaded.scene
    if model is None:
        raise RenderError("interactive GLB does not contain a scene")

    for mesh in model.iter(lambda item: isinstance(item, gfx.Mesh)):
        for map_name in ("map", "emissive_map", "specular_map"):
            texture_map = getattr(mesh.material, map_name, None)
            if isinstance(texture_map, gfx.TextureMap):
                texture_map.mag_filter = "nearest"
                texture_map.min_filter = "nearest"
                texture_map.mipmap_filter = "nearest"
    return model


def _build_viewer_scene(
    gfx: Any,
    model: Any,
    bounds_min: NDArray[np.float32],
    bounds_max: NDArray[np.float32],
) -> tuple[Any, Any, NDArray[np.float32], float]:
    center = ((bounds_min + bounds_max) * 0.5).astype(np.float32)
    extent = bounds_max - bounds_min
    radius = max(float(np.linalg.norm(extent)) * 0.5, 1.0)
    model.local.position = -center

    scene = gfx.Scene()
    scene.add(gfx.Background(None, gfx.BackgroundMaterial("#12161d")))
    scene.add(gfx.AmbientLight("#ffffff", 0.7))
    key_light = gfx.DirectionalLight("#ffffff", 1.8)
    key_light.local.position = (radius, radius * 2, radius)
    scene.add(key_light)
    fill_light = gfx.DirectionalLight("#c8d8ff", 0.6)
    fill_light.local.position = (-radius, radius, -radius)
    scene.add(fill_light)

    floor_height = float(bounds_min[1] - center[1] - 0.01)
    grid = gfx.Grid(
        None,
        gfx.GridMaterial(
            major_step=1.0,
            minor_step=0.25,
            major_thickness=1.0,
            minor_thickness=0.0,
            axis_thickness=2.0,
            axis_color="#69717d",
            major_color="#3d444e",
            minor_color="#2b3038",
        ),
        orientation="xz",
    )
    grid.local.position = (0.0, floor_height, 0.0)
    scene.add(grid)
    scene.add(model)

    camera = gfx.PerspectiveCamera(50, width=radius * 2, height=radius * 2)
    camera.show_object(model, view_dir=(-1, -1, -1), up=(0, 1, 0), scale=1.25)
    return scene, camera, np.zeros(3, dtype=np.float32), floor_height


def _fallback_resource_pack(structure: Structure) -> ResourcePack:
    pack = ResourcePack.from_list(ResourcePackList.create())
    palette = json.loads(structure.schematic.all_palettes_json())
    block_states = sorted(
        {
            name
            for names in palette.values()
            for name in names
            if name not in ("air", "minecraft:air")
        }
    )
    for block_state in block_states:
        block_name = block_state if ":" in block_state else f"minecraft:{block_state}"
        path = block_name.split(":", 1)[1]
        safe_name = path.replace("/", "_")
        texture_name = f"minecraft:block/simple_redstone_fallback/{safe_name}"
        model_name = f"minecraft:block/simple_redstone_fallback/{safe_name}"
        pack.add_texture(texture_name, 16, 16, _fallback_texture(block_name))
        pack.add_model_json(model_name, _cube_model(texture_name))
        pack.add_blockstate_json(block_name, json.dumps({"variants": {"": {"model": model_name}}}))
    return pack


def _fallback_texture(block_name: str) -> list[int]:
    if "redstone" in block_name:
        color = np.array([190, 24, 24], dtype=np.uint8)
    elif "repeater" in block_name or "comparator" in block_name:
        color = np.array([205, 70, 25], dtype=np.uint8)
    elif "glass" in block_name:
        color = np.array([135, 205, 220], dtype=np.uint8)
    elif "lever" in block_name:
        color = np.array([105, 78, 52], dtype=np.uint8)
    else:
        digest = hashlib.sha256(block_name.encode("utf-8")).digest()
        color = np.array([80 + digest[0] % 150, 80 + digest[1] % 150, 80 + digest[2] % 150], dtype=np.uint8)

    pixels = np.empty((16, 16, 4), dtype=np.uint8)
    pixels[..., :3] = color
    pixels[..., 3] = 255
    pixels[0, :, :3] = np.maximum(color // 2, 0)
    pixels[-1, :, :3] = np.maximum(color // 2, 0)
    pixels[:, 0, :3] = np.maximum(color // 2, 0)
    pixels[:, -1, :3] = np.maximum(color // 2, 0)
    return pixels.reshape(-1).tolist()


def _cube_model(texture_name: str) -> str:
    faces = {face: {"texture": "#all"} for face in ("down", "up", "north", "south", "west", "east")}
    return json.dumps(
        {
            "textures": {"all": texture_name},
            "elements": [{"from": [0, 0, 0], "to": [16, 16, 16], "faces": faces}],
        }
    )
