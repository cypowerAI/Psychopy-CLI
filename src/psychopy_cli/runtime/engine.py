"""Presentation runtime.

A deliberately small interpreter of the spec on top of ``psychopy.visual``
rather than an execution of a generated script. Two reasons:

* the generated Builder script opens an experiment-info dialog, which blocks an
  unattended caller;
* a small interpreter can enforce a timeout, cap the number of trials, and
  inject scripted responses, none of which a generated script exposes.

Supported components are listed in ``HANDLERS``. Everything else is still
compiled into the ``.psyexp`` by ``build`` -- this runtime is for running, not
for completeness.
"""

from __future__ import annotations

import ast
import csv
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..context import ensure_dir
from ..environment import require_psychopy, sanitized_streams
from ..errors import invalid, runtime
from ..spec.model import ComponentSpec, RoutineSpec, Spec, Timing, enumerate_trials, normalize_key

#: Safety valve: a routine that never ends otherwise would hang a caller.
ROUTINE_WALL_LIMIT = 60.0
#: How long a scripted (auto) response waits before "pressing".
AUTO_RESPONSE_LATENCY = 0.25

STATUS_NOT_STARTED = "NOT_STARTED"
STATUS_STARTED = "STARTED"
STATUS_FINISHED = "FINISHED"


@dataclass
class ComponentState:
    """Per-component mutable state, exposed to condition expressions."""

    name: str
    type: str
    status: str = STATUS_NOT_STARTED
    t_start: float | None = None
    t_stop: float | None = None
    rt: float | None = None
    keys: list[str] = field(default_factory=list)
    corr: bool | None = None
    value: Any = None
    stim: Any = None
    ended: bool = False


# --------------------------------------------------------------------------
# value resolution
# --------------------------------------------------------------------------


def resolve_value(raw: Any, namespace: dict[str, Any], *, where: str) -> Any:
    """Resolve a spec parameter into a runtime value.

    Supports the three forms a spec can contain: a native Python value, a
    ``$expression`` referring to trial variables or components, and a string
    that looks like a Python literal (what ``inspect`` produces).
    """
    if not isinstance(raw, str):
        return raw
    stripped = raw.strip()
    if stripped.startswith("$"):
        expression = stripped[1:]
        try:
            return eval(expression, {"__builtins__": _SAFE_BUILTINS}, namespace)  # noqa: S307
        except Exception as exc:
            raise invalid(
                f"could not evaluate {stripped!r} in {where}",
                hint="expressions see trial columns and component attributes (resp.rt, fixation.status)",
                details=[{"path": where, "message": str(exc)}],
            ) from exc
    if stripped[:1] in "[(" and stripped[-1:] in "])":
        try:
            return ast.literal_eval(stripped)
        except (ValueError, SyntaxError):
            return raw
    if stripped in ("True", "False", "None"):
        return {"True": True, "False": False, "None": None}[stripped]
    try:
        return float(stripped) if "." in stripped else int(stripped)
    except ValueError:
        return raw


_SAFE_BUILTINS = {
    "abs": abs, "min": min, "max": max, "len": len, "float": float, "int": int,
    "str": str, "round": round, "sum": sum, "list": list, "dict": dict,
    "True": True, "False": False, "None": None,
}


# --------------------------------------------------------------------------
# component handlers
# --------------------------------------------------------------------------


class Handler:
    """Build a stim, then drive it frame by frame."""

    params: tuple[str, ...] = ()

    def __init__(self, component: ComponentSpec, state: ComponentState, context: "RunContext") -> None:
        self.component = component
        self.state = state
        self.context = context

    def build(self, kwargs: dict[str, Any]) -> None:
        raise NotImplementedError

    def on_start(self) -> None:
        """Called once, the frame the component's start condition is met."""

    def on_frame(self, kwargs: dict[str, Any], elapsed: float) -> None:
        pass

    def close(self) -> None:
        pass


