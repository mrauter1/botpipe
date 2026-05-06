# Test Author ↔ Test Auditor Feedback

- Task ID: this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0
- Pair: test
- Phase ID: runtime-and-inspection-alignment
- Phase Directory Key: runtime-and-inspection-alignment
- Phase Title: Align Runtime And Reporting
- Scope: phase-local authoritative verifier artifact

- Added focused coverage for simplified provider-schema fallback reporting, topology-hash sensitivity to route visibility/schema metadata, and selected-workflow capability/decomposition payload exposure of compiled route contracts and inheritance details.
- Added a follow-up selected-workflow inspection fallback test that forces `schema_simplified=True` through `inspect_workflow_reference()` and asserts the capability/decomposition payloads surface the same fallback metadata as the static-graph artifacts.
- TST-001 `blocking`: `tests/runtime/test_runtime_static_graph.py::test_static_graph_and_compile_report_surface_simplified_provider_schema_fallback` covers the forced fallback path only for `workflow_static_step_graph_payload()` and `compile_report.md`, but the same phase also added `provider_response_contracts` fallback reporting to selected-workflow inspection payloads in `autoloop/core/workflow_capabilities.py`. The only selected-workflow assertions in `tests/unit/test_stdlib_and_extensions.py:2661-2671` pin `schema_simplified is False`, so a regression that drops or mis-propagates `True` on `selected_workflow_capability_payload()` / `selected_workflow_decomposition_surface_payload()` would pass. Add a deterministic forced-fallback test on those inspection payloads as well, preferably by reusing the same monkeypatched schema-builder approach already recorded in `decisions.txt`.
- Re-audit result: no remaining blocking or non-blocking findings. `TST-001` is addressed by `tests/unit/test_stdlib_and_extensions.py::test_selected_workflow_inspection_payloads_surface_simplified_provider_schema_fallback`, which forces fallback before `inspect_workflow_reference()` and verifies the selected-workflow inspection payloads propagate the fallback metadata.
