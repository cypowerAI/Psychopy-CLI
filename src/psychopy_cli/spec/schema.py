"""JSON Schema for the spec language.

This document is the contract an agent reads before authoring a spec. It is
written by hand rather than generated, because the descriptions carry the
conventions (what a bare number on ``end`` means, which components need code
blocks) that a mechanical schema cannot express.
"""

from __future__ import annotations

from typing import Any

from .model import (
    CANONICAL_COMPONENTS,
    RUNNABLE_COMPONENTS,
    START_KINDS,
    STOP_KINDS,
    SUPPORTED_SPEC_VERSION,
    WINDOW_BACKENDS,
    WINDOW_UNITS,
)

_COMPONENT_ALIASES = sorted({"Text", "Image", "Grating", "Polygon", "Keyboard",
                             "Mouse", "Sound", "Code", "Slider", "Textbox"})


def _timing_schema(allowed: tuple[str, ...], *, is_start: bool, default_text: str) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    if "time" in allowed:
        properties["time"] = {"type": "number", "description": "seconds from routine start"}
    if "frame" in allowed:
        properties["frame"] = {"type": "integer", "description": "frame number from routine start"}
    if "condition" in allowed:
        properties["condition"] = {
            "type": "string",
            "description": "Python expression evaluated per trial, e.g. \"resp.corr\" or \"t > 2\"",
        }
    if "duration" in allowed:
        properties["duration"] = {"type": "number", "description": "seconds to stay on screen"}
    if "duration_frames" in allowed:
        properties["duration_frames"] = {"type": "integer", "description": "frames to stay on screen"}
    return {
        "oneOf": [
            {
                "type": "number",
                "description": (
                    "shorthand for {" + ("time" if is_start else "duration") + ": <number>}"
                    + (" (seconds from routine start)" if is_start else " (seconds on screen)")
                ),
            },
            {"type": "string", "description": "shorthand for {\"condition\": <expression>}"},
            {
                "type": "object",
                "properties": properties,
                "minProperties": 1,
                "maxProperties": 1,
                "additionalProperties": False,
            },
        ],
        "default": default_text,
    }


