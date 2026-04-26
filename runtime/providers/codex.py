"""Runtime-backed Codex CLI provider."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from ...core.errors import ProviderExecutionError
from ...core.providers.models import LLMRequest, OutcomeResponse, ProducerRequest, ProducerResponse, VerifierRequest
from ...core.providers.parsing import parse_outcome_json
from ...core.providers.protocols import LLMProvider
from ...core.stores.protocols import SessionBinding
from ..config import ConfigError, ResolvedRuntimeConfig
from ._common import (
    build_session_binding,
    ensure_session_provider_match,
    format_subprocess_streams,
    render_verifier_input,
    require_prompt_text,
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


def parse_codex_exec_json(raw_stdout: str) -> tuple[str, str | None, dict[str, Any]]:
    """Parse Codex JSONL stdout into assistant text and canonical session data."""

    assistant_messages: list[str] = []
    parsed_line_count = 0
    malformed_line_count = 0
    session_id: str | None = None

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
            continue
        if event_type == "item.completed":
            item = payload.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                assistant_messages.append(item["text"])

    if parsed_line_count == 0:
        raise ProviderExecutionError("provider 'codex' returned unusable JSONL output.")
    if not assistant_messages:
        raise ProviderExecutionError("provider 'codex' did not return assistant text in JSONL output.")

    provider_metadata = {
        "assistant_message_count": len(assistant_messages),
        "jsonl_event_count": parsed_line_count,
        "malformed_jsonl_lines": malformed_line_count,
    }
    return "\n\n".join(assistant_messages), session_id, provider_metadata


class CodexProvider:
    """Concrete LLMProvider backed by the Codex CLI."""

    def __init__(self, config: ResolvedRuntimeConfig, commands: CodexCLICommand) -> None:
        self._commands = commands
        self._model = config.provider.codex.model
        self._model_effort = config.provider.codex.model_effort

    def run_producer(self, request: ProducerRequest) -> ProducerResponse:
        prompt_text = require_prompt_text(request.prompt, "codex", request.step_name)
        assistant_text, binding, metadata = self._run_turn(
            step_name=request.step_name,
            prompt_text=prompt_text,
            session=request.session,
        )
        return ProducerResponse(raw_output=assistant_text, session=binding, metadata=metadata)

    def run_verifier(self, request: VerifierRequest) -> OutcomeResponse:
        prompt_text = require_prompt_text(request.prompt, "codex", request.step_name)
        verifier_input = render_verifier_input(prompt_text, request.raw_output)
        assistant_text, binding, metadata = self._run_turn(
            step_name=request.step_name,
            prompt_text=verifier_input,
            session=request.session,
        )
        return OutcomeResponse(
            outcome=parse_outcome_json(assistant_text),
            session=binding,
            metadata=metadata,
        )

    def run_llm(self, request: LLMRequest) -> OutcomeResponse:
        prompt_text = require_prompt_text(request.prompt, "codex", request.step_name)
        assistant_text, binding, metadata = self._run_turn(
            step_name=request.step_name,
            prompt_text=prompt_text,
            session=request.session,
        )
        return OutcomeResponse(
            outcome=parse_outcome_json(assistant_text),
            session=binding,
            metadata=metadata,
        )

    def _run_turn(
        self,
        *,
        step_name: str,
        prompt_text: str,
        session: SessionBinding | None,
    ) -> tuple[str, SessionBinding | None, dict[str, Any]]:
        ensure_session_provider_match("codex", session)
        resume_session_id = _resumable_session_id("codex", session)

        if resume_session_id is None:
            command = list(self._commands.start_command)
        else:
            command = [*self._commands.resume_command, resume_session_id, "-"]

        completed = subprocess.run(
            command,
            input=prompt_text,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            streams = format_subprocess_streams(completed.stdout, completed.stderr)
            raise ProviderExecutionError(
                f"provider 'codex' failed while running step {step_name!r} "
                f"(exit code {completed.returncode}): {streams}"
            )

        assistant_text, resolved_session_id, provider_metadata = parse_codex_exec_json(completed.stdout)
        if resolved_session_id is None and resume_session_id is not None:
            resolved_session_id = resume_session_id
        if resolved_session_id is None and session is not None:
            raise ProviderExecutionError(
                f"provider 'codex' did not return a resumable session_id for step {step_name!r}."
            )

        binding = (
            build_session_binding(
                session,
                session_id=resolved_session_id,
                provider_name="codex",
                provider_metadata=provider_metadata,
                model=self._model,
                effort=self._model_effort,
            )
            if session is not None and resolved_session_id is not None
            else None
        )
        metadata = {
            "mode": "resume" if resume_session_id is not None else "start",
            "provider_metadata": dict(provider_metadata),
        }
        return assistant_text, binding, metadata


def build_codex_provider(config: ResolvedRuntimeConfig) -> LLMProvider:
    """Build the concrete Codex runtime provider."""

    return CodexProvider(config, resolve_codex_cli_commands(config))


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
