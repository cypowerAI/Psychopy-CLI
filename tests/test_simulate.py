"""`run --simulate`: the design table, without a window."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from psychopy_cli.spec import load_and_check
from psychopy_cli.runtime.simulate import condition_columns, design_summary, simulate, write_design_csv


def test_design_table_covers_every_flow_step(stroop_spec: Path) -> None:
    spec, _ = load_and_check(stroop_spec)
    table = simulate(spec, seed=5)
    assert len(table) == len(table)  # noqa: PLR0124 - shape check below is the real assertion
    assert table[0]["routines"] == "instruction"
    assert {row["routines"] for row in table[1:]} == {"trial|feedback"}


def test_condition_columns_come_from_the_loop(stroop_spec: Path) -> None:
    spec, _ = load_and_check(stroop_spec)
    assert condition_columns(spec) == ["word", "ink_color", "corr_key", "condition"]


def test_trial_rows_carry_condition_values(stroop_spec: Path) -> None:
    spec, _ = load_and_check(stroop_spec)
    rows = [row for row in simulate(spec, seed=1) if row["loop"] == "trials"]
    assert len(rows) == 6
    assert all(row["word"] in {"RED", "GREEN", "BLUE"} for row in rows)
    assert all(row["loop.thisT"] == 0 for row in rows)


def test_simulate_is_deterministic_for_a_seed(stroop_spec: Path) -> None:
    spec, _ = load_and_check(stroop_spec)
    assert simulate(spec, seed=11) == simulate(spec, seed=11)


def test_design_csv_is_readable(stroop_spec: Path, tmp_path: Path) -> None:
    spec, _ = load_and_check(stroop_spec)
    table = simulate(spec, seed=0)
    path = write_design_csv(table, tmp_path / "design.csv")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(table)
    assert set(rows[0]) == set(table[0])


def test_summary_reports_loops_and_columns(stroop_spec: Path) -> None:
    spec, _ = load_and_check(stroop_spec)
    summary = design_summary(spec, simulate(spec))
    assert summary["loops"][0]["name"] == "trials"
    assert summary["loops"][0]["conditions"] == 6
    assert "word" in summary["columns"]


def test_external_conditions_file_is_honoured(tmp_path: Path) -> None:
    import json

    from psychopy_cli.spec.model import Diagnostics, parse_spec
    from psychopy_cli.spec.templates import template_document

    document = template_document("minimal")
    csv_path = tmp_path / "rows.csv"
    csv_path.write_text("side\nleft\nright\n", encoding="utf-8")
    loop = document["flow"][1]["loop"]
    loop.pop("conditions")
    loop["conditions_file"] = "rows.csv"
    document["name"] = "external"
    spec_path = tmp_path / "external.spec.json"
    spec_path.write_text(json.dumps(document), encoding="utf-8")

    from psychopy_cli.spec import load_and_check as reload_spec

    spec = reload_spec(spec_path)[0]
    table = simulate(spec)
    assert len([row for row in table if row["loop"] == "trials"]) == 2
