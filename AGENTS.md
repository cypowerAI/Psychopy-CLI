# AGENTS.md

Instructions for coding agents working **in this repository**, and a short
contract for agents that call the installed CLI.

## Calling the CLI

- Read the contract first: `psychopy-cli catalog --format json` and, for the
  command you are about to use, `psychopy-cli catalog <command>`.
- stdout is one JSON document. Parse it; never scrape prose. Branch on the exit
  code: `0` ok, `2` usage, `3` invalid spec, `4` not found, `5` missing
  dependency, `6` runtime, `7` environment, `130` interrupted.
- Treat `error.details[].path` as the list of fields to fix.
- Validate (`spec validate`) and rehearse (`run --simulate`) before building or
  running. Both are cheap and need no display.
- Do not invent flags. If a flag is not in `catalog`, it does not exist.

Deeper walkthrough: `docs/llm-guide.md`. Grammar: `docs/spec-reference.md`.

## Working on the code

```bash
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[psychopy,stim,dev]"
python -m pytest -q                               # full suite
python -m pytest -q -m "not psychopy and not stim" # core only, no heavy deps
```

### Rules that keep the design honest

1. **The registry is the only source of truth.** A new command is one
   `Command` entry in `registry.py` plus a handler in `commands/`. Never add an
   `argparse` argument by hand, and never document a flag outside the registry.
2. **stdout is sacred.** Any code path that can print (PsychoPy imports, PIL,
   numpy warnings) must run inside `sanitized_streams()`. Print nothing
   yourself; return a `Result`.
3. **Errors are typed.** Raise `CliError` through the helpers in `errors.py`
   (`usage`, `invalid`, `not_found`, `missing_dependency`, `runtime`,
   `environment`). Free-text exceptions become `INTERNAL` and are a bug.
4. **Build with Builder.** Do not template `.psyexp` XML. Use the component
   classes; add a round-trip test for anything new.
5. **Spec changes need three edits**: parser (`spec/model.py`), schema
   (`spec/schema.py`), and the reference (`docs/spec-reference.md`).
6. **Keep the core dependency-free.** `catalog`, `doctor`, `spec`, `data` and
   `run --simulate` must import nothing outside the standard library.

### Before you finish

- `python -m pytest -q` passes;
- `python tools/gen_command_docs.py` leaves `docs/commands.md` unchanged;
- `psychopy-cli catalog --format json` still parses;
- if you touched a template, `spec new <template> -o /tmp/x.json && spec validate /tmp/x.json`
  succeeds.
