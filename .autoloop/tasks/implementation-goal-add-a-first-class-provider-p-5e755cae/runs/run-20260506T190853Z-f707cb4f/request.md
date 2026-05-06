* **Implementation goal**

  * Add a first-class provider policy layer to Autoloop v3.
  * The policy layer must support:

    * system defaults,
    * runtime/config `default_policy`,
    * optional runtime/config `strict_policy`,
    * workflow-level default policy,
    * reusable policy objects in workflow code,
    * per-step policy overrides,
    * per-turn resolved policy,
    * provider-specific emission for Codex CLI and Claude Code,
    * capability reports for unsupported, lossy, or unsafe mappings.
  * Native P0 policy must include:

    * model,
    * permission mode,
    * dangerous bypass controls,
    * sandbox mode,
    * workspace filesystem policy,
    * workspace network policy,
    * environment policy,
    * tool allow/ask/deny rules.
  * Defer MCP, hooks, subagents, plugins, and managed-enterprise policy emitters to later patches.
  * Do not mutate user-level provider config files during workflow runs.
  * Generate run-scoped policy files under the current run directory.

* **Current codebase facts to preserve**

  * Runtime provider backend dispatch currently selects built-in `claude` or `codex` transports and wraps them in `RenderedLLMProvider`; provider backend names with `module:function` are rejected. 
  * Current Codex transport is thin: it stores CLI commands, model, and model effort, then calls `subprocess.run(...)` with the rendered prompt. 
  * Current config parsing has strict unknown-key validation for runtime config; preserve strict validation when adding `provider_policy`. 
  * Existing tests expect provider config merge behavior for generic/provider-specific model and effort fields. 
  * Existing provider tests use fake CLI/subprocess patterns; extend those patterns instead of invoking real Codex or Claude binaries. 

* **External provider facts to account for**

  * Codex configuration supports model/provider configuration, `approval_policy`, `sandbox_mode`, and workspace-write options such as writable roots and network access; current docs describe `on-failure` approval as deprecated, so do not make it a canonical normalized mode. ([Claude][1])
  * Claude Code supports hierarchical user/project/local/managed settings, permission allow/ask/deny rules, `defaultMode`, and `disableBypassPermissionsMode`. ([Claude API Docs][2])
  * Claude Code current sandbox settings expose native filesystem policy fields including `filesystem.allowWrite`, `filesystem.denyWrite`, `filesystem.denyRead`, and `filesystem.allowRead`; these merge across scopes and also merge with `Edit(...)` and `Read(...)` permission rules. ([Claude][1])
  * Claude Code sandbox network settings expose domain allow/deny fields and local binding controls. ([Claude][1])
  * Treat Claude sandbox filesystem/network support as capability-profile dependent, because older Claude Code docs describe settings primarily through hierarchical settings and permission rules. ([Claude API Docs][2])

* **Architecture**

  * Add policy support in these layers:

    * core policy model,
    * runtime config parsing and merging,
    * workflow/step declaration,
    * compiler,
    * provider request model,
    * runtime policy resolver,
    * provider emitters,
    * provider transports.
  * Do not bury normalized policy logic inside `codex.py` or `claude.py`.
  * Do not add policy-specific behavior into workflow business logic.
  * Avoid modifying `autoloop/core/engine.py` except for narrowly passing resolved policy through existing provider request construction if there is no better seam.
  * Provider transports should receive an already-resolved policy and emit provider-specific config.

* **Policy resolution order**

  * Effective policy resolution must be:

    ```text
    system default_policy
    → runtime/config default_policy using existing global/workspace/CLI merge rules
    → workflow default policy, if declared
    → step policy, if declared
    → optional strict_policy validation and required-deny injection
    → provider emitter
    ```
  * `default_policy` is a normal merge layer.
  * `strict_policy` is not a normal merge layer.
  * `strict_policy` validates the resolved policy and injects required denials.
  * Step policies may specialize but must not silently exceed the runtime/admin strict envelope.

* **System default policy**

  * System defaults are:

    ```text
    sandbox on
    full-auto sandboxed
    network on
    ```
  * “Full-auto” must mean autonomous inside sandbox, not unsandboxed dangerous bypass.
  * Define the system default as:

    ```python
    SYSTEM_DEFAULT_PROVIDER_POLICY = ProviderPolicy(
        permissions=PermissionPolicy(
            mode="full_auto_sandboxed",
            allow_dangerous_bypass=False,
            disable_dangerous_bypass=True,
            allow=(),
            ask=(),
            deny=(),
        ),
        sandbox=SandboxPolicy(
            enabled=True,
            required=True,
            mode="workspace_write",
            workspace=WorkspacePolicy(
                filesystem=WorkspaceFilesystemPolicy(
                    allow_read=(".",),
                    allow_write=(".",),
                    deny_read=(),
                    deny_write=(),
                ),
                network=WorkspaceNetworkPolicy(
                    enabled=True,
                    mode="full",
                    allow_domains=(),
                    deny_domains=(),
                    allow_local_binding=False,
                ),
            ),
        ),
        env=EnvPolicy(
            inherit="core",
            allow=(),
            deny=("*TOKEN*", "*SECRET*", "*KEY*"),
            set={},
        ),
    )
    ```

