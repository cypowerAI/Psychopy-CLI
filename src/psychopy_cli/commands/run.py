"""Running an experiment: rehearse the design, or present it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..console import Result
from ..context import ensure_dir, slugify, timestamp_slug, write_json
from ..errors import invalid, usage
from ..spec import load_and_check, summarize_diagnostics


def cmd_run(context: Any, args: Any) -> Result:
    path = context.require_file(args.path, what="experiment")
    spec, warnings = _load(path, context)

    simulate = bool(getattr(args, "simulate", False))
    seed = getattr(args, "seed", None)
    max_trials = int(getattr(args, "max_trials", 0) or 0)
    timeout = float(getattr(args, "timeout", 600.0) or 600.0)
    participant = getattr(args, "participant", None) or "auto"
    if participant == "auto":
        import random

        participant = f"s{random.randint(0, 999999):06d}"
    session = getattr(args, "session", None) or "001"

    run_dir = _run_dir(context, args.output, spec.name)

    window_size = _parse_size(getattr(args, "window_size", None))
    fullscreen = getattr(args, "fullscreen", None)
    auto_response = bool(getattr(args, "auto_response", False))

    if simulate:
        from ..runtime.simulate import design_summary, simulate, write_design_csv

        table = simulate(spec, seed=seed, max_trials=max_trials)
        if not table:
            raise invalid("the flow produced no trials", hint="check `flow` and loop `conditions`")
        design_path = write_design_csv(table, run_dir / "design.csv")
        summary = design_summary(spec, table)
        manifest = _manifest(spec, run_dir, "simulate", participant, session, summary)
        _write_manifest(run_dir, manifest)
        return Result(
            data={
                "run_dir": str(run_dir),
                "design_file": str(design_path),
                "data_file": None,
                "mode": "simulate",
                "n_trials": len(table),
                "summary": summary,
                "warnings": warnings,
            },
            warnings=warnings,
        )

    from ..runtime.engine import present

    result = present(
        spec,
        run_dir=run_dir,
        participant=participant,
        session=session,
        timeout=timeout,
        max_trials=max_trials,
        seed=seed,
        window_size=window_size,
        fullscreen=fullscreen,
        auto_response=auto_response,
    )
    summary = _post_run_summary(Path(result["data_file"]))
    manifest = _manifest(spec, run_dir, "present", participant, session, summary)
    _write_manifest(run_dir, manifest)
    return Result(
        data={
            **result,
            "summary": summary,
            "warnings": warnings,
        },
        warnings=([f"run ended early: {result['aborted_reason']}"] if result.get("aborted_reason") else []),
    )


def _load(path: Path, context: Any) -> tuple[Any, list[str]]:
    if path.suffix.lower() == ".psyexp":
        from ..builder.inspect import inspect_psyexp
        from ..spec.model import Diagnostics, parse_spec

        document = inspect_psyexp(path)
        diags = Diagnostics()
        spec = parse_spec(document, path=path, diags=diags)
        if diags.errors:
            raise invalid(
                "the .psyexp could not be converted into a runnable spec",
                details=[d.to_dict() for d in diags.errors],
            )
        return spec, [d.message for d in diags.warnings]

    spec, diags = load_and_check(path)
    valid, errors, warnings = summarize_diagnostics(diags)
    if not valid:
        raise invalid(
            f"spec has {len(errors)} error(s); nothing was run",
            hint="fix them, or rehearse with `--simulate` after editing",
            details=errors,
            next_actions=[f"psychopy-cli spec validate {path}", f"psychopy-cli run {path} --simulate"],
        )
    return spec, [w["message"] for w in warnings]


def _run_dir(context: Any, requested: str | None, name: str) -> Path:
    if requested:
        return context.resolve(requested)
    return context.cwd / "runs" / f"{timestamp_slug()}-{slugify(name)}"


def _parse_size(raw: str | None) -> tuple[int, int] | None:
    if not raw:
        return None
    parts = str(raw).lower().replace(" ", "").split("x")
    if len(parts) != 2:
        raise usage(
            f"window size {raw!r} is not WIDTHxHEIGHT",
            hint="for example --window-size 1024x768",
        )
    try:
        width, height = int(parts[0]), int(parts[1])
    except ValueError:
        raise usage(f"window size {raw!r} must contain integers")
    return (width, height)


def _post_run_summary(data_file: Path) -> dict[str, Any]:
    try:
        from ..analysis.summary import summarize

        result = summarize(data_file)
        return {
            "rows": result["rows"],
            "overall": result["overall"],
        }
    except Exception:  # pragma: no cover - a missing summary must not fail a run
        return {}


def _manifest(spec: Any, run_dir: Path, mode: str, participant: str, session: str, summary: dict[str, Any]) -> dict[str, Any]:
    import time

    from .. import __version__
    from ..context import sha256_file

    return {
        "mode": mode,
        "name": spec.name,
        "spec": str(spec.path) if spec.path else None,
        "spec_sha256": sha256_file(spec.path) if spec.path and spec.path.exists() else None,
        "participant": participant,
        "session": session,
        "cli_version": __version__,
        "run_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": summary,
    }


def _write_manifest(run_dir: Path, manifest: dict[str, Any]) -> None:
    ensure_dir(run_dir)
    write_json(run_dir / "run-manifest.json", manifest)


__all__ = ["cmd_run"]
