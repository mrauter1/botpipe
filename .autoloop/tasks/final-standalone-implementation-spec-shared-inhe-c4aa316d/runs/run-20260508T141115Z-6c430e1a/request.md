## Final standalone implementation spec: shared inheriting `Policy(...)` facade, SDK/simple API alignment, and greenfield cleanup

* **Greenfield directive:** Treat this project as greenfield for the public API decisions in this specification.

* **Supersession directive:** This specification supersedes and takes precedence over all earlier policy-facade specs, SDK API notes, simple API notes, brainstorms, invariants, and compatibility assumptions discussed previously.

* If any previous instruction, older spec, existing naming convention, or older API assumption conflicts with this document, implement this document.

* Remove public compatibility layers that conflict with this spec.

  * Remove public SDK `root=` compatibility.
  * Remove public SDK `typed_input=` compatibility.
  * Do not add public `parameters=` compatibility for workflow parameters.
  * Do not add public `PolicyOverride`.
  * Do not add uppercase policy keyword aliases.
  * Do not allow raw strings for enum-backed public `Policy(...)` fields.

* Implement a single shared public policy authoring facade for Autoloop v3.

* Implement SDK and simple API naming consistently.

* Treat `autoloop.simple` as the canonical authoring style for workflow/step concepts.

* Treat SDK APIs as programmatic entry points that use the same public vocabulary and shapes as the simple authoring API wherever the concepts match.

---

## Canonical public naming conventions

* Public APIs must use `workspace` for the actual user project/repository working directory.

* `workspace` does **not** mean the `.autoloop` directory.

* `.autoloop` is the internal Autoloop state directory inside the workspace.

* Canonical distinction:

```text
workspace = actual project/repository working directory
state_root = workspace / ".autoloop"
```

* Provider filesystem policies such as `allow_write=("src/", "tests/")` are relative to the workspace root unless absolute paths are explicitly supplied and allowed by lower-level policy behavior.

* Internal runtime code may continue using `root` for the resolved absolute workspace path.

* Public SDK APIs must use `workspace=`, not `root=`, as the user-facing constructor parameter.

* Remove public `root=` SDK constructor compatibility.

* Public SDK APIs must use `input=` for typed workflow input.

* Remove public `typed_input=` SDK compatibility.

* Public simple and SDK APIs must use `params=` for workflow parameters, matching `Workflow.Params`.

* Do not introduce `parameters=` as a public workflow-parameter argument.

* `prompt` means provider/step instruction.

* `message` means task/run request.

* Keep `prompt` and `message` distinct where both concepts are present.

* `control_routes` remains a workflow/step authoring concept.

* `provider_questions` remains an SDK/runtime behavior option.

* Do not merge or rename `control_routes` and `provider_questions`; document their distinction.

---

## Shared policy module

* Create a new module:

```text
autoloop/policy.py
```

* `autoloop/policy.py` is the canonical implementation module and source of truth for:

  * `Policy`
  * `PolicyInput`
  * `ProviderName`
  * `ModelEffort`
  * `ModelVerbosity`
  * `ReasoningSummary`
  * `SandboxMode`
  * `NetworkMode`
  * `PermissionMode`
  * shared policy coercion helpers
  * shared policy resolution helpers

* Do **not** implement or export a public `PolicyOverride(...)` facade.

* Do **not** duplicate policy enums, type definitions, or flattening logic in `autoloop/simple.py`.

* Do **not** duplicate policy enums, type definitions, or flattening logic in `autoloop/sdk.py`.

* `autoloop.policy` is the canonical module path for policy definitions.

* `autoloop.__init__` must re-export the public policy names as the primary user-facing import path.

* `autoloop.simple` must re-export shared policy names from `autoloop.policy`.

* `autoloop.sdk` must re-export shared policy names from `autoloop.policy`.

* Keep the nested core provider-policy schema as the engine-facing representation:

  * `ProviderPolicy`
  * `ProviderPolicyOverride`
  * `ModelPolicy`
  * `PermissionPolicy`
  * `SandboxPolicy`
  * `WorkspacePolicy`
  * `WorkspaceFilesystemPolicy`
  * `WorkspaceNetworkPolicy`

* Do **not** modify `ProviderPolicy` to accept flat public kwargs.

* Do **not** add Pydantic pre-validators to `ProviderPolicy` for public flat fields.

* Public `Policy(...)` must be an inheriting policy layer:

  * It stores only author-supplied fields.
  * It does not eagerly fill unspecified fields from `SYSTEM_DEFAULT_PROVIDER_POLICY`.
  * It resolves against a base policy at runtime or explicit inspection time.
  * Unset fields always inherit from the base policy.

* Concrete `ProviderPolicy` objects are produced only by resolution.

* Existing internal/core `ProviderPolicyOverride` remains supported as an internal/core compatibility type only.

* Do not add a public constructor, public re-export, public example, or public documentation path named `PolicyOverride`.

---

## Public authoring examples

* Primary import path for examples:

```python
from autoloop import Policy, ModelEffort
```

* Canonical module import path for advanced users and tests:

```python
from autoloop.policy import Policy, ModelEffort
```

* Local convenience import paths must also work:

```python
from autoloop.simple import Policy, ModelEffort
from autoloop.sdk import Policy, ModelEffort
```

* Workflow-level policy example:

```python
from autoloop import Workflow, Policy, ModelEffort, step, FINISH


class DocsPatchWorkflow(Workflow):
    policy = Policy(
        network_domains=("docs.python.org", "github.com"),
        allow_write=("src/", "tests/"),
        deny_write=(".env", "secrets/"),
        effort=ModelEffort.MEDIUM,
    )

    implement = step(
        "Use the allowed documentation domains and update the code.",
        routes={"done": FINISH},
    )
```

* Step-level policy example:

```python
from autoloop import Workflow, Policy, ModelEffort, step, FINISH


class DocsPatchWorkflow(Workflow):
    policy = Policy(
        network_domains=("docs.python.org", "github.com"),
        allow_write=("src/", "tests/"),
        effort=ModelEffort.MEDIUM,
    )

    inspect = step(
        "Inspect only.",
        policy=Policy(
            effort=ModelEffort.LOW,
            read_only=True,
        ),
        routes={"done": "implement"},
    )

    implement = step(
        "Apply the plan.",
        policy=Policy(
            allow_write=("src/", "tests/"),
            effort=ModelEffort.HIGH,
        ),
        routes={"done": FINISH},
    )
```

