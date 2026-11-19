"""Discovery commands: `catalog` and `doctor`.

Everything here must work with zero optional dependencies, because it is how
an agent finds out what it can do and what the machine can support.
"""

from __future__ import annotations

from typing import Any

from .. import __version__
from .. import environment
from ..console import Result
from ..errors import usage
from ..registry import COMMANDS, find_command


def cmd_catalog(context: Any, args: Any) -> Result:
    requested = getattr(args, "command", None)
    if requested:
        command = find_command(requested)
        if command is None:
            known = ", ".join(c.id for c in COMMANDS)
            raise usage(
                f"unknown command {requested!r}",
                hint=f"known commands: {known}",
            )
        return Result(data={"command": command.to_catalog()})

    return Result(data={
        "cli_version": __version__,
        "commands": [command.to_catalog() for command in COMMANDS],
        "conventions": {
            "output": "one JSON envelope on stdout: {ok, command, data, warnings?, meta}",
            "errors": "{ok: false, command, error: {code, message, hint?, details?, next?}}",
            "exit_codes": {
                "0": "success",
                "2": "usage error",
                "3": "invalid spec",
                "4": "file not found",
                "5": "missing optional dependency",
                "6": "runtime failure",
                "7": "environment problem",
            },
            "workflow": [
                "psychopy-cli doctor",
                "psychopy-cli spec schema",
                "psychopy-cli spec new <template> -o <file>.spec.json",
                "psychopy-cli spec validate <file>.spec.json",
                "psychopy-cli build <file>.spec.json",
                "psychopy-cli run <file>.spec.json --simulate",
                "psychopy-cli run <file>.spec.json --participant p01",
            ],
        },
    })


def cmd_doctor(context: Any, args: Any) -> Result:
    python = environment.python_info()
    psychopy = environment.psychopy_info()
    stim = environment.stim_dependencies()

    data: dict[str, Any] = {
        "cli": {"version": __version__},
        "python": python,
        "psychopy": psychopy,
        "stim": stim,
    }

    warnings: list[str] = []
    if not psychopy["available"]:
        warnings.append(
            "PsychoPy is not importable: `build`, `inspect` and `run` will fail. "
            "Install with `pip install psychopy-cli[psychopy]`."
        )
    elif not python["supports_psychopy_range"]:
        warnings.append(
            f"Python {python['version']} is outside PsychoPy's supported range (>=3.10,<3.13)."
        )
    if not stim["available"]:
        warnings.append(
            "numpy/Pillow missing: `stim` commands need `pip install psychopy-cli[stim]`."
        )

    if psychopy["available"]:
        try:
            registry = environment.component_registry()
            data["components"] = {"count": len(registry), "names": sorted(registry)}
        except Exception as exc:
            data["components"] = {"count": 0, "error": str(exc)}

    if getattr(args, "check_window", False):
        if psychopy["available"]:
            data["display"] = environment.display_probe()
            working = data["display"].get("working") or []
            if not working:
                warnings.append("no window backend could open; `run` without --simulate will fail")
        else:
            data["display"] = {"checked": False, "error": "PsychoPy not importable"}
    else:
        data["display"] = {
            "checked": False,
            "hint": "pass --check-window to open and close a real window",
            "environment_has_display": environment.has_display(),
        }

    return Result(data=data, warnings=warnings)


__all__ = ["cmd_catalog", "cmd_doctor"]