* **New files**

  * Add:

    ```text
    autoloop/core/provider_policy.py
    autoloop/runtime/provider_policy_resolver.py
    autoloop/runtime/providers/codex_policy.py
    autoloop/runtime/providers/claude_policy.py
    tests/unit/test_provider_policy.py
    tests/runtime/test_provider_policy_config.py
    tests/runtime/test_provider_policy_emitters.py
    tests/runtime/test_provider_policy_steps.py
    ```
  * Modify:

    ```text
    autoloop/core/steps.py
    autoloop/simple.py
    autoloop/core/compiler.py
    autoloop/core/providers/models.py
    autoloop/core/providers/rendering.py
    autoloop/core/operations.py
    autoloop/runtime/config.py
    autoloop/runtime/provider_backends.py
    autoloop/runtime/providers/codex.py
    autoloop/runtime/providers/claude.py
    autoloop/runtime/runner.py
    autoloop/runtime/tracing.py
    ```

* **Core policy module**

  * Implement in:

    ```text
    autoloop/core/provider_policy.py
    ```
  * Use Pydantic `BaseModel` for config-facing policy models.
  * Models should be immutable or treated as copy-on-write.
  * Export:

    ```python
    __all__ = [
        "SYSTEM_DEFAULT_PROVIDER_POLICY",
        "ProviderPolicy",
        "ProviderPolicyOverride",
        "ResolvedProviderPolicy",
        "StrictProviderPolicy",
        "ModelPolicy",
        "PermissionPolicy",
        "SandboxPolicy",
        "WorkspacePolicy",
        "WorkspaceFilesystemPolicy",
        "WorkspaceNetworkPolicy",
        "EnvPolicy",
        "ToolPolicy",
        "InstructionPolicy",
        "TelemetryPolicy",
        "PolicyValidationMode",
        "ProviderPolicyError",
        "ProviderPolicyViolation",
        "ProviderPolicyCapabilityReport",
        "ProviderPolicyEmission",
        "merge_provider_policies",
        "validate_against_strict_policy",
        "policy_fingerprint",
    ]
    ```

* **Model policy**

  * Implement:

    ```python
    class ModelPolicy(BaseModel):
        default: str | None = None
        provider: str | None = None
        base_url: str | None = None
        effort: Literal["minimal", "low", "medium", "high", "xhigh"] | None = None
        verbosity: Literal["low", "medium", "high"] | None = None
        reasoning_summary: Literal["auto", "concise", "detailed", "none"] | None = None
        overrides: dict[str, str] = Field(default_factory=dict)
    ```
  * Preserve existing model/model-effort behavior by mapping existing fields into policy defaults during runtime config resolution:

    * `provider.codex.model` → `provider_policy.default.model.default`
    * `provider.codex.model_effort` → `provider_policy.default.model.effort`
    * `provider.claude.model` → `provider_policy.default.model.default`
    * `provider.claude.effort` → `provider_policy.default.model.effort`
  * Do not remove the existing provider fields in the first patch.

* **Permission policy**

  * Implement:

    ```python
    class PermissionPolicy(BaseModel):
        mode: Literal[
            "ask",
            "auto_edit",
            "full_auto_sandboxed",
            "full_auto_unsandboxed",
            "deny_all",
        ] = "ask"
        allow_dangerous_bypass: bool = False
        disable_dangerous_bypass: bool = True
        allow: tuple[str, ...] = ()
        ask: tuple[str, ...] = ()
        deny: tuple[str, ...] = ()
    ```
  * `full_auto_sandboxed` means autonomous with sandbox required.
  * `full_auto_unsandboxed` means autonomous without sandbox and must require:

    ```python
    allow_dangerous_bypass=True
    ```
  * If `mode="full_auto_unsandboxed"` and `allow_dangerous_bypass=False`, validation must fail.
  * Deny rules dominate ask/allow rules.
  * Do not let a step override clear runtime/admin deny rules unless strict policy explicitly allows it.

* **Workspace filesystem policy**

  * Implement as native P0:

    ```python
    class WorkspaceFilesystemPolicy(BaseModel):
        allow_read: tuple[str, ...] = (".",)
        allow_write: tuple[str, ...] = (".",)
        deny_read: tuple[str, ...] = ()
        deny_write: tuple[str, ...] = ()
    ```
  * Validate:

    * entries are non-empty strings,
    * entries contain no NUL bytes,
    * duplicates are removed preserving order,
    * relative paths are allowed,
    * absolute paths are allowed only if strict policy permits them,
    * core model does not expand `~`.
  * Merge:

    * `allow_read`: replace by default,
    * `allow_write`: replace by default,
    * `deny_read`: union preserving order,
    * `deny_write`: union preserving order.

* **Workspace path semantics**

  * Relative paths resolve against the active workspace root, not process cwd.
  * `"."` means workspace root.
  * Normalize path strings before strict-policy checks.
  * For strict validation:

    * compare canonical paths using `Path.resolve(strict=False)`;
    * if a path does not exist, validate its nearest existing parent and preserve the intended suffix;
    * do not allow symlink traversal to escape an allowed root unless `strict_policy.sandbox.workspace.filesystem.allow_symlink_escape=True`.
  * Add this strict option:

    ```python
    allow_symlink_escape: bool = False
    ```

    on strict filesystem policy.

