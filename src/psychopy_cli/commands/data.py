"""Data commands."""

from __future__ import annotations

from typing import Any

from ..analysis.summary import summarize
from ..console import Result


def cmd_data_summarize(context: Any, args: Any) -> Result:
    path = context.require_file(args.path, what="data file")
    group_by = getattr(args, "group_by", None) or []
    result = summarize(
        path,
        group_by=group_by,
        rt_column=getattr(args, "rt_column", None),
        correct_column=getattr(args, "correct_column", None),
    )
    if not result["overall"]:
        from ..errors import invalid

        raise invalid(f"no rows in {path.name}", hint="did the run finish?")
    return Result(data=result)


__all__ = ["cmd_data_summarize"]
