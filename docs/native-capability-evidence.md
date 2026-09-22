# Native provider capability evidence

Updated 2026-09-22 for the provider-first rewrite. This file records the
implementation profile separately from the completed-release gate. A profile
is advertised by code only when the adapter can configure the documented
native surface and reject unsupported requests before dispatch. Native support
still requires pinned-version integration receipts on each supported platform.

## Implemented matrix

| Adapter profile | Generate, empty grants | Exact generate grants | Read-only query | Run | Sessions | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| `codex-exec-v1` | rejected | rejected | rejected | implemented | yes | no |
| `codex-app-server-v2` (reviewed against Codex 0.155.1) | implemented in code; native receipt pending | implemented in code; native receipt pending | implemented in code; native receipt pending | implemented for current compatible protocol; native receipt pending | fingerprint-bound | no |
| `claude-code-cli-v1` | implemented for Claude Code 2.1.259+; native receipt pending | rejected | rejected | implemented | yes | no |
| `claude-agent-sdk-0.2.155` | implemented; native receipt pending | implemented mediator; host proof pending | implemented mediator; native receipt pending | delegated to CLI profile | yes; transitions unproven | no |
| `pi-json-v1` | implemented; native receipt pending | rejected | rejected | unrestricted explicit policy only | yes | no |
| `pi-agent-sdk-0.73.1` | implemented; native receipt pending | implemented mediator; host proof pending | implemented mediator; native receipt pending | same SDK; explicitly unrestricted policy | persistent v3 JSONL | no |
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

The implemented app-server profile exposes structured mediated tools while
generic shell tools remain disabled. Its current Codex 0.155.1 source audit,
local binary checks, and remaining limitations are recorded below. Empty-grant
generation uses the reviewed per-turn environment/tool configuration; native
credentialed receipts and hostile-configuration conformance remain release
gates.

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
tools and the scoped `count_lines` command. `dontAsk` denies any
unapproved tool. The bridge delegates `run` to the separately validated CLI
profile. Install the optional Python profile with `pip install
'botpipe[claude-sdk]'`.

The tool handlers run in Botpipe's process, outside Claude's built-in Bash
sandbox. File reads therefore use held directory descriptors with no-follow
component traversal. Exact generation grants use the finite bubblewrap
mediator; query's fixed line-count command consumes only an authorized frozen
snapshot. SDK package/options checks and protocol tests pass, but credentialed
hostile-config conformance receipts are still missing. Cancellation requests
the active native client's interrupt and waits within a bounded control time;
it returns `Unknown` when full process-tree quiescence cannot be established.

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
same Botpipe mediator used by Claude. All three operations use the same pinned
SDK and persistent v3 JSONL session manager. Run enables the reviewed native
read/bash/edit/write/grep/find/ls inventory only under an explicitly
unrestricted policy. Generation and query close those built-ins and register
their own permitted tools on each turn. This avoids crossing SDK/CLI versions
to continue one conversation. A deployment installs
`@mariozechner/pi-coding-agent@0.73.1` and may point
`BOTPIPE_PI_SDK_ROOT` at that exact package root and configures an explicit
model. Typed requests add the schema to the supplied prompt; completed raw
text reaches the common coordinator for JSON/schema validation and bounded
repair. Malformed output remains a completed native response, preserving
session advancement before the repair turn.

### Botpipe mediator

The shared local mediator accepts no shell text. Exact generation grants
currently support only `("git", "status", "--short")` and require an effective
workspace-wide read scope with no explicit read exclusions. It resolves and hashes
root-owned, non-group/world-writable system `git` and `bubblewrap` executables,
rechecks their identities and the workspace identity immediately before each
call, clears both the outer and sandbox environments, supplies empty stdin,
unshares the network namespace, mounts the workspace read-only, bounds retained
output, and owns the full process tree through Botpipe process containment.
The adapter probes that exact sandbox profile before exposing any command tool.

Query uses a separate `count_lines(path)` recipe. Descriptor-confined reading
first freezes a complete authorized regular-file snapshot; oversized sources
are rejected rather than reported as full-file counts. The command receives
only those bytes on stdin, using pinned trusted system `wc -l`, fixed arguments,
a minimal environment, process-tree containment, bounded output, and a finite
timeout. No model-selected filename or argument reaches the executable. Its
receipt includes the source identity and digest. This preserves narrower roots
and private-path exclusions without exposing repository-wide git status.