* **Workspace network policy**

  * Implement:

    ```python
    class WorkspaceNetworkPolicy(BaseModel):
        enabled: bool = True
        mode: Literal["none", "limited", "full"] = "full"
        allow_domains: tuple[str, ...] = ()
        deny_domains: tuple[str, ...] = ()
        allow_local_binding: bool = False
    ```
  * Rules:

    * `mode="none"` implies `enabled=False`;
    * `enabled=False` implies `mode="none"`;
    * `mode="limited"` requires at least one allowed domain unless strict policy explicitly permits empty limited mode;
    * `mode="full"` ignores `allow_domains` for permit decisions but still applies `deny_domains`;
    * deny domains dominate allow domains.
  * Domain validation:

    * entries are non-empty strings,
    * allow bare domains like `github.com`,
    * allow wildcard prefixes like `*.npmjs.org`,
    * reject values with URL schemes such as `https://`.

* **Workspace policy**

  * Implement:

    ```python
    class WorkspacePolicy(BaseModel):
        root: str = "."
        filesystem: WorkspaceFilesystemPolicy = Field(default_factory=WorkspaceFilesystemPolicy)
        network: WorkspaceNetworkPolicy = Field(default_factory=WorkspaceNetworkPolicy)
    ```

* **Sandbox policy**

  * Implement:

    ```python
    class SandboxPolicy(BaseModel):
        enabled: bool = True
        required: bool = True
        mode: Literal["read_only", "workspace_write", "danger_full_access"] = "workspace_write"
        workspace: WorkspacePolicy = Field(default_factory=WorkspacePolicy)
    ```
  * Validation:

    * if `mode="read_only"`, `workspace.filesystem.allow_write` must be empty or ignored by emitters with a capability warning; prefer failing in strict mode;
    * if `mode="danger_full_access"`, `permissions.allow_dangerous_bypass=True` must be set;
    * if `required=True`, the selected provider target must support sandbox enforcement or the capability report must fail when validation mode requires failure.

* **Environment policy**

  * Implement:

    ```python
    class EnvPolicy(BaseModel):
        inherit: Literal["all", "core", "none"] = "core"
        allow: tuple[str, ...] = ()
        deny: tuple[str, ...] = ("*TOKEN*", "*SECRET*", "*KEY*")
        set: dict[str, str] = Field(default_factory=dict)
    ```
  * Deny dominates allow.
  * `set` values must be strings.
  * Do not log values that look secret-bearing.

* **Tool policy**

  * Implement:

    ```python
    class ToolPolicy(BaseModel):
        allow: tuple[str, ...] = ()
        ask: tuple[str, ...] = ()
        deny: tuple[str, ...] = ()
    ```
  * Initial implementation may map `permissions.allow/ask/deny` and `tools.allow/ask/deny` into the same provider permission surface.
  * Keep both fields to allow future distinction between runtime tool registration and provider permission rules.

* **Instructions and telemetry policy**

  * Implement P0/P0.5 containers:

    ```python
    class InstructionPolicy(BaseModel):
        files: tuple[str, ...] = ()
        inline: str | None = None
        output_style: str | None = None

    class TelemetryPolicy(BaseModel):
        enabled: bool = False
        exporter: str | None = None
        headers: dict[str, str] = Field(default_factory=dict)
    ```
  * Do not wire full hooks/agents/plugins in this patch.

* **Provider policy root model**

  * Implement:

    ```python
    class ProviderPolicy(BaseModel):
        model: ModelPolicy = Field(default_factory=ModelPolicy)
        permissions: PermissionPolicy = Field(default_factory=PermissionPolicy)
        sandbox: SandboxPolicy = Field(default_factory=SandboxPolicy)
        env: EnvPolicy = Field(default_factory=EnvPolicy)
        tools: ToolPolicy = Field(default_factory=ToolPolicy)
        instructions: InstructionPolicy = Field(default_factory=InstructionPolicy)
        telemetry: TelemetryPolicy = Field(default_factory=TelemetryPolicy)
        codex: dict[str, Any] = Field(default_factory=dict)
        claude: dict[str, Any] = Field(default_factory=dict)

        def with_overrides(self, **kwargs: Any) -> "ProviderPolicy": ...
        def allow_workspace_write(self, *paths: str) -> "ProviderPolicy": ...
        def deny_workspace_read(self, *paths: str) -> "ProviderPolicy": ...
        def with_network_domains(self, *domains: str) -> "ProviderPolicy": ...
        def with_model_effort(self, effort: str) -> "ProviderPolicy": ...
    ```
  * Implement:

    ```python
    class ProviderPolicyOverride(BaseModel):
        model: ModelPolicy | None = None
        permissions: PermissionPolicy | None = None
        sandbox: SandboxPolicy | None = None
        env: EnvPolicy | None = None
        tools: ToolPolicy | None = None
        instructions: InstructionPolicy | None = None
        telemetry: TelemetryPolicy | None = None
        codex: dict[str, Any] | None = None
        claude: dict[str, Any] | None = None
    ```
  * `ResolvedProviderPolicy` can initially be an alias or subclass of `ProviderPolicy`.

* **Strict policy config shape**

  * The external config shape should mirror the default shape:

    ```yaml
    provider_policy:
      strict:
        permissions:
          allow_dangerous_bypass: false
          disable_dangerous_bypass: true
        sandbox:
          required: true
          allowed_modes: ["read_only", "workspace_write"]
          workspace:
            filesystem:
              allowed_read_roots: ["."]
              allowed_write_roots: ["."]
              required_deny_read: ["./.env", "./secrets/**"]
              required_deny_write: ["/etc", "/usr/local/bin"]
              allow_symlink_escape: false
            network:
              allowed_modes: ["none", "limited", "full"]
              allowed_domains: null
              required_deny_domains: []
              allow_local_binding: false
    ```
  * Internally, use distinct strict model classes.

