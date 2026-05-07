Task: Do a complete cleanup on unneeded, stale tests or out of scope tests.

Modify only tests/. Do not modify other folders.

I did a deeper pass over the extracted checkout and separated actually obsolete tests from tests that merely mention workflows, legacy, or docs while still protecting current v3 behavior.

The key correction to my first pass: not every test that mentions workflows is obsolete. The current runtime still supports user/workspace workflow packages under workflows/ and .autoloop/workflows/; those tests are valid when they create fixtures in tmp_path. What is obsolete is the assumption that this repository itself still contains bundled workflow packages under autoloop/workflows, repo-level docs under docs, recursive wrapper templates, or autoloop_v1 parity assets.

The uploaded current tree shows autoloop/core, autoloop/runtime, autoloop/stdlib, autoloop/sdk.py, and autoloop_optimizer; it does not show active autoloop/workflows, docs, recursive_autoloop, or autoloop/framework directories.

Probe results

I inspected the extracted checkout and found:

Probe	Result
Test files	53
Test functions by AST scan	1,305
Files that mention absent/legacy repo surfaces	29
Test functions in those files	759
Immediate top-level import blockers	2 files
Files that should be deleted or moved to a workflow-package suite	18 files / about 282 tests
Files that should stay but be edited/split	8–10 files

Stronger conclusion

The active suite should be narrowed to framework, runtime, SDK, stdlib, optimizer, catalog, and generated-fixture workflow tests.

It should stop running tests that validate bundled workflow packages that are no longer in this checkout.

The previous/legacy uploaded tree did include workflow packages built on the old autoloop.framework / Book-style architecture; for example, the old release_candidate_to_go_no_go package imports autoloop.framework.artifacts, autoloop.framework.boards, autoloop.framework.book, and related modules. The current checkout has moved away from that package shape, so tests that still assert old package assets are present are stale.

A. Delete or move these whole files

These should not be in default framework CI anymore.

1. tests/runtime/test_workflow_integration_parity.py

Delete or archive.

Reason: this is explicitly an autoloop_v1 parity suite. It imports autoloop.workflows.autoloop_v1.*, asserts discovery of autoloop_v1, and validates old raw_phase_log.md, phase events, and old v1 session paths.

This is not a current v3 framework contract. It is a migration-parity suite whose migration window appears to have passed.

2. tests/test_architecture_baseline_docs.py

Delete or move to a docs repo.

Reason: it assumes these repo-level assets exist:

DOCS_ROOT = PACKAGE_ROOT / "docs"
WORKFLOW_INSTRUCTIONS_PATH = PACKAGE_ROOT / "Workflow_Instructions.md"
WORKING_TREE_NOTE_PATH = PACKAGE_ROOT / "cleanup.md"
RECURSIVE_TEMPLATE_ROOT = PACKAGE_ROOT / "recursive_autoloop" / ...
WORKFLOW_PACKAGE_ROOT = PACKAGE_ROOT / "autoloop" / "workflows"

It then asserts docs and workflow prompt READMEs exist. These paths are absent from the current pasted tree. This is no longer a framework test; it is an asset-baseline test for a different repository shape.

3. tests/runtime/test_wheel_packaging_smoke.py

Rewrite or delete.

Current test name:

test_built_wheel_installs_cli_and_packaged_workflow_assets

It asserts packaged workflow assets, including autoloop_v1, are installed. Since the current tree does not include bundled workflows, this smoke test is stale.

Replacement should be much smaller:

test_built_wheel_installs_public_autoloop_package_and_cli

It should only check:

wheel builds
python -m autoloop or installed CLI imports
public API imports from autoloop
no bundled workflow package assumptions
4. Move the workflow-package runtime tests out of default CI

These are package regression tests, not framework tests, in the current checkout:

tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py
tests/runtime/test_company_operation_to_recursive_improvement_cycle.py
tests/runtime/test_incident_to_hardening_program.py
tests/runtime/test_investigation_request_to_evidence_pack.py
tests/runtime/test_release_candidate_to_go_no_go.py
tests/runtime/test_security_finding_to_verified_remediation.py
tests/runtime/test_task_to_candidate_workflow_set.py
tests/runtime/test_task_to_workflow_strategy.py
tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py
tests/runtime/test_workflow_builder_package.py
tests/runtime/test_workflow_package_to_composable_building_blocks.py
tests/runtime/test_workflow_portfolio_to_operating_system.py
tests/runtime/test_workflow_run_history_to_failure_modes.py
tests/runtime/test_workflow_run_traces_to_optimization_candidates.py
tests/runtime/test_workflow_to_eval_suite.py

Common stale pattern:

shutil.copytree(REPO_ROOT / "autoloop" / "workflows" / package_name, ...)
shutil.copytree(REPO_ROOT / "docs", ...)

That pattern appears directly in the runtime workflow-package tests. They also read docs and prompts under REPO_ROOT / "docs" / "workflows" and REPO_ROOT / "autoloop" / "workflows" / ....

These tests are useful only if the project intentionally restores or separately ships these workflow packages. Otherwise, move them to an optional suite such as:

tests/workflow_packages/

and run them only when autoloop/workflows exists.

B. Keep these files, but clean them
1. tests/unit/test_stdlib_and_extensions.py

Do not delete the whole file. It contains many legitimate tests for:

autoloop.stdlib
autoloop.extensions.git
autoloop.extensions.session_paths
autoloop_optimizer
selected-workflow helpers
candidate surfaces
diagnostics/evaluation/refinement helpers

But the file currently blocks collection because it imports absent workflow-package contract constants at top level:

from autoloop.workflows.candidate_workflow_to_adapted_execution_plan.contracts import ...
from autoloop.workflows.company_operation_to_recursive_improvement_cycle.contracts import ...
...

Those imports should be removed.

Recommended cleanup:

Replace imported workflow contract constants with local fixture JsonArtifactSpec declarations.
Move optimizer-related tests into tests/unit/optimizer/.
Move stdlib helper tests into tests/unit/stdlib/.
Move git/session extension tests into tests/unit/extensions/.
Delete doc-only assertions that read absent repo docs.
Keep tests that create their own temporary workflow packages and docs under tmp_path.
2. tests/unit/test_simple_surface.py

Keep the public API and simple-authoring tests.

Delete only the package-export tests that import old bundled workflows:

test_exported_public_simple_workflows_no_longer_fail_for_legacy_class_handlers
test_discovered_exported_workflow_sources_avoid_removed_public_contract_forms

The first parametrizes over autoloop.workflows.company_operation_to_recursive_improvement_cycle, autoloop.workflows.incident_to_hardening_program, and other absent package modules.

Everything that tests Workflow, step, python_step, produce_verify_step, Route, Session, FanIn, Worklist, validation errors, and public exports should stay.

3. tests/contract/test_engine_contracts.py

Keep the engine contracts, but split the file. It is over 10,000 lines and contains 182 test functions.

Remove this one docs-coupled test:

test_ctx_runtime_prompt_docs_describe_preferred_bindings_and_snapshot_semantics

It reads:

PACKAGE_ROOT / "docs" / "authoring.md"
PACKAGE_ROOT / "docs" / "architecture.md"

Those docs are not present in the current tree. The behavior itself should remain covered by runtime prompt/context tests, not docs text assertions.

Suggested split:

tests/contract/engine/test_artifacts.py
tests/contract/engine/test_routes.py
tests/contract/engine/test_sessions.py
tests/contract/engine/test_hooks.py
tests/contract/engine/test_worklists.py
tests/contract/engine/test_child_workflows.py
tests/contract/engine/test_runtime_controls.py
tests/contract/engine/test_prompt_context.py
tests/contract/engine/test_errors_and_retries.py
4. tests/runtime/test_package_cli.py

