"""Runtime resolution for authored and configured provider policy layers."""

from __future__ import annotations

from pathlib import Path

from botpipe.policy import PolicyInput
from botpipe.core.provider_policy_resolution import LayeredProviderPolicyResolver

from .config import (
    ProviderConfig,
    ProviderPolicyRuntimeConfig,
    ResolvedRuntimeConfig,
    RuntimeConfig,
)


class ProviderPolicyResolver(LayeredProviderPolicyResolver):
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
        super().__init__(
            base_policy=config.provider_policy.default,
            policy_layers=(sdk_default_policy, workflow_policy, run_policy),
            strict_policy=config.provider_policy.strict,
            workspace_root=workspace_root.resolve(strict=False),
        )

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
