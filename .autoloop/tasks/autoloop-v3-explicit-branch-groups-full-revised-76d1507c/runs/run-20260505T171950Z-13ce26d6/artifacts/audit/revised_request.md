Add the missing branch-group regression coverage that is still required by the explicit-branch-groups v1 request. Do not rerun the whole feature and do not widen scope beyond branch-group runtime/checkpoint behavior.

Focus only on these unresolved items:

1. Add committed runtime/contract coverage proving that real branch execution preserves the requested shared-effect semantics:
   - branch `ctx.state` assignment reaches the shared parent state cell;
   - branch `ctx.values` mutation is visible after branch settlement;
   - overlapping writes to the same workspace path are not rejected by the framework.

2. Add committed runtime/contract coverage for the fan-in pending-input path:
   - make an authored fan-in step ask for input;
   - assert the workflow checkpoints at the composite boundary under the branch-group step;
   - resume normally and assert downstream completion after the answer is provided.

If any of these new tests fail, implement only the minimal fix needed in the branch-group runtime/checkpoint path to satisfy the requested behavior.
