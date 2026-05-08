from __future__ import annotations

import json
from pathlib import Path
import tomllib

import pytest

from botlane.core.errors import ProviderExecutionError
from botlane.core.provider_policy import (
    PermissionPolicy,
    ProviderPolicy,
    ProviderPolicyOverride,
    ProviderPolicyValidationConfig,
    SandboxPolicy,
    SYSTEM_DEFAULT_PROVIDER_POLICY,
    WorkspaceFilesystemPolicy,
    WorkspaceNetworkPolicy,
    WorkspacePolicy,
    merge_provider_policies,
)
from botlane.runtime.providers.claude_policy import ClaudeCapabilities, ClaudePolicyEmitter
from botlane.runtime.providers.codex_policy import CodexPolicyEmitter


def _emit(
    tmp_path: Path,
    policy: ProviderPolicy,
    *,
    validation: ProviderPolicyValidationConfig | None = None,
):
    emitter = CodexPolicyEmitter()
    return emitter.emit(
        policy,
        run_dir=tmp_path,
        step_key="implement__visit-1",
        validation=validation or ProviderPolicyValidationConfig(),
        step_name="implement",
    )


def _emit_claude(
    tmp_path: Path,
    policy: ProviderPolicy,
    *,
    validation: ProviderPolicyValidationConfig | None = None,
    capabilities: ClaudeCapabilities | None = None,
    workspace_root: Path | None = None,
):
    emitter = ClaudePolicyEmitter(capabilities=capabilities)
    return emitter.emit(
        policy,
        run_dir=tmp_path,
        step_key="implement__visit-1",
        validation=validation or ProviderPolicyValidationConfig(),
        step_name="implement",
        workspace_root=workspace_root,
    )


def test_codex_emitter_full_auto_sandboxed_emits_workspace_write_config(tmp_path: Path) -> None:
    policy = merge_provider_policies(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        ProviderPolicyOverride(
            sandbox=SandboxPolicy(
                workspace=WorkspacePolicy(
                    filesystem=WorkspaceFilesystemPolicy(allow_write=(".", "./build", "./dist")),
                    network=WorkspaceNetworkPolicy(enabled=True, mode="full"),
                )
            )
        ),
    )

    emission = _emit(tmp_path, policy)
    config_path = emission.config_files["config"]
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))

    assert config_path == tmp_path / "provider_policy" / "implement__visit-1" / "codex" / "config.toml"
    assert config["approval_policy"] == "never"
    assert config["sandbox_mode"] == "workspace-write"
    assert config["sandbox_workspace_write"]["writable_roots"] == [".", "./build", "./dist"]
    assert config["sandbox_workspace_write"]["network_access"] is True
    assert emission.env["CODEX_HOME"] == str(config_path.parent)


def test_codex_emitter_records_unsupported_deny_read_with_warn_validation(tmp_path: Path) -> None:
    policy = merge_provider_policies(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        ProviderPolicyOverride(
            sandbox=SandboxPolicy(
                workspace=WorkspacePolicy(
                    filesystem=WorkspaceFilesystemPolicy(deny_read=("./.env",)),
                )
            )
        ),
    )

    emission = _emit(
        tmp_path,
        policy,
        validation=ProviderPolicyValidationConfig(unsupported="warn"),
    )

    assert emission.capability_report.decision == "warn"
    assert emission.capability_report.unsupported == (
        "sandbox.workspace.filesystem.deny_read is not enforced by Codex",
    )
    report = json.loads(emission.config_files["capability_report"].read_text(encoding="utf-8"))
    assert report["decision"] == "warn"


def test_codex_emitter_records_unsupported_domain_filters(tmp_path: Path) -> None:
    policy = merge_provider_policies(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        ProviderPolicyOverride(
            sandbox=SandboxPolicy(
                workspace=WorkspacePolicy(
                    network=WorkspaceNetworkPolicy(
                        allow_domains=("github.com",),
                        deny_domains=("example.com",),
                    )
                )
            )
        ),
    )

    emission = _emit(
        tmp_path,
        policy,
        validation=ProviderPolicyValidationConfig(unsupported="warn"),
    )

    assert emission.capability_report.decision == "warn"
    assert emission.capability_report.unsupported == (
        "sandbox.workspace.network domain allow/deny filters are not enforced by Codex",
    )