* **Strict policy models**

  * Implement:

    ```python
    class StrictPermissionPolicy(BaseModel):
        allow_dangerous_bypass: bool | None = False
        disable_dangerous_bypass: bool | None = True
        required_deny: tuple[str, ...] = ()
        forbidden_allow: tuple[str, ...] = ()

    class StrictWorkspaceFilesystemPolicy(BaseModel):
        allowed_read_roots: tuple[str, ...] | None = (".",)
        allowed_write_roots: tuple[str, ...] | None = (".",)
        required_deny_read: tuple[str, ...] = ("./.env", "./secrets/**")
        required_deny_write: tuple[str, ...] = ("/etc", "/usr/local/bin")
        allow_symlink_escape: bool = False

    class StrictWorkspaceNetworkPolicy(BaseModel):
        allowed_modes: tuple[Literal["none", "limited", "full"], ...] = ("none", "limited", "full")
        allowed_domains: tuple[str, ...] | None = None
        required_deny_domains: tuple[str, ...] = ()
        allow_local_binding: bool | None = False

    class StrictWorkspacePolicy(BaseModel):
        filesystem: StrictWorkspaceFilesystemPolicy = Field(default_factory=StrictWorkspaceFilesystemPolicy)
        network: StrictWorkspaceNetworkPolicy = Field(default_factory=StrictWorkspaceNetworkPolicy)

    class StrictSandboxPolicy(BaseModel):
        required: bool | None = True
        allowed_modes: tuple[Literal["read_only", "workspace_write", "danger_full_access"], ...] = (
            "read_only",
            "workspace_write",
        )
        workspace: StrictWorkspacePolicy = Field(default_factory=StrictWorkspacePolicy)

    class StrictEnvPolicy(BaseModel):
        required_deny: tuple[str, ...] = ("*TOKEN*", "*SECRET*", "*KEY*")
        allowed_set_keys: tuple[str, ...] | None = None

    class StrictProviderPolicy(BaseModel):
        permissions: StrictPermissionPolicy = Field(default_factory=StrictPermissionPolicy)
        sandbox: StrictSandboxPolicy = Field(default_factory=StrictSandboxPolicy)
        env: StrictEnvPolicy = Field(default_factory=StrictEnvPolicy)
    ```

* **Strict policy validation**

  * Implement:

    ```python
    def validate_against_strict_policy(
        policy: ProviderPolicy,
        strict: StrictProviderPolicy | None,
        *,
        step_name: str | None = None,
        workspace_root: Path | None = None,
    ) -> ProviderPolicy:
        ...
    ```
  * If `strict is None`, return canonicalized policy.
  * If strict policy is present:

    * reject dangerous bypass if strict forbids it;
    * reject sandbox disabled if strict requires sandbox;
    * reject sandbox mode not in allowed modes;
    * reject `full_auto_unsandboxed` unless dangerous bypass and `danger_full_access` are both allowed;
    * reject `allow_read` outside allowed read roots;
    * reject `allow_write` outside allowed write roots;
    * inject required `deny_read`;
    * inject required `deny_write`;
    * inject required network deny domains;
    * inject env required deny patterns;
    * reject network mode not in allowed modes;
    * reject local binding if strict forbids it;
    * reject allow domains outside strict allowed domains when set.
  * Error message must include:

    * step name if available,
    * field path,
    * requested value,
    * allowed value or constraint.

* **Provider policy error**

  * Implement:

    ```python
    class ProviderPolicyError(WorkflowExecutionError): ...
    ```
  * Example message:

    ```text
    Provider policy violation for step 'implement':
    - sandbox.mode='danger_full_access' exceeds strict sandbox.allowed_modes=['read_only', 'workspace_write']
    - sandbox.workspace.filesystem.allow_write='/tmp' is outside strict allowed_write_roots=['.']
    ```

* **Policy merge semantics**

  * Implement:

    ```python
    def merge_provider_policies(*layers: ProviderPolicy | ProviderPolicyOverride | None) -> ProviderPolicy:
        ...
    ```
  * Rules:

    * missing layer ignored;
    * scalar fields: last non-null wins;
    * dict fields: deep merge;
    * `codex` / `claude` extras: deep merge;
    * `permissions.deny`: union preserving order;
    * `permissions.ask`: replace by default;
    * `permissions.allow`: replace by default;
    * `tools.deny`: union preserving order;
    * `tools.ask`: replace by default;
    * `tools.allow`: replace by default;
    * `filesystem.deny_read`: union preserving order;
    * `filesystem.deny_write`: union preserving order;
    * `filesystem.allow_read`: replace by default;
    * `filesystem.allow_write`: replace by default;
    * `network.deny_domains`: union preserving order;
    * `network.allow_domains`: replace by default;
    * `env.deny`: union preserving order;
    * `env.allow`: replace by default;
    * `env.set`: deep merge, later values override earlier values.

