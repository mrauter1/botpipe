"""Core provider policy resolver protocol and shared layer resolution."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .provider_policy import ProviderPolicy, ResolvedProviderPolicy, validate_against_strict_policy


@runtime_checkable
class ProviderPolicyResolverProtocol(Protocol):
    def resolve_for_step(self, step: Any) -> Any:
        ...

    def resolve_for_operation(
        self,
        ctx: Any | None,
        explicit_policy: Any = None,
    ) -> Any:
        ...


class LayeredProviderPolicyResolver(ProviderPolicyResolverProtocol):
    """Resolve provider policy from ordered layers plus an optional strict policy."""

    def __init__(
        self,
        *,
        base_policy: ProviderPolicy,
        policy_layers: Iterable[Any] = (),
        strict_policy: Any | None = None,
        workspace_root: Path,
    ) -> None:
        self._base_policy = base_policy
        self._policy_layers = tuple(policy_layers)
        self._strict_policy = strict_policy
        self._workspace_root = workspace_root

    def resolve_for_step(self, step: Any) -> ResolvedProviderPolicy:
        candidate = self._base_candidate()
        candidate = _resolve_policy_layer(candidate, getattr(step, "provider_policy", None))
        return self._validate(candidate, step_name=getattr(step, "name", None))

    def resolve_for_operation(
        self,
        ctx: Any | None,
        explicit_policy: Any = None,
    ) -> ResolvedProviderPolicy:
        inherited_policy = None if ctx is None else getattr(ctx, "_provider_policy", None)
        if isinstance(inherited_policy, ProviderPolicy):
            candidate = _resolve_policy_layer(inherited_policy, explicit_policy)
        else:
            candidate = self._base_candidate()
            candidate = _resolve_policy_layer(candidate, explicit_policy)
        return self._validate(candidate, step_name=None if ctx is None else getattr(ctx, "_step_name", None))

    def _base_candidate(self) -> ProviderPolicy:
        candidate = self._base_policy
        for layer in self._policy_layers:
            candidate = _resolve_policy_layer(candidate, layer)
        return candidate

    def _validate(self, policy: ProviderPolicy, *, step_name: str | None) -> ResolvedProviderPolicy:
        return validate_against_strict_policy(
            policy,
            self._strict_policy,
            step_name=step_name,
            workspace_root=self._workspace_root,
        )


def _resolve_policy_layer(base: ProviderPolicy, layer: Any) -> ProviderPolicy:
    from botpipe.policy import resolve_policy_layer

    return resolve_policy_layer(base, layer)
