# Implement ↔ Code Reviewer Feedback

- Task ID: additional-botlane-rename-requirements-discovere-28c3ecb0
- Pair: implement
- Phase ID: rename-package-and-public-api
- Phase Directory Key: rename-package-and-public-api
- Phase Title: Rename Package And Public API
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` [botlane/runtime/cli.py]
  The installed public CLI still advertises `autoloop` in help text: `_WORKSPACE_HELP` says workspace workflows load from `.autoloop/workflows/`, and `init workflow` still says it scaffolds under `.autoloop/workflows/`. That directly misses P1-AC2 (`entry-point definitions no longer install or advertise autoloop`) and the user’s runtime/CLI identity requirement for public help/description text. Minimal fix: finish the public CLI rename in `botlane/runtime/cli.py` so every maintained help/description string shown by `botlane --help` is Botlane-only, or explicitly defer P1-AC2 instead of marking it complete.

- IMP-002 `blocking` [botlane/workflows/autoloop_v1/__init__.py, botlane/workflows/autoloop_v1/workflow.py, botlane/workflows/autoloop_v1/workflow.toml]
  The distributed `botlane` package still contains a maintained public import path and exported symbol with Autoloop branding: `botlane.workflows.autoloop_v1`, `AutoloopV1`, and alias `autoloop-v1`. That violates P1-AC1’s requirement that no maintained public import path or exported symbol still use Autoloop branding after this phase. Minimal fix: rename or remove this packaged public surface within the `botlane/workflows/autoloop_v1` slice so the shipped package does not expose `Autoloop*` names.

- IMP-003 `non-blocking` [phase re-review]
  Re-review of cycle 2 found IMP-001 and IMP-002 resolved. No remaining blocking findings were identified within the phase-local acceptance boundary; the surviving Autoloop strings under workspace/schema/config surfaces and the `botlane_v1` parity artifact markers match the documented later-phase deferrals and compatibility decision in the run ledger.