* **Validation config**

  * Implement:

    ```python
    class ProviderPolicyValidationConfig(BaseModel):
        unsupported: Literal["fail", "warn", "ignore"] = "fail"
        lossy_mapping: Literal["fail", "warn", "ignore"] = "warn"
        unsafe_expansion: Literal["fail", "warn", "ignore"] = "fail"
    ```
  * Use `unsafe_expansion`, not `dangerous_expansion`.

* **Runtime config integration**

  * Add to runtime config:

    ```python
    class ProviderPolicyRuntimeConfig(BaseModel):
        default: ProviderPolicy = Field(default_factory=lambda: SYSTEM_DEFAULT_PROVIDER_POLICY)
        strict: StrictProviderPolicy | None = None
        validation: ProviderPolicyValidationConfig = Field(default_factory=ProviderPolicyValidationConfig)
    ```
  * Add to resolved runtime config:

    ```python
    provider_policy: ProviderPolicyRuntimeConfig
    ```
  * Add config parsing for top-level:

    ```yaml
    provider_policy:
      default: ...
      strict: ...
      validation: ...
    ```
  * Preserve existing provider fields.
  * Preserve strict unknown-key rejection.
  * Add CLI:

    ```text
    --policy-file PATH
    --policy-validation-unsupported fail|warn|ignore
    --policy-validation-lossy fail|warn|ignore
    --policy-validation-unsafe-expansion fail|warn|ignore
    ```
  * Do not add CLI flags for every policy field in the first patch.
  * Existing `runtime.full_auto` should map to:

    ```python
    provider_policy.default.permissions.mode = "full_auto_sandboxed"
    ```

    unless explicitly set.

* **Example config**

  * Must parse:

    ```yaml
    provider:
      name: codex
      codex:
        model: gpt-5.4
        model_effort: high

    provider_policy:
      default:
        permissions:
          mode: full_auto_sandboxed
          allow_dangerous_bypass: false
          disable_dangerous_bypass: true
        sandbox:
          enabled: true
          required: true
          mode: workspace_write
          workspace:
            filesystem:
              allow_read: ["."]
              allow_write: [".", "./build", "./dist"]
              deny_read: ["./.env", "./secrets/**"]
              deny_write: ["/etc", "/usr/local/bin"]
            network:
              enabled: true
              mode: full
              allow_domains: []
              deny_domains: []
              allow_local_binding: false
        env:
          inherit: core
          deny: ["*TOKEN*", "*SECRET*", "*KEY*"]

      strict:
        permissions:
          allow_dangerous_bypass: false
          disable_dangerous_bypass: true
        sandbox:
          required: true
          allowed_modes: ["read_only", "workspace_write"]
          workspace:
            filesystem:
              allowed_read_roots: ["."]
              allowed_write_roots: [".", "./build", "./dist"]
              required_deny_read: ["./.env", "./secrets/**"]
              required_deny_write: ["/etc", "/usr/local/bin"]
              allow_symlink_escape: false
            network:
              allowed_modes: ["none", "limited", "full"]
              allowed_domains: null
              required_deny_domains: []
              allow_local_binding: false

      validation:
        unsupported: fail
        lossy_mapping: warn
        unsafe_expansion: fail
    ```

* **Workflow authoring API**

  * Add optional `policy` to core step classes.
  * Add optional `policy` to simple authoring:

    ```python
    step(..., policy: ProviderPolicy | ProviderPolicyOverride | None = None)
    produce_verify_step(..., policy: ProviderPolicy | ProviderPolicyOverride | None = None)
    workflow_step(..., policy: ProviderPolicy | ProviderPolicyOverride | None = None)
    python_step(..., policy: ProviderPolicy | ProviderPolicyOverride | None = None)
    ```
  * Add optional workflow-level default:

    ```python
    class MyWorkflow(Workflow):
        policy = ProviderPolicy(...)
    ```
  * `python_step(policy=...)` applies only to provider-backed operations called inside the Python step.
  * Document clearly:

    ```text
    A python_step policy is not an OS sandbox for Python code. It only applies to llm()/classify() provider operations made inside the step.
    ```

* **Reusable policy objects**

  * Authors must be able to define:

    ```python
    FULL_AUTO_WORKSPACE = ProviderPolicy(
        permissions=PermissionPolicy(mode="full_auto_sandboxed"),
        sandbox=SandboxPolicy(
            enabled=True,
            required=True,
            mode="workspace_write",
            workspace=WorkspacePolicy(
                filesystem=WorkspaceFilesystemPolicy(
                    allow_read=(".",),
                    allow_write=(".", "./build", "./dist"),
                    deny_read=("./.env", "./secrets/**"),
                    deny_write=("/etc", "/usr/local/bin"),
                ),
                network=WorkspaceNetworkPolicy(enabled=True, mode="full"),
            ),
        ),
    )

    READ_ONLY_REVIEW = ProviderPolicy(
        permissions=PermissionPolicy(mode="ask"),
        sandbox=SandboxPolicy(
            enabled=True,
            required=True,
            mode="read_only",
            workspace=WorkspacePolicy(
                filesystem=WorkspaceFilesystemPolicy(
                    allow_read=(".",),
                    allow_write=(),
                    deny_read=("./.env", "./secrets/**"),
                    deny_write=("/etc", "/usr/local/bin"),
                ),
                network=WorkspaceNetworkPolicy(enabled=False, mode="none"),
            ),
        ),
    )
    ```
  * Then:

    ```python
    implement = produce_verify_step("implement", policy=FULL_AUTO_WORKSPACE, ...)
    audit = produce_verify_step("audit", policy=READ_ONLY_REVIEW, ...)
    ```

