"""The spec language: parsing, validation, and the messages an agent sees."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from psychopy_cli.spec import load_and_check, summarize_diagnostics
from psychopy_cli.spec.model import Diagnostics, enumerate_trials, parse_spec, spec_stats
from psychopy_cli.spec.schema import spec_json_schema
from psychopy_cli.spec.templates import TEMPLATES, template_document


def test_every_template_is_valid(any_spec: Path) -> None:
    spec, diags = load_and_check(any_spec)
    valid, errors, _ = summarize_diagnostics(diags)
    assert valid, errors
    assert spec.name


def test_templates_are_named_and_distinct() -> None:
    assert set(TEMPLATES) == {"minimal", "stroop", "flanker"}
    names = {template_document(name)["name"] for name in TEMPLATES}
    assert len(names) == len(TEMPLATES)


def test_schema_describes_the_timing_forms() -> None:
    schema = spec_json_schema()
    text = json.dumps(schema)
    for marker in ("start", "end", "routines", "flow", "spec_version"):
        assert marker in text


def test_unknown_routine_in_flow_is_reported_with_a_path() -> None:
    document = template_document("minimal")
    document["flow"].append({"routine": "does_not_exist"})
    diags = Diagnostics()
    parse_spec(document, path=None, diags=diags)
    assert [d.code for d in diags.errors] == ["FLOW_ROUTINE_MISSING"]
    assert diags.errors[0].path == f"$.flow[{len(document['flow']) - 1}].routine"


def test_end_as_bare_number_means_duration() -> None:
    document = template_document("minimal")
    component = document["routines"]["trial"]["components"][0]
    component["end"] = 2.5
    spec = parse_spec(document, path=None, diags=Diagnostics())
    timing = spec.routines["trial"].components[0].end
    assert timing.kind == "duration"
    assert timing.value == 2.5


def test_keyboard_default_end_is_open_ended() -> None:
    document = template_document("minimal")
    keyboard = next(c for c in document["routines"]["trial"]["components"] if c["type"] == "Keyboard")
    assert "end" not in keyboard
    spec = parse_spec(document, path=None, diags=Diagnostics())
    resolved = next(c for c in spec.routines["trial"].components if c.type == "KeyboardComponent")
    assert resolved.end is None


def test_bad_timing_shape_is_a_typed_error() -> None:
    document = template_document("minimal")
    document["routines"]["trial"]["components"][0]["end"] = {"minutes": 1.0}
    diags = Diagnostics()
    parse_spec(document, path=None, diags=diags)
    assert [d.code for d in diags.errors] == ["TIMING_KIND"]


def test_two_timing_keys_are_rejected() -> None:
    document = template_document("minimal")
    document["routines"]["trial"]["components"][0]["end"] = {"duration": 1.0, "frame": 5}
    diags = Diagnostics()
    parse_spec(document, path=None, diags=diags)
    assert [d.code for d in diags.errors] == ["TIMING_SHAPE"]


def test_loop_without_conditions_is_an_error() -> None:
    document = template_document("minimal")
    loop = document["flow"][1]["loop"]
    loop.pop("conditions")
    diags = Diagnostics()
    parse_spec(document, path=None, diags=diags)
    assert any(d.code == "LOOP_EMPTY_CONDITIONS" for d in diags.errors)


def test_flat_colour_lists_are_allowed_in_conditions() -> None:
    document = template_document("stroop")
    spec = parse_spec(document, path=None, diags=Diagnostics())
    assert spec.loops[0].conditions[0]["ink_color"] == [1, 0, 0]


def test_stats_count_trials_across_loops(stroop_spec: Path) -> None:
    spec, _ = load_and_check(stroop_spec)
    stats = spec_stats(spec)
    assert stats["loops"] == 1
    assert stats["components"] == 8  # 7 visual/keyboard components + the feedback code
    assert stats["trials"] == len(enumerate_trials(spec, seed=0))


def test_seeded_enumeration_is_reproducible(tmp_path: Path) -> None:
    document = template_document("stroop")
    document["flow"][1]["loop"].pop("seed")
    path = tmp_path / "unseeded.spec.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    spec, _ = load_and_check(path)

    first = enumerate_trials(spec, seed=42)
    second = enumerate_trials(spec, seed=42)
    assert [row.get("word") for row in first] == [row.get("word") for row in second]
    other = enumerate_trials(spec, seed=7)
    assert [row.get("word") for row in first] != [row.get("word") for row in other]


def test_loop_seed_beats_the_cli_seed(stroop_spec: Path) -> None:
    spec, _ = load_and_check(stroop_spec)
    assert spec.loops[0].seed == 7
    assert enumerate_trials(spec, seed=1) == enumerate_trials(spec, seed=2)


def test_max_trials_truncates(stroop_spec: Path) -> None:
    spec, _ = load_and_check(stroop_spec)
    assert len(enumerate_trials(spec, max_trials=3)) == 3


def test_strict_mode_promotes_warnings(stroop_spec: Path) -> None:
    document = json.loads(stroop_spec.read_text(encoding="utf-8"))
    document["routines"]["trial"]["components"][0]["start"] = 0.0
    stroop_spec.write_text(json.dumps(document), encoding="utf-8")
    _, diags = load_and_check(stroop_spec)
    plain_valid, _, warnings = summarize_diagnostics(diags)
    strict_valid, _, _ = summarize_diagnostics(diags, strict=True)
    assert plain_valid
    assert warnings == [] or strict_valid is False


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_templates_round_trip_through_json(name: str) -> None:
    document = template_document(name)
    assert json.loads(json.dumps(document)) == document
