# Native provider capability evidence

Observed 2026-09-21 for the provider-first rewrite. This file records the
implementation profile separately from the completed-release gate. A profile
is advertised by code only when the adapter can configure the documented
native surface and reject unsupported requests before dispatch. Native support
still requires pinned-version integration receipts on each supported platform.

## Implemented matrix

| Adapter profile | Generate, empty grants | Exact generate grants | Read-only query | Run | Sessions | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| `codex-exec-v1` | rejected | rejected | rejected | implemented | yes | no |
| `codex-app-server-0.131.0` | rejected: unavoidable internal tools | implemented in code; native receipt pending | implemented in code; native receipt pending | delegated to `codex-exec-v1` | fingerprint-bound | no |
| `claude-code-cli-v1` | implemented for Claude Code 2.1.259+; native receipt pending | rejected | rejected | implemented | yes | no |
| `claude-agent-sdk-0.2.155` | implemented; native receipt pending | implemented mediator; host proof pending | implemented mediator; host proof pending | delegated to CLI profile | planning only | no |
| `pi-json-v1` | implemented; native receipt pending | rejected | rejected | unrestricted explicit policy only | yes | no |
| `pi-agent-sdk-0.73.1` | implemented; native receipt pending | implemented mediator; host proof pending | implemented mediator; host proof pending | delegated to CLI profile | no | no |
| `typesafe-systemone-v1` | n/a | n/a | n/a | n/a | no | implemented; native receipt pending |
| `deterministic-v1` | test-only | test-only | test-only | test-only | yes | no |

The executable matrix is `botpipe.providers.NATIVE_CAPABILITY_MATRIX`.
`validate_request()` runs before receipt creation or process dispatch. Missing
operations, exact grants without a mediator, unknown settings, and policies a
native profile cannot enforce raise `CapabilityError`.

## Architecture decision

Botpipe treats provider SDKs as planning and conversation transports, not as
the effect enforcement boundary. Generate and query disable the provider's
generic built-ins and register a finite structured tool inventory. Botpipe
validates each call, executes it through its own confined mediator, persists
the observation before returning it to the planner, and preserves the native
event stream. Run continues through each provider's native coding profile and
its separately validated policy translation. Profiles are version-pinned and
fail closed when package shape, tool inventory, isolation probe, or requested
policy differs from the reviewed contract.

## Interfaces investigated

### Codex

