"""Create isolated fixture snapshots and reject changes outside task source."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from .tasks import Task


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("fixture contains a symlink")
        if path.is_file() and ".git" not in path.parts and "__pycache__" not in path.parts:
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def prepare_workspace(task: Task, target: Path, *, git: bool) -> str:
    if target.exists():
        raise FileExistsError(target)
    shutil.copytree(task.fixture, target, symlinks=False, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
    start_hash = tree_hash(target)
    if git:
        subprocess.run(["git", "-c", "init.defaultBranch=main", "init", "-q", str(target)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "add", "."], check=True, capture_output=True)
        fixed_env = {**os.environ, "GIT_AUTHOR_DATE": "2026-09-28T00:00:00+00:00", "GIT_COMMITTER_DATE": "2026-09-28T00:00:00+00:00"}
        subprocess.run(
            ["git", "-C", str(target), "-c", "commit.gpgsign=false", "-c", "user.name=Agent Cost Lab", "-c", "user.email=lab@example.invalid", "commit", "-q", "-m", "fixture snapshot"],
            check=True, capture_output=True, env=fixed_env,
        )
    return start_hash


def commit_hash(workspace: Path) -> str:
    result = subprocess.run(["git", "-C", str(workspace), "rev-parse", "HEAD"], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def validate_candidate(task: Task, workspace: Path) -> None:
    original = {p.relative_to(task.fixture) for p in task.fixture.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    observed = {p.relative_to(workspace) for p in workspace.rglob("*") if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts}
    if original != observed:
        raise ValueError("candidate added or removed fixture files")
    for relative in original:
        path = workspace / relative
        if path.is_symlink():
            raise ValueError("candidate added a symlink")
        if relative != task.allowed_source and file_hash(path) != file_hash(task.fixture / relative):
            raise ValueError("candidate modified protected fixture file: " + str(relative))


def copy_candidate_for_verification(task: Task, candidate: Path, target: Path) -> None:
    validate_candidate(task, candidate)
    if target.exists():
        raise FileExistsError(target)
    shutil.copytree(task.fixture, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
    source = candidate / task.allowed_source
    if source.is_symlink() or not source.is_file():
        raise ValueError("candidate source is invalid")
    shutil.copyfile(source, target / task.allowed_source)