Keep tests that create temporary .autoloop/workflows packages and test the current runtime CLI.

Delete these stale recursive-wrapper tests:

test_recursive_wrapper_targets_the_global_cli_contract
test_recursive_templates_reference_current_global_cli_contract

They read recursive_autoloop/run_recursive_autoloop.sh and recursive_autoloop/run_recursive_autoloop_templates/..., but that directory is absent in the current checkout. The test also asserts references to docs and workflow roots that are no longer maintained in this repo.

5. tests/unit/test_optimization_helpers.py

Keep most of it. It tests autoloop_optimizer.optimization, which exists in the current tree.

But rewrite the helper:

_install_selected_workflow(root)

It copies:

REPO_ROOT / "autoloop" / "workflows" / "release_candidate_to_go_no_go"
REPO_ROOT / "docs"

Those paths are absent. The tests using that helper should create a small synthetic selected workflow package under tmp_path / "workflows" instead. This keeps optimizer source-manifest coverage without depending on old bundled packages.

6. tests/strictness/test_no_compat.py

Keep the idea, reduce the blast radius.

This file currently scans:

REPO_ROOT / "autoloop"
REPO_ROOT / "docs"
REPO_ROOT / "autoloop_optimizer"
REPO_ROOT / "tests"

and also expects paths such as docs/architecture.md, docs/authoring.md, and autoloop/workflows/autoloop_v1/prompts/README.md to be part of the scan.

That is stale. Adjust it to scan only maintained roots:

autoloop/
autoloop_optimizer/
tests/

And exclude archived/optional workflow-package tests if those are kept in the repo.

Do keep strictness checks for:

no sync provider fallback in runtime providers
no removed public route-contract symbols
no reintroduction of thread-pool branch-group execution
no stale workflow.primitives import surface
no legacy class handler support in simple authoring

Do not scan missing docs or missing workflow packages.

C. Keep these files

These still look aligned with current v3 behavior.

Keep contract tests
tests/contract/test_async_engine_spine.py
tests/contract/test_async_step_dispatcher.py
tests/contract/test_branch_group_runtime.py
tests/contract/test_canonical_runtime_contracts.py
tests/contract/test_engine_contracts.py   # after splitting/removing docs assertion

Branch groups, async dispatcher behavior, engine contracts, route finalization, runtime controls, and canonical runtime schemas are current framework concerns.

Keep runtime infrastructure tests
tests/runtime/test_golden_workflow.py
tests/runtime/test_history.py
tests/runtime/test_optional_extensions.py
tests/runtime/test_progress_worklists.py
tests/runtime/test_provider_backends.py
tests/runtime/test_provider_policy_config.py
tests/runtime/test_provider_policy_emitters.py
tests/runtime/test_provider_policy_steps.py
tests/runtime/test_runtime_cli_metadata_integration.py
tests/runtime/test_runtime_git_tracking.py
tests/runtime/test_runtime_providers.py
tests/runtime/test_runtime_static_graph.py
tests/runtime/test_runtime_tracing.py
tests/runtime/test_workflow_catalog_roots.py
tests/runtime/test_workflow_reference_resolution.py
tests/runtime/test_workspace_and_context.py

Important nuance: files like test_golden_workflow.py, test_workflow_catalog_roots.py, test_workflow_reference_resolution.py, and test_workspace_and_context.py mention workflows, but they mostly generate workflow packages under tmp_path. That is current behavior and should stay.

The runtime loader still has logic for workflows and autoloop.workflows namespaces; for example, current loader code evicts stale workflows.* and autoloop.workflows.* modules when resolving workflow packages. So tests for generated workflow-package discovery remain valid.

