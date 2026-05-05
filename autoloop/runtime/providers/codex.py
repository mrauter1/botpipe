"""Runtime-backed Codex CLI transport."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from ...core.errors import ProviderExecutionError
from ...core.providers.models import TokenUsage
from ...core.providers.protocols import ProviderTransport
from ...core.providers.rendered import RenderedLLMProvider
from ...core.providers.turns import ProviderTurnResult, RenderedProviderTurn
from ...core.stores.protocols import SessionBinding
from ..config import ConfigError, ResolvedRuntimeConfig
from ._common import (
    build_session_binding,
    ensure_session_provider_match,
    extract_token_usage,
    format_subprocess_streams,
)


@dataclass(frozen=True, slots=True)
class CodexCLICommand:
    """Resolved Codex start/resume command prefixes."""

    start_command: tuple[str, ...]
    resume_command: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _CodexExecSurface:
    start_help: str
    resume_help: str

    @property
    def start_auto_flag(self) -> str | None:
        return _preferred_codex_auto_flag(self.start_help)

    @property
    def resume_auto_flag(self) -> str | None:
        return _preferred_codex_auto_flag(self.resume_help)

    @property
    def start_supports_model(self) -> bool:
        return "--model" in self.start_help or "-m, --model" in self.start_help

    @property
    def resume_supports_model(self) -> bool:
        return "--model" in self.resume_help or "-m, --model" in self.resume_help

    @property
    def start_supports_json(self) -> bool:
        return "--json" in self.start_help

    @property
    def resume_supports_json(self) -> bool:
        return "--json" in self.resume_help

    @property
    def start_supports_model_effort(self) -> bool:
        return "--model-effort" in self.start_help

    @property
    def resume_supports_model_effort(self) -> bool:
        return "--model-effort" in self.resume_help


def verify_codex_exec_capabilities() -> None:
    """Validate the installed Codex CLI surface."""

    _validate_codex_surface(_probe_codex_exec_surface(), require_model_effort=False)


def resolve_codex_cli_commands(config: ResolvedRuntimeConfig) -> CodexCLICommand:
    """Resolve the cached Codex CLI command prefixes for the given config."""

    surface = _probe_codex_exec_surface()
    require_model_effort = config.provider.codex.model_effort is not None
    _validate_codex_surface(surface, require_model_effort=require_model_effort)

    start_command = ["codex", "exec", "--json", surface.start_auto_flag or ""]
    resume_command = ["codex", "exec", "resume", "--json", surface.resume_auto_flag or ""]

    model = config.provider.codex.model
    if model:
        start_command.extend(["--model", model])
        resume_command.extend(["--model", model])

    model_effort = config.provider.codex.model_effort
    if model_effort:
        start_command.extend(["--model-effort", model_effort])
        resume_command.extend(["--model-effort", model_effort])

    return CodexCLICommand(
        start_command=tuple(arg for arg in start_command if arg),
        resume_command=tuple(arg for arg in resume_command if arg),
    )


def parse_codex_exec_json(raw_stdout: str) -> tuple[str, str | None, dict[str, Any], TokenUsage | None]:
    """Parse Codex JSONL stdout into assistant text and canonical session data."""

    assistant_messages: list[str] = []
    parsed_line_count = 0
    malformed_line_count = 0
    session_id: str | None = None
    usage = None

    for raw_line in raw_stdout.splitlines():
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError:
            malformed_line_count += 1
            continue

        if not isinstance(payload, dict):
            continue

        parsed_line_count += 1
        event_type = payload.get("type")
        if event_type == "thread.started":
            thread_id = payload.get("thread_id")
            if isinstance(thread_id, str) and thread_id:
                session_id = thread_id
        elif event_type == "item.completed":
            item = payload.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                assistant_messages.append(item["text"])
        resolved_usage = extract_token_usage(payload, source="codex")
        if resolved_usage is not None:
            usage = resolved_usage

    if parsed_line_count == 0:
        raise ProviderExecutionError("provider 'codex' returned unusable JSONL output.")
    if not assistant_messages:
        raise ProviderExecutionError("provider 'codex' did not return assistant text in JSONL output.")

    provider_metadata = {
        "assistant_message_count": len(assistant_messages),
        "jsonl_event_count": parsed_line_count,
        "malformed_jsonl_lines": malformed_line_count,
    }
    return "\n\n".join(assistant_messages), session_id, provider_metadata, usage


class CodexTransport(ProviderTransport):
    """Transport-only Codex CLI executor."""

    def __init__(self, *, commands: CodexCLICommand, model: str | None, model_effort: str | None) -> None:
        self._commands = commands
        self._model = model
        self._model_effort = model_effort

    def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult:
        ensure_session_provider_match("codex", turn.session)
        resume_session_id = _resumable_session_id("codex", turn.session)

        if resume_session_id is None:
            command = list(self._commands.start_command)
        else:
            command = [*self._commands.resume_command, resume_session_id, "-"]

        completed = subprocess.run(
            command,
            input=turn.prompt_text,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            streams = format_subprocess_streams(completed.stdout, completed.stderr)
            raise ProviderExecutionError(
                f"provider 'codex' failed while running step {turn.step_name!r} "
                f"(exit code {completed.returncode}): {streams}"
            )

        assistant_text, resolved_session_id, provider_metadata, usage = parse_codex_exec_json(completed.stdout)
        if resolved_session_id is None and resume_session_id is not None:
            resolved_session_id = resume_session_id
        if resolved_session_id is None and turn.session is not None:
            raise ProviderExecutionError(
                f"provider 'codex' did not return a resumable session_id for step {turn.step_name!r}."
            )

        binding = (
            build_session_binding(
                turn.session,
                session_id=resolved_session_id,
                provider_name="codex",
                provider_metadata=provider_metadata,
                model=self._model,
                effort=self._model_effort,
            )
            if turn.session is not None and resolved_session_id is not None
            else None
        )
        metadata = {
            "mode": "resume" if resume_session_id is not None else "start",
            "provider_metadata": dict(provider_metadata),
        }
        return ProviderTurnResult(raw_text=assistant_text, session=binding, metadata=metadata, usage=usage)

    async def run_turn_async(self, turn: RenderedProviderTurn) -> ProviderTurnResult:
        ensure_session_provider_match("codex", turn.session)
        resume_session_id = _resumable_session_id("codex", turn.session)

        if resume_session_id is None:
            command = list(self._commands.start_command)
        else:
            command = [*self._commands.resume_command, resume_session_id, "-"]

        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await process.communicate(turn.prompt_text.encode("utf-8"))
        stdout = stdout_bytes.decode("utf-8")
        stderr = stderr_bytes.decode("utf-8")
        if process.returncode != 0:
            streams = format_subprocess_streams(stdout, stderr)
            raise ProviderExecutionError(
                f"provider 'codex' failed while running step {turn.step_name!r} "
                f"(exit code {process.returncode}): {streams}"
            )

        assistant_text, resolved_session_id, provider_metadata, usage = parse_codex_exec_json(stdout)
        if resolved_session_id is None and resume_session_id is not None:
            resolved_session_id = resume_session_id
        if resolved_session_id is None and turn.session is not None:
            raise ProviderExecutionError(
                f"provider 'codex' did not return a resumable session_id for step {turn.step_name!r}."
            )

        binding = (
            build_session_binding(
                turn.session,
                session_id=resolved_session_id,
                provider_name="codex",
                provider_metadata=provider_metadata,
                model=self._model,
                effort=self._model_effort,
            )
            if turn.session is not None and resolved_session_id is not None
            else None
        )
        metadata = {
            "mode": "resume" if resume_session_id is not None else "start",
            "provider_metadata": dict(provider_metadata),
        }
        return ProviderTurnResult(raw_text=assistant_text, session=binding, metadata=metadata, usage=usage)


def build_codex_transport(config: ResolvedRuntimeConfig) -> CodexTransport:
    """Build the Codex runtime transport."""

    return CodexTransport(
        commands=resolve_codex_cli_commands(config),
        model=config.provider.codex.model,
        model_effort=config.provider.codex.model_effort,
    )


class CodexProvider(RenderedLLMProvider):
    """Compatibility semantic provider backed by CodexTransport."""

    def __init__(self, config: ResolvedRuntimeConfig, commands: CodexCLICommand | None = None) -> None:
        super().__init__(
            CodexTransport(
                commands=commands or resolve_codex_cli_commands(config),
                model=config.provider.codex.model,
                model_effort=config.provider.codex.model_effort,
            )
        )


def build_codex_provider(config: ResolvedRuntimeConfig) -> CodexProvider:
    """Build the compatibility Codex semantic provider wrapper."""

    return CodexProvider(config)


@lru_cache(maxsize=1)
def _probe_codex_exec_surface() -> _CodexExecSurface:
    if shutil.which("codex") is None:
        raise ConfigError("provider 'codex' is unavailable in this environment: the 'codex' CLI was not found on PATH.")

    start_help = _run_help_command(["codex", "exec", "--help"], provider_name="codex")
    resume_help = _run_help_command(["codex", "exec", "resume", "--help"], provider_name="codex")
    return _CodexExecSurface(start_help=start_help, resume_help=resume_help)


def _validate_codex_surface(surface: _CodexExecSurface, *, require_model_effort: bool) -> None:
    if not surface.start_supports_json:
        raise ConfigError("provider 'codex' requires 'codex exec --json' support, but '--json' is unavailable.")
    if not surface.resume_supports_json:
        raise ConfigError(
            "provider 'codex' requires 'codex exec resume --json' support, but '--json' is unavailable."
        )
    if not surface.start_supports_model:
        raise ConfigError("provider 'codex' requires 'codex exec --model' support, but '--model' is unavailable.")
    if not surface.resume_supports_model:
        raise ConfigError(
            "provider 'codex' requires 'codex exec resume --model' support, but '--model' is unavailable."
        )
    if surface.start_auto_flag is None:
        raise ConfigError(
            "provider 'codex' requires either '--dangerously-bypass-approvals-and-sandbox' or '--full-auto' "
            "on 'codex exec'."
        )
    if surface.resume_auto_flag is None:
        raise ConfigError(
            "provider 'codex' requires either '--dangerously-bypass-approvals-and-sandbox' or '--full-auto' "
            "on 'codex exec resume'."
        )
    if require_model_effort and not surface.start_supports_model_effort:
        raise ConfigError(
            "provider 'codex' cannot honor provider.codex.model_effort because 'codex exec' does not support "
            "'--model-effort'."
        )
    if require_model_effort and not surface.resume_supports_model_effort:
        raise ConfigError(
            "provider 'codex' cannot honor provider.codex.model_effort because 'codex exec resume' does not support "
            "'--model-effort'."
        )


def _preferred_codex_auto_flag(help_text: str) -> str | None:
    if "--dangerously-bypass-approvals-and-sandbox" in help_text:
        return "--dangerously-bypass-approvals-and-sandbox"
    if "--full-auto" in help_text:
        return "--full-auto"
    return None


def _run_help_command(command: list[str], *, provider_name: str) -> str:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        streams = format_subprocess_streams(completed.stdout, completed.stderr)
        raise ConfigError(
            f"provider '{provider_name}' capability verification failed while running "
            f"{' '.join(command)!r}: {streams}"
        )
    return "\n".join(part for part in (completed.stdout, completed.stderr) if part)


def _resumable_session_id(provider_name: str, session: SessionBinding | None) -> str | None:
    if session is None:
        return None
    seen_provider = session.metadata.get("provider")
    if seen_provider == provider_name and session.session_id:
        return session.session_id
    return None