def test_codex_emitter_raises_when_unsupported_validation_is_fail(tmp_path: Path) -> None:
    policy = merge_provider_policies(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        ProviderPolicyOverride(
            sandbox=SandboxPolicy(
                workspace=WorkspacePolicy(
                    filesystem=WorkspaceFilesystemPolicy(deny_read=("./.env",)),
                )
            )
        ),
    )

    with pytest.raises(ProviderExecutionError, match="provider policy capability validation failed"):
        _emit(tmp_path, policy)

    report_path = tmp_path / "provider_policy" / "implement__visit-1" / "codex" / "capability_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["decision"] == "fail"


def test_codex_emitter_raises_for_unsafe_expansion_when_read_roots_are_narrowed(tmp_path: Path) -> None:
    policy = merge_provider_policies(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        ProviderPolicyOverride(
            sandbox=SandboxPolicy(
                workspace=WorkspacePolicy(
                    filesystem=WorkspaceFilesystemPolicy(allow_read=("./src",)),
                )
            )
        ),
    )

    with pytest.raises(ProviderExecutionError, match="unsafe"):
        _emit(tmp_path, policy)


def test_codex_emitter_does_not_claim_read_root_enforcement_for_narrowed_allow_read(tmp_path: Path) -> None:
    policy = merge_provider_policies(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        ProviderPolicyOverride(
            sandbox=SandboxPolicy(
                workspace=WorkspacePolicy(
                    filesystem=WorkspaceFilesystemPolicy(allow_read=("./src",)),
                )
            )
        ),
    )

    emission = _emit(
        tmp_path,
        policy,
        validation=ProviderPolicyValidationConfig(unsafe_expansion="warn"),
    )

    assert emission.capability_report.decision == "warn"
    assert emission.capability_report.unsafe_expansions == (
        "sandbox.workspace.filesystem.allow_read cannot be narrowed by Codex",
    )
    assert emission.capability_report.effective_enforcement.read_roots == ()
    report = json.loads(emission.config_files["capability_report"].read_text(encoding="utf-8"))
    assert report["effective_enforcement"]["read_roots"] == []


def test_codex_emitter_uses_warn_mode_for_lossy_read_only_allow_write(tmp_path: Path) -> None:
    policy = ProviderPolicy(
        permissions=PermissionPolicy(mode="ask"),
        sandbox=SandboxPolicy(
            mode="read_only",
            workspace=WorkspacePolicy(
                filesystem=WorkspaceFilesystemPolicy(allow_write=("./dist",)),
            ),
        ),
    )

    emission = _emit(
        tmp_path,
        policy,
        validation=ProviderPolicyValidationConfig(lossy_mapping="warn"),
    )

    assert emission.capability_report.decision == "warn"
    assert emission.capability_report.lossy == (
        "sandbox.mode='read_only' ignores filesystem.allow_write in Codex",
    )