* SDK client default policy example:

```python
from autoloop import Autoloop, Policy, ModelEffort


client = Autoloop(
    workspace=".",
    default_policy=Policy(
        network_domains=("docs.python.org", "github.com"),
        effort=ModelEffort.MEDIUM,
    ),
)
```

* SDK per-run policy example:

```python
result = client.run(
    DocsPatchWorkflow,
    "Fix the bug.",
    policy=Policy(
        allow_write="reports/",
        effort=ModelEffort.HIGH,
    ),
)
```

* SDK one-step invocation policy example:

```python
result = client.step(
    some_step,
    "Run this one step.",
    policy=Policy(
        read_only=True,
        effort=ModelEffort.LOW,
    ),
)
```

* Dangerous full-auto access example:

```python
from autoloop import Workflow, Policy, PermissionMode, ModelEffort, step, FINISH


class DangerousMigrationWorkflow(Workflow):
    policy = Policy(
        permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED,
        effort=ModelEffort.HIGH,
    )

    migrate = step(
        "Run the unrestricted migration.",
        routes={"done": FINISH},
    )
```

* Dangerous sandbox access without full-auto permission example:

```python
from autoloop import Workflow, Policy, SandboxMode, ModelEffort, step, FINISH


class DangerousManualWorkflow(Workflow):
    policy = Policy(
        sandbox_mode=SandboxMode.DANGER_FULL_ACCESS,
        effort=ModelEffort.HIGH,
    )

    inspect = step(
        "Run with unrestricted sandbox mode.",
        routes={"done": FINISH},
    )
```

---

## Public `Policy(...)` semantics

* `Policy(...)` represents a policy layer, not an immediately concrete provider policy.

* `Policy(...)` must not mean “start from system default and fill every field immediately.”

* `Policy(...)` means:

  * inherit unset values from the effective base policy
  * override only the fields supplied by the author

* If `base=` is not supplied, the base is the effective policy from the previous resolver layer.

* If `base=` is supplied, unset values inherit from that explicit base.

* `base=` may be:

  * another public `Policy`
  * a concrete core `ProviderPolicy`
  * `None`

* `base=` must not accept arbitrary dictionaries.

* `base=` must not accept raw flat dictionaries.

* `Policy(base=None, ...)` means “inherit from the ambient resolver base.”

* `Policy(base=some_policy, ...)` means:

  * resolve `some_policy`
  * apply this layer over the resolved result

* `Policy()` with no fields is a no-op layer:

  * resolved against base `X`, it produces `X`

* `Policy(effort=ModelEffort.HIGH)` means:

  * inherit every field from base
  * set only model effort to `"high"`

* `Policy(allow_write="reports/")` means:

  * inherit every field from base
  * set sandbox mode to `"workspace_write"`
  * set filesystem `allow_write` to `("reports/",)`

* `Policy(read_only=True)` means:

  * inherit every field from base
  * set sandbox mode to `"read_only"`
  * set filesystem `allow_write` to `()`

* `Policy(permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED)` means:

  * inherit every field from base
  * set permission mode to `"full_auto_unsandboxed"`
  * set sandbox mode to `"danger_full_access"`
  * internally set `permissions.allow_dangerous_bypass=True`

* `Policy(sandbox_mode=SandboxMode.DANGER_FULL_ACCESS)` means:

  * inherit every field from base
  * set sandbox mode to `"danger_full_access"`
  * internally set `permissions.allow_dangerous_bypass=True`
  * preserve inherited permission mode unless explicitly overridden

* Do not expose `allow_dangerous_bypass` as a public flat parameter.

* Do not expose a public `PolicyOverride`.

---

## Public enum definitions

* Implement enum support in Python 3.10-compatible form.

* Do not require Python 3.11 `StrEnum`.

* Add this base class in `autoloop/policy.py`:

```python
from enum import Enum


class _PolicyEnum(str, Enum):
    def __str__(self) -> str:
        return self.value
```

* Add:

```python
class ProviderName(_PolicyEnum):
    CODEX = "codex"
    CLAUDE = "claude"
```

* Add:

```python
class ModelEffort(_PolicyEnum):
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
```

* Add:

```python
class ModelVerbosity(_PolicyEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
```

* Add:

```python
class ReasoningSummary(_PolicyEnum):
    AUTO = "auto"
    CONCISE = "concise"
    DETAILED = "detailed"
    NONE = "none"
```

* Add:

```python
class SandboxMode(_PolicyEnum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    DANGER_FULL_ACCESS = "danger_full_access"
```

* Add:

```python
class NetworkMode(_PolicyEnum):
    FULL = "full"
    LIMITED = "limited"
    NONE = "none"
```

* Add:

```python
class PermissionMode(_PolicyEnum):
    ASK = "ask"
    AUTO_EDIT = "auto_edit"
    FULL_AUTO_SANDBOXED = "full_auto_sandboxed"
    FULL_AUTO_UNSANDBOXED = "full_auto_unsandboxed"
    DENY_ALL = "deny_all"
```

* Public fixed-option fields must use these enums.

* Raw strings must be rejected for enum-backed public `Policy(...)` fields.

* Internal serialized policy values must remain strings.

---

## Public `Policy` signature

* Implement `Policy` as a class, preferably immutable/frozen if practical.

* Public shape:

```python
from collections.abc import Mapping, Sequence
from pathlib import Path


class Policy:
    def __init__(
        self,
        *,
        base: "Policy | ProviderPolicy | None" = None,

        model: str | None = None,
        provider: ProviderName | None = None,
        base_url: str | None = None,
        effort: ModelEffort | None = None,
        verbosity: ModelVerbosity | None = None,
        reasoning_summary: ReasoningSummary | None = None,
        model_overrides: Mapping[str, str] | None = None,

        sandbox_mode: SandboxMode | None = None,
        read_only: bool = False,
        allow_read: str | Path | Sequence[str | Path] | None = None,
        deny_read: str | Path | Sequence[str | Path] | None = None,
        allow_write: str | Path | Sequence[str | Path] | None = None,
        deny_write: str | Path | Sequence[str | Path] | None = None,

        network: NetworkMode | None = None,
        network_domains: str | Sequence[str] | None = None,
        deny_network_domains: str | Sequence[str] | None = None,
        allow_local_binding: bool | None = None,

        permission_mode: PermissionMode | None = None,
        allow_permissions: str | Sequence[str] | None = None,
        ask_permissions: str | Sequence[str] | None = None,
        deny_permissions: str | Sequence[str] | None = None,
    ) -> None:
        ...
```

