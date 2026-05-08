Finish the shared-policy export cleanup on the simple public surface.

The current implementation still leaves `autoloop.simple.PolicyInput` importable and also leaves a stale `ProviderPolicyInput` alias importable from `autoloop.simple`. That violates the required export contract for this task:

- `PolicyInput` must remain publicly available from `autoloop.policy` and `autoloop.sdk`.
- `PolicyInput` must not be publicly importable from `autoloop.simple` or `autoloop`.
- `autoloop.simple` must not expose a duplicate policy type alias such as `ProviderPolicyInput`.

Required outcome:

- `from autoloop.simple import PolicyInput` fails.
- `getattr(autoloop.simple, "PolicyInput")` raises `AttributeError`.
- `from autoloop.simple import ProviderPolicyInput` fails or the symbol is otherwise removed from the public module namespace.
- Existing simple authoring declarations and runtime typing behavior continue to accept `Policy`, `ProviderPolicy`, `ProviderPolicyOverride`, and `None` where already supported.

Validation required:

- `./.venv/bin/pytest tests/unit/test_simple_policy.py`
- `./.venv/bin/pytest tests/unit/test_simple_surface.py tests/unit/test_policy.py tests/runtime/test_sdk_policy.py tests/unit/test_sdk_facade.py`
