"""Spec loading and checking entry points used by the commands."""

from __future__ import annotations

from pathlib import Path

from .model import Diagnostics, Spec, check_spec, load_spec_file, parse_spec, spec_stats


def load_and_check(path: Path, *, strict: bool = False) -> tuple[Spec, Diagnostics]:
    """Load a spec from disk, parse it, and run every cross-field check."""
    raw = load_spec_file(path)
    diags = Diagnostics()
    spec = parse_spec(raw, path=path, diags=diags)
    check_spec(spec, diags)
    return spec, diags


def summarize_diagnostics(diags: Diagnostics, *, strict: bool = False) -> tuple[bool, list[dict], list[dict]]:
    errors = [d.to_dict() for d in diags.errors]
    warnings = [d.to_dict() for d in diags.warnings]
    valid = not errors and (not strict or not warnings)
    return valid, errors, warnings


def describe(spec: Spec) -> dict:
    stats = spec_stats(spec)
    return {
        "name": spec.name,
        "title": spec.title,
        "spec_version": spec.spec_version,
        "source": str(spec.path) if spec.path else None,
        **stats,
    }


__all__ = ["load_and_check", "summarize_diagnostics", "describe", "spec_stats"]
