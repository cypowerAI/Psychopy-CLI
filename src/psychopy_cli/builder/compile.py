"""Compiling a spec into real Builder objects and a `.psyexp` file.

The compilation deliberately goes *through* PsychoPy's own classes
(``Experiment``, ``Routine``, component classes, ``TrialHandler``) instead of
templating XML. A generated file is therefore indistinguishable from one
saved by Builder: same defaults, same legacy handling, same schema conformance,
and it round-trips through ``loadFromXML`` -- which is what the round-trip
tests assert.
"""

from __future__ import annotations

import csv
import shutil
import time
from pathlib import Path
from typing import Any

from .. import __version__
from ..context import ensure_dir, sha256_file, write_json
from ..environment import require_psychopy, sanitized_streams
from ..errors import invalid, runtime
from ..spec.model import ComponentSpec, LoopSpec, RoutineRef, Spec
from .params import apply_timing, code_block_keys, resolve_param_key, unknown_param_error, value_for_param

MAX_NAME_LEN = 60


def component_class_map() -> dict[str, Any]:
    """Return Builder component classes keyed by canonical type name."""
    from psychopy.experiment.components import getAllComponents

    with sanitized_streams():
        registry = getAllComponents(fetchIcons=False)
    return dict(registry)


def _apply_settings(exp: Any, spec: Spec) -> None:
    settings = exp.settings.params

    def set_param(key: str, value: str) -> None:
        if key in settings:
            settings[key].val = value

    set_param("expName", spec.name)
    set_param("Full-screen window", "True" if spec.window.fullscreen else "False")
    set_param("Window size (pixels)", f"[{spec.window.size[0]}, {spec.window.size[1]}]")
    set_param("Units", spec.window.units)
    set_param("color", value_for_param(settings["color"], spec.window.color, key="color", component="settings")
              if "color" in settings else "$[0,0,0]")
    set_param("Monitor", spec.window.monitor)
    set_param("Experiment info", _experiment_info_literal(spec.info))
    set_param("Data filename", spec.data.filename)
    set_param("Data file delimiter", spec.data.delimiter)
    set_param("Enable Escape", "True")

    if spec.window.backend:
        set_param("winBackend", spec.window.backend)

    formats = set(spec.data.formats)
    set_param("Save wide csv file", "True" if {"wide_csv", "csv"} & formats else "False")
    set_param("Save csv file", "True" if "csv" in formats else "False")
    set_param("Save excel file", "True" if "excel" in formats else "False")
    set_param("Save psydat file", "True" if "psydat" in formats else "False")
    if "hdf5" in formats:
        set_param("Save hdf5 file", "True")


def _experiment_info_literal(info: dict[str, Any]) -> str:
    """Render the Experiment-info dict, mirroring Builder's 'auto' participant."""
    parts: list[str] = []
    for key, value in info.items():
        if value == "auto" and str(key) == "participant":
            parts.append(f"'{key}':'f\"{{randint(0, 999999):06.0f}}\"'")
        elif isinstance(value, str):
            parts.append(f"{key!r}:{value!r}")
        else:
            parts.append(f"{key!r}:{value!r}")
    return "{" + ", ".join(parts) + "}"


def _write_conditions_csv(loop: LoopSpec, directory: Path) -> Path:
    """Write inline conditions to CSV so the .psyexp stays portable."""
    ensure_dir(directory)
    path = directory / f"{loop.name}.csv"
    columns = loop.condition_columns()
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in loop.conditions:
            writer.writerow({k: _csv_scalar(v) for k, v in row.items() if k in columns})
    return path


def _csv_scalar(value: Any) -> Any:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (list, tuple)):
        return repr(value)
    return value


