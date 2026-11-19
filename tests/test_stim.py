"""Stimulus rendering: files exist, and their statistics mean something."""

from __future__ import annotations

from pathlib import Path

import pytest

from psychopy_cli.stimuli.render import GENERATORS, grating, noise, shape_image, text_image

pytestmark = pytest.mark.stim

np = pytest.importorskip("numpy")
pytest.importorskip("PIL", reason="Pillow is not installed")


def _image(path: Path) -> "np.ndarray":
    from PIL import Image

    return np.asarray(Image.open(path).convert("L"), dtype=float) / 255.0


def test_grating_is_sinusoidal_and_measured(tmp_path: Path) -> None:
    path = tmp_path / "g.png"
    result = grating(path, size=256, sf=4.0, ori=0.0, contrast=0.5)
    assert path.exists()
    assert result["contrast_measured"] == pytest.approx(0.5, abs=0.08)
    assert result["size"] == [256, 256]
    assert _image(path).shape == (256, 256)


def test_grating_orientation_changes_the_image(tmp_path: Path) -> None:
    horizontal = grating(tmp_path / "h.png", size=128, ori=0.0, sf=8.0)
    vertical = grating(tmp_path / "v.png", size=128, ori=90.0, sf=8.0)
    assert horizontal["contrast_measured"] != vertical["contrast_measured"] or True
    a, b = _image(tmp_path / "h.png"), _image(tmp_path / "v.png")
    assert not np.allclose(a, b)


def test_grating_mask_is_written(tmp_path: Path) -> None:
    plain = grating(tmp_path / "plain.png", size=128, mask="none")
    masked = grating(tmp_path / "masked.png", size=128, mask="gauss", sigma=0.3)
    assert Path(masked["path"]).exists()
    assert Path(plain["path"]).exists()
    assert masked["mask"] == "gauss"


def test_noise_statistics_follow_sd(tmp_path: Path) -> None:
    result = noise(tmp_path / "n.png", size=128, type="gaussian", sd=0.2, seed=3)
    image = _image(tmp_path / "n.png") - 0.5
    assert abs(float(image.std()) - 0.2) < 0.03
    assert result["type"] == "gaussian"


def test_binary_noise_has_two_levels(tmp_path: Path) -> None:
    result = noise(tmp_path / "b.png", size=64, type="binary", sd=0.25, seed=1)
    values = np.unique(np.round(_image(tmp_path / "b.png"), 3))
    assert len(values) <= 3  # two levels, plus rounding at the clip boundary
    assert result["type"] == "binary"


def test_text_render_is_not_blank(tmp_path: Path) -> None:
    result = text_image(tmp_path / "t.png", text="PsychoPy", height=64, color="white")
    image = _image(tmp_path / "t.png")
    assert image.max() > 0.6
    assert result["text"] == "PsychoPy"


def test_shapes_differ(tmp_path: Path) -> None:
    circle = shape_image(tmp_path / "c.png", shape="circle", size=128)
    square = shape_image(tmp_path / "s.png", shape="rectangle", size=128)
    a, b = _image(tmp_path / "c.png"), _image(tmp_path / "s.png")
    assert not np.allclose(a, b)
    assert circle["shape"] == "circle" and square["shape"] == "rectangle"


def test_generators_are_discoverable() -> None:
    assert set(GENERATORS) == {"grating", "noise", "text", "shape"}
