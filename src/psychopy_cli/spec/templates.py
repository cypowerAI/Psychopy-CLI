"""Starter specs.

Each template is complete and runnable: validate, build, simulate, present.
Templates are the fastest way for a caller to learn the conventions.
"""

from __future__ import annotations

from typing import Any

TEMPLATES: dict[str, dict[str, Any]] = {
    "minimal": {
        "spec_version": "1.0",
        "name": "minimal",
        "title": "One fixation screen, then one response",
        "window": {"size": [1024, 768], "fullscreen": False, "units": "height", "color": [0, 0, 0]},
        "info": {"participant": "auto", "session": "001"},
        "routines": {
            "instruction": {
                "components": [
                    {
                        "type": "Text",
                        "name": "prompt",
                        "start": 0,
                        "end": {"condition": "start_resp.rt"},
                        "params": {
                            "text": "Press SPACE to continue",
                            "pos": [0, 0],
                            "letterHeight": 0.05,
                            "color": "white",
                        },
                    },
                    {
                        "type": "Keyboard",
                        "name": "start_resp",
                        "params": {"allowedKeys": ["space"], "forceEndRoutine": True},
                    },
                ]
            },
            "trial": {
                "components": [
                    {
                        "type": "Text",
                        "name": "stim",
                        "start": 0,
                        "end": {"duration": 1.0},
                        "params": {"text": "Hello", "pos": [0, 0], "letterHeight": 0.08},
                    },
                    {
                        "type": "Keyboard",
                        "name": "resp",
                        "params": {"allowedKeys": ["left", "right"], "store": "first"},
                    },
                ]
            },
            "goodbye": {
                "components": [
                    {"type": "Text", "name": "thanks", "start": 0, "end": {"duration": 2.0},
                     "params": {"text": "Thank you!", "letterHeight": 0.05}}
                ]
            },
        },
        "flow": [
            {"routine": "instruction"},
            {
                "loop": {
                    "name": "trials",
                    "routines": ["trial"],
                    "n_reps": 1,
                    "order": "sequential",
                    "conditions": [{"side": "left"}, {"side": "right"}],
                }
            },
            {"routine": "goodbye"},
        ],
        "data": {"filename": "data/{participant}/{name}_{date}", "formats": ["wide_csv"]},
    },
    "stroop": {
        "spec_version": "1.0",
        "name": "stroop",
        "title": "Colour-word Stroop task",
        "window": {"size": [1024, 768], "fullscreen": False, "units": "height", "color": [0, 0, 0]},
        "info": {"participant": "auto", "session": "001"},
        "routines": {
            "instruction": {
                "components": [
                    {
                        "type": "Text",
                        "name": "prompt",
                        "start": 0,
                        "end": {"condition": "start_resp.rt"},
                        "params": {
                            "text": (
                                "Name the INK COLOUR of the word.\n\n"
                                "r = red    g = green    b = blue    y = yellow\n\n"
                                "Press SPACE to start"
                            ),
                            "letterHeight": 0.045,
                            "wrapWidth": 1.2,
                        },
                    },
                    {"type": "Keyboard", "name": "start_resp",
                     "params": {"allowedKeys": ["space"], "forceEndRoutine": True}},
                ]
            },
            "trial": {
                "components": [
                    {"type": "Text", "name": "fixation", "start": 0, "end": {"duration": 0.5},
                     "params": {"text": "+", "letterHeight": 0.08}},
                    {
                        "type": "Text",
                        "name": "word",
                        "start": {"condition": "fixation.status == FINISHED"},
                        "end": {"condition": "resp.rt"},
                        "params": {
                            "text": "$word",
                            "color": "$ink_color",
                            "letterHeight": 0.1,
                            "pos": [0, 0],
                        },
                    },
                    {"type": "Keyboard", "name": "resp",
                     "params": {
                         "allowedKeys": ["r", "g", "b", "y"],
                         "store": "first",
                         "storeCorrect": True,
                         "correctAns": "$corr_key",
                     }},
                    {
                        "type": "Code",
                        "name": "feedback_code",
                        "code": {
                            "end_routine": "feedback_text = 'Correct!' if resp.corr else 'Incorrect'"
                        },
                    },
                ]
            },
            "feedback": {
                "components": [
                    {"type": "Text", "name": "msg", "start": 0, "end": {"condition": "feedback_resp.rt"},
                     "params": {"text": "$feedback_text", "letterHeight": 0.06, "wrapWidth": 1.2}},
                    {"type": "Keyboard", "name": "feedback_resp",
                     "params": {"allowedKeys": ["space"], "forceEndRoutine": True}},
                ]
            },
        },
        "flow": [
            {"routine": "instruction"},
            {
                "loop": {
                    "name": "trials",
                    "routines": ["trial", "feedback"],
                    "n_reps": 1,
                    "order": "random",
                    "seed": 7,
                    "conditions": [
                        {"word": "RED", "ink_color": [1, 0, 0], "corr_key": "r", "condition": "congruent"},
                        {"word": "GREEN", "ink_color": [0, 1, 0], "corr_key": "g", "condition": "congruent"},
                        {"word": "RED", "ink_color": [0, 1, 0], "corr_key": "g", "condition": "incongruent"},
                        {"word": "GREEN", "ink_color": [1, 0, 0], "corr_key": "r", "condition": "incongruent"},
                        {"word": "BLUE", "ink_color": [0, 0, 1], "corr_key": "b", "condition": "congruent"},
                        {"word": "BLUE", "ink_color": [1, 1, 0], "corr_key": "y", "condition": "incongruent"},
                    ],
                }
            },
        ],
        "data": {"filename": "data/{participant}/{name}_{date}", "formats": ["wide_csv"]},
    },
    "flanker": {
        "spec_version": "1.0",
        "name": "flanker",
        "title": "Eriksen flanker task",
        "window": {"size": [1024, 768], "fullscreen": False, "units": "height", "color": [0, 0, 0]},
        "info": {"participant": "auto", "session": "001"},
        "routines": {
            "instruction": {
                "components": [
                    {"type": "Text", "name": "prompt", "start": 0, "end": {"condition": "start_resp.rt"},
                     "params": {"text": "Indicate the CENTRE letter.\n\nf = left    j = right\n\nPress SPACE to begin",
                                "letterHeight": 0.045, "wrapWidth": 1.2}},
                    {"type": "Keyboard", "name": "start_resp",
                     "params": {"allowedKeys": ["space"], "forceEndRoutine": True}},
                ]
            },
            "trial": {
                "components": [
                    {"type": "Text", "name": "fixation", "start": 0, "end": {"duration": 0.5},
                     "params": {"text": "+", "letterHeight": 0.08}},
                    {"type": "Text", "name": "flankers", "start": {"frame": 9},
                     "end": {"condition": "resp.rt"},
                     "params": {"text": "$flanker_string", "letterHeight": 0.1,
                                "font": "Consolas", "pos": [0, 0]}},
                    {"type": "Keyboard", "name": "resp",
                     "params": {"allowedKeys": ["f", "j"], "store": "first",
                                "storeCorrect": True, "correctAns": "$corr_key"}},
                ]
            },
        },
        "flow": [
            {"routine": "instruction"},
            {
                "loop": {
                    "name": "trials",
                    "routines": ["trial"],
                    "n_reps": 2,
                    "order": "random",
                    "seed": 11,
                    "conditions": [
                        {"flanker_string": "fffff", "corr_key": "f", "congruency": "congruent"},
                        {"flanker_string": "jjjjj", "corr_key": "j", "congruency": "congruent"},
                        {"flanker_string": "ffjff", "corr_key": "j", "congruency": "incongruent"},
                        {"flanker_string": "jjfjj", "corr_key": "f", "congruency": "incongruent"},
                    ],
                }
            },
        ],
        "data": {"filename": "data/{participant}/{name}_{date}", "formats": ["wide_csv"]},
    },
}


def template_document(name: str) -> dict[str, Any]:
    """Return a deep copy so callers cannot mutate the template registry."""
    import copy

    if name not in TEMPLATES:
        from ..errors import usage

        raise usage(
            f"unknown template {name!r}",
            hint=f"available templates: {', '.join(sorted(TEMPLATES))}",
        )
    return copy.deepcopy(TEMPLATES[name])


__all__ = ["TEMPLATES", "template_document"]