def _build_component(
    spec: Spec,
    exp: Any,
    routine: Any,
    component: ComponentSpec,
    classes: dict[str, Any],
) -> None:
    cls = classes.get(component.type)
    if cls is None:
        raise invalid(
            f"the installed PsychoPy has no component {component.type!r}",
            hint="`psychopy-cli components list` shows what this version provides",
        )

    with sanitized_streams():
        instance = cls(exp=exp, parentName=routine.name, name=component.name)

    apply_timing(instance, component.start, component.end, name=component.name)

    if component.disabled and "disabled" in instance.params:
        instance.params["disabled"].val = "True"

    for key, value in component.params.items():
        resolved, suggestions = resolve_param_key(instance.params, key, component=component.type)
        if resolved is None:
            raise unknown_param_error(component.type, key, suggestions)
        if resolved in ("startType", "startVal", "stopType", "stopVal"):
            raise invalid(
                f"component {component.name!r}: set timing with `start`/`end`, not params.{resolved}",
                hint='use {"start": 0, "end": {"duration": 1.0}}',
            )
        instance.params[resolved].val = value_for_param(
            instance.params[resolved], value, key=resolved, component=component.type,
        )

    if component.code:
        blocks = code_block_keys(instance.params)
        wanted = {
            "before_experiment": "beforeexperiment",
            "begin_experiment": "beginexperiment",
            "begin_routine": "beginroutine",
            "each_frame": "eachframe",
            "end_routine": "endroutine",
            "end_experiment": "endexperiment",
        }
        for block_name, source in component.code.items():
            target_norm = wanted.get(block_name.replace("-", "_").lower())
            if target_norm is None or target_norm not in blocks:
                raise invalid(
                    f"component {component.name!r}: code block {block_name!r} is not supported by this PsychoPy",
                    hint=f"available blocks: {', '.join(sorted(blocks))}",
                )
            instance.params[blocks[target_norm]].val = source

    routine.addComponent(instance)


def compile_spec(
    spec: Spec,
    out_dir: Path,
    *,
    write_script: bool = False,
    force: bool = True,
) -> dict[str, Any]:
    """Compile the spec and return a manifest describing what was written."""
    require_psychopy()
    try:
        from psychopy.experiment import Experiment
        from psychopy.experiment.flow import LoopInitiator, LoopTerminator
        from psychopy.experiment.loops import TrialHandler
    except Exception as exc:  # pragma: no cover
        raise runtime(f"could not import the Builder API: {exc}") from exc

    ensure_dir(out_dir)
    conditions_dir = out_dir / "conditions"

    classes = component_class_map()
    with sanitized_streams():
        exp = Experiment()
    _apply_settings(exp, spec)

    # ---- routines -------------------------------------------------------
    loops_by_name: dict[str, tuple[LoopSpec, str]] = {}
    for loop in spec.loops:
        conditions_path = _conditions_for_loop(spec, loop, conditions_dir)
        loops_by_name[loop.name] = (loop, conditions_path)

    for routine_name, routine_spec in spec.routines.items():
        with sanitized_streams():
            routine = exp.addRoutine(routine_name)
        for component in routine_spec.components:
            _build_component(spec, exp, routine, component, classes)

    # ---- flow -----------------------------------------------------------
    with sanitized_streams():
        for entry in spec.flow:
            if isinstance(entry, RoutineRef):
                exp.flow.append(exp.routines[entry.routine])
                continue

            loop_spec, conditions_path = loops_by_name[entry.name]
            relative = conditions_path.relative_to(out_dir).as_posix()
            loop_handler = TrialHandler(
                exp=exp,
                name=loop_spec.name,
                loopType={"sequential": "sequential", "random": "random",
                          "random_per_rep": "random"}.get(loop_spec.order, "random"),
                nReps=loop_spec.n_reps,
                conditionsFile=relative,
                randomSeed="" if loop_spec.seed is None else str(loop_spec.seed),
                selectedRows=loop_spec.selected_rows,
            )
            exp.flow.append(LoopInitiator(loop_handler))
            for routine_name in loop_spec.routines:
                exp.flow.append(exp.routines[routine_name])
            exp.flow.append(LoopTerminator(loop_handler))
            exp.requirePsychopyLibs(["data"])

    # ---- write ----------------------------------------------------------
    psyexp_path = out_dir / f"{spec.name}.psyexp"
    try:
        with sanitized_streams():
            saved = exp.saveToXML(str(psyexp_path))
        psyexp_path = Path(saved)
    except Exception as exc:
        raise runtime(f"PsychoPy refused to save the experiment: {exc}") from exc

    artifacts: list[dict[str, Any]] = [
        {
            "path": str(psyexp_path),
            "role": "psyexp",
            "bytes": psyexp_path.stat().st_size,
            "sha256": sha256_file(psyexp_path),
        }
    ]
    for loop_spec, conditions_path in loops_by_name.values():
        artifacts.append({
            "path": str(conditions_path),
            "role": "conditions",
            "bytes": conditions_path.stat().st_size,
            "rows": len(loop_spec.conditions) if loop_spec.conditions else None,
        })

    script_path = _maybe_write_script(exp, psyexp_path, out_dir, write_script)
    if script_path:
        artifacts.append({
            "path": str(script_path),
            "role": "script",
            "bytes": script_path.stat().st_size,
        })

    manifest = {
        "name": spec.name,
        "spec": str(spec.path) if spec.path else None,
        "spec_sha256": sha256_file(spec.path) if spec.path and spec.path.exists() else None,
        "psychopy_version": _psychopy_version(),
        "cli_version": __version__,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "artifacts": artifacts,
    }
    manifest_path = write_json(out_dir / "build-manifest.json", manifest)

    return {
        "output_dir": str(out_dir),
        "psyexp": str(psyexp_path),
        "script": str(script_path) if script_path else None,
        "conditions": [str(p) for _, p in loops_by_name.values()],
        "artifacts": artifacts,
        "manifest": str(manifest_path),
    }


