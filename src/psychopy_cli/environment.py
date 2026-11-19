"""Runtime environment probing.

PsychoPy is an optional, slow, and sometimes fragile import: it takes seconds,
it can open dialogs, and it writes to stdout. Everything that touches it goes
through here, so the rest of the package can stay lazy and predictable.
"""

from __future__ import annotations

import contextlib
import importlib
import os
import platform
import sys
from functools import lru_cache
from typing import Any, Iterator

from .errors import environment, missing_dependency, runtime


PSYCHOPY_INSTALL_HINT = (
    "install the optional dependency: `pip install psychopy-cli[psychopy]`, "
    "or install PsychoPy directly with `pip install psychopy`"
)


@lru_cache(maxsize=1)
def psychopy_module() -> Any:
    """Import psychopy once, without letting it write to stdout."""
    try:
        with sanitized_streams():
            return importlib.import_module("psychopy")
    except Exception as exc:  # pragma: no cover - depends on the machine
        raise missing_dependency(
            f"PsychoPy is not importable: {exc}",
            hint=PSYCHOPY_INSTALL_HINT,
            next_actions=["psychopy-cli doctor"],
        ) from exc


def psychopy_info() -> dict[str, Any]:
    """Describe the PsychoPy installation without failing when it is absent."""
    info: dict[str, Any] = {
        "available": False,
        "version": None,
        "path": None,
        "error": None,
    }
    try:
        module = psychopy_module()
    except Exception as exc:
        info["error"] = str(exc)
        return info
    info["available"] = True
    try:
        info["version"] = module.__version__
        info["path"] = os.path.dirname(getattr(module, "__file__", "") or "")
    except Exception as exc:  # pragma: no cover
        info["error"] = str(exc)
    return info


def require_psychopy() -> Any:
    return psychopy_module()


def python_info() -> dict[str, Any]:
    return {
        "version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "executable": sys.executable,
        "platform": platform.platform(),
        "supports_psychopy_range": _within_supported_range(platform.python_version()),
    }


def _within_supported_range(version: str) -> bool:
    """PsychoPy 2026.x requires >=3.10,<3.13."""
    try:
        parts = [int(p) for p in version.split(".")[:2]]
    except ValueError:
        return False
    return (3, 10) <= (tuple(parts)) < (3, 13)  # type: ignore[return-value]


def stim_dependencies() -> dict[str, Any]:
    status: dict[str, Any] = {"numpy": None, "pillow": None, "available": False}
    for name, module_name in (("numpy", "numpy"), ("pillow", "PIL")):
        try:
            module = importlib.import_module(module_name)
            status[name] = getattr(module, "__version__", "unknown")
        except Exception:
            status[name] = None
    status["available"] = status["numpy"] is not None and status["pillow"] is not None
    return status


def require_stim_dependencies() -> tuple[Any, Any]:
    """Return (numpy, PIL.Image), or raise with an install hint."""
    try:
        numpy = importlib.import_module("numpy")
        image = importlib.import_module("PIL.Image")
    except Exception as exc:  # pragma: no cover - depends on the machine
        raise missing_dependency(
            f"stimulus rendering needs numpy and Pillow: {exc}",
            hint="install the optional dependency: `pip install psychopy-cli[stim]`",
        ) from exc
    return numpy, image


def component_registry() -> dict[str, Any]:
    """Return the installed Builder component registry."""
    require_psychopy()
    try:
        with sanitized_streams():
            module = importlib.import_module("psychopy.experiment.components")
            return module.getAllComponents(fetchIcons=False)
    except Exception as exc:  # pragma: no cover
        raise runtime(f"could not read the PsychoPy component registry: {exc}") from exc


def display_probe(backends: tuple[str, ...] = ("pyglet", "pygame", "glfw")) -> dict[str, Any]:
    """Try to open and immediately close a window with each backend.

    This really does open a window, so it requires a display and is only run
    when the caller asks for it.
    """
    require_psychopy()
    result: dict[str, Any] = {"checked": True, "backends": {}}
    try:
        with sanitized_streams():
            visual = importlib.import_module("psychopy.visual")
    except Exception as exc:  # pragma: no cover
        return {"checked": True, "backends": {}, "error": str(exc)}

    for backend in backends:
        try:
            with sanitized_streams():
                window = visual.Window(
                    (320, 240), fullscr=False, screen=0, winType=backend,
                    units="pix", checkTiming=False, autoLog=False, allowStencil=False,
                )
                window.flip()
                window.close()
            result["backends"][backend] = {"works": True, "error": None}
        except Exception as exc:
            result["backends"][backend] = {"works": False, "error": str(exc)[:200]}
    result["working"] = [b for b, s in result["backends"].items() if s["works"]]
    return result


def has_display() -> bool:
    """Cheap heuristic; the real answer needs `display_probe`."""
    if os.environ.get("PSYCHOPY_CLI_FORCE_HEADLESS") == "1":
        return False
    if sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        return False
    return True


@contextlib.contextmanager
def sanitized_streams() -> Iterator[None]:
    """Silence the third-party chatter that would corrupt our stdout contract.

    PsychoPy and its dependencies print version banners, monitor warnings and
    frame-rate messages at import and at run time. Our stdout carries exactly
    one document, so anything they emit is rerouted to stderr.
    """
    real_stdout = sys.stdout
    real_stderr = sys.stderr
    try:
        sys.stdout = real_stderr
        yield
    finally:
        sys.stdout = real_stdout
        sys.stderr = real_stderr


def ensure_writable(path: Any) -> None:
    from pathlib import Path

    target = Path(path)
    probe_dir = target if target.is_dir() else target.parent
    if not probe_dir.exists():
        raise environment(f"directory does not exist: {probe_dir}")
    if not os.access(probe_dir, os.W_OK):
        raise environment(f"directory is not writable: {probe_dir}")