* `Policy` must store only explicitly supplied fields.

* `read_only=False` must be treated as unset.

* `read_only=True` must be stored as an explicit read-only request.

* `base` must be stored as supplied.

* `Policy` must expose:

```python
def resolve(
    self,
    base: ProviderPolicy | None = None,
) -> ProviderPolicy:
    ...
```

* `Policy.resolve(base=None)` must resolve against `SYSTEM_DEFAULT_PROVIDER_POLICY`.

* `Policy.resolve(base=some_provider_policy)` must resolve against `some_provider_policy`.

* `Policy.resolve(...)` must recursively resolve `self.base` first when `self.base` is supplied.

* Resolver internals may use helper functions instead of the public `resolve(...)` method, but externally observable behavior must match.

---

## Shared type alias and runtime checks

* Add this type alias in `autoloop/policy.py`:

```python
PolicyInput = Policy | ProviderPolicy | ProviderPolicyOverride | None
```

* `PolicyInput` must be used by public SDK APIs and internal resolver APIs where a policy layer may be accepted.

* `ProviderPolicyOverride` remains accepted as a compatibility/internal sparse layer type.

* Runtime checks must use explicit `isinstance` branches for:

  * `Policy`
  * `ProviderPolicy`
  * `ProviderPolicyOverride`
  * `None`

* Do not rely on `PolicyInput` for runtime type checks.

* Do not introduce a public constructor named `PolicyOverride`.

* Public examples must use `Policy(...)`, not `ProviderPolicyOverride`.

---

## Shared coercion helpers

* Implement these private helpers in `autoloop/policy.py`.

* Add:

```python
def _policy_enum_value(
    value: object,
    *,
    enum_cls: type[_PolicyEnum],
    field_name: str,
) -> str | None:
    ...
```

* `_policy_enum_value(None, ...)` must return `None`.

* `_policy_enum_value(enum_member, ...)` must return `enum_member.value`.

* `_policy_enum_value(raw_string, ...)` must raise `TypeError`.

* `_policy_enum_value(member_of_wrong_enum, ...)` must raise `TypeError`.

* The error message should instruct the author to use the relevant enum class.

* Add:

```python
def _policy_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    ...
```

* Add:

```python
def _policy_optional_tuple(value: object, *, field_name: str) -> tuple[str, ...] | None:
    ...
```

* Add:

```python
def _policy_string_mapping(value: object, *, field_name: str) -> dict[str, str] | None:
    ...
```

* `_policy_optional_tuple(None, ...)` must return `None`.

* `_policy_tuple(None, ...)` must return `()`.

* A single `str` must become a one-element tuple.

* A single `Path` must become a one-element tuple containing `str(path)`.

* A `Sequence[str | Path]` must become a tuple of strings.

* Do not treat `str` as a generic sequence.

* Do not treat `bytes` as valid.

* Strip whitespace from string entries.

* Reject empty string entries with `ValueError`.

* Reject unsupported item types with `TypeError`.

* Deduplicate values while preserving first occurrence order.

* `_policy_string_mapping(None, ...)` must return `None`.

* `_policy_string_mapping(...)` must reject non-mapping values with `TypeError`.

* `_policy_string_mapping(...)` must convert mapping keys and values to strings.

* `_policy_string_mapping(...)` must reject empty string keys with `ValueError`.

---

## Policy layer lowering

* Implement an internal helper that converts a public `Policy` layer into a sparse core `ProviderPolicyOverride`.

* Suggested helper:

```python
def _policy_layer_to_override(policy: Policy) -> ProviderPolicyOverride:
    ...
```

* This helper must include only fields explicitly supplied on the public `Policy`.

* This helper must not fill unspecified fields from `SYSTEM_DEFAULT_PROVIDER_POLICY`.

* Resolution must operate conceptually as:

```text
base ProviderPolicy + sparse ProviderPolicyOverride produced from Policy
```

* Reuse existing `merge_provider_policies(...)` behavior if available.

* Implement one central helper in `autoloop/policy.py`:

```python
def resolve_policy_layer(
    base: ProviderPolicy,
    layer: PolicyInput,
) -> ProviderPolicy:
    ...
```

* `resolve_policy_layer(base, None)` must return `base`.

* `resolve_policy_layer(base, ProviderPolicyOverride)` must merge the override into `base`.

* `resolve_policy_layer(base, Policy)` must:

  * resolve `Policy.base` first if supplied
  * convert public `Policy` fields to a sparse `ProviderPolicyOverride`
  * merge that override into the resolved base
  * return a concrete `ProviderPolicy`

* `resolve_policy_layer(base, ProviderPolicy)` must use the existing concrete policy semantics for core/legacy provider policies.

  * Do not reinterpret concrete `ProviderPolicy` as a public inheriting layer.
  * Public `Policy` is sparse/inheriting.
  * Concrete `ProviderPolicy` remains a complete legacy/core policy object.
  * Preserve current resolver behavior for concrete `ProviderPolicy` as closely as possible.

* Add recursion protection for cyclic `Policy(base=...)` references.

* Final resolved policy must be validated after all layers merge.

* Final validation must catch cross-layer conflicts, such as a base policy requesting unsandboxed full-auto permissions and a later layer changing sandbox mode back to workspace-write.

---

## Model lowering

* `model` lowers to `ModelPolicy.default`.

* `provider=ProviderName.CODEX` lowers to `ModelPolicy.provider == "codex"`.

* `provider=ProviderName.CLAUDE` lowers to `ModelPolicy.provider == "claude"`.

* `base_url` lowers to `ModelPolicy.base_url`.

* `effort=ModelEffort.MEDIUM` lowers to `ModelPolicy.effort == "medium"`.

* `verbosity=ModelVerbosity.HIGH` lowers to `ModelPolicy.verbosity == "high"`.

* `reasoning_summary=ReasoningSummary.CONCISE` lowers to `ModelPolicy.reasoning_summary == "concise"`.

