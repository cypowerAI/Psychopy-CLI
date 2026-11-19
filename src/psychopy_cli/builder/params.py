"""Translating spec parameter names and values into Builder parameters.

Two jobs:

* **Forgiving names.** An agent writes keys from memory. ``letter_height``,
``Letter Height``, ``letterHeight`` and a near-miss like ``letterHeigth`` all
have to land on the same Builder parameter, or every call becomes a
guess-and-retry loop. Exact matches win; then normalised names; then labels;
then a conservative fuzzy match that suggests instead of silently guessing.
* **Correct value syntax.** Builder parameters are strings that are later
``eval``-ed or parsed. Colours need ``$[1, 0, 0]``, list parameters need
``[0, 0.1]``, booleans need ``True``/``False``. Getting this wrong produces a
file that opens but misbehaves, which is the worst failure mode.
"""

from __future__ import annotations

import difflib
from typing import Any, Iterable

from ..errors import invalid
from ..spec.model import Timing, normalize_key

#: Names an agent is likely to reach for that are not the Builder key.
ALIASES: dict[str, str] = {
    "allowed_keys": "allowedKeys",
    "allowedkeyslist": "allowedKeys",
    "correct_answer": "correctAns",
    "correctanswer": "correctAns",
    "store_correct": "storeCorrect",
    "force_end_routine": "forceEndRoutine",
    "letter_height": "letterHeight",
    "wrap_width": "wrapWidth",
    "fill_color": "fillColor",
    "line_color": "lineColor",
    "line_width": "lineWidth",
    "color_space": "colorSpace",
    "background_color": "color",
    "image_path": "image",
    "imagefile": "image",
    "sound_file": "sound",
}


def resolve_param_key(
    params: dict[str, Any],
    requested: str,
    *,
    component: str,
) -> tuple[str | None, list[str]]:
    """Find the Builder parameter key behind a caller's name.

    Returns ``(key, suggestions)``; ``key`` is None when nothing plausible
    matched, in which case ``suggestions`` lists the nearest real keys.
    """
    keys = list(params.keys())

    # 1. exact
    if requested in params:
        return requested, []

    # 2. normalised key (ignores case, spaces, underscores, hyphens)
    norm = normalize_key(requested)
    for key in keys:
        if normalize_key(key) == norm:
            return key, []

    # 3. Builder label, e.g. "Letter Height"
    for key, param in params.items():
        label = getattr(param, "label", None)
        if label and normalize_key(label) == norm:
            return key, []

    # 4. known aliases
    alias = ALIASES.get(norm)
    if alias and alias in params:
        return alias, []

    # 5. conservative fuzzy match -- suggest, do not guess
    close = difflib.get_close_matches(norm, [normalize_key(k) for k in keys], n=3, cutoff=0.86)
    suggestions = [k for k in keys if normalize_key(k) in close]
    return None, suggestions


def value_for_param(param: Any, value: Any, *, key: str, component: str) -> str:
    """Render a Python value as the string Builder expects for this param."""
    val_type = getattr(param, "valType", "str")

    if isinstance(value, bool):
        return "True" if value else "False"
    if value is None:
        return ""

    if val_type == "color":
        if isinstance(value, (list, tuple)) and len(value) in (3, 4) and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in value
        ):
            # Builder's canonical literal-colour form.
            return "$[" + ", ".join(_number(v) for v in value) + "]"
        if isinstance(value, str):
            return value
        raise invalid(
            f"parameter {key!r} of {component} expects a colour",
            hint="use a name ('red'), '#rrggbb', [r, g, b] in 0..1, or a $expression",
            details=[{"path": component, "message": f"got {value!r}"}],
        )

    if val_type == "list":
        if isinstance(value, (list, tuple)):
            return "[" + ", ".join(_literal(v) for v in value) + "]"
        if isinstance(value, str):
            return value
        raise invalid(f"parameter {key!r} of {component} expects a list", details=[{"message": f"got {value!r}"}])

    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_literal(v) for v in value) + "]"

    if isinstance(value, float):
        return repr(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value
    raise invalid(
        f"parameter {key!r} of {component} has an unsupported value type {type(value).__name__}",
        hint="parameters accept strings, numbers, booleans and flat lists",
    )


def _number(value: float | int) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return repr(value) if isinstance(value, float) else str(value)


def _literal(value: Any) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return _number(value)
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_literal(v) for v in value) + "]"
    return repr(value)


START_TYPE_LABELS = {
    "time": "time (s)",
    "frame": "frame N",
    "condition": "condition",
}

STOP_TYPE_LABELS = {
    "duration": "duration (s)",
    "duration_frames": "duration (frames)",
    "time": "time (s)",
    "frame": "frame N",
    "condition": "condition",
}


def apply_timing(component: Any, start: Timing, end: Timing | None, *, name: str) -> bool:
    """Write start/stop timing onto a Builder component.

    Code components (and a few others) have no timing controls at all, so the
    timing is simply not applicable; the component still runs at its hook
    points. Returns whether timing was written.
    """
    params = component.params
    if not {"startType", "startVal", "stopType", "stopVal"} & set(params):
        return False

    start_type = START_TYPE_LABELS.get(start.kind)
    if start_type is None:
        raise invalid(f"component {name!r}: unsupported start unit {start.kind!r}")
    params["startType"].val = start_type
    params["startVal"].val = _timing_value(start)

    params["stopType"].val = STOP_TYPE_LABELS.get(end.kind, "duration (s)") if end else "duration (s)"
    params["stopVal"].val = _timing_value(end) if end else ""
    return True


def _timing_value(timing: Timing | None) -> str:
    if timing is None:
        return ""
    if timing.kind == "condition":
        return str(timing.value)
    if timing.kind in ("frame", "duration_frames"):
        return str(int(float(timing.value)))
    value = float(timing.value)
    return repr(value) if not value.is_integer() else f"{value:.1f}"


def code_block_keys(params: dict[str, Any]) -> dict[str, str]:
    """Map our snake_case code block names onto the Builder keys."""
    mapping: dict[str, str] = {}
    for key in params:
        norm = normalize_key(key)
        if norm.startswith(("beforeexperiment", "beginexperiment", "beginroutine",
                            "eachframe", "endroutine", "endexperiment")):
            mapping[norm] = key
    return mapping


def describe_param(param: Any) -> dict[str, Any]:
    allowed = getattr(param, "allowedVals", None) or []
    return {
        "default": getattr(param, "val", None),
        "type": getattr(param, "valType", None),
        "input": getattr(param, "inputType", None),
        "allowed": list(allowed),
        "label": getattr(param, "label", None),
    }


def unknown_param_error(component: str, key: str, suggestions: Iterable[str]) -> Exception:
    suggestions = list(suggestions)
    hint = "call `psychopy-cli components describe " + component + "` for the parameter list"
    if suggestions:
        hint = f"did you mean {', '.join(suggestions)}? " + hint
    return invalid(
        f"{component} has no parameter {key!r}",
        hint=hint,
        details=[{"path": key, "message": "unknown parameter"}],
        next_actions=[f"psychopy-cli components describe {component}"],
    )
