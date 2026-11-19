"""Output envelope: one JSON object per invocation, or a compact text view.

Design rules this module enforces:

* stdout carries **exactly one** machine-readable document (JSON envelope) or
  human text -- never a mix, never progress chatter. Logs go to stderr.
* the envelope shape is stable, so an agent can parse ``ok`` first and only
  then look at the payload.
* ``--format`` defaults to ``auto``: JSON when stdout is not a TTY (i.e. when
  a program or agent runs the command), text in an interactive shell.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

from . import __version__
from .errors import CliError


@dataclass
class Result:
    """What a handler returns on success."""

    data: dict[str, Any] = field(default_factory=dict)
    text: str | None = None
    warnings: list[str] = field(default_factory=list)


TextRenderer = Callable[[dict[str, Any]], str]


def resolve_format(requested: str) -> str:
    """Turn ``auto`` into ``json`` or ``text`` based on the stream."""
    if requested in ("json", "text"):
        return requested
    return "text" if sys.stdout.isatty() else "json"


def ok_envelope(command: str, result: Result, elapsed_ms: float, fmt: str) -> dict[str, Any]:
    env: dict[str, Any] = {
        "ok": True,
        "command": command,
        "data": result.data,
    }
    if result.warnings:
        env["warnings"] = result.warnings
    env["meta"] = {"version": __version__, "duration_ms": round(elapsed_ms, 1), "format": fmt}
    return env


def error_envelope(command: str, error: CliError, elapsed_ms: float) -> dict[str, Any]:
    return {
        "ok": False,
        "command": command,
        "error": error.to_dict(),
        "meta": {"version": __version__, "duration_ms": round(elapsed_ms, 1)},
    }


def dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# text rendering
# --------------------------------------------------------------------------


def _render_pairs(data: dict[str, Any], indent: str = "") -> list[str]:
    lines: list[str] = []
    for key, value in data.items():
        label = key.replace("_", " ")
        if isinstance(value, dict):
            lines.append(f"{indent}{label}:")
            lines.extend(_render_pairs(value, indent + "  "))
        elif isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
            lines.append(f"{indent}{label}:")
            lines.extend(render_table(value, indent + "  "))
        elif isinstance(value, list):
            lines.append(f"{indent}{label}: " + (", ".join(str(v) for v in value) if value else "-"))
        elif value is None or value == "":
            lines.append(f"{indent}{label}: -")
        else:
            lines.append(f"{indent}{label}: {value}")
    return lines


def render_table(rows: list[dict[str, Any]], indent: str = "") -> list[str]:
    if not rows:
        return [f"{indent}(empty)"]
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in columns}
    header = "  ".join(c.ljust(widths[c]) for c in columns)
    sep = "  ".join("-" * widths[c] for c in columns)
    out = [indent + header, indent + sep]
    for row in rows:
        out.append(indent + "  ".join(str(row.get(c, "")).ljust(widths[c]) for c in columns))
    return out


def _render_catalog(data: dict[str, Any]) -> str:
    if "command" in data:
        cmd = data["command"]
        lines = [f"{cmd['usage']}", "", cmd["summary"], ""]
        if cmd.get("description"):
            lines += [cmd["description"], ""]
        lines.append("arguments:")
        for arg in cmd.get("arguments", []):
            flag = arg["name"] if arg.get("positional") else "--" + arg["name"].replace("_", "-")
            req = " (required)" if arg.get("required") else ""
            default = "" if arg.get("default") in (None, "") else f" [default: {arg['default']}]"
            lines.append(f"  {flag}{req}{default}")
            lines.append(f"      {arg.get('description', '')}")
        if cmd.get("examples"):
            lines += ["", "examples:"] + [f"  {e}" for e in cmd["examples"]]
        return "\n".join(lines)
    rows = [
        {"command": c["id"], "summary": c["summary"], "effects": c.get("effects", "")}
        for c in data.get("commands", [])
    ]
    return "\n".join([f"{len(rows)} commands", ""] + render_table(rows))


def _render_doctor(data: dict[str, Any]) -> str:
    lines: list[str] = []
    for section, payload in data.items():
        label = section.replace("_", " ").title()
        lines.append(label)
        if isinstance(payload, dict):
            for key, value in payload.items():
                mark = ""
                if key == "available" or key == "installed":
                    mark = "ok  " if value else "MISS"
                lines.append(f"  {mark}{key.replace('_', ' ')}: {value}")
        else:
            lines.append(f"  {payload}")
        lines.append("")
    return "\n".join(lines)


def _render_generic(data: dict[str, Any]) -> str:
    return "\n".join(_render_pairs(data))


_RENDERERS: dict[str, TextRenderer] = {}


def register_renderer(command_path: str, renderer: TextRenderer) -> None:
    _RENDERERS[command_path] = renderer


def render_result(command_path: str, data: dict[str, Any]) -> str:
    renderer = _RENDERERS.get(command_path)
    if renderer is not None:
        try:
            return renderer(data)
        except Exception:  # a broken pretty-printer must not break the command
            return _render_generic(data)
    if command_path in ("catalog", "catalog show"):
        return _render_catalog(data)
    if command_path == "doctor":
        return _render_doctor(data)
    return _render_generic(data)


def emit_error_text(error: CliError) -> str:
    lines = [f"error: {error.message}", f"code: {error.code}"]
    if error.hint:
        lines.append(f"hint: {error.hint}")
    for detail in error.details:
        loc = detail.get("path") or detail.get("file") or ""
        lines.append(f"  - {loc}: {detail.get('message', '')}" if loc else f"  - {detail.get('message', '')}")
    if error.next_actions:
        lines.append("next: " + ", ".join(error.next_actions))
    return "\n".join(lines)
