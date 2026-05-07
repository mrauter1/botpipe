Follow-up implementation request:

Complete the remaining SDK/runtime contract gaps without reopening the full original task.

1. Fix runtime `ctx.input.message` rendering so every `ctx.*` template path uses the composite input view.
   - `ctx.input.message` must resolve from the runtime message even when no typed `Workflow.Input` instance exists.
   - When typed input exists, `ctx.input.message` must still resolve from the runtime message, while `ctx.input.<field>` continues to read typed fields.
   - This must work for runtime artifact templates and workflow-step child message rendering, not only for bare `{input.message}` placeholders.

2. Broaden `Autoloop.step(...)` to accept directly resolvable strict `ChildWorkflowStep` instances.
   - Keep rejecting branch-group, worklist-scoped, and unresolved child-workflow declarations.
   - Route the accepted strict child-workflow case through the same synthetic one-step workflow execution path used for other supported core `Step` instances.

3. Add focused regression coverage and rerun the SDK/runtime slice.
   - Cover message-only and typed-input `ctx.input.message` rendering at the runtime-template level.
   - Cover a successful directly-resolvable strict `ChildWorkflowStep` call through `client.step(...)` and an unresolved-reference failure path.
   - Finish with the focused SDK/runtime regression slice passing.
