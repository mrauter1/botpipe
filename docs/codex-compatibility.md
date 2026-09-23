# Codex compatibility

Botpipe uses the installed `codex app-server`, not `codex exec`. It has no pinned,
reviewed, maximum or accepted-version list. Model names also pass through.
Run `botpipe doctor` to check the installation that will execute your work.

## Required capabilities

| Capability | Requirement | Missing capability |
| --- | --- | --- |
| `thread/start`, `thread/resume`, `turn/start` | Every provider call | CapabilityError naming the method |
| Per-turn `sandboxPolicy` | Every provider call | CapabilityError before dispatch |
| `turn/interrupt` | Every provider call | CapabilityError before dispatch |
| `outputSchema` | Optional | Embed schema in prompt; validate and repair locally |
| Tool-feature configuration | Read-only presets | Affected preset unavailable |
| Ambient MCP disablement | Read-only presets | Affected preset unavailable |

The probe reads the executable identity (resolved path, size and modification
time), version, generated app-server JSON schemas and reported feature inventory.
It caches capabilities in state and records the probe hash with each operation.
Executable changes trigger another probe. Corrupt cache data triggers probing,
not relaxed enforcement. The feature inventory comes from the installed Codex;
there is no maintained list of approved Codex releases.

The earliest installation checked during this rewrite is **Codex 0.156.0**.
This is a measured compatibility reference, not a hard-coded minimum. Earlier
versions may work if they expose the required capabilities; they have not been
established by this rewrite's validation. A later release is accepted on its
capabilities. A failed cross-version `thread/resume` raises `SessionError`, so a
workflow can choose a new session. Replayed operations do not require Codex.

## Enforcement

Approval is always `never`. Presets use Codex read-only/no-network policy;
generation restricts configured tools and audits observed tool calls. Ambient
MCP servers are disabled unless explicitly named. If the installed protocol
cannot express a restriction, Botpipe reports the missing capability before
dispatch. It does not silently broaden the requested profile.

`full-access` inherits no Codex sandbox guarantee. Codex's unrestricted policy
cannot enforce network off, so full access also requires an explicit network
opt-in when that native limitation applies. A named remote MCP server can have
remote effects; filesystem read-only does not constrain that server.

The app-server process uses a POSIX process group or a Windows kill-on-close Job.
Cancellation requests `turn/interrupt`, waits the configured grace period, then
kills the process tree if needed. A process that escapes its group is outside
Botpipe's containment. Killing a shared app-server interrupts its other active
turns too; writable turns remain subject to reconciliation.

## Validation and release gate

The deterministic suite uses fake adapters and recorded app-server behavior,
without a Codex installation, model credentials or network access. Required CI
contract jobs install `@openai/codex@latest` on Linux, macOS and Windows and use
a local Responses fixture to exercise the protocol and sandbox. The nightly
schedule runs the same contracts to detect new-release incompatibility.

Local fixture evidence verifies transport and effects handling. It does not
establish authenticated model behavior. **Before tagging 2.0.0, run each preset
against a real model with credentials on each supported platform.** Record the
Codex version and doctor output alongside those release results.
