Below is the revised standalone correction spec for Codex CLI. It incorporates the agreed cleanup: use `policy_layer`, remove the `ProviderPolicy` fingerprint shortcut, keep SDK/simple cleanup strict, and make CLI `--workspace` required if runtime CLI is included in this patch. This is based on the pasted implementation review. 

## Standalone correction spec: policy payload kind cleanup and public API consistency

* **Supersession directive:** This correction spec supersedes any previous wording that used:

  * `"kind": "policy"` for public `Policy(...)`
  * `"kind": "layer"` for public `Policy(...)`
  * `"kind": "policy"` for concrete `ProviderPolicy`
  * `"kind": "override"` for core `ProviderPolicyOverride`

* **Greenfield directive remains active:** Do not preserve public compatibility paths that conflict with the current greenfield public API.

* Implement this spec exactly.

* Scope:

  * Rename serialized/fingerprint kind labels for public `Policy(...)`.
  * Make public `Policy(...)` serialize consistently as `policy_layer`.
  * Make concrete core policies serialize with explicit core-kind names.
  * Remove the `ProviderPolicy` fingerprint shortcut in compiler/topology fingerprinting.
  * Clean up public-facing messages that leak internal policy types.
  * Confirm SDK/simple public naming cleanup remains enforced.
  * Rename runtime CLI public `--root` to `--workspace` if runtime CLI is part of this implementation patch.
  * Update existing tests or add new tests where needed.

---

## Required serialized kind names

* Public `Policy(...)` is an inheriting policy layer.

* Every public `Policy(...)` occurrence in serialized/fingerprint payloads must use:

```python
{"kind": "policy_layer", "payload": ...}
```

* This applies whether the public `Policy(...)` appears:

  * as a top-level workflow policy
  * as a step policy
  * as an SDK client default policy
  * as an SDK run policy
  * as an SDK step-invocation policy
  * as an inline operation policy
  * as `base=` inside another public `Policy(...)`

* Public `Policy(...)` must never serialize as:

```python
{"kind": "policy"}
```

* Public `Policy(...)` must never serialize as:

```python
{"kind": "layer"}
```

* Concrete core `ProviderPolicy` must serialize as:

```python
{"kind": "provider_policy", "payload": ...}
```

* Concrete core `ProviderPolicyOverride` must serialize as:

```python
{"kind": "provider_policy_override", "payload": ...}
```

* Rationale:

  * `Policy(...)` is public and sparse/inheriting.
  * `ProviderPolicy` is concrete and engine-facing.
  * `ProviderPolicyOverride` is core/internal sparse policy.
  * Serialized kinds must make those distinctions explicit.

---

## `Policy.to_layer_payload()` correction

* Update `Policy.to_layer_payload()` in `autoloop/policy.py`.

* If `self.base` is a public `Policy`, serialize it as:

```python
payload["base"] = {
    "kind": "policy_layer",
    "payload": self.base.to_layer_payload(),
}
```

* If `self.base` is a concrete `ProviderPolicy`, serialize it as:

```python
payload["base"] = {
    "kind": "provider_policy",
    "payload": self.base.model_dump(mode="json", warnings=False),
}
```

* `Policy.to_layer_payload()` must never emit:

```python
{"kind": "policy"}
```

* `Policy.to_layer_payload()` must never emit:

```python
{"kind": "layer"}
```

* `Policy.to_layer_payload()` must remain deterministic:

  * include only explicitly supplied fields
  * convert enum values to strings
  * convert paths to strings
  * convert tuples to JSON-compatible lists
  * preserve deterministic ordering where dict insertion order is relied upon
  * serialize nested `base` recursively when `base` is a public `Policy`

---

## Compiler/fingerprint payload correction

* Update compiler policy fingerprint serialization wherever policy inputs are serialized.

* In compiler helpers such as `_policy_input_payload(...)`, public `Policy` must serialize as:

```python
{
    "kind": "policy_layer",
    "payload": policy.to_layer_payload(),
}
```

* Do not serialize public `Policy` as:

```python
{
    "kind": "layer",
    "payload": ...
}
```

* Do not serialize public `Policy` as:

```python
{
    "kind": "policy",
    "payload": ...
}
```

* Concrete `ProviderPolicy` in compiler/fingerprint payloads must serialize as:

```python
{
    "kind": "provider_policy",
    "payload": policy.model_dump(mode="json", warnings=False),
}
```

