"""Typed errors that map onto stable process exit codes.

Every failure an agent can cause has a code, a message written for a reader
that cannot see the source tree, and usually a ``hint`` plus ``next`` actions
naming the command that resolves it. The exit code is part of the contract:
an agent can branch on it without parsing free text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Exit codes are a public contract. Do not renumber.
EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_USAGE = 2
EXIT_VALIDATION = 3
EXIT_NOT_FOUND = 4
EXIT_MISSING_DEPENDENCY = 5
EXIT_RUNTIME = 6
EXIT_ENVIRONMENT = 7
EXIT_INTERRUPTED = 130

_CODE_TO_EXIT = {
    "INTERNAL": EXIT_INTERNAL,
    "USAGE": EXIT_USAGE,
    "SPEC_INVALID": EXIT_VALIDATION,
    "NOT_FOUND": EXIT_NOT_FOUND,
    "MISSING_DEPENDENCY": EXIT_MISSING_DEPENDENCY,
    "RUNTIME_ERROR": EXIT_RUNTIME,
    "ENVIRONMENT": EXIT_ENVIRONMENT,
    "INTERRUPTED": EXIT_INTERRUPTED,
}


@dataclass
class CliError(Exception):
    """A failure that is the caller's to fix (or the environment's)."""

    code: str
    message: str
    hint: str | None = None
    details: list[dict[str, Any]] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    exit_code: int | None = None

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.code}: {self.message}"

    @property
    def status(self) -> int:
        if self.exit_code is not None:
            return self.exit_code
        return _CODE_TO_EXIT.get(self.code, EXIT_RUNTIME)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.hint:
            payload["hint"] = self.hint
        if self.details:
            payload["details"] = self.details
        if self.next_actions:
            payload["next"] = self.next_actions
        return payload


def usage(message: str, **kwargs: Any) -> CliError:
    return CliError("USAGE", message, **kwargs)


def not_found(message: str, **kwargs: Any) -> CliError:
    return CliError("NOT_FOUND", message, **kwargs)


def invalid(message: str, **kwargs: Any) -> CliError:
    return CliError("SPEC_INVALID", message, **kwargs)


def missing_dependency(message: str, **kwargs: Any) -> CliError:
    return CliError("MISSING_DEPENDENCY", message, **kwargs)


def runtime(message: str, **kwargs: Any) -> CliError:
    return CliError("RUNTIME_ERROR", message, **kwargs)


def environment(message: str, **kwargs: Any) -> CliError:
    return CliError("ENVIRONMENT", message, **kwargs)