The [Codex app-server reference](https://developers.openai.com/codex/app-server/)
documents threads, turns, per-turn sandbox policy and output schemas,
notifications, and `turn/interrupt`. The
[CLI reference](https://developers.openai.com/codex/cli/reference/) documents
`exec`, JSONL, sandbox selection, configuration overrides, output schemas, and
resume.

`codex exec` does not document a global inventory/allowlist that closes every
model tool. Shell, apps, MCP, web search, image tools, multi-agent tools, hooks,
and configuration sources have distinct controls. Hooks are guardrails and do
not intercept every hosted/specialized path. The read-only sandbox constrains
filesystem writes; it does not prove the PRD's external non-mutation boundary
or an exact argv command envelope. Therefore this adapter advertises `run`
only.

An app-server bridge could expose one dynamic tool per persisted command
recipe while generic shell tools remain disabled. Dynamic tools and app-server
schemas are experimental/version-coupled, and the documented controls still
do not close the complete tool inventory without a pinned native conformance
probe. That path is not guessed in the Python adapter.

### Claude Code

The [CLI reference](https://code.claude.com/docs/en/cli-reference),
[permissions reference](https://code.claude.com/docs/en/permissions), and
[Agent SDK custom-tool documentation](https://code.claude.com/docs/en/agent-sdk/custom-tools)
distinguish tool availability from approval. `allowedTools` approves calls; it
does not restrict the available inventory. Native Bash permission patterns are
command strings, not resolved argv/executable/cwd/environment envelopes.

The CLI no-tool profile combines `--bare`, `--restricted`,
`--strict-mcp-config`, an empty `--tools` value, `dontAsk`, and a deny-all
settings rule. It requires Claude Code 2.1.259+ because unattended permission
prompt denial was added there. Exact grants and query need an Agent SDK
in-process MCP server exposing only Botpipe-owned structured tools.

`claude-agent-sdk-0.2.155` implements that bridge. It pins the Python package,
checks the audited `ClaudeAgentOptions` dataclass fields at runtime, supplies
`tools=[]`, `strict_mcp_config=True`, `setting_sources=[]`, `skills=[]`, and
`plugins=[]`, and registers only the in-process `botpipe` MCP tools. Empty-grant
generate registers no tools. Exact-grant generate registers only an opaque
grant-ID tool. Query registers bounded descriptor-confined read/list/search
tools and the fixed read-only git-status recipe. `dontAsk` denies any
unapproved tool. The bridge delegates `run` to the separately validated CLI
profile. Install the optional Python profile with `pip install
'botpipe[claude-sdk]'`.

The tool handlers run in Botpipe's process, outside Claude's built-in Bash
sandbox. File reads therefore use held directory descriptors with no-follow
component traversal, and commands use the finite bubblewrap mediator described
below. The SDK package and option closure are covered by protocol tests; native
credentials and a pinned hostile-config conformance receipt are still missing.

### Pi

The current upstream [Pi CLI/SDK documentation](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/README.md)
was observed at release v0.86.1. It documents `--no-tools`, strict tool
allowlists, `--no-extensions`, `--no-skills`, `--no-prompt-templates`,
`--no-themes`, `--no-context-files`, `--no-approve`, JSON event mode, and
explicit sessions. The adapter uses all resource-discovery closures for
tool-free generation and parses the authoritative `message_end` event.

Pi explicitly has no built-in sandbox. Its built-in `bash` accepts shell text,
and its built-in read tools do not document the required root, private-path,
symlink, immutable-evidence, or command containment guarantees. The Pi SDK can
replace built-ins with schema-validated `customTools`, but a compliant bridge
also needs an external sandbox. Stock CLI query and exact grants therefore
remain rejected. Stock run is accepted only with an explicitly unrestricted
policy.

`pi-agent-sdk-0.73.1` implements a separate JSONL bridge against the final
release under the original `@mariozechner/pi-coding-agent` package name. The
next tag changed package ownership, so this profile rejects every other
manifest version before importing it. It supplies `noTools: "builtin"`, an
explicit custom-tool allowlist, an empty ResourceLoader for extensions, skills,
prompts, themes and context files, an isolated temporary agent directory, and
disabled prompt-template expansion. Tool calls cross the JSONL boundary as
structured read/list/search or opaque grant IDs and are executed only by the
same Botpipe mediator used by Claude. The bridge is one-shot and does not claim
resumable SDK sessions. A deployment installs
`@mariozechner/pi-coding-agent@0.73.1` and may point
`BOTPIPE_PI_SDK_ROOT` at that exact package root.

### Botpipe mediator

The shared local mediator accepts no shell text. Its command recipe inventory
currently contains only `("git", "status", "--short")`. It resolves and hashes
root-owned, non-group/world-writable system `git` and `bubblewrap` executables,
rechecks their identities and the workspace identity immediately before each
call, clears both the outer and sandbox environments, supplies empty stdin,
unshares the network namespace, mounts the workspace read-only, bounds retained
output, and owns the full process tree through Botpipe process containment.
The adapter probes that exact sandbox profile before exposing any command tool.

Read tools hold authorized root directory descriptors, traverse components
with `O_NOFOLLOW`, reject private and configured excluded paths, require regular
files, and bound file bytes, traversal depth, visited nodes, matches, entries,
and returned output. Truncated reads label their digest as a captured-prefix
digest rather than claiming a full-file hash.

The workspace mount uses bubblewrap's `--ro-bind-fd` with a held no-follow
directory descriptor, preserving the checked directory identity across host
renames. The trusted setup closes inherited setup descriptors before executing
the command. The git-status recipe disables submodules, hooks, filesystem
monitors, maintenance, and global configuration; descriptor-based repository
checks reject attributes that could invoke filters and linked/external Git
directories before exposure and again before execution.

### TypeSafe Jev

The [TypeSafe primitives](https://docs.typesafe.ai/primitives) and
[quickstart](https://docs.typesafe.ai/introduction/quickstart) document
`POST /v1/systemone`, shared state, independent batched Choice/Score/Noul
questions, and their native answer shapes. `Choice` retains the selected option,
probabilities, and confidence. `Score` retains score, legend, probabilities,
and confidence. `Noul` retains only its truth probability; the adapter rejects
a fabricated confidence field. The adapter validates question IDs, answer
types, option/level sets, distributions, model identity, and finite JSON before
committing its receipt.

The API documentation uses mutable `jev-latest` and an example response model
of `jev-1.13.0`. A lost synchronous HTTP response has no documented native
idempotency/lookup key, so recovery remains `Unknown` and cannot redispatch.

## Local probe result

The implementation environment contained no `codex`, `claude`, or `pi`
executable on `PATH`, and its Python environment did not contain
`typesafe_sdk`. Node 24.19.0 and npm 11.9.0 were present. No provider
credentials were available. Its installed bubblewrap binary also rejected the
required isolation probe with `Failed to create NETLINK_ROUTE socket:
Operation not permitted`, so exact-command profiles fail before model dispatch
on this host. Package installation was not treated as proof:
it would not supply credentials, pinned provider responses, hostile-config
fixtures, platform sandboxes, or cancellation/recovery receipts.

Consequently no claim here proves A07, A07b, A08, A08b, A20, or A30 against a
native backend. The focused tests prove request validation, emitted profile
arguments, parsers, typed JEV preservation, local receipt fencing, and
fail-closed behavior. The complete-release baseline remains blocked until
native conformance runs on pinned Linux and Windows profiles. The bridge code,
inventory closure, protocol validation, durable recovery fencing, and local
mediator contracts are implemented; native authentication and supported-host
receipts remain a separate release gate.

## Codex app-server source audit and mediated bridge

`botpipe.codex_appserver` pins `rust-v0.131.0`, peeled commit
`05eb8678451435cbc8d79c6d8254276289f2bdf1`. It accepts no other reported
`codex-cli` version. This is a code capability and stub-protocol proof, not a
native conformance receipt: the build and tests used for this rewrite had no
Codex executable or authentication.

The pinned release has already refactored the older
`codex-rs/core/src/tools/spec.rs` path. The complete registry construction is
in [`spec_plan.rs`](https://github.com/openai/codex/blob/05eb8678451435cbc8d79c6d8254276289f2bdf1/codex-rs/core/src/tools/spec_plan.rs),
with configuration derivation in
[`tool_config.rs`](https://github.com/openai/codex/blob/05eb8678451435cbc8d79c6d8254276289f2bdf1/codex-rs/tools/src/tool_config.rs)
and feature defaults in
[`features/src/lib.rs`](https://github.com/openai/codex/blob/05eb8678451435cbc8d79c6d8254276289f2bdf1/codex-rs/features/src/lib.rs).
Those sources establish this closure:

- `thread/start.environments: []` selects no execution environment. The tool
  builder therefore omits shell/exec, stdin, `apply_patch`, and `view_image`.
- The per-thread override set disables hooks, code mode, permission tools,
  collaboration and fanout, apps, plugins, tool search and suggestions, image
  generation, skill installers, goals, memories, artifacts, and web search.
- An isolated `CODEX_HOME`, workspace-config rejection, `config/read` layer
  inspection, and rejection of all managed requirements close ambient MCP,
  plugin, and hook registration before `thread/start`.
- [`thread/start.dynamicTools`](https://github.com/openai/codex/blob/05eb8678451435cbc8d79c6d8254276289f2bdf1/codex-rs/app-server-protocol/src/protocol/v2/thread.rs)
  supplies schema-validated structured tools. Calls arrive as the bidirectional
  [`item/tool/call`](https://github.com/openai/codex/blob/05eb8678451435cbc8d79c6d8254276289f2bdf1/codex-rs/app-server-protocol/src/protocol/v2/item.rs)
  server request. The bridge services only an exact registered name and rejects
  every other server-initiated request.
- The
  [`turn/start` and `turn/interrupt` protocol](https://github.com/openai/codex/blob/05eb8678451435cbc8d79c6d8254276289f2bdf1/codex-rs/app-server-protocol/src/protocol/v2/turn.rs)
  provides native output schemas, streaming notifications, terminal status,
  and cancellation. Dynamic-tool definitions are persisted with threads in
  the pinned core, and the bridge binds a resumed thread ID to a deterministic
  tool-registry fingerprint.

The same source audit found an upstream blocker for strict command-free
generation: `update_plan` and `request_user_input` are registered
unconditionally. Neither has a documented hiding switch in this release.
Although they do not directly mutate the host, A07 requires every autonomous
tool to be blocked when the grant list is empty. The provider wrapper therefore
rejects empty-grant generate before version probing, receipt creation, or
process dispatch. `CodexAppServerProvider` is a real ProviderAdapter surface
for read-only query, non-empty exact generation, durable recovery, and
fingerprint-bound session resume; its `run` delegates to `codex-exec-v1`.
This conditional profile must not be presented as complete Codex support.
Codex cannot be marked complete until a pinned native interface can hide those
two tools and a credentialed hostile-config conformance run supplies receipts.

`tests/test_codex_appserver.py` exercises a full bidirectional JSONL transcript:
initialization with experimental API negotiation, runtime config audits,
thread and turn startup, a structured dynamic callback, bounded response,
usage and terminal events, fail-closed version and session fingerprints, and
denial of a non-mediated server request. Provider-level tests also cover exact
generation, autonomous bounded query, completed receipt recovery, durable tool
evidence, empty-grant preflight rejection, and fingerprint-bound native resume.
Passing `evidence=ToolEvidence(...)`
and the resolved `envelopes` to `execute()` publishes the manifest immediately
before native launch. When the mediator returns a `ToolObservation`, the bridge
publishes it through `ToolEvidence.record()` before sending any result to
Codex. A structured observation without an evidence recorder fails closed.
