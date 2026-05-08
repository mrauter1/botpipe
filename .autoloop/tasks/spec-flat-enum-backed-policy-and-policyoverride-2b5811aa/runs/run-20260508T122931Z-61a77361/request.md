## Spec: flat enum-backed `Policy(...)` and `PolicyOverride(...)` facade for Autoloop v3

* Implement a flat public policy authoring API in `autoloop/simple.py`.

* Add two public helper functions:

  * `Policy(...) -> ProviderPolicy`
  * `PolicyOverride(...) -> ProviderPolicyOverride`

* Add public enum classes for all fixed option sets:

  * `ProviderName`
  * `ModelEffort`
  * `ModelVerbosity`
  * `ReasoningSummary`
  * `SandboxMode`
  * `NetworkMode`
  * `PermissionMode`

* Export all new public names from:

  * `autoloop/simple.py`
  * `autoloop/__init__.py`
  * `autoloop.__all__`

* Do **not** modify the nested core schema in `autoloop/core/provider_policy.py`.

* Do **not** add flat fields directly to `ProviderPolicy`.

* Do **not** add Pydantic pre-validators to `ProviderPolicy` to accept undeclared flat kwargs.

* Keep these as the canonical engine-facing objects:

  * `ProviderPolicy`
  * `ProviderPolicyOverride`
  * `ModelPolicy`
  * `PermissionPolicy`
  * `SandboxPolicy`
  * `WorkspacePolicy`
  * `WorkspaceFilesystemPolicy`
  * `WorkspaceNetworkPolicy`

* The flat facade must lower into the nested core policy objects.

* Fixed option fields in the flat facade must use public enums, not arbitrary strings.

* Internal serialized policy values must remain strings, because the existing nested schema, config files, JSON fingerprints, and provider emitters already operate on string values.

* The public facade may continue to accept arbitrary strings only for open-ended values:

  * `model`
  * `base_url`
  * filesystem paths
  * network domains
  * permission rule patterns
  * model override keys and values

* The public facade must reject raw strings for enum-backed fields at runtime with `TypeError`.

* The enum-backed fields are:

  * `provider`
  * `effort`
  * `verbosity`
  * `reasoning_summary`
  * `sandbox_mode`
  * `network`
  * `permission_mode`

---

## Public enum definitions

* Implement enum support in Python 3.10-compatible form.

* Do not require Python 3.11 `StrEnum`.

* Add this base class in `autoloop/simple.py`:

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

* Enum names must be documented and used in all new examples and tests.

* Raw string examples for enum-backed fields must not be added.

---

## Primary authoring shape

* Workflow-level policy shape:

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

* Step-level override shape:

```python
from autoloop import Workflow, Policy, PolicyOverride, ModelEffort, step, FINISH


class DocsPatchWorkflow(Workflow):
    policy = Policy(
        network_domains=("docs.python.org", "github.com"),
        allow_write=("src/", "tests/"),
        effort=ModelEffort.MEDIUM,
    )

    inspect = step(
        "Inspect the repository and produce a plan.",
        policy=PolicyOverride(
            effort=ModelEffort.LOW,
            read_only=True,
        ),
        routes={"done": "implement"},
    )

    implement = step(
        "Apply the plan.",
        policy=PolicyOverride(
            allow_write=("src/", "tests/"),
            effort=ModelEffort.HIGH,
        ),
        routes={"done": FINISH},
    )
```

* Dangerous full-auto access must use the same flat API shape:

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

* Dangerous sandbox access without changing permission mode must also use the same flat API shape:

```python
from autoloop import Workflow, Policy, SandboxMode, ModelEffort, step, FINISH


class DangerousManualWorkflow(Workflow):
    policy = Policy(
        sandbox_mode=SandboxMode.DANGER_FULL_ACCESS,
        effort=ModelEffort.HIGH,
    )

    inspect = step(
        "Run the operation with unrestricted sandbox mode.",
        routes={"done": FINISH},
    )
```

* Do not implement special constructors such as:

  * `Policy.workspace_write(...)`
  * `Policy.read_only(...)`
  * `Policy.danger_full_access(...)`

