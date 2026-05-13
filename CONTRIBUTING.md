# Contributing to Botpipe

Botpipe is a runtime framework for trusted agentic workflows. Contributions are
welcome when they preserve the framework's core shape: one implementation behind
the SDK and CLI, explicit provider policy, inspectable run state, and strict
runtime boundaries.

## Development Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pytest
```

Run tests:

```bash
python -m pytest -q
```

Some packaging smoke tests may need normal package-build cache access depending
on the local sandbox. Do not hide unrelated failures behind a packaging-cache
failure.

## Contribution Rules

- Keep the SDK and CLI behavior on one runtime implementation. The CLI should be
  argument parsing plus formatting over the SDK/runtime surface.
- Do not add CLI-only behavior when the same capability belongs in the SDK.
- Prefer compile-time rejection for deterministic authoring errors.
- Keep provider-specific enforcement checks at provider-policy emission time,
  where the backend target is known.
- Do not claim a backend enforces a policy feature unless Botpipe can prove or
  emit it accurately.
- Unsupported provider-policy controls must fail by default or be explicitly
  recorded when the user configures warning behavior.
- Treat workflows, Python handlers, prompt files, and Jinja templates as trusted
  code. Do not add misleading sandbox claims around template rendering.
- Avoid compatibility shims unless they preserve persisted run data or an
  explicitly documented public contract.
- Public API changes require docs and focused tests.
- Prefer fake providers and deterministic fixtures in tests. Tests that require
  real provider CLIs should be clearly isolated.

## Pull Request Checklist

Before opening a PR, make sure the change:

- has a clear user-facing or maintenance reason
- is scoped to the relevant subsystem
- includes tests for changed runtime, SDK, CLI, policy, or template behavior
- updates documentation when public behavior changes
- does not weaken provider-policy reporting or enforcement
- does not leak secrets through logs, traces, policy reports, or fixtures
- keeps generated caches, local state, and build artifacts out of the commit
- passes the relevant focused tests and, when practical, the full suite

## Security-Sensitive Changes

Call out security-sensitive changes explicitly in the PR description when they
touch:

- provider policy
- sandbox or filesystem behavior
- network policy
- environment variable handling
- prompt/template rendering
- task state, run state, traces, events, or retention
- resume behavior
- provider adapters

For these changes, include what the backend can enforce, what Botpipe records,
and what happens when enforcement is unsupported.

## AI-Assisted Contributions

AI-assisted contributions are allowed. Contributors are responsible for the final
patch, tests, licensing, and provenance. Do not submit proprietary code,
private prompts, private data, or generated code that you do not have the right
to contribute.

## License

By contributing to Botpipe, you agree that your contribution is licensed under
the Apache License, Version 2.0, unless you explicitly state otherwise in
writing.
