"""Opt-in contract test against the current native Codex executable.

The executable talks only to the local Responses fixture below. No Codex login,
OpenAI credential, external network, or model charge is involved.
"""

from __future__ import annotations

import gzip
import json
import os
import shlex
import shutil
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from pydantic import BaseModel

from botpipe import Botpipe, Provider
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
    server = ResponsesFixture()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
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
    assert discovered.supports_output_schema
    assert discovered.presets["run"].available
    assert discovered.presets["query"].available
    assert discovered.presets["generate"].available

    runtime = Botpipe(
        workspace,
        provider=CodexProvider(adapter=client),
        state_dir=workspace.parent / "runtime-state",
    )
    sdk = Provider(runtime=runtime, model="gpt-5.4", workspace=workspace)
    try:
        default = sdk.run("Return the fixed response.", returns=NativeAnswer)
    except (CodexProtocolError, UncertainOperation) as exc:
        # Runtime restores provider exceptions for the public SDK path.
        if (
            not os.environ.get("CI")
            and "bwrap:" in str(exc)
            and "Operation not permitted" in str(exc)
        ):
            pytest.skip(f"host cannot start the native Codex sandbox: {exc}")
        raise
    assert default.value == NativeAnswer(ok=True)
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
        command = (
            f"{shlex.quote(sys.executable)} -c "
            + shlex.quote(
                "from pathlib import Path; "
                f"Path({str(forbidden)!r}).write_text('changed', encoding='utf-8')"
            )
        )
    server.queue_exec("query-write", command)
    query = sdk.query(
        "Try the requested write, then return the fixed response.",
        returns=NativeAnswer,
        tools=["shell"],
    )
    assert query.value == NativeAnswer(ok=True)
    assert not forbidden.exists()
    assert query.metadata["enforcement"]["sandbox_policy"] == {
        "type": "readOnly",
        "networkAccess": False,
    }
    assert query.metadata["enforcement"]["allowed_tools"] == ["shell"]

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
    assert enforcement["allowed_tools"] == []
    assert enforcement["mcp_servers"] == {}
    assert enforcement["feature_overrides"]
    assert not any(enforcement["feature_overrides"].values())

    # First response call is run, the query consumes an exec request plus its
    # follow-up, and the last response call is the tool-free generate turn.
    assert len(server.requests) == 4
    assert server.authorizations == [None, None, None, None]
    assert server.requests[-1].get("tools") == []
    function_outputs = [
        item
        for item in server.requests[2].get("input", [])
        if item.get("type") == "function_call_output"
        and item.get("call_id") == "query-write"
    ]
    assert len(function_outputs) == 1
    output = function_outputs[0]["output"].lower()
    assert any(word in output for word in ("denied", "read-only", "permission")), output


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
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_latest_native_timeout_cleans_up_long_running_shell_process(native) -> None:
    client, server, workspace = native
    pid_file = workspace / "native-sleeper.pid"
    if os.name == "nt":
        windows_pid = str(pid_file).replace("'", "''")
        command = (
            f"Set-Content -LiteralPath '{windows_pid}' -Value $PID -NoNewline; "
            "Start-Sleep -Seconds 60"
        )
    else:
        program = (
            "import os,pathlib,sys,time; "
            "pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(60)"
        )
        command = (
            f"{shlex.quote(sys.executable)} -c {shlex.quote(program)} "
            f"{shlex.quote(str(pid_file))}"
        )
    server.queue_exec("native-sleeper", command)
    call = native_request(
        workspace,
        operation_id="native-timeout-cleanup",
        preset="run",
        prompt="Run the requested sleeper command.",
        tools=("shell",),
        timeout=2,
    )

    try:
        with pytest.raises(ProviderTimeoutError):
            _start_or_skip_local_sandbox(client, call)
    finally:
        # A failed assertion must not leave the diagnostic sleeper behind.
        if pid_file.exists():
            process_id = int(pid_file.read_text(encoding="utf-8").strip())
        else:
            process_id = None
    assert process_id is not None, "native shell never launched the sleeper"
    deadline = time.monotonic() + 5
    while _process_exists(process_id) and time.monotonic() < deadline:
        time.sleep(0.05)
    if _process_exists(process_id):
        try:
            os.kill(process_id, signal.SIGKILL)
        except (OSError, ValueError):
            pass
        pytest.fail(f"native Codex sleeper {process_id} survived timeout cleanup")