* Do not implement namespaced keyword syntax such as:

  * `Network.domains=...`

* Do not support uppercase aliases such as:

  * `Allow_write`
  * `Deny_write`
  * `Network_domains`

* The accepted public keyword is `network_domains`.

* Unknown kwargs should naturally raise Python `TypeError`.

---

## Public signatures

* Implement `Policy(...)` with this signature:

```python
from collections.abc import Mapping, Sequence
from pathlib import Path


def Policy(
    *,
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
) -> ProviderPolicy:
    ...
```

* Implement `PolicyOverride(...)` with the same public keyword parameters and return type `ProviderPolicyOverride`.

* `Policy(...)` must always return a complete `ProviderPolicy`.

* `PolicyOverride(...)` must always return a sparse `ProviderPolicyOverride`.

* `Policy(...)` is not sparse.

* `PolicyOverride(...)` is the sparse form.

* Do not include `allow_dangerous_bypass` in either public signature.

* Do not include `disable_dangerous_bypass` in either public signature.

* The facade must set dangerous-bypass fields internally when dangerous access is requested.

---

## Imports required in `autoloop/simple.py`

* Import these from `collections.abc`:

  * `Mapping`
  * `Sequence`

* Import `Path` from `pathlib`.

* Import `Enum` from `enum`.

* Import these from `autoloop.core.provider_policy`:

  * `ModelPolicy`
  * `PermissionPolicy`
  * `ProviderPolicy`
  * `ProviderPolicyOverride`
  * `SandboxPolicy`
  * `SYSTEM_DEFAULT_PROVIDER_POLICY`
  * `WorkspaceFilesystemPolicy`
  * `WorkspaceNetworkPolicy`
  * `WorkspacePolicy`

---

## Shared coercion helpers

* Implement private coercion helpers in `autoloop/simple.py`.

* Add:

```python
def _policy_enum_value(value: object, *, enum_cls: type[_PolicyEnum], field_name: str) -> str | None:
    ...
```

* `_policy_enum_value(None, ...)` must return `None`.

* `_policy_enum_value(enum_member, ...)` must return `enum_member.value`.

* `_policy_enum_value(raw_string, ...)` must raise `TypeError`.

* `_policy_enum_value(other_type, ...)` must raise `TypeError`.

* The error message should tell the author to use the relevant enum class.

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

* Do not treat `str` as a sequence.

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

## Model lowering

* `model` lowers to `ModelPolicy.default`.

* `provider=ProviderName.CODEX` lowers to `ModelPolicy.provider == "codex"`.

* `provider=ProviderName.CLAUDE` lowers to `ModelPolicy.provider == "claude"`.

* `base_url` lowers to `ModelPolicy.base_url`.

* `effort=ModelEffort.MEDIUM` lowers to `ModelPolicy.effort == "medium"`.

* `verbosity=ModelVerbosity.HIGH` lowers to `ModelPolicy.verbosity == "high"`.

* `reasoning_summary=ReasoningSummary.CONCISE` lowers to `ModelPolicy.reasoning_summary == "concise"`.

* `model_overrides` lowers to `ModelPolicy.overrides`.

* Raw string values for `provider`, `effort`, `verbosity`, or `reasoning_summary` must raise `TypeError` in the flat facade.

* The nested core schema may continue accepting strings; only the flat facade is enum-strict.

---

## Permission lowering

* `permission_mode=PermissionMode.ASK` lowers to `PermissionPolicy.mode == "ask"`.

* `permission_mode=PermissionMode.AUTO_EDIT` lowers to `PermissionPolicy.mode == "auto_edit"`.

* `permission_mode=PermissionMode.FULL_AUTO_SANDBOXED` lowers to `PermissionPolicy.mode == "full_auto_sandboxed"`.

* `permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED` lowers to `PermissionPolicy.mode == "full_auto_unsandboxed"`.

* `permission_mode=PermissionMode.DENY_ALL` lowers to `PermissionPolicy.mode == "deny_all"`.

