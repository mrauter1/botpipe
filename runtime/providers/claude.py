"""Runtime-backed Claude Code CLI transport."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from ...core.errors import ProviderExecutionError
from ...core.providers.protocols import ProviderTransport
from ...core.providers.rendered import RenderedLLMProvider
from ...core.providers.turns import ProviderTurnResult, RenderedProviderTurn
from ...core.stores.protocols import SessionBinding
from ..config import ClaudeProviderConfig, ConfigError, ResolvedRuntimeConfig
from ._common import (
    build_session_binding,
    ensure_session_provider_match,
    format_subprocess_streams,
)


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


def parse_claude_exec_json(raw_stdout: str) -> tuple[str, str | None, dict[str, Any]]:
    """Parse Claude JSON stdout into result text and canonical session data."""

    try:
        payload = json.loads(raw_stdout)
    except json.JSONDecodeError as exc:
        raise ProviderExecutionError(f"provider 'claude' returned malformed JSON output: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise ProviderExecutionError("provider 'claude' must return a JSON object.")

    result = payload.pop("result", None)
    if not isinstance(result, str):
        raise ProviderExecutionError("provider 'claude' JSON output must contain a string 'result'.")

    session_id = payload.pop("session_id", None)
    if session_id is not None and not isinstance(session_id, str):
        raise ProviderExecutionError("provider 'claude' JSON field 'session_id' must be a string when provided.")

    return result, session_id, dict(payload)


class ClaudeTransport(ProviderTransport):
    """Transport-only Claude CLI executor."""

    def __init__(self, *, config: ClaudeProviderConfig) -> None:
        self._config = config

    def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult:
        ensure_session_provider_match("claude", turn.session)
        resume_session_id = _resumable_session_id("claude", turn.session)

        command = ["claude"]
        if resume_session_id is not None:
            command.extend(["--resume", resume_session_id])
        command.extend(["-p", turn.prompt_text, "--output-format", "json"])
        if self._config.model:
            command.extend(["--model", self._config.model])
        if self._config.effort:
            command.extend(["--effort", self._config.effort])
        command.extend(claude_permission_args(self._config))

        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            streams = format_subprocess_streams(completed.stdout, completed.stderr)
            raise ProviderExecutionError(
                f"provider 'claude' failed while running step {turn.step_name!r} "
                f"(exit code {completed.returncode}): {streams}"
            )

        result_text, resolved_session_id, provider_metadata = parse_claude_exec_json(completed.stdout)
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
                model=self._config.model,
                effort=self._config.effort,
            )
            if turn.session is not None and resolved_session_id is not None
            else None
        )
        metadata = {
            "mode": "resume" if resume_session_id is not None else "start",
            "provider_metadata": dict(provider_metadata),
        }
        return ProviderTurnResult(raw_text=result_text, session=binding, metadata=metadata)


def build_claude_transport(config: ResolvedRuntimeConfig) -> ClaudeTransport:
    """Build the Claude runtime transport."""

    verify_claude_code_capabilities(config.provider.claude)
    return ClaudeTransport(config=config.provider.claude)


class ClaudeProvider(RenderedLLMProvider):
    """Compatibility semantic provider backed by ClaudeTransport."""

    def __init__(self, config: ResolvedRuntimeConfig) -> None:
        super().__init__(build_claude_transport(config))


def build_claude_provider(config: ResolvedRuntimeConfig) -> ClaudeProvider:
    """Build the compatibility Claude semantic provider wrapper."""

    return ClaudeProvider(config)


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


def _resumable_session_id(provider_name: str, session: SessionBinding | None) -> str | None:
    if session is None:
        return None
    seen_provider = session.metadata.get("provider")
    if seen_provider == provider_name and session.session_id:
        return session.session_id
    return None
