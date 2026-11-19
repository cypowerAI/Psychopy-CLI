"""The CLI contract itself: one JSON envelope, stable exit codes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"


def run_cli(*args: str, cwd: Path | None = None) -> tuple[int, dict]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC) + os.sep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [sys.executable, "-m", "psychopy_cli", *args, "--format", "json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(cwd) if cwd else None,
        env=env,
        timeout=600,
    )
    payload = json.loads(completed.stdout)
    return completed.returncode, payload


def test_catalog_lists_every_command() -> None:
    code, payload = run_cli("catalog")
    assert code == 0
    assert payload["ok"]
    commands = payload["data"]["commands"]
    assert len(commands) >= 13
    for command in commands:
        assert command["id"] and command["usage"] and command["summary"]
    assert {"catalog", "doctor", "build", "inspect", "run"} <= {c["id"] for c in commands}


def test_catalog_for_one_command_exposes_its_arguments() -> None:
    code, payload = run_cli("catalog", "build")
    assert code == 0
    schema = payload["data"]["command"]
    names = {argument["name"] for argument in schema["arguments"]}
    assert {"path", "output", "script", "force"} <= names


def test_spec_new_then_validate_succeeds(tmp_path: Path) -> None:
    target = tmp_path / "demo.spec.json"
    code, payload = run_cli("spec", "new", "minimal", "-o", str(target))
    assert code == 0 and payload["ok"]
    assert target.exists()

    code, payload = run_cli("spec", "validate", str(target))
    assert code == 0 and payload["ok"]
    assert payload["data"]["valid"] is True


def test_invalid_spec_reports_spec_invalid_and_exit_3(tmp_path: Path) -> None:
    bad = tmp_path / "bad.spec.json"
    bad.write_text(
        json.dumps(
            {
                "spec_version": "1.0",
                "name": "bad",
                "routines": {"trial": {"components": [{"type": "Text", "name": "t"}]}},
                "flow": [{"routine": "trial"}, {"routine": "nope"}],
            }
        ),
        encoding="utf-8",
    )
    code, payload = run_cli("spec", "validate", str(bad))
    assert code == 3
    assert payload["ok"] is False
    assert payload["error"]["code"] == "SPEC_INVALID"
    assert payload["error"]["details"][0]["path"].startswith("$.flow")


def test_missing_file_reports_not_found_and_exit_4(tmp_path: Path) -> None:
    code, payload = run_cli("build", str(tmp_path / "ghost.spec.json"))
    assert code == 4
    assert payload["error"]["code"] == "NOT_FOUND"


def test_usage_error_is_exit_2() -> None:
    code, payload = run_cli("spec", "new", "not-a-template", "-o", "x.json")
    assert code == 2
    assert payload["error"]["code"] == "USAGE"


def test_doctor_reports_environment_probe() -> None:
    code, payload = run_cli("doctor")
    assert code == 0
    data = payload["data"]
    assert "python" in data and "psychopy" in data and "stim" in data
    assert data["python"]["supports_psychopy_range"] in (True, False)


def test_stdout_is_a_single_document_even_for_psychopy_commands(tmp_path: Path) -> None:
    if not _has_psychopy():
        pytest.skip("PsychoPy is not installed")
    target = tmp_path / "h.json"
    run_cli("spec", "new", "stroop", "-o", str(target))
    code, payload = run_cli("spec", "validate", str(target))
    assert code == 0
    assert payload["command"]


def _has_psychopy() -> bool:
    try:
        import psychopy  # noqa: F401
    except Exception:
        return False
    return True
