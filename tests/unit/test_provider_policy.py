from __future__ import annotations

from pathlib import Path

import pytest

from autoloop.core.provider_policy import (
    SYSTEM_DEFAULT_PROVIDER_POLICY,
    PermissionPolicy,
    ProviderPolicy,
    ProviderPolicyError,
    ProviderPolicyOverride,
    SandboxPolicy,
    StrictProviderPolicy,
    StrictSandboxPolicy,
    StrictWorkspaceFilesystemPolicy,
    StrictWorkspaceNetworkPolicy,
    StrictWorkspacePolicy,
    WorkspaceFilesystemPolicy,
    WorkspaceNetworkPolicy,
    WorkspacePolicy,
    merge_provider_policies,
    policy_fingerprint,
    validate_against_strict_policy,
)


def test_system_default_policy_matches_requested_baseline() -> None:
    policy = SYSTEM_DEFAULT_PROVIDER_POLICY

    assert policy.permissions.mode == "full_auto_sandboxed"
    assert policy.permissions.allow_dangerous_bypass is False
    assert policy.permissions.disable_dangerous_bypass is True
    assert policy.sandbox.enabled is True
    assert policy.sandbox.required is True
    assert policy.sandbox.mode == "workspace_write"
    assert policy.sandbox.workspace.filesystem.allow_read == (".",)
    assert policy.sandbox.workspace.filesystem.allow_write == (".",)
    assert policy.sandbox.workspace.network.enabled is True
    assert policy.sandbox.workspace.network.mode == "full"
    assert policy.env.inherit == "core"
    assert policy.env.deny == ("*TOKEN*", "*SECRET*", "*KEY*")


def test_merge_provider_policies_applies_scalar_union_and_replace_rules() -> None:
    base = ProviderPolicy(
        permissions=PermissionPolicy(mode="ask", deny=("Shell(rm -rf)",), allow=("Read",)),
        sandbox=SandboxPolicy(
            workspace=WorkspacePolicy(
                filesystem=WorkspaceFilesystemPolicy(
                    allow_write=(".", "./build"),
                    deny_read=("./.env",),
                    deny_write=("/etc",),
                ),
                network=WorkspaceNetworkPolicy(deny_domains=("blocked.example",)),
            )
        ),
        env={"deny": ("*TOKEN*",), "set": {"A": "1"}},
        codex={"sandbox_workspace_write": {"network_access": False}},
    )
    override = ProviderPolicyOverride(
        permissions=PermissionPolicy(mode="auto_edit", deny=("Shell(rm -rf)", "Shell(curl)"), allow=("Edit",)),
        sandbox=SandboxPolicy(
            workspace=WorkspacePolicy(
                filesystem=WorkspaceFilesystemPolicy(
                    allow_write=("./dist",),
                    deny_read=("./secrets/**",),
                    deny_write=("/usr/local/bin",),
                ),
                network=WorkspaceNetworkPolicy(deny_domains=("denied.example",)),
            )
        ),
        env={"deny": ("*SECRET*",), "set": {"B": "2"}},
        codex={"sandbox_workspace_write": {"writable_roots": [".", "./dist"]}},
    )

    merged = merge_provider_policies(base, override)

    assert merged.permissions.mode == "auto_edit"
    assert merged.permissions.allow == ("Edit",)
    assert merged.permissions.deny == ("Shell(rm -rf)", "Shell(curl)")
    assert merged.sandbox.workspace.filesystem.allow_write == ("./dist",)
    assert merged.sandbox.workspace.filesystem.deny_read == ("./.env", "./secrets/**")
    assert merged.sandbox.workspace.filesystem.deny_write == ("/etc", "/usr/local/bin")
    assert merged.sandbox.workspace.network.deny_domains == ("blocked.example", "denied.example")
    assert merged.env.deny == ("*TOKEN*", "*SECRET*")
    assert merged.env.set == {"A": "1", "B": "2"}
    assert merged.codex == {
        "sandbox_workspace_write": {
            "network_access": False,
            "writable_roots": [".", "./dist"],
        }
    }


def test_strict_policy_rejects_danger_full_access() -> None:
    policy = merge_provider_policies(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        ProviderPolicyOverride(
            permissions=PermissionPolicy(mode="full_auto_unsandboxed", allow_dangerous_bypass=True),
            sandbox=SandboxPolicy(mode="danger_full_access"),
        ),
    )

    with pytest.raises(ProviderPolicyError, match="sandbox.mode='danger_full_access' exceeds strict"):
        validate_against_strict_policy(policy, StrictProviderPolicy(), step_name="implement")


def test_strict_policy_rejects_disabled_sandbox_when_required() -> None:
    policy = merge_provider_policies(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        ProviderPolicyOverride(
            permissions=PermissionPolicy(mode="ask"),
            sandbox=SandboxPolicy(enabled=False, required=False),
        ),
    )

    with pytest.raises(ProviderPolicyError, match="sandbox.enabled=False violates strict sandbox.required=True"):
        validate_against_strict_policy(policy, StrictProviderPolicy(), step_name="review")