Read tools hold authorized root directory descriptors, traverse components
with `O_NOFOLLOW`, reject private and configured excluded paths, require regular
files, and bound file bytes, traversal depth, visited nodes, matches, entries,
and returned output. Truncated reads label their digest as a captured-prefix
digest rather than claiming a full-file hash.

The excluded names are `.aws`, `.azure`, `.botpipe`, `.botpipe-v2`, `.claude`,
`.codex`, `.config`, `.env` and `.env.*`, `.git`, `.gnupg`, `.pi`, `.ssh`,
`.botpipe-workspace.lock`, `credential`, `credentials`, and `credentials.json`.
Explicit policy exclusions apply as well. Shared read claims are held through
the read turn and bound to directory device/inode identities. Root or nested
path replacement fails closed. Both readers and writers now use the same local
path-overlap coordinator, so a reader at `root/child` conflicts with a writer at
`root` in either acquisition order, without probing for existing markers.
This coordination covers cooperating runtimes on one host/account; native
end-to-end conformance remains a separate proof requirement.

Every mediated attempt saves an immutable resolved-envelope manifest before
dispatch. Each tool observation is atomically published and synced before its
result returns to the native loop. Count/byte limits and persistence failures
stop delivery; an observed attempt cannot be silently restarted. Native
protocol queues, individual records, accumulated event evidence, and public
stream buffers have separate bounds. Accepted native payloads are preserved.

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

Two actual-package checks subsequently passed without prompt or inference:

- Claude Agent SDK 0.2.155 installed in an isolated environment and accepted
  the real empty-tool options, strict MCP configuration, and empty settings,
  skills, and plugin sources.
- Pi 0.73.1 imported from the actual installed npm package. Isolated
  `AuthStorage`, `ModelRegistry`, `SettingsManager`, `SessionManager`, a closed
  resource loader, and `createAgentSession` worked. Startup inventories were
  empty for generation, a representative custom read tool for query, and the
  seven reviewed built-ins for unrestricted run. Persistent session IDs/files
  were created, with no extensions or extension errors. No prompt, credential
  resolution, or model request was executed in this check.

These checks establish dependency/API compatibility, not native-turn proof.
No claim here proves A07, A07b, A08, A08b, A20, or A30 against a
native backend. The focused tests prove request validation, emitted profile
arguments, parsers, typed JEV preservation, local receipt fencing, and
fail-closed behavior. The complete-release baseline remains blocked until
native conformance runs on pinned Linux and Windows profiles. The bridge code,
inventory closure, protocol validation, durable recovery fencing, and local
mediator contracts are implemented; native authentication and supported-host
receipts remain a separate release gate.

The common session fingerprint records provider configuration, profile,
adapter version, model, and workspace. Real adapters do not currently establish
a verified non-secret native account identity. Account changes behind an
environment credential and native default-model drift therefore remain A10
gaps; credential values or hashes are not used as substitutes for identity.

## Codex app-server source audit and mediated bridge

`botpipe.codex_appserver` currently verifies Codex 0.155.1, peeled commit
`be2951ea34f0d295ed0becf97079f92fa5f6950e`, for the reviewed mediated profile.
The app-server accepts newer protocol-compatible versions for native RUN after
the protocol capability checks; strict mediated generate/query profiles require
an explicitly reviewed release. This is code and local native-binary evidence,
not a credentialed conformance receipt or proof of model cache hits.

