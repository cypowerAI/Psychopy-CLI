# psychopy-cli

A command line interface for [PsychoPy](https://github.com/psychopy/psychopy) built to be driven by a language model.

Every command takes JSON-friendly arguments and returns one JSON envelope on stdout. The tool describes itself (`psychopy-cli catalog`), checks its own environment (`doctor`), and turns a declarative experiment spec into a real `.psyexp` file that opens in PsychoPy Builder.

```console
$ psychopy-cli catalog --format json | head -c 400
{"ok": true, "command": "catalog", "data": {"cli_version": "0.1.0", "commands": [...]}}
```

**中文速览** — 把 PsychoPy 变成一个「大模型能直接调用」的 CLI：用 JSON 写实验、一条命令编译成 `.psyexp`、一条命令彩排设计、一条命令真正呈现并落数据。所有输出都是结构化 JSON，错误带机器可读的代号和修复建议。安装后从 `psychopy-cli catalog` 开始。

---

## Why this exists

PsychoPy is excellent at presenting experiments and awkward for a model to drive: its API is a large Python surface, its Builder format is XML with version-dependent defaults, and its stimuli need an OpenGL window. An agent that guesses produces experiment files that open but misbehave.

This tool fixes the interface rather than the science:

| Problem | What this CLI does |
| --- | --- |
| "What can I even call?" | `catalog` publishes every command with a JSON Schema for its input |
| Guessing parameter names | `components describe Text` prints the real keys, defaults and allowed values |
| Fragile XML templating | builds **through** PsychoPy's own `Experiment`/component classes, so files round-trip with Builder |
| Free-text errors | typed error codes, hints and `next` actions, plus stable exit codes |
| Needing a screen to check the design | `run --simulate` enumerates every trial with no window at all |
| Chatty libraries polluting stdout | stdout carries exactly one document; library chatter is rerouted to stderr |

## Install

```bash
pip install psychopy-cli            # core: catalog, spec, build-plan, data, and no PsychoPy
pip install psychopy-cli[psychopy]  # adds PsychoPy: build, inspect, run
pip install psychopy-cli[stim]      # adds numpy + Pillow: the stim generators
```

PsychoPy currently supports Python `>=3.10,<3.13`. If `doctor` reports the wrong interpreter, build the environment with 3.11 or 3.12.

From source:

```bash
git clone https://github.com/cypowerAI/Psychopy-CLI.git
cd Psychopy-CLI
python -m venv .venv && . .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[psychopy,stim,dev]"
```

## Quickstart

```bash
psychopy-cli doctor                                        # is PsychoPy importable? can a window open?
psychopy-cli spec schema                                   # the grammar, as JSON Schema
psychopy-cli spec new stroop -o stroop.spec.json           # a complete, runnable starting point
psychopy-cli spec validate stroop.spec.json                # static checks, down to parameter typos
psychopy-cli build stroop.spec.json -o build/ --script     # -> .psyexp (+ generated .py)
psychopy-cli run stroop.spec.json --simulate               # the trial table, no window needed
psychopy-cli run stroop.spec.json --participant p01        # present it, write data
psychopy-cli data summarize runs/<run>/data.csv --group-by condition
```

`build` writes `build/stroop.psyexp`, `build/conditions/*.csv` and `build/build-manifest.json`. `run` writes `runs/<timestamp>-stroop/data.csv` and `run-manifest.json`.

## Commands

| Command | Needs | What it does |
| --- | --- | --- |
| `catalog [command]` | – | the machine-readable contract of every command |
| `doctor [--check-window]` | – | Python, PsychoPy, display backends, component count |
| `components list` | PsychoPy | the installed Builder components |
| `components describe <Type>` | PsychoPy | every parameter of a component, with defaults |
| `spec schema` | – | JSON Schema of the spec language |
| `spec new <template> -o <file>` | – | scaffold `minimal`, `stroop` or `flanker` |
| `spec validate <file>` | – (PsychoPy improves it) | structural + registry checks with JSON paths |
| `build <spec> -o <dir>` | PsychoPy | compile to `.psyexp`, conditions CSVs, manifest |
| `inspect <.psyexp>` | PsychoPy | read an experiment back into spec JSON |
| `run <spec|.psyexp> --simulate` | – | expand the design into a trial table |
| `run <spec|.psyexp>` | PsychoPy + display | present it, record responses, write data |
| `stim grating\|noise\|text\|shape` | numpy, Pillow | render stimuli to PNG without a display |
| `data summarize <csv>` | – | rows, accuracy, RT statistics, grouped |

## The spec language

An experiment is one JSON document. This is the whole idea:

```json
{
  "spec_version": "1.0",
  "name": "stroop",
  "window": {"size": [1024, 768], "units": "height", "color": [0, 0, 0]},
  "routines": {
    "instruction": {"components": [
      {"type": "Text", "name": "prompt", "start": 0,
       "end": {"condition": "resp.rt"},
       "params": {"text": "Press SPACE to begin", "letterHeight": 0.05}},
      {"type": "Keyboard", "name": "resp",
       "params": {"allowedKeys": ["space"], "forceEndRoutine": true}}
    ]},
    "trial": {"components": [
      {"type": "Text", "name": "word", "start": 0, "end": {"condition": "resp.rt"},
       "params": {"text": "$word", "color": "$ink_color", "letterHeight": 0.1}},
      {"type": "Keyboard", "name": "resp",
       "params": {"allowedKeys": ["r", "g", "b", "y"], "correctAns": "$corr_key"}}
    ]}
  },
  "flow": [
    {"routine": "instruction"},
    {"loop": {"name": "trials", "routines": ["trial"], "n_reps": 1, "order": "random",
              "conditions": [{"word": "RED", "ink_color": [1, 0, 0], "corr_key": "r"}]}}
  ]
}
```

Conventions worth knowing:

- **Timing is explicit.** `start` and `end` accept a number, a condition expression, or an object like `{"duration": 1.5}` / `{"frame": 9}`. A bare number on `end` means *duration in seconds*, which is Builder's own default.
- **Two kinds of default.** Visual components end after 1 s; `Keyboard`, `Mouse` and `Button` stay open until the routine ends, matching Builder.
- **`$name` is an expression.** Values starting with `$` are evaluated per trial against the condition columns and the components in the routine, so `"$word"`, `"$ink_color"` and `"correctAns": "$corr_key"` all work.
- **Names are forgiving.** `letterHeight`, `letter_height` and `Letter Height` resolve to the same parameter. Misspellings are rejected with suggestions rather than silently ignored.

`psychopy-cli spec schema` is the authoritative version of this section.

## Output contract

Success:

```json
{"ok": true, "command": "spec.validate", "data": {...}, "warnings": ["..."],
 "meta": {"version": "0.1.0", "duration_ms": 41.2, "format": "json"}}
```

Failure:

```json
{"ok": false, "command": "build",
 "error": {"code": "SPEC_INVALID", "message": "spec has 2 error(s)",
           "hint": "fix the entries in `details`",
           "details": [{"path": "$.routines.trial.components[0].params.textt", "message": "..."}],
           "next": ["psychopy-cli spec validate stroop.spec.json"]},
 "meta": {"version": "0.1.0", "duration_ms": 12.0}}
```

| Exit | Meaning | Typical `code` |
| --- | --- | --- |
| 0 | success | – |
| 2 | usage error | `USAGE` |
| 3 | spec is invalid | `SPEC_INVALID` |
| 4 | file not found | `NOT_FOUND` |
| 5 | optional dependency missing | `MISSING_DEPENDENCY` |
| 6 | failure while building or running | `RUNTIME_ERROR` |
| 7 | environment problem | `ENVIRONMENT` |

`--format` is `auto` by default: JSON when stdout is not a TTY (i.e. when a program or agent runs it), human text in a terminal. Pass `--format json` to force it.

## Documentation

| Page | For |
| --- | --- |
| [`docs/llm-guide.md`](docs/llm-guide.md) | a model driving the tool: decision tree, failure handling, pitfalls |
| [`docs/spec-reference.md`](docs/spec-reference.md) | the spec language, timing forms, validation codes |
| [`docs/commands.md`](docs/commands.md) | every command and argument, generated from the registry |
| [`docs/architecture.md`](docs/architecture.md) | why build goes through Builder, why run is an interpreter |
| [`examples/`](examples/) | three complete experiments to copy from |
| [`AGENTS.md`](AGENTS.md) | instructions for coding agents in this repository |

## Design notes

- **Build goes through Builder.** `.psyexp` files are produced by instantiating `psychopy.experiment.Experiment`, `Routine`, component classes and `TrialHandler`, then calling `saveToXML`. No XML is templated here, so version defaults and legacy handling stay PsychoPy's business. The test suite asserts `build` → `loadFromXML` round-trips.
- **Run is an interpreter, not a script.** The generated Builder script opens an experiment-info dialog, which blocks an unattended caller. The built-in runtime drives `psychopy.visual` directly, so it can enforce `--timeout`, cap `--max-trials`, inject `--auto-response` for smoke tests, and honour `--simulate`.
- **The core has no dependencies.** `catalog`, `doctor`, `spec`, `data` and `run --simulate` run on the standard library, so an agent can inspect the tool before paying for a PsychoPy install.

## Limitations

- Spec 1.0 has no nested loops; flatten with `n_reps`.
- `run` presents `Text`, `Textbox`, `Image`, `Grating`, `Polygon`, `Sound`, `Keyboard`, `Mouse` and `Code`. Other components (`Slider`, `Form`, `Movie`, hardware devices…) still compile into `.psyexp` via `build`.
- Frame-accurate timing depends on the machine and the display; `ctypes`/`PTB` priority settings are left to `build`.

## License

GPL-3.0, the same as PsychoPy. This project depends on and derives its file format from PsychoPy, so it keeps that license.
