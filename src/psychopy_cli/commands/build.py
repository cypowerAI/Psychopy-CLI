"""Build commands: spec -> .psyexp, and .psyexp -> spec."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..console import Result
from ..context import refuse_overwrite, write_json
from ..errors import invalid
from ..spec import load_and_check, summarize_diagnostics


def cmd_build(context: Any, args: Any) -> Result:
    path = context.require_file(args.path, what="spec")
    spec, diags = load_and_check(path)
    valid, errors, warnings = summarize_diagnostics(diags)
    if not valid:
        raise invalid(
            f"spec has {len(errors)} error(s); nothing was built",
            hint="run `spec validate` to see them all, then fix and rebuild",
            details=errors,
            next_actions=[f"psychopy-cli spec validate {path}"],
        )

    out_dir = context.resolve(args.output) if args.output else path.parent
    dry_run = bool(getattr(args, "dry_run", False))
    force = bool(getattr(args, "force", False))

    plan = {
        "spec": str(path),
        "name": spec.name,
        "output_dir": str(out_dir),
        "psyexp": str(out_dir / f"{spec.name}.psyexp"),
        "script": bool(getattr(args, "script", False)),
        "conditions": [loop.name for loop in spec.loops],
    }

    if dry_run:
        from ..spec.model import spec_stats

        return Result(data={**plan, "dry_run": True, "stats": spec_stats(spec)})

    if not force and (out_dir / f"{spec.name}.psyexp").exists():
        refuse_overwrite(out_dir / f"{spec.name}.psyexp", force)

    from ..builder.compile import compile_spec

    try:
        result = compile_spec(spec, out_dir, write_script=bool(getattr(args, "script", False)))
    except Exception as exc:
        from ..errors import CliError

        if isinstance(exc, CliError):
            raise
        raise invalid(
            f"the build failed: {exc}",
            hint="check `psychopy-cli doctor` and that every component type is installed",
        ) from exc

    return Result(
        data={
            **result,
            "name": spec.name,
            "spec": str(path),
            "stats": _stats(spec),
            "open_in_builder": f"psychopy {result['psyexp']}",
        },
        warnings=[w["message"] for w in warnings] if warnings else [],
    )


def _stats(spec: Any) -> dict[str, Any]:
    from ..spec.model import spec_stats

    stats = spec_stats(spec)
    stats["duration_note"] = "verify timing with `run --simulate`"
    return stats


def cmd_inspect(context: Any, args: Any) -> Result:
    path = context.require_file(args.path, what="experiment")
    if path.suffix.lower() != ".psyexp":
        raise invalid(
            f"expected a .psyexp file, got {path.suffix or 'no extension'}",
            hint="`inspect` reads Builder experiments; use `spec validate` for JSON specs",
        )

    from ..builder.inspect import inspect_psyexp

    spec_document = inspect_psyexp(path)

    output = getattr(args, "output", None)
    if output:
        target = context.resolve(output)
        refuse_overwrite(target, bool(getattr(args, "force", False)))
        write_json(target, spec_document)
        return Result(data={"path": str(target), "source": str(path), "spec": spec_document})

    return Result(data={"spec": spec_document, "source": str(path)})


__all__ = ["cmd_build", "cmd_inspect"]
