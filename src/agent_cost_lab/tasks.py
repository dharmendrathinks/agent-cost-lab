"""Public, declarative task manifests."""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    fixture: Path
    allowed_source: Path
    verifier: Path
    requirements: str
    manifest_hash: str


def load_task(path: Path, project_root: Path) -> Task:
    root = project_root.resolve()
    manifest = path.resolve()
    if not manifest.is_relative_to(root / "tasks") or manifest.suffix != ".toml":
        raise ValueError("task manifest must be in the project tasks directory")
    content = path.read_bytes()
    raw = tomllib.loads(content.decode("utf-8"))
    required = {"id", "title", "fixture", "allowed_source", "verifier", "requirements"}
    if set(raw) != required or not all(isinstance(raw[k], str) and raw[k] for k in required):
        raise ValueError("task manifest has unsupported or missing fields")
    fixture = (root / raw["fixture"]).resolve()
    verifier = (root / raw["verifier"]).resolve()
    if fixture != root / "fixtures/timeledger" or not verifier.is_relative_to(root / "verification") or verifier.suffix != ".py":
        raise ValueError("task fixture or verifier path is outside the trusted layout")
    if not fixture.is_dir() or not verifier.is_file():
        raise ValueError("task fixture or verifier is missing")
    allowed = Path(raw["allowed_source"])
    if allowed.is_absolute() or ".." in allowed.parts or not (fixture / allowed).is_file():
        raise ValueError("allowed source path is invalid")
    return Task(raw["id"], raw["title"], fixture, allowed, verifier, raw["requirements"], hashlib.sha256(content).hexdigest())