class TextHandler(Handler):
    params = ("text", "color", "letterHeight", "font", "pos", "ori", "wrapWidth", "opacity", "bold", "italic", "units")

    def build(self, kwargs: dict[str, Any]) -> None:
        from psychopy import visual

        text = kwargs.get("text", "")
        stim_kwargs = {
            "win": self.context.window,
            "text": "" if text is None else str(text),
        }
        if "letterHeight" in kwargs:
            stim_kwargs["height"] = kwargs["letterHeight"]
        for key in ("color", "font", "pos", "ori", "wrapWidth", "opacity", "bold", "italic", "units"):
            if key in kwargs:
                stim_kwargs[key] = kwargs[key]
        if "pos" not in kwargs:
            stim_kwargs["pos"] = (0, 0)
        with sanitized_streams():
            self.state.stim = visual.TextStim(**stim_kwargs)


class TextboxHandler(Handler):
    params = ("text", "color", "letterHeight", "font", "pos", "ori", "wrapWidth", "opacity",
              "bold", "italic", "units", "fillColor", "borderColor", "borderWidth")

    def build(self, kwargs: dict[str, Any]) -> None:
        from psychopy import visual

        text = kwargs.get("text", "")
        stim_kwargs: dict[str, Any] = {"win": self.context.window, "text": "" if text is None else str(text)}
        if "letterHeight" in kwargs:
            stim_kwargs["height"] = kwargs["letterHeight"]
        for key in ("color", "font", "pos", "ori", "wrapWidth", "opacity", "bold", "italic",
                    "units", "fillColor", "borderColor", "borderWidth"):
            if key in kwargs:
                stim_kwargs[key] = kwargs[key]
        if "pos" not in kwargs:
            stim_kwargs["pos"] = (0, 0)
        with sanitized_streams():
            try:
                self.state.stim = visual.TextBox2(**stim_kwargs)
            except TypeError:
                self.state.stim = visual.TextStim(**{
                    k: v for k, v in stim_kwargs.items()
                    if k not in ("fillColor", "borderColor", "borderWidth")
                })


class ImageHandler(Handler):
    params = ("image", "pos", "size", "ori", "opacity", "color", "units")

    def build(self, kwargs: dict[str, Any]) -> None:
        from psychopy import visual

        if "image" not in kwargs:
            raise invalid(
                f"component {self.component.name!r} of type Image needs params.image",
                hint="give a file path, e.g. {\"image\": \"stimuli/cue.png\"}",
            )
        path = Path(str(kwargs["image"]))
        if not path.is_absolute():
            path = (self.context.spec.dir / path).resolve()
        if not path.exists():
            raise invalid(
                f"image not found for component {self.component.name!r}: {kwargs['image']}",
                hint=f"looked for {path}",
            )
        stim_kwargs = {"win": self.context.window, "image": str(path)}
        for key in ("pos", "size", "ori", "opacity", "color", "units"):
            if key in kwargs:
                stim_kwargs[key] = kwargs[key]
        with sanitized_streams():
            self.state.stim = visual.ImageStim(**stim_kwargs)


class GratingHandler(Handler):
    params = ("sf", "ori", "size", "pos", "contrast", "phase", "mask", "opacity", "color", "tex")

    def build(self, kwargs: dict[str, Any]) -> None:
        from psychopy import visual

        stim_kwargs = {"win": self.context.window}
        for key in self.params:
            if key in kwargs:
                stim_kwargs[key] = kwargs[key]
        with sanitized_streams():
            self.state.stim = visual.GratingStim(**stim_kwargs)


class PolygonHandler(Handler):
    params = ("shape", "pos", "size", "ori", "fillColor", "lineColor", "lineWidth",
               "opacity", "vertices", "units", "fillColorSpace", "lineColorSpace")

    def build(self, kwargs: dict[str, Any]) -> None:
        from psychopy import visual

        stim_kwargs = {"win": self.context.window}
        for key in self.params:
            if key in kwargs:
                stim_kwargs[key] = kwargs[key]
        with sanitized_streams():
            self.state.stim = visual.Polygon(**stim_kwargs)


