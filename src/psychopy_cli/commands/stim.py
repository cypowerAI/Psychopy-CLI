"""Stimulus generation commands."""

from __future__ import annotations

from typing import Any

from ..console import Result
from ..context import refuse_overwrite
from ..stimuli.render import GENERATORS, grating, noise, shape_image, text_image


def cmd_stim_list(context: Any, args: Any) -> Result:
    return Result(data={
        "generators": [
            {"name": name, "summary": summary, "command": f"psychopy-cli stim {name}"}
            for name, summary in GENERATORS.items()
        ],
        "note": "rendering needs numpy + Pillow (`pip install psychopy-cli[stim]`); no display required",
    })


def _output(context: Any, raw: str) -> Any:
    path = context.resolve(raw)
    if path.suffix.lower() != ".png":
        path = path.with_suffix(".png")
    refuse_overwrite(path, True)
    return path


def cmd_stim_grating(context: Any, args: Any) -> Result:
    path = _output(context, args.output)
    return Result(data=grating(
        path,
        size=int(args.size),
        sf=float(args.sf),
        ori=float(args.ori),
        phase=float(args.phase),
        contrast=float(args.contrast),
        mask=args.mask,
        sigma=float(args.sigma),
        background=float(args.background),
        foreground_is_dark=bool(getattr(args, "foreground_is_dark", False)),
    ))


def cmd_stim_noise(context: Any, args: Any) -> Result:
    path = _output(context, args.output)
    return Result(data=noise(
        path,
        size=int(args.size),
        type=args.type,
        sd=float(args.sd),
        seed=int(args.seed),
        background=float(args.background),
    ))


def cmd_stim_text(context: Any, args: Any) -> Result:
    path = _output(context, args.output)
    text = args.text.replace("\\n", "\n")
    return Result(data=text_image(
        path,
        text=text,
        height=int(args.height),
        font=args.font,
        color=args.color,
        background=args.background,
        padding=int(args.padding),
    ))


def cmd_stim_shape(context: Any, args: Any) -> Result:
    path = _output(context, args.output)
    return Result(data=shape_image(
        path,
        shape=args.shape,
        size=int(args.size),
        fill=args.fill,
        line=args.line,
        line_width=int(args.line_width),
        rotation=float(args.rotation),
        background=args.background,
    ))


__all__ = ["cmd_stim_list", "cmd_stim_grating", "cmd_stim_noise", "cmd_stim_text", "cmd_stim_shape"]
