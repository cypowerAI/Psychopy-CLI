# The spec language (1.0)

One JSON document describes an experiment. `psychopy-cli spec schema` is the
authoritative version of this page; this is the readable one.

## Top level

| Key | Required | Meaning |
| --- | --- | --- |
| `spec_version` | yes | `"1.0"` |
| `name` | yes | filename-safe experiment name |
| `title` | no | human title, goes into the `.psyexp` |
| `info` | no | experiment-info fields, default `{"participant": "auto", "session": "001"}` |
| `window` | no | `size`, `fullscreen`, `units`, `color`, `monitor`, `backend` |
| `routines` | yes | map of routine name → `{components: [...]}` |
| `flow` | yes | list of `{"routine": name}` and `{"loop": {...}}` |
| `data` | no | `filename`, `formats`, `delimiter` |

## Components

```json
{
  "type": "Text",
  "name": "word",
  "start": 0,
  "end": {"condition": "resp.rt"},
  "params": {"text": "$word", "color": "$ink_colour", "letterHeight": 0.1},
  "disabled": false
}
```

- `type` accepts either Builder class names (`Text`) or full names
  (`TextComponent`); case, spaces and underscores are ignored.
- `params` keys go through the same forgiving match against the real Builder
  parameters, with typo suggestions. `letterHeight`, `letter_height` and
  `Letter Height` are the same key.
- `code` is only valid on `type: "Code"`, with blocks `before_experiment`,
  `begin_experiment`, `begin_routine`, `each_frame`, `end_routine`,
  `end_experiment`.
- Do not set `startType`/`startVal`/`stopType`/`stopVal` in `params`; timing is
  expressed with `start`/`end` and the tool writes those for you.

## Timing

`start` and `end` accept three forms:

| Form | Example | Meaning |
| --- | --- | --- |
| number | `0`, `1.5` | `start`: absolute seconds into the routine. `end`: **duration** in seconds |
| condition | `"resp.rt"` | a Python expression over trial columns and component states |
| object | `{"duration": 1.0}`, `{"frame": 9}`, `{"duration_frames": 12}`, `{"time": 2.0}`, `{"condition": "resp.corr"}` | explicit unit |

Defaults when `end` is omitted: 1.0 s for visual components; open-ended for
`Keyboard`, `Mouse` and `Button` (they end with the routine or on response).

A condition expression sees:

- every condition column of the current trial, e.g. `word`, `corr_key`;
- each component in the routine, by name, with `.status`, `.rt`, `.keys`,
  `.corr`;
- the constants `NOT_STARTED`, `STARTED`, `FINISHED`, e.g.
  `fixation.status == FINISHED`;
- `t` (routine time) and `frame` (frame index).

## Loops and flow

```json
{"loop": {
  "name": "trials",
  "routines": ["trial", "feedback"],
  "n_reps": 2,
  "order": "random",
  "seed": 7,
  "conditions": [{"word": "RED", "ink_colour": [1, 0, 0], "corr_key": "r"}]
}}
```

- `order`: `sequential` (default), `random`, `random_per_rep`.
- `seed`: makes the order reproducible; without it the CLI seed (default 0) is
  used, so runs are reproducible by default.
- `conditions_file`: path to a CSV, relative to the spec. Mutually exclusive
  with `conditions`.
- `selected_rows`: Builder-style row selector, e.g. `"0:3"`.
- Nested loops are rejected in 1.0; flatten with `n_reps`.

A loop repeats *all* its routines `n_reps × len(conditions)` times, one
condition row per iteration — the same thing Builder does with a loop that
wraps several routines.

## Condition values

Each column is a CSV cell, so values are scalars or flat lists:

- strings pass through (`"RED"`), numbers stay numbers (`0.5`),
- booleans become `True`/`False`,
- a flat list is stored as its repr and evaluated at run time: `[1, 0, 0]`
  becomes a colour, `["a", "b"]` becomes a list.

Objects and nested lists are rejected, because they do not survive a CSV.

## Data settings

| Key | Default | Meaning |
| --- | --- | --- |
| `filename` | `data/{participant}/{name}_{date}` | Builder-style filename template |
| `formats` | `["wide_csv"]` | any of `wide_csv`, `csv`, `excel`, `psydat`, `hdf5` |
| `delimiter` | `,` | field separator |

`run` writes its own `data.csv` inside the run directory; this block controls
what the `.psyexp` asks Builder to save.

## Validation codes

`spec validate` reports one entry per problem, with `path`, `code` and often a
`hint`. The codes are stable:

| Code | Meaning |
| --- | --- |
| `SPEC_VERSION_UNSUPPORTED` | not `1.0` |
| `NAME_MISSING`, `NAME_UNSAFE` | experiment name |
| `ROUTINES_*`, `ROUTINE_*` | routine shape |
| `COMPONENT_UNKNOWN`, `COMPONENT_NAME`, `COMPONENT_PARAMS` | component shape |
| `TIMING_*` | timing form, unit or value |
| `FLOW_*` | flow entries and references |
| `LOOP_*` | loops, conditions, ordering |
| `CODE_BLOCK_UNKNOWN`, `CODE_BLOCK_UNSUPPORTED` | code component blocks |
| `PARAM_UNKNOWN` | parameter not in the installed Builder |
| `DATA_*` | data settings |

`PARAM_UNKNOWN` only appears when PsychoPy is installed; without it the
structural checks still run.