* `model_overrides` lowers to `ModelPolicy.overrides`.

* Raw strings for `provider`, `effort`, `verbosity`, or `reasoning_summary` must raise `TypeError`.

---

## Sandbox lowering

* `sandbox_mode=SandboxMode.READ_ONLY` lowers to `SandboxPolicy.mode == "read_only"`.

* `sandbox_mode=SandboxMode.WORKSPACE_WRITE` lowers to `SandboxPolicy.mode == "workspace_write"`.

* `sandbox_mode=SandboxMode.DANGER_FULL_ACCESS` lowers to `SandboxPolicy.mode == "danger_full_access"`.

* Raw strings for `sandbox_mode` must raise `TypeError`.

* `read_only=True` is an alias for `sandbox_mode=SandboxMode.READ_ONLY`.

* If `read_only=True` and `sandbox_mode is None`, set effective sandbox mode to `"read_only"`.

* If `read_only=True` and `sandbox_mode != SandboxMode.READ_ONLY`, raise `ValueError`.

* If `read_only=True`, set `WorkspaceFilesystemPolicy.allow_write=()`.

* If `sandbox_mode=SandboxMode.READ_ONLY`, set `WorkspaceFilesystemPolicy.allow_write=()`.

* If `read_only=True` and `allow_write is not None`, raise `ValueError`.

* If `sandbox_mode=SandboxMode.READ_ONLY` and `allow_write is not None`, raise `ValueError`.

* If `read_only=False`, `sandbox_mode is None`, and `allow_write is not None`, set effective sandbox mode to `"workspace_write"`.

* If `sandbox_mode=SandboxMode.DANGER_FULL_ACCESS`, internally set `PermissionPolicy.allow_dangerous_bypass=True`.

* Do not expose `allow_dangerous_bypass` publicly.

---

## Filesystem lowering

* `allow_read` lowers to `WorkspaceFilesystemPolicy.allow_read`.

* `deny_read` lowers to `WorkspaceFilesystemPolicy.deny_read`.

* `allow_write` lowers to `WorkspaceFilesystemPolicy.allow_write`.

* `deny_write` lowers to `WorkspaceFilesystemPolicy.deny_write`.

* Scalar string paths normalize to one-element tuples.

* `Path` values normalize to strings.

* Duplicate paths are removed while preserving first occurrence order.

* Explicit empty tuples are allowed for filesystem fields.

* `Policy(read_only=True)` must set:

  * `sandbox.mode == "read_only"`
  * `sandbox.workspace.filesystem.allow_write == ()`

* This is required so a read-only policy layer clears inherited write roots.

---

## Network lowering

* Keep the public parameter name `network`.

* `network=NetworkMode.FULL` lowers to:

  * `WorkspaceNetworkPolicy.enabled=True`
  * `WorkspaceNetworkPolicy.mode == "full"`

* `network=NetworkMode.NONE` lowers to:

  * `WorkspaceNetworkPolicy.enabled=False`
  * `WorkspaceNetworkPolicy.mode == "none"`
  * `WorkspaceNetworkPolicy.allow_domains == ()`

* `network=NetworkMode.LIMITED` lowers to:

  * `WorkspaceNetworkPolicy.enabled=True`
  * `WorkspaceNetworkPolicy.mode == "limited"`
  * `WorkspaceNetworkPolicy.allow_domains == <normalized network_domains>`

* Raw strings for `network` must raise `TypeError`.

* `network_domains=<non-empty>` with `network is None` must imply `network=NetworkMode.LIMITED`.

* `network_domains=None` with `network is None` must leave inherited network policy unchanged.

* `network_domains=()` with `network is None` must raise `ValueError`.

* `network=NetworkMode.LIMITED` requires non-empty `network_domains`.

* `network=NetworkMode.LIMITED` without `network_domains` must raise `ValueError`.

* `network=NetworkMode.FULL` with non-empty `network_domains` must raise `ValueError`.

* `network=NetworkMode.NONE` with non-empty `network_domains` must raise `ValueError`.

* `deny_network_domains` lowers to `WorkspaceNetworkPolicy.deny_domains`.

* `allow_local_binding` lowers to `WorkspaceNetworkPolicy.allow_local_binding`.

---

## Permission lowering

* `permission_mode=PermissionMode.ASK` lowers to `PermissionPolicy.mode == "ask"`.

* `permission_mode=PermissionMode.AUTO_EDIT` lowers to `PermissionPolicy.mode == "auto_edit"`.

* `permission_mode=PermissionMode.FULL_AUTO_SANDBOXED` lowers to `PermissionPolicy.mode == "full_auto_sandboxed"`.

* `permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED` lowers to `PermissionPolicy.mode == "full_auto_unsandboxed"`.

* `permission_mode=PermissionMode.DENY_ALL` lowers to `PermissionPolicy.mode == "deny_all"`.

* Raw strings for `permission_mode` must raise `TypeError`.

* `allow_permissions` lowers to `PermissionPolicy.allow`.

* `ask_permissions` lowers to `PermissionPolicy.ask`.

* `deny_permissions` lowers to `PermissionPolicy.deny`.

* Permission rules remain strings because they are open-ended permission patterns.

* `permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED` must imply:

  * `sandbox_mode=SandboxMode.DANGER_FULL_ACCESS` if no explicit sandbox mode was supplied in the same layer
  * `PermissionPolicy.allow_dangerous_bypass=True`

* If `permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED` and `sandbox_mode=SandboxMode.READ_ONLY`, raise `ValueError`.

* If `permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED` and `sandbox_mode=SandboxMode.WORKSPACE_WRITE`, raise `ValueError`.

* If the same public `Policy` layer explicitly sets both:

  * `sandbox_mode=SandboxMode.DANGER_FULL_ACCESS`
  * `permission_mode=PermissionMode.FULL_AUTO_SANDBOXED`

  then raise `ValueError`.

* Do not require a `reason` field for dangerous access.

---

## Resolver merge order

* Extend policy resolution so every policy layer accepts `PolicyInput`.

* Effective merge order for workflow steps must be:

```text
SYSTEM_DEFAULT_PROVIDER_POLICY
→ runtime config default policy
→ SDK client default_policy
→ workflow class policy
→ SDK run policy
→ step policy
```

* Effective merge order for inline operations inside a workflow step must be:

```text
SYSTEM_DEFAULT_PROVIDER_POLICY
→ runtime config default policy
→ SDK client default_policy
→ workflow class policy
→ SDK run policy
→ current step policy
→ inline operation explicit policy
```

* Effective merge order for direct SDK operations such as `client.llm(...)` and `client.classify(...)` must be:

```text
SYSTEM_DEFAULT_PROVIDER_POLICY
→ runtime config default policy
→ SDK client default_policy
→ explicit operation policy
```

* Inline operations executed from a workflow step inherit the current compiled step policy before applying the explicit operation policy.

* Direct SDK operations do not have a current workflow step policy.

* Each public `Policy(...)` layer must resolve against the effective policy from the layer immediately before it unless it has an explicit `base=`.

* Existing strict-policy validation remains the hard enforcement boundary.

* `Policy(...)` is not a hard cap.

* If users need a hard security cap, that remains a strict-policy feature and is out of scope for this patch.

---

## Simple API integration

* `autoloop.simple` must import and re-export these from `autoloop.policy`:

  * `Policy`
  * `ProviderName`
  * `ModelEffort`
  * `ModelVerbosity`
  * `ReasoningSummary`
  * `SandboxMode`
  * `NetworkMode`
  * `PermissionMode`

* Do not define duplicate policy enums in `autoloop.simple`.

* Do not define duplicate flat-policy lowering helpers in `autoloop.simple`.

* Simple workflow authoring must accept public `Policy` in:

  * `Workflow.policy`
  * `step(..., policy=...)`
  * `llm(..., policy=...)`
  * `classify(..., policy=...)`
  * any other simple operation or declaration that already accepts provider policy objects

* Keep accepting concrete `ProviderPolicy` and core `ProviderPolicyOverride` internally for compatibility.

* Do not add a public `PolicyOverride` re-export from `simple`.

* Simple-style artifact output specs are canonical:

  * `writes=(Md(...), Json(...), Text(...), Raw(...))`

---

## SDK API integration

* `autoloop.sdk` must re-export shared policy names for convenience, while canonical policy definitions remain in `autoloop.policy`.

* `autoloop.sdk` must import these names from `autoloop.policy`, not define them:

  * `Policy`
  * `PolicyInput`
  * `ProviderName`
  * `ModelEffort`
  * `ModelVerbosity`
  * `ReasoningSummary`
  * `SandboxMode`
  * `NetworkMode`
  * `PermissionMode`

* Do not define duplicate policy enums in `autoloop.sdk`.

* Do not define duplicate flat-policy lowering helpers in `autoloop.sdk`.

* Update `Autoloop.__init__(...)` to accept:

```python
workspace: str | Path = "."
default_policy: PolicyInput = None
```

* `workspace` is the actual project/repository working directory.

* `workspace` is not `.autoloop`.

* Remove public SDK constructor compatibility for `root=`.

* Internally, the resolved absolute workspace path may be called `root`.

* `default_policy` is the SDK client-level policy layer.

* Store `default_policy` on the client.

* Do not resolve `default_policy` eagerly unless the runtime path requires a concrete effective policy.

* Update `Autoloop.run(...)` to accept:

```python
policy: PolicyInput = None
input: BaseModel | Mapping[str, object] | None = None
params: BaseModel | Mapping[str, object] | None = None
```

* `policy` on `Autoloop.run(...)` is the SDK per-run policy layer.

* `input=` is the canonical public name for typed workflow input.

* Remove public SDK compatibility for `typed_input=`.

* `params=` is the canonical public name for workflow parameters.

* Do not introduce `parameters=` as a canonical public name.

* Update `Autoloop.step(...)` to accept:

```python
policy: PolicyInput = None
input: BaseModel | Mapping[str, object] | None = None
params: BaseModel | Mapping[str, object] | None = None
```

* `policy` on `Autoloop.step(...)` applies only to that one step invocation.

* `Autoloop.step(..., policy=...)` must not mutate the caller-provided `Step` object.

* If the supplied `Step` object already has authored policy, `Autoloop.step(..., policy=...)` must apply as an invocation-local policy layer **after** the step’s authored policy for that one synthetic invocation.

* If necessary, implement this by creating an invocation-local copy or wrapper step.

* Special precedence for `client.step(..., policy=...)` must be:

```text
SDK client default_policy
→ synthetic workflow policy, if any
→ supplied step authored policy
→ client.step(..., policy=...)
```

* Update SDK step convenience helpers to accept `policy: PolicyInput = None` where applicable:

  * `client.prompt_step(...)`
  * `client.produce_verify_step(...)`
  * `client.python_step(...)`
  * `client.workflow_step(...)`

* SDK step helper signatures should align with simple naming and shapes.

* SDK step helpers should use `prompt` for provider/step instruction.

* SDK step helpers should use `message` for task/run request when they immediately execute a run.

* SDK step helpers should use `writes=(Md(...), Json(...), Text(...), Raw(...))` as the canonical artifact output shape.

* Remove public SDK examples using mapping-style `writes={...}`.

* Mapping-style `writes={...}` may remain internal only if required by existing lower-level code paths, but it must not be the public canonical SDK helper shape.

* For SDK helpers that construct a new step, `policy=` should attach to the constructed step as that step’s authored policy.

* Update direct SDK operation methods to accept public `Policy`:

  * `client.llm(..., policy=Policy(...))`
  * `client.classify(..., policy=Policy(...))`

* Existing support for concrete `ProviderPolicy` and core `ProviderPolicyOverride` should continue to work where already supported internally.

* Do not add SDK `strict_policy` in this patch.

* Do not add CLI policy flags in this patch.

* Do not change config-file policy syntax in this patch.

---

## SDK/simple naming alignment

* Public SDK APIs must use `workspace=`, matching the workspace concept used by the framework and providers.

* Public SDK APIs must use `input=`, matching workflow `Input` and runtime `ctx.input`.

* Public SDK APIs must use `params=`, matching workflow `Params`.

* Public SDK step helpers must use simple-style artifact specs as the canonical `writes` shape.

* Public SDK operation methods and simple operation helpers must share the same policy type: `PolicyInput`.

* `prompt` and `message` must remain distinct:

  * `prompt` = provider/step instruction
  * `message` = task/run request

