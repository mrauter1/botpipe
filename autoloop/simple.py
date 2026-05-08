"""Simple workflow authoring declarations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from autoloop.core import Artifact
from autoloop.core.branch_groups.declarations import FanIn
from autoloop.core.context import context_runtime
from autoloop.core.effects import Effects, WorklistEffect
from autoloop.core.operations import OperationStepSpec, classify_call, execute_step_operation, llm_call
from autoloop.core.provider_policy import (
    ModelPolicy,
    PermissionPolicy,
    ProviderPolicy,
    ProviderPolicyOverride,
    SandboxPolicy,
    SYSTEM_DEFAULT_PROVIDER_POLICY,
    WorkspaceFilesystemPolicy,
    WorkspaceNetworkPolicy,
    WorkspacePolicy,
)
from autoloop.core.primitives import AWAIT_INPUT, Event, FAIL, FINISH, Goto, Outcome, RequestInput, SELF, Fail
from autoloop.core.prompts import Prompt
from autoloop.core.routes import Route
from autoloop.core.sessions import Continuity
from autoloop.core.step_state import StateVar
from autoloop.core.steps import ControlRoutes, Session, normalize_control_routes
from autoloop.core.validation_helpers import ValidationResult, render_validation_feedback
from autoloop.core.worklists import Worklist


PromptInput = str | Path | Prompt
RouteMapping = Mapping[str, Route | object]
ProviderPolicyInput = ProviderPolicy | ProviderPolicyOverride | None


class _PolicyEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ProviderName(_PolicyEnum):
    CODEX = "codex"
    CLAUDE = "claude"


class ModelEffort(_PolicyEnum):
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class ModelVerbosity(_PolicyEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReasoningSummary(_PolicyEnum):
    AUTO = "auto"
    CONCISE = "concise"
    DETAILED = "detailed"
    NONE = "none"


class SandboxMode(_PolicyEnum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    DANGER_FULL_ACCESS = "danger_full_access"


class NetworkMode(_PolicyEnum):
    FULL = "full"
    LIMITED = "limited"
    NONE = "none"


class PermissionMode(_PolicyEnum):
    ASK = "ask"
    AUTO_EDIT = "auto_edit"
    FULL_AUTO_SANDBOXED = "full_auto_sandboxed"
    FULL_AUTO_UNSANDBOXED = "full_auto_unsandboxed"
    DENY_ALL = "deny_all"


def _policy_enum_value(value: object, *, enum_cls: type[_PolicyEnum], field_name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, enum_cls):
        return value.value
    raise TypeError(f"{field_name} must use {enum_cls.__name__} values, not {value!r}")


def _policy_string_item(value: object, *, field_name: str) -> str:
    item = value if isinstance(value, str) else str(value)
    normalized = item.strip()
    if not normalized:
        raise ValueError(f"{field_name} entries must be non-empty strings")
    return normalized


def _policy_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, bytes):
        raise TypeError(f"{field_name} must be a string, Path, or sequence of strings/Paths")
    if isinstance(value, (str, Path)):
        values = (value,)
    elif isinstance(value, Sequence):
        values = value
    else:
        raise TypeError(f"{field_name} must be a string, Path, or sequence of strings/Paths")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        if isinstance(item, bytes):
            raise TypeError(f"{field_name} entries must be strings or Paths, not bytes")
        if not isinstance(item, (str, Path)):
            raise TypeError(f"{field_name} entries must be strings or Paths, not {type(item).__name__}")
        entry = _policy_string_item(item, field_name=field_name)
        if entry in seen:
            continue
        seen.add(entry)
        normalized.append(entry)
    return tuple(normalized)


def _policy_optional_tuple(value: object, *, field_name: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    return _policy_tuple(value, field_name=field_name)


def _policy_string_mapping(value: object, *, field_name: str) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping of string keys to string values")
    normalized: dict[str, str] = {}
    for key, item in value.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            raise ValueError(f"{field_name} keys must be non-empty strings")
        normalized[normalized_key] = str(item)
    return normalized


def _policy_section(payload: dict[str, object], *keys: str) -> dict[str, object]:
    current = payload
    for key in keys:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    return current


def _flat_policy_payload(
    *,
    full_policy: bool,
    model: str | None,
    provider: ProviderName | None,
    base_url: str | None,
    effort: ModelEffort | None,
    verbosity: ModelVerbosity | None,
    reasoning_summary: ReasoningSummary | None,
    model_overrides: Mapping[str, str] | None,
    sandbox_mode: SandboxMode | None,
    read_only: bool,
    allow_read: object,
    deny_read: object,
    allow_write: object,
    deny_write: object,
    network: NetworkMode | None,
    network_domains: object,
    deny_network_domains: object,
    allow_local_binding: bool | None,
    permission_mode: PermissionMode | None,
    allow_permissions: object,
    ask_permissions: object,
    deny_permissions: object,
) -> dict[str, object]:
    payload: dict[str, object] = (
        SYSTEM_DEFAULT_PROVIDER_POLICY.model_dump(mode="python", warnings=False) if full_policy else {}
    )

    provider_value = _policy_enum_value(provider, enum_cls=ProviderName, field_name="provider")
    effort_value = _policy_enum_value(effort, enum_cls=ModelEffort, field_name="effort")
    verbosity_value = _policy_enum_value(verbosity, enum_cls=ModelVerbosity, field_name="verbosity")
    reasoning_summary_value = _policy_enum_value(
        reasoning_summary,
        enum_cls=ReasoningSummary,
        field_name="reasoning_summary",
    )
    sandbox_mode_value = _policy_enum_value(sandbox_mode, enum_cls=SandboxMode, field_name="sandbox_mode")
    network_value = _policy_enum_value(network, enum_cls=NetworkMode, field_name="network")
    permission_mode_value = _policy_enum_value(
        permission_mode,
        enum_cls=PermissionMode,
        field_name="permission_mode",
    )

    model_overrides_value = _policy_string_mapping(model_overrides, field_name="model_overrides")
    allow_read_values = _policy_optional_tuple(allow_read, field_name="allow_read")
    deny_read_values = _policy_optional_tuple(deny_read, field_name="deny_read")
    allow_write_values = _policy_optional_tuple(allow_write, field_name="allow_write")
    deny_write_values = _policy_optional_tuple(deny_write, field_name="deny_write")
    network_domains_values = _policy_optional_tuple(network_domains, field_name="network_domains")
    deny_network_domains_values = _policy_optional_tuple(
        deny_network_domains,
        field_name="deny_network_domains",
    )
    allow_permissions_values = _policy_optional_tuple(
        allow_permissions,
        field_name="allow_permissions",
    )
    ask_permissions_values = _policy_optional_tuple(ask_permissions, field_name="ask_permissions")
    deny_permissions_values = _policy_optional_tuple(deny_permissions, field_name="deny_permissions")

    effective_sandbox_mode = sandbox_mode_value
    if read_only:
        if effective_sandbox_mode is None:
            effective_sandbox_mode = SandboxMode.READ_ONLY.value
        elif effective_sandbox_mode != SandboxMode.READ_ONLY.value:
            raise ValueError("read_only=True is incompatible with sandbox_mode other than SandboxMode.READ_ONLY")
    if effective_sandbox_mode == SandboxMode.READ_ONLY.value and allow_write is not None:
        raise ValueError("allow_write cannot be set when sandbox mode is read-only")

    if permission_mode_value == PermissionMode.FULL_AUTO_UNSANDBOXED.value:
        if effective_sandbox_mode in {
            SandboxMode.READ_ONLY.value,
            SandboxMode.WORKSPACE_WRITE.value,
        }:
            raise ValueError(
                "permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED requires "
                "sandbox_mode=SandboxMode.DANGER_FULL_ACCESS"
            )
        if effective_sandbox_mode is None:
            effective_sandbox_mode = SandboxMode.DANGER_FULL_ACCESS.value

    if not read_only and effective_sandbox_mode is None and allow_write is not None:
        effective_sandbox_mode = SandboxMode.WORKSPACE_WRITE.value

    if (
        effective_sandbox_mode == SandboxMode.DANGER_FULL_ACCESS.value
        and permission_mode_value == PermissionMode.FULL_AUTO_SANDBOXED.value
    ):
        raise ValueError(
            "sandbox_mode=SandboxMode.DANGER_FULL_ACCESS is incompatible with "
            "permission_mode=PermissionMode.FULL_AUTO_SANDBOXED"
        )

    effective_permission_mode = permission_mode_value
    if effective_sandbox_mode == SandboxMode.DANGER_FULL_ACCESS.value and effective_permission_mode is None:
        raise ValueError(
            "sandbox_mode=SandboxMode.DANGER_FULL_ACCESS requires an explicit compatible permission_mode"
        )

    dangerous_access = (
        effective_sandbox_mode == SandboxMode.DANGER_FULL_ACCESS.value
        or permission_mode_value == PermissionMode.FULL_AUTO_UNSANDBOXED.value
    )

    effective_network = network_value
    if network_domains is not None and network_domains_values == ():
        raise ValueError("network_domains must not be empty when provided")
    if effective_network is None and network_domains_values is not None:
        effective_network = NetworkMode.LIMITED.value
    if effective_network == NetworkMode.LIMITED.value and not network_domains_values:
        raise ValueError("network=NetworkMode.LIMITED requires non-empty network_domains")
    if effective_network in {NetworkMode.FULL.value, NetworkMode.NONE.value} and network_domains_values:
        raise ValueError(f"network={network!r} cannot be combined with network_domains")

    model_supplied = any(
        value is not None
        for value in (
            model,
            provider,
            base_url,
            effort,
            verbosity,
            reasoning_summary,
            model_overrides,
        )
    )
    filesystem_supplied = any(value is not None for value in (allow_read, deny_read, allow_write, deny_write))
    permission_supplied = any(
        value is not None
        for value in (
            permission_mode,
            allow_permissions,
            ask_permissions,
            deny_permissions,
        )
    )
    network_supplied = any(
        value is not None
        for value in (
            network,
            network_domains,
            deny_network_domains,
            allow_local_binding,
        )
    )
    sandbox_supplied = sandbox_mode is not None or read_only or filesystem_supplied or network_supplied or dangerous_access
    filesystem_required = filesystem_supplied or effective_sandbox_mode == SandboxMode.READ_ONLY.value
    network_required = network_supplied
    permissions_required = permission_supplied or dangerous_access

    if full_policy or model_supplied:
        model_payload = _policy_section(payload, "model")
        if model is not None:
            model_payload["default"] = model
        if provider_value is not None:
            model_payload["provider"] = provider_value
        if base_url is not None:
            model_payload["base_url"] = base_url
        if effort_value is not None:
            model_payload["effort"] = effort_value
        if verbosity_value is not None:
            model_payload["verbosity"] = verbosity_value
        if reasoning_summary_value is not None:
            model_payload["reasoning_summary"] = reasoning_summary_value
        if model_overrides_value is not None:
            model_payload["overrides"] = model_overrides_value

    if full_policy or permissions_required:
        permissions_payload = _policy_section(payload, "permissions")
        if effective_permission_mode is not None:
            permissions_payload["mode"] = effective_permission_mode
        if allow_permissions_values is not None:
            permissions_payload["allow"] = allow_permissions_values
        if ask_permissions_values is not None:
            permissions_payload["ask"] = ask_permissions_values
        if deny_permissions_values is not None:
            permissions_payload["deny"] = deny_permissions_values
        if dangerous_access:
            permissions_payload["allow_dangerous_bypass"] = True

    if full_policy or sandbox_supplied:
        sandbox_payload = _policy_section(payload, "sandbox")
        if effective_sandbox_mode is not None:
            sandbox_payload["mode"] = effective_sandbox_mode

    if full_policy or filesystem_required:
        filesystem_payload = _policy_section(payload, "sandbox", "workspace", "filesystem")
        if allow_read_values is not None:
            filesystem_payload["allow_read"] = allow_read_values
        if deny_read_values is not None:
            filesystem_payload["deny_read"] = deny_read_values
        if allow_write_values is not None:
            filesystem_payload["allow_write"] = allow_write_values
        if deny_write_values is not None:
            filesystem_payload["deny_write"] = deny_write_values
        if effective_sandbox_mode == SandboxMode.READ_ONLY.value:
            filesystem_payload["allow_write"] = ()

    if full_policy or network_required:
        network_payload = _policy_section(payload, "sandbox", "workspace", "network")
        if effective_network == NetworkMode.FULL.value:
            network_payload["enabled"] = True
            network_payload["mode"] = NetworkMode.FULL.value
            network_payload["allow_domains"] = ()
        elif effective_network == NetworkMode.NONE.value:
            network_payload["enabled"] = False
            network_payload["mode"] = NetworkMode.NONE.value
            network_payload["allow_domains"] = ()
        elif effective_network == NetworkMode.LIMITED.value:
            network_payload["enabled"] = True
            network_payload["mode"] = NetworkMode.LIMITED.value
            network_payload["allow_domains"] = network_domains_values
        if deny_network_domains_values is not None:
            network_payload["deny_domains"] = deny_network_domains_values
        if allow_local_binding is not None:
            network_payload["allow_local_binding"] = allow_local_binding

    return payload


def Policy(
    *,
    model: str | None = None,
    provider: ProviderName | None = None,
    base_url: str | None = None,
    effort: ModelEffort | None = None,
    verbosity: ModelVerbosity | None = None,
    reasoning_summary: ReasoningSummary | None = None,
    model_overrides: Mapping[str, str] | None = None,
    sandbox_mode: SandboxMode | None = None,
    read_only: bool = False,
    allow_read: str | Path | Sequence[str | Path] | None = None,
    deny_read: str | Path | Sequence[str | Path] | None = None,
    allow_write: str | Path | Sequence[str | Path] | None = None,
    deny_write: str | Path | Sequence[str | Path] | None = None,
    network: NetworkMode | None = None,
    network_domains: str | Sequence[str] | None = None,
    deny_network_domains: str | Sequence[str] | None = None,
    allow_local_binding: bool | None = None,
    permission_mode: PermissionMode | None = None,
    allow_permissions: str | Sequence[str] | None = None,
    ask_permissions: str | Sequence[str] | None = None,
    deny_permissions: str | Sequence[str] | None = None,
) -> ProviderPolicy:
    """Flat workflow-level authoring facade for ProviderPolicy.

    Omitted fields preserve SYSTEM_DEFAULT_PROVIDER_POLICY. Fixed option fields use
    Autoloop policy enums rather than raw strings. network_domains implies limited
    network mode. allow_write implies workspace_write mode unless read_only or
    sandbox_mode=SandboxMode.READ_ONLY is set, which is invalid with allow_write.
    sandbox_mode=SandboxMode.DANGER_FULL_ACCESS and
    permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED use the same flat API and
    internally enable the dangerous-bypass latch required by the nested policy
    schema.
    """

    return ProviderPolicy.model_validate(
        _flat_policy_payload(
            full_policy=True,
            model=model,
            provider=provider,
            base_url=base_url,
            effort=effort,
            verbosity=verbosity,
            reasoning_summary=reasoning_summary,
            model_overrides=model_overrides,
            sandbox_mode=sandbox_mode,
            read_only=read_only,
            allow_read=allow_read,
            deny_read=deny_read,
            allow_write=allow_write,
            deny_write=deny_write,
            network=network,
            network_domains=network_domains,
            deny_network_domains=deny_network_domains,
            allow_local_binding=allow_local_binding,
            permission_mode=permission_mode,
            allow_permissions=allow_permissions,
            ask_permissions=ask_permissions,
            deny_permissions=deny_permissions,
        )
    )


def PolicyOverride(
    *,
    model: str | None = None,
    provider: ProviderName | None = None,
    base_url: str | None = None,
    effort: ModelEffort | None = None,
    verbosity: ModelVerbosity | None = None,
    reasoning_summary: ReasoningSummary | None = None,
    model_overrides: Mapping[str, str] | None = None,
    sandbox_mode: SandboxMode | None = None,
    read_only: bool = False,
    allow_read: str | Path | Sequence[str | Path] | None = None,
    deny_read: str | Path | Sequence[str | Path] | None = None,
    allow_write: str | Path | Sequence[str | Path] | None = None,
    deny_write: str | Path | Sequence[str | Path] | None = None,
    network: NetworkMode | None = None,
    network_domains: str | Sequence[str] | None = None,
    deny_network_domains: str | Sequence[str] | None = None,
    allow_local_binding: bool | None = None,
    permission_mode: PermissionMode | None = None,
    allow_permissions: str | Sequence[str] | None = None,
    ask_permissions: str | Sequence[str] | None = None,
    deny_permissions: str | Sequence[str] | None = None,
) -> ProviderPolicyOverride:
    """Flat step/operation-level authoring facade for ProviderPolicyOverride.

    Only supplied fields are included in the override payload. Fixed option fields
    use Autoloop policy enums rather than raw strings. read_only=True also sets
    allow_write=() so merged policy cannot inherit write roots. network_domains
    implies limited network mode. sandbox_mode=SandboxMode.DANGER_FULL_ACCESS and
    permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED use the same flat API and
    internally enable the dangerous-bypass latch required by the nested policy
    schema.
    """

    return ProviderPolicyOverride.model_validate(
        _flat_policy_payload(
            full_policy=False,
            model=model,
            provider=provider,
            base_url=base_url,
            effort=effort,
            verbosity=verbosity,
            reasoning_summary=reasoning_summary,
            model_overrides=model_overrides,
            sandbox_mode=sandbox_mode,
            read_only=read_only,
            allow_read=allow_read,
            deny_read=deny_read,
            allow_write=allow_write,
            deny_write=deny_write,
            network=network,
            network_domains=network_domains,
            deny_network_domains=deny_network_domains,
            allow_local_binding=allow_local_binding,
            permission_mode=permission_mode,
            allow_permissions=allow_permissions,
            ask_permissions=ask_permissions,
            deny_permissions=deny_permissions,
        )
    )


class EmptyState(BaseModel):
    """Default state model for workflows that do not declare ``State``."""


class EmptyParams(BaseModel):
    """Default params model for workflows that do not declare ``Params``."""


class Workflow:
    """Simple public authoring surface."""

    extensions: tuple[object, ...] = ()
    Params = EmptyParams
    State = EmptyState
    policy: ProviderPolicy | None = None


@dataclass(frozen=True, slots=True)
class ArtifactSpec:
    """Simple authoring artifact declaration with optional inferred step-local paths."""

    name: str
    kind: str
    schema: type[BaseModel] | dict[str, object] | None = None
    path: str | Path | None = None
    required: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("artifact name must be a non-empty string")
        if self.kind not in {"json", "markdown", "text", "raw"}:
            raise ValueError(f"unsupported artifact kind {self.kind!r}")

    def path_template(self, step_name: str) -> str:
        if self.path is not None:
            return str(self.path)
        suffix = {
            "json": ".json",
            "markdown": ".md",
            "text": ".txt",
            "raw": "",
        }[self.kind]
        return f"{{workflow_folder}}/{step_name}/{self.name}{suffix}"

    def materialize(self, step_name: str) -> Artifact:
        template = self.path_template(step_name)
        if self.kind == "json":
            return Artifact.json(template, schema=self.schema, required=self.required, name=self.name)
        if self.kind == "markdown":
            return Artifact.md(template, required=self.required, name=self.name)
        if self.kind == "raw":
            return Artifact.raw(template, required=self.required, name=self.name)
        return Artifact.text(template, required=self.required, name=self.name)


ArtifactInput = Artifact | ArtifactSpec | str


def Json(
    name: str,
    schema: type[BaseModel] | dict[str, object] | None = None,
    *,
    path: str | Path | None = None,
    required: bool = False,
) -> ArtifactSpec:
    return ArtifactSpec(name=name, kind="json", schema=schema, path=path, required=required)


def Md(name: str, *, path: str | Path | None = None, required: bool = False) -> ArtifactSpec:
    return ArtifactSpec(name=name, kind="markdown", path=path, required=required)


def Text(name: str, *, path: str | Path | None = None, required: bool = False) -> ArtifactSpec:
    return ArtifactSpec(name=name, kind="text", path=path, required=required)


def Raw(name: str, *, path: str | Path | None = None, required: bool = False) -> ArtifactSpec:
    return ArtifactSpec(name=name, kind="raw", path=path, required=required)


class _NamedDeclaration:
    __slots__ = ("name", "_explicit_name")
    default_chain_route = "done"

    def __init__(self, *, name: str | None = None) -> None:
        self.name = name
        self._explicit_name = name

    def __set_name__(self, owner: type[object], attr_name: str) -> None:
        if self.name is None:
            self.name = attr_name

    def __getattr__(self, item: str) -> Artifact | ArtifactSpec:
        for collection_name in ("writes", "verifier_writes"):
            try:
                artifacts = object.__getattribute__(self, collection_name)
            except AttributeError:
                artifacts = ()
            for artifact in artifacts:
                if getattr(artifact, "name", None) == item:
                    return artifact
        raise AttributeError(item)


class StepDeclaration(_NamedDeclaration):
    """Simple step declaration lowered during workflow definition discovery."""

    kind = "step"

    def __init__(
        self,
        prompt: PromptInput,
        *,
        name: str | None = None,
        reads: Sequence[ArtifactInput] = (),
        requires: Sequence[ArtifactInput] = (),
        writes: Sequence[Artifact | ArtifactSpec] = (),
        scope: Worklist | str | None = None,
        item_state: type[BaseModel] | Mapping[str, StateVar] | None = None,
        routes: RouteMapping | None = None,
        before: Any | None = None,
        after: Any | None = None,
        control_schema: Any | None = None,
        retry: Any | None = None,
        session: Any | None = None,
        control_routes: ControlRoutes | bool = True,
        policy: ProviderPolicyInput = None,
    ) -> None:
        super().__init__(name=name)
        self.prompt = _normalize_simple_prompt(prompt)
        self.reads = tuple(reads)
        self.requires = tuple(requires)
        self.writes = _normalize_writes(writes)
        self.scope = scope
        self.item_state = item_state
        self.routes = dict(routes or {})
        self.before = before
        self.after = after
        self.control_schema = control_schema
        self.retry = retry
        self.session = session
        self.policy = _normalize_provider_policy(policy)
        self.control_routes = normalize_control_routes(
            control_routes,
            default=ControlRoutes(question="auto"),
        )


class ProduceVerifyStepDeclaration(_NamedDeclaration):
    """Simple producer/verifier declaration lowered during workflow definition discovery."""

    kind = "produce_verify"
    default_chain_route = "accepted"

    def __init__(
        self,
        producer_prompt: PromptInput,
        verifier_prompt: PromptInput,
        *,
        name: str | None = None,
        reads: Sequence[ArtifactInput] = (),
        requires: Sequence[ArtifactInput] = (),
        verifier_reads: Sequence[ArtifactInput] = (),
        verifier_requires: Sequence[ArtifactInput] = (),
        producer_writes: Sequence[Artifact | ArtifactSpec] = (),
        verifier_writes: Sequence[Artifact | ArtifactSpec] = (),
        scope: Worklist | str | None = None,
        routes: RouteMapping | None = None,
        state: type[BaseModel] | Mapping[str, StateVar] | None = None,
        item_state: type[BaseModel] | Mapping[str, StateVar] | None = None,
        before_producer: Any | None = None,
        after_producer: Any | None = None,
        before_verifier: Any | None = None,
        after_verifier: Any | None = None,
        control_schema: Any | None = None,
        retry: Any | None = None,
        session: Any | None = None,
        verifier_session: Any | None = None,
        control_routes: ControlRoutes | bool = True,
        policy: ProviderPolicyInput = None,
    ) -> None:
        super().__init__(name=name)
        self.producer_prompt = _normalize_simple_prompt(producer_prompt)
        self.verifier_prompt = _normalize_simple_prompt(verifier_prompt)
        self.reads = tuple(reads)
        self.requires = tuple(requires)
        self.verifier_reads = tuple(verifier_reads)
        self.verifier_requires = tuple(verifier_requires)
        self.writes = _normalize_writes(producer_writes)
        self.verifier_writes = _normalize_writes(verifier_writes)
        self.scope = scope
        self.routes = dict(routes or {})
        self.state = state
        self.item_state = item_state
        self.before_producer = before_producer
        self.after_producer = after_producer
        self.before_verifier = before_verifier
        self.after_verifier = after_verifier
        self.control_schema = control_schema
        self.retry = retry
        self.session = session
        self.verifier_session = verifier_session
        self.policy = _normalize_provider_policy(policy)
        self.control_routes = normalize_control_routes(
            control_routes,
            default=ControlRoutes(question="auto"),
        )


class PythonStepDeclaration(_NamedDeclaration):
    """Simple python-step declaration lowered during workflow definition discovery.

    The optional provider policy applies only to provider-backed operations called
    inside the handler. It does not sandbox the Python code itself.
    """

    kind = "python"

    def __init__(
        self,
        fn: Any,
        *,
        name: str | None = None,
        reads: Sequence[ArtifactInput] = (),
        requires: Sequence[ArtifactInput] = (),
        writes: Sequence[Artifact | ArtifactSpec] = (),
        routes: RouteMapping | None = None,
        before: Any | None = None,
        after: Any | None = None,
        control_routes: ControlRoutes | bool = True,
        policy: ProviderPolicyInput = None,
    ) -> None:
        super().__init__(name=name)
        self.fn = fn
        self.reads = tuple(reads)
        self.requires = tuple(requires)
        self.writes = _normalize_writes(writes)
        self.routes = dict(routes or {})
        self.before = before
        self.after = after
        self.policy = _normalize_provider_policy(policy)
        self.control_routes = normalize_control_routes(
            control_routes,
            default=ControlRoutes(question="never"),
        )


class _WorkflowStepDeclaration(_NamedDeclaration):
    """Child-workflow invocation step declaration."""

    kind = "workflow"

    def __init__(
        self,
        workflow: object,
        *,
        name: str | None = None,
        message: str | None = None,
        message_from: Artifact | str | Path | None = None,
        params: Mapping[str, object] | None = None,
        input: object | None = None,
        reads: Sequence[ArtifactInput] = (),
        requires: Sequence[ArtifactInput] = (),
        writes: Sequence[Artifact | ArtifactSpec] = (),
        routes: RouteMapping | None = None,
        before: Any | None = None,
        after: Any | None = None,
        control_routes: ControlRoutes | bool = True,
        policy: ProviderPolicyInput = None,
    ) -> None:
        super().__init__(name=name)
        self.workflow = workflow
        self.message = message
        self.message_from = message_from
        self.params = dict(params or {})
        self.input = input
        self.reads = tuple(reads)
        self.requires = tuple(requires)
        self.writes = _normalize_writes(writes)
        self.routes = dict(routes or {})
        self.before = before
        self.after = after
        self.policy = _normalize_provider_policy(policy)
        self.control_routes = normalize_control_routes(
            control_routes,
            default=ControlRoutes(question="never"),
        )


class _BranchGroupDeclaration(_NamedDeclaration):
    """Simple branch-group declaration lowered to one composite step."""

    kind = "branch_group"
    writes: tuple[Artifact | ArtifactSpec, ...] = ()
    verifier_writes: tuple[Artifact | ArtifactSpec, ...] = ()

    def __init__(
        self,
        *,
        name: str | None = None,
        settle: str = "all",
        concurrency: int | None = None,
        fan_in: Any | None = None,
        outcome: Any = "all_done",
        success_routes: Sequence[str] = ("done", "accepted"),
        routes: RouteMapping | None = None,
        branch_group_kind: str,
    ) -> None:
        super().__init__(name=name)
        self.branch_group_kind = branch_group_kind
        self.settle = settle
        self.concurrency = concurrency
        self.fan_in = fan_in
        self.outcome = outcome
        self.success_routes = tuple(dict.fromkeys(success_routes))
        self.routes = dict(routes or {})
        self.control_routes = ControlRoutes(question="never")
        self.implicit_routes = {"question": AWAIT_INPUT, "failed": FAIL} if fan_in is None else {}
        self.default_chain_route, self.rework_chain_route = _default_branch_group_chain_routes(fan_in)

    def nested_declarations(self) -> tuple[object, ...]:
        raise NotImplementedError


class ParallelDeclaration(_BranchGroupDeclaration):
    """Simple `parallel(...)` composite declaration."""

    def __init__(
        self,
        *,
        branches: Mapping[str, object],
        name: str | None = None,
        concurrency: int | None = None,
        settle: str = "all",
        fan_in: Any | None = None,
        outcome: Any = "all_done",
        success_routes: Sequence[str] = ("done", "accepted"),
        routes: RouteMapping | None = None,
    ) -> None:
        super().__init__(
            name=name,
            settle=settle,
            concurrency=concurrency,
            fan_in=fan_in,
            outcome=outcome,
            success_routes=success_routes,
            routes=routes,
            branch_group_kind="parallel",
        )
        self.branches = dict(branches)

    def nested_declarations(self) -> tuple[object, ...]:
        nested = list(self.branches.values())
        if self.fan_in is not None:
            nested.append(self.fan_in)
        return tuple(nested)


class FanOutDeclaration(_BranchGroupDeclaration):
    """Simple `fan_out(...)` composite declaration."""

    def __init__(
        self,
        *,
        step: object,
        branches: Mapping[str, object],
        name: str | None = None,
        concurrency: int | None = None,
        settle: str = "all",
        fan_in: Any | None = None,
        outcome: Any = "all_done",
        success_routes: Sequence[str] = ("done", "accepted"),
        routes: RouteMapping | None = None,
    ) -> None:
        super().__init__(
            name=name,
            settle=settle,
            concurrency=concurrency,
            fan_in=fan_in,
            outcome=outcome,
            success_routes=success_routes,
            routes=routes,
            branch_group_kind="fan_out",
        )
        self.step = step
        self.branches = dict(branches)

    def nested_declarations(self) -> tuple[object, ...]:
        nested = [self.step]
        if self.fan_in is not None:
            nested.append(self.fan_in)
        return tuple(nested)


class OperationStepDeclaration(_NamedDeclaration):
    """Simple feedforward value-producing declaration."""

    kind = "operation"

    def __init__(
        self,
        operation_kind: str,
        prompt: PromptInput,
        *,
        returns: Any = str,
        choices: Sequence[str] = (),
        name: str | None = None,
        reads: Sequence[ArtifactInput] = (),
        requires: Sequence[ArtifactInput] = (),
        retry: int = 3,
    ) -> None:
        super().__init__(name=name)
        self.operation_kind = operation_kind
        self.prompt = _normalize_simple_prompt(prompt)
        self.returns = returns
        self.choices = _normalize_simple_choices(choices) if operation_kind == "classify" else ()
        self.reads = tuple(reads)
        self.requires = tuple(requires)
        self.retry = retry
        self.control_routes = ControlRoutes(question="never")

    def build_handler(self) -> Any:
        step_name = self.name or "<operation>"
        spec = OperationStepSpec(
            operation_kind=self.operation_kind,
            prompt=self.prompt,
            returns=self.returns,
            choices=tuple(self.choices),
            retry=self.retry,
        )

        def handler(ctx: Any) -> str:
            execute_step_operation(ctx, step_name=step_name, spec=spec)
            return "done"

        handler.__name__ = f"_operation_step_{step_name}"
        return handler


def step(
    prompt: PromptInput,
    *,
    name: str | None = None,
    reads: Sequence[ArtifactInput] = (),
    requires: Sequence[ArtifactInput] = (),
    writes: Sequence[Artifact | ArtifactSpec] = (),
    scope: Worklist | str | None = None,
    item_state: type[BaseModel] | Mapping[str, StateVar] | None = None,
    routes: RouteMapping | None = None,
    before: Any | None = None,
    after: Any | None = None,
    control_schema: Any | None = None,
    retry: Any | None = None,
    session: Any | None = None,
    control_routes: ControlRoutes | bool = True,
    policy: ProviderPolicyInput = None,
) -> StepDeclaration:
    return StepDeclaration(
        prompt,
        name=name,
        reads=reads,
        requires=requires,
        writes=writes,
        scope=scope,
        item_state=item_state,
        routes=routes,
        before=before,
        after=after,
        control_schema=control_schema,
        retry=retry,
        session=session,
        control_routes=control_routes,
        policy=policy,
    )


def produce_verify_step(
    *,
    producer_prompt: PromptInput,
    verifier_prompt: PromptInput,
    name: str | None = None,
    reads: Sequence[ArtifactInput] = (),
    requires: Sequence[ArtifactInput] = (),
    verifier_reads: Sequence[ArtifactInput] = (),
    verifier_requires: Sequence[ArtifactInput] = (),
    producer_writes: Sequence[Artifact | ArtifactSpec] = (),
    verifier_writes: Sequence[Artifact | ArtifactSpec] = (),
    scope: Worklist | str | None = None,
    routes: RouteMapping | None = None,
    state: type[BaseModel] | Mapping[str, StateVar] | None = None,
    item_state: type[BaseModel] | Mapping[str, StateVar] | None = None,
    before_producer: Any | None = None,
    after_producer: Any | None = None,
    before_verifier: Any | None = None,
    after_verifier: Any | None = None,
    control_schema: Any | None = None,
    retry: Any | None = None,
    session: Any | None = None,
    verifier_session: Any | None = None,
    control_routes: ControlRoutes | bool = True,
    policy: ProviderPolicyInput = None,
) -> ProduceVerifyStepDeclaration:
    return ProduceVerifyStepDeclaration(
        producer_prompt,
        verifier_prompt,
        name=name,
        reads=reads,
        requires=requires,
        verifier_reads=verifier_reads,
        verifier_requires=verifier_requires,
        producer_writes=producer_writes,
        verifier_writes=verifier_writes,
        scope=scope,
        routes=routes,
        state=state,
        item_state=item_state,
        before_producer=before_producer,
        after_producer=after_producer,
        before_verifier=before_verifier,
        after_verifier=after_verifier,
        control_schema=control_schema,
        retry=retry,
        session=session,
        verifier_session=verifier_session,
        control_routes=control_routes,
        policy=policy,
    )


def python_step(
    fn: Any | None = None,
    *,
    name: str | None = None,
    reads: Sequence[ArtifactInput] = (),
    requires: Sequence[ArtifactInput] = (),
    writes: Sequence[Artifact | ArtifactSpec] = (),
    routes: RouteMapping | None = None,
    before: Any | None = None,
    after: Any | None = None,
    control_routes: ControlRoutes | bool = True,
    policy: ProviderPolicyInput = None,
) -> PythonStepDeclaration | Any:
    if fn is None:
        def decorator(inner: Any) -> PythonStepDeclaration:
            return PythonStepDeclaration(
                inner,
                name=name,
                reads=reads,
                requires=requires,
                writes=writes,
                routes=routes,
                before=before,
                after=after,
                control_routes=control_routes,
                policy=policy,
            )

        return decorator
    return PythonStepDeclaration(
        fn,
        name=name,
        reads=reads,
        requires=requires,
        writes=writes,
        routes=routes,
        before=before,
        after=after,
        control_routes=control_routes,
        policy=policy,
    )


def validation_step(
    fn: Any | None = None,
    *,
    name: str | None = None,
    feedback: Artifact | ArtifactSpec,
    success: str = "done",
    repair: str = "repair",
    failed: object | None = None,
    reads: Sequence[ArtifactInput] = (),
    requires: Sequence[ArtifactInput] = (),
    writes: Sequence[Artifact | ArtifactSpec] = (),
    routes: RouteMapping | None = None,
    before: Any | None = None,
    after: Any | None = None,
    control_routes: ControlRoutes | bool = True,
) -> PythonStepDeclaration | Any:
    combined_writes = tuple(dict.fromkeys((*writes, feedback)))
    implicit_routes = {"failed": failed} if failed is not None else {}

    def decorator(inner: Any) -> PythonStepDeclaration:
        step_name = name or getattr(inner, "__name__", "validation")

        def handler(ctx):
            try:
                result = inner(ctx)
            except Exception as exc:
                if failed is None:
                    raise
                return Event("failed", reason=f"{type(exc).__name__}: {exc}")
            if not isinstance(result, ValidationResult):
                raise TypeError(f"validation_step {step_name!r} must return ValidationResult")
            runtime = context_runtime(ctx)
            if ctx.artifacts is None:
                raise RuntimeError("validation_step requires runtime artifact handles")
            feedback_name = _artifact_reference_name(feedback)
            feedback_handle = getattr(ctx.artifacts, feedback_name)
            if result.ok:
                runtime.emit_runtime_event(
                    "validation_step_passed",
                    feedback_artifact=str(feedback_handle.path),
                    message=None,
                    details=[],
                )
                return Event(success)
            feedback_handle.write_text(render_validation_feedback(result))
            runtime.emit_runtime_event(
                "validation_step_failed_repairable",
                feedback_artifact=str(feedback_handle.path),
                message=result.message,
                details=list(result.details),
            )
            return Event(
                repair,
                reason=result.message,
                handoff=f"Review feedback artifact: {feedback_handle.path}",
            )

        declaration = PythonStepDeclaration(
            handler,
            name=name,
            reads=reads,
            requires=requires,
            writes=combined_writes,
            routes=routes,
            before=before,
            after=after,
            control_routes=control_routes,
        )
        setattr(declaration, "implicit_routes", dict(implicit_routes))
        return declaration

    if fn is None:
        return decorator
    return decorator(fn)


def workflow_step(
    workflow: object,
    *,
    name: str | None = None,
    message: str | None = None,
    message_from: Artifact | str | Path | None = None,
    params: Mapping[str, object] | None = None,
    input: object | None = None,
    reads: Sequence[ArtifactInput] = (),
    requires: Sequence[ArtifactInput] = (),
    writes: Sequence[Artifact | ArtifactSpec] = (),
    routes: RouteMapping | None = None,
    before: Any | None = None,
    after: Any | None = None,
    control_routes: ControlRoutes | bool = True,
    policy: ProviderPolicyInput = None,
) -> _WorkflowStepDeclaration:
    return _WorkflowStepDeclaration(
        workflow,
        name=name,
        message=message,
        message_from=message_from,
        params=params,
        input=input,
        reads=reads,
        requires=requires,
        writes=writes,
        routes=routes,
        before=before,
        after=after,
        control_routes=control_routes,
        policy=policy,
    )


def parallel(
    *,
    branches: Mapping[str, object],
    name: str | None = None,
    concurrency: int | None = None,
    settle: str = "all",
    fan_in: Any | None = None,
    outcome: Any = "all_done",
    success_routes: Sequence[str] = ("done", "accepted"),
    routes: RouteMapping | None = None,
) -> ParallelDeclaration:
    return ParallelDeclaration(
        branches=branches,
        name=name,
        concurrency=concurrency,
        settle=settle,
        fan_in=fan_in,
        outcome=outcome,
        success_routes=success_routes,
        routes=routes,
    )


def fan_out(
    *,
    step: object,
    branches: Mapping[str, object],
    name: str | None = None,
    concurrency: int | None = None,
    settle: str = "all",
    fan_in: Any | None = None,
    outcome: Any = "all_done",
    success_routes: Sequence[str] = ("done", "accepted"),
    routes: RouteMapping | None = None,
) -> FanOutDeclaration:
    return FanOutDeclaration(
        step=step,
        branches=branches,
        name=name,
        concurrency=concurrency,
        settle=settle,
        fan_in=fan_in,
        outcome=outcome,
        success_routes=success_routes,
        routes=routes,
    )


def _normalize_writes(
    writes: Sequence[Artifact | ArtifactSpec],
) -> tuple[Artifact | ArtifactSpec, ...]:
    return tuple(writes)


def _default_branch_group_chain_routes(fan_in: Any | None) -> tuple[str, str | None]:
    fan_in_kind = getattr(fan_in, "kind", None)
    if fan_in_kind in {"review", "produce_verify"}:
        return "accepted", "needs_rework"
    return "done", None


def _artifact_reference_name(reference: Artifact | ArtifactSpec) -> str:
    name = getattr(reference, "name", None)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("validation_step feedback artifacts must have a stable name")
    return name.strip()


def _normalize_provider_policy(policy: ProviderPolicyInput) -> ProviderPolicyInput:
    if policy is None or isinstance(policy, (ProviderPolicy, ProviderPolicyOverride)):
        return policy
    raise TypeError("policy must be a ProviderPolicy, ProviderPolicyOverride, or None")


def _normalize_simple_prompt(prompt: PromptInput) -> Prompt:
    if isinstance(prompt, Prompt):
        return prompt
    if isinstance(prompt, Path):
        return Prompt.file(prompt)
    if isinstance(prompt, str):
        return Prompt.inline(prompt)
    raise TypeError(f"unsupported prompt type: {type(prompt)!r}")


def _normalize_simple_choices(choices: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for choice in choices:
        if not isinstance(choice, str) or not choice.strip():
            raise TypeError("classification choices must be non-empty strings")
        normalized.append(choice.strip())
    if not normalized:
        raise TypeError("classification choices must not be empty")
    unique = tuple(dict.fromkeys(normalized))
    if len(unique) != len(normalized):
        raise TypeError("classification choices must not repeat")
    return unique


class LLMOperation:
    """Public LLM operation surface for inline calls and operation steps."""

    def __call__(
        self,
        prompt: PromptInput,
        *,
        returns: Any = str,
        retry: int = 3,
        provider: Any | None = None,
        prompt_registry: Any | None = None,
        context: Any | None = None,
        run_folder: Path | None = None,
        policy: ProviderPolicyInput = None,
    ) -> Any:
        normalized_prompt = _normalize_simple_prompt(prompt)
        return llm_call(
            normalized_prompt,
            returns=returns,
            retry=retry,
            provider=provider,
            prompt_registry=prompt_registry,
            context=context,
            run_folder=run_folder,
            policy=policy,
        )

    def step(
        self,
        *,
        prompt: PromptInput,
        returns: Any = str,
        name: str | None = None,
        reads: Sequence[ArtifactInput] = (),
        requires: Sequence[ArtifactInput] = (),
        retry: int = 3,
    ) -> OperationStepDeclaration:
        return OperationStepDeclaration(
            "llm",
            prompt,
            returns=returns,
            name=name,
            reads=reads,
            requires=requires,
            retry=retry,
        )

    def __repr__(self) -> str:
        return "LLMOperation()"


class ClassifyOperation:
    """Public classification operation surface for inline calls and operation steps."""

    def __call__(
        self,
        prompt: PromptInput,
        *,
        choices: Sequence[str],
        retry: int = 3,
        provider: Any | None = None,
        prompt_registry: Any | None = None,
        context: Any | None = None,
        run_folder: Path | None = None,
        policy: ProviderPolicyInput = None,
    ) -> str:
        normalized_prompt = _normalize_simple_prompt(prompt)
        return classify_call(
            normalized_prompt,
            choices=choices,
            retry=retry,
            provider=provider,
            prompt_registry=prompt_registry,
            context=context,
            run_folder=run_folder,
            policy=policy,
        )

    def step(
        self,
        *,
        prompt: PromptInput,
        choices: Sequence[str],
        name: str | None = None,
        reads: Sequence[ArtifactInput] = (),
        requires: Sequence[ArtifactInput] = (),
        retry: int = 3,
    ) -> OperationStepDeclaration:
        return OperationStepDeclaration(
            "classify",
            prompt,
            choices=choices,
            name=name,
            reads=reads,
            requires=requires,
            retry=retry,
        )

    def __repr__(self) -> str:
        return "ClassifyOperation()"


llm = LLMOperation()
classify = ClassifyOperation()


__all__ = [
    "AWAIT_INPUT",
    "FanIn",
    "Continuity",
    "Effects",
    "Event",
    "FAIL",
    "Fail",
    "FINISH",
    "Goto",
    "Json",
    "LLMOperation",
    "Md",
    "ModelEffort",
    "ModelVerbosity",
    "NetworkMode",
    "Outcome",
    "PermissionMode",
    "Policy",
    "PolicyOverride",
    "Prompt",
    "ProviderName",
    "Raw",
    "ReasoningSummary",
    "RequestInput",
    "Route",
    "SELF",
    "Session",
    "SandboxMode",
    "StateVar",
    "Text",
    "ValidationResult",
    "Workflow",
    "WorklistEffect",
    "Worklist",
    "ClassifyOperation",
    "classify",
    "fan_out",
    "llm",
    "parallel",
    "produce_verify_step",
    "python_step",
    "step",
    "validation_step",
    "workflow_step",
]
