"""The experiment spec: a small, explicit dialect of the Builder model.

The spec is what an agent writes. It is deliberately *flatter* than a
`.psyexp` file and stricter about meaning: every timing says whether it is a
time, a frame, or a condition, so nothing depends on invisible defaults.

Parsing is forgiving on structure (unknown keys are reported, not fatal) and
strict on semantics (errors block `build`). ``parse_spec`` returns a model
plus diagnostics rather than raising, so `spec validate` can report everything
at once instead of one error per invocation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from ..errors import CliError, invalid, not_found

SUPPORTED_SPEC_VERSION = "1.0"

#: Canonical Builder component types, kept here so validation works even when
#: PsychoPy is not installed. `build` re-checks against the live registry.
CANONICAL_COMPONENTS: dict[str, str] = {
    "aperture": "ApertureComponent",
    "brush": "BrushComponent",
    "button": "ButtonComponent",
    "buttonbox": "ButtonBoxComponent",
    "camera": "CameraComponent",
    "code": "CodeComponent",
    "dots": "DotsComponent",
    "eyetrackermarker": "EyetrackerMarkerComponent",
    "eyetrackerrecord": "EyetrackerRecordComponent",
    "form": "FormComponent",
    "grating": "GratingComponent",
    "image": "ImageComponent",
    "joybuttons": "JoyButtonsComponent",
    "joystick": "JoystickComponent",
    "keyboard": "KeyboardComponent",
    "microphone": "MicrophoneComponent",
    "mouse": "MouseComponent",
    "movie": "MovieComponent",
    "panorama": "PanoramaComponent",
    "parallelout": "ParallelOutComponent",
    "polygon": "PolygonComponent",
    "progress": "ProgressComponent",
    "regionofinterest": "RegionOfInterestComponent",
    "resourcemanager": "ResourceManagerComponent",
    "serialout": "SerialOutComponent",
    "slider": "SliderComponent",
    "sound": "SoundComponent",
    "soundsensor": "SoundSensorComponent",
    "static": "StaticComponent",
    "text": "TextComponent",
    "textbox": "TextboxComponent",
    "variable": "VariableComponent",
}

#: Components the presentation runtime can actually drive (see runtime/engine).
RUNNABLE_COMPONENTS = frozenset(
    {"TextComponent", "ImageComponent", "GratingComponent", "PolygonComponent",
     "SoundComponent", "KeyboardComponent", "MouseComponent", "CodeComponent",
     "TextboxComponent", "SliderComponent"}
)

WINDOW_UNITS = ("height", "norm", "cm", "pix", "deg")
WINDOW_BACKENDS = ("pyglet", "pygame", "glfw")
START_KINDS = ("time", "frame", "condition")
STOP_KINDS = ("duration", "duration_frames", "time", "frame", "condition")

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FILENAME_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")


# --------------------------------------------------------------------------
# diagnostics
# --------------------------------------------------------------------------


@dataclass
class Diagnostic:
    severity: str          # "error" | "warning"
    code: str
    message: str
    path: str = ""
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.path:
            payload["path"] = self.path
        if self.hint:
            payload["hint"] = self.hint
        return payload


class Diagnostics:
    def __init__(self) -> None:
        self.items: list[Diagnostic] = []

    def error(self, code: str, message: str, path: str = "", hint: str | None = None) -> None:
        self.items.append(Diagnostic("error", code, message, path, hint))

    def warn(self, code: str, message: str, path: str = "", hint: str | None = None) -> None:
        self.items.append(Diagnostic("warning", code, message, path, hint))

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity == "error"]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity == "warning"]

    def __len__(self) -> int:
        return len(self.items)


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------


@dataclass
class Timing:
    """When a component starts or stops, with the unit made explicit."""

    kind: str
    value: Any

    def to_dict(self) -> dict[str, Any]:
        return {self.kind: self.value}

    def describe(self) -> str:
        return f"{self.kind}:{self.value}"


@dataclass
class ComponentSpec:
    type: str
    name: str
    start: Timing
    end: Timing | None          # None means "runs until the routine ends"
    params: dict[str, Any] = field(default_factory=dict)
    code: dict[str, str] = field(default_factory=dict)
    disabled: bool = False
    path: str = ""


@dataclass
class RoutineSpec:
    name: str
    components: list[ComponentSpec] = field(default_factory=list)


@dataclass
class RoutineRef:
    routine: str
    kind: str = "routine"


@dataclass
class LoopSpec:
    name: str
    routines: list[str]
    n_reps: int = 1
    order: str = "sequential"        # sequential | random | random_per_rep
    seed: int | None = None
    conditions: list[dict[str, Any]] = field(default_factory=list)
    conditions_file: str | None = None
    selected_rows: str = ""
    kind: str = "loop"

    def condition_columns(self) -> list[str]:
        columns: list[str] = []
        for row in self.conditions:
            for key in row:
                if key not in columns:
                    columns.append(key)
        return columns


@dataclass
class WindowSpec:
    size: tuple[int, int] = (1024, 768)
    fullscreen: bool = False
    units: str = "height"
    color: Any = (0, 0, 0)
    monitor: str = "testMonitor"
    backend: str | None = None


@dataclass
class DataSpec:
    filename: str = "data/{participant}/{name}_{date}"
    formats: list[str] = field(default_factory=lambda: ["wide_csv"])
    delimiter: str = "auto"


@dataclass
class Spec:
    raw: dict[str, Any]
    path: Path | None
    name: str
    spec_version: str
    window: WindowSpec
    info: dict[str, Any]
    routines: dict[str, RoutineSpec]
    flow: list[RoutineRef | LoopSpec]
    data: DataSpec
    title: str | None = None

    @property
    def dir(self) -> Path:
        return self.path.parent if self.path else Path.cwd()

    def routine(self, name: str) -> RoutineSpec:
        return self.routines[name]

    @property
    def loops(self) -> list[LoopSpec]:
        return [entry for entry in self.flow if isinstance(entry, LoopSpec)]


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------


def load_spec_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise not_found(
            f"spec not found: {path}",
            hint="author one with `psychopy-cli spec new`",
            next_actions=["psychopy-cli spec new --template minimal"],
        )
    text = path.read_text(encoding="utf-8-sig")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise invalid(
            f"spec is not valid JSON: {path.name}",
            details=[{"path": f"line {exc.lineno}, column {exc.colno}", "message": exc.msg}],
            hint="specs are JSON documents; check quoting and trailing commas",
        ) from exc
    if not isinstance(raw, dict):
        raise invalid(
            "spec root must be a JSON object",
            hint="a spec is an object with `name`, `routines` and `flow`",
        )
    return raw


def parse_spec(raw: dict[str, Any], *, path: Path | None = None, diags: Diagnostics | None = None) -> Spec:
    diags = diags if diags is not None else Diagnostics()

    name = _require_name(raw, diags)
    version = str(raw.get("spec_version", SUPPORTED_SPEC_VERSION))
    if "spec_version" not in raw:
        diags.warn(
            "SPEC_VERSION_MISSING",
            "spec has no `spec_version`; assuming 1.0",
            path="$.spec_version",
            hint='add "spec_version": "1.0"',
        )
    elif version != SUPPORTED_SPEC_VERSION:
        diags.error(
            "SPEC_VERSION_UNSUPPORTED",
            f"unsupported spec_version {version!r}",
            path="$.spec_version",
            hint=f'this build understands "{SUPPORTED_SPEC_VERSION}"',
        )

    window = _parse_window(raw.get("window"), diags)
    info = _parse_info(raw.get("info"), diags)
    routines = _parse_routines(raw.get("routines"), diags)
    flow = _parse_flow(raw.get("flow"), routines, diags)
    data = _parse_data(raw.get("data"), diags)

    return Spec(
        raw=raw,
        path=path,
        name=name,
        spec_version=version,
        window=window,
        info=info,
        routines=routines,
        flow=flow,
        data=data,
        title=raw.get("title") if isinstance(raw.get("title"), str) else None,
    )


def _require_name(raw: dict[str, Any], diags: Diagnostics) -> str:
    name = raw.get("name")
    if not name:
        diags.error(
            "NAME_MISSING",
            "spec needs a `name`",
            path="$.name",
            hint='use a short filename-safe name, e.g. "stroop"',
        )
        return "experiment"
    if not isinstance(name, str):
        diags.error("NAME_TYPE", "`name` must be a string", path="$.name")
        return "experiment"
    if not _FILENAME_SAFE.match(name):
        diags.error(
            "NAME_UNSAFE",
            f"`name` {name!r} contains characters that are unsafe in filenames",
            path="$.name",
            hint="use letters, digits, dot, dash or underscore",
        )
    return name


def _parse_window(raw: Any, diags: Diagnostics) -> WindowSpec:
    window = WindowSpec()
    if raw is None:
        diags.warn(
            "WINDOW_DEFAULTED",
            "no `window` section; using 1024x768, windowed, units=height",
            path="$.window",
        )
        return window
    if not isinstance(raw, dict):
        diags.error("WINDOW_TYPE", "`window` must be an object", path="$.window")
        return window

    size = raw.get("size")
    if size is not None:
        if (
            isinstance(size, (list, tuple)) and len(size) == 2
            and all(isinstance(v, int) and v > 0 for v in size)
        ):
            window.size = (int(size[0]), int(size[1]))
        else:
            diags.error(
                "WINDOW_SIZE",
                "`window.size` must be [width, height] in pixels",
                path="$.window.size",
            )

    fullscreen = raw.get("fullscreen")
    if fullscreen is not None:
        if isinstance(fullscreen, bool):
            window.fullscreen = fullscreen
        else:
            diags.error("WINDOW_FULLSCREEN", "`window.fullscreen` must be true or false", path="$.window.fullscreen")

    units = raw.get("units")
    if units is not None:
        if units in WINDOW_UNITS:
            window.units = units
        else:
            diags.error(
                "WINDOW_UNITS",
                f"`window.units` must be one of {', '.join(WINDOW_UNITS)}",
                path="$.window.units",
                hint="'height' is the least surprising default",
            )

    if "color" in raw:
        window.color = raw["color"]
    if "monitor" in raw:
        if isinstance(raw["monitor"], str):
            window.monitor = raw["monitor"]
        else:
            diags.error("WINDOW_MONITOR", "`window.monitor` must be a string", path="$.window.monitor")
    backend = raw.get("backend")
    if backend is not None:
        if backend in WINDOW_BACKENDS:
            window.backend = backend
        else:
            diags.error(
                "WINDOW_BACKEND",
                f"`window.backend` must be one of {', '.join(WINDOW_BACKENDS)}",
                path="$.window.backend",
            )
    return window


def _parse_info(raw: Any, diags: Diagnostics) -> dict[str, Any]:
    if raw is None:
        return {"participant": "auto", "session": "001"}
    if not isinstance(raw, dict):
        diags.error("INFO_TYPE", "`info` must be an object of experiment-info fields", path="$.info")
        return {"participant": "auto", "session": "001"}
    return {str(k): v for k, v in raw.items()}


def _parse_routines(raw: Any, diags: Diagnostics) -> dict[str, RoutineSpec]:
    routines: dict[str, RoutineSpec] = {}
    if raw is None:
        diags.error(
            "ROUTINES_MISSING",
            "spec needs a `routines` object",
            path="$.routines",
            hint="a routine is one screen of events; at least one is required",
        )
        return routines
    if not isinstance(raw, dict):
        diags.error("ROUTINES_TYPE", "`routines` must be an object keyed by routine name", path="$.routines")
        return routines
    if not raw:
        diags.error("ROUTINES_EMPTY", "`routines` is empty", path="$.routines")

    for routine_name, routine_raw in raw.items():
        routine_path = f"$.routines.{routine_name}"
        if not _IDENT.match(routine_name):
            diags.error(
                "ROUTINE_NAME",
                f"routine name {routine_name!r} must be a valid identifier (letters, digits, underscore)",
                path=routine_path,
                hint="Builder uses routine names as Python variables",
            )
        if not isinstance(routine_raw, dict):
            diags.error("ROUTINE_TYPE", f"routine {routine_name!r} must be an object", path=routine_path)
            continue
        components_raw = routine_raw.get("components", [])
        if not isinstance(components_raw, list):
            diags.error(
                "ROUTINE_COMPONENTS",
                f"routine {routine_name!r}: `components` must be a list",
                path=f"{routine_path}.components",
            )
            continue
        if not components_raw:
            diags.warn(
                "ROUTINE_EMPTY",
                f"routine {routine_name!r} has no components; it will present one blank screen",
                path=f"{routine_path}.components",
            )
        components = [
            _parse_component(comp_raw, f"{routine_path}.components[{index}]", diags)
            for index, comp_raw in enumerate(components_raw)
        ]
        components = [c for c in components if c is not None]
        _check_unique_names(components, routine_name, f"{routine_path}.components", diags)
        routines[routine_name] = RoutineSpec(name=routine_name, components=components)
    return routines


def _parse_component(raw: Any, path: str, diags: Diagnostics) -> ComponentSpec | None:
    if not isinstance(raw, dict):
        diags.error("COMPONENT_TYPE", "component must be an object", path=path)
        return None

    type_raw = raw.get("type")
    if not type_raw:
        diags.error(
            "COMPONENT_NOTYPE",
            "component is missing `type`",
            path=f"{path}.type",
            hint="e.g. \"Text\", \"Image\", \"Grating\", \"Polygon\", \"Keyboard\"",
        )
        return None
    component_type = resolve_component_type(str(type_raw))
    if component_type is None:
        diags.error(
            "COMPONENT_UNKNOWN",
            f"unknown component type {type_raw!r}",
            path=f"{path}.type",
            hint="`psychopy-cli components list` shows the installed types",
        )
        return None

    name = raw.get("name")
    if name is None:
        name = _default_component_name(component_type)
    elif not isinstance(name, str) or not _IDENT.match(name):
        diags.error(
            "COMPONENT_NAME",
            f"component name {name!r} must be a valid identifier",
            path=f"{path}.name",
        )
        name = _default_component_name(component_type)

    start = _parse_start(raw, path, diags)
    end = _parse_end(raw, path, component_type, diags)

    params = raw.get("params") or {}
    if not isinstance(params, dict):
        diags.error("COMPONENT_PARAMS", "`params` must be an object", path=f"{path}.params")
        params = {}

    code = raw.get("code") or {}
    if code and component_type != "CodeComponent":
        diags.error(
            "COMPONENT_CODE_MISPLACED",
            "`code` is only valid on a component of type `Code`",
            path=f"{path}.code",
            hint="use \"type\": \"Code\" with a `code` block",
        )
        code = {}
    if isinstance(code, dict):
        allowed = {"before_experiment", "begin_experiment", "begin_routine", "each_frame", "end_routine", "end_experiment"}
        for key in code:
            if normalize_key(key) not in {normalize_key(a) for a in allowed}:
                diags.error(
                    "CODE_BLOCK_UNKNOWN",
                    f"unknown code block {key!r}",
                    path=f"{path}.code.{key}",
                    hint=f"valid blocks: {', '.join(sorted(allowed))}",
                )
        code = {str(k): str(v) for k, v in code.items() if isinstance(v, str)}
    elif code:
        diags.error("CODE_TYPE", "`code` must be an object of source blocks", path=f"{path}.code")
        code = {}

    disabled = raw.get("disabled", False)
    if not isinstance(disabled, bool):
        diags.error("COMPONENT_DISABLED", "`disabled` must be true or false", path=f"{path}.disabled")
        disabled = False

    known = {"type", "name", "start", "end", "params", "code", "disabled"}
    for key in raw:
        if key not in known:
            diags.warn(
                "COMPONENT_UNKNOWN_KEY",
                f"unknown component key {key!r} ignored",
                path=f"{path}.{key}",
                hint=f"valid keys: {', '.join(sorted(known))}",
            )

    return ComponentSpec(
        type=component_type, name=name, start=start, end=end,
        params=dict(params), code=code, disabled=disabled, path=path,
    )


def _parse_start(raw: dict[str, Any], path: str, diags: Diagnostics) -> Timing:
    if "start" not in raw:
        return Timing("time", 0.0)
    return _parse_timing(raw["start"], f"{path}.start", START_KINDS, Timing("time", 0.0), diags, is_start=True)


def _parse_end(raw: dict[str, Any], path: str, component_type: str, diags: Diagnostics) -> Timing | None:
    if "end" not in raw:
        # Response collectors stay open until the routine ends, matching Builder.
        if component_type in ("KeyboardComponent", "MouseComponent", "ButtonComponent"):
            return None
        return Timing("duration", 1.0)
    return _parse_timing(raw["end"], f"{path}.end", STOP_KINDS, Timing("duration", 1.0), diags, is_start=False)


def _parse_timing(
    raw: Any,
    path: str,
    allowed: Iterable[str],
    default: Timing,
    diags: Diagnostics,
    *,
    is_start: bool,
) -> Timing:
    allowed_set = set(allowed)

    if isinstance(raw, bool):
        diags.error("TIMING_TYPE", "timing must be a number, a condition string, or an object", path=path)
        return default

    if isinstance(raw, (int, float)):
        # A bare number on `end` means duration, which is Builder's default.
        return Timing("time" if is_start else "duration", float(raw))

    if isinstance(raw, str):
        if not raw.strip():
            diags.error("TIMING_EMPTY", "timing expression is empty", path=path)
            return default
        return Timing("condition", raw)

    if isinstance(raw, dict):
        if len(raw) != 1:
            diags.error(
                "TIMING_SHAPE",
                "timing object must have exactly one key from "
                + ", ".join(sorted(allowed_set)),
                path=path,
            )
            return default
        kind, value = next(iter(raw.items()))
        normalized = normalize_key(kind)
        kind_map = {
            "time": "time", "second": "time", "seconds": "time", "s": "time",
            "frame": "frame", "frameN": "frame", "frames": "frame",
            "condition": "condition", "expr": "condition", "code": "condition",
            "duration": "duration", "dur": "duration",
            "durationframes": "duration_frames", "durationframe": "duration_frames",
        }
        resolved = kind_map.get(normalized)
        if resolved is None:
            diags.error(
                "TIMING_KIND",
                f"unknown timing unit {kind!r}",
                path=f"{path}.{kind}",
                hint=f"valid units: {', '.join(sorted(allowed_set))}",
            )
            return default
        if resolved not in allowed_set:
            diags.error(
                "TIMING_UNIT_NOT_ALLOWED",
                f"unit {resolved!r} is not valid here; use one of {', '.join(sorted(allowed_set))}",
                path=f"{path}.{kind}",
            )
            return default
        if resolved == "condition":
            if not isinstance(value, str) or not value.strip():
                diags.error("TIMING_CONDITION", "condition timing needs a non-empty expression string", path=f"{path}.{kind}")
                return default
            return Timing("condition", value)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            diags.error("TIMING_VALUE", f"{resolved} timing needs a number", path=f"{path}.{kind}")
            return default
        if resolved in ("frame", "duration_frames") and float(value) != int(value):
            diags.error("TIMING_FRAME_FRACTION", "frame counts must be whole numbers", path=f"{path}.{kind}")
            return default
        return Timing(resolved, float(value))

    diags.error("TIMING_TYPE", "timing must be a number, a condition string, or an object", path=path)
    return default


def _parse_flow(raw: Any, routines: dict[str, RoutineSpec], diags: Diagnostics) -> list[RoutineRef | LoopSpec]:
    flow: list[RoutineRef | LoopSpec] = []
    if raw is None:
        diags.error(
            "FLOW_MISSING",
            "spec needs a `flow` list",
            path="$.flow",
            hint='e.g. [{"routine": "trial"}] or [{"loop": {...}}]',
        )
        return flow
    if not isinstance(raw, list):
        diags.error("FLOW_TYPE", "`flow` must be a list", path="$.flow")
        return flow
    if not raw:
        diags.error("FLOW_EMPTY", "`flow` is empty; nothing would run", path="$.flow")
        return flow

    for index, entry in enumerate(raw):
        entry_path = f"$.flow[{index}]"
        if not isinstance(entry, dict):
            diags.error("FLOW_ENTRY_TYPE", "flow entry must be an object", path=entry_path)
            continue
        if "routine" in entry:
            name = entry["routine"]
            if not isinstance(name, str):
                diags.error("FLOW_ROUTINE_TYPE", "`routine` must be a routine name string", path=f"{entry_path}.routine")
                continue
            if name not in routines:
                diags.error(
                    "FLOW_ROUTINE_MISSING",
                    f"flow references unknown routine {name!r}",
                    path=f"{entry_path}.routine",
                    hint=f"defined routines: {', '.join(routines) or '(none)'}",
                )
                continue
            flow.append(RoutineRef(routine=name))
        elif "loop" in entry:
            loop = _parse_loop(entry["loop"], f"{entry_path}.loop", routines, diags)
            if loop is not None:
                flow.append(loop)
        else:
            diags.error(
                "FLOW_ENTRY_KIND",
                'flow entry must be {"routine": ...} or {"loop": {...}}',
                path=entry_path,
            )
    return flow


def _parse_loop(raw: Any, path: str, routines: dict[str, RoutineSpec], diags: Diagnostics) -> LoopSpec | None:
    if not isinstance(raw, dict):
        diags.error("LOOP_TYPE", "`loop` must be an object", path=path)
        return None

    name = raw.get("name")
    if not isinstance(name, str) or not _IDENT.match(name):
        diags.error("LOOP_NAME", "loop needs a valid identifier `name`", path=f"{path}.name")
        name = name if isinstance(name, str) else "trials"

    routines_raw = raw.get("routines")
    if isinstance(routines_raw, str):
        routines_raw = [routines_raw]
    if not isinstance(routines_raw, list) or not routines_raw:
        diags.error(
            "LOOP_ROUTINES",
            "loop needs `routines`: one routine name or a non-empty list",
            path=f"{path}.routines",
        )
        return None
    resolved: list[str] = []
    for item in routines_raw:
        if not isinstance(item, str):
            diags.error("LOOP_ROUTINE_TYPE", "loop routine entries must be strings", path=f"{path}.routines")
            continue
        if item not in routines:
            diags.error(
                "LOOP_ROUTINE_MISSING",
                f"loop references unknown routine {item!r}",
                path=f"{path}.routines",
                hint=f"defined routines: {', '.join(routines) or '(none)'}",
            )
            continue
        resolved.append(item)
    if not resolved:
        return None

    if "loop" in raw.get("routines", []) or any(isinstance(r, dict) for r in routines_raw):
        diags.error(
            "LOOP_NESTED_UNSUPPORTED",
            "nested loops are not supported in spec 1.0",
            path=f"{path}.routines",
            hint="flatten the design or express the inner repetition with n_reps",
        )

    n_reps = raw.get("n_reps", 1)
    if not isinstance(n_reps, int) or isinstance(n_reps, bool) or n_reps < 1:
        diags.error("LOOP_NREPS", "`n_reps` must be an integer >= 1", path=f"{path}.n_reps")
        n_reps = 1

    order = raw.get("order", "sequential")
    if order not in ("sequential", "random", "random_per_rep"):
        diags.error(
            "LOOP_ORDER",
            "`order` must be sequential, random or random_per_rep",
            path=f"{path}.order",
        )
        order = "sequential"

    seed = raw.get("seed")
    if seed is not None and not isinstance(seed, int):
        diags.error("LOOP_SEED", "`seed` must be an integer", path=f"{path}.seed")
        seed = None

    conditions = raw.get("conditions") or []
    if not isinstance(conditions, list):
        diags.error("LOOP_CONDITIONS", "`conditions` must be a list of row objects", path=f"{path}.conditions")
        conditions = []
    for row_index, row in enumerate(conditions):
        if not isinstance(row, dict):
            diags.error(
                "LOOP_CONDITION_ROW",
                "each condition row must be an object",
                path=f"{path}.conditions[{row_index}]",
            )
            continue
        for key, value in row.items():
            if not _IDENT.match(str(key)):
                diags.error(
                    "LOOP_CONDITION_KEY",
                    f"condition column {key!r} must be a valid identifier",
                    path=f"{path}.conditions[{row_index}].{key}",
                    hint="columns become variable names inside routines",
                )
            if isinstance(value, dict):
                diags.error(
                    "LOOP_CONDITION_VALUE",
                    f"condition value for {key!r} must be a scalar or a flat list, not an object",
                    path=f"{path}.conditions[{row_index}].{key}",
                )
            elif isinstance(value, list) and any(isinstance(item, (dict, list)) for item in value):
                diags.error(
                    "LOOP_CONDITION_VALUE",
                    f"condition list for {key!r} must be flat (numbers, strings or booleans)",
                    path=f"{path}.conditions[{row_index}].{key}",
                    hint='use [1, 0, 0] for a colour, not [[1], [0], [0]]',
                )

    conditions_file = raw.get("conditions_file")
    if conditions_file is not None:
        if not isinstance(conditions_file, str):
            diags.error("LOOP_CONDITIONS_FILE", "`conditions_file` must be a path string", path=f"{path}.conditions_file")
            conditions_file = None
        elif conditions:
            diags.error(
                "LOOP_CONDITIONS_CONFLICT",
                "provide either inline `conditions` or `conditions_file`, not both",
                path=f"{path}",
            )

    if not conditions and not conditions_file:
        diags.error(
            "LOOP_EMPTY_CONDITIONS",
            "loop has no `conditions` and no `conditions_file`",
            path=f"{path}",
            hint="a loop needs rows to iterate over",
        )

    selected_rows = raw.get("selected_rows", "")
    if not isinstance(selected_rows, str):
        diags.error("LOOP_SELECTED_ROWS", "`selected_rows` must be a string", path=f"{path}.selected_rows")
        selected_rows = ""

    return LoopSpec(
        name=name, routines=resolved, n_reps=n_reps, order=order, seed=seed,
        conditions=[dict(row) for row in conditions if isinstance(row, dict)],
        conditions_file=conditions_file, selected_rows=selected_rows,
    )


def _parse_data(raw: Any, diags: Diagnostics) -> DataSpec:
    data = DataSpec()
    if raw is None:
        return data
    if not isinstance(raw, dict):
        diags.error("DATA_TYPE", "`data` must be an object", path="$.data")
        return data

    filename = raw.get("filename")
    if filename is not None:
        if isinstance(filename, str) and filename.strip():
            data.filename = filename
        else:
            diags.error("DATA_FILENAME", "`data.filename` must be a non-empty string", path="$.data.filename")

    formats = raw.get("formats")
    if formats is not None:
        if isinstance(formats, str):
            formats = [formats]
        if not isinstance(formats, list) or not all(isinstance(f, str) for f in formats):
            diags.error("DATA_FORMATS", "`data.formats` must be a list of format names", path="$.data.formats")
        else:
            unknown = [f for f in formats if f not in ("wide_csv", "csv", "excel", "psydat", "hdf5")]
            if unknown:
                diags.error(
                    "DATA_FORMAT_UNKNOWN",
                    f"unknown data format(s): {', '.join(unknown)}",
                    path="$.data.formats",
                    hint="valid: wide_csv, csv, excel, psydat, hdf5",
                )
            data.formats = formats

    delimiter = raw.get("delimiter")
    if delimiter is not None:
        if isinstance(delimiter, str):
            data.delimiter = delimiter
        else:
            diags.error("DATA_DELIMITER", "`data.delimiter` must be a string", path="$.data.delimiter")
    return data


# --------------------------------------------------------------------------
# semantic checks that need the whole document
# --------------------------------------------------------------------------


def check_spec(spec: Spec, diags: Diagnostics) -> None:
    """Cross-field checks: unused routines, duplicate loops, filename placeholders."""
    used = {ref.routine for ref in spec.flow if isinstance(ref, RoutineRef)}
    for loop in spec.loops:
        used.update(loop.routines)
    for name in spec.routines:
        if name not in used:
            diags.warn(
                "ROUTINE_UNUSED",
                f"routine {name!r} is defined but not in the flow, so it never runs",
                path=f"$.routines.{name}",
            )

    loop_names: list[str] = []
    for index, loop in enumerate(spec.loops):
        if loop.name in loop_names:
            diags.error(
                "LOOP_NAME_DUPLICATE",
                f"loop name {loop.name!r} is used twice",
                path=f"$.flow[{index}]",
                hint="loop names become data columns",
            )
        loop_names.append(loop.name)

    placeholders = set(re.findall(r"\{([a-z_]+)\}", spec.data.filename))
    unknown = placeholders - {"participant", "session", "name", "date", "time", "rand", "now"}
    if unknown:
        diags.error(
            "DATA_FILENAME_PLACEHOLDER",
            f"unknown placeholder(s) in `data.filename`: {', '.join(sorted(unknown))}",
            path="$.data.filename",
            hint="available: participant, session, name, date, time, rand",
        )

    for routine_name, routine in spec.routines.items():
        for index, component in enumerate(routine.components):
            if component.type == "CodeComponent" and component.code:
                continue
            if component.type == "CodeComponent" and not component.code:
                diags.warn(
                    "CODE_EMPTY",
                    f"code component {component.name!r} has no source blocks",
                    path=component.path,
                )


def resolve_component_type(raw: str) -> str | None:
    """Map 'Text', 'text', 'TextComponent' onto the canonical class name."""
    key = normalize_key(raw)
    if key.endswith("component"):
        key = key[: -len("component")]
    return CANONICAL_COMPONENTS.get(key)


def normalize_key(raw: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(raw).lower())


def _default_component_name(component_type: str) -> str:
    base = component_type.replace("Component", "").lower()
    return f"{base}1"


def _check_unique_names(components: list[ComponentSpec], routine_name: str, path: str, diags: Diagnostics) -> None:
    seen: dict[str, int] = {}
    for component in components:
        seen[component.name] = seen.get(component.name, 0) + 1
    for name, count in seen.items():
        if count > 1:
            diags.error(
                "COMPONENT_NAME_DUPLICATE",
                f"component name {name!r} appears {count} times in routine {routine_name!r}",
                path=path,
                hint="names become data column prefixes",
            )


# --------------------------------------------------------------------------
# trial enumeration (shared by validation stats, simulate and the runtime)
# --------------------------------------------------------------------------


def enumerate_trials(spec: Spec, *, seed: int | None = None, max_trials: int = 0) -> list[dict[str, Any]]:
    """Expand the flow into concrete trial rows.

    Nested loops are not supported, so each loop is a flat block of
    ``len(conditions) * n_reps`` trials. A trial carries the condition
    variables, the routines it runs (``__routines``), and the loop bookkeeping
    an agent needs to reproduce an order: ``__loop``, ``__loop_thisN`` (trial
    index) and ``__loop_thisT`` (repetition index).
    """
    rows: list[dict[str, Any]] = []
    for entry in spec.flow:
        if isinstance(entry, RoutineRef):
            rows.append({
                "__routines": [entry.routine],
                "__loop": None,
                "__loop_thisN": -1,
                "__loop_thisT": -1,
            })
            if max_trials and len(rows) >= max_trials:
                return rows[:max_trials]
            continue

        conditions = entry.conditions
        if not conditions and entry.conditions_file:
            conditions = read_conditions_file(spec.dir / entry.conditions_file)

        order = list(range(len(conditions)))
        if entry.order in ("random", "random_per_rep"):
            import random

            rng = random.Random(entry.seed if entry.seed is not None else seed)
            rng.shuffle(order)

        for rep in range(entry.n_reps):
            if entry.order == "random_per_rep":
                import random

                rng = random.Random((entry.seed if entry.seed is not None else (seed or 0)) + rep)
                rng.shuffle(order)
            for position, index in enumerate(order):
                row = dict(conditions[index])
                row.update({
                    "__routines": list(entry.routines),
                    "__loop": entry.name,
                    "__loop_thisN": rep * len(conditions) + position,
                    "__loop_thisT": rep,
                })
                rows.append(row)
                if max_trials and len(rows) >= max_trials:
                    return rows[:max_trials]
    return rows


def read_conditions_file(path: Path) -> list[dict[str, Any]]:
    import csv

    if not path.exists():
        raise not_found(
            f"conditions file not found: {path}",
            hint="check `conditions_file`; it resolves relative to the spec",
        )
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def spec_stats(spec: Spec) -> dict[str, Any]:
    trials = enumerate_trials(spec)
    routines = {name: len(r.components) for name, r in spec.routines.items()}
    return {
        "routines": len(spec.routines),
        "components": sum(routines.values()),
        "loops": len(spec.loops),
        "trials": len(trials),
        "components_per_routine": routines,
    }


__all__ = [
    "SUPPORTED_SPEC_VERSION", "CANONICAL_COMPONENTS", "RUNNABLE_COMPONENTS",
    "Diagnostic", "Diagnostics", "Timing", "ComponentSpec", "RoutineSpec",
    "RoutineRef", "LoopSpec", "WindowSpec", "DataSpec", "Spec",
    "load_spec_file", "parse_spec", "check_spec", "resolve_component_type",
    "normalize_key", "enumerate_trials", "read_conditions_file", "spec_stats",
]
