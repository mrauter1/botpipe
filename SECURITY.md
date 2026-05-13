# Security Policy

Botpipe is an execution framework for trusted, operator-authored workflows that
run agentic provider harnesses such as Codex CLI and Claude Code. Security
reports are most useful when they identify a mismatch between Botpipe's declared
runtime policy, recorded enforcement state, and the behavior actually delivered
to a provider backend.

## Supported Versions

Until the project reaches a stable release line, security fixes target the
latest released version and the `main` branch.

## Reporting a Vulnerability

Use GitHub private vulnerability reporting when it is enabled for this
repository. If private reporting is not available, contact the repository owner
through a private maintainer channel before opening a public issue.

Please include:

- affected Botpipe version or commit
- provider backend and provider CLI version when relevant
- operating system and Python version
- minimal reproduction steps
- expected policy or security boundary
- observed behavior
- whether credentials, private files, or production data may have been exposed

Do not include live secrets, private customer data, or proprietary source code in
the report. Redacted reproductions are preferred.

We aim to acknowledge vulnerability reports within 3 business days and provide
an initial assessment within 7 business days.

## Security Model

Botpipe treats workflow code, Python handlers, Jinja templates, prompt files,
artifact templates, and provider prompts as trusted author-controlled code. Do
not run untrusted workflows or untrusted templates in a sensitive workspace.

Botpipe provider policy is an execution contract and audit surface. Enforcement
depends on the selected provider backend. If a backend cannot enforce a requested
policy feature, Botpipe must fail by default or record the unsupported behavior
explicitly according to the configured provider-policy validation mode.

Current important boundaries:

- provider sandboxing is backend-dependent
- Codex CLI does not enforce `deny_read` or domain-level network filters through
  the current Botpipe Codex emission surface
- unsupported provider-policy controls fail by default
- workflow and Jinja authors are responsible for the behavior of their own code
  and templates
- Python handlers are local code and are not sandboxed by Botpipe
- provider prompt injection inside an authorized run is not treated as a Botpipe
  sandbox bypass by itself

## In Scope

- Botpipe claiming or recording enforcement that the backend does not provide
- provider-policy emission bugs that expand filesystem, network, env, model, or
  permission access unexpectedly
- unintended reads or writes outside configured workspace or write roots
- secret leakage through logs, traces, events, SDK results, policy reports, or
  retained task directories
- path traversal or unsafe path resolution in workflow loading, prompt loading,
  artifact resolution, state, resume, or trace browsing
- SDK or CLI behavior that exposes another task's run data unexpectedly
- unsafe resume/checkpoint behavior that bypasses policy or corrupts task state

## Out of Scope

- malicious workflow authors
- malicious Jinja templates or prompt files
- a user intentionally selecting unsandboxed or dangerous provider modes
- a user changing provider-policy validation to warn or ignore unsupported
  backend controls
- model output quality, hallucination, or ordinary prompt injection within an
  authorized provider execution
- provider CLI vulnerabilities that Botpipe accurately reports as backend
  behavior rather than Botpipe enforcement

## Public Disclosure

Please allow maintainers reasonable time to investigate and release a fix before
public disclosure. Security advisories should describe the affected versions,
impact, fixed version or commit, and practical mitigation.
