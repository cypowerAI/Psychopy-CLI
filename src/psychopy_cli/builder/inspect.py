"""Reading a `.psyexp` back into this tool's spec dialect.

Used to take over an existing experiment, and to prove that a build is
lossless: ``build`` then ``inspect`` must reproduce the components, parameters
and flow that went in.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..environment import require_psychopy, sanitized_streams
from ..errors import invalid, runtime
from ..spec.model import resolve_component_type

#: Parameters that carry timing or identity and are re-expressed elsewhere.
_SKIP_PARAMS = {
    "name", "startType", "startVal", "stopType", "stopVal",
    "startEstim", "durationEstim", "saveStartStop", "syncScreenRefresh",
}

_START_KIND = {"time (s)": "time", "frame N": "frame", "condition": "condition"}
_STOP_KIND = {
    "duration (s)": "duration",
    "duration (frames)": "duration_frames",
    "time (s)": "time",
    "frame N": "frame",
    "condition": "condition",
}


def inspect_psyexp(path: Path) -> dict[str, Any]:
    require_psychopy()
    try:
        from psychopy.experiment import Experiment
    except Exception as exc:  # pragma: no cover
        raise runtime(f"could not import the Builder API: {exc}") from exc
    if not path.exists():
        raise invalid(f"experiment file not found: {path}")

    with sanitized_streams():
        exp = Experiment()
        exp.loadFromXML(str(path))

    spec: dict[str, Any] = {
        "spec_version": "1.0",
        "name": _as_str(exp.settings.params.get("expName", None)) or path.stem,
    }

    info = _parse_experiment_info(_as_str(exp.settings.params.get("Experiment info", None)))
    if info:
        spec["info"] = info

    spec["window"] = _window_from_settings(exp)
    spec["routines"] = _routines(exp)
    spec["flow"] = _flow(exp)
    data = _data_from_settings(exp)
    if data:
        spec["data"] = data
    return spec


def _as_str(param: Any) -> str | None:
    if param is None:
        return None
    value = getattr(param, "val", None)
    if value is None:
        return None
    return str(value)


def _window_from_settings(exp: Any) -> dict[str, Any]:
    settings = exp.settings.params
    window: dict[str, Any] = {}
    fullscreen = _as_str(settings.get("Full-screen window"))
    if fullscreen is not None:
        window["fullscreen"] = fullscreen == "True"
    size = _as_str(settings.get("Window size (pixels)"))
    if size:
        try:
            parsed = eval(size, {"__builtins__": {}})  # noqa: S307 - Builder's own format
            if isinstance(parsed, (list, tuple)) and len(parsed) == 2:
                window["size"] = [int(parsed[0]), int(parsed[1])]
        except Exception:
            pass
    units = _as_str(settings.get("Units"))
    if units:
        window["units"] = units
    color = _as_str(settings.get("color"))
    if color:
        window["color"] = color
    monitor = _as_str(settings.get("Monitor"))
    if monitor:
        window["monitor"] = monitor
    backend = _as_str(settings.get("winBackend"))
    if backend:
        window["backend"] = backend
    return window or {"size": [1024, 768], "fullscreen": False}


def _data_from_settings(exp: Any) -> dict[str, Any]:
    settings = exp.settings.params
    data: dict[str, Any] = {}
    filename = _as_str(settings.get("Data filename"))
    if filename:
        data["filename"] = filename
    formats: list[str] = []
    if _as_str(settings.get("Save wide csv file")) == "True":
        formats.append("wide_csv")
    if _as_str(settings.get("Save csv file")) == "True":
        formats.append("csv")
    if _as_str(settings.get("Save excel file")) == "True":
        formats.append("excel")
    if _as_str(settings.get("Save psydat file")) == "True":
        formats.append("psydat")
    if formats:
        data["formats"] = formats
    return data


def _parse_experiment_info(literal: str | None) -> dict[str, Any]:
    if not literal:
        return {}
    try:
        value = eval(literal, {"__builtins__": {}, "randint": _zero})  # noqa: S307
    except Exception:
        return {}
    if not isinstance(value, dict):
        return {}
    out: dict[str, Any] = {}
    for key, item in value.items():
        out[str(key)] = "auto" if isinstance(item, str) and "randint" in item else item
    return out


def _zero(*_args: Any, **_kwargs: Any) -> str:  # pragma: no cover - helper for eval
    return "0"


def _routines(exp: Any) -> dict[str, Any]:
    routines: dict[str, Any] = {}
    defaults_cache: dict[str, Any] = {}
    for routine_name, routine in exp.routines.items():
        if routine_name in getattr(exp, "allRoutines", {}):
            continue  # standalone routines (eyetracker calibration etc.)
        components: list[dict[str, Any]] = []
        for component in routine:
            if component.type in ("RoutineSettingsComponent", "SettingsComponent"):
                continue
            type_name = resolve_component_type(component.type) or component.type
            entry: dict[str, Any] = {"type": _short_type(component.type)}

            name = _as_str(component.params.get("name"))
            if name:
                entry["name"] = name

            start, end = _timing(component)
            entry["start"] = start
            if end is not None:
                entry["end"] = end

            if _as_str(component.params.get("disabled")) == "True":
                entry["disabled"] = True

            default_component = defaults_cache.get(type_name)
            if type_name not in defaults_cache:
                default_component = _fresh_component(exp, type(component))
                defaults_cache[type_name] = default_component

            params: dict[str, Any] = {}
            code: dict[str, str] = {}
            for key, param in component.params.items():
                if key in _SKIP_PARAMS:
                    continue
                value = param.val
                default = None
                if default_component is not None and key in default_component.params:
                    default = default_component.params[key].val
                if _same(value, default):
                    continue
                if component.type == "CodeComponent" and _is_code_key(key):
                    code[_code_block_name(key)] = str(value)
                    continue
                params[key] = value
            if params:
                entry["params"] = params
            if code:
                entry["code"] = code
            components.append(entry)
        routines[routine_name] = {"components": components}
    return routines


def _fresh_component(exp: Any, component_cls: type) -> Any:
    try:
        with sanitized_streams():
            return component_cls(exp=exp, parentName="probe", name="probe")
    except Exception:  # pragma: no cover - odd components
        return None


def _same(value: Any, default: Any) -> bool:
    if value is None and default is None:
        return True
    try:
        return str(value) == str(default)
    except Exception:  # pragma: no cover
        return False


def _short_type(type_name: str) -> str:
    resolved = resolve_component_type(type_name)
    if resolved:
        return resolved.replace("Component", "")
    return type_name.replace("Component", "")


_CODE_KEYS = {
    "Before Experiment": "before_experiment",
    "Begin Experiment": "begin_experiment",
    "Begin Routine": "begin_routine",
    "Each Frame": "each_frame",
    "End Routine": "end_routine",
    "End Experiment": "end_experiment",
}


def _is_code_key(key: str) -> bool:
    return key in _CODE_KEYS


def _code_block_name(key: str) -> str:
    return _CODE_KEYS.get(key, key)


def _timing(component: Any) -> tuple[dict[str, Any], dict[str, Any] | None]:
    start_type = _as_str(component.params.get("startType")) or "time (s)"
    start_val = _as_str(component.params.get("startVal")) or "0"
    stop_type = _as_str(component.params.get("stopType")) or "duration (s)"
    stop_val = _as_str(component.params.get("stopVal")) or ""

    start_kind = _START_KIND.get(start_type, "time")
    start: dict[str, Any] = {start_kind: _coerce(start_val, start_kind)}

    if stop_val == "":
        return start, None
    stop_kind = _STOP_KIND.get(stop_type, "duration")
    return start, {stop_kind: _coerce(stop_val, stop_kind)}


def _coerce(raw: str, kind: str) -> Any:
    if kind in ("condition",):
        return raw
    if kind in ("frame", "duration_frames"):
        try:
            return int(float(raw))
        except ValueError:
            return raw
    try:
        value = float(raw)
    except ValueError:
        return raw
    return int(value) if value.is_integer() else value


def _flow(exp: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    for item in exp.flow:
        item_type = type(item).__name__
        if item_type == "LoopInitiator":
            loop = item.loop
            order = _as_str(loop.params.get("loopType")) or "random"
            loop_entry: dict[str, Any] = {
                "name": _as_str(loop.params.get("name")) or "trials",
                "routines": [],
                "n_reps": int(float(_as_str(loop.params.get("nReps")) or 1)),
                "order": "random" if order == "random" else "sequential",
            }
            seed = _as_str(loop.params.get("random seed"))
            if seed:
                try:
                    loop_entry["seed"] = int(seed)
                except ValueError:
                    pass
            conditions_file = _as_str(loop.params.get("conditionsFile"))
            if conditions_file:
                loop_entry["conditions_file"] = conditions_file
            selected = _as_str(loop.params.get("Selected rows"))
            if selected:
                loop_entry["selected_rows"] = selected
            pending = loop_entry
            entries.append({"loop": loop_entry})
        elif item_type == "LoopTerminator":
            pending = None
        else:
            name = getattr(item, "name", None)
            if pending is not None and name:
                pending["routines"].append(name)
            else:
                entries.append({"routine": name})
    return entries


__all__ = ["inspect_psyexp"]