* **Compiler changes**

  * Add:

    ```python
    CompiledWorkflow.provider_policy: ProviderPolicy | None
    CompiledStep.provider_policy: ProviderPolicy | ProviderPolicyOverride | None
    ```
  * Include policy fingerprints in topology hash.
  * Validate that policy objects are serializable.
  * Do not resolve runtime/config policy at compile time; only workflow/step policy metadata belongs in the compiled workflow.

* **Provider request model changes**

  * Add:

    ```python
    policy: ResolvedProviderPolicy | None = None
    ```

    to:

    ```python
    ProducerRequest
    VerifierRequest
    LLMRequest
    OperationRequest
    ProviderTurnContext
    RenderedProviderTurn
    ```
  * Provider rendering may include a short policy summary for debugging.
  * Provider rendering must not include secret env values.

* **Runtime policy resolver**

  * Add:

    ```text
    autoloop/runtime/provider_policy_resolver.py
    ```
  * Implement:

    ```python
    class ProviderPolicyResolver:
        def __init__(
            self,
            *,
            config: ResolvedRuntimeConfig,
            workflow_policy: ProviderPolicy | None,
            workspace_root: Path,
        ) -> None: ...

        def resolve_for_step(self, step: CompiledStep) -> ResolvedProviderPolicy: ...

        def resolve_for_operation(
            self,
            ctx: Context,
            explicit_policy: ProviderPolicy | ProviderPolicyOverride | None = None,
        ) -> ResolvedProviderPolicy: ...
    ```
  * Emit runtime events:

    ```text
    provider_policy_resolved
    provider_policy_violation
    ```
  * Do not include secret env values in events.

* **Operation policy propagation**

  * Add policy support to:

    ```python
    llm_call(..., policy: ProviderPolicy | ProviderPolicyOverride | None = None)
    classify_call(..., policy: ProviderPolicy | ProviderPolicyOverride | None = None)
    ```
  * If omitted, operations inherit current step policy.
  * Add `policy` to `OperationRuntime`.
  * Include policy fingerprint in operation replay fingerprint.
  * Preserve existing replay mismatch behavior.

* **Policy fingerprint**

  * Implement:

    ```python
    def policy_fingerprint(policy: ProviderPolicy) -> str:
        ...
    ```
  * Use stable JSON serialization.
  * Include fingerprint in:

    * provider metadata,
    * operation replay fingerprint,
    * runtime trace events,
    * capability reports.
  * Never log raw secret env values.

* **Capability report**

  * Implement:

    ```python
    class EffectiveEnforcementReport(BaseModel):
        sandbox_mode: str | None = None
        write_roots: tuple[str, ...] = ()
        read_roots: tuple[str, ...] = ()
        deny_read_enforced: bool | None = None
        deny_write_enforced: bool | None = None
        network_domain_filter_enforced: bool | None = None
        dangerous_bypass_disabled: bool | None = None

    class ProviderPolicyCapabilityReport(BaseModel):
        target: Literal["codex", "claude"]
        step_name: str | None = None
        policy_fingerprint: str
        unsupported: tuple[str, ...] = ()
        lossy: tuple[str, ...] = ()
        unsafe_expansions: tuple[str, ...] = ()
        emitted_files: tuple[str, ...] = ()
        emitted_cli_args: tuple[str, ...] = ()
        effective_enforcement: EffectiveEnforcementReport = Field(default_factory=EffectiveEnforcementReport)
        decision: Literal["ok", "warn", "fail"] = "ok"
    ```
  * Behavior:

    * unsupported + validation `fail` → fail before provider run;
    * lossy + validation `fail` → fail before provider run;
    * unsafe expansion + validation `fail` → fail before provider run;
    * warn modes write runtime warning and continue;
    * ignore modes record only.
  * Always write:

    ```text
    <run_dir>/provider_policy/<step-key>/<target>/capability_report.json
    ```

* **Provider policy emission**

  * Implement:

    ```python
    class ProviderPolicyEmission(BaseModel):
        target: Literal["codex", "claude"]
        config_files: dict[str, Path]
        cli_args: tuple[str, ...]
        env: dict[str, str]
        capability_report: ProviderPolicyCapabilityReport
    ```
  * All generated files go under:

    ```text
    <run_dir>/provider_policy/<step-key>/
    ```
  * Step key should include:

    * safe step name,
    * scope if available,
    * item id if available,
    * visit if available.
  * Do not write to:

    ```text
    ~/.codex/config.toml
    ~/.claude/settings.json
    ```

