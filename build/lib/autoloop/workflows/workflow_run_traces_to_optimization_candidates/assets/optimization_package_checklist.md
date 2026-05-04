# Optimization Package Checklist

- Keep the optimizer candidate-only.
- Keep the selected workflow source package read-only.
- Use runtime-owned `run.json`, `trace.jsonl`, `git_tracking.jsonl`, `static_step_graph.json`, and `raw/` as evidence only.
- Do not claim reruns, ablations, or improvements without explicit evidence.
- Separate observed evidence from inference in every optimization conclusion.
- Prefer local step fixes before workflow-level redesign.
- Publish a no-op packet when no eligible Plan-1 observability bundles exist.