* Concrete `ProviderPolicyOverride` in compiler/fingerprint payloads must serialize as:

```python
{
    "kind": "provider_policy_override",
    "payload": policy.model_dump(mode="json", warnings=False),
}
```

* `_policy_input_fingerprint(...)` must compute fingerprints from `_policy_input_payload(...)` for all non-`None` policy inputs, including concrete `ProviderPolicy`.

* Do not bypass `_policy_input_payload(...)` with `policy_fingerprint(...)` in compiler/topology fingerprinting.

* `policy_fingerprint(...)` may remain available for other internal uses, but compiler/topology fingerprinting must use the unified payload-kind scheme.

* The fingerprint must change when the serialized kind changes.

* The fingerprint must remain stable for identical authored `Policy(...)` inputs.

* SDK run policy must still not affect workflow topology hash.

---

## Public error-message cleanup

* Audit public-facing SDK/simple/core-normalization error messages.

* Public-facing errors should refer to public concepts:

  * `Policy`
  * `core provider policy object`
  * `provider policy layer`
  * `concrete ProviderPolicy` only when the user directly supplied a core type

* Avoid exposing `ProviderPolicyOverride` in public SDK/simple error messages.

* `ProviderPolicyOverride` may still appear in:

  * internal code comments
  * internal type aliases
  * core-only tests
  * advanced/core error messages where the user explicitly passed a core object

* Replace public normalization messages such as:

```text
must be a Policy, ProviderPolicy, or ProviderPolicyOverride
```

with public wording such as:

```text
must be a Policy or core provider policy object
```

* If a message is explicitly core/internal and intentionally mentions all accepted types, this wording is acceptable:

```text
must be a Policy, concrete ProviderPolicy, or internal ProviderPolicyOverride
```

* Prefer the shorter public wording in SDK/simple APIs.

* Keep runtime compatibility for concrete `ProviderPolicy` and core `ProviderPolicyOverride` where the implementation already accepts them internally.

* Do not add a public `PolicyOverride` constructor, import, docs path, or example.

---

## SDK/simple public API cleanup confirmation

* Ensure the public SDK constructor accepts:

```python
Autoloop(workspace=..., default_policy=...)
```

* Ensure the public SDK constructor rejects:

```python
Autoloop(root=...)
```

* Ensure `workspace` means the actual project/repository working directory.

* Ensure `.autoloop` remains the internal state directory inside `workspace`.

* Ensure `client.run(...)` accepts:

```python
input=...
params=...
policy=...
```

* Ensure `client.run(...)` rejects:

```python
typed_input=...
parameters=...
```

* Ensure `client.step(...)` accepts:

```python
input=...
params=...
policy=...
```

* Ensure `client.step(...)` rejects:

```python
typed_input=...
parameters=...
```

* Ensure SDK step helper examples use simple-style writes:

```python
writes=(Md("report"), Json("data"))
```

* Remove public SDK examples using mapping-style writes:

```python
writes={"report": Md(...)}
```

* Mapping-style writes may remain internal only if needed by lower-level implementation, but it must not be documented or surfaced as the canonical SDK shape.

---

## Runtime CLI naming cleanup

* If this implementation patch includes `autoloop/runtime/cli.py`, rename public `--root` flags to `--workspace`.

* If CLI is handled in a separate patch, track this as a required follow-up, not as optional compatibility.

* Runtime CLI public help text must say “workspace” for the user project/repository directory.

* Internally, the resolved path may still be stored in a variable named `root`.

* Do not expose new public `--root` flags.

* If old CLI `--root` flags currently exist in the implementation scope, remove them under the greenfield directive.

* Tests must assert that `--workspace` is the supported public flag for runtime CLI entry points covered by this patch.

---

## `__all__` cleanup

* `autoloop.policy.__all__` must include:

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

* `autoloop.__all__` must include:

  * `Policy`
  * `ProviderName`
  * `ModelEffort`
  * `ModelVerbosity`
  * `ReasoningSummary`
  * `SandboxMode`
  * `NetworkMode`
  * `PermissionMode`

* `autoloop.sdk.__all__` must include:

  * `Policy`
  * `PolicyInput`
  * `ProviderName`
  * `ModelEffort`
  * `ModelVerbosity`
  * `ReasoningSummary`
  * `SandboxMode`
  * `NetworkMode`
  * `PermissionMode`

* `autoloop.simple.__all__` must include:

  * `Policy`
  * `ProviderName`
  * `ModelEffort`
  * `ModelVerbosity`
  * `ReasoningSummary`
  * `SandboxMode`
  * `NetworkMode`
  * `PermissionMode`