* `allow_permissions` lowers to `PermissionPolicy.allow`.

* `ask_permissions` lowers to `PermissionPolicy.ask`.

* `deny_permissions` lowers to `PermissionPolicy.deny`.

* Permission rules remain strings because they are open-ended provider/tool permission patterns.

* Raw string values for `permission_mode` must raise `TypeError` in the flat facade.

* `permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED` must imply:

  * `sandbox_mode=SandboxMode.DANGER_FULL_ACCESS` if `sandbox_mode is None`
  * `PermissionPolicy.allow_dangerous_bypass=True`

* If `permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED` and `sandbox_mode=SandboxMode.READ_ONLY`, raise `ValueError`.

* If `permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED` and `sandbox_mode=SandboxMode.WORKSPACE_WRITE`, raise `ValueError`.

* If `sandbox_mode=SandboxMode.DANGER_FULL_ACCESS`, lower internally to:

  * `SandboxPolicy.mode == "danger_full_access"`
  * `PermissionPolicy.allow_dangerous_bypass is True`

* If `sandbox_mode=SandboxMode.DANGER_FULL_ACCESS` and `permission_mode=PermissionMode.FULL_AUTO_SANDBOXED`, raise `ValueError`.

* Do not require a `reason` field for dangerous access.

* Do not implement a separate dangerous-access helper.

* Existing strict-policy validation must remain responsible for rejecting dangerous access where strict policy forbids it.

---

## Sandbox mode lowering

* `sandbox_mode=SandboxMode.READ_ONLY` lowers to `SandboxPolicy.mode == "read_only"`.

* `sandbox_mode=SandboxMode.WORKSPACE_WRITE` lowers to `SandboxPolicy.mode == "workspace_write"`.

* `sandbox_mode=SandboxMode.DANGER_FULL_ACCESS` lowers to `SandboxPolicy.mode == "danger_full_access"`.

* Raw string values for `sandbox_mode` must raise `TypeError`.

* `read_only=True` is a convenience alias for `sandbox_mode=SandboxMode.READ_ONLY`.

* If `read_only=True` and `sandbox_mode is None`, set effective sandbox mode to `SandboxMode.READ_ONLY`.

* If `read_only=True` and `sandbox_mode != SandboxMode.READ_ONLY`, raise `ValueError`.

* If `read_only=True`, set `WorkspaceFilesystemPolicy.allow_write=()`.

* If `sandbox_mode=SandboxMode.READ_ONLY`, set `WorkspaceFilesystemPolicy.allow_write=()`.

* If `read_only=True` and `allow_write is not None`, raise `ValueError`.

* If `sandbox_mode=SandboxMode.READ_ONLY` and `allow_write is not None`, raise `ValueError`.

* If `read_only=False`, `sandbox_mode is None`, and `allow_write is not None`, set effective sandbox mode to `SandboxMode.WORKSPACE_WRITE`.

* If `sandbox_mode=SandboxMode.DANGER_FULL_ACCESS`, do not reject `allow_read`, `deny_read`, `allow_write`, or `deny_write`.

  * The facade should lower them if provided.
  * Runtime emitters and strict validation remain responsible for actual enforcement/reporting.

---

## Filesystem lowering

* `allow_read` lowers to `WorkspaceFilesystemPolicy.allow_read`.

* `deny_read` lowers to `WorkspaceFilesystemPolicy.deny_read`.

* `allow_write` lowers to `WorkspaceFilesystemPolicy.allow_write`.

* `deny_write` lowers to `WorkspaceFilesystemPolicy.deny_write`.

* A scalar string such as `allow_write="src/"` must normalize to `("src/",)`.

* A tuple such as `allow_write=("src/", "tests/")` must remain ordered.

* Duplicate paths must be removed while preserving the first occurrence.

* `Policy(read_only=True)` must set:

  * `sandbox.mode == "read_only"`
  * `sandbox.workspace.filesystem.allow_write == ()`

* `PolicyOverride(read_only=True)` must also set:

  * `sandbox.mode == "read_only"`
  * `sandbox.workspace.filesystem.allow_write == ()`

