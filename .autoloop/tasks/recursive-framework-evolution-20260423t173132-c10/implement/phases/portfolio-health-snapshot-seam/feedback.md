# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260423t173132-c10
- Pair: implement
- Phase ID: portfolio-health-snapshot-seam
- Phase Directory Key: portfolio-health-snapshot-seam
- Phase Title: Portfolio Health Snapshot Seam
- Scope: phase-local authoritative verifier artifact

- IMP-001 | blocking | `stdlib/portfolio.py:61-80`, `write_workflow_portfolio_health_snapshot(...)`: the helper consumes `statuses` twice. A valid one-shot iterable such as `(status for status in ["paused", "failed"])` is first exhausted by `list_workflow_run_summaries(...)`, then `_normalized_filters(statuses)` re-reads the exhausted iterator and raises `ValueError` even though the caller supplied a legal `Iterable[str]`. Minimal fix: normalize `statuses` once inside `write_workflow_portfolio_health_snapshot(...)`, pass the normalized value to both the runtime summary helper and the serialized payload, and centralize that normalization instead of keeping two slightly different status-normalization paths.