def test_strict_policy_injects_required_denies_without_mutating_input() -> None:
    policy = merge_provider_policies(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        ProviderPolicyOverride(
            sandbox=SandboxPolicy(
                workspace=WorkspacePolicy(
                    filesystem=WorkspaceFilesystemPolicy(
                        deny_read=("existing-read",),
                        deny_write=("existing-write",),
                    ),
                    network=WorkspaceNetworkPolicy(deny_domains=("already-blocked.example",)),
                )
            ),
            env={"deny": ("EXISTING_*",)},
        ),
    )

    resolved = validate_against_strict_policy(policy, StrictProviderPolicy(), workspace_root=Path.cwd())

    assert policy.sandbox.workspace.filesystem.deny_read == ("existing-read",)
    assert policy.sandbox.workspace.filesystem.deny_write == ("existing-write",)
    assert policy.sandbox.workspace.network.deny_domains == ("already-blocked.example",)
    assert policy.env.deny == ("EXISTING_*",)
    assert resolved.sandbox.workspace.filesystem.deny_read == ("existing-read", "./.env", "./secrets/**")
    assert resolved.sandbox.workspace.filesystem.deny_write == (
        "existing-write",
        "/etc",
        "/usr/local/bin",
    )
    assert resolved.sandbox.workspace.network.deny_domains == ("already-blocked.example",)
    assert resolved.env.deny == ("EXISTING_*", "*TOKEN*", "*SECRET*", "*KEY*")


def test_strict_policy_rejects_write_path_outside_allowed_roots_with_step_context(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    policy = merge_provider_policies(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        ProviderPolicyOverride(
            sandbox=SandboxPolicy(
                workspace=WorkspacePolicy(
                    filesystem=WorkspaceFilesystemPolicy(allow_write=("/tmp",)),
                )
            )
        ),
    )

    with pytest.raises(ProviderPolicyError) as exc_info:
        validate_against_strict_policy(policy, StrictProviderPolicy(), step_name="implement", workspace_root=workspace_root)

    message = str(exc_info.value)
    assert "Provider policy violation for step 'implement':" in message
    assert "sandbox.workspace.filesystem.allow_write='/tmp'" in message


def test_strict_policy_rejects_local_binding_when_forbidden() -> None:
    policy = merge_provider_policies(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        ProviderPolicyOverride(
            sandbox=SandboxPolicy(
                workspace=WorkspacePolicy(
                    network=WorkspaceNetworkPolicy(allow_local_binding=True),
                )
            )
        ),
    )

    with pytest.raises(ProviderPolicyError, match="allow_local_binding=True"):
        validate_against_strict_policy(policy, StrictProviderPolicy())


def test_strict_policy_rejects_domains_outside_allowed_domains() -> None:
    policy = merge_provider_policies(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        ProviderPolicyOverride(
            sandbox=SandboxPolicy(
                workspace=WorkspacePolicy(
                    network=WorkspaceNetworkPolicy(
                        mode="limited",
                        allow_domains=("evil.example",),
                    )
                )
            )
        ),
    )
    strict = StrictProviderPolicy(
        sandbox=StrictSandboxPolicy(
            workspace=StrictWorkspacePolicy(
                network=StrictWorkspaceNetworkPolicy(allowed_domains=("github.com", "*.npmjs.org"))
            )
        )
    )

    with pytest.raises(ProviderPolicyError, match="evil.example"):
        validate_against_strict_policy(policy, strict)


def test_strict_policy_detects_symlink_escape_according_to_policy(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    outside_root = tmp_path / "outside"
    workspace_root.mkdir()
    outside_root.mkdir()
    (workspace_root / "link").symlink_to(outside_root, target_is_directory=True)
    policy = merge_provider_policies(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        ProviderPolicyOverride(
            sandbox=SandboxPolicy(
                workspace=WorkspacePolicy(
                    filesystem=WorkspaceFilesystemPolicy(allow_write=("link/output.txt",)),
                )
            )
        ),
    )
    strict = StrictProviderPolicy(
        sandbox=StrictSandboxPolicy(
            workspace=StrictWorkspacePolicy(
                filesystem=StrictWorkspaceFilesystemPolicy(
                    allowed_write_roots=("link",),
                    allow_symlink_escape=False,
                )
            )
        )
    )

    with pytest.raises(ProviderPolicyError, match="symlink traversal"):
        validate_against_strict_policy(policy, strict, workspace_root=workspace_root)

    relaxed = strict.model_copy(
        update={
            "sandbox": strict.sandbox.model_copy(
                update={
                    "workspace": strict.sandbox.workspace.model_copy(
                        update={
                            "filesystem": strict.sandbox.workspace.filesystem.model_copy(
                                update={"allow_symlink_escape": True}
                            )
                        }
                    )
                }
            )
        }
    )

    resolved = validate_against_strict_policy(policy, relaxed, workspace_root=workspace_root)
    assert resolved.sandbox.workspace.filesystem.allow_write == ("link/output.txt",)


def test_policy_fingerprint_is_stable_for_equivalent_policies() -> None:
    left = ProviderPolicy(
        sandbox=SandboxPolicy(
            workspace=WorkspacePolicy(
                filesystem=WorkspaceFilesystemPolicy(deny_read=("./.env", "./.env")),
            )
        ),
        env={"set": {"B": "2", "A": "1"}},
    )
    right = ProviderPolicy(
        sandbox=SandboxPolicy(
            workspace=WorkspacePolicy(
                filesystem=WorkspaceFilesystemPolicy(deny_read=("./.env",)),
            )
        ),
        env={"set": {"A": "1", "B": "2"}},
    )

    assert policy_fingerprint(left) == policy_fingerprint(right)