def _conditions_for_loop(spec: Spec, loop: LoopSpec, conditions_dir: Path) -> Path:
    if loop.conditions_file:
        source = (spec.dir / loop.conditions_file).resolve()
        if not source.exists():
            raise invalid(
                f"loop {loop.name!r}: conditions file not found: {loop.conditions_file}",
                hint=f"looked in {spec.dir}",
            )
        ensure_dir(conditions_dir)
        target = conditions_dir / source.name
        if source != target:
            shutil.copyfile(source, target)
        return target
    return _write_conditions_csv(loop, conditions_dir)


def _maybe_write_script(exp: Any, psyexp_path: Path, out_dir: Path, wanted: bool) -> Path | None:
    """`Experiment.writeScript` returns source text instead of writing a file."""
    if not wanted:
        return None
    before = {p for p in out_dir.glob("*.py")}
    try:
        with sanitized_streams():
            returned = exp.writeScript(expPath=str(psyexp_path), target="PsychoPy", modular=True)
    except Exception as exc:
        raise runtime(
            f"PsychoPy could not generate a script from the experiment: {exc}",
            hint="the .psyexp was still written; run it with `psychopy-cli run <spec>` instead",
        ) from exc

    if isinstance(returned, str) and returned.strip():
        target = psyexp_path.with_suffix(".py")
        target.write_text(returned, encoding="utf-8", newline="\n")
        return target

    if isinstance(returned, Path) and returned.exists():
        return returned

    fresh = sorted((p for p in out_dir.glob("*.py") if p not in before), key=lambda p: p.stat().st_mtime)
    if fresh:
        return fresh[-1]
    legacy = sorted(out_dir.glob("*_lastrun.py"), key=lambda p: p.stat().st_mtime)
    return legacy[-1] if legacy else None


def _psychopy_version() -> str | None:
    try:
        import psychopy

        return getattr(psychopy, "__version__", None)
    except Exception:  # pragma: no cover
        return None