Keep unit tests
tests/unit/test_branch_group_context_sessions.py
tests/unit/test_primitives_and_stores.py
tests/unit/test_provider_boundary_core.py
tests/unit/test_provider_policy.py
tests/unit/test_provider_retries.py
tests/unit/test_sdk_facade.py
tests/unit/test_simple_surface.py       # after deleting old package-export tests
tests/unit/test_stdlib_progress_worklists.py
tests/unit/test_validation.py
tests/unit/test_worklist_selectors.py
tests/unit/test_optimization_helpers.py # after replacing repo package fixture

These cover maintained modules and public API surfaces.

D. Cleanup actions by priority
Priority 1: unblock collection

Do these first:

delete/archive tests/runtime/test_workflow_integration_parity.py
remove top-level autoloop.workflows imports from tests/unit/test_stdlib_and_extensions.py
delete/archive tests/test_architecture_baseline_docs.py
rewrite or delete tests/runtime/test_wheel_packaging_smoke.py

This removes the hard failures caused by missing autoloop.workflows and missing repo asset assumptions.

Priority 2: quarantine package regression suites

Move the 15 workflow-package runtime tests into an optional suite:

tests/workflow_packages/

Add a guard in conftest.py or a marker:

pytest.mark.workflow_packages

Default CI should exclude it:

pytest -m "not workflow_packages"

The optional suite should run only when:

autoloop/workflows/
docs/workflows/
Workflow_Instructions.md

are present.

Priority 3: replace repo-copy fixtures

Replace helpers that do:

copytree(REPO_ROOT / "autoloop" / "workflows" / ...)
copytree(REPO_ROOT / "docs", ...)

with synthetic fixture packages created in tmp_path.

This affects at least:

tests/unit/test_optimization_helpers.py
some tests inside tests/unit/test_stdlib_and_extensions.py
all archived workflow-package runtime files if kept optional
Priority 4: split monoliths

Split:

tests/contract/test_engine_contracts.py
tests/unit/test_stdlib_and_extensions.py

These are doing too much. Splitting will make stale assumptions much easier to detect.

E. Revised delete / keep / edit matrix
File/group	Action	Reason
test_workflow_integration_parity.py	Delete/archive	Pure autoloop_v1 parity and old phase/runtime shape
test_architecture_baseline_docs.py	Delete/archive	Assumes absent docs, recursive templates, bundled workflows
test_wheel_packaging_smoke.py	Rewrite	Current assertion is packaged workflow assets, not framework wheel
15 workflow-package runtime files	Move optional/archive	Depend on absent autoloop/workflows and docs
test_stdlib_and_extensions.py	Keep but split/fix imports	Valuable helper tests, but top-level absent workflow imports
test_simple_surface.py	Keep but remove 2 tests	Public API valid; bundled workflow import assertions stale
test_engine_contracts.py	Keep but split/remove docs test	Core coverage valuable; docs assertion stale
test_package_cli.py	Keep but remove recursive template tests	CLI tests valid; recursive wrapper absent
test_optimization_helpers.py	Keep but rewrite selected workflow fixture	Optimizer valid; copied package fixture stale
test_no_compat.py	Keep but reduce scan roots	Strictness useful; missing docs/workflow expectations stale
catalog/reference/workspace runtime tests	Keep	They generate fixture workflows and test current loader/runtime behavior
Bottom line

The suite is not simply “too large”; it is mixing current framework contracts with removed bundled workflow-package contracts.

The cleanup should not weaken coverage. It should remove or quarantine tests for assets that are no longer in the checkout:

autoloop/workflows/*
docs/*
recursive_autoloop/*
autoloop_v1 parity assets
old autoloop.framework package workflows

The maintained default suite should focus on:

core compiler/engine/runtime
branch groups
provider boundaries
provider policy
runtime loader/catalog/workspace
SDK facade
simple authoring API
stdlib helpers
extensions
optimizer helpers
generated workflow fixtures

After this cleanup, the test suite should become smaller, collectable, and much more representative of the current Autoloop v3 framework.
