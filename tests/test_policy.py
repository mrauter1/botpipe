from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from botpipe.policy import NetworkMode, PermissionMode, Policy, SandboxMode


def test_policy_round_trip_and_deduplicates_paths() -> None:
    policy = Policy.from_dict(
        {
            "model": "test-model",
            "base_url": "https://provider.invalid",
            "model_overrides": {"review": "test-review"},
            "sandbox_mode": "workspace_write",
            "network": "limited",
            "network_domains": ["example.com", "example.com"],
            "allow_write": ["out", "out"],
            "timeout": 12.5,
        }
    )
    assert policy.network is NetworkMode.LIMITED
    assert policy.allow_write == ("out",)
    assert Policy.from_dict(policy.to_dict()) == policy
    with pytest.raises(FrozenInstanceError):
        policy.model = "changed"  # type: ignore[misc]


def test_policy_merge_only_replaces_authored_fields() -> None:
    base = Policy(
        model="a",
        network=NetworkMode.LIMITED,
        network_domains=("example.com",),
        allow_write=("out",),
    )
    merged = base.merged(Policy(model="b", permission_mode=PermissionMode.ASK))
    assert merged.model == "b"
    assert merged.network_domains == ("example.com",)
    assert merged.allow_write == ("out",)


def test_policy_merge_read_only_clears_inherited_writes() -> None:
    base = Policy(sandbox_mode=SandboxMode.WORKSPACE_WRITE, allow_write=(".",))
    resolved = Policy.resolve(base, Policy(sandbox_mode=SandboxMode.READ_ONLY))
    assert resolved.sandbox_mode is SandboxMode.READ_ONLY
    assert resolved.allow_write == ()


@pytest.mark.parametrize(
    "payload",
    [
        {"network": "limited"},
        {"network": "none", "network_domains": ["example.com"]},
        {"sandbox_mode": "read_only", "allow_write": ["out"]},
        {"sandbox_mode": "workspace_write", "permission_mode": "full_auto_unsandboxed"},
    ],
)
def test_policy_rejects_inconsistent_controls(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        Policy.from_dict(payload)


def test_effective_policy_has_safe_explicit_defaults() -> None:
    policy = Policy().effective()
    assert policy.sandbox_mode is SandboxMode.WORKSPACE_WRITE
    assert policy.permission_mode is PermissionMode.ASK
    assert policy.network is NetworkMode.NONE
    assert policy.allow_write == (".",)
