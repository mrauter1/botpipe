"""Opt-in contract test against the current native Codex executable.

The executable talks only to the local Responses fixture below. No Codex login,
OpenAI credential, external network, or model charge is involved.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import os
import shlex
import shutil
import signal
import subprocess
import threading
import time
import uuid
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from pydantic import BaseModel

from botpipe import Artifact, Botpipe, Provider
from botpipe.codex_appserver import CodexAppServerAdapter, CodexProtocolError
from botpipe.errors import UncertainOperation
from botpipe.policy import NetworkMode, Policy, SandboxMode
from botpipe.providers import CodexProvider, ProviderRequest, ProviderTimeoutError

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


class NativeAnswer(BaseModel):
    ok: bool


class ResponsesFixture(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), ResponsesHandler)
        self.requests: list[dict] = []
        self.authorizations: list[str | None] = []
        self._next_function: tuple[str, str] | None = None

    def queue_exec(self, call_id: str, command: str) -> None:
        assert self._next_function is None
        self._next_function = (call_id, command)

    def diagnostics(self) -> str:
        return json.dumps([
            {
                "tools": [
                    {"name": tool.get("name", tool.get("type")),
                     "arguments": sorted(tool.get("parameters", {}).get("properties", {}))}
                    for tool in request.get("tools", [])
                ],
                "outputs": [item for item in request.get("input", [])
                            if item.get("type") == "function_call_output"],
            }
            for request in self.requests
        ], indent=2)


class ResponsesHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        pass

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"data":[]}')

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if self.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        request = json.loads(body)
        self.server.requests.append(request)
        self.server.authorizations.append(self.headers.get("Authorization"))
        index = len(self.server.requests)
        queued = self.server._next_function
        if queued is not None:
            self.server._next_function = None
            call_id, command = queued
            item = {
                "type": "function_call",
                "call_id": call_id,
                "name": "exec_command",
                "arguments": json.dumps(
                    {"cmd": command, "login": False, "yield_time_ms": 10_000}
                ),
            }
            self._events(
                [
                    {"type": "response.created", "response": {"id": f"response_{index}"}},
                    {"type": "response.output_item.done", "output_index": 0, "item": item},
                    {
                        "type": "response.completed",
                        "response": {
                            "id": f"response_{index}",
                            "status": "completed",
                            "output": [item],
                            "usage": self._usage(),
                        },
                    },
                ]
            )
            return

        text = '{"ok":true}'
        message = {
            "id": f"message_{index}",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        }
        response = {
            "id": f"response_{index}",
            "object": "response",
            "status": "completed",
            "model": request.get("model", "fixture-model"),
            "output": [message],
            "usage": self._usage(),
        }
        self._events(
            [
                {
                    "type": "response.created",
                    "response": {**response, "status": "in_progress", "output": []},
                },
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": {**message, "status": "in_progress", "content": []},
                },
                {
                    "type": "response.content_part.added",
                    "item_id": message["id"],
                    "output_index": 0,
                    "content_index": 0,
                    "part": {"type": "output_text", "text": "", "annotations": []},
                },
                {
                    "type": "response.output_text.delta",
                    "item_id": message["id"],
                    "output_index": 0,
                    "content_index": 0,
                    "delta": text,
                },
                {
                    "type": "response.output_text.done",
                    "item_id": message["id"],
                    "output_index": 0,
                    "content_index": 0,
                    "text": text,
                },
                {"type": "response.output_item.done", "output_index": 0, "item": message},
                {"type": "response.completed", "response": response},
            ]
        )

    @staticmethod
    def _usage() -> dict:
        return {
            "input_tokens": 20,
            "output_tokens": 4,
            "total_tokens": 24,
            "input_tokens_details": {"cached_tokens": 0},
        }

    def _events(self, events: list[dict]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for event in events:
            self.wfile.write(
                f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode()
            )
        self.wfile.flush()


def native_binary() -> Path:
    configured = os.environ.get("BOTPIPE_NATIVE_CODEX")
    if not configured:
        pytest.skip("set BOTPIPE_NATIVE_CODEX=codex to run native Codex contracts")
    # CI uses the simple value `codex`; a full path is convenient locally.
    resolved = shutil.which(configured) if len(shlex.split(configured)) == 1 else None
    if resolved is None:
        candidate = Path(configured).expanduser()
        if not candidate.is_file():
            pytest.fail(f"BOTPIPE_NATIVE_CODEX does not resolve to an executable: {configured}")
        resolved = str(candidate.resolve())
    return Path(resolved)


@pytest.fixture
def native(tmp_path: Path):
    binary = native_binary()
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    if os.name == "nt":
        subprocess.run(
            [str(binary), "sandbox", "setup", "--elevated", "--current-user",
             "--codex-home", str(codex_home)],
            check=True,
            timeout=120,
        )
    server = ResponsesFixture()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    provider = (
        '{name="Botpipe local fixture", '
        f'base_url="http://127.0.0.1:{server.server_port}/v1", '
        'wire_api="responses", requires_openai_auth=false}'
    )
    client = CodexAppServerAdapter(
        (
            str(binary),
            "-c",
            'model_provider="botpipe_fixture"',
            "-c",
            f"model_providers.botpipe_fixture={provider}",
            "app-server",
            "--listen",
            "stdio://",
        ),
        env={
            "CODEX_HOME": str(codex_home),
            "OPENAI_API_KEY": "",
            "CODEX_API_KEY": "",
        },
        state_dir=tmp_path / "probe-state",
        interrupt_grace_seconds=1,
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    try:
        yield client, server, workspace
    finally:
        client.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def native_request(
    root: Path,
    *,
    operation_id: str,
    preset: str,
    prompt: str,
    tools: tuple[str, ...] | None,
    session_id: str | None = None,
    timeout: float = 30,
) -> ProviderRequest:
    return ProviderRequest(
        operation_id=operation_id,
        prompt=prompt,
        workspace=root,
        session_id=session_id,
        output_schema=OUTPUT_SCHEMA,
        policy=Policy(
            model="gpt-5.4",
            sandbox_mode=(
                SandboxMode.READ_ONLY if preset in {"query", "generate"} else SandboxMode.WORKSPACE_WRITE
            ),
            network=NetworkMode.NONE,
        ),
        artifacts={},
        receipt_dir=root.parent / "receipts",
        timeout=timeout,
        preset=preset,
        tools=tools,
    )


def _start_or_skip_local_sandbox(
    client: CodexAppServerAdapter, request: ProviderRequest
):
    try:
        return client.start_turn(request)
    except (CodexProtocolError, UncertainOperation) as exc:
        # Some nested Linux containers prohibit the user/network namespaces
        # required by Codex's bwrap sandbox. Hosted CI runners do not.
        if (
            not os.environ.get("CI")
            and "bwrap:" in str(exc)
            and "Operation not permitted" in str(exc)
        ):
            pytest.skip(f"host cannot start the native Codex sandbox: {exc}")
        raise


def test_latest_native_default_session_presets_and_read_only_enforcement(native) -> None:
    client, server, workspace = native
    discovered = client.probe()
    assert discovered.version.startswith("codex-cli ")
    assert discovered.supports_turn_sandbox
    assert discovered.supports_interrupt
    assert discovered.presets["run"].available
    assert discovered.presets["query"].available
    assert discovered.presets["generate"].available

    runtime = Botpipe(
        workspace,
        provider=CodexProvider(adapter=client),
        state_dir=workspace.parent / "runtime-state",
    )
    sdk = Provider(runtime=runtime, model="gpt-5.4", workspace=workspace)
    report = workspace / "native-report.md"
    if os.name == "nt":
        windows_report = str(report).replace("'", "''")
        write_command = (
            f"Set-Content -LiteralPath '{windows_report}' "
            "-Value 'native artifact' -NoNewline"
        )
    else:
        write_command = f"printf %s 'native artifact' > {shlex.quote(str(report))}"
    server.queue_exec("run-write", write_command)
    try:
        default = sdk.run(
            "Write the requested report, then return the fixed response.",
            returns=NativeAnswer,
            writes=(Artifact.md(report, name="report", required=True),),
        )
    except (CodexProtocolError, UncertainOperation) as exc:
        # Runtime restores provider exceptions for the public SDK path.
        if (
            not os.environ.get("CI")
            and "bwrap:" in str(exc)
            and "Operation not permitted" in str(exc)
        ):
            pytest.skip(f"host cannot start the native Codex sandbox: {exc}")
        raise
    finally:
        if not report.exists():
            print("Native fixture diagnostics:", server.diagnostics())
    assert default.value == NativeAnswer(ok=True)
    assert report.read_text(encoding="utf-8") == "native artifact"
    assert default.artifacts.report.read_text() == "native artifact"
    assert default.artifacts.report.path != report
    assert default.metadata["probe_hash"] == discovered.probe_hash
    assert default.metadata["enforcement"]["approval_policy"] == "never"
    assert default.metadata["enforcement"]["sandbox_policy"] == {
        "type": "workspaceWrite",
        "writableRoots": [str(workspace.resolve())],
        "networkAccess": False,
    }

    forbidden = workspace / "query-must-not-write.txt"
    if os.name == "nt":
        windows_target = str(forbidden).replace("'", "''")
        command = f"Set-Content -LiteralPath '{windows_target}' -Value 'changed'"
    else:
        command = f"printf %s changed > {shlex.quote(str(forbidden))}"
    server.queue_exec("query-write", command)
    before_query = {
        path.relative_to(workspace): path.read_bytes()
        for path in workspace.rglob("*")
        if path.is_file()
    }
    query = sdk.query(
        "Try the requested write, then return the fixed response.",
        returns=NativeAnswer,
        tools=["shell"],
    )
    assert query.value == NativeAnswer(ok=True)
    assert not forbidden.exists()
    assert {
        path.relative_to(workspace): path.read_bytes()
        for path in workspace.rglob("*")
        if path.is_file()
    } == before_query
    assert query.metadata["enforcement"]["sandbox"] == "codex:read-only"
    assert query.metadata["enforcement"]["sandbox_policy"] == {
        "type": "readOnly",
        "networkAccess": False,
    }
    assert query.metadata["enforcement"]["tools"] == {
        "mode": "allowlist",
        "allowed": ["shell"],
        "disabled_via": "codex-features",
    }

    generated = sdk.generate(
        "Return the fixed response without tools.",
        returns=NativeAnswer,
        allowed_tools=[],
    )
    assert generated.value == NativeAnswer(ok=True)
    assert {
        default.metadata["thread_id"],
        query.metadata["thread_id"],
        generated.metadata["thread_id"],
    } == {default.metadata["thread_id"]}
    enforcement = generated.metadata["enforcement"]
    assert enforcement["tools"]["allowed"] == []
    assert enforcement["mcp_servers"] == {}
    assert enforcement["feature_overrides"]
    assert not any(enforcement["feature_overrides"].values())
    assert enforcement["audit"] == "no-tool-calls-observed"

    # Run and query each consume an exec request plus its follow-up; generate
    # needs one response without tools.
    assert len(server.requests) == 5
    assert server.authorizations == [None] * 5
    function_outputs = [
        item
        for item in server.requests[3].get("input", [])
        if item.get("type") == "function_call_output"
        and item.get("call_id") == "query-write"
    ]
    assert len(function_outputs) == 1
    output = function_outputs[0]["output"].lower()
    assert any(word in output for word in ("denied", "read-only", "permission", "not permitted")), output
    report.write_text("later workspace edit", encoding="utf-8")
    assert default.artifacts.report.read_text() == "native artifact"


def _process_exists(process_id: int) -> bool:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(0x1000, False, process_id)
        if not handle:
            return False
        try:
            status = wintypes.DWORD()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(status))) and status.value == 259
        finally:
            kernel32.CloseHandle(handle)
    result = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(process_id)],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return False
    # A zombie has terminated and cannot perform more edits; kill(0) alone
    # reports it as alive until its parent reaps it, especially on macOS.
    return any(not state.lstrip().startswith("Z") for state in result.stdout.splitlines())


def _process_diagnostic(process_id: int) -> str:
    if os.name == "nt":
        return f"Windows process {process_id} is still active"
    result = subprocess.run(
        ["ps", "-o", "pid=,ppid=,pgid=,state=,command=", "-p", str(process_id)],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    return (result.stdout + result.stderr).strip()


def _marked_processes(marker: str) -> set[int]:
    """Find host PIDs, since a sandbox shell's $$ can be namespace-local."""
    result = subprocess.run(
        ["ps", "-ww", "-axo", "pid=,stat=,command="],
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    )
    found = set()
    for line in result.stdout.splitlines():
        fields = line.split(None, 2)
        if len(fields) != 3 or marker not in fields[2] or fields[1].startswith("Z"):
            continue
        process_id = int(fields[0])
        if process_id > 1 and process_id not in {os.getpid(), os.getppid()}:
            found.add(process_id)
    return found