* This is required so a read-only override cannot inherit write roots from an outer policy after merge.

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

* Raw string values for `network` must raise `TypeError`.

* `network_domains=<non-empty>` with `network is None` must imply `network=NetworkMode.LIMITED`.

* `network_domains=None` with `network is None` must leave network policy unchanged for `PolicyOverride(...)`.

* `network_domains=None` with `network is None` must preserve `SYSTEM_DEFAULT_PROVIDER_POLICY` network values for `Policy(...)`.

* `network_domains=()` with `network is None` must raise `ValueError`.

* `network=NetworkMode.LIMITED` requires non-empty `network_domains`.

* `network=NetworkMode.LIMITED` without `network_domains` must raise `ValueError`.

* `network=NetworkMode.FULL` with non-empty `network_domains` must raise `ValueError`.

* `network=NetworkMode.NONE` with non-empty `network_domains` must raise `ValueError`.

* `deny_network_domains` lowers to `WorkspaceNetworkPolicy.deny_domains`.

* `allow_local_binding` lowers to `WorkspaceNetworkPolicy.allow_local_binding`.

---

## `Policy(...)` construction algorithm

* Start from:

```python
SYSTEM_DEFAULT_PROVIDER_POLICY.model_dump(mode="python", warnings=False)
```

* Apply only flat fields whose effective value changes because the caller passed a non-`None` value or because another flat field implied them.

* Convert enum members to their `.value` strings before building nested Pydantic policy objects.

* Build the nested payload shape expected by `ProviderPolicy`.

* Return:

```python
ProviderPolicy.model_validate(updated_payload)
```

* `Policy()` with no args must return a `ProviderPolicy` equivalent to `SYSTEM_DEFAULT_PROVIDER_POLICY`.

* `Policy(effort=ModelEffort.MEDIUM)` must return a complete provider policy with only model effort changed from the system default.

* `Policy(allow_write="src/")` must return a complete provider policy with:

  * `sandbox.mode == "workspace_write"`
  * `sandbox.workspace.filesystem.allow_write == ("src/",)`

* `Policy(network_domains=("docs.python.org",))` must return a complete provider policy with:

  * `sandbox.workspace.network.mode == "limited"`
  * `sandbox.workspace.network.allow_domains == ("docs.python.org",)`

* `Policy(permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED)` must return a complete provider policy with:

  * `permissions.mode == "full_auto_unsandboxed"`
  * `permissions.allow_dangerous_bypass is True`
  * `sandbox.mode == "danger_full_access"`

* `Policy(sandbox_mode=SandboxMode.DANGER_FULL_ACCESS)` must return a complete provider policy with:

  * `sandbox.mode == "danger_full_access"`
  * `permissions.allow_dangerous_bypass is True`
  * the default permission mode preserved unless explicitly overridden.

---

## `PolicyOverride(...)` construction algorithm

* Build a payload from scratch.

* Convert enum members to their `.value` strings before building nested Pydantic policy objects.

* Include `model` only if at least one model-related flat field was supplied.

* Include `permissions` only if:

  * at least one permission-related flat field was supplied, or
  * dangerous access implied `allow_dangerous_bypass=True`.

* Include `sandbox` only if:

  * at least one sandbox field was supplied, or
  * at least one filesystem field was supplied, or
  * at least one network field was supplied, or
  * dangerous access was implied.

* Include `workspace.filesystem` only if:

  * at least one filesystem field was supplied, or
  * read-only mode requires `allow_write=()`.

* Include `workspace.network` only if at least one network field was supplied.

* Return:

```python
ProviderPolicyOverride.model_validate(payload)
```

* `PolicyOverride(effort=ModelEffort.LOW)` must return a sparse override with:

  * `model.effort == "low"`
  * `sandbox is None`
  * `permissions is None`

* `PolicyOverride(allow_write="src/")` must return a sparse override with:

  * `sandbox.mode == "workspace_write"`
  * `sandbox.workspace.filesystem.allow_write == ("src/",)`

