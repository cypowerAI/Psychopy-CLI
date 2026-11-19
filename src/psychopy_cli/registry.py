"""The command catalogue: one table that drives the parser *and* the docs.

Both ``argparse`` (how a human or agent invokes the command) and the JSON
schemas published by ``psychopy-cli catalog`` are generated from the same
``COMMANDS`` tuple. That keeps the machine-readable contract honest: if an
argument exists, it is described; if it is described, it exists.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Any, Iterable

TYPE_TO_JSON: dict[str, dict[str, Any]] = {
    "str": {"type": "string"},
    "path": {"type": "string", "format": "path"},
    "int": {"type": "integer"},
    "float": {"type": "number"},
    "bool": {"type": "boolean"},
    "json": {"type": ["object", "array", "string"]},
}


@dataclass(frozen=True)
class Arg:
    name: str
    type: str = "str"
    help: str = ""
    positional: bool = False
    required: bool = False
    default: Any = None
    enum: tuple[str, ...] = ()
    repeatable: bool = False
    metavar: str | None = None
    short: str | None = None

    @property
    def flag(self) -> str:
        return "--" + self.name.replace("_", "-")

    def json_schema(self) -> dict[str, Any]:
        schema = dict(TYPE_TO_JSON.get(self.type, {"type": "string"}))
        if self.enum:
            schema["enum"] = list(self.enum)
        if self.help:
            schema["description"] = self.help
        if self.default not in (None, ""):
            schema["default"] = self.default
        if self.repeatable:
            return {"type": "array", "items": schema, "description": self.help}
        return schema


@dataclass(frozen=True)
class Command:
    path: str                       # e.g. "spec validate"
    summary: str
    handler: str                    # "module:function"
    args: tuple[Arg, ...] = ()
    description: str = ""
    examples: tuple[str, ...] = ()
    effects: str = "read_only"      # read_only | writes_files | runs_experiment
    requires: tuple[str, ...] = ()  # psychopy | stim | display
    returns: str = ""

    @property
    def id(self) -> str:
        return self.path.replace(" ", ".")

    @property
    def usage(self) -> str:
        parts = ["psychopy-cli", self.path]
        for arg in self.args:
            if arg.positional:
                parts.append(f"<{arg.name}>")
            elif arg.required:
                parts.append(f"{arg.flag} <{arg.name}>")
            else:
                parts.append(f"[{arg.flag}]")
        return " ".join(parts)

    def input_schema(self) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []
        for arg in self.args:
            properties[arg.name] = arg.json_schema()
            if arg.required or (arg.positional and arg.default is None):
                required.append(arg.name)
        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    def to_catalog(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "command": self.path,
            "usage": self.usage,
            "summary": self.summary,
            "description": self.description,
            "effects": self.effects,
            "requires": list(self.requires),
            "returns": self.returns,
            "arguments": [
                {
                    "name": a.name,
                    "flag": a.flag,
                    "positional": a.positional,
                    "type": a.type,
                    "required": a.required or (a.positional and a.default is None),
                    "default": a.default,
                    "enum": list(a.enum),
                    "description": a.help,
                }
                for a in self.args
            ],
            "input_schema": self.input_schema(),
            "examples": list(self.examples),
        }


_COMMON_FORMAT = Arg(
    "format", "enum", "output format; auto emits JSON when stdout is not a TTY",
    enum=("auto", "json", "text"), default="auto",
)


COMMANDS: tuple[Command, ...] = (
    # ---------------------------------------------------------------- discovery
    Command(
        path="catalog",
        summary="List every command with its JSON input schema (start here).",
        description=(
            "Returns the machine-readable contract for this tool: command ids, "
            "arguments, JSON Schema for each input, side effects, and examples. "
            "Pass a command id to get a single entry. An agent should call this "
            "once, then drive the tool from the result."
        ),
        handler="psychopy_cli.commands.discovery:cmd_catalog",
        args=(
            Arg("command", "str", "command id to describe, e.g. 'build' or 'spec.validate'", positional=True),
            _COMMON_FORMAT,
        ),
        examples=("psychopy-cli catalog", "psychopy-cli catalog build"),
        returns="{commands: [Command]} or {command: Command}",
    ),
    Command(
        path="doctor",
        summary="Probe the environment: Python, PsychoPy, display, audio, components.",
        description=(
            "Runs the checks you need before trusting any other command: is "
            "PsychoPy importable and at which version, which window backends "
            "can actually open, are numpy/Pillow present for stimulus "
            "rendering. `--check-window` opens and closes a real window, which "
            "needs a display."
        ),
        handler="psychopy_cli.commands.discovery:cmd_doctor",
        args=(
            Arg("check_window", "bool", "open and close a real window to test the display backend"),
            _COMMON_FORMAT,
        ),
        examples=("psychopy-cli doctor", "psychopy-cli doctor --check-window"),
        returns="{python, psychopy, display, components, stim}",
    ),
    Command(
        path="components list",
        summary="List Builder components available in the installed PsychoPy.",
        description=(
            "The authoritative component registry of the installed PsychoPy. "
            "Use it to confirm a component type exists before putting it in a "
            "spec, and to see the version that defines its parameter set."
        ),
        handler="psychopy_cli.commands.components:cmd_components_list",
        args=(
            Arg("filter", "str", "only show components whose name contains this text"),
            _COMMON_FORMAT,
        ),
        requires=("psychopy",),
        examples=("psychopy-cli components list --filter text",),
        returns="{count, components: [{type, label, categories}]}",
    ),
    Command(
        path="components describe",
        summary="Show the exact parameter names, defaults and allowed values of a component.",
        description=(
            "Everything the Builder knows about one component: every parameter "
            "key, its default, its allowed values and whether it accepts code. "
            "Build specs against this output rather than guessing parameter "
            "names; key lookup in specs is forgiving but values are not."
        ),
        handler="psychopy_cli.commands.components:cmd_components_describe",
        args=(
            Arg("name", "str", "component type, e.g. TextComponent or 'Text'", positional=True),
            _COMMON_FORMAT,
        ),
        requires=("psychopy",),
        examples=("psychopy-cli components describe Text",),
        returns="{type, label, version, parameters: [{name, default, type, allowed}]}",
    ),
    # ------------------------------------------------------------------- spec
    Command(
        path="spec schema",
        summary="Emit the JSON Schema of the experiment spec language.",
        description=(
            "The full grammar an agent must follow when authoring an "
            "experiment spec. Fetch it once and keep it in context; do not "
            "infer the format from examples alone."
        ),
        handler="psychopy_cli.commands.spec:cmd_spec_schema",
        args=(_COMMON_FORMAT,),
        examples=("psychopy-cli spec schema",),
        returns="JSON Schema document",
    ),
    Command(
        path="spec new",
        summary="Write a starter spec you can edit.",
        description=(
            "Scaffolds a valid spec for a known design. Templates are complete "
            "and runnable, so the fastest path is: `spec new` -> edit -> "
            "`spec validate` -> `build` -> `run --simulate`."
        ),
        handler="psychopy_cli.commands.spec:cmd_spec_new",
        args=(
            Arg("template", "enum", "design template to scaffold", positional=True,
                enum=("minimal", "stroop", "flanker"), default="minimal"),
            Arg("output", "path", "file to write (default: <template>.spec.json)", short="-o"),
            Arg("force", "bool", "overwrite an existing file"),
            _COMMON_FORMAT,
        ),
        effects="writes_files",
        examples=("psychopy-cli spec new stroop -o stroop.spec.json",),
        returns="{path, template}",
    ),
    Command(
        path="spec validate",
        summary="Check a spec for errors before building or running it.",
        description=(
            "Static checks: required fields, unknown component types, unknown "
            "parameters (with suggestions), timing expressions, flow references, "
            "condition column usage. Errors carry a JSON path so an agent can "
            "patch the file it produced."
        ),
        handler="psychopy_cli.commands.spec:cmd_spec_validate",
        args=(
            Arg("path", "path", "spec file to validate", positional=True, required=True),
            Arg("strict", "bool", "treat warnings as errors"),
            _COMMON_FORMAT,
        ),
        examples=("psychopy-cli spec validate stroop.spec.json",),
        returns="{valid, errors: [{path, code, message, hint}], warnings, stats}",
    ),
    # ------------------------------------------------------------------ build
    Command(
        path="build",
        summary="Compile a spec into a runnable PsychoPy .psyexp plus optional Python.",
        description=(
            "Builds the artifacts through PsychoPy's own Builder classes, so "
            "the result opens in Builder and round-trips through "
            "`loadFromXML`. Writes the .psyexp, any conditions CSVs, an "
            "optional generated script and a manifest describing the build."
        ),
        handler="psychopy_cli.commands.build:cmd_build",
        args=(
            Arg("path", "path", "spec file", positional=True, required=True),
            Arg("output", "path", "output directory (default: alongside the spec)", short="-o"),
            Arg("psyexp", "bool", "write the .psyexp file", default=True),
            Arg("script", "bool", "also write a generated PsychoPy script"),
            Arg("force", "bool", "overwrite existing artifacts"),
            Arg("dry_run", "bool", "validate and plan only, write nothing"),
            _COMMON_FORMAT,
        ),
        effects="writes_files",
        requires=("psychopy",),
        examples=(
            "psychopy-cli build stroop.spec.json -o build/",
            "psychopy-cli build stroop.spec.json --script --force",
        ),
        returns="{artifacts: [{path, role, bytes}], psyexp, script, manifest}",
    ),
    Command(
        path="inspect",
        summary="Read a .psyexp back into a spec-shaped JSON description.",
        description=(
            "Parses an experiment with PsychoPy's Builder and re-emits it in "
            "this tool's spec dialect. Use it to take over an existing "
            "experiment, or to diff a build against its source spec."
        ),
        handler="psychopy_cli.commands.build:cmd_inspect",
        args=(
            Arg("path", "path", ".psyexp file to read", positional=True, required=True),
            Arg("output", "path", "write the spec JSON here instead of stdout", short="-o"),
            Arg("force", "bool", "overwrite the output file"),
            _COMMON_FORMAT,
        ),
        requires=("psychopy",),
        examples=("psychopy-cli inspect build/stroop.psyexp",),
        returns="{spec} or {path, spec}",
    ),
    # -------------------------------------------------------------------- run
    Command(
        path="run",
        summary="Execute an experiment: simulate the design, or present it for real.",
        description=(
            "Two modes with one contract. `--simulate` enumerates trials, resolves "
            "condition variables and writes the trial table without opening a "
            "window -- always available and the right first check. Without "
            "`--simulate` it presents stimuli on a real window, records "
            "responses and timings, honours --timeout and --max-trials, and "
            "writes data plus a manifest into a run directory."
        ),
        handler="psychopy_cli.commands.run:cmd_run",
        args=(
            Arg("path", "path", "spec file or .psyexp", positional=True, required=True),
            Arg("participant", "str", "participant id", default="auto"),
            Arg("session", "str", "session id", default="001"),
            Arg("simulate", "bool", "enumerate the design only; no window, no rendering"),
            Arg("timeout", "float", "hard wall-clock limit in seconds", default=600.0),
            Arg("max_trials", "int", "stop after N trials (0 = run them all)", default=0),
            Arg("output", "path", "run directory (default: runs/<timestamp>-<name>)", short="-o"),
            Arg("seed", "int", "random seed for condition order"),
            Arg("window_size", "str", "window size as WIDTHxHEIGHT, e.g. 1024x768"),
            Arg("fullscreen", "bool", "present full screen"),
            Arg("auto_response", "bool", "answer every keyboard component automatically (smoke tests only)"),
            _COMMON_FORMAT,
        ),
        effects="runs_experiment",
        requires=("psychopy",),
        examples=(
            "psychopy-cli run stroop.spec.json --simulate",
            "psychopy-cli run stroop.spec.json --participant p01 --max-trials 4",
        ),
        returns="{run_dir, data_file, n_trials, mode, summary}",
    ),
    # ------------------------------------------------------------------ stim
    Command(
        path="stim list",
        summary="List the stimulus generators that need no display.",
        description=(
            "Pure-numpy stimulus synthesis. Every generator writes a PNG and "
            "reports the numeric properties it used, so it works on a headless "
            "box and is deterministic given the same arguments."
        ),
        handler="psychopy_cli.commands.stim:cmd_stim_list",
        args=(_COMMON_FORMAT,),
        requires=("stim",),
        examples=("psychopy-cli stim list",),
        returns="{generators: [...]}",
    ),
    Command(
        path="stim grating",
        summary="Render a Gabor / grating patch to PNG.",
        description=(
            "Sinusoidal luminance grating with an optional Gaussian or circular "
            "window -- the standard psychophysics stimulus. Frequencies are in "
            "cycles per pixel, contrast is Michelson contrast in [0, 1]."
        ),
        handler="psychopy_cli.commands.stim:cmd_stim_grating",
        args=(
            Arg("output", "path", "PNG file to write", required=True, short="-o"),
            Arg("size", "int", "image side length in pixels", default=512),
            Arg("sf", "float", "spatial frequency in cycles/pixel", default=0.05),
            Arg("ori", "float", "orientation in degrees", default=0.0),
            Arg("phase", "float", "phase in cycles", default=0.0),
            Arg("contrast", "float", "Michelson contrast, 0..1", default=1.0),
            Arg("mask", "enum", "envelope", enum=("none", "circle", "gaussian"), default="gaussian"),
            Arg("sigma", "float", "Gaussian sigma as a fraction of the radius", default=0.3),
            Arg("background", "float", "background luminance, 0..1", default=0.5),
            Arg("foreground_is_dark", "bool", "invert so dark bars sit on the background"),
            _COMMON_FORMAT,
        ),
        effects="writes_files",
        requires=("stim",),
        examples=("psychopy-cli stim grating -o gabor.png --sf 0.04 --ori 45",),
        returns="{path, size, sf, ori, contrast, contrast_measured}",
    ),
    Command(
        path="stim noise",
        summary="Render a random-noise field to PNG.",
        description="Gaussian or uniform noise with a fixed seed, for masking and texture work.",
        handler="psychopy_cli.commands.stim:cmd_stim_noise",
        args=(
            Arg("output", "path", "PNG file to write", required=True, short="-o"),
            Arg("size", "int", "image side length in pixels", default=512),
            Arg("type", "enum", "noise distribution", enum=("gaussian", "uniform", "binary"), default="gaussian"),
            Arg("sd", "float", "standard deviation for gaussian noise", default=0.1),
            Arg("seed", "int", "seed for reproducibility", default=0),
            Arg("background", "float", "background luminance, 0..1", default=0.5),
            _COMMON_FORMAT,
        ),
        effects="writes_files",
        requires=("stim",),
        examples=("psychopy-cli stim noise -o noise.png --type uniform",),
        returns="{path, size, type, sd, seed}",
    ),
    Command(
        path="stim text",
        summary="Render text to a transparent PNG (no PsychoPy needed).",
        description=(
            "Text as an image, for posters, instruction screens or materials "
            "that must not depend on the presentation machine's fonts."
        ),
        handler="psychopy_cli.commands.stim:cmd_stim_text",
        args=(
            Arg("output", "path", "PNG file to write", required=True, short="-o"),
            Arg("text", "str", "text to draw; \n starts a new line", required=True),
            Arg("height", "int", "cap height in pixels", default=64),
            Arg("font", "str", "font family or file", default="Arial"),
            Arg("color", "str", "foreground colour, e.g. '#ffffff' or 'white'", default="white"),
            Arg("background", "str", "background colour, or 'transparent'", default="transparent"),
            Arg("padding", "int", "padding in pixels", default=16),
            _COMMON_FORMAT,
        ),
        effects="writes_files",
        requires=("stim",),
        examples=("psychopy-cli stim text -o fix.png --text '+' --height 96",),
        returns="{path, width, height}",
    ),
    Command(
        path="stim shape",
        summary="Render a geometric shape to PNG.",
        description="Circle, triangle, rectangle, cross or star, filled or outlined, with rotation.",
        handler="psychopy_cli.commands.stim:cmd_stim_shape",
        args=(
            Arg("output", "path", "PNG file to write", required=True, short="-o"),
            Arg("shape", "enum", "shape to draw", enum=("circle", "triangle", "rectangle", "cross", "star"), default="circle"),
            Arg("size", "int", "image side length in pixels", default=256),
            Arg("fill", "str", "fill colour, or 'none'", default="white"),
            Arg("line", "str", "outline colour, or 'none'", default="none"),
            Arg("line_width", "int", "outline width in pixels", default=0),
            Arg("rotation", "float", "rotation in degrees", default=0.0),
            Arg("background", "str", "background colour, or 'transparent'", default="transparent"),
            _COMMON_FORMAT,
        ),
        effects="writes_files",
        requires=("stim",),
        examples=("psychopy-cli stim shape -o cue.png --shape triangle --rotation 90",),
        returns="{path, shape, size}",
    ),
    # ------------------------------------------------------------------ data
    Command(
        path="data summarize",
        summary="Summarise a result file: trial counts, accuracy, response times.",
        description=(
            "Reads the CSV written by `run` (or a conditions file) and reports "
            "row counts, per-condition grouping, accuracy from *.corr columns "
            "and RT statistics from *.rt columns. Standard library only."
        ),
        handler="psychopy_cli.commands.data:cmd_data_summarize",
        args=(
            Arg("path", "path", "CSV file to summarize", positional=True, required=True),
            Arg("group_by", "str", "column to group by; repeatable", repeatable=True),
            Arg("rt_column", "str", "response-time column (default: first column ending in .rt)"),
            Arg("correct_column", "str", "accuracy column (default: first column ending in .corr)"),
            _COMMON_FORMAT,
        ),
        examples=("psychopy-cli data summarize runs/20260101-120000-stroop/data.csv --group-by condition",),
        returns="{rows, columns, groups: [{group, n, accuracy, rt_mean, rt_median}]}",
    ),
)


# --------------------------------------------------------------------------
# helpers used by the parser and by `catalog`
# --------------------------------------------------------------------------


def find_command(command_id: str) -> Command | None:
    target = command_id.strip().replace(" ", ".").lower()
    for command in COMMANDS:
        if command.id.lower() == target or command.path.lower() == target.replace(".", " "):
            return command
    return None


def command_groups() -> dict[str, list[Command]]:
    groups: dict[str, list[Command]] = {}
    for command in COMMANDS:
        head = command.path.split()[0]
        groups.setdefault(head, []).append(command)
    return groups


def _apply_arg(parser: argparse.ArgumentParser, arg: Arg) -> None:
    if arg.positional:
        positional_kwargs: dict[str, Any] = {
            "metavar": arg.metavar or arg.name,
            "nargs": None if arg.required else "?",
            "default": arg.default,
            "help": arg.help,
        }
        if arg.enum:
            positional_kwargs["choices"] = list(arg.enum)
        parser.add_argument(arg.name, **positional_kwargs)
        return

    kwargs: dict[str, Any] = {"dest": arg.name, "help": arg.help}
    if arg.type == "bool":
        kwargs["action"] = "store_false" if arg.default is True else "store_true"
        if arg.default is not None:
            kwargs["default"] = arg.default
    else:
        if arg.default is not None:
            kwargs["default"] = arg.default
        if arg.required and not arg.positional:
            kwargs["required"] = True
        if arg.enum:
            kwargs["choices"] = list(arg.enum)
        if arg.repeatable:
            kwargs["action"] = "append"
        kwargs["type"] = float if arg.type == "float" else int if arg.type == "int" else str
        if arg.metavar is None and arg.type != "str":
            kwargs["metavar"] = arg.name.upper()
    flags = [arg.flag] + ([arg.short] if arg.short else [])
    parser.add_argument(*flags, **kwargs)


def build_parser(parser_class: type[argparse.ArgumentParser] = argparse.ArgumentParser):
    """Build the full CLI from the table above.

    ``parser_class`` lets the caller supply a parser that raises on bad usage
    instead of exiting, without duplicating the table-driven construction.
    """
    parser = parser_class(
        prog="psychopy-cli",
        description=(
            "Machine-readable PsychoPy driver. Start with `psychopy-cli catalog`, "
            "check the box with `psychopy-cli doctor`, then spec -> build -> run."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "JSON is emitted when stdout is not a TTY. Exit codes: "
            "0 ok, 2 usage, 3 invalid spec, 4 not found, 5 missing dependency, "
            "6 runtime failure, 7 environment."
        ),
    )
    parser.add_argument("--version", action="version", version="psychopy-cli 0.1.0")
    parser.add_argument("--cwd", default=None, help="base directory for relative paths")
    parser.add_argument(
        "--format", dest="global_format", choices=("auto", "json", "text"), default=None,
        help="output format (each command also accepts --format)",
    )
    parser.add_argument("--debug", action="store_true", help="print a traceback on unexpected errors")

    groups = command_groups()
    subparsers = parser.add_subparsers(dest="group", metavar="GROUP", parser_class=parser_class)
    for group_name, commands in groups.items():
        group_parser = subparsers.add_parser(
            group_name,
            help=_group_help(group_name, commands),
            description=_group_help(group_name, commands),
        )
        # A group name that *is* a command is dispatched straight away...
        direct = next((c for c in commands if c.path == group_name), None)
        if direct is not None:
            _apply_command(group_parser, direct)
            continue
        # ...otherwise the group is a namespace and every member is a leaf.
        leaf_parsers = group_parser.add_subparsers(
            dest="action", metavar="ACTION", required=True, parser_class=parser_class,
        )
        for command in commands:
            leaf_name = command.path.split()[1]
            leaf = leaf_parsers.add_parser(leaf_name, help=command.summary, description=command.summary)
            _apply_command(leaf, command)
    return parser


def _group_help(group_name: str, commands: Iterable[Command]) -> str:
    for command in commands:
        if command.path == group_name:
            return command.summary
    return "sub-commands: " + ", ".join(c.path.split()[1] for c in commands if len(c.path.split()) > 1)


def _apply_command(parser: argparse.ArgumentParser, command: Command) -> None:
    for arg in command.args:
        if arg.name == "format":
            # declared once per command so `--format` works in both positions
            if not parser._option_string_actions.get("--format"):  # noqa: SLF001
                parser.add_argument(
                    "--format", choices=list(arg.enum), default=None, dest="format",
                    help=arg.help,
                )
            continue
        _apply_arg(parser, arg)
    parser.set_defaults(_command_id=command.id, _command_path=command.path)
