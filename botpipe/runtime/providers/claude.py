"""Runtime-backed Claude Code CLI transport."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import json
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from ...core.errors import FailureContext, ProviderExecutionError
from ...core.provider_policy import ProviderPolicyEmission, ProviderPolicyValidationConfig
from ...core.providers.models import TokenUsage
from ...core.providers.protocols import ProviderTransport
from ...core.providers.rendered import RenderedLLMProvider
from ...core.providers.turns import ProviderTurnResult, RenderedProviderTurn
from ..config import ClaudeProviderConfig, ConfigError, ResolvedRuntimeConfig
from ._common import (
    build_session_binding,
    communicate_text_subprocess,
    emit_turn_policy,
    ensure_session_provider_match,
    extract_token_usage,
    format_subprocess_streams,
    merge_subprocess_env,
    provider_metadata_with_policy,
    resumable_session_id,
    run_text_subprocess,
    structured_output_metadata,
)
from .claude_policy import ClaudeCapabilities, ClaudePolicyEmitter


@dataclass(frozen=True, slots=True)
class _ClaudeHelpSurface:
    help_text: str

    @property
    def supports_print(self) -> bool:
        return "--print" in self.help_text or "-p" in self.help_text

    @property
    def supports_output_format(self) -> bool:
        return "--output-format" in self.help_text

    @property
    def supports_resume(self) -> bool:
        return "--resume" in self.help_text or "-r" in self.help_text

    @property
    def supports_model(self) -> bool:
        return "--model" in self.help_text

    @property
    def supports_allowed_tools(self) -> bool:
        return "--allowedTools" in self.help_text

    @property
    def supports_bypass_permissions(self) -> bool:
        return "--dangerously-skip-permissions" in self.help_text

    @property
    def supports_effort(self) -> bool:
        return "--effort" in self.help_text

    @property
    def supports_settings(self) -> bool:
        return "--settings" in self.help_text

    @property
    def supports_add_dir(self) -> bool:
        return "--add-dir" in self.help_text


def verify_claude_code_capabilities(config: ClaudeProviderConfig | None = None) -> None:
    """Validate the installed Claude Code CLI surface."""

    _validate_claude_surface(_probe_claude_help_surface(), config=config)


def claude_permission_args(config: ClaudeProviderConfig) -> list[str]:
    """Translate the configured permission strategy into Claude CLI arguments."""

    if config.permission_strategy == "inherit":
        return []
    if config.permission_strategy == "allow_core_tools":
        return ["--allowedTools", "Read,Write,Edit,Glob,Grep,Bash"]
    if config.permission_strategy == "bypass":
        return ["--dangerously-skip-permissions"]
    raise ConfigError(
        "provider.claude.permission_strategy must be one of: allow_core_tools, bypass, inherit."
    )


def parse_claude_exec_json(raw_stdout: str) -> tuple[str, str | None, dict[str, Any], TokenUsage | None]:
    """Parse Claude JSON stdout into result text and canonical session data."""

    try:
        payload = json.loads(raw_stdout)
    except json.JSONDecodeError as exc:
        raise _adapter_output_error(f"provider 'claude' returned malformed JSON output: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise ProviderExecutionError("provider 'claude' must return a JSON object.")

    result = payload.pop("result", None)
    if not isinstance(result, str):
        raise ProviderExecutionError("provider 'claude' JSON output must contain a string 'result'.")

    session_id = payload.pop("session_id", None)
    if session_id is not None and not isinstance(session_id, str):
        raise ProviderExecutionError("provider 'claude' JSON field 'session_id' must be a string when provided.")

    provider_metadata = dict(payload)
    return result, session_id, provider_metadata, extract_token_usage(provider_metadata, source="claude")


def _adapter_output_error(message: str) -> ProviderExecutionError:
    return ProviderExecutionError(
        message,
        failure_context=FailureContext(
            kind="malformed_provider_output",
            step_name="",
            provider_attributable=True,
            details={"error": message, "provider_failure_stage": "adapter_output"},
        ),
        retry_kind="malformed_provider_output",
    )


class ClaudeTransport(ProviderTransport):
    """Transport-only Claude CLI executor."""

    def __init__(
        self,
        *,
        config: ClaudeProviderConfig,
        validation: ProviderPolicyValidationConfig | None = None,
        capabilities: ClaudeCapabilities | None = None,
    ) -> None:
        self._config = config
        self._validation = validation or ProviderPolicyValidationConfig()
        self._emitter = ClaudePolicyEmitter(capabilities=capabilities)

    async def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult:
        ensure_session_provider_match("claude", turn.session)
        resume_session_id = resumable_session_id("claude", turn.session)
        emission, command_args, model, effort = _prepare_turn_command(
            turn,
            config=self._config,
            emitter=self._emitter,
            validation=self._validation,
        )
        structured_output = _structured_output_fallback(turn)
        subprocess_env, subprocess_cwd = _claude_subprocess_options(turn, emission)
        command = ["claude"]
        if resume_session_id is not None:
            command.extend(["--resume", resume_session_id])
        command.extend(["-p", turn.prompt_text, "--output-format", "json"])
        command.extend(command_args)

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=subprocess_env,
            cwd=str(subprocess_cwd) if subprocess_cwd is not None else None,
        )
        stdout, stderr = await communicate_text_subprocess(process)
        if process.returncode != 0:
            streams = format_subprocess_streams(stdout, stderr)
            raise ProviderExecutionError(
                f"provider 'claude' failed while running step {turn.step_name!r} "
                f"(exit code {process.returncode}): {streams}"
            )

        result_text, resolved_session_id, provider_metadata, usage = parse_claude_exec_json(stdout)
        if emission is not None:
            provider_metadata = provider_metadata_with_policy(provider_metadata, emission=emission)
        return _build_claude_result(
            turn=turn,
            resume_session_id=resume_session_id,
            resolved_session_id=resolved_session_id,
            provider_metadata=provider_metadata,
            usage=usage,
            result_text=result_text,
            model=model,
            effort=effort,
            structured_output=structured_output,
        )


def build_claude_transport(config: ResolvedRuntimeConfig) -> ClaudeTransport:
    """Build the Claude runtime transport."""

    verify_claude_code_capabilities(config.provider.claude)
    return ClaudeTransport(
        config=config.provider.claude,
        validation=config.provider_policy.validation,
    )


def build_claude_operation_executor(
    config: ResolvedRuntimeConfig,
) -> Callable[[RenderedProviderTurn], ProviderTurnResult]:
    """Build the explicit sync operation executor for compatibility helpers."""

    verify_claude_code_capabilities(config.provider.claude)
    provider_config = config.provider.claude

    def execute(turn: RenderedProviderTurn) -> ProviderTurnResult:
        ensure_session_provider_match("claude", turn.session)
        resume_session_id = resumable_session_id("claude", turn.session)
        emission, command_args, model, effort = _prepare_turn_command(
            turn,
            config=provider_config,
            emitter=ClaudePolicyEmitter(),
            validation=config.provider_policy.validation,
        )
        structured_output = _structured_output_fallback(turn)
        subprocess_env, subprocess_cwd = _claude_subprocess_options(turn, emission)
        command = ["claude"]
        if resume_session_id is not None:
            command.extend(["--resume", resume_session_id])
        command.extend(["-p", turn.prompt_text, "--output-format", "json"])
        command.extend(command_args)
        stdout, stderr, returncode = run_text_subprocess(
            command,
            env=subprocess_env,
            cwd=subprocess_cwd,
        )
        if returncode != 0:
            streams = format_subprocess_streams(stdout, stderr)
            raise ProviderExecutionError(
                f"provider 'claude' failed while running step {turn.step_name!r} "
                f"(exit code {returncode}): {streams}"
            )
        result_text, resolved_session_id, provider_metadata, usage = parse_claude_exec_json(stdout)
        if emission is not None:
            provider_metadata = provider_metadata_with_policy(provider_metadata, emission=emission)
        return _build_claude_result(
            turn=turn,
            resume_session_id=resume_session_id,
            resolved_session_id=resolved_session_id,
            provider_metadata=provider_metadata,
            usage=usage,
            result_text=result_text,
            model=model,
            effort=effort,
            structured_output=structured_output,
        )

    return execute


class ClaudeProvider(RenderedLLMProvider):
    """Compatibility semantic provider backed by ClaudeTransport."""

    def __init__(self, config: ResolvedRuntimeConfig) -> None:
        super().__init__(
            build_claude_transport(config),
            operation_executor=build_claude_operation_executor(config),
        )


def build_claude_provider(config: ResolvedRuntimeConfig) -> ClaudeProvider:
    """Build the compatibility Claude semantic provider wrapper."""

    return ClaudeProvider(config)


def _build_claude_result(
    *,
    turn: RenderedProviderTurn,
    resume_session_id: str | None,
    resolved_session_id: str | None,
    provider_metadata: dict[str, Any],
    usage: TokenUsage | None,
    result_text: str,
    model: str | None,
    effort: str | None,
    structured_output: dict[str, Any] | None,
) -> ProviderTurnResult:
    if resolved_session_id is None and resume_session_id is not None:
        resolved_session_id = resume_session_id
    if resolved_session_id is None and turn.session is not None:
        raise ProviderExecutionError(
            f"provider 'claude' did not return a resumable session_id for step {turn.step_name!r}."
        )

    binding = (
        build_session_binding(
            turn.session,
            session_id=resolved_session_id,
            provider_name="claude",
            provider_metadata=provider_metadata,
            model=model,
            effort=effort,
        )
        if turn.session is not None and resolved_session_id is not None
        else None
    )
    metadata = {
        "mode": "resume" if resume_session_id is not None else "start",
        "provider_metadata": dict(provider_metadata),
    }
    if structured_output is not None:
        metadata["structured_output"] = dict(structured_output)
    return ProviderTurnResult(raw_text=result_text, session=binding, metadata=metadata, usage=usage)


def _structured_output_fallback(turn: RenderedProviderTurn) -> dict[str, Any] | None:
    if turn.response_schema is None:
        return None
    return structured_output_metadata(
        provider_name="claude",
        delivery_mode="prompt_only",
        reason="backend_does_not_support_output_schema",
    )


@lru_cache(maxsize=1)
def _probe_claude_help_surface() -> _ClaudeHelpSurface:
    if shutil.which("claude") is None:
        raise ConfigError(
            "provider 'claude' is unavailable in this environment: the 'claude' CLI was not found on PATH."
        )

    completed = subprocess.run(["claude", "--help"], text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        streams = format_subprocess_streams(completed.stdout, completed.stderr)
        raise ConfigError(
            f"provider 'claude' capability verification failed while running 'claude --help': {streams}"
        )
    help_text = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    return _ClaudeHelpSurface(help_text=help_text)


def _validate_claude_surface(surface: _ClaudeHelpSurface, config: ClaudeProviderConfig | None) -> None:
    if not surface.supports_print:
        raise ConfigError("provider 'claude' requires '--print' or '-p' support, but neither flag is available.")
    if not surface.supports_output_format:
        raise ConfigError("provider 'claude' requires '--output-format' support, but the flag is unavailable.")
    if not surface.supports_resume:
        raise ConfigError("provider 'claude' requires '--resume' support, but the flag is unavailable.")
    if not surface.supports_model:
        raise ConfigError("provider 'claude' requires '--model' support, but the flag is unavailable.")
    if not surface.supports_settings:
        raise ConfigError("provider 'claude' requires '--settings' support, but the flag is unavailable.")
    if not surface.supports_add_dir:
        raise ConfigError("provider 'claude' requires '--add-dir' support, but the flag is unavailable.")
    permission_strategy = config.permission_strategy if config is not None else None
    if permission_strategy == "allow_core_tools" and not surface.supports_allowed_tools:
        raise ConfigError("provider 'claude' requires '--allowedTools' support, but the flag is unavailable.")
    if permission_strategy == "bypass" and not surface.supports_bypass_permissions:
        raise ConfigError(
            "provider 'claude' requires '--dangerously-skip-permissions' support, but the flag is unavailable."
        )
    if config is not None and config.effort is not None and not surface.supports_effort:
        raise ConfigError(
            "provider 'claude' cannot honor provider.claude.effort because the installed CLI does not support "
            "'--effort'."
        )


def _prepare_turn_command(
    turn: RenderedProviderTurn,
    *,
    config: ClaudeProviderConfig,
    emitter: ClaudePolicyEmitter,
    validation: ProviderPolicyValidationConfig,
) -> tuple[ProviderPolicyEmission | None, list[str], str | None, str | None]:
    emission = emit_turn_policy(
        emitter,
        turn,
        provider_target="claude",
        validation=validation,
        emit_kwargs={"workspace_root": turn.workspace_root},
    )
    command: list[str] = []
    model = config.model
    effort = config.effort
    if turn.policy is not None:
        model = turn.policy.model.default or model
        effort = turn.policy.model.effort or effort
    if emission is not None and emission.cli_args:
        command.extend(emission.cli_args)
    if turn.policy is None or turn.policy.model.default is None:
        if config.model:
            command.extend(["--model", config.model])
    if turn.policy is None or turn.policy.model.effort is None:
        if config.effort:
            command.extend(["--effort", config.effort])
    if emission is None:
        command.extend(claude_permission_args(config))
    elif config.permission_strategy == "allow_core_tools":
        command.extend(["--allowedTools", "Read,Write,Edit,Glob,Grep,Bash"])
    return emission, command, model, effort


def _claude_subprocess_options(
    turn: RenderedProviderTurn,
    emission: ProviderPolicyEmission | None,
) -> tuple[dict[str, str], Path | None]:
    return merge_subprocess_env(None if emission is None else emission.env), None
