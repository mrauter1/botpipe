# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-revised-standalone-correction-spec-a9877342
- Pair: implement
- Phase ID: runtime-cli-workspace-flag
- Phase Directory Key: runtime-cli-workspace-flag
- Phase Title: Runtime CLI Workspace Flag
- Scope: phase-local authoritative verifier artifact

- IMP-001 | blocking | `autoloop/runtime/cli.py:43-60` shared `--workspace` arguments still inherit the internal `dest="root"` metavar, so public help renders `--workspace ROOT` in usage and option help. This contradicts the phase contract and spec requirement that runtime CLI help text describe the user directory as the workspace and avoid leaking the old root terminology. Concrete failure: `cli.build_arg_parser().format_help()` and `workflows list --help` currently expose `ROOT`, so a user following help still sees the removed public name. Minimal fix: set an explicit `metavar="WORKSPACE"` (or equivalent centralized override) on both shared parser arguments and extend the help assertions in the runtime CLI tests to reject `ROOT` in help output, not just `--root`.

- Review cycle 2: IMP-001 no longer reproduces after the shared `--workspace` arguments gained `metavar="WORKSPACE"` and the runtime CLI help assertions were strengthened to reject `ROOT`. No additional findings.