class SoundHandler(Handler):
    params = ("sound", "volume", "secs")

    def build(self, kwargs: dict[str, Any]) -> None:
        from psychopy import sound

        value = kwargs.get("sound")
        if value is None:
            raise invalid(
                f"component {self.component.name!r} of type Sound needs params.sound",
                hint="a file path, or a frequency in Hz",
            )
        if isinstance(value, str) and value.lower().endswith((".wav", ".mp3", ".ogg", ".flac")):
            path = Path(value)
            if not path.is_absolute():
                path = (self.context.spec.dir / path).resolve()
            if not path.exists():
                raise invalid(f"sound file not found: {value}", hint=f"looked for {path}")
            value = str(path)
        with sanitized_streams():
            self.state.stim = sound.Sound(
                value=value,
                volume=kwargs.get("volume", 1.0),
                secs=kwargs.get("secs", -1),
            )

    def on_start(self) -> None:
        if self.state.stim is not None:
            with sanitized_streams():
                self.state.stim.play()


class KeyboardHandler(Handler):
    params = ("allowedKeys", "forceEndRoutine", "store", "storeCorrect", "correctAns",
               "discard previous", "registerOn")

    def __init__(self, component: ComponentSpec, state: ComponentState, context: "RunContext") -> None:
        super().__init__(component, state, context)
        self.allowed: list[str] = []
        self.force_end = True
        self.correct_answer: Any = None

    def build(self, kwargs: dict[str, Any]) -> None:
        allowed = kwargs.get("allowedKeys", [])
        if isinstance(allowed, str):
            allowed = [k.strip() for k in allowed.replace("'", "").replace("[", "").replace("]", "").split(",")]
        self.allowed = [str(k) for k in allowed if str(k).strip()]
        self.force_end = bool(kwargs.get("forceEndRoutine", True))
        self.correct_answer = kwargs.get("correctAns")

    def answers(self) -> list[str]:
        """`correctAns` normalized to a list of key strings."""
        raw = self.correct_answer
        if raw is None:
            return []
        if isinstance(raw, str):
            items = raw.replace("'", "").replace("[", "").replace("]", "").split(",")
        elif isinstance(raw, (list, tuple)):
            items = list(raw)
        else:
            items = [raw]
        return [str(item).strip() for item in items if str(item).strip()]

    def register(self, key: str, rt: float) -> None:
        if self.state.keys:
            return  # store="first": the first response is the response
        self.state.keys.append(key)
        self.state.rt = float(rt)
        answers = self.answers()
        if answers:
            self.state.corr = key in answers
        if self.force_end and self.component.end is None:
            self.state.ended = True

    def on_frame(self, kwargs: dict[str, Any], elapsed: float) -> None:
        from psychopy import event

        keys = event.getKeys(keyList=self.allowed or None, timeStamped=self.context.clock)
        for key, timestamp in keys:
            self.register(key, timestamp if timestamp is not None else elapsed)


class MouseHandler(Handler):
    params = ("saveMouseState", "saveParamsClickable", "timeRelativeTo")

    def build(self, kwargs: dict[str, Any]) -> None:
        from psychopy import event

        self._mouse = event.Mouse(win=self.context.window)
        with sanitized_streams():
            self.state.stim = self._mouse

    def on_frame(self, kwargs: dict[str, Any], elapsed: float) -> None:
        import numpy as np

        buttons = self._mouse.getPressed()
        if isinstance(buttons, (list, tuple)) and len(buttons) and any(buttons):
            pos = self._mouse.getPos()
            self.state.value = tuple(float(v) for v in np.asarray(pos).ravel()[:2])