The reviewed release has already refactored the older
`codex-rs/core/src/tools/spec.rs` path. The complete registry construction is
in [`spec_plan.rs`](https://github.com/openai/codex/blob/be2951ea34f0d295ed0becf97079f92fa5f6950e/codex-rs/core/src/tools/spec_plan.rs),
with configuration derivation in
[`tool_config.rs`](https://github.com/openai/codex/blob/be2951ea34f0d295ed0becf97079f92fa5f6950e/codex-rs/tools/src/tool_config.rs)
and feature defaults in
[`features/src/lib.rs`](https://github.com/openai/codex/blob/be2951ea34f0d295ed0becf97079f92fa5f6950e/codex-rs/features/src/lib.rs).
Those sources establish this closure:

- `thread/start.environments: []` selects no execution environment. The tool
  builder therefore omits shell/exec, stdin, `apply_patch`, and `view_image`.
- The per-thread override set disables hooks, code mode, permission tools,
  collaboration and fanout, apps, plugins, tool search and suggestions, image
  generation, skill installers, goals, memories, artifacts, and web search.
- An isolated `CODEX_HOME`, workspace-config rejection, `config/read` layer
  inspection, and rejection of all managed requirements close ambient MCP,
  plugin, and hook registration before `thread/start`.
- [`thread/start.dynamicTools`](https://github.com/openai/codex/blob/be2951ea34f0d295ed0becf97079f92fa5f6950e/codex-rs/app-server-protocol/src/protocol/v2/thread.rs)
  supplies schema-validated structured tools. Calls arrive as the bidirectional
  [`item/tool/call`](https://github.com/openai/codex/blob/be2951ea34f0d295ed0becf97079f92fa5f6950e/codex-rs/app-server-protocol/src/protocol/v2/item.rs)
  server request. The bridge services only an exact registered name and rejects
  every other server-initiated request.
- The
  [`turn/start` and `turn/interrupt` protocol](https://github.com/openai/codex/blob/be2951ea34f0d295ed0becf97079f92fa5f6950e/codex-rs/app-server-protocol/src/protocol/v2/turn.rs)
  provides native output schemas, streaming notifications, terminal status,
  and cancellation. Dynamic-tool definitions are persisted with threads in
  the pinned core, and the bridge binds a resumed thread ID to a deterministic
  tool-registry fingerprint.
- Continued role updates use the supported per-turn `collaborationMode`
  instruction delta. Thread-level `developerInstructions` is unsuitable in this
  pinned build: it is persisted, but changes are omitted from the resumed
  settings-diff builder. The per-turn path appends changed guidance and leaves
  unchanged guidance unduplicated; clearing uses an explicit nonempty reset.
  Native model/base instructions, ordinary developer instructions, and prior
  conversation messages remain intact. Botpipe owns the collaboration instruction
  block; the public preset-list response does not expose the built-in Default
  template text, so the reset clears Botpipe guidance without claiming to restore
  that separate native template.
  Pinned `core/tests/suite/collaboration_instructions.rs` verifies the request
  history for changed and unchanged roles; `context_manager/updates.rs` and
  `session/rollout_reconstruction.rs` establish incremental resume behavior.
  This is source and transcript evidence for preserving cacheable prefixes,
  not a credentialed receipt showing a provider cache hit.

The current 0.155.1 source and local endpoint checks establish the reviewed
per-turn environment/tool configuration for command-free generation and the
finite mediator inventory for exact grants. `CodexAppServerProvider` is a real
ProviderAdapter surface for generate, read-only query, exact generation,
durable recovery, native RUN on a compatible protocol, and fingerprint-bound
session resume. Its RUN path uses the app-server bridge directly; it does not
delegate to `codex-exec-v1`.
The query profile exposes read/list/search and `count_lines` within the resolved
policy roots. Exact-generation grants fail before probing when a narrower or
denied read policy would let the fixed git-status command bypass path semantics.
This conditional profile must not be presented as complete Codex support.
Codex cannot be marked complete until credentialed hostile-config and
platform-specific native conformance runs supply receipts.

`tests/test_codex_appserver.py` exercises a full bidirectional JSONL transcript:
initialization with experimental API negotiation, runtime config audits,
thread and turn startup, a structured dynamic callback, bounded response,
usage and terminal events, fail-closed version and session fingerprints, and
denial of a non-mediated server request. Provider-level tests also cover exact
generation, autonomous bounded query, completed receipt recovery, durable tool
evidence, mediated-profile preflight checks, and fingerprint-bound native
resume.
The wrapper publishes the resolved envelope manifest before reserving dispatch
budget or creating a receipt; the bridge repeats that idempotent check before
native launch. When the mediator returns a `ToolObservation`, the bridge
publishes it through `ToolEvidence.record()` before sending any result to
Codex. Evidence-record failure terminates the owned process and leaves the
already-dispatched receipt uncertain. A structured observation without an
evidence recorder fails closed.

The JSONL reader bounds each binary line before UTF-8 decoding or JSON parsing,
uses a bounded backpressure queue, and retains a byte-bounded stderr suffix.
Cancellation sends the pinned native `turn/interrupt` request to an owned
active turn, waits for a bounded terminal notification, and then contains the
process; it still returns `Unknown` because this wrapper has no independent
native quiescence receipt. Local version/config/workspace checks run before
budget dispatch. The effective `config/read` and managed-requirements audit
requires a live initialized app-server, so an audit rejection occurs after the
wrapper marks dispatch, but before `thread/start`, and remains uncertain in the
durable receipt.