* Do not add `PolicyOverride` to any public `__all__`.

---

## Required tests

* Add or update tests for `Policy.to_layer_payload()`.

* Test nested public `Policy` base:

```python
base = Policy(effort=ModelEffort.LOW)
child = Policy(base=base, allow_write="reports/")
payload = child.to_layer_payload()

assert payload["base"]["kind"] == "policy_layer"
assert payload["base"]["payload"]["effort"] == "low"
```

* Test concrete `ProviderPolicy` base:

```python
child = Policy(base=SYSTEM_DEFAULT_PROVIDER_POLICY, effort=ModelEffort.HIGH)
payload = child.to_layer_payload()

assert payload["base"]["kind"] == "provider_policy"
```

* Test `to_layer_payload()` never emits `"kind": "policy"` for public `Policy` bases.

* Test `to_layer_payload()` never emits `"kind": "layer"` for public `Policy` bases.

* Test compiler/fingerprint helper for public `Policy` emits:

```python
{"kind": "policy_layer", "payload": ...}
```

* Test compiler/fingerprint helper for concrete `ProviderPolicy` emits:

```python
{"kind": "provider_policy", "payload": ...}
```

* Test compiler/fingerprint helper for core `ProviderPolicyOverride` emits:

```python
{"kind": "provider_policy_override", "payload": ...}
```

* Test `_policy_input_fingerprint(...)` uses `_policy_input_payload(...)` for concrete `ProviderPolicy`.

* Test deterministic fingerprinting:

  * identical `Policy(...)` inputs produce identical payloads/fingerprints
  * different authored policy fields produce different payloads/fingerprints
  * different policy kinds produce different payloads/fingerprints even if nested policy values are otherwise similar

* Test no public `PolicyOverride` export:

  * `PolicyOverride` is not in `autoloop.__all__`
  * `PolicyOverride` is not in `autoloop.policy.__all__`
  * `PolicyOverride` is not in `autoloop.simple.__all__`
  * `PolicyOverride` is not in `autoloop.sdk.__all__`

* Test SDK public naming:

  * `Autoloop(workspace=tmp_path)` works
  * `Autoloop(root=tmp_path)` raises `TypeError`
  * `client.run(..., input=...)` works
  * `client.run(..., typed_input=...)` raises `TypeError`
  * `client.run(..., params=...)` works
  * `client.run(..., parameters=...)` raises `TypeError`

* Test SDK/simple writes shape:

  * SDK helpers accept `writes=(Md("report"),)`
  * public SDK helper examples do not use mapping-style writes

* Test CLI naming if runtime CLI is in scope:

  * `--workspace` works
  * `--root` is not accepted

---

## Non-goals

* Do not redesign the policy facade.

* Do not reintroduce public `PolicyOverride`.

* Do not change the public `Policy(...)` authoring shape.

* Do not alter provider emitters unless a test failure reveals they consume the corrected serialized kind directly.

* Do not change runtime YAML/TOML config policy syntax.

* Do not change strict-policy validation semantics.

* Do not add compatibility aliases for removed public names.

---

## Acceptance criteria

* Every public `Policy(...)` serialized/fingerprint occurrence uses:

```python
"kind": "policy_layer"
```

* No public serialized/fingerprint payload for public `Policy(...)` uses:

```python
"kind": "policy"
```

* No public serialized/fingerprint payload for public `Policy(...)` uses:

```python
"kind": "layer"
```

* Concrete `ProviderPolicy` serialized/fingerprint payloads use:

```python
"kind": "provider_policy"
```

* Core `ProviderPolicyOverride` serialized/fingerprint payloads use:

```python
"kind": "provider_policy_override"
```

* Compiler/topology fingerprinting uses the unified `_policy_input_payload(...)` path for all policy input kinds.

* Public SDK and simple surfaces still expose only `Policy` as the public policy facade.

* Removed public compatibility names remain removed:

  * no public `root=`
  * no public `typed_input=`
  * no public `parameters=`
  * no public `PolicyOverride`
  * no raw strings for enum-backed `Policy(...)` fields

* Existing policy resolution behavior remains unchanged except for corrected serialized/fingerprint kind labels.

* Existing tests plus the updated policy/SDK/CLI cleanup tests pass.

Implement the spec exactly as written; do not preserve older public API compatibility where this spec explicitly removes it.
