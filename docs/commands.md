# Command reference

Generated from `src/psychopy_cli/registry.py` by `python tools/gen_command_docs.py`.
The same table is available at runtime, with JSON Schema, from `psychopy-cli catalog`.

## `catalog`

### `psychopy-cli catalog <command> [--format]`

List every command with its JSON input schema (start here).

Returns the machine-readable contract for this tool: command ids, arguments, JSON Schema for each input, side effects, and examples. Pass a command id to get a single entry. An agent should call this once, then drive the tool from the result.

- requires: nothing beyond Python
- effects: read_only
- returns: `{commands: [Command]} or {command: Command}`

| argument | type | required | default | description |
| --- | --- | --- | --- | --- |
| `command` | str | no | — | command id to describe, e.g. 'build' or 'spec.validate' |
| `--format` | enum | no | `auto` | output format; auto emits JSON when stdout is not a TTY |

Examples:

```bash
psychopy-cli catalog
psychopy-cli catalog build
```


## `doctor`

### `psychopy-cli doctor [--check-window] [--format]`

Probe the environment: Python, PsychoPy, display, audio, components.

Runs the checks you need before trusting any other command: is PsychoPy importable and at which version, which window backends can actually open, are numpy/Pillow present for stimulus rendering. `--check-window` opens and closes a real window, which needs a display.

- requires: nothing beyond Python
- effects: read_only
- returns: `{python, psychopy, display, components, stim}`

| argument | type | required | default | description |
| --- | --- | --- | --- | --- |
| `--check-window` | bool | no | — | open and close a real window to test the display backend |
| `--format` | enum | no | `auto` | output format; auto emits JSON when stdout is not a TTY |

Examples:

```bash
psychopy-cli doctor
psychopy-cli doctor --check-window
```


## `components`

### `psychopy-cli components list [--filter] [--format]`

List Builder components available in the installed PsychoPy.

The authoritative component registry of the installed PsychoPy. Use it to confirm a component type exists before putting it in a spec, and to see the version that defines its parameter set.

- requires: psychopy
- effects: read_only
- returns: `{count, components: [{type, label, categories}]}`

| argument | type | required | default | description |
| --- | --- | --- | --- | --- |
| `--filter` | str | no | — | only show components whose name contains this text |
| `--format` | enum | no | `auto` | output format; auto emits JSON when stdout is not a TTY |

Examples:

```bash
psychopy-cli components list --filter text
```

### `psychopy-cli components describe <name> [--format]`

Show the exact parameter names, defaults and allowed values of a component.

Everything the Builder knows about one component: every parameter key, its default, its allowed values and whether it accepts code. Build specs against this output rather than guessing parameter names; key lookup in specs is forgiving but values are not.

- requires: psychopy
- effects: read_only
- returns: `{type, label, version, parameters: [{name, default, type, allowed}]}`

| argument | type | required | default | description |
| --- | --- | --- | --- | --- |
| `name` | str | no | — | component type, e.g. TextComponent or 'Text' |
| `--format` | enum | no | `auto` | output format; auto emits JSON when stdout is not a TTY |

Examples:

```bash
psychopy-cli components describe Text
```


## `spec`

### `psychopy-cli spec schema [--format]`

Emit the JSON Schema of the experiment spec language.

The full grammar an agent must follow when authoring an experiment spec. Fetch it once and keep it in context; do not infer the format from examples alone.

- requires: nothing beyond Python
- effects: read_only
- returns: `JSON Schema document`

| argument | type | required | default | description |
| --- | --- | --- | --- | --- |
| `--format` | enum | no | `auto` | output format; auto emits JSON when stdout is not a TTY |

Examples:

```bash
psychopy-cli spec schema
```

### `psychopy-cli spec new <template> [--output] [--force] [--format]`

Write a starter spec you can edit.

Scaffolds a valid spec for a known design. Templates are complete and runnable, so the fastest path is: `spec new` -> edit -> `spec validate` -> `build` -> `run --simulate`.

- requires: nothing beyond Python
- effects: writes_files
- returns: `{path, template}`

| argument | type | required | default | description |
| --- | --- | --- | --- | --- |
| `template` | enum | no | `minimal` | design template to scaffold |
| `--output` | path | no | — | file to write (default: <template>.spec.json) |
| `--force` | bool | no | — | overwrite an existing file |
| `--format` | enum | no | `auto` | output format; auto emits JSON when stdout is not a TTY |

Examples:

```bash
psychopy-cli spec new stroop -o stroop.spec.json
```

### `psychopy-cli spec validate <path> [--strict] [--format]`

Check a spec for errors before building or running it.

Static checks: required fields, unknown component types, unknown parameters (with suggestions), timing expressions, flow references, condition column usage. Errors carry a JSON path so an agent can patch the file it produced.

- requires: nothing beyond Python
- effects: read_only
- returns: `{valid, errors: [{path, code, message, hint}], warnings, stats}`

| argument | type | required | default | description |
| --- | --- | --- | --- | --- |
| `path` | path | yes | — | spec file to validate |
| `--strict` | bool | no | — | treat warnings as errors |
| `--format` | enum | no | `auto` | output format; auto emits JSON when stdout is not a TTY |

