Finish the stale-test cleanup by repairing the retained split tests under `tests/` only.

The earlier run successfully removed most clearly stale or misowned coverage from `tests/`, but the final source-level split of the retained monoliths introduced regressions and left one repo-owned workflow import behind.

Required follow-up:

1. Fix the retained split modules so moved tests import all required shared helpers explicitly.
   - The current split files such as `tests/contract/engine/test_artifacts.py` and `tests/unit/stdlib/test_authoring_helpers.py` use `from ... import *`, but the helpers they rely on are underscore-prefixed in `_shared.py` modules and are therefore not imported.
   - Repair this without restoring the removed monolith entrypoints.

2. Update `tests/strictness/test_no_compat.py` for the new split layout.
   - It still asserts that `tests/contract/test_engine_contracts.py` exists in the scan set even though that file was removed.

3. Remove the remaining direct imports of repo-owned workflow-package modules from retained shared tests.
   - At minimum, replace the imports in `tests/unit/stdlib/test_authoring_helpers.py` that currently read from `autoloop.workflows.workflow_and_eval_to_refined_workflow_package.params` and `autoloop.workflows.workflow_package_to_composable_building_blocks.params`.
   - Use local or synthetic parameter models/fixtures instead of repo-owned workflow modules.

4. Preserve the already-completed cleanup.
   - Do not restore the deleted parity/docs/workflow-package runtime suites to `tests/`.
   - Keep the work limited to `tests/`.

Validation target:

- `.venv/bin/python -m pytest tests/strictness/test_no_compat.py tests/contract tests/unit -q`

This follow-up should be considered complete only when the retained split suite is green and no retained shared test depends directly on repo-owned workflow-package modules.