* `control_routes` and `provider_questions` must remain distinct:

  * `control_routes` = workflow/step topology authoring
  * `provider_questions` = SDK/runtime behavior option

---

## Runtime/runner integration

* Add runner option fields or equivalent runtime wiring for:

  * SDK client default policy
  * SDK run policy

* Suggested neutral fields:

```python
RunnerOptions.sdk_default_policy: PolicyInput = None
RunnerOptions.run_policy: PolicyInput = None
```

* Do not smuggle SDK client default policy into runtime config defaults.

* Runtime config policy and SDK policy are distinct layers.

* Extend `ProviderPolicyResolver` to accept:

  * runtime config default policy
  * SDK client default policy
  * workflow policy
  * SDK run policy

* The resolver must own merge order.

* Do not duplicate merge logic in SDK methods.

* Direct SDK operations should use the same resolver or shared resolution helper, not separate ad hoc merge logic.

---

## Compiler/core integration

* Update workflow validation to accept public `Policy` objects for `Workflow.policy`.

* Keep accepting concrete `ProviderPolicy` for backwards compatibility.

* Keep accepting core `ProviderPolicyOverride` where already accepted internally.

* Update step policy normalization to accept public `Policy` objects.

* Update operation policy normalization to accept public `Policy` objects.

* Update compiled workflow and step policy typing to support `PolicyInput`.

* Update topology hash and compile-cache policy fingerprinting to support public `Policy`.

* Public `Policy` must expose a JSON-serializable authored-layer payload for fingerprinting.

* Suggested method:

```python
def to_layer_payload(self) -> dict[str, object]:
    ...
```

* `to_layer_payload()` must:

  * include only explicitly supplied fields
  * convert enum values to strings
  * convert paths to strings
  * include normalized tuples/lists in deterministic order
  * include nested base payload if `base` is a public `Policy`
  * include `ProviderPolicy.model_dump(mode="json", warnings=False)` if `base` is a concrete `ProviderPolicy`

* Compiler fingerprinting must include this layer payload for workflow and step policies.

* SDK run policy must not affect workflow topology hash.

---

## Import-cycle constraints

* `autoloop/policy.py` must not import `autoloop.simple`.

* `autoloop/policy.py` must not import `autoloop.sdk`.

* `autoloop/policy.py` may import core provider-policy types.

* `autoloop.simple` may import from `autoloop.policy`.

* `autoloop.sdk` may import from `autoloop.policy`.

* `autoloop.__init__` may re-export from `autoloop.policy`.

* This dependency direction must be preserved to avoid circular imports.

---

## `__all__` requirements

* `autoloop/policy.py` must define:

```python
__all__ = [
    "Policy",
    "PolicyInput",
    "ProviderName",
    "ModelEffort",
    "ModelVerbosity",
    "ReasoningSummary",
    "SandboxMode",
    "NetworkMode",
    "PermissionMode",
    "resolve_policy_layer",
]
```

* `autoloop/__init__.py` must re-export:

  * `Policy`
  * `ProviderName`
  * `ModelEffort`
  * `ModelVerbosity`
  * `ReasoningSummary`
  * `SandboxMode`
  * `NetworkMode`
  * `PermissionMode`

* `autoloop.simple` must re-export:

  * `Policy`
  * `ProviderName`
  * `ModelEffort`
  * `ModelVerbosity`
  * `ReasoningSummary`
  * `SandboxMode`
  * `NetworkMode`
  * `PermissionMode`

* `autoloop.sdk` must re-export:

  * `Policy`
  * `PolicyInput`
  * `ProviderName`
  * `ModelEffort`
  * `ModelVerbosity`
  * `ReasoningSummary`
  * `SandboxMode`
  * `NetworkMode`
  * `PermissionMode`

* Do not export public `PolicyOverride`.

---

## Docstrings

* `Policy` docstring:

```python
"""Flat inheriting policy layer for Autoloop.

Policy stores only supplied fields. Unset fields inherit from the effective
base policy at resolution time, or from the explicit base= policy when provided.
Fixed option fields use Autoloop policy enums rather than raw strings.
network_domains implies limited network mode. allow_write implies workspace_write
mode unless read_only=True or sandbox_mode=SandboxMode.READ_ONLY is set, which is
invalid with allow_write. Dangerous access uses the same flat API:
sandbox_mode=SandboxMode.DANGER_FULL_ACCESS and
permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED internally enable the
dangerous-bypass latch required by the nested core policy schema.
"""
```

* `Autoloop.__init__` docstring must explain:

  * `workspace` is the actual project/repository working directory.
  * `workspace` is not `.autoloop`.
  * `default_policy` is an SDK client-level policy layer.
  * unset values inherit from runtime config and system defaults.
  * it is not a hard security cap.

* `Autoloop.run` docstring must explain:

  * `message` is the task/run request.
  * `input` is typed workflow input.
  * `params` are workflow parameters.
  * `policy` is a per-run policy layer.
  * unset values inherit from client, workflow, config, and system layers.
  * it is not a hard security cap.

* `Autoloop.step` docstring must explain:

  * `policy` applies only to that one SDK step invocation.
  * the supplied step object is not mutated.
  * `message` is the task/run request.
  * `input` is typed input for the synthetic invocation when applicable.
  * `params` are workflow parameters for the synthetic invocation when applicable.

---

## Tests

### Export tests

* `from autoloop import Policy` works.

* `from autoloop.policy import Policy` works.

* `from autoloop.simple import Policy` works.

* `from autoloop.sdk import Policy` works.

* `from autoloop import ProviderName, ModelEffort, ModelVerbosity, ReasoningSummary, SandboxMode, NetworkMode, PermissionMode` works.

* `Policy` and all policy enum classes are present in `autoloop.__all__`.

* `PolicyOverride` is not added to `autoloop.__all__`.

### Basic construction tests

* `Policy()` constructs successfully.

* `Policy(effort=ModelEffort.LOW)` constructs successfully.

* `Policy(allow_write="src/")` constructs successfully.

* `Policy(base=Policy(effort=ModelEffort.LOW), effort=ModelEffort.HIGH)` constructs successfully.

* `Policy(base=SYSTEM_DEFAULT_PROVIDER_POLICY, effort=ModelEffort.HIGH)` constructs successfully.

* `Policy(base=Policy(effort=ModelEffort.LOW)).resolve().model.effort == "low"`.