class CodeHandler(Handler):
    """Runs agent-supplied Python at the four Builder hook points."""

    params = ()
    accepts_any = True

    def __init__(self, component: ComponentSpec, state: ComponentState, context: "RunContext") -> None:
        super().__init__(component, state, context)
        self.blocks = {key.replace("-", "_").lower(): value for key, value in component.code.items()}

    def run_block(self, name: str, namespace: dict[str, Any]) -> None:
        source = self.blocks.get(name)
        if not source:
            return
        scope = dict(namespace)
        try:
            exec(compile(source, f"<{self.component.name}:{name}>", "exec"), {"__builtins__": _SAFE_BUILTINS}, scope)  # noqa: S102
        except Exception as exc:
            raise runtime(
                f"code component {self.component.name!r} failed in block {name!r}: {exc}",
                details=[{"path": self.component.name, "message": str(exc)}],
            ) from exc
        # assignments made by the code stay visible to later components and routines
        for key, value in scope.items():
            if key.startswith("__"):
                continue
            if key in namespace and namespace[key] is value:
                continue
            self.context.vars[key] = value

    def build(self, kwargs: dict[str, Any]) -> None:
        self.run_block("begin_routine", self.context.namespace())

    def on_frame(self, kwargs: dict[str, Any], elapsed: float) -> None:
        self.run_block("each_frame", self.context.namespace())

    def close(self) -> None:
        self.run_block("end_routine", self.context.namespace())


HANDLERS: dict[str, type[Handler]] = {
    "TextComponent": TextHandler,
    "TextboxComponent": TextboxHandler,
    "ImageComponent": ImageHandler,
    "GratingComponent": GratingHandler,
    "PolygonComponent": PolygonHandler,
    "SoundComponent": SoundHandler,
    "KeyboardComponent": KeyboardHandler,
    "MouseComponent": MouseHandler,
    "CodeComponent": CodeHandler,
}


# --------------------------------------------------------------------------
# run context and driver
# --------------------------------------------------------------------------


@dataclass
class RunContext:
    spec: Spec
    window: Any
    clock: Any
    trial: dict[str, Any] = field(default_factory=dict)
    states: dict[str, ComponentState] = field(default_factory=dict)
    vars: dict[str, Any] = field(default_factory=dict)
    auto_response: bool = False
    rng: random.Random = field(default_factory=lambda: random.Random(0))

    def namespace(self) -> dict[str, Any]:
        namespace: dict[str, Any] = dict(self.vars)
        namespace.update({k: v for k, v in self.trial.items() if not k.startswith("__")})
        namespace.update({
            "thisTrial": dict(self.trial),
            "win": self.window,
            "t": self.clock.getTime(),
            "frame": getattr(self, "frame", 0),
            "NOT_STARTED": STATUS_NOT_STARTED,
            "STARTED": STATUS_STARTED,
            "FINISHED": STATUS_FINISHED,
            "autoDraw": self.auto_draw,
        })
        namespace.update({name: state for name, state in self.states.items()})
        return namespace

    @staticmethod
    def auto_draw(stim: Any, value: bool = True) -> None:
        """Builder's ``autoDraw`` helper; Window lost its own method in 2026."""
        if stim is not None and hasattr(stim, "setAutoDraw"):
            stim.setAutoDraw(value)


def _should_start(timing: Timing, elapsed: float, frame_index: int, namespace: dict[str, Any], where: str) -> bool:
    if timing.kind == "time":
        return elapsed >= float(timing.value)
    if timing.kind == "frame":
        return frame_index >= int(float(timing.value))
    if timing.kind == "condition":
        return _truthy_condition(str(timing.value), namespace, where)
    return False


def _should_stop(timing: Timing, elapsed: float, t_start: float, frame_index: int, start_frame: int,
                 namespace: dict[str, Any], where: str) -> bool:
    if timing.kind == "duration":
        return (elapsed - t_start) >= float(timing.value)
    if timing.kind == "duration_frames":
        return (frame_index - start_frame) >= int(float(timing.value))
    if timing.kind == "time":
        return elapsed >= float(timing.value)
    if timing.kind == "frame":
        return frame_index >= int(float(timing.value))
    if timing.kind == "condition":
        return _truthy_condition(str(timing.value), namespace, where)
    return False


def _truthy_condition(expression: str, namespace: dict[str, Any], where: str) -> bool:
    try:
        return bool(eval(expression, {"__builtins__": _SAFE_BUILTINS}, namespace))  # noqa: S307
    except Exception as exc:
        raise invalid(
            f"condition {expression!r} in {where} could not be evaluated",
            hint="conditions see trial columns and component attributes, e.g. 'resp.rt'",
            details=[{"path": where, "message": str(exc)}],
        ) from exc


