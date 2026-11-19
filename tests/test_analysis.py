"""`data summarize`: the three numbers an agent actually needs."""

from __future__ import annotations

from pathlib import Path

import pytest

from psychopy_cli.analysis.summary import summarize
from psychopy_cli.errors import CliError

CSV = """trial_index,condition,resp.rt,resp.corr
0,congruent,0.50,True
1,congruent,0.60,True
2,incongruent,0.80,False
3,incongruent,0.90,True
"""


@pytest.fixture
def data_file(tmp_path: Path) -> Path:
    path = tmp_path / "data.csv"
    path.write_text(CSV, encoding="utf-8")
    return path


def test_overall_statistics(data_file: Path) -> None:
    result = summarize(data_file)
    assert result["rows"] == 4
    assert result["overall"]["n"] == 4
    assert result["overall"]["rt"]["mean"] == 0.7
    assert result["overall"]["accuracy"] == 0.75
    assert result["overall"]["rt_column"] == "resp.rt"


def test_group_by_condition(data_file: Path) -> None:
    result = summarize(data_file, group_by=["condition"])
    groups = {entry["group"]["condition"]: entry for entry in result["groups"]}
    assert set(groups) == {"congruent", "incongruent"}
    assert groups["incongruent"]["rt"]["mean"] == 0.85
    assert groups["incongruent"]["accuracy"] == 0.5


def test_unknown_group_column_is_an_error(data_file: Path) -> None:
    with pytest.raises(CliError) as excinfo:
        summarize(data_file, group_by=["nope"])
    assert excinfo.value.code == "SPEC_INVALID"


def test_missing_file_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(CliError) as excinfo:
        summarize(tmp_path / "ghost.csv")
    assert excinfo.value.code == "NOT_FOUND"


def test_non_csv_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "data.tsv"
    path.write_text(CSV.replace(",", "\t"), encoding="utf-8")
    with pytest.raises(CliError) as excinfo:
        summarize(path)
    assert excinfo.value.code == "SPEC_INVALID"


def test_empty_data_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    path.write_text("trial_index,resp.rt\n", encoding="utf-8")
    result = summarize(path)
    assert result["rows"] == 0