### Enum validation tests

* `Policy(effort="medium")` raises `TypeError`.

* `Policy(provider="codex")` raises `TypeError`.

* `Policy(verbosity="high")` raises `TypeError`.

* `Policy(reasoning_summary="concise")` raises `TypeError`.

* `Policy(sandbox_mode="workspace_write")` raises `TypeError`.

* `Policy(network="none")` raises `TypeError`.

* `Policy(permission_mode="full_auto_unsandboxed")` raises `TypeError`.

* `Policy(effort=NetworkMode.FULL)` raises `TypeError`.

### Resolve tests

* `Policy().resolve()` equals `SYSTEM_DEFAULT_PROVIDER_POLICY`.

* `Policy(effort=ModelEffort.MEDIUM).resolve()` sets:

  * `model.effort == "medium"`
  * unrelated defaults preserved from `SYSTEM_DEFAULT_PROVIDER_POLICY`

* `Policy(allow_write="src/").resolve()` sets:

  * `sandbox.mode == "workspace_write"`
  * `sandbox.workspace.filesystem.allow_write == ("src/",)`

* `Policy(read_only=True).resolve()` sets:

  * `sandbox.mode == "read_only"`
  * `sandbox.workspace.filesystem.allow_write == ()`

* Given:

```python
base = Policy(
    network_domains=("docs.python.org",),
    effort=ModelEffort.LOW,
)
child = Policy(
    base=base,
    effort=ModelEffort.HIGH,
)
resolved = child.resolve()
```

* Assert:

  * `resolved.model.effort == "high"`
  * `resolved.sandbox.workspace.network.mode == "limited"`
  * `resolved.sandbox.workspace.network.allow_domains == ("docs.python.org",)`

* Given:

```python
base = Policy(read_only=True)
child = Policy(base=base, allow_write="reports/")
resolved = child.resolve()
```

* Assert:

  * `resolved.sandbox.mode == "workspace_write"`
  * `resolved.sandbox.workspace.filesystem.allow_write == ("reports/",)`

### Network tests

* `Policy(network_domains=("docs.python.org", "github.com")).resolve()` sets:

  * `network.mode == "limited"`
  * `network.allow_domains == ("docs.python.org", "github.com")`

* `Policy(network=NetworkMode.LIMITED)` raises `ValueError`.

* `Policy(network_domains=())` raises `ValueError`.

* `Policy(network=NetworkMode.NONE, network_domains=("github.com",))` raises `ValueError`.

* `Policy(network=NetworkMode.FULL, network_domains=("github.com",))` raises `ValueError`.

* `Policy(network=NetworkMode.NONE).resolve()` sets:

  * `network.enabled is False`
  * `network.mode == "none"`

### Read-only tests

* `Policy(read_only=True).resolve()` clears inherited write roots.

* Given a base with `allow_write=("src/",)`, resolving `Policy(read_only=True)` over that base results in:

  * `allow_write == ()`

* `Policy(read_only=True, allow_write="src/")` raises `ValueError`.

* `Policy(sandbox_mode=SandboxMode.READ_ONLY, allow_write="src/")` raises `ValueError`.

### Dangerous access tests

* `Policy(sandbox_mode=SandboxMode.DANGER_FULL_ACCESS).resolve()` sets:

  * `sandbox.mode == "danger_full_access"`
  * `permissions.allow_dangerous_bypass is True`

* `Policy(permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED).resolve()` sets:

  * `permissions.mode == "full_auto_unsandboxed"`
  * `permissions.allow_dangerous_bypass is True`
  * `sandbox.mode == "danger_full_access"`

* `Policy(permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED, sandbox_mode=SandboxMode.WORKSPACE_WRITE)` raises `ValueError`.

* `Policy(permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED, sandbox_mode=SandboxMode.READ_ONLY)` raises `ValueError`.

* `Policy(sandbox_mode=SandboxMode.DANGER_FULL_ACCESS, permission_mode=PermissionMode.FULL_AUTO_SANDBOXED)` raises `ValueError`.

### Path relativity tests

* `Policy(allow_write="reports/").resolve()` must represent `reports/` as relative to the effective workspace root.

* It must not interpret `reports/` as relative to `.autoloop`.

* SDK policy path tests should use `Autoloop(workspace=tmp_path)` and verify that policy paths are interpreted relative to `tmp_path`.

### Workflow compilation tests

* Define:

```python
from autoloop import Workflow, Policy, ModelEffort, step, FINISH
from autoloop.core.compiler import compile_workflow


class DocsPatchWorkflow(Workflow):
    policy = Policy(
        network_domains=("docs.python.org",),
        allow_write="src/",
        effort=ModelEffort.MEDIUM,
    )

    implement = step(
        "Update the code.",
        routes={"done": FINISH},
    )


compiled = compile_workflow(DocsPatchWorkflow)
```

* Assert the compiled workflow stores or accepts the public `Policy` layer.

* Resolve the compiled provider policy through the resolver and assert:

  * `model.effort == "medium"`
  * `sandbox.mode == "workspace_write"`
  * `filesystem.allow_write == ("src/",)`
  * `network.mode == "limited"`
  * `network.allow_domains == ("docs.python.org",)`

### Step policy compilation tests

* Define:

```python
from autoloop import Workflow, Policy, ModelEffort, step, FINISH
from autoloop.core.compiler import compile_workflow


class StepPolicyWorkflow(Workflow):
    inspect = step(
        "Inspect only.",
        policy=Policy(
            effort=ModelEffort.LOW,
            read_only=True,
        ),
        routes={"done": FINISH},
    )


compiled = compile_workflow(StepPolicyWorkflow)
```

* Assert the compiled step stores or accepts the public `Policy` layer.

* Resolve effective step policy and assert:

  * `model.effort == "low"`
  * `sandbox.mode == "read_only"`
  * `filesystem.allow_write == ()`

### SDK constructor and naming tests

* `Autoloop(workspace=tmp_path)` works.

* `Autoloop(root=tmp_path)` raises `TypeError`.

* `workspace` is interpreted as the actual project/repository working directory.

* Autoloop state is created under `workspace / ".autoloop"` if state creation is part of the tested code path.

* Public SDK examples and tests do not use `root=`.

* `client.run(..., input=...)` works for typed workflow input.

