# Architecture

## The problem

PsychoPy is a mature, large Python API for running behavioural experiments. An
assistant driving it directly has three failure modes: it does not know what
exists, it produces files that open but misbehave, and it cannot tell whether a
run worked because the output is a stream of free text.

This tool answers each of those with one design decision.

## One table drives everything

`src/psychopy_cli/registry.py` holds `COMMANDS`, a tuple of `Command(path,
summary, args, effects, requires, examples, returns)`. From it:

- `build_parser()` produces the `argparse` tree, including short flags,
  enums, repeatable arguments and defaults;
- `catalog` serialises the same data, plus a JSON Schema per argument;
- `tools/gen_command_docs.py` writes `docs/commands.md`.

Adding a command means adding one entry and one handler. There is no second
place where a flag can exist without being documented, or be documented without
existing. This is the anti-drift mechanism, and it is the reason `catalog` can
be trusted by a model.

## One document on stdout

`console.Result` wraps every successful command; `cli.main` wraps every failure.
stdout carries exactly one JSON document (or, in a TTY with `--format auto`,
human text). This is what makes the tool machine-consumable:

- PsychoPy, numpy and PIL are noisy. `sanitized_streams()` and
  `_StdoutIsolation` redirect their prints to stderr for the duration of any
  library call, so a chatty import cannot corrupt the envelope.
- Exit codes are a public contract, mapped from `error.code` in `errors.py`.
  An agent can branch on `3` (bad spec) versus `5` (missing dependency) without
  parsing English.
- Errors carry `hint` (how to fix it) and `next` (which command fixes it), plus
  `details` with JSON paths when the failure is per-field.

## Build through Builder, not around it

`builder/compile.py` does **not** template XML. It constructs
`psychopy.experiment.Experiment`, `addRoutine()`, instantiates the real
component classes, sets `params[key].val`, appends `LoopInitiator`/`LoopTerminator`
around `TrialHandler`, and calls `saveToXML()`. Consequences:

- version defaults, legacy parameter names and schema details stay PsychoPy's
  business;
- the result round-trips through `loadFromXML`, which the tests assert by
  reloading and comparing component counts and loop parameters;
- if a component exists in the installed PsychoPy, `build` can emit it, even
  the ones `run` cannot present.

`builder/precheck.py` uses the same registry *before* building, so a typo in a
parameter name is reported by `spec validate` with a suggestion, rather than
discovered halfway through a build.

## Run is an interpreter

`runtime/engine.py` drives `psychopy.visual` directly instead of executing the
generated script. The generated script is not suitable for an unattended
caller: it opens the experiment-info dialog, and it cannot be bounded.

The interpreter gives

- `--timeout` (wall clock cap) and `--max-trials` (smoke runs);
- `--auto-response` (scripted keypresses, so the runtime can be tested end to
  end without a participant);
- `--simulate`, which shares `spec.model.enumerate_trials()` with the real
  runtime, so the rehearsal and the run agree on the trial list by construction;
- a per-component state machine (`NOT_STARTED`/`STARTED`/`FINISHED`) exposed to
  `$` expressions and condition timings.

`HANDLERS` is a whitelist. Unsupported components fail with `SPEC_INVALID` and a
message pointing at `build`, instead of silently doing nothing.

## Two dependency tiers

The core (`catalog`, `doctor`, `spec`, `data`, `run --simulate`) is
standard-library only: an agent can inspect, author, validate and rehearse an
experiment on a bare Python. `build`/`inspect`/`run` need PsychoPy, `stim` needs
numpy + Pillow, and `run` needs a display. `doctor` reports each tier, and the
commands declare `requires` in the catalogue so the caller knows before calling.

## Deliberate limits

- Spec 1.0 has one loop level. Nested designs are rejected with a hint.
- `run` implements the components it can drive well; everything else is
  build-only.
- No MCP server: this is a CLI, and the envelope + `catalog` are the machine
  interface. A wrapper could be added later without changing the contract.
