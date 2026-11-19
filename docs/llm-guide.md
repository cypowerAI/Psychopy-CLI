# Driving psychopy-cli from a model

This page is written for an assistant that has a shell and a user who wants an
experiment. It is a decision tree, not a tour.

## 0. Establish what the tool can do — once per session

```bash
psychopy-cli catalog --format json          # every command + JSON Schema
psychopy-cli doctor --format json           # is PsychoPy importable? can it open a window?
```

Read `data.commands[].id`, `.usage`, `.requires`, `.effects`. If
`data.psychopy.available` is false, `build` and `run` will exit with code 5:
either install the extra (`pip install "psychopy-cli[psychopy]"`) or stay in
`spec` / `run --simulate` / `data` land, which need nothing.

Do not guess a flag. `psychopy-cli catalog build` prints exactly the arguments
`build` accepts.

## 1. Turn the user's request into a spec

Start from the closest template rather than a blank file:

```bash
psychopy-cli spec new minimal -o exp.spec.json    # one routine, one loop
psychopy-cli spec new stroop  -o exp.spec.json    # colour conditions + scoring
psychopy-cli spec new flanker -o exp.spec.json    # frame timing + accuracy
psychopy-cli spec schema --format json            # the full grammar
```

Edit the JSON, keeping these invariants:

- `spec_version` stays `"1.0"`.
- Every routine named in `flow` exists in `routines`.
- Every loop has `conditions` (inline rows) or `conditions_file`.
- `start`/`end` are numbers, condition strings, or one-key objects
  (`{"duration": 1.0}`, `{"frame": 9}`, `{"duration_frames": 12}`).
- Values beginning with `$` are evaluated per trial (`"$word"`, `"$corr_key"`).
- Component names are unique across the whole experiment. Builder renames
  duplicates on load, which silently breaks `$` references.

If you are unsure a parameter exists, ask the tool:

```bash
psychopy-cli components describe Text --format json
```

The reply lists every key with its default, type and allowed values.

## 2. Validate before building

```bash
psychopy-cli spec validate exp.spec.json
```

Exit code 3 means the spec is wrong; `error.details[]` carries one entry per
problem, each with a JSON path (`$.routines.trial.components[0].params.textt`).
Fix the paths, re-run, and only then build. `--strict` also promotes warnings
(e.g. a loop with a single repetition) to errors.

## 3. Check the design without a display

```bash
psychopy-cli run exp.spec.json --simulate -o runs/rehearsal --max-trials 5
```

`data.design_file` is a CSV with one row per flow step: the routines it runs,
the loop bookkeeping, and the condition columns. This is where a wrong loop
count, an empty condition column, or a routine that never ends becomes obvious.
It needs no PsychoPy and no window.

## 4. Build the artifact

```bash
psychopy-cli build exp.spec.json -o build/ --script
```

- `data.psyexp` opens in PsychoPy Builder; it is produced by Builder's own
  classes, not by templating XML.
- `data.conditions` lists the condition CSVs that were written next to it.
- `data.script` is the generated Python, only when `--script` is passed.
- `data.manifest` records versions and hashes, so a result can be traced back
  to the exact spec that produced it.

`build` refuses to overwrite an existing `.psyexp` unless `--force` is given.
Use `--dry-run` to see the planned paths without writing.

## 5. Run it

Two modes, and the difference matters:

| Mode | Command | Needs | What it proves |
| --- | --- | --- | --- |
| rehearse | `run --simulate` | nothing | the design expands as intended |
| present | `run` | PsychoPy + display | the experiment actually runs |

```bash
psychopy-cli run exp.spec.json --participant p01 --session 001
psychopy-cli run exp.spec.json --participant p01 --auto-response --timeout 120
```

- `--timeout` is a hard wall clock cap; a stuck routine cannot hang the caller.
- `--max-trials` caps the number of trials, for smoke runs.
- `--auto-response` answers every keyboard component automatically. Use it to
  prove the runtime works; never for real data.
- `--fullscreen` / `--window-size 1024x768` override the spec.
- The reply's `data.aborted_reason` is `null` for a complete run.

## 6. Read the results

```bash
psychopy-cli data summarize runs/<run>/data.csv --group-by condition
```

`data.overall` has `n`, `rt` (mean/median/sd/min/max) and `accuracy`; `data.groups`
repeats that per condition value. Columns are detected by suffix (`*.rt`, `*.corr`),
so differently named keyboard components still work.

## Failure handling

Branch on the exit code, not the prose:

| Exit | `error.code` | What to do |
| --- | --- | --- |
| 2 | `USAGE` | the invocation is wrong; re-read `catalog <command>` |
| 3 | `SPEC_INVALID` | fix `error.details[]` by path, then re-validate |
| 4 | `NOT_FOUND` | the path is wrong; `error.hint` shows what was looked for |
| 5 | `MISSING_DEPENDENCY` | install the extra named in `error.message` |
| 6 | `RUNTIME_ERROR` | the experiment failed while running; check `details` |
| 7 | `ENVIRONMENT` | the machine cannot do this (no display, wrong Python) |
| 130 | `INTERRUPTED` | the user pressed Ctrl-C |

Every failure carries `hint` when the tool knows how to fix it, and `next`
when a specific command does. When `--debug` is set, stdout still carries the
envelope and the traceback goes to stderr.

## Things that will bite you

- **Two things named `resp`.** Builder renames the second one to `resp_2` on
  load. Give each routine's keyboard its own name.
- **`end` on a visual component defaults to 1.0 s.** A fixation that should
  persist until a response needs `"end": {"condition": "resp.rt"}`.
- **Condition values are CSV cells.** A colour like `[1, 0, 0]` is stored as its
  repr and evaluated at run time; that is supported, and it is what the stroop
  template does.
- **`run` implements a subset.** It presents Text, Textbox, Image, Grating,
  Polygon, Sound, Keyboard, Mouse and Code. Anything else still compiles into
  `.psyexp`; `run` says so in `error.message` rather than pretending.