def present(
    spec: Spec,
    *,
    run_dir: Path,
    participant: str,
    session: str,
    timeout: float,
    max_trials: int,
    seed: int | None,
    window_size: tuple[int, int] | None,
    fullscreen: bool | None,
    auto_response: bool,
) -> dict[str, Any]:
    """Present the experiment and write the data file."""
    require_psychopy()
    from psychopy import core, visual

    trials = enumerate_trials(spec, seed=seed, max_trials=max_trials)
    if not trials:
        raise invalid("the flow produced no trials", hint="check `flow` and loop `conditions`")

    ensure_dir(run_dir)
    window_kwargs: dict[str, Any] = {
        "size": window_size or spec.window.size,
        "fullscr": spec.window.fullscreen if fullscreen is None else fullscreen,
        "units": spec.window.units,
        "color": resolve_value(spec.window.color, {}, where="window.color"),
        "monitor": spec.window.monitor,
    }
    if spec.window.backend:
        window_kwargs["winType"] = spec.window.backend

    with sanitized_streams():
        window = visual.Window(**window_kwargs)
    clock = core.Clock()

    context = RunContext(spec=spec, window=window, clock=clock, auto_response=auto_response,
                         rng=random.Random(seed if seed is not None else 0))

    rows: list[dict[str, Any]] = []
    columns: list[str] = []
    aborted_reason: str | None = None
    started = time.time()

    try:
        for trial_index, trial in enumerate(trials):
            if time.time() - started > timeout:
                aborted_reason = f"timeout after {timeout:g}s"
                break
            context.trial = trial
            context.states = {}
            row: dict[str, Any] = {
                "trial_index": trial_index,
                "expName": spec.name,
                "participant": participant,
                "session": session,
                "date": time.strftime("%Y-%m-%d_%H:%M:%S"),
                "loop": trial["__loop"] or "",
                "loop.thisN": trial["__loop_thisN"],
                "loop.thisT": trial["__loop_thisT"],
            }
            for key, value in trial.items():
                if not key.startswith("__"):
                    row[key] = value

            for routine_name in trial["__routines"]:
                routine = spec.routines.get(routine_name)
                if routine is None:
                    raise invalid(f"flow references unknown routine {routine_name!r}")
                _run_routine(context, routine, row)

            rows.append(row)
            for key in row:
                if key not in columns:
                    columns.append(key)
            _write_csv(run_dir / "data.csv", rows, columns)
    finally:
        try:
            with sanitized_streams():
                window.close()
        except Exception:  # pragma: no cover
            pass

    data_path = run_dir / "data.csv"
    _write_csv(data_path, rows, columns)
    return {
        "run_dir": str(run_dir),
        "data_file": str(data_path),
        "n_trials": len(rows),
        "n_trials_planned": len(trials),
        "mode": "present",
        "columns": columns,
        "aborted_reason": aborted_reason,
        "participant": participant,
        "session": session,
    }