Examples:

```bash
psychopy-cli spec validate stroop.spec.json
```


## `build`

### `psychopy-cli build <path> [--output] [--psyexp] [--script] [--force] [--dry-run] [--format]`

Compile a spec into a runnable PsychoPy .psyexp plus optional Python.

Builds the artifacts through PsychoPy's own Builder classes, so the result opens in Builder and round-trips through `loadFromXML`. Writes the .psyexp, any conditions CSVs, an optional generated script and a manifest describing the build.

- requires: psychopy
- effects: writes_files
- returns: `{artifacts: [{path, role, bytes}], psyexp, script, manifest}`

| argument | type | required | default | description |
| --- | --- | --- | --- | --- |
| `path` | path | yes | — | spec file |
| `--output` | path | no | — | output directory (default: alongside the spec) |
| `--psyexp` | bool | no | true | write the .psyexp file |
| `--script` | bool | no | — | also write a generated PsychoPy script |
| `--force` | bool | no | — | overwrite existing artifacts |
| `--dry-run` | bool | no | — | validate and plan only, write nothing |
| `--format` | enum | no | `auto` | output format; auto emits JSON when stdout is not a TTY |

Examples:

```bash
psychopy-cli build stroop.spec.json -o build/
psychopy-cli build stroop.spec.json --script --force
```


## `inspect`

### `psychopy-cli inspect <path> [--output] [--force] [--format]`

Read a .psyexp back into a spec-shaped JSON description.

Parses an experiment with PsychoPy's Builder and re-emits it in this tool's spec dialect. Use it to take over an existing experiment, or to diff a build against its source spec.

- requires: psychopy
- effects: read_only
- returns: `{spec} or {path, spec}`

| argument | type | required | default | description |
| --- | --- | --- | --- | --- |
| `path` | path | yes | — | .psyexp file to read |
| `--output` | path | no | — | write the spec JSON here instead of stdout |
| `--force` | bool | no | — | overwrite the output file |
| `--format` | enum | no | `auto` | output format; auto emits JSON when stdout is not a TTY |

Examples:

```bash
psychopy-cli inspect build/stroop.psyexp
```


## `run`

### `psychopy-cli run <path> [--participant] [--session] [--simulate] [--timeout] [--max-trials] [--output] [--seed] [--window-size] [--fullscreen] [--auto-response] [--format]`

Execute an experiment: simulate the design, or present it for real.

Two modes with one contract. `--simulate` enumerates trials, resolves condition variables and writes the trial table without opening a window -- always available and the right first check. Without `--simulate` it presents stimuli on a real window, records responses and timings, honours --timeout and --max-trials, and writes data plus a manifest into a run directory.

- requires: psychopy
- effects: runs_experiment
- returns: `{run_dir, data_file, n_trials, mode, summary}`

| argument | type | required | default | description |
| --- | --- | --- | --- | --- |
| `path` | path | yes | — | spec file or .psyexp |
| `--participant` | str | no | `auto` | participant id |
| `--session` | str | no | `001` | session id |
| `--simulate` | bool | no | — | enumerate the design only; no window, no rendering |
| `--timeout` | float | no | `600.0` | hard wall-clock limit in seconds |
| `--max-trials` | int | no | `0` | stop after N trials (0 = run them all) |
| `--output` | path | no | — | run directory (default: runs/<timestamp>-<name>) |
| `--seed` | int | no | — | random seed for condition order |
| `--window-size` | str | no | — | window size as WIDTHxHEIGHT, e.g. 1024x768 |
| `--fullscreen` | bool | no | — | present full screen |
| `--auto-response` | bool | no | — | answer every keyboard component automatically (smoke tests only) |
| `--format` | enum | no | `auto` | output format; auto emits JSON when stdout is not a TTY |

Examples:

```bash
psychopy-cli run stroop.spec.json --simulate
psychopy-cli run stroop.spec.json --participant p01 --max-trials 4
```


## `stim`

### `psychopy-cli stim list [--format]`

List the stimulus generators that need no display.

Pure-numpy stimulus synthesis. Every generator writes a PNG and reports the numeric properties it used, so it works on a headless box and is deterministic given the same arguments.

- requires: stim
- effects: read_only
- returns: `{generators: [...]}`

| argument | type | required | default | description |
| --- | --- | --- | --- | --- |
| `--format` | enum | no | `auto` | output format; auto emits JSON when stdout is not a TTY |

Examples:

```bash
psychopy-cli stim list
```

### `psychopy-cli stim grating --output <output> [--size] [--sf] [--ori] [--phase] [--contrast] [--mask] [--sigma] [--background] [--foreground-is-dark] [--format]`

Render a Gabor / grating patch to PNG.

Sinusoidal luminance grating with an optional Gaussian or circular window -- the standard psychophysics stimulus. Frequencies are in cycles per pixel, contrast is Michelson contrast in [0, 1].

- requires: stim
- effects: writes_files
- returns: `{path, size, sf, ori, contrast, contrast_measured}`

