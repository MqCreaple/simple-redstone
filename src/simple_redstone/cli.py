from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .backend import SchematicExporter
from .errors import SimpleRedstoneError
from .model import Structure
from .parser import parse, parse_file
from .render import render_interactive, render_to_png


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="simple-redstone", description="Parse and convert Simple Redstone structures.")
    subparsers = parser.add_subparsers(dest="command")

    check_parser = subparsers.add_parser("check", help="check a structure for rule violations")
    check_parser.add_argument("-i", "--input", help="input .smprd file; defaults to stdin")

    convert_parser = subparsers.add_parser("convert", help="convert a structure to a schematic format")
    convert_parser.add_argument("-i", "--input", help="input .smprd file; defaults to stdin")
    convert_parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="output .schem or .litematic file",
    )

    render_parser = subparsers.add_parser("render", help="render a structure")
    render_parser.add_argument("-i", "--input", help="input .smprd file; defaults to stdin")
    render_parser.add_argument("-o", "--output", help="output PNG file; omit for an interactive window")
    render_parser.add_argument("--resource-pack", help="optional Minecraft resource-pack ZIP")
    render_parser.add_argument("--width", type=int, default=800, help="render width in pixels")
    render_parser.add_argument("--height", type=int, default=600, help="render height in pixels")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0

    try:
        if args.command == "convert":
            structure = _read_structure(args.input)
            output = SchematicExporter.export(structure, args.output)
            print(f"Wrote {output}")
            return 0
        if args.command == "render":
            structure = _read_structure(args.input)
            if args.output:
                output = render_to_png(
                    structure,
                    args.output,
                    width=args.width,
                    height=args.height,
                    resource_pack=args.resource_pack,
                )
                print(f"Wrote {output}")
            else:
                render_interactive(
                    structure,
                    width=args.width,
                    height=args.height,
                    resource_pack=args.resource_pack,
                )
            return 0
    except (OSError, SimpleRedstoneError) as exc:
        print(f"simple-redstone: error: {exc}", file=sys.stderr)
        return 1

    parser.error(f"command {args.command!r} is not implemented yet")
    return 2


def _read_structure(value: str | None) -> Structure:
    if value is None:
        return parse(sys.stdin.read(), source="<stdin>")

    path = Path(value)
    if not path.is_file():
        raise OSError(f"input file does not exist: {value}")
    return parse_file(path)
