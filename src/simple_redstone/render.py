"""PNG and interactive rendering support."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from nucleation import NucleationError, RenderConfig, Renderer, ResourcePack, ResourcePackList

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
    try:
        import tkinter as tk
    except ImportError as exc:
        raise RenderError("interactive rendering requires tkinter") from exc

    pack_path = Path(resource_pack) if resource_pack is not None else None
    renderer = StructureRenderer(structure, pack_path)
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise RenderError(f"cannot open interactive renderer: {exc}") from exc

    root.title("Simple Redstone Renderer")
    canvas = tk.Canvas(root, width=width, height=height, highlightthickness=0)
    canvas.pack()

    state = {"yaw": -45.0, "pitch": 30.0, "zoom": 1.0, "drag": None, "scheduled": False, "image": None}

    def draw() -> None:
        state["scheduled"] = False
        options = RenderOptions(width=width, height=height, resource_pack=pack_path, yaw=state["yaw"], pitch=state["pitch"], zoom=state["zoom"])
        try:
            image = tk.PhotoImage(data=base64.b64encode(renderer.render_png_bytes(options)).decode("ascii"))
        except RenderError as exc:
            root.destroy()
            raise exc
        state["image"] = image
        canvas.delete("all")
        canvas.create_image(width // 2, height // 2, image=image)

    def schedule_draw() -> None:
        if not state["scheduled"]:
            state["scheduled"] = True
            root.after(50, draw)

    def start_drag(event: Any) -> None:
        state["drag"] = (event.x, event.y)

    def drag(event: Any) -> None:
        previous = state["drag"]
        if previous is None:
            return
        state["yaw"] += (event.x - previous[0]) * 0.5
        state["pitch"] = max(-89.0, min(89.0, state["pitch"] + (event.y - previous[1]) * 0.5))
        state["drag"] = (event.x, event.y)
        schedule_draw()

    def stop_drag(_: Any) -> None:
        state["drag"] = None

    def zoom(event: Any) -> None:
        factor = 1.1 if event.delta > 0 else 1 / 1.1
        state["zoom"] = max(0.1, min(10.0, state["zoom"] * factor))
        schedule_draw()

    canvas.bind("<ButtonPress-1>", start_drag)
    canvas.bind("<B1-Motion>", drag)
    canvas.bind("<ButtonRelease-1>", stop_drag)
    canvas.bind("<MouseWheel>", zoom)
    root.bind("<Escape>", lambda _: root.destroy())
    draw()
    root.mainloop()


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