| argument | type | required | default | description |
| --- | --- | --- | --- | --- |
| `--output` | path | yes | — | PNG file to write |
| `--size` | int | no | `512` | image side length in pixels |
| `--sf` | float | no | `0.05` | spatial frequency in cycles/pixel |
| `--ori` | float | no | `0.0` | orientation in degrees |
| `--phase` | float | no | `0.0` | phase in cycles |
| `--contrast` | float | no | `1.0` | Michelson contrast, 0..1 |
| `--mask` | enum | no | `gaussian` | envelope |
| `--sigma` | float | no | `0.3` | Gaussian sigma as a fraction of the radius |
| `--background` | float | no | `0.5` | background luminance, 0..1 |
| `--foreground-is-dark` | bool | no | — | invert so dark bars sit on the background |
| `--format` | enum | no | `auto` | output format; auto emits JSON when stdout is not a TTY |

Examples:

```bash
psychopy-cli stim grating -o gabor.png --sf 0.04 --ori 45
```

### `psychopy-cli stim noise --output <output> [--size] [--type] [--sd] [--seed] [--background] [--format]`

Render a random-noise field to PNG.

Gaussian or uniform noise with a fixed seed, for masking and texture work.

- requires: stim
- effects: writes_files
- returns: `{path, size, type, sd, seed}`

| argument | type | required | default | description |
| --- | --- | --- | --- | --- |
| `--output` | path | yes | — | PNG file to write |
| `--size` | int | no | `512` | image side length in pixels |
| `--type` | enum | no | `gaussian` | noise distribution |
| `--sd` | float | no | `0.1` | standard deviation for gaussian noise |
| `--seed` | int | no | `0` | seed for reproducibility |
| `--background` | float | no | `0.5` | background luminance, 0..1 |
| `--format` | enum | no | `auto` | output format; auto emits JSON when stdout is not a TTY |

Examples:

```bash
psychopy-cli stim noise -o noise.png --type uniform
```

### `psychopy-cli stim text --output <output> --text <text> [--height] [--font] [--color] [--background] [--padding] [--format]`

Render text to a transparent PNG (no PsychoPy needed).

Text as an image, for posters, instruction screens or materials that must not depend on the presentation machine's fonts.

- requires: stim
- effects: writes_files
- returns: `{path, width, height}`

| argument | type | required | default | description |
| --- | --- | --- | --- | --- |
| `--output` | path | yes | — | PNG file to write |
| `--text` | str | yes | — | text to draw; 
 starts a new line |
| `--height` | int | no | `64` | cap height in pixels |
| `--font` | str | no | `Arial` | font family or file |
| `--color` | str | no | `white` | foreground colour, e.g. '#ffffff' or 'white' |
| `--background` | str | no | `transparent` | background colour, or 'transparent' |
| `--padding` | int | no | `16` | padding in pixels |
| `--format` | enum | no | `auto` | output format; auto emits JSON when stdout is not a TTY |

Examples:

```bash
psychopy-cli stim text -o fix.png --text '+' --height 96
```

### `psychopy-cli stim shape --output <output> [--shape] [--size] [--fill] [--line] [--line-width] [--rotation] [--background] [--format]`

Render a geometric shape to PNG.

Circle, triangle, rectangle, cross or star, filled or outlined, with rotation.

- requires: stim
- effects: writes_files
- returns: `{path, shape, size}`

| argument | type | required | default | description |
| --- | --- | --- | --- | --- |
| `--output` | path | yes | — | PNG file to write |
| `--shape` | enum | no | `circle` | shape to draw |
| `--size` | int | no | `256` | image side length in pixels |
| `--fill` | str | no | `white` | fill colour, or 'none' |
| `--line` | str | no | `none` | outline colour, or 'none' |
| `--line-width` | int | no | `0` | outline width in pixels |
| `--rotation` | float | no | `0.0` | rotation in degrees |
| `--background` | str | no | `transparent` | background colour, or 'transparent' |
| `--format` | enum | no | `auto` | output format; auto emits JSON when stdout is not a TTY |

Examples:

```bash
psychopy-cli stim shape -o cue.png --shape triangle --rotation 90
```


## `data`

### `psychopy-cli data summarize <path> [--group-by] [--rt-column] [--correct-column] [--format]`

Summarise a result file: trial counts, accuracy, response times.

Reads the CSV written by `run` (or a conditions file) and reports row counts, per-condition grouping, accuracy from *.corr columns and RT statistics from *.rt columns. Standard library only.

- requires: nothing beyond Python
- effects: read_only
- returns: `{rows, columns, groups: [{group, n, accuracy, rt_mean, rt_median}]}`

| argument | type | required | default | description |
| --- | --- | --- | --- | --- |
| `path` | path | yes | — | CSV file to summarize |
| `--group-by` | str | no | — | column to group by; repeatable |
| `--rt-column` | str | no | — | response-time column (default: first column ending in .rt) |
| `--correct-column` | str | no | — | accuracy column (default: first column ending in .corr) |
| `--format` | enum | no | `auto` | output format; auto emits JSON when stdout is not a TTY |

Examples:

```bash
psychopy-cli data summarize runs/20260101-120000-stroop/data.csv --group-by condition
```
