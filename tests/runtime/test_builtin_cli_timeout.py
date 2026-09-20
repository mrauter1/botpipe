from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import textwrap

import pytest

from botpipe.core.providers.turns import RenderedProviderTurn
from botpipe.runtime.providers.codex import CodexCLICommand, CodexTransport

_FAKE_CODEX = r"""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def child(marker: Path) -> None:
    def terminate(*_args: object) -> None:
        marker.with_suffix(".terminated").write_text("terminated", encoding="utf-8")
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, terminate)
    marker.with_suffix(".child_ready").write_text("ready", encoding="utf-8")
    while True:
        time.sleep(1)


if sys.argv[1] == "--child":
    child(Path(sys.argv[2]))

marker = Path(sys.argv[1])
descendant = subprocess.Popen(
    [sys.executable, __file__, "--child", str(marker)],
    stdin=subprocess.DEVNULL,
)
marker.with_suffix(".child_pid").write_text(str(descendant.pid), encoding="utf-8")
deadline = time.monotonic() + 5
while not marker.with_suffix(".child_ready").exists():
    if time.monotonic() >= deadline:
        raise RuntimeError("descendant did not become ready")
    time.sleep(0.01)

chunk = b"x" * 65536
for _ in range(32):
    os.write(1, chunk)
    os.write(2, chunk)
marker.with_suffix(".noise_ready").write_text("ready", encoding="utf-8")
if sys.argv[2] == "exit":
    os.write(1, b'\n{"type":"thread.started","thread_id":"fake-thread"}\n')
    os.write(1, b'{"type":"item.completed","item":{"type":"agent_message","text":"done"}}\n')
    raise SystemExit(0)
while True:
    time.sleep(1)
"""


async def _wait_for_file(path: Path, *, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not path.exists():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError(f"timed out waiting for {path.name}")
        await asyncio.sleep(0.01)


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat = Path(f"/proc/{pid}/stat")
    if stat.exists():
        fields = stat.read_text(encoding="utf-8").split()
        return len(fields) < 3 or fields[2] != "Z"
    return True


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group regression")
def test_codex_transport_timeout_bounds_noise_and_terminates_descendant(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "fake_codex.py"
    executable.write_text(textwrap.dedent(_FAKE_CODEX), encoding="utf-8")
    marker = tmp_path / "provider"
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=(sys.executable, str(executable), str(marker), "hang"),
            resume_command=(sys.executable, str(executable), str(marker), "hang"),
        ),
        model="fake-model",
        model_effort=None,
    )
    turn = RenderedProviderTurn(
        step_name="noisy-timeout",
        turn_kind="producer",
        prompt_text="prompt",
        session=None,
        expected_response="raw_text",
        workspace_root=tmp_path,
    )

    async def run() -> None:
        task = asyncio.create_task(transport.run_turn(turn))
        await _wait_for_file(marker.with_suffix(".noise_ready"))
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(task, timeout=0.05)
        assert task.cancelled()

    asyncio.run(asyncio.wait_for(run(), timeout=12))

    child_pid = int(marker.with_suffix(".child_pid").read_text(encoding="utf-8"))
    assert marker.with_suffix(".terminated").read_text(encoding="utf-8") == "terminated"
    assert not _pid_is_running(child_pid)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group regression")
def test_codex_transport_reaps_pipe_holding_descendant_after_leader_exit(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "fake_codex.py"
    executable.write_text(textwrap.dedent(_FAKE_CODEX), encoding="utf-8")
    marker = tmp_path / "provider-exit"
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=(sys.executable, str(executable), str(marker), "exit"),
            resume_command=(sys.executable, str(executable), str(marker), "exit"),
        ),
        model="fake-model",
        model_effort=None,
    )
    turn = RenderedProviderTurn(
        step_name="noisy-leader-exit",
        turn_kind="producer",
        prompt_text="prompt",
        session=None,
        expected_response="raw_text",
        workspace_root=tmp_path,
    )

    result = asyncio.run(asyncio.wait_for(transport.run_turn(turn), timeout=5))

    assert result.raw_text == "done"
    child_pid = int(marker.with_suffix(".child_pid").read_text(encoding="utf-8"))
    assert marker.with_suffix(".terminated").read_text(encoding="utf-8") == "terminated"
    assert not _pid_is_running(child_pid)