def _component_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["type"],
        "properties": {
            "type": {
                "type": "string",
                "description": (
                    "Builder component type. 'Text', 'Keyboard', ... and "
                    "'TextComponent' all resolve to the same class."
                ),
                "examples": _COMPONENT_ALIASES,
            },
            "name": {
                "type": "string",
                "pattern": "^[A-Za-z_][A-Za-z0-9_]*$",
                "description": (
                    "Identifier used in generated code and as the data-column "
                    "prefix. Defaults to a lower-cased type name."
                ),
            },
            "start": _timing_schema(START_KINDS, is_start=True, default_text="0"),
            "end": _timing_schema(STOP_KINDS, is_start=False, default_text="1.0"),
            "disabled": {"type": "boolean", "default": False},
            "params": {
                "type": "object",
                "description": (
                    "Component parameters, keyed by Builder parameter name. "
                    "Lookup is forgiving: 'letterHeight', 'letter_height' and "
                    "'Letter Height' all match. Values are passed through; "
                    "colors accept a name, '#rrggbb', [r, g, b] or a $code "
                    "expression. Call `psychopy-cli components describe <Type>` "
                    "for the authoritative list."
                ),
                "additionalProperties": True,
            },
            "code": {
                "type": "object",
                "description": "Source blocks, only valid when type is 'Code'.",
                "properties": {
                    "before_experiment": {"type": "string"},
                    "begin_experiment": {"type": "string"},
                    "begin_routine": {"type": "string"},
                    "each_frame": {"type": "string"},
                    "end_routine": {"type": "string"},
                    "end_experiment": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }


def spec_json_schema() -> dict[str, Any]:
    """Return the JSON Schema document published by `spec schema`."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/cypowerAI/Psychopy-CLI/spec-1.0.schema.json",
        "title": "psychopy-cli experiment spec",
        "description": (
            "A declarative experiment description. Author it as JSON, validate "
            "with `spec validate`, compile with `build`, rehearse with "
            "`run --simulate`, present with `run`. Everything an agent authors "
            "is a plain object: no Python is required unless a Code component "
            "is used."
        ),
        "type": "object",
        "required": ["spec_version", "name", "routines", "flow"],
        "properties": {
            "spec_version": {
                "type": "string",
                "enum": [SUPPORTED_SPEC_VERSION],
                "description": "Version of this spec dialect.",
            },
            "name": {
                "type": "string",
                "pattern": "^[A-Za-z0-9._-]+$",
                "description": "Short filename-safe experiment name; also the default expName.",
            },
            "title": {"type": "string", "description": "Human-readable title, for documentation."},
            "info": {
                "type": "object",
                "description": (
                    "Experiment-info fields collected at run time, keyed by "
                    "field name. Values are default expressions; the string "
                    "'auto' generates a random participant id."
                ),
                "default": {"participant": "auto", "session": "001"},
                "additionalProperties": True,
            },
            "window": {
                "type": "object",
                "properties": {
                    "size": {
                        "type": "array", "items": {"type": "integer", "minimum": 64},
                        "minItems": 2, "maxItems": 2, "default": [1024, 768],
                        "description": "[width, height] in pixels when not fullscreen.",
                    },
                    "fullscreen": {"type": "boolean", "default": False},
                    "units": {"type": "string", "enum": list(WINDOW_UNITS), "default": "height"},
                    "color": {
                        "type": ["string", "array", "number"],
                        "default": [0, 0, 0],
                        "description": "Background colour.",
                    },
                    "monitor": {"type": "string", "default": "testMonitor"},
                    "backend": {
                        "type": "string", "enum": list(WINDOW_BACKENDS),
                        "description": "Rendering backend; omit to let PsychoPy choose.",
                    },
                },
                "additionalProperties": False,
            },
            "routines": {
                "type": "object",
                "description": "Routine name -> the screen of events it presents.",
                "minProperties": 1,
                "additionalProperties": {
                    "type": "object",
                    "required": ["components"],
                    "properties": {
                        "components": {
                            "type": "array",
                            "items": _component_schema(),
                            "description": "Presented together, ordered.",
                        }
                    },
                    "additionalProperties": False,
                },
            },
            "flow": {
                "type": "array",
                "minItems": 1,
                "description": "Order in which routines run; loops repeat routines.",
                "items": {
                    "oneOf": [
                        {
                            "type": "object",
                            "required": ["routine"],
                            "properties": {"routine": {"type": "string"}},
                            "additionalProperties": False,
                            "description": "Run one routine once.",
                        },
                        {
                            "type": "object",
                            "required": ["loop"],
                            "properties": {
                                "loop": {
                                    "type": "object",
                                    "required": ["name", "routines", "conditions"],
                                    "properties": {
                                        "name": {
                                            "type": "string",
                                            "pattern": "^[A-Za-z_][A-Za-z0-9_]*$",
                                            "description": "Becomes the loop column prefix in data.",
                                        },
                                        "routines": {
                                            "oneOf": [
                                                {"type": "string"},
                                                {"type": "array", "items": {"type": "string"}, "minItems": 1},
                                            ],
                                            "description": "Routine(s) repeated by this loop, in order.",
                                        },
                                        "n_reps": {"type": "integer", "minimum": 1, "default": 1},
                                        "order": {
                                            "type": "string",
                                            "enum": ["sequential", "random", "random_per_rep"],
                                            "default": "random",
                                            "description": "Condition order within each repetition.",
                                        },
                                        "seed": {
                                            "type": "integer",
                                            "description": "Seed for a reproducible random order.",
                                        },
                                        "conditions": {
                                            "type": "array",
                                            "items": {"type": "object"},
                                            "description": (
                                                "Condition rows. Each key becomes a variable "
                                                "readable inside the routine."
                                            ),
                                        },
                                        "conditions_file": {
                                            "type": "string",
                                            "description": "Alternative to inline conditions: a CSV path relative to the spec.",
                                        },
                                        "selected_rows": {
                                            "type": "string",
                                            "default": "",
                                            "description": "Builder row selection expression, e.g. '0:4' or '$congruent'.",
                                        },
                                    },
                                    "additionalProperties": False,
                                }
                            },
                            "additionalProperties": False,
                        },
                    ]
                },
            },
            "data": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "default": "data/{participant}/{name}_{date}",
                        "description": "Output path template. Placeholders: participant, session, name, date, time, rand.",
                    },
                    "formats": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["wide_csv", "csv", "excel", "psydat", "hdf5"]},
                        "default": ["wide_csv"],
                    },
                    "delimiter": {"type": "string", "default": "auto"},
                },
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
        "$comment": (
            "Components that `run` can present: "
            + ", ".join(sorted(RUNNABLE_COMPONENTS))
            + ". Every other component is still compiled into .psyexp by `build`."
        ),
    }


__all__ = ["spec_json_schema", "CANONICAL_COMPONENTS"]
