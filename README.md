# Simple Redstone

Simple Redstone defines a pure ASCII format to encode Minecraft redstone structures. This repo provides the definition of Simple Redstone format and utility scripts to convert it into Minecraft schematics, commands, etc.

## Code Format

A Simple Redstone file consists of an optional YAML header and an ASCII body. The header specifies the structure's metadata (e.g. orientations, block choices, ...). The body encodes the blocks in the structure. A Simple Redstone structure usually look like this:

```plaintext
---
dim1: west
dim2: north
solid_block: iron_block
---
 , ,.,.,.,|-,.,.,redstone_lamp
x,x,x,x,x,x ,x,x,
```

Or, the header can be omitted, in which case all configurations are set to their default values.

```plaintext
 , ,.,.,.,|-,.,.,redstone_lamp
x,x,x,x,x,x ,x,x,
```

### Header

Here are the full list of configurable attributes in the header in Simple Redstone v0.1.0.

| Attribute | Meaning | Values | Default |
|:---------:|:-------:|:------:|:-------:|
| `dim1` | The orientation of the first dimension. | `north`, `south`, `east`, `west` | `east` |
| `dim2` | The orientation of the second dimension. Must be a different axis from `dim1`. That is, if `dim1` is `south`, then `dim2` can only be west or east. | `north`, `south`, `east`, `west` | `south` |
| `dim3` | The orientation of the third dimension. | `up`, `down` | `down` |
| `solid_block` | The type of solid block / opaque block chosen for the structure. | Any Minecraft solid block | `stone` |
| `colored_solid_block` | The type of colored solid block chosen for the structure. | Any block name suffix for colored solid blocks | `concrete` |
| `transparent_block` | The type of transparent block chosen for the structure. | Any Minecraft transparent block | `glass` |
| `colored_transparent_block` | The type of colored transparent block chosen for the structure. | Any block name suffix for colored transparent blocks | `stained_glass` |
| `ground` | Specifies the additional ground layer attached to the very bottom of the structure. `none` means no additional ground layer; `minimal` means only attaching `solid_block` to positions requiring attachment blocks (e.g. with redstone wires above it); `full` means adding a full layer filled with `solid_block`. | `none`, `minimal`, `full` | `minimal` |

### Body

The body uses a CSV-like format to encode the blocks in the structure, except that it encodes a 3-dimensional array of blocks instead of a 2-dimensional table. Commas (`,`) are used to separate blocks. Colons (`;`) are used to separate rows of blocks. Newlines are used to separate layers.

Each row goes along the `dim1` direction specified in the header. The rows are stacked together along the `dim2` direction into layers. Finally, the layers are stacked together along the `dim3` direction.

Each cell in this table is a Minecraft block. The block can either be represented by its full name or its shorthand name. The full name is the same as how you will represent them in Minecraft commands. For example, `stone`, `stone_slab[type=top]`, `oak_leaves[persistent=true,waterlogged=true]` are all valid full names. Since the structure's `dim1`, `dim2`, and `dim3` values can be changed, we also allow inserting these variables in the data fields. For example, `stone_stairs[facing=$dim1]` and `stone_stairs[facing=$-dim1]` represents the stone stairs with its full side facing the direction of `dim1` and the opposite direction to `dim1`.

The shorthand names of common redstone blocks are given in the following table. Symbols in brackets denote alternative representations of the same symbol.