* `PolicyOverride(read_only=True)` must return a sparse override with:

  * `sandbox.mode == "read_only"`
  * `sandbox.workspace.filesystem.allow_write == ()`

* `PolicyOverride(permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED)` must return a sparse override with:

  * `permissions.mode == "full_auto_unsandboxed"`
  * `permissions.allow_dangerous_bypass is True`
  * `sandbox.mode == "danger_full_access"`

* `PolicyOverride(sandbox_mode=SandboxMode.DANGER_FULL_ACCESS)` must return a sparse override with:

  * `sandbox.mode == "danger_full_access"`
  * `permissions.allow_dangerous_bypass is True`

---

## Internal helper structure

* Implement a private helper to avoid duplicating lowering logic.

* Suggested helper:

```python
def _flat_policy_payload(
    *,
    full_policy: bool,
    model: str | None,
    provider: ProviderName | None,
    base_url: str | None,
    effort: ModelEffort | None,
    verbosity: ModelVerbosity | None,
    reasoning_summary: ReasoningSummary | None,
    model_overrides: Mapping[str, str] | None,
    sandbox_mode: SandboxMode | None,
    read_only: bool,
    allow_read: object,
    deny_read: object,
    allow_write: object,
    deny_write: object,
    network: NetworkMode | None,
    network_domains: object,
    deny_network_domains: object,
    allow_local_binding: bool | None,
    permission_mode: PermissionMode | None,
    allow_permissions: object,
    ask_permissions: object,
    deny_permissions: object,
) -> dict[str, object]:
    ...
```

* The exact helper name may differ.

* The helper must support both full and sparse policy payload construction.

* The helper must centralize:

  * enum normalization
  * read-only handling
  * workspace-write inference
  * network-domain inference
  * dangerous-access inference
  * tuple coercion
  * validation of incompatible flat inputs

---

## Docstrings

* `Policy` docstring:

```python
"""Flat workflow-level authoring facade for ProviderPolicy.

Omitted fields preserve SYSTEM_DEFAULT_PROVIDER_POLICY. Fixed option fields use
Autoloop policy enums rather than raw strings. network_domains implies limited
network mode. allow_write implies workspace_write mode unless read_only or
sandbox_mode=SandboxMode.READ_ONLY is set, which is invalid with allow_write.
sandbox_mode=SandboxMode.DANGER_FULL_ACCESS and
permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED use the same flat API and
internally enable the dangerous-bypass latch required by the nested policy
schema.
"""
```

* `PolicyOverride` docstring:

```python
"""Flat step/operation-level authoring facade for ProviderPolicyOverride.

Only supplied fields are included in the override payload. Fixed option fields
use Autoloop policy enums rather than raw strings. read_only=True also sets
allow_write=() so merged policy cannot inherit write roots. network_domains
implies limited network mode. sandbox_mode=SandboxMode.DANGER_FULL_ACCESS and
permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED use the same flat API and
internally enable the dangerous-bypass latch required by the nested policy
schema.
"""
```

---

## Existing policy normalization behavior

* Keep `_normalize_provider_policy(policy)` unchanged unless import ordering requires a small adjustment.

* The objects returned by `Policy(...)` and `PolicyOverride(...)` should already satisfy existing accepted policy types.

* Do not change workflow discovery or compilation validation except through the new helper objects naturally being instances of accepted policy classes.

---

## Tests to add

* Add tests in either:

  * `tests/unit/test_simple_surface.py`
  * or a new `tests/unit/test_simple_policy.py`

### Export tests

* `from autoloop import Policy, PolicyOverride` must work.

* `from autoloop.simple import Policy, PolicyOverride` must work.

* `from autoloop import ProviderName, ModelEffort, ModelVerbosity, ReasoningSummary, SandboxMode, NetworkMode, PermissionMode` must work.

* `from autoloop.simple import ProviderName, ModelEffort, ModelVerbosity, ReasoningSummary, SandboxMode, NetworkMode, PermissionMode` must work.

* `Policy` must be present in `autoloop.__all__`.

* `PolicyOverride` must be present in `autoloop.__all__`.

