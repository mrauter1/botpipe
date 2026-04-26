"""Shared helpers for runtime-side CLI providers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ...core.errors import ProviderExecutionError
from ...core.prompts import ResolvedPrompt
from ...core.stores.protocols import SessionBinding


def require_prompt_text(prompt: ResolvedPrompt, provider_name: str, step_name: str) -> str:
    """Return resolved prompt text or raise a provider execution error."""

    if prompt.text is None:
        raise ProviderExecutionError(
            f"provider '{provider_name}' cannot run step {step_name!r}: prompt {prompt.path!r} did not resolve to text."
        )
    return prompt.text


def format_subprocess_streams(stdout: str, stderr: str) -> str:
    """Render stdout/stderr for error and debug surfaces."""

    sections: list[str] = []
    if stdout:
        sections.append(f"stdout:\n{stdout}")
    if stderr:
        sections.append(f"stderr:\n{stderr}")
    if not sections:
        return "[empty stdout/stderr]"
    return "\n\n".join(sections)


def ensure_session_provider_match(provider_name: str, binding: SessionBinding | None) -> None:
    """Reject attempts to resume a session across provider backends."""

    if binding is None:
        return
    seen_provider = binding.metadata.get("provider")
    if isinstance(seen_provider, str) and seen_provider != provider_name:
        raise ProviderExecutionError(
            f"provider '{provider_name}' cannot resume session {binding.session_id!r} from provider "
            f"'{seen_provider}'; resuming across providers is forbidden and a new run is required."
        )


def render_verifier_input(verifier_prompt_text: str, producer_raw_output: str) -> str:
    """Render the verifier prompt and producer output in one deterministic packet."""

    return (
        "<verifier_prompt>\n"
        f"{verifier_prompt_text}\n"
        "</verifier_prompt>\n\n"
        "<producer_raw_output>\n"
        f"{producer_raw_output}\n"
        "</producer_raw_output>\n"
    )


def build_session_binding(
    binding: SessionBinding,
    *,
    session_id: str,
    provider_name: str,
    provider_metadata: dict[str, Any],
    model: str | None,
    effort: str | None,
) -> SessionBinding:
    """Build a canonical provider session binding."""

    if not session_id:
        raise ProviderExecutionError(f"provider '{provider_name}' did not return a resumable session_id.")

    metadata = deepcopy(binding.metadata)
    metadata["provider"] = provider_name
    metadata["mode"] = str(metadata.get("mode") or "persistent")
    metadata["provider_metadata"] = {
        key: deepcopy(value)
        for key, value in dict(provider_metadata).items()
        if key != "thread_id"
    }
    metadata["model_override"] = model
    metadata["effort_override"] = effort
    return SessionBinding(
        key=binding.key,
        session_id=session_id,
        provider=provider_name,
        provider_metadata=metadata["provider_metadata"],
        metadata=metadata,
    )
