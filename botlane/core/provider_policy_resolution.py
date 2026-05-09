"""Core provider policy resolver protocol.

Runtime implementations live outside botlane.core.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


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