* **Codex emitter**

  * Add:

    ```text
    autoloop/runtime/providers/codex_policy.py
    ```
  * Implement:

    ```python
    class CodexPolicyEmitter:
        def emit(
            self,
            policy: ResolvedProviderPolicy,
            *,
            run_dir: Path,
            step_key: str,
            validation: ProviderPolicyValidationConfig,
        ) -> ProviderPolicyEmission:
            ...
    ```
  * Generate:

    ```text
    <run_dir>/provider_policy/<step-key>/codex/config.toml
    <run_dir>/provider_policy/<step-key>/codex/effective_policy.json
    <run_dir>/provider_policy/<step-key>/codex/capability_report.json
    ```
  * Map:

    * `model.default` → `model`
    * `model.effort` → `model_reasoning_effort` or CLI equivalent when supported
    * `permissions.mode="ask"` → `approval_policy="on-request"`
    * `permissions.mode="full_auto_sandboxed"` → `approval_policy="never"` and `sandbox_mode="workspace-write"`
    * `permissions.mode="full_auto_unsandboxed"` → `approval_policy="never"` and `sandbox_mode="danger-full-access"` only when dangerous bypass is allowed and strict policy permits it
    * `sandbox.mode="read_only"` → `sandbox_mode="read-only"`
    * `sandbox.mode="workspace_write"` → `sandbox_mode="workspace-write"`
    * `sandbox.workspace.filesystem.allow_write` → `sandbox_workspace_write.writable_roots`
    * `sandbox.workspace.network.enabled=True` with workspace-write → `sandbox_workspace_write.network_access=true`
    * `env.inherit/allow/deny/set` → `shell_environment_policy` when supported
  * Treat as unsupported or lossy unless target capability says otherwise:

    * `deny_read`
    * `deny_write`
    * domain-level `allow_domains`
    * domain-level `deny_domains`
    * dangerous bypass disable via managed policy.
  * Do not imply that Codex fully enforces read-deny or domain allow/deny unless capability detection confirms it.

* **Claude emitter**

  * Add:

    ```text
    autoloop/runtime/providers/claude_policy.py
    ```
  * Implement capability model:

    ```python
    class ClaudeCapabilities(BaseModel):
        supports_sandbox_filesystem: bool = True
        supports_sandbox_network_domains: bool = True
        supports_disable_bypass: bool = True
    ```
  * Generate:

    ```text
    <run_dir>/provider_policy/<step-key>/claude/settings.json
    <run_dir>/provider_policy/<step-key>/claude/effective_policy.json
    <run_dir>/provider_policy/<step-key>/claude/capability_report.json
    ```
  * Map:

    * `model.default` → `model`
    * `permissions.mode="ask"` → permission `defaultMode="default"`
    * `permissions.mode="auto_edit"` → `defaultMode="acceptEdits"`
    * `permissions.mode="full_auto_sandboxed"` → sandbox enabled and auto approvals only when sandboxed
    * `permissions.mode="full_auto_unsandboxed"` → bypass only when dangerous bypass is explicitly allowed and strict policy permits it
    * `disable_dangerous_bypass=True` → `disableBypassPermissionsMode="disable"`
    * `filesystem.allow_read` → `sandbox.filesystem.allowRead`
    * `filesystem.allow_write` → `sandbox.filesystem.allowWrite`
    * `filesystem.deny_read` → `sandbox.filesystem.denyRead` and `permissions.deny += Read(...)`
    * `filesystem.deny_write` → `sandbox.filesystem.denyWrite` and `permissions.deny += Edit(...)`
    * `network.allow_domains` → `sandbox.network.allowedDomains` and/or `WebFetch(domain:...)` allow rules
    * `network.deny_domains` → `sandbox.network.deniedDomains` and/or `WebFetch(domain:...)` deny rules
  * If capabilities do not support sandbox filesystem fields, emit permission-rule approximations and mark OS-level enforcement as lossy.
  * Never emit `--dangerously-skip-permissions` unless `full_auto_unsandboxed` and dangerous bypass is explicitly allowed.

* **Provider transport integration**

  * Extend provider transport execution to use per-turn policy emissions.
  * Preferred design:

    ```python
    class PolicyAwareTransport(ProviderTransport):
        inner: ProviderTransport
        emitter: ProviderPolicyEmitter
    ```

    or provider-specific emitter integration inside `CodexTransport` / `ClaudeTransport`.
  * For each provider turn:

    * compute or receive resolved policy,
    * emit run-scoped config files,
    * apply capability validation,
    * pass config CLI args and env to subprocess.
  * Add metadata:

    ```python
    provider_metadata["policy"] = {
        "effective_policy_file": "...",
        "capability_report_file": "...",
        "policy_fingerprint": "...",
    }
    ```
  * Preserve session resume behavior and cross-provider resume checks.

* **Rendered turn changes**

  * Add policy field to rendered turn:

    ```python
    @dataclass(frozen=True, slots=True)
    class RenderedProviderTurn:
        ...
        policy: ResolvedProviderPolicy | None = None
    ```
  * Rendering should not dump full policy unless debug mode requires it.
  * If policy summary appears in prompt, redact env values.

* **Run-scoped policy directory**

  * Create:

    ```text
    <run_dir>/provider_policy/
      <safe-step-key>/
        effective_policy.json
        capability_report.json
        codex/
          config.toml
        claude/
          settings.json
    ```
  * Include emitted files in runtime trace metadata.
  * Do not treat generated provider policy files as user-authored artifacts unless runtime artifact tracking already handles generated files.

* **Tracing**

  * Add runtime events:

    ```text
    provider_policy_resolved
    provider_policy_emitted
    provider_policy_violation
    provider_policy_capability_report
    ```
  * Payload fields:

    * step name,
    * step execution id,
    * provider target,
    * policy fingerprint,
    * capability report path,
    * decision.
  * Exclude:

    * env values,
    * headers,
    * tokens,
    * secrets.

