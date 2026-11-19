"""Vector stimulus synthesis without a display.

PsychoPy's own stimuli need an OpenGL window. For materials, for checking a
stimulus numerically, and for working on a headless machine, these generators
do the mathematics directly with numpy and write PNGs.

The numbers are reported back, not just drawn: a caller that asked for
contrast 0.5 gets told what contrast the saved image actually has.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import ensure_dir
from ..environment import require_stim_dependencies


def _grid(size: int, numpy: Any) -> tuple[Any, Any, Any]:
    if size < 8:
        from ..errors import usage

        raise usage("`size` must be at least 8 pixels")
    coords = (numpy.arange(size) - (size - 1) / 2.0) / size
    x, y = numpy.meshgrid(coords, coords)
    radius = numpy.sqrt(x ** 2 + y ** 2)
    return x, y, radius


def _save(array: Any, path: Path, image_module: Any, *, transparent_mask: Any = None) -> Path:
    import numpy as np

    ensure_dir(path.parent)
    values = np.clip(array, 0.0, 1.0)
    pixels = (values * 255).round().astype("uint8")
    if transparent_mask is None:
        image = image_module.fromarray(pixels)  # uint8 HxW -> mode "L"
    else:
        alpha = (np.clip(transparent_mask, 0.0, 1.0) * 255).round().astype("uint8")
        rgba = np.stack([pixels, pixels, pixels, alpha], axis=-1)
        image = image_module.fromarray(rgba)  # uint8 HxWx4 -> mode "RGBA"
    image.save(path, format="PNG")
    return path


def grating(
    output: Path,
    *,
    size: int = 512,
    sf: float = 0.05,
    ori: float = 0.0,
    phase: float = 0.0,
    contrast: float = 1.0,
    mask: str = "gaussian",
    sigma: float = 0.3,
    background: float = 0.5,
    foreground_is_dark: bool = False,
) -> dict[str, Any]:
    """Render a sinusoidal grating with an optional window."""
    import numpy as np

    numpy, image_module = require_stim_dependencies()
    x, y, radius = _grid(size, numpy)

    theta = np.deg2rad(ori)
    # Project onto the grating axis: orientation 0 gives vertical bars.
    projection = x * np.cos(theta) + y * np.sin(theta)
    carrier = np.cos(2 * np.pi * sf * projection + 2 * np.pi * phase)

    if mask == "circle":
        envelope = (radius <= 0.5).astype(float)
    elif mask == "gaussian":
        envelope = np.exp(-(radius ** 2) / (2 * (sigma ** 2)))
    else:
        envelope = np.ones_like(radius)

    amplitude = contrast / 2.0
    image = background + (-amplitude if foreground_is_dark else amplitude) * carrier * envelope
    image = np.clip(image, 0.0, 1.0)

    path = _save(image, output, image_module)

    in_window = envelope > 0.05
    if in_window.any():
        peak = float(np.max(image[in_window]))
        trough = float(np.min(image[in_window]))
        measured = (peak - trough) / (peak + trough) if (peak + trough) else 0.0
    else:
        peak = trough = measured = 0.0

    return {
        "path": str(path),
        "size": [size, size],
        "sf": sf,
        "ori": ori,
        "phase": phase,
        "contrast_requested": contrast,
        "contrast_measured": round(measured, 4),
        "mask": mask,
        "clip_fraction": round(float(np.mean((image <= 0.0) | (image >= 1.0))), 4),
    }


def noise(
    output: Path,
    *,
    size: int = 512,
    type: str = "gaussian",
    sd: float = 0.1,
    seed: int = 0,
    background: float = 0.5,
) -> dict[str, Any]:
    """Render a noise field."""
    import numpy as np

    numpy, image_module = require_stim_dependencies()
    rng = np.random.default_rng(seed)
    if type == "uniform":
        field = rng.uniform(-sd, sd, size=(size, size))
    elif type == "binary":
        field = rng.choice([-sd, sd], size=(size, size))
    else:
        field = rng.normal(0.0, sd, size=(size, size))
    image = np.clip(background + field, 0.0, 1.0)
    path = _save(image, output, image_module)
    return {
        "path": str(path),
        "size": [size, size],
        "type": type,
        "sd": sd,
        "seed": seed,
        "mean": round(float(image.mean()), 4),
        "std": round(float(image.std()), 4),
    }


def _parse_color(value: str, image_module: Any) -> tuple[int, int, int, int] | None:
    from PIL import ImageColor

    if value is None or str(value).lower() in ("none", "transparent"):
        return None
    try:
        rgb = ImageColor.getrgb(value)
    except ValueError as exc:
        from ..errors import usage

        raise usage(
            f"unrecognised colour {value!r}",
            hint="use a name ('white'), '#rrggbb', or 'transparent'",
        ) from exc
    return (rgb[0], rgb[1], rgb[2], 255)


def text_image(
    output: Path,
    *,
    text: str,
    height: int = 64,
    font: str = "Arial",
    color: str = "white",
    background: str = "transparent",
    padding: int = 16,
) -> dict[str, Any]:
    """Render text into a PNG."""
    numpy, image_module = require_stim_dependencies()
    from PIL import ImageDraw, ImageFont

    try:
        pil_font = ImageFont.truetype(font, height)
    except OSError:
        try:
            pil_font = ImageFont.load_default(size=height)
        except TypeError:  # very old Pillow
            pil_font = ImageFont.load_default()

    lines = text.split("\n")
    scratch = ImageDraw.Draw(image_module.new("RGBA", (1, 1)))
    widths, heights = [], []
    for line in lines:
        box = scratch.textbbox((0, 0), line or " ", font=pil_font)
        widths.append(box[2] - box[0])
        heights.append(box[3] - box[1])
    canvas = (
        max(1, max(widths) + padding * 2),
        sum(heights) + padding * 2 + (len(lines) - 1) * padding // 2,
    )

    background_color = _parse_color(background, image_module)
    image = image_module.new("RGBA", canvas, (0, 0, 0, 0) if background_color is None else background_color)
    drawer = ImageDraw.Draw(image)
    fill = _parse_color(color, image_module) or (255, 255, 255, 255)

    y = padding
    for line, height_px in zip(lines, heights):
        drawer.text((padding, y), line, font=pil_font, fill=fill)
        y += height_px + padding // 2

    ensure_dir(output.parent)
    image.save(output, format="PNG")
    return {"path": str(output), "text": text, "width": canvas[0], "height": canvas[1], "lines": len(lines)}


def shape_image(
    output: Path,
    *,
    shape: str = "circle",
    size: int = 256,
    fill: str = "white",
    line: str = "none",
    line_width: int = 0,
    rotation: float = 0.0,
    background: str = "transparent",
) -> dict[str, Any]:
    """Render a geometric shape."""
    import math

    numpy, image_module = require_stim_dependencies()
    from PIL import ImageDraw

    background_color = _parse_color(background, image_module)
    image = image_module.new("RGBA", (size, size), (0, 0, 0, 0) if background_color is None else background_color)
    drawer = ImageDraw.Draw(image)
    fill_color = _parse_color(fill, image_module)
    outline_color = _parse_color(line, image_module)

    inset = max(2, int(size * 0.06))
    box = (inset, inset, size - inset, size - inset)

    if shape == "circle":
        drawer.ellipse(box, fill=fill_color, outline=outline_color, width=line_width)
    elif shape == "rectangle":
        drawer.rectangle(box, fill=fill_color, outline=outline_color, width=line_width)
    elif shape == "triangle":
        points = _rotate([(size / 2, inset), (size - inset, size - inset), (inset, size - inset)], rotation, size)
        drawer.polygon(points, fill=fill_color, outline=outline_color, width=line_width)
    elif shape == "cross":
        arm = size * 0.12
        centre = size / 2
        quads = [
            (centre - arm, inset, centre + arm, size - inset),
            (inset, centre - arm, size - inset, centre + arm),
        ]
        for quad in quads:
            drawer.rectangle(quad, fill=fill_color)
    elif shape == "star":
        points = _star_points(size, inset, 5, rotation)
        drawer.polygon(points, fill=fill_color, outline=outline_color, width=line_width)
    else:
        from ..errors import usage

        raise usage(f"unknown shape {shape!r}", hint="circle, rectangle, triangle, cross or star")

    ensure_dir(output.parent)
    image.save(output, format="PNG")
    return {"path": str(output), "shape": shape, "size": [size, size], "rotation": rotation}


def _rotate(points: list[tuple[float, float]], degrees: float, size: int) -> list[tuple[float, float]]:
    if not degrees:
        return points
    import math

    centre = size / 2.0
    theta = math.radians(degrees)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    rotated = []
    for x, y in points:
        dx, dy = x - centre, y - centre
        rotated.append((centre + dx * cos_t - dy * sin_t, centre + dx * sin_t + dy * cos_t))
    return rotated


def _star_points(size: int, inset: int, points: int, rotation: float) -> list[tuple[float, float]]:
    import math

    centre = size / 2.0
    outer = (size - 2 * inset) / 2.0
    inner = outer * 0.45
    result = []
    for index in range(points * 2):
        radius = outer if index % 2 == 0 else inner
        angle = math.radians(rotation) + math.pi * index / points - math.pi / 2
        result.append((centre + radius * math.cos(angle), centre + radius * math.sin(angle)))
    return result


GENERATORS = {
    "grating": "Sinusoidal grating / Gabor patch with a Gaussian or circular window.",
    "noise": "Gaussian or uniform noise field with a fixed seed.",
    "text": "Text rendered to a PNG, independent of presentation-machine fonts.",
    "shape": "Circle, rectangle, triangle, cross or star, rotatable.",
}


__all__ = ["grating", "noise", "text_image", "shape_image", "GENERATORS"]
