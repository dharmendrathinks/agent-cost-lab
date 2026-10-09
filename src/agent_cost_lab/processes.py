"""Cleanup for processes started in their own session by Agent Cost Lab."""

from __future__ import annotations

import os
import signal
import subprocess
import time


def stop_owned_process(process: subprocess.Popen) -> None:
    # A reaped leader can leave descendants holding pipes or running in its group.
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, signum)
        except ProcessLookupError:
            process.wait(timeout=2)
            return
        deadline = time.monotonic() + 2
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            continue
        if signum != signal.SIGKILL:
            # Preserve the grace period for descendants even if their leader exited.
            time.sleep(max(0, deadline - time.monotonic()))
    # SIGKILL has reached every remaining member of this owned group.
    process.wait(timeout=2)
