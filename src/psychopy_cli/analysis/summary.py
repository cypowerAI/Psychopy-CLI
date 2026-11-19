"""Summarising result files with the standard library only.

An agent needs three numbers after a run -- did it finish, how accurate, how
fast -- and a way to group them by condition. This does exactly that, without
pulling pandas into a tool whose selling point is that you can inspect it before
installing anything heavy.
"""

from __future__ import annotations

import csv
import math
import statistics
from pathlib import Path
from typing import Any

from ..errors import invalid, not_found

_TRUE = {"1", "true", "yes", "y", "t", "correct"}
_FALSE = {"0", "false", "no", "n", "f", "incorrect"}


def read_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        raise not_found(f"data file not found: {path}")
    if path.suffix.lower() != ".csv":
        raise invalid(
            f"summarising expects a CSV, got {path.suffix or 'no extension'}",
            hint="`build` and `run` write CSV; pass the data.csv from a run directory",
        )
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [dict(row) for row in reader]
        columns = list(reader.fieldnames or [])
    return rows, columns


def _as_bool(raw: Any) -> bool | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


def _as_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(value) else value


def _pick_column(columns: list[str], explicit: str | None, suffix: str) -> str | None:
    if explicit:
        return explicit if explicit in columns else None
    for column in columns:
        if column.lower().endswith(suffix):
            return column
    return None


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "median": None, "sd": None, "min": None, "max": None}
    mean = statistics.fmean(values)
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    return {
        "n": len(values),
        "mean": round(mean, 4),
        "median": round(statistics.median(values), 4),
        "sd": round(sd, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def summarize(
    path: Path,
    *,
    group_by: list[str] | None = None,
    rt_column: str | None = None,
    correct_column: str | None = None,
) -> dict[str, Any]:
    rows, columns = read_rows(path)
    rt = _pick_column(columns, rt_column, ".rt")
    correct = _pick_column(columns, correct_column, ".corr")

    groups: list[str] = [c for c in (group_by or []) if c]
    for column in groups:
        if column not in columns:
            raise invalid(
                f"cannot group by {column!r}: not a column in {path.name}",
                hint=f"columns: {', '.join(columns)}",
            )

    def collect(rows_subset: list[dict[str, str]]) -> dict[str, Any]:
        rt_values = [v for v in (_as_float(row.get(rt)) for row in rows_subset if rt) if v is not None]
        acc_values = [v for v in (_as_bool(row.get(correct)) for row in rows_subset if correct) if v is not None]
        entry: dict[str, Any] = {"n": len(rows_subset)}
        if rt_values:
            entry["rt"] = _stats(rt_values)
        if acc_values:
            entry["accuracy"] = round(sum(1 for v in acc_values if v) / len(acc_values), 4)
            entry["n_scored"] = len(acc_values)
        return entry

    overall = collect(rows)
    overall["rows"] = len(rows)
    if rt:
        overall["rt_column"] = rt
    if correct:
        overall["correct_column"] = correct

    grouped: list[dict[str, Any]] = []
    if groups:
        buckets: dict[tuple[str, ...], list[dict[str, str]]] = {}
        for row in rows:
            key = tuple(str(row.get(column, "")) for column in groups)
            buckets.setdefault(key, []).append(row)
        for key, subset in sorted(buckets.items()):
            entry = {"group": {column: value for column, value in zip(groups, key)}}
            entry.update(collect(subset))
            grouped.append(entry)

    return {
        "file": str(path),
        "rows": len(rows),
        "columns": columns,
        "overall": overall,
        "groups": grouped,
    }


__all__ = ["summarize", "read_rows"]
