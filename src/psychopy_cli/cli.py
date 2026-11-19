"""Entry point: parse, dispatch, print exactly one document, exit with a code."""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Sequence

from . import console
from .context import Context
from .errors import (
    EXIT_INTERNAL,
    EXIT_INTERRUPTED,
    EXIT_USAGE,
    CliError,
    usage,
)
from .registry import build_parser, find_command

_HANDLER_CACHE: dict[str, Any] = {}


class _Parser(argparse.ArgumentParser):
    """argparse that raises instead of calling sys.exit on bad usage."""

    def error(self, message: str):  # type: ignore[override]
        raise usage(message, hint=f"see `{self.prog} --help`")


class _StdoutIsolation:
    """Route incidental writes to stderr while a handler runs.

    The handler may import PsychoPy, call libraries that print, or be given a
    third-party function that logs. None of that may land on stdout, because
    stdout carries the single JSON envelope the caller parses.
    """

    def __init__(self) -> None:
        self._real = sys.stdout

    def __enter__(self) -> "_StdoutIsolation":
        sys.stdout = sys.stderr  # type: ignore[assignment]
        return self

    def __exit__(self, *exc: object) -> None:
        sys.stdout = self._real


def _load_handler(spec: str) -> Any:
    if spec in _HANDLER_CACHE:
        return _HANDLER_CACHE[spec]
    module_name, _, function_name = spec.partition(":")
    module = importlib.import_module(module_name)
    handler = getattr(module, function_name)
    _HANDLER_CACHE[spec] = handler
    return handler


def _resolve_command_id(namespace: argparse.Namespace) -> str:
    command_id = getattr(namespace, "_command_id", None)
    if command_id:
        return command_id
    raise usage(
        "no command given",
        hint="run `psychopy-cli catalog` to see every command, or `--help`",
        next_actions=["psychopy-cli catalog"],
    )


def _build_context(namespace: argparse.Namespace) -> Context:
    cwd = Path(namespace.cwd).expanduser().resolve() if namespace.cwd else Path.cwd()
    requested = namespace.format or namespace.global_format or "auto"
    return Context(cwd=cwd, fmt=console.resolve_format(requested))


def _write(stream: Any, text: str) -> None:
    try:
        stream.write(text)
        if not text.endswith("\n"):
            stream.write("\n")
        stream.flush()
    except UnicodeEncodeError:  # pragma: no cover - legacy console code pages
        stream.write(text.encode("ascii", "backslashreplace").decode("ascii") + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser(_Parser)
    real_stdout = sys.stdout

    started = time.perf_counter()
    fmt = console.resolve_format("auto")
    command_path = ""
    try:
        namespace = parser.parse_args(argv)
        command = find_command(getattr(namespace, "_command_id", "") or "")
        command_path = command.path if command else ""
        context = _build_context(namespace)
        fmt = context.fmt

        if command is None:
            raise usage(
                "no command given",
                hint="run `psychopy-cli catalog` to see every command",
                next_actions=["psychopy-cli catalog"],
            )

        handler = _load_handler(command.handler)
        with _StdoutIsolation():
            result = handler(context, namespace)

        if result is None:  # defensive: a handler must return a Result
            raise CliError("INTERNAL", f"{command.id} returned no result")
        elapsed = (time.perf_counter() - started) * 1000
        envelope = console.ok_envelope(command.id, result, elapsed, fmt)
        if fmt == "json":
            _write(real_stdout, console.dumps(envelope))
        else:
            _write(real_stdout, console.render_result(command.path, result.data))
            for warning in result.warnings:
                sys.stderr.write(f"warning: {warning}\n")
        return 0

    except CliError as error:
        elapsed = (time.perf_counter() - started) * 1000
        if fmt == "json":
            _write(real_stdout, console.dumps(console.error_envelope(command_path, error, elapsed)))
        else:
            _write(sys.stderr, console.emit_error_text(error))
        return error.status

    except KeyboardInterrupt:  # pragma: no cover
        error = CliError("INTERRUPTED", "interrupted", exit_code=EXIT_INTERRUPTED)
        if fmt == "json":
            _write(real_stdout, console.dumps(console.error_envelope(command_path, error, 0)))
        else:
            _write(sys.stderr, "interrupted")
        return EXIT_INTERRUPTED

    except SystemExit:
        raise

    except Exception as exc:  # pragma: no cover - last resort
        if os.environ.get("PSYCHOPY_CLI_DEBUG") == "1" or "--debug" in argv:
            traceback.print_exc(file=sys.stderr)
        error = CliError(
            "INTERNAL",
            f"{type(exc).__name__}: {exc}",
            hint="re-run with --debug for a traceback; this is likely a bug in psychopy-cli",
            exit_code=EXIT_INTERNAL,
        )
        elapsed = (time.perf_counter() - started) * 1000
        if fmt == "json":
            _write(real_stdout, console.dumps(console.error_envelope(command_path, error, elapsed)))
        else:
            _write(sys.stderr, console.emit_error_text(error))
        return EXIT_INTERNAL


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
