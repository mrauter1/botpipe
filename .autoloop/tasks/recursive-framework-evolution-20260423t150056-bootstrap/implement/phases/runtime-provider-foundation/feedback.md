# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260423t150056-bootstrap
- Pair: implement
- Phase ID: runtime-provider-foundation
- Phase Directory Key: runtime-provider-foundation
- Phase Title: Shared Provider Foundation
- Scope: phase-local authoritative verifier artifact
- Reviewed the runtime provider foundation implementation across the new runtime provider package, backend dispatch, focused tests, docs, and phase notes artifacts.
- IMP-001 `blocking`: [runtime/providers/claude.py] `verify_claude_code_capabilities()` / `_validate_claude_surface()` unconditionally require `--allowedTools` and `--dangerously-skip-permissions`, even when the configured permission strategy is the default `inherit` and the adapter will never pass either flag. That makes backend resolution fail on otherwise valid Claude CLI installations that support the required automation surface (`-p`/`--print`, `--output-format`, `--resume`, `--model`) but omit one unused permission flag. Local repro in the review shell: building `ClaudeProvider` with `permission_strategy='inherit'` and a mocked help surface containing only the headless flags raises `ConfigError: provider 'claude' requires '--allowedTools' support, but the flag is unavailable.` Minimal fix: make permission-flag capability checks conditional on the selected `provider.claude.permission_strategy`, keep the always-used headless flags unconditional, and add focused tests for the `inherit` path so unused permission controls do not block provider resolution.
