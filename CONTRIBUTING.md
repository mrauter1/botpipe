# Contributing to Botpipe

Botpipe has one runtime behind the SDK and CLI. Contributions should preserve
its central invariant: Python owns control flow, and every material observation
or external effect goes through a recorded operation.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m pytest -q
```

Use `FakeProvider` in tests. Tests that invoke a real provider CLI must be
isolated and opt-in.

## Design rules

- Add durable behavior to the SDK/runtime first; keep the CLI as parsing and
  formatting over that surface.
- Use ordinary Python for workflow control flow. Do not add graph compilation,
  routes, transition tables, or a second interpreter.
- Record operation intent before an effect and commit durable output before its
  ledger result. Never retry an uncertain effect implicitly.
- Give concurrent branches stable scopes independent of scheduling order.
- Keep committed operation outcomes immutable and fail on replay mismatch.
- Treat workflow source and prompt templates as trusted code. Provider policy is
  a separate boundary and must fail when requested controls cannot be enforced.
- Inspect only declared callable contracts before a run and observed operations
  afterward. Do not claim a complete static topology for Python.
- Public API changes need focused behavior tests and documentation.

## Pull requests

Explain the user-visible problem, the resulting behavior, and how it was tested.
Call out changes to provider policy, network or filesystem access, environment
handling, prompt rendering, persistence, resume, cancellation, or interruption
reconciliation.

Do not include secrets, raw provider transcripts, local state databases, receipt
directories, virtual environments, or generated caches. AI-assisted
contributions are welcome; the contributor remains responsible for correctness,
licensing, and provenance.

Contributions are licensed under Apache-2.0.
