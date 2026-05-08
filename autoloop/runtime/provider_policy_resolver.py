"""Runtime resolution for authored and configured provider policy layers."""

from __future__ import annotations

from pathlib import Path

from autoloop.policy import PolicyInput, resolve_policy_layer
from autoloop.core.compiler import CompiledStep
from autoloop.core.context import Context
from autoloop.core.provider_policy import (
    ProviderPolicy,
    ResolvedProviderPolicy,
    validate_against_strict_policy,
)

from .config import (
    ProviderConfig,
    ProviderPolicyRuntimeConfig,
    ResolvedRuntimeConfig,
    RuntimeConfig,
)


class ProviderPolicyResolver:
    """Resolve effective provider policy for steps and inline operations."""

    def __init__(
        self,
        *,
        config: ResolvedRuntimeConfig,
        workflow_policy: PolicyInput,
        workspace_root: Path,
    ) -> None:
        self._config = config
        self._workflow_policy = workflow_policy
        self._workspace_root = workspace_root.resolve(strict=False)

    @property
    def config(self) -> ResolvedRuntimeConfig:
        return self._config

    @property
    def workflow_policy(self) -> PolicyInput:
        return self._workflow_policy

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def resolve_for_step(self, step: CompiledStep) -> ResolvedProviderPolicy:
        candidate = resolve_policy_layer(self._config.provider_policy.default, self._workflow_policy)
        candidate = resolve_policy_layer(candidate, step.provider_policy)
        return self._validate(candidate, step_name=step.name)

    def resolve_for_operation(
        self,
        ctx: Context,
        explicit_policy: PolicyInput = None,
    ) -> ResolvedProviderPolicy:
        inherited_policy = getattr(ctx, "_provider_policy", None)
        if isinstance(inherited_policy, ProviderPolicy):
            candidate = resolve_policy_layer(inherited_policy, explicit_policy)
        else:
            candidate = resolve_policy_layer(self._config.provider_policy.default, self._workflow_policy)
            candidate = resolve_policy_layer(candidate, explicit_policy)
        return self._validate(candidate, step_name=getattr(ctx, "_step_name", None))

    def _validate(self, policy: ProviderPolicy, *, step_name: str | None) -> ResolvedProviderPolicy:
        return validate_against_strict_policy(
            policy,
            self._config.provider_policy.strict,
            step_name=step_name,
            workspace_root=self._workspace_root,
        )


def create_provider_policy_resolver(
    *,
    workflow_policy: PolicyInput,
    workspace_root: Path,
    provider_policy: ProviderPolicyRuntimeConfig | None = None,
    runtime: RuntimeConfig | None = None,
    provider: ProviderConfig | None = None,
) -> ProviderPolicyResolver:
    """Build a resolver from the resolved-or-default runtime policy inputs."""

    return ProviderPolicyResolver(
        config=ResolvedRuntimeConfig(
            provider=provider or ProviderConfig(),
            runtime=runtime or RuntimeConfig(),
            provider_policy=provider_policy or ProviderPolicyRuntimeConfig(),
        ),
        workflow_policy=workflow_policy,
        workspace_root=workspace_root,
    )