| Shorthand | Meaning | Equivalent Full Name |
|:---------:|:-------:|:--------------------:|
| `x` | Default solid block | `$solid_block` |
| `white`, `orange`, `magenta`, ... | Colored solid block | `<color-name>` + `_` + `$colored_solid_block` |
| `+` | Default transparent block | `$transparent_block` |
| `+white`, `+orange`, `+magenta`, ... | Colored transparent block | `<color-name>` + `_` + `$colored_transparent_block` |
| `.` | Redstone wire with automatic neighbor connection | `redstone_wire` |
| `\|-`, `-\|`, `^\|^`, `_\|_` | Redstone repeater orienting toward `-dim1`, `dim1`, `-dim2`, and `dim2` respectively | `repeater[facing=$-dim1]`, `repeater[facing=$dim1]`, `repeater[facing=$-dim2]`, `repeater[facing=$dim2]` |
| `:-`, `-:`, `*\|*`, `.\|.` | Redstone comparator orienting toward `-dim1`, `dim1`, `-dim2`, and `dim2` respectively | `comparator[facing=$-dim1]`, `comparator[facing=$dim1]`, `comparator[facing=$-dim2]`, `comparator[facing=$dim2]` |
| `o` | Redstone torch attached to the bottom block | `redstone_torch` |
| `o-`, `-o`, `_o`, `^o` | Redstone torch facing `-dim1`, `dim1`, `-dim2`, and `dim2` direction respectively | `redstone_wall_torch[facing=$-dim1]`, `redstone_wall_torch[facing=$dim1]`, `redstone_wall_torch[facing=$-dim2]`, `redstone_wall_torch[facing=$dim2]` |
| `/` | Lever attached to the floor | `lever[face=floor]` |
| `\` | Lever attached to the ceiling | `lever[face=ceiling]` |
| `/-` (`\-`), `-/` (`-\`), `_/` (`_\`), `^/` (`^\`) | Lever facing `-dim1`, `dim1`, `-dim2`, and `dim2` direction respectively | `lever[face=wall,facing=$-dim1]`, `lever[face=wall,facing=$dim1]`, `lever[face=wall,facing=$-dim2]`, `lever[face=wall,facing=$dim2]` |

Note that for repeaters and comparators, their blocks' `facing` fields are the directions **from their output to their input**, opposite from the directions of the redstone signals. This is a little counterintuitive. The symbols for repeaters and comparators are intended to mimic the shaes of their in-game appearances: the dash `-` and the long bar `|` point to the directions redstone signals flow.

Also note that `facing` directions of redstone torches and levers are the opposite to the blocks they are attached to. A redstone torch facing north is attached to the north-facing side of the block at the south of that torch.

The shorthands can also have attributes attached to them. For example, `-o[lit=false]` will expand to `redstone_wall_torch[facing=$dim1,lit=false]`.

Empty cells are treated as air blocks. If a row has fewer than expected number of blocks, or if a layer has fewer than expected number of rows, they are padded with air blocks.

The first block (either a concrete block or an air block) is assigned with position (0, 0, 0). Blocks after it will be assigned with consecutive coordinates.

### Annotations

Occasionally, we need to refer to certain blocks or components in the structure, in which case we need to label them in the structure's Simple Redstone text encoding with the `@` symbol. The `@` labels are ignored in the actual structure generation. They only serve as a convenient way to reference the blocks.

For example. The structure

```plaintext
.@Q;_|_,-|,.@C;.@D
```

is the classical gated D latch with 2 repeaters. Its spatial structure is shown in the following table.

|| col 1 | col 2 | col 3 |
|-|-|-|-|
|row 1| `.@Q` | | |
|row 2| `_\|_` | `-\|` | `.@C` |
|row 3| `.@D` | | |

`.@Q` is the output redstone wire. `.@C` is the control wire. `.@D` is the data (input) wire.

Tags can also be added to air blocks to indicate a vacant position. For example,

```plaintext
/,|-,@QC
x,x,piston
```

The label `@QC` is on an air block, which indicates the quasi-connectivity point of the piston.

## Usage

The command-line program `simple-redstone` takes in a `.smprd` file or reads a Simple Redstone encoded string from stdin, and performs the operation specified by the command arguments. Here are some examples:

```shell
# Check for rule violations in a structure (e.g. incorrect attachment of blocks, ...)
simple-redstone check -i demo.smprd

# Converting a Simple Redstone structure to WorldEdit schematic
simple-redstone convert -i demo.smprd -o demo.schem
# Converting a Simple Redstone structure to Litematica schematic
simple-redstone convert -i demo.smprd -o demo.litematic
# Converting a Simple Redstone string from the shell input ending with EOF to WorldEdit schematic
simple-redstone convert -o demo.schem << EOF
.@Q;_|_,-|,.@C;.@D
EOF

# Render a structure in an interactive window
simple-redstone render -i demo.smprd
# Render a structure to a PNG image
simple-redstone render -i demo.smprd -o rendered.png
# Use a resource pack for accurate Minecraft textures
simple-redstone render -i demo.smprd -o rendered.png --resource-pack resourcepack.zip
```

Interactive rendering uses Pygfx and WebGPU. Drag with the left mouse button to orbit, drag with the right mouse button to pan, use the mouse wheel to zoom, and press Escape to close the window.

The program uses [Nucleation](https://github.com/schem-at/nucleation) as its back end for storing block structures, converting into schematics, and rendering structures.
