"""Independent verifier running candidate code inside a deny-default macOS sandbox."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .records import VerificationResult
from .processes import stop_owned_process
from .tasks import Task
from .workspace import copy_candidate_for_verification


class VerificationBoundaryError(RuntimeError):
    pass


def _literal(path: Path) -> str:
    return json.dumps(str(path.resolve()))


def _profile(candidate: Path, scratch: Path, python: Path) -> str:
    candidate = candidate.resolve()
    scratch = scratch.resolve()
    python_root = python.resolve().parents[1]
    ancestors = set(candidate.parents) | set(scratch.parents) | set(python_root.parents)
    reads = " ".join(
        [f"(literal {_literal(p)})" for p in sorted(ancestors, key=str)]
        + [f"(subpath {_literal(p)})" for p in (candidate, scratch, python_root, Path("/System"), Path("/usr"), Path("/bin"), Path("/sbin"), Path("/Library"), Path("/dev"))]
    )
    # uv's venv interpreter can point through a version alias before the real
    # runtime. Script shebang execution needs metadata access to that alias,
    # without granting reads of unrelated contents in the runtime store.
    alias_metadata = ""
    interpreter = python.absolute()
    if interpreter.is_symlink():
        target = interpreter.readlink()
        if not target.is_absolute():
            target = interpreter.parent / target
        paths = (target, *target.parents)
        alias_metadata = "(allow file-read-metadata " + " ".join("(literal " + json.dumps(str(path)) + ")" for path in paths) + ")"
    return "\n".join([
        "(version 1)", "(deny default)", "(allow process*)", "(allow sysctl-read)",
        "(allow file-read* " + reads + ")",
        alias_metadata,
        "(allow file-write* (subpath " + _literal(scratch) + ") (literal \"/dev/null\"))",
    ]) + "\n"


def sandbox_available() -> bool:
    return sys.platform == "darwin" and shutil.which("sandbox-exec") is not None


def _sandbox_run(candidate: Path, profile: Path, source: str, payload: object, timeout: int, scratch: Path) -> subprocess.CompletedProcess[str]:
    if not sandbox_available():
        raise VerificationBoundaryError("macOS sandbox-exec is required; no unrestricted fallback")
    # Match the canonical paths granted by the profile. macOS /var and /tmp
    # aliases otherwise require traversal permissions outside that boundary.
    candidate = candidate.resolve()
    profile = profile.resolve()
    scratch = scratch.resolve()
    python = Path(sys.executable).resolve()
    env = {"PATH": "/usr/bin:/bin", "TMPDIR": str(scratch), "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(scratch)}
    command = ["sandbox-exec", "-f", str(profile), str(python), "-I", "-S", "-c", source, str(candidate)]
    process = subprocess.Popen(command, text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, cwd=candidate, env=env, start_new_session=True)
    try:
        stdout, stderr = process.communicate(json.dumps(payload), timeout=timeout)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    finally:
        stop_owned_process(process)


def boundary_probe(candidate: Path, protected: Path) -> None:
    """Prove code can run but cannot read or write a private sentinel."""
    with tempfile.TemporaryDirectory(prefix="acl-boundary-") as td:
        scratch = Path(td)
        sentinel = scratch.parent / (scratch.name + "-sentinel")
        sentinel.write_text("untouched")
        profile = scratch / "candidate.sb"
        profile.write_text(_profile(candidate, scratch, Path(sys.executable)))
        try:
            positive = _sandbox_run(candidate, profile, "print('sandbox-ok')", {}, 10, scratch)
            if positive.returncode != 0 or positive.stdout.strip() != "sandbox-ok":
                if "sandbox_apply" in positive.stderr and "Operation not permitted" in positive.stderr:
                    raise VerificationBoundaryError("current host denies nested macOS sandbox creation (sandbox_apply); restricted execution cannot start in this session")
                raise VerificationBoundaryError("candidate sandbox cannot execute Python")
            read_code = "open(" + json.dumps(str(protected.resolve())) + ").read()"
            denied = _sandbox_run(candidate, profile, read_code, {}, 10, scratch)
            if denied.returncode == 0:
                raise VerificationBoundaryError("candidate sandbox can read protected material")
            write_code = "open(" + json.dumps(str(sentinel)) + ", 'a').write('x')"
            denied_write = _sandbox_run(candidate, profile, write_code, {}, 10, scratch)
            if denied_write.returncode == 0 or sentinel.read_text() != "untouched":
                raise VerificationBoundaryError("candidate sandbox can modify protected material")
        finally:
            sentinel.unlink(missing_ok=True)


def fixture_execution_probe(task: Task) -> None:
    """Check the buggy fixture and trusted reference through the real verifier."""
    starting = verify(task, task.fixture, timeout=30)
    if starting.status != "failed" or starting.passed is not False or "public_development_tests" in starting.failure_ids:
        raise VerificationBoundaryError("starting fixture must pass public checks and fail targeted acceptance checks in the restricted verifier")
    with tempfile.TemporaryDirectory(prefix="acl-fixture-probe-") as td:
        root = Path(td)
        candidate = root / "candidate"
        shutil.copytree(task.fixture, candidate, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
        reference = task.verifier.parent / "reference_ledger.py"
        shutil.copyfile(reference, candidate / task.allowed_source)
        result = verify(task, candidate, timeout=30)
        if result.passed is not True:
            raise VerificationBoundaryError("trusted reference cannot pass acceptance checks in the restricted verifier")


def _public_test_source() -> str:
    return "import runpy,sys; sys.path.insert(0,sys.argv[1]); runpy.run_path(sys.argv[1] + '/tests/test_public.py')['test_same_day_project_summary']()"


def _cases_from_trusted_file(path: Path):
    spec = importlib.util.spec_from_file_location("trusted_midnight_cases", path)
    if spec is None or spec.loader is None:
        raise ValueError("invalid trusted case file")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CASES


def verify(task: Task, candidate: Path, *, timeout: int = 60) -> VerificationResult:
    deadline = time.monotonic() + timeout
    with tempfile.TemporaryDirectory(prefix="acl-verify-") as td:
        root = Path(td)
        trusted_candidate = root / "candidate"
        copy_candidate_for_verification(task, candidate, trusted_candidate)
        protected = task.verifier.resolve()
        boundary_probe(trusted_candidate, protected)
        scratch = root / "scratch"
        scratch.mkdir()
        profile = scratch / "candidate.sb"
        profile.write_text(_profile(trusted_candidate, scratch, Path(sys.executable)))
        code = "import sys; sys.path.insert(0, sys.argv[1]); from timeledger.harness import main; main()"
        failures = []
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return VerificationResult(False, "timeout")
        try:
            public = _sandbox_run(trusted_candidate, profile, _public_test_source(), {}, remaining, scratch)
        except subprocess.TimeoutExpired:
            return VerificationResult(False, "timeout")
        if public.returncode != 0:
            failures.append("public_development_tests")
        cases = _cases_from_trusted_file(task.verifier)
        for case_id, rows, expected in cases:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return VerificationResult(False, "timeout", len(cases) + 1)
            try:
                result = _sandbox_run(trusted_candidate, profile, code, rows, remaining, scratch)
                actual = json.loads(result.stdout) if result.returncode == 0 else None
            except subprocess.TimeoutExpired:
                return VerificationResult(False, "timeout", len(cases) + 1)
            except json.JSONDecodeError:
                actual = None
            if isinstance(expected, dict) and expected.get("error") == "ValueError":
                matched = isinstance(actual, dict) and actual.get("error") == "ValueError" and expected["contains"] in actual.get("message", "")
            else:
                matched = actual == expected
            if not matched:
                failures.append(case_id)
        total = len(cases) + 1
        return VerificationResult(not failures, "passed" if not failures else "failed", total, total - len(failures), tuple(failures))
