"""Spec authoring commands: `spec schema`, `spec new`, `spec validate`."""

from __future__ import annotations

import json
from typing import Any

from ..console import Result
from ..context import refuse_overwrite, write_json
from ..errors import invalid
from ..spec import load_and_check, summarize_diagnostics
from ..spec.model import spec_stats
from ..spec.schema import spec_json_schema
from ..spec.templates import TEMPLATES, template_document


def cmd_spec_schema(context: Any, args: Any) -> Result:
    schema = spec_json_schema()
    return Result(data={
        "schema": schema,
        "templates": sorted(TEMPLATES),
        "conventions": {
            "end_shorthand": "a bare number on `end` means duration in seconds, matching Builder",
            "end_default": "1.0s for visual components, open-ended for Keyboard/Mouse/Button",
            "code_values": "a string starting with $ is evaluated per trial, e.g. \"$word\"",
            "forgiving_keys": "parameter names ignore case, spaces and underscores",
        },
    })


def cmd_spec_new(context: Any, args: Any) -> Result:
    template = args.template or "minimal"
    document = template_document(template)
    output = args.output or f"{template}.spec.json"
    path = context.resolve(output)
    refuse_overwrite(path, bool(getattr(args, "force", False)))
    write_json(path, document)
    return Result(data={
        "path": str(path),
        "template": template,
        "name": document["name"],
        "trials": spec_stats(_parse(document, path)),
        "next": f"psychopy-cli spec validate {path}",
    })


def _parse(document: dict[str, Any], path: Any):
    from ..spec.model import Diagnostics, parse_spec

    diags = Diagnostics()
    return parse_spec(document, path=path, diags=diags)


def cmd_spec_validate(context: Any, args: Any) -> Result:
    path = context.require_file(args.path, what="spec")
    try:
        spec, diags = load_and_check(path, strict=bool(getattr(args, "strict", False)))
    except Exception as exc:
        from ..errors import CliError

        if isinstance(exc, CliError):
            raise
        raise invalid(f"could not read the spec: {exc}") from exc

    notes: list[str] = []
    registry_checked = False
    try:
        from ..builder.precheck import check_against_registry

        registry_checked = check_against_registry(spec, diags)
    except Exception as exc:  # pragma: no cover - defensive
        notes.append(f"registry checks skipped: {exc}")
    if not registry_checked:
        notes.append(
            "component and parameter names were not checked against PsychoPy "
            "(not installed); structural checks only"
        )

    valid, errors, warnings = summarize_diagnostics(diags, strict=bool(getattr(args, "strict", False)))
    stats = spec_stats(spec)

    if not valid:
        raise invalid(
            f"spec has {len(errors)} error(s)",
            hint="fix the entries in `details`, then re-run `spec validate`",
            details=_flatten(errors),
            next_actions=[f"psychopy-cli spec schema"],
        )
    return Result(
        data={
            "valid": True,
            "path": str(path),
            "name": spec.name,
            "source": str(path),
            "errors": [],
            "warnings": warnings,
            "stats": stats,
            "checks": {"structure": True, "registry": registry_checked},
            "notes": notes,
        },
        warnings=[w["message"] for w in warnings] if warnings else [],
    )


def _flatten(diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "path": item.get("path", ""),
            "code": item.get("code", ""),
            "message": item.get("message", ""),
            **({"hint": item["hint"]} if item.get("hint") else {}),
        }
        for item in diagnostics
    ]


__all__ = ["cmd_spec_schema", "cmd_spec_new", "cmd_spec_validate"]
