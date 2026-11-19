"""Small path/IO helpers shared by handlers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import not_found, invalid


DEFAULT_DATA_DIRNAME = "data"


@dataclass
class Context:
    """Per-invocation state."""

    cwd: Path
    fmt: str

    def resolve(self, raw: str | os.PathLike[str]) -> Path:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = (self.cwd / path).resolve()
        return path

    def require_file(self, raw: str, *, what: str = "file") -> Path:
        path = self.resolve(raw)
        if not path.exists():
            raise not_found(
                f"{what} not found: {raw}",
                hint=f"resolve path: {path}",
                next_actions=["psychopy-cli catalog"],
            )
        if not path.is_file():
            raise not_found(f"{what} is not a file: {raw}", hint=f"resolve path: {path}")
        return path


def slugify(text: str, limit: int = 40) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "-", str(text)).strip("-._")
    return (cleaned or "run")[:limit]


def timestamp_slug() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_text(path: Path, text: str, encoding: str = "utf-8") -> Path:
    ensure_dir(path.parent)
    path.write_text(text, encoding=encoding)
    return path


def write_json(path: Path, payload: Any) -> Path:
    return write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def atomic_write_text(path: Path, text: str) -> Path:
    """Write via a temp file in the same directory, then replace."""
    ensure_dir(path.parent)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=path.suffix)
    os.close(fd)
    tmp_path = Path(tmp)
    try:
        tmp_path.write_text(text, encoding="utf-8")
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def refuse_overwrite(path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise invalid(
            f"refusing to overwrite existing file: {path}",
            hint="pass --force to replace it, or choose a different output path",
        )