def test_claude_emitter_maps_allow_write_and_disable_bypass(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    policy = merge_provider_policies(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        ProviderPolicyOverride(
            model={"default": "claude-sonnet-4-6"},
            sandbox=SandboxPolicy(
                workspace=WorkspacePolicy(
                    filesystem=WorkspaceFilesystemPolicy(allow_write=(".", "./build", "./dist")),
                )
            ),
        ),
    )

    emission = _emit_claude(tmp_path, policy, workspace_root=workspace_root)
    settings_path = emission.config_files["settings"]
    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    assert settings_path == tmp_path / "provider_policy" / "implement__visit-1" / "claude" / "settings.json"
    assert settings["model"] == "claude-sonnet-4-6"
    assert settings["permissions"]["defaultMode"] == "auto"
    assert settings["permissions"]["disableBypassPermissionsMode"] == "disable"
    assert settings["sandbox"]["filesystem"]["allowWrite"] == [
        str(workspace_root.resolve()),
        str((workspace_root / "build").resolve()),
        str((workspace_root / "dist").resolve()),
    ]
    assert settings["sandbox"]["enabled"] is True
    assert emission.cli_args == ("--settings", str(settings_path), "--add-dir", str(workspace_root.resolve()))
    assert emission.env["CLAUDE_CONFIG_DIR"] == str(tmp_path / "provider_policy" / "claude_runtime")
    assert emission.env["CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD"] == "1"


def test_claude_emitter_maps_deny_read_and_deny_write_to_sandbox_and_permission_rules(tmp_path: Path) -> None:
    policy = merge_provider_policies(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        ProviderPolicyOverride(
            sandbox=SandboxPolicy(
                workspace=WorkspacePolicy(
                    filesystem=WorkspaceFilesystemPolicy(
                        deny_read=("./.env",),
                        deny_write=("/etc",),
                    ),
                )
            )
        ),
    )

    emission = _emit_claude(tmp_path, policy)
    settings = json.loads(emission.config_files["settings"].read_text(encoding="utf-8"))

    assert settings["sandbox"]["filesystem"]["denyRead"] == ["./.env"]
    assert settings["sandbox"]["filesystem"]["denyWrite"] == ["/etc"]
    assert "Read(./.env)" in settings["permissions"]["deny"]
    assert "Edit(//etc)" in settings["permissions"]["deny"]


def test_claude_emitter_maps_network_domains(tmp_path: Path) -> None:
    policy = merge_provider_policies(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        ProviderPolicyOverride(
            sandbox=SandboxPolicy(
                workspace=WorkspacePolicy(
                    network=WorkspaceNetworkPolicy(
                        mode="limited",
                        allow_domains=("github.com", "*.npmjs.org"),
                        deny_domains=("example.com",),
                    ),
                )
            )
        ),
    )

    emission = _emit_claude(tmp_path, policy)
    settings = json.loads(emission.config_files["settings"].read_text(encoding="utf-8"))

    assert settings["sandbox"]["network"]["allowedDomains"] == ["github.com", "*.npmjs.org"]
    assert settings["sandbox"]["network"]["deniedDomains"] == ["example.com"]
    assert "WebFetch(domain:github.com)" in settings["permissions"]["allow"]
    assert "WebFetch(domain:example.com)" in settings["permissions"]["deny"]


def test_claude_emitter_marks_filesystem_capability_lossy_when_native_support_is_missing(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    policy = merge_provider_policies(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        ProviderPolicyOverride(
            sandbox=SandboxPolicy(
                workspace=WorkspacePolicy(
                    filesystem=WorkspaceFilesystemPolicy(
                        allow_write=(".", "./dist"),
                        deny_read=("./.env",),
                    ),
                )
            )
        ),
    )

    emission = _emit_claude(
        tmp_path,
        policy,
        validation=ProviderPolicyValidationConfig(lossy_mapping="warn"),
        capabilities=ClaudeCapabilities(supports_sandbox_filesystem=False),
        workspace_root=workspace_root,
    )
    settings = json.loads(emission.config_files["settings"].read_text(encoding="utf-8"))

    assert emission.capability_report.decision == "warn"
    assert emission.capability_report.lossy == (
        "sandbox.filesystem native enforcement unavailable; emitted Read/Edit permission rules only",
    )
    assert settings["permissions"]["allow"].count(f"Edit(//{(workspace_root / 'dist').resolve().as_posix().lstrip('/')})") == 1
    assert settings["permissions"]["deny"].count(
        f"Read(//{(workspace_root / '.env').resolve().as_posix().lstrip('/')})"
    ) == 1
    assert emission.capability_report.effective_enforcement.write_roots == ()
    assert "filesystem" not in settings.get("sandbox", {})


def test_claude_emitter_marks_default_workspace_write_lossy_when_native_support_is_missing(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    emission = _emit_claude(
        tmp_path,
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        validation=ProviderPolicyValidationConfig(lossy_mapping="warn"),
        capabilities=ClaudeCapabilities(supports_sandbox_filesystem=False),
        workspace_root=workspace_root,
    )

    assert emission.capability_report.decision == "warn"
    assert emission.capability_report.lossy == (
        "sandbox.filesystem native enforcement unavailable; emitted Read/Edit permission rules only",
    )


def test_claude_emitter_raises_when_lossy_mapping_is_fail(tmp_path: Path) -> None:
    policy = merge_provider_policies(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        ProviderPolicyOverride(
            sandbox=SandboxPolicy(
                workspace=WorkspacePolicy(
                    filesystem=WorkspaceFilesystemPolicy(allow_write=(".", "./dist")),
                )
            )
        ),
    )

    with pytest.raises(ProviderExecutionError, match="provider policy capability validation failed"):
        _emit_claude(
            tmp_path,
            policy,
            validation=ProviderPolicyValidationConfig(lossy_mapping="fail"),
            capabilities=ClaudeCapabilities(supports_sandbox_filesystem=False),
        )
