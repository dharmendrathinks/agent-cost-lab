"""Inspect release archives without extracting or executing their contents."""

from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path, PurePosixPath


FORBIDDEN = {".git", ".venv", ".uv-cache", ".cache", ".pytest_cache", "__pycache__",
             "artifacts", "raw-events", ".aws", ".codex", ".agents", ".DS_Store"}


def inspect_archive(path: Path) -> None:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            members = archive.getmembers()
            if any(member.issym() or member.islnk() for member in members):
                raise ValueError("distribution contains links")
            names = [member.name for member in members]
    else:
        raise ValueError("unsupported distribution format")
    for name in names:
        parts = PurePosixPath(name)
        if parts.is_absolute() or ".." in parts.parts or set(parts.parts) & FORBIDDEN:
            raise ValueError("distribution contains a forbidden path: " + name)
        if parts.name.startswith(".env") or parts.name.endswith((".local.toml", ".pyc", ".pyo")):
            raise ValueError("distribution contains local state: " + name)
    if not any(PurePosixPath(name).name == "LICENSE" for name in names):
        raise ValueError("distribution is missing LICENSE")
    if not any(name.endswith("agent_cost_lab/cli.py") for name in names):
        raise ValueError("distribution is missing the CLI")
    if path.name.endswith(".tar.gz"):
        for required in ("README.md", "CONTRIBUTING.md", "SECURITY.md", "THIRD_PARTY_NOTICES.md",
                         "configs/headroom-compatibility.toml", "configs/pricing.toml",
                         "tasks/fix-midnight.toml", "verification/midnight_cases.py",
                         "fixtures/timeledger/timeledger/ledger.py"):
            if not any(name.endswith("/" + required) for name in names):
                raise ValueError("source distribution is missing " + required)
    print(path.name + ": clean release contents")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    wheels = sorted(args.directory.glob("*.whl"))
    sources = sorted(args.directory.glob("*.tar.gz"))
    if not wheels or not sources:
        parser.error("both a wheel and source distribution are required")
    for path in wheels + sources:
        inspect_archive(path)


if __name__ == "__main__":
    main()
