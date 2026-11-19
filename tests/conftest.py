"""Shared fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from psychopy_cli.spec.templates import TEMPLATES, template_document


@pytest.fixture
def stroop_spec(tmp_path: Path) -> Path:
    path = tmp_path / "stroop.spec.json"
    path.write_text(json.dumps(template_document("stroop"), indent=2), encoding="utf-8")
    return path


@pytest.fixture(params=sorted(TEMPLATES))
def any_spec(request, tmp_path: Path) -> Path:
    path = tmp_path / f"{request.param}.spec.json"
    path.write_text(json.dumps(template_document(request.param), indent=2), encoding="utf-8")
    return path
