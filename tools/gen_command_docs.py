#!/usr/bin/env python
"""Render `docs/commands.md` from the command registry.

The registry is the single source of truth for the CLI: this script makes sure
the human documentation cannot drift away from `psychopy-cli catalog`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from psychopy_cli.registry import command_groups  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs" / "commands.md"


def render() -> str:
    lines = [
        "# Command reference",
        "",
        "Generated from `src/psychopy_cli/registry.py` by `python tools/gen_command_docs.py`.",
        "The same table is available at runtime, with JSON Schema, from `psychopy-cli catalog`.",
        "",
    ]
    for group, commands in command_groups().items():
        lines.append(f"## `{group}`")
        lines.append("")
        for command in commands:
            lines.extend(_render_command(command))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_command(command) -> list[str]:
    lines = [f"### `{command.usage}`", "", command.summary, ""]
    if command.description and command.description != command.summary:
        lines.extend([command.description, ""])
    lines.append(f"- requires: {', '.join(command.requires) if command.requires else 'nothing beyond Python'}")
    lines.append(f"- effects: {command.effects}")
    lines.append(f"- returns: `{command.returns}`")
    lines.append("")
    if command.args:
        lines.append("| argument | type | required | default | description |")
        lines.append("| --- | --- | --- | --- | --- |")
        for argument in command.args:
            flag = argument.name if argument.positional else argument.flag
            lines.append(
                f"| `{flag}` | {argument.type} | "
                f"{'yes' if argument.required else 'no'} | "
                f"{_default(argument)} | {argument.help} |"
            )
        lines.append("")
    if command.examples:
        lines.append("Examples:")
        lines.append("")
        lines.append("```bash")
        lines.extend(command.examples)
        lines.append("```")
        lines.append("")
    return lines


def _default(argument) -> str:
    if argument.default is None:
        return "—"
    if isinstance(argument.default, bool):
        return "true" if argument.default else "false"
    return f"`{argument.default}`"


if __name__ == "__main__":
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(render(), encoding="utf-8")
    print(f"wrote {TARGET}")
