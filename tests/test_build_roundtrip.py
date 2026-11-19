"""`build` must produce files PsychoPy itself can read back."""

from __future__ import annotations

from pathlib import Path

import pytest

from psychopy_cli.spec import load_and_check

pytestmark = pytest.mark.psychopy

psychopy = pytest.importorskip("psychopy", reason="PsychoPy is not installed")


def _build(spec_path: Path, out_dir: Path, **kwargs) -> dict:
    from psychopy_cli.builder.compile import compile_spec

    spec, diags = load_and_check(spec_path)
    assert not diags.errors, [d.to_dict() for d in diags.errors]
    return compile_spec(spec, out_dir, **kwargs)


def test_build_writes_expected_artifacts(any_spec: Path, tmp_path: Path) -> None:
    result = _build(any_spec, tmp_path / "build")
    psyexp = Path(result["psyexp"])
    assert psyexp.exists() and psyexp.suffix == ".psyexp"
    manifest = Path(result["manifest"])
    assert manifest.exists()
    for conditions in result["conditions"]:
        assert Path(conditions).exists()


def test_psychopy_can_read_the_built_file_back(any_spec: Path, tmp_path: Path) -> None:
    from psychopy.experiment import Experiment

    result = _build(any_spec, tmp_path / "build")
    reloaded = Experiment()
    reloaded.loadFromXML(str(result["psyexp"]))
    assert reloaded.settings.params["expName"].val
    assert len(reloaded.routines) >= 1
    assert len(reloaded.flow) >= 1


def test_component_count_survives_round_trip(stroop_spec: Path, tmp_path: Path) -> None:
    from psychopy.experiment import Experiment

    spec, _ = load_and_check(stroop_spec)
    result = _build(stroop_spec, tmp_path / "build")
    reloaded = Experiment()
    reloaded.loadFromXML(str(result["psyexp"]))
    built = sum(len(routine) for routine in reloaded.routines.values()) - len(reloaded.routines)
    planned = sum(len(routine.components) for routine in spec.routines.values())
    assert built == planned


def test_loop_conditions_file_is_referenced(stroop_spec: Path, tmp_path: Path) -> None:
    from psychopy.experiment import Experiment
    from psychopy.experiment.flow import LoopInitiator

    result = _build(stroop_spec, tmp_path / "build")
    reloaded = Experiment()
    reloaded.loadFromXML(str(result["psyexp"]))
    initiators = [entry for entry in reloaded.flow if isinstance(entry, LoopInitiator)]
    assert initiators, "the rebuilt flow lost its loop"
    loop = initiators[0].loop
    assert loop.params["conditionsFile"].val.endswith(".csv")


def test_script_is_written_on_request(stroop_spec: Path, tmp_path: Path) -> None:
    result = _build(stroop_spec, tmp_path / "build", write_script=True)
    script = Path(result["script"])
    assert script.exists()
    source = script.read_text(encoding="utf-8")
    assert "from psychopy import" in source
    assert "win = visual.Window" in source


def test_inspect_reconstructs_a_usable_spec(stroop_spec: Path, tmp_path: Path) -> None:
    from psychopy_cli.builder.inspect import inspect_psyexp
    from psychopy_cli.spec.model import Diagnostics, parse_spec

    result = _build(stroop_spec, tmp_path / "build")
    document = inspect_psyexp(Path(result["psyexp"]))
    spec = parse_spec(document, path=None, diags=Diagnostics())
    assert spec.name
    assert set(spec.routines) == set(load_and_check(stroop_spec)[0].routines)


def test_unknown_component_type_is_rejected_before_building() -> None:
    from psychopy_cli.spec.model import Diagnostics, parse_spec
    from psychopy_cli.spec.templates import template_document

    document = template_document("minimal")
    document["routines"]["trial"]["components"][0]["type"] = "Spline"
    diags = Diagnostics()
    parse_spec(document, path=None, diags=diags)
    assert [d.code for d in diags.errors] == ["COMPONENT_UNKNOWN"]