* All new enum classes must be present in `autoloop.__all__`.

* `callable(Policy)` must be true.

* `callable(PolicyOverride)` must be true.

### Basic return-type tests

* `Policy()` returns `ProviderPolicy`.

* `PolicyOverride(effort=ModelEffort.LOW)` returns `ProviderPolicyOverride`.

### Enum validation tests

* `Policy(effort="medium")` must raise `TypeError`.

* `Policy(provider="codex")` must raise `TypeError`.

* `Policy(verbosity="high")` must raise `TypeError`.

* `Policy(reasoning_summary="concise")` must raise `TypeError`.

* `Policy(sandbox_mode="workspace_write")` must raise `TypeError`.

* `Policy(network="none")` must raise `TypeError`.

* `Policy(permission_mode="full_auto_unsandboxed")` must raise `TypeError`.

* Equivalent `PolicyOverride(...)` cases must also raise `TypeError`.

### Workflow-level policy tests

* This must pass:

```python
policy = Policy(
    network_domains=("docs.python.org", "github.com"),
    allow_write=("src/", "tests/"),
    effort=ModelEffort.MEDIUM,
)
```

* Assert:

  * `isinstance(policy, ProviderPolicy)`
  * `policy.model.effort == "medium"`
  * `policy.sandbox.mode == "workspace_write"`
  * `policy.sandbox.workspace.filesystem.allow_write == ("src/", "tests/")`
  * `policy.sandbox.workspace.network.mode == "limited"`
  * `policy.sandbox.workspace.network.allow_domains == ("docs.python.org", "github.com")`

* `Policy(provider=ProviderName.CODEX)` must lower to:

  * `policy.model.provider == "codex"`

* `Policy(allow_write="src/")` must normalize to:

  * `("src/",)`

* `Policy(deny_write=(".env", ".env", "secrets/"))` must normalize to:

  * `(".env", "secrets/")`

* `Policy(read_only=True)` must set:

  * `sandbox.mode == "read_only"`
  * `sandbox.workspace.filesystem.allow_write == ()`

* `Policy(read_only=True, allow_write="src/")` must raise `ValueError`.

* `Policy(sandbox_mode=SandboxMode.READ_ONLY, allow_write="src/")` must raise `ValueError`.

* `Policy(network=NetworkMode.LIMITED)` must raise `ValueError`.

* `Policy(network_domains=())` must raise `ValueError`.

* `Policy(network=NetworkMode.NONE, network_domains=("github.com",))` must raise `ValueError`.

* `Policy(network=NetworkMode.FULL, network_domains=("github.com",))` must raise `ValueError`.

* `Policy(network=NetworkMode.NONE)` must set:

  * `network.enabled is False`
  * `network.mode == "none"`

* `Policy()` must preserve:

  * `SYSTEM_DEFAULT_PROVIDER_POLICY.permissions.mode`
  * `SYSTEM_DEFAULT_PROVIDER_POLICY.sandbox.mode`

### Dangerous workflow-level tests

* `Policy(sandbox_mode=SandboxMode.DANGER_FULL_ACCESS)` must set:

  * `policy.sandbox.mode == "danger_full_access"`
  * `policy.permissions.allow_dangerous_bypass is True`

* `Policy(permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED)` must set:

  * `policy.permissions.mode == "full_auto_unsandboxed"`
  * `policy.permissions.allow_dangerous_bypass is True`
  * `policy.sandbox.mode == "danger_full_access"`

* `Policy(permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED, sandbox_mode=SandboxMode.WORKSPACE_WRITE)` must raise `ValueError`.

* `Policy(permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED, sandbox_mode=SandboxMode.READ_ONLY)` must raise `ValueError`.

* `Policy(sandbox_mode=SandboxMode.DANGER_FULL_ACCESS, permission_mode=PermissionMode.FULL_AUTO_SANDBOXED)` must raise `ValueError`.

### Override tests

* `PolicyOverride(effort=ModelEffort.LOW)` must return `ProviderPolicyOverride`.

* Assert:

  * `override.model.effort == "low"`
  * `override.sandbox is None`
  * `override.permissions is None`

