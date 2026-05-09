"""Runtime resolution for authored and configured provider policy layers."""

from __future__ import annotations

from pathlib import Path

from botlane.policy import PolicyInput, resolve_policy_layer
from botlane.core.context import Context
from botlane.core.provider_policy import (
    ProviderPolicy,
    ResolvedProviderPolicy,
    validate_against_strict_policy,
)
from botlane.core.provider_policy_resolution import ProviderPolicyResolverProtocol
from botlane.core.step_plans import StepPlan

from .config import (
    ProviderConfig,
    ProviderPolicyRuntimeConfig,
    ResolvedRuntimeConfig,
    RuntimeConfig,
)


class ProviderPolicyResolver(ProviderPolicyResolverProtocol):
    """Resolve effective provider policy for steps and inline operations."""

    def __init__(
        self,
        *,
        config: ResolvedRuntimeConfig,
        sdk_default_policy: PolicyInput,
        workflow_policy: PolicyInput,
        run_policy: PolicyInput,
        workspace_root: Path,
    ) -> None:
        self._config = config
        self._sdk_default_policy = sdk_default_policy
        self._workflow_policy = workflow_policy
        self._run_policy = run_policy
        self._workspace_root = workspace_root.resolve(strict=False)

    @property
    def config(self) -> ResolvedRuntimeConfig:
        return self._config

    @property
    def workflow_policy(self) -> PolicyInput:
        return self._workflow_policy

    @property
    def sdk_default_policy(self) -> PolicyInput:
        return self._sdk_default_policy

    @property
    def run_policy(self) -> PolicyInput:
        return self._run_policy

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def resolve_for_step(self, step: StepPlan) -> ResolvedProviderPolicy:
        candidate = self._base_candidate()
        candidate = resolve_policy_layer(candidate, step.provider_policy)
        return self._validate(candidate, step_name=step.name)

    def resolve_for_operation(
        self,
        ctx: Context | None,
        explicit_policy: PolicyInput = None,
    ) -> ResolvedProviderPolicy:
        inherited_policy = None if ctx is None else getattr(ctx, "_provider_policy", None)
        if isinstance(inherited_policy, ProviderPolicy):
            candidate = resolve_policy_layer(inherited_policy, explicit_policy)
        else:
            candidate = self._base_candidate()
            candidate = resolve_policy_layer(candidate, explicit_policy)
        return self._validate(candidate, step_name=None if ctx is None else getattr(ctx, "_step_name", None))

    def _base_candidate(self) -> ProviderPolicy:
        candidate = resolve_policy_layer(self._config.provider_policy.default, self._sdk_default_policy)
        candidate = resolve_policy_layer(candidate, self._workflow_policy)
        return resolve_policy_layer(candidate, self._run_policy)

    def _validate(self, policy: ProviderPolicy, *, step_name: str | None) -> ResolvedProviderPolicy:
        return validate_against_strict_policy(
            policy,
            self._config.provider_policy.strict,
            step_name=step_name,
            workspace_root=self._workspace_root,
        )


def create_provider_policy_resolver(
    *,
    sdk_default_policy: PolicyInput = None,
    workflow_policy: PolicyInput,
    workspace_root: Path,
    run_policy: PolicyInput = None,
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
        sdk_default_policy=sdk_default_policy,
        workflow_policy=workflow_policy,
        run_policy=run_policy,
        workspace_root=workspace_root,
    )
