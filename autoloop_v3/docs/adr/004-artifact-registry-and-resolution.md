# ADR 004: Artifact Registry And Resolution

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `6. Artifact Registry And Resolution`

Final decision:
- Artifact declarations are compiled into one workflow-wide registry.
- Templates resolve generically from `task_folder`, `run_folder`, and dot-path state access.
- Steps declare required and produced artifacts explicitly and receive resolved handles.
- Workflow-specific path conventions stay in workflow code, not in the runtime core.

Rejected shape:
- no ad hoc file-path handling inside step handlers
- no runtime-owned artifact conventions for individual workflows
- no hidden artifact lookup rules