* `PolicyOverride(allow_write="src/")` must set:

  * `override.sandbox.mode == "workspace_write"`
  * `override.sandbox.workspace.filesystem.allow_write == ("src/",)`

* `PolicyOverride(network_domains="docs.python.org")` must set:

  * `override.sandbox.workspace.network.mode == "limited"`
  * `override.sandbox.workspace.network.allow_domains == ("docs.python.org",)`

* `PolicyOverride(read_only=True)` must set:

  * `override.sandbox.mode == "read_only"`
  * `override.sandbox.workspace.filesystem.allow_write == ()`

* Merging this must preserve unrelated defaults:

```python
resolved = merge_provider_policies(
    SYSTEM_DEFAULT_PROVIDER_POLICY,
    PolicyOverride(effort=ModelEffort.LOW),
)
```

* Assert:

  * `resolved.model.effort == "low"`
  * `resolved.sandbox == SYSTEM_DEFAULT_PROVIDER_POLICY.sandbox`
  * `resolved.permissions == SYSTEM_DEFAULT_PROVIDER_POLICY.permissions`

* Merging this must clear write roots:

```python
resolved = merge_provider_policies(
    SYSTEM_DEFAULT_PROVIDER_POLICY,
    PolicyOverride(read_only=True),
)
```

* Assert:

  * `resolved.sandbox.mode == "read_only"`
  * `resolved.sandbox.workspace.filesystem.allow_write == ()`

* Merging this must change write roots and inferred mode:

```python
resolved = merge_provider_policies(
    SYSTEM_DEFAULT_PROVIDER_POLICY,
    PolicyOverride(allow_write="src/"),
)
```

* Assert:

  * `resolved.sandbox.mode == "workspace_write"`
  * `resolved.sandbox.workspace.filesystem.allow_write == ("src/",)`

### Dangerous override tests

* `PolicyOverride(sandbox_mode=SandboxMode.DANGER_FULL_ACCESS)` must set:

  * `override.sandbox.mode == "danger_full_access"`
  * `override.permissions.allow_dangerous_bypass is True`

* `PolicyOverride(permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED)` must set:

  * `override.permissions.mode == "full_auto_unsandboxed"`
  * `override.permissions.allow_dangerous_bypass is True`
  * `override.sandbox.mode == "danger_full_access"`

* Merging this must produce a coherent dangerous policy:

```python
resolved = merge_provider_policies(
    SYSTEM_DEFAULT_PROVIDER_POLICY,
    PolicyOverride(permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED),
)
```

* Assert:

  * `resolved.permissions.mode == "full_auto_unsandboxed"`
  * `resolved.permissions.allow_dangerous_bypass is True`
  * `resolved.sandbox.mode == "danger_full_access"`

* `PolicyOverride(permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED, sandbox_mode=SandboxMode.WORKSPACE_WRITE)` must raise `ValueError`.

* `PolicyOverride(permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED, sandbox_mode=SandboxMode.READ_ONLY)` must raise `ValueError`.

* `PolicyOverride(sandbox_mode=SandboxMode.DANGER_FULL_ACCESS, permission_mode=PermissionMode.FULL_AUTO_SANDBOXED)` must raise `ValueError`.

### Workflow compilation test

* Define:

```python
from autoloop import Workflow, Policy, ModelEffort, step, FINISH
from autoloop.core.compiler import compile_workflow
from autoloop.core.provider_policy import ProviderPolicy


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

* Assert:

  * `isinstance(compiled.provider_policy, ProviderPolicy)`
  * `compiled.provider_policy.model.effort == "medium"`
  * `compiled.provider_policy.sandbox.mode == "workspace_write"`
  * `compiled.provider_policy.sandbox.workspace.filesystem.allow_write == ("src/",)`
  * `compiled.provider_policy.sandbox.workspace.network.mode == "limited"`
  * `compiled.provider_policy.sandbox.workspace.network.allow_domains == ("docs.python.org",)`

### Step policy compilation test

* Define:

```python
from autoloop import Workflow, PolicyOverride, ModelEffort, step, FINISH
from autoloop.core.compiler import compile_workflow
from autoloop.core.provider_policy import ProviderPolicyOverride