* `client.run(..., typed_input=...)` raises `TypeError`.

* `client.run(..., params=...)` works for workflow parameters.

* `client.run(..., parameters=...)` raises `TypeError`.

### SDK client default policy tests

* Create:

```python
client = Autoloop(
    workspace=tmp_path,
    default_policy=Policy(
        effort=ModelEffort.LOW,
        network_domains=("docs.python.org",),
    ),
)
```

* Run a simple workflow without workflow policy.

* Assert effective provider policy includes:

  * `model.effort == "low"`
  * `network.mode == "limited"`
  * `network.allow_domains == ("docs.python.org",)`

### SDK run policy tests

* Create client default:

```python
client = Autoloop(
    workspace=tmp_path,
    default_policy=Policy(effort=ModelEffort.LOW),
)
```

* Run:

```python
client.run(
    MyWorkflow,
    "Run it.",
    policy=Policy(effort=ModelEffort.HIGH),
)
```

* Assert run policy overrides client default:

  * effective effort is `"high"`

* Run:

```python
client.run(
    MyWorkflow,
    "Run it.",
    policy=Policy(allow_write="reports/"),
)
```

* Assert unset effort inherits from client, workflow, config, or system layers.

### SDK `client.step(...)` policy tests

* `client.step(..., policy=Policy(read_only=True))` must apply only to that invocation.

* The caller-provided step object must not be mutated.

* If the same step object is reused without `policy=...`, it must not retain the previous invocation policy.

* `client.step(..., policy=Policy(effort=ModelEffort.HIGH))` must resolve effective effort to `"high"` for that invocation.

* If a supplied step object already has authored policy, `client.step(..., policy=...)` must apply the invocation policy after the authored step policy for that invocation only.

### SDK helper tests

* `client.prompt_step(..., policy=Policy(effort=ModelEffort.LOW))` must construct a step with that policy.

* `client.produce_verify_step(..., policy=Policy(effort=ModelEffort.HIGH))` must construct a step with that policy.

* `client.workflow_step(..., policy=Policy(read_only=True))` must construct a step with that policy.

* SDK step helpers accept simple-style writes:

```python
client.prompt_step(
    prompt="Write a report.",
    message="Create the report.",
    writes=(Md("report"),),
)
```

* `client.llm(..., policy=Policy(effort=ModelEffort.LOW))` must accept public `Policy`.

* `client.classify(..., policy=Policy(effort=ModelEffort.LOW))` must accept public `Policy`.

### Topology/fingerprint tests

* Two otherwise identical workflows with different `Policy(effort=...)` layers must produce different topology or policy fingerprints where current system expects policy fingerprints to differ.

* SDK run policy must not affect workflow topology hash.

* `Policy.to_layer_payload()` must be deterministic for identical authored inputs.

---

## Do not change

* Do not change provider emitters in this patch.

* Do not change Codex policy emitter behavior.

* Do not change Claude policy emitter behavior.

* Do not change runtime config YAML/TOML policy syntax.

* Do not change strict-policy validation semantics.

* Do not change core provider-policy schema definitions.

* Do not add uppercase keyword aliases.

* Do not add public `PolicyOverride`.

* Do not allow raw strings for enum-backed fields in public `Policy`.

* Do not add SDK `strict_policy` in this patch.

* Do not add CLI policy flags in this patch.

---

## Minimum test commands

* Run existing relevant tests:

```bash
pytest tests/unit/test_provider_policy.py
pytest tests/runtime/test_provider_policy_steps.py
pytest tests/runtime/test_provider_policy_emitters.py
pytest tests/runtime/test_provider_policy_config.py
pytest tests/unit/test_simple_surface.py
pytest tests/unit/test_sdk_facade.py
```

* If new test files are created, also run:

```bash
pytest tests/unit/test_policy.py
pytest tests/runtime/test_sdk_policy.py
```

---

## Acceptance criteria

* This workflow must import, compile, and resolve correctly:

```python
from autoloop import Workflow, Policy, ModelEffort, step, FINISH


class DocsPatchWorkflow(Workflow):
    policy = Policy(
        network_domains=("docs.python.org", "github.com"),
        allow_write=("src/", "tests/"),
        deny_write=(".env", "secrets/"),
        effort=ModelEffort.MEDIUM,
    )

    inspect = step(
        "Inspect the repository and produce a plan.",
        policy=Policy(
            effort=ModelEffort.LOW,
            read_only=True,
        ),
        routes={"done": "implement"},
    )

    implement = step(
        "Use the plan and update src/ and tests/ only.",
        policy=Policy(
            allow_write=("src/", "tests/"),
            effort=ModelEffort.HIGH,
        ),
        routes={"done": FINISH},
    )
```

* This SDK usage must work:

```python
from autoloop import Autoloop, Policy, ModelEffort


client = Autoloop(
    workspace=".",
    default_policy=Policy(
        effort=ModelEffort.LOW,
        network_domains=("docs.python.org",),
    ),
)

result = client.run(
    DocsPatchWorkflow,
    "Fix the bug.",
    policy=Policy(
        effort=ModelEffort.HIGH,
        allow_write="reports/",
    ),
)
```

* This dangerous-access workflow must import, compile, and resolve correctly:

```python
from autoloop import Workflow, Policy, PermissionMode, ModelEffort, step, FINISH


class DangerousMigrationWorkflow(Workflow):
    policy = Policy(
        permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED,
        effort=ModelEffort.HIGH,
    )

    migrate = step(
        "Run the unrestricted migration.",
        routes={"done": FINISH},
    )
```

* The dangerous workflow must resolve to:

  * `sandbox.mode == "danger_full_access"`
  * `permissions.mode == "full_auto_unsandboxed"`
  * `permissions.allow_dangerous_bypass is True`

* No public API should require authors to choose between `Policy` and `PolicyOverride`.

* Unset public `Policy(...)` fields must always inherit from the effective base policy.

* Public SDK and simple APIs must consistently use:

  * `workspace` for the actual project/repository working directory
  * `input` for typed workflow input
  * `params` for workflow parameters
  * simple-style `writes=(Md(...), Json(...), Text(...), Raw(...))` for artifact output specs
  * `Policy` as the only public policy facade.

Implement the spec exactly as written; do not preserve older public API compatibility where this spec explicitly removes it.
