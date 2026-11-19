"""Component inspection: what can go into a spec, and with which parameters."""

from __future__ import annotations

from typing import Any

from .. import environment
from ..console import Result
from ..errors import invalid
from ..spec.model import resolve_component_type


def _short(type_name: str) -> str:
    return type_name.replace("Component", "")


def cmd_components_list(context: Any, args: Any) -> Result:
    registry = environment.component_registry()
    needle = (getattr(args, "filter", None) or "").lower()

    entries = []
    for type_name, cls in sorted(registry.items()):
        label = getattr(cls, "label", "") or ""
        if needle and (needle not in type_name.lower() and needle not in str(label).lower()):
            continue
        entries.append({
            "type": type_name,
            "short": _short(type_name),
            "label": str(label),
            "version": getattr(cls, "version", None),
            "categories": list(getattr(cls, "categories", []) or []),
            "plugin": getattr(cls, "plugin", None),
        })
    # RoutineSettings/Settings are plumbing, not something to put in a spec.
    entries = [e for e in entries if e["type"] not in ("RoutineSettingsComponent", "SettingsComponent")]

    return Result(data={"count": len(entries), "components": entries})


def cmd_components_describe(context: Any, args: Any) -> Result:
    registry = environment.component_registry()
    requested = args.name

    canonical = resolve_component_type(requested)
    candidates = [canonical] if canonical else []
    if requested in registry:
        candidates.append(requested)
    match = next((name for name in candidates if name in registry), None)
    if match is None:
        for name in registry:
            if name.lower() == str(requested).lower():
                match = name
                break
    if match is None:
        raise invalid(
            f"unknown component {requested!r}",
            hint=f"available: {', '.join(sorted(registry))}",
            next_actions=["psychopy-cli components list"],
        )

    cls = registry[match]
    parameters = _parameters_for(cls)
    return Result(data={
        "type": match,
        "short": _short(match),
        "label": str(getattr(cls, "label", "") or ""),
        "version": getattr(cls, "version", None),
        "categories": list(getattr(cls, "categories", []) or []),
        "parameters": parameters,
        "spec_example": _spec_example(match, parameters),
    })


def _parameters_for(cls: type) -> list[dict[str, Any]]:
    from psychopy.experiment import Experiment

    with environment.sanitized_streams():
        exp = Experiment()
        instance = cls(exp=exp, parentName="probe", name="probe")

    out: list[dict[str, Any]] = []
    for key, param in instance.params.items():
        allowed = getattr(param, "allowedVals", None) or []
        allowed_updates = getattr(param, "allowedUpdates", None) or []
        out.append({
            "name": key,
            "default": getattr(param, "val", None),
            "value_type": getattr(param, "valType", None),
            "input_type": getattr(param, "inputType", None),
            "allowed": list(allowed),
            "updates": list(allowed_updates),
            "label": str(getattr(param, "label", "") or ""),
            "hint": str(getattr(param, "hint", "") or ""),
        })
    return out


def _spec_example(type_name: str, parameters: list[dict[str, Any]]) -> dict[str, Any]:
    plausible = ("text", "image", "allowedKeys", "shape", "sf", "sound", "storeCorrect", "correctAns")
    params: dict[str, Any] = {}
    for entry in parameters:
        if entry["name"] in plausible and entry["default"] not in (None, ""):
            params[entry["name"]] = entry["default"]
    example: dict[str, Any] = {"type": _short(type_name), "name": _short(type_name).lower() + "1",
                               "start": 0, "end": {"duration": 1.0}}
    if type_name == "KeyboardComponent":
        example["end"] = {"condition": "resp.rt"}
    if params:
        example["params"] = params
    return example


__all__ = ["cmd_components_list", "cmd_components_describe"]