@pytest.mark.parametrize("interruption", ["timeout", "cancel"])
def test_latest_native_interruption_cleans_up_long_running_shell_process(
    native, interruption: str
) -> None:
    client, server, workspace = native
    marker = f"BOTPIPE_SLEEPER_{uuid.uuid4().hex}"
    readiness = workspace / f"{marker}.ready"
    if os.name == "nt":
        windows_ready = str(readiness).replace("'", "''")
        command = (
            f"Set-Content -LiteralPath '{windows_ready}' "
            '-Value "$PID READY" -NoNewline -Encoding ascii; while ($true) {}'
        )
    else:
        # The file is a readiness barrier, not a namespace-local PID source.
        command = f"printf %s READY > {shlex.quote(str(readiness))}; while :; do :; done"
    server.queue_exec("native-sleeper", command)
    call = native_request(
        workspace,
        operation_id="native-timeout-cleanup",
        preset="run",
        prompt="Run the requested sleeper command.",
        tools=("shell",),
        timeout=8,
    )

    observed: set[int] = set()
    monitor_errors: list[Exception] = []
    stop_monitor = threading.Event()
    remaining_at_return: set[int] | None = None
    cancellation_elapsed = 0.0

    def ready_seen() -> bool:
        if not readiness.is_file():
            return False
        value = readiness.read_text(encoding="ascii")
        if os.name == "nt":
            process_text, _, status = value.partition(" ")
            if status != "READY":
                return False
            process_id = int(process_text)
            assert process_id > 1 and process_id not in {os.getpid(), os.getppid()}
            observed.add(process_id)
            return True
        return value == "READY"

    def survivors() -> set[int]:
        if os.name == "nt":
            return {pid for pid in observed if _process_exists(pid)}
        return _marked_processes(marker)

    async def cancel_public_call() -> None:
        nonlocal remaining_at_return, cancellation_elapsed
        with Botpipe(
            workspace,
            provider=CodexProvider(adapter=client),
            state_dir=workspace.parent / "runtime-state",
        ) as runtime:
            sdk = Provider(runtime=runtime, model="gpt-5.4", workspace=workspace)
            task = asyncio.create_task(sdk.arun(
                "Run the requested sleeper command.",
                tools=("shell",),
                timeout=30,
            ))
            try:
                deadline = time.monotonic() + 30
                while not ready_seen() or not observed:
                    if task.done():
                        print("Native fixture diagnostics:", server.diagnostics())
                        await task
                        pytest.fail("native shell returned before cancellation")
                    assert time.monotonic() < deadline, "native shell never started"
                    await asyncio.sleep(0.02)
                assert survivors(), "native shell exited before cancellation"
                cancelled_at = time.monotonic()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                cancellation_elapsed = time.monotonic() - cancelled_at
                # Check before closing the runtime: cancellation itself must
                # join process cleanup, without help from context teardown.
                remaining_at_return = survivors()
            finally:
                if not task.done():
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task

    def monitor() -> None:
        try:
            while not stop_monitor.is_set():
                observed.update(_marked_processes(marker))
                stop_monitor.wait(0.02)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            monitor_errors.append(exc)

    monitor_thread = None
    if os.name != "nt":
        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()
    try:
        if interruption == "timeout":
            with pytest.raises(ProviderTimeoutError):
                _start_or_skip_local_sandbox(client, call)
                print("Native fixture diagnostics:", server.diagnostics())
        else:
            try:
                asyncio.run(cancel_public_call())
            except (CodexProtocolError, UncertainOperation) as exc:
                if (
                    not os.environ.get("CI")
                    and "bwrap:" in str(exc)
                    and "Operation not permitted" in str(exc)
                ):
                    pytest.skip(f"host cannot start the native Codex sandbox: {exc}")
                raise
    finally:
        stop_monitor.set()
        if monitor_thread is not None:
            monitor_thread.join(timeout=6)
            assert not monitor_thread.is_alive()
    assert not monitor_errors
    assert ready_seen(), f"native shell never wrote its readiness file: {server.diagnostics()}"
    assert observed, "native shell never appeared in the host process table"

    deadline = time.monotonic() + 5
    while survivors() and time.monotonic() < deadline:
        time.sleep(0.05)
    remaining = survivors()
    diagnostics = [_process_diagnostic(pid) for pid in remaining]
    for process_id in remaining:
        # Recheck the marker before cleanup, so a reused host PID cannot target
        # an unrelated process. Windows's reported $PID is already a host PID.
        if os.name != "nt" and process_id not in _marked_processes(marker):
            continue
        try:
            os.kill(process_id, signal.SIGTERM if os.name == "nt" else signal.SIGKILL)
        except (OSError, ValueError):
            pass
    assert not remaining, f"native Codex processes survived timeout cleanup: {diagnostics}"
    if interruption == "cancel":
        assert not remaining_at_return, f"arun returned before cleanup: {remaining_at_return}"
        assert cancellation_elapsed <= 6, "cancellation exceeded interrupt grace plus 5 seconds"
