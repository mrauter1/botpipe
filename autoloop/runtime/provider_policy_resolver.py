"""Runtime resolution for authored and configured provider policy layers."""

from __future__ import annotations

from pathlib import Path

from autoloop.core.compiler import CompiledStep
from autoloop.core.context import Context
from autoloop.core.provider_policy import (
    ProviderPolicy,
    ProviderPolicyOverride,
    ResolvedProviderPolicy,
    SYSTEM_DEFAULT_PROVIDER_POLICY,
    merge_provider_policies,
    validate_against_strict_policy,
)

from .config import ResolvedRuntimeConfig


class ProviderPolicyResolver:
    """Resolve effective provider policy for steps and inline operations."""

    def __init__(
        self,
        *,
        config: ResolvedRuntimeConfig,
        workflow_policy: ProviderPolicy | None,
        workspace_root: Path,
    ) -> None:
        self._config = config
        self._workflow_policy = workflow_policy
        self._workspace_root = workspace_root.resolve(strict=False)

    @property
    def config(self) -> ResolvedRuntimeConfig:
        return self._config

    @property
    def workflow_policy(self) -> ProviderPolicy | None:
        return self._workflow_policy

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def resolve_for_step(self, step: CompiledStep) -> ResolvedProviderPolicy:
        return self._validate(
            merge_provider_policies(
                SYSTEM_DEFAULT_PROVIDER_POLICY,
                self._config.provider_policy.default,
                self._workflow_policy,
                step.provider_policy,
            ),
            step_name=step.name,
        )

    def resolve_for_operation(
        self,
        ctx: Context,
        explicit_policy: ProviderPolicy | ProviderPolicyOverride | None = None,
    ) -> ResolvedProviderPolicy:
        inherited_policy = getattr(ctx, "_provider_policy", None)
        if isinstance(inherited_policy, ProviderPolicy):
            candidate = merge_provider_policies(inherited_policy, explicit_policy)
        else:
            candidate = merge_provider_policies(
                SYSTEM_DEFAULT_PROVIDER_POLICY,
                self._config.provider_policy.default,
                self._workflow_policy,
                explicit_policy,
            )
        return self._validate(candidate, step_name=getattr(ctx, "_step_name", None))

    def _validate(self, policy: ProviderPolicy, *, step_name: str | None) -> ResolvedProviderPolicy:
        return validate_against_strict_policy(
            policy,
            self._config.provider_policy.strict,
            step_name=step_name,
            workspace_root=self._workspace_root,
        )
