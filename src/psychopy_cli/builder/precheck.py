"""Registry-aware checks: is this component real, is this parameter real?

Structural validation lives in ``spec.model`` and runs without PsychoPy. This
layer adds the checks that need the installed Builder: component existence and
parameter names, with suggestions. `spec validate` runs it when PsychoPy
happens to be installed, so an agent gets typo feedback *before* building.
"""

from __future__ import annotations

from typing import Any

from ..spec.model import Diagnostics, Spec
from .compile import component_class_map
from .params import code_block_keys, resolve_param_key

#: Parameters that `start`/`end` own; a spec must not set them by hand.
_TIMING_PARAMS = {"startType", "startVal", "stopType", "stopVal"}


def check_against_registry(spec: Spec, diags: Diagnostics) -> bool:
    """Return False when the registry could not be consulted."""
    try:
        classes = component_class_map()
    except Exception:
        return False

    exp = _experiment()
    for routine_name, routine in spec.routines.items():
        for component in routine.components:
            cls = classes.get(component.type)
            if cls is None:
                diags.error(
                    "COMPONENT_UNAVAILABLE",
                    f"the installed PsychoPy does not provide {component.type}",
                    path=component.path,
                    hint="`psychopy-cli components list` shows what this version has",
                )
                continue
            instance = _instantiate(cls, exp, routine_name, component.name)
            if instance is None:
                continue

            for key in component.params:
                if key in _TIMING_PARAMS:
                    diags.error(
                        "PARAM_TIMING_MISPLACED",
                        f"component {component.name!r}: timing lives in `start`/`end`, not params.{key}",
                        path=f"{component.path}.params.{key}",
                        hint='use {"start": 0, "end": {"duration": 1.0}}',
                    )
                    continue
                resolved, suggestions = resolve_param_key(instance.params, key, component=component.type)
                if resolved is None:
                    hint = "call `psychopy-cli components describe " + component.type + "`"
                    if suggestions:
                        hint = "did you mean " + ", ".join(suggestions) + "? " + hint
                    diags.error(
                        "PARAM_UNKNOWN",
                        f"{component.type} has no parameter {key!r}",
                        path=f"{component.path}.params.{key}",
                        hint=hint,
                    )

            if component.type == "CodeComponent" and component.code:
                blocks = code_block_keys(instance.params)
                for block in component.code:
                    # Builder's own keys are 'endroutine' etc; ours are 'end_routine'.
                    normalized = block.replace("-", "_").lower().replace("_", "")
                    if normalized not in blocks:
                        diags.error(
                            "CODE_BLOCK_UNSUPPORTED",
                            f"code block {block!r} is not available in this PsychoPy",
                            path=f"{component.path}.code.{block}",
                            hint=f"available: {', '.join(sorted(blocks))}",
                        )
    return True


def _experiment() -> Any:
    from psychopy.experiment import Experiment

    from ..environment import sanitized_streams

    with sanitized_streams():
        return Experiment()


def _instantiate(cls: type, exp: Any, parent: str, name: str) -> Any:
    from ..environment import sanitized_streams

    try:
        with sanitized_streams():
            return cls(exp=exp, parentName=parent, name=name)
    except Exception:  # pragma: no cover - component needs unusual arguments
        return None


__all__ = ["check_against_registry"]
