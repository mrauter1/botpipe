# Implement ↔ Code Reviewer Feedback

- Task ID: implementation-goal-add-a-first-class-provider-p-5e755cae
- Pair: implement
- Phase ID: policy-claude-regression
- Phase Directory Key: policy-claude-regression
- Phase Title: Claude Emission And Regression Sweep
- Scope: phase-local authoritative verifier artifact

## Findings

- `IMP-001` `blocking` [autoloop/runtime/providers/claude_policy.py:87-145]
  The Claude emitter now relies on `--settings <run_dir>/.../settings.json` as the policy seam, but Claude settings merge across command-line, local, project, and user scopes. That means an existing repo or user `.claude/settings*.json` can contribute additional `sandbox.filesystem.allowWrite`, `permissions.allow`, or `network.allowedDomains` entries that exceed the already-validated resolved policy, so a step that passed Autoloop strict-policy validation can still run with broader Claude-side privileges. Minimal fix: isolate policy-backed Claude turns from ambient Claude settings sources instead of layering `--settings` on top of them, and keep session continuity inside that runtime-owned isolation seam rather than depending on global/project config merging.

- `IMP-002` `blocking` [autoloop/runtime/providers/claude.py:_prepare_turn_command() lines 336-362, autoloop/runtime/config.py:518-563]
  Existing `provider.claude.permission_strategy=bypass` behavior no longer survives normal engine-backed turns. Once a turn has a resolved policy and run folder, `_prepare_turn_command()` keeps only the additive `allow_core_tools` branch and drops the legacy `bypass` branch entirely, even though the request explicitly says existing Claude `permission_strategy` settings must keep working. This is a compatibility regression for existing Claude users who rely on `bypass` without authoring a new `provider_policy`. Minimal fix: decide the compatibility mapping before transport emission, ideally by mirroring legacy Claude `permission_strategy` into the resolved default provider policy during config resolution or resolver construction instead of conditionally discarding it in the transport.

- `IMP-003` `blocking` [autoloop/runtime/providers/claude_policy.py:262-284]
  AC-1 requires lossy warnings when native sandbox filesystem support is unavailable, but the current lossy check only fires when filesystem settings differ from the default `allow_read=["."]` / `allow_write=["."]` shape or add deny rules. Under a degraded Claude capability profile with the default workspace-write sandbox, the emitter falls back to permission rules while still reporting `decision="ok"`, so operators get no warning even though OS-level filesystem enforcement is missing. Minimal fix: whenever sandboxed filesystem enforcement is expected and `supports_sandbox_filesystem=False`, emit a lossy capability finding for the fallback path, including the default workspace-write case.