def _run_routine(context: RunContext, routine: RoutineSpec, row: dict[str, Any]) -> None:
    """Present one routine and record responses into ``row``."""
    handlers: list[tuple[ComponentState, Handler]] = []
    created: list[tuple[ComponentSpec, ComponentState, Handler]] = []

    for component in routine.components:
        if component.disabled:
            continue
        handler_cls = HANDLERS.get(component.type)
        if handler_cls is None:
            raise invalid(
                f"`run` cannot present {component.type} (component {component.name!r})",
                hint="`build` still compiles it into .psyexp; remove it from the running routine "
                     "or use `build --script`",
                details=[{"path": component.path, "message": "unsupported by the runtime"}],
            )
        state = ComponentState(name=component.name, type=component.type)
        context.states[component.name] = state
        handler = handler_cls(component, state, context)
        created.append((component, state, handler))
        handlers.append((state, handler))

    # Code components first: their 'begin routine' blocks define variables that
    # later components may reference in `$` expressions (e.g. feedback text).
    for component, state, handler in created:
        if isinstance(handler, CodeHandler):
            handler.build({})

    for component, state, handler in created:
        if isinstance(handler, CodeHandler):
            continue
        kwargs = _resolve_kwargs(component, type(handler), context.namespace())
        handler.build(kwargs)

    routine_clock = context.clock
    routine_clock.reset()
    frame_index = 0
    start_frames: dict[str, int] = {}
    namespace = context.namespace()

    try:
        while True:
            elapsed = routine_clock.getTime()
            if elapsed > ROUTINE_WALL_LIMIT:
                break
            namespace = context.namespace()
            context.frame = frame_index

            alive = False
            for state, handler in handlers:
                if state.ended:
                    continue
                component = handler.component
                alive = True

                if state.status == STATUS_NOT_STARTED:
                    if _should_start(component.start, elapsed, frame_index, namespace, component.path):
                        state.status = STATUS_STARTED
                        state.t_start = elapsed
                        start_frames[state.name] = frame_index
                        kwargs = _resolve_kwargs(component, type(handler), namespace)
                        handler.on_start()
                        if state.stim is not None and not isinstance(handler, (KeyboardHandler, MouseHandler, CodeHandler, SoundHandler)):
                            with sanitized_streams():
                                state.stim.setAutoDraw(True)
                        if isinstance(handler, CodeHandler):
                            pass
                    else:
                        continue

                if state.status == STATUS_STARTED:
                    if isinstance(handler, KeyboardHandler) and context.auto_response and state.rt is None:
                        if elapsed - (state.t_start or 0) > AUTO_RESPONSE_LATENCY and handler.allowed:
                            answers = handler.answers()
                            pick = next((key for key in handler.allowed if key in answers), handler.allowed[0])
                            handler.register(pick, elapsed - (state.t_start or 0))

                    kwargs = _resolve_kwargs(component, type(handler), namespace)
                    handler.on_frame(kwargs, elapsed)

                    should_end = state.ended
                    if component.end is None:
                        should_end = should_end or (state.status == STATUS_STARTED and elapsed > ROUTINE_WALL_LIMIT * 0.5)
                    else:
                        should_end = should_end or _should_stop(
                            component.end, elapsed, state.t_start or 0, frame_index,
                            start_frames.get(state.name, 0), namespace, component.path,
                        )
                    if should_end:
                        state.status = STATUS_FINISHED
                        state.ended = True
                        state.t_stop = elapsed
                        if not isinstance(handler, (KeyboardHandler, MouseHandler, CodeHandler)):
                            with sanitized_streams():
                                if state.stim is not None:
                                    state.stim.setAutoDraw(False)

            context.window.flip()
            frame_index += 1
            if not alive:
                break
    finally:
        for state, handler in handlers:
            try:
                handler.close()
            except Exception:  # pragma: no cover
                pass
            _write_row_columns(row, state)


def _resolve_kwargs(component: ComponentSpec, handler_cls: type[Handler], namespace: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if getattr(handler_cls, "accepts_any", False):
        return kwargs
    supported = set(handler_cls.params)
    for key, value in component.params.items():
        matched = None
        normalized = normalize_key(key)
        for candidate in supported:
            if normalize_key(candidate) == normalized:
                matched = candidate
                break
        if matched is None:
            raise invalid(
                f"component {component.name!r} ({component.type}): parameter {key!r} is not supported by `run`",
                hint=f"supported here: {', '.join(sorted(supported)) or '(none)'}; `build` supports all Builder parameters",
            )
        kwargs[matched] = resolve_value(value, namespace, where=f"{component.name}.{key}")
    return kwargs


def _write_row_columns(row: dict[str, Any], state: ComponentState) -> None:
    prefix = state.name
    if state.rt is not None:
        row[f"{prefix}.rt"] = round(state.rt, 4)
    if state.keys:
        row[f"{prefix}.keys"] = "|".join(state.keys)
    if state.corr is not None:
        row[f"{prefix}.corr"] = state.corr
    row[f"{prefix}.status"] = state.status


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in columns})


__all__ = ["present", "HANDLERS", "RunContext", "resolve_value"]
