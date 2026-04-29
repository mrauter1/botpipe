# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: implement
- Phase ID: engine-provider-persistence
- Phase Directory Key: engine-provider-persistence
- Phase Title: Runtime Contract Cleanup
- Scope: phase-local authoritative verifier artifact

- IMP-001 | blocking | `core/stores/protocols.py::normalize_session_snapshot`, `core/stores/protocols.py::_normalize_session_key_for_run`
  Legacy default-session checkpoints are not fully normalized on resume. Repro: normalizing `SessionSnapshot(bindings=(...), active_keys_by_slot={"default": SessionKey("default", "run", "default")})` currently yields `{"default": SessionKey(slot="global", domain="run", value="global")}` instead of rekeying the slot to `"global"` and rebinding the run key value to the current `run_id`. In the actual resume path (`Engine.run(..., resume=True)`), that leaves the active-session table indexed under the old slot name and can cause the canonical global session lookup to miss or duplicate the legacy binding instead of reusing it. This violates AC-2 for legacy default-session resume support. Minimal fix: centralize slot normalization so the helper first canonicalizes slot/value, then rewrites run-domain self-keys to `run_id`, and rebuilds `active_keys_by_slot` using the normalized slot name.

- IMP-002 | blocking | `runtime/stores/filesystem.py::_session_key_from_payload`
  The filesystem reader corrupts non-run session identities whose persisted value is literally `"default"`. Repro: `_session_key_from_payload({"slot": "orbit", "domain": "explicit_key", "value": "default"}, fallback_slot="orbit")` returns `SessionKey(slot="orbit", domain="explicit_key", value="global")`, and the same happens for `explicit_scope`. That is broader than the allowed legacy migration and can silently change persisted explicit key/scope/work-item bindings during checkpoint or session-store hydration. Minimal fix: make `"default" -> "global"` value rewriting domain-aware and apply it only to the legacy run-slot migration path, ideally by reusing the same normalization helper as the checkpoint snapshot restore path.