* **Testing: unit policy**

  * Add `tests/unit/test_provider_policy.py`.
  * Test:

    * system default policy is sandbox enabled, workspace-write, network full, full-auto sandboxed;
    * scalar merge behavior;
    * deny-read union;
    * deny-write union;
    * allow-write replacement;
    * env deny union;
    * strict rejects `danger_full_access`;
    * strict rejects disabled sandbox when required;
    * strict injects required deny read/write;
    * strict rejects write path outside allowed roots;
    * strict rejects local binding when forbidden;
    * strict rejects domains outside allowed domains;
    * strict detects symlink escape according to policy;
    * policy fingerprint is stable.

* **Testing: runtime config**

  * Add `tests/runtime/test_provider_policy_config.py`.
  * Test:

    * no config → system default policy;
    * global provider_policy default merges with workspace provider_policy default;
    * workspace strict policy applies;
    * `--policy-file` overrides/extends config;
    * unknown `provider_policy` key fails;
    * invalid enum fails with path-aware error;
    * existing provider model/model_effort still maps correctly;
    * existing `runtime.full_auto` maps to `full_auto_sandboxed`;
    * current provider backend config tests still pass.

* **Testing: step policies**

  * Add `tests/runtime/test_provider_policy_steps.py`.
  * Test:

    * workflow policy inherited by provider steps;
    * step policy overrides workflow policy;
    * reusable policy object can be reused by two steps;
    * strict policy rejects unsafe step override;
    * `python_step(policy=...)` affects `llm()` / `classify()` operations only;
    * explicit operation policy overrides current step policy.

* **Testing: emitters**

  * Add `tests/runtime/test_provider_policy_emitters.py`.
  * Codex tests:

    * full-auto sandboxed emits workspace-write sandbox;
    * allow-write maps to writable roots;
    * network full maps to workspace-write network access;
    * unsupported deny-read produces capability report;
    * unsupported domain allow/deny produces capability report;
    * dangerous bypass rejected unless allowed.
  * Claude tests:

    * allow-write maps to sandbox filesystem allowWrite;
    * deny-write maps to sandbox filesystem denyWrite and permission deny rules;
    * deny-read maps to sandbox filesystem denyRead and permission deny rules;
    * disable bypass emits `disableBypassPermissionsMode`;
    * network domains map to sandbox network allowed/denied domains;
    * capability profile without sandbox filesystem marks OS enforcement as lossy.
  * Capability report tests:

    * unsupported fail raises;
    * lossy warn continues with report;
    * unsafe expansion fail raises.

* **Testing: provider transports**

  * Extend existing provider tests.
  * Do not run real provider CLIs.
  * Use existing fake subprocess/help-surface patterns.
  * Verify:

    * Codex subprocess command includes policy config/CLI args;
    * Codex subprocess env includes emitted env policy;
    * Claude subprocess receives safe settings mechanism or fails if strict sandbox required and unsupported;
    * provider metadata includes policy report path;
    * cross-provider resume behavior remains unchanged.

* **Backward compatibility**

  * Existing configs without `provider_policy` must keep working.
  * Existing Codex model/model_effort settings must keep working.
  * Existing Claude model/effort/permission_strategy settings must keep working.
  * Existing runtime `full_auto` must keep working but map to `full_auto_sandboxed`.
  * Existing provider backend dispatch must keep rejecting unsupported provider names and module:function strings.
  * Existing provider tests should keep passing after updates.

* **Non-goals for this patch**

  * Full MCP support.
  * Full hooks support.
  * Subagents/agents.
  * Skills/plugins.
  * Managed enterprise policy emitters.
  * Arbitrary third-party provider backends.
  * Writing user/global provider settings files.
  * Changing provider prompt contracts except redacted policy metadata if needed.

* **Acceptance criteria**

  * Native P0 policy exists and includes model, permissions, sandbox, workspace filesystem, workspace network, env, and tools.
  * `default_policy` exists and uses system defaults when absent.
  * Optional `strict_policy` exists and validates after all normal merging.
  * Authors can define reusable `ProviderPolicy` objects and attach them to steps.
  * Step policies cannot silently exceed strict policy.
  * `allow_read`, `allow_write`, `deny_read`, and `deny_write` are typed native fields.
  * Deny rules are preserved and unioned through merges.
  * Provider policy files are generated under the run directory.
  * Codex and Claude emitters produce capability reports.
  * Unsupported/lossy/unsafe mappings obey validation modes.
  * Operation replay fingerprint includes policy fingerprint.
  * Secrets are not written to trace events or logs.
  * Existing provider config behavior remains compatible.

* **Suggested implementation order**

  * Step 1: implement core models, merge, strict validation, and unit tests.
  * Step 2: implement runtime config parsing and config tests.
  * Step 3: add workflow/step policy fields and compiler support.
  * Step 4: pass resolved policy through provider request/rendered turn models.
  * Step 5: emit capability reports without executing with generated configs yet.
  * Step 6: implement Codex emitter and transport integration.
  * Step 7: implement Claude emitter and transport integration.
  * Step 8: implement operation policy inheritance and replay fingerprinting.
  * Step 9: add runtime integration tests.
  * Step 10: update docs/config examples.

[1]: https://code.claude.com/docs/en/configuration?utm_source=chatgpt.com "Claude Code settings - Claude Code Docs"
[2]: https://docs.anthropic.com/en/docs/claude-code/settings?utm_source=chatgpt.com "Claude Code settings - Anthropic"
