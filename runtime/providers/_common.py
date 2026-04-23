"""Shared helpers for runtime-side CLI providers."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from ...core.errors import ProviderExecutionError
from ...core.primitives import Outcome
from ...core.prompts import ResolvedPrompt
from ...core.stores.protocols import SessionBinding


_JSON_FENCE_RE = re.compile(r"\A```json\s*\n(?P<body>[\s\S]*?)\n?```\s*\Z")
_OUTCOME_OPTIONAL_FIELDS = {"clarification", "payload", "question", "reason"}


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


def parse_outcome_json(raw_text: str) -> Outcome:
    """Parse a strict provider outcome JSON object."""

    candidate = raw_text.strip()
    match = _JSON_FENCE_RE.fullmatch(candidate)
    if match is not None:
        candidate = match.group("body").strip()

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ProviderExecutionError(f"provider returned malformed outcome JSON: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise ProviderExecutionError("provider outcome JSON must be an object.")

    unknown = sorted(set(payload) - {"tag", *_OUTCOME_OPTIONAL_FIELDS})
    if unknown:
        rendered = ", ".join(unknown)
        raise ProviderExecutionError(f"provider outcome JSON contains unsupported keys: {rendered}.")

    tag = payload.get("tag")
    if not isinstance(tag, str) or not tag:
        raise ProviderExecutionError("provider outcome JSON must contain a non-empty string 'tag'.")

    parsed_payload = payload.get("payload", {})
    if not isinstance(parsed_payload, dict):
        raise ProviderExecutionError("provider outcome JSON field 'payload' must be an object when provided.")

    reason = _optional_string_field(payload, "reason")
    clarification = _optional_string_field(payload, "clarification")
    question = _optional_string_field(payload, "question")

    return Outcome(
        raw_output=raw_text,
        tag=tag,
        reason=reason or "",
        clarification=clarification,
        question=question,
        payload=deepcopy(parsed_payload),
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
        ref_name=binding.ref_name,
        scope=binding.scope,
        session_id=session_id,
        metadata=metadata,
    )


def _optional_string_field(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProviderExecutionError(f"provider outcome JSON field {key!r} must be a string when provided.")
    return value