class StepPolicyWorkflow(Workflow):
    inspect = step(
        "Inspect only.",
        policy=PolicyOverride(
            effort=ModelEffort.LOW,
            read_only=True,
        ),
        routes={"done": FINISH},
    )


compiled = compile_workflow(StepPolicyWorkflow)
step_policy = compiled.steps["inspect"].provider_policy
```

* Assert:

  * `isinstance(step_policy, ProviderPolicyOverride)`
  * `step_policy.model.effort == "low"`
  * `step_policy.sandbox.mode == "read_only"`
  * `step_policy.sandbox.workspace.filesystem.allow_write == ()`

### Dangerous workflow compilation test

* Define:

```python
from autoloop import Workflow, Policy, PermissionMode, step, FINISH
from autoloop.core.compiler import compile_workflow


class DangerousWorkflow(Workflow):
    policy = Policy(
        permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED,
    )

    migrate = step(
        "Run migration.",
        routes={"done": FINISH},
    )


compiled = compile_workflow(DangerousWorkflow)
policy = compiled.provider_policy
```

* Assert:

  * `policy.sandbox.mode == "danger_full_access"`
  * `policy.permissions.mode == "full_auto_unsandboxed"`
  * `policy.permissions.allow_dangerous_bypass is True`

### Operation policy test

* Verify this passes `_normalize_provider_policy` or the existing operation policy normalization path:

```python
llm(
    "Summarize risks.",
    policy=PolicyOverride(effort=ModelEffort.LOW),
)
```

* Verify this also passes operation policy normalization:

```python
llm(
    "Run unrestricted analysis.",
    policy=PolicyOverride(
        permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED,
    ),
)
```

* No provider call is required for this test unless an existing operation test can be extended cheaply.

---

## Do not change

* Do not change provider emitters in this patch.

* Do not change Codex policy emitter behavior.

* Do not change Claude policy emitter behavior.

* Do not change runtime config YAML/TOML provider-policy parsing.

* Do not change provider policy resolver merge order.

* Do not change strict-policy validation semantics.

* Do not change provider policy schema definitions.

* Do not add a compatibility layer for uppercase aliases.

* Do not add a separate dangerous-access constructor.

* Do not allow raw strings for enum-backed fields in the new flat facade.

---

## Minimum test commands

* Run:

```bash
pytest tests/unit/test_simple_surface.py
pytest tests/unit/test_provider_policy.py
pytest tests/runtime/test_provider_policy_steps.py
pytest tests/runtime/test_provider_policy_emitters.py
pytest tests/runtime/test_provider_policy_config.py
```

* If a new file is created, also run:

```bash
pytest tests/unit/test_simple_policy.py
```

---

## Acceptance criterion

* This exact workflow must import, compile, and lower correctly:

```python
from autoloop import Workflow, Policy, PolicyOverride, ModelEffort, step, FINISH


class DocsPatchWorkflow(Workflow):
    policy = Policy(
        network_domains=("docs.python.org", "github.com"),
        allow_write=("src/", "tests/"),
        deny_write=(".env", "secrets/"),
        effort=ModelEffort.MEDIUM,
    )

    inspect = step(
        "Inspect the repository and produce a plan.",
        policy=PolicyOverride(
            effort=ModelEffort.LOW,
            read_only=True,
        ),
        routes={"done": "implement"},
    )

    implement = step(
        "Use the plan and update src/ and tests/ only.",
        policy=PolicyOverride(
            allow_write=("src/", "tests/"),
            effort=ModelEffort.HIGH,
        ),
        routes={"done": FINISH},
    )
```

* This exact dangerous-access workflow must also import, compile, and lower correctly:

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

* The dangerous-access workflow must lower to:

  * `sandbox.mode == "danger_full_access"`
  * `permissions.mode == "full_auto_unsandboxed"`
  * `permissions.allow_dangerous_bypass is True`
