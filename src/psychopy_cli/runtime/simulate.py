"""Design rehearsal: turn a spec into the table of trials it will run.

This is the check that needs no window, no display and no keypress. If the
design is wrong -- a missing condition column, a loop that repeats nothing, a
routine referencing an undefined variable -- it shows up here instead of
halfway through a session with a participant.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from ..context import ensure_dir
from ..spec.model import Spec, enumerate_trials, spec_stats

META_COLUMNS = ("routines", "loop", "loop.thisN", "loop.thisT")


def condition_columns(spec: Spec) -> list[str]:
    columns: list[str] = []
    for loop in spec.loops:
        for column in loop.condition_columns():
            if column not in columns:
                columns.append(column)
    if not columns:
        # conditions may live in external files
        for loop in spec.loops:
            if loop.conditions_file:
                path = spec.dir / loop.conditions_file
                if path.exists():
                    with path.open("r", encoding="utf-8-sig", newline="") as handle:
                        for column in next(csv.reader(handle), []):
                            if column not in columns:
                                columns.append(column)
    return columns


def simulate(spec: Spec, *, seed: int | None = None, max_trials: int = 0) -> list[dict[str, Any]]:
    trials = enumerate_trials(spec, seed=seed, max_trials=max_trials)
    columns = condition_columns(spec)
    table: list[dict[str, Any]] = []
    for index, trial in enumerate(trials):
        row: dict[str, Any] = {
            "trial_index": index,
            "routines": "|".join(trial["__routines"]),
            "loop": trial["__loop"] or "",
            "loop.thisN": trial["__loop_thisN"],
            "loop.thisT": trial["__loop_thisT"],
        }
        for column in columns:
            row[column] = trial.get(column, "")
        table.append(row)
    return table


def write_design_csv(table: list[dict[str, Any]], path: Path) -> Path:
    ensure_dir(path.parent)
    columns = list(table[0].keys()) if table else ["trial_index"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in table:
            writer.writerows([row])
    return path


def design_summary(spec: Spec, table: list[dict[str, Any]]) -> dict[str, Any]:
    stats = spec_stats(spec)
    per_loop: list[dict[str, Any]] = []
    for loop in spec.loops:
        runs = [row for row in table if row["loop"] == loop.name]
        per_loop.append({
            "name": loop.name,
            "routines": loop.routines,
            "n_reps": loop.n_reps,
            "conditions": len(loop.conditions) or None,
            "trials": len(runs),
            "order": loop.order,
            "seed": loop.seed,
        })
    return {
        "routine_screens": stats["routines"],
        "components": stats["components"],
        "trials": len(table),
        "loops": per_loop,
        "columns": list(table[0].keys()) if table else [],
    }


__all__ = ["simulate", "write_design_csv", "design_summary", "condition_columns", "META_COLUMNS"]
